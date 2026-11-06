"""Validated, atomic checkpoint storage for resumable URL scans."""

from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
from pathlib import Path

from pingpanda.models import UrlResult

CHECKPOINT_VERSION = 1


class CheckpointError(Exception):
    """Raised when a checkpoint cannot safely be read or written."""


def _normalized_url(url: str) -> str:
    url = url.strip()
    return url if "://" in url else "https://" + url


def _input_hash(urls: list[str]) -> str:
    serialized = json.dumps(urls, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def save_checkpoint(
    path: str | Path,
    urls: list[str],
    results: dict[int, UrlResult],
) -> None:
    """Atomically persist completed results for the exact ordered input list."""
    path = Path(path)

    completed = {}
    for url_id, result in sorted(results.items()):
        if isinstance(url_id, bool) or not isinstance(url_id, int):
            raise CheckpointError("A completed result has an invalid URL ID.")
        if not 0 <= url_id < len(urls):
            raise CheckpointError(f"URL ID {url_id} is outside the input list.")
        if not isinstance(result, UrlResult):
            raise CheckpointError(f"Result {url_id} is not a UrlResult.")
        if result.url_id != url_id or result.url != _normalized_url(urls[url_id]):
            raise CheckpointError(f"Result {url_id} does not match its input URL.")

        completed[str(url_id)] = {
            "url_id": result.url_id,
            "url": result.url,
            "status": result.status,
            "elapsed": result.elapsed,
            "redirect_to": result.redirect_to,
            "ip_port": result.ip_port,
            "redirect_ip_port": result.redirect_ip_port,
            "attempts": result.attempts,
        }

    payload = {
        "version": CHECKPOINT_VERSION,
        "input_hash": _input_hash(urls),
        "urls": urls,
        "completed": completed,
    }

    temporary_path = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            json.dump(payload, temporary_file, ensure_ascii=False, indent=2)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())

        os.replace(temporary_path, path)
    except (OSError, TypeError, ValueError) as exc:
        raise CheckpointError(f"Could not save checkpoint: {exc}") from exc
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def load_checkpoint(
    path: str | Path,
    urls: list[str],
) -> dict[int, UrlResult]:
    """Load completed results after validating schema and input identity."""
    path = Path(path)
    try:
        with path.open("r", encoding="utf-8") as checkpoint_file:
            payload = json.load(checkpoint_file)
    except (OSError, json.JSONDecodeError) as exc:
        raise CheckpointError(f"Could not read checkpoint: {exc}") from exc

    if not isinstance(payload, dict):
        raise CheckpointError("Invalid checkpoint structure.")
    version = payload.get("version")
    if isinstance(version, bool) or version != CHECKPOINT_VERSION:
        raise CheckpointError("Unsupported checkpoint version.")
    if payload.get("input_hash") != _input_hash(urls) or payload.get("urls") != urls:
        raise CheckpointError("Checkpoint belongs to a different ordered URL list.")

    completed = payload.get("completed")
    if not isinstance(completed, dict):
        raise CheckpointError("Invalid completed-results section.")

    results = {}
    for key, item in completed.items():
        try:
            url_id = int(key)
            if str(url_id) != key or not 0 <= url_id < len(urls):
                raise ValueError("Invalid URL ID.")
            if url_id in results or not isinstance(item, dict):
                raise ValueError("Duplicate URL ID or invalid result object.")

            status = item["status"]
            elapsed = item["elapsed"]
            redirect_to = item["redirect_to"]
            redirect_ip_port = item["redirect_ip_port"]
            result_url = item["url"]
            result_id = item["url_id"]
            ip_port = item["ip_port"]
            attempts = item.get("attempts", 1)

            if (
                isinstance(result_id, bool)
                or not isinstance(result_id, int)
                or result_id != url_id
                or result_url != _normalized_url(urls[url_id])
                or (
                    status is not None
                    and (isinstance(status, bool) or not isinstance(status, int))
                )
                or isinstance(elapsed, bool)
                or not isinstance(elapsed, (int, float))
                or not math.isfinite(elapsed)
                or elapsed < 0
                or (redirect_to is not None and not isinstance(redirect_to, str))
                or not isinstance(ip_port, str)
                or isinstance(attempts, bool)
                or not isinstance(attempts, int)
                or attempts < 1
                or (
                    redirect_ip_port is not None
                    and not isinstance(redirect_ip_port, str)
                )
            ):
                raise ValueError("Invalid result fields.")

            results[url_id] = UrlResult(
                url_id=url_id,
                url=result_url,
                status=status,
                elapsed=float(elapsed),
                redirect_to=redirect_to,
                ip_port=ip_port,
                redirect_ip_port=redirect_ip_port,
                attempts=attempts,
            )
        except (KeyError, TypeError, ValueError, OverflowError) as exc:
            raise CheckpointError(
                f"Invalid checkpoint result for URL ID {key}: {exc}"
            ) from exc

    return dict(sorted(results.items()))
