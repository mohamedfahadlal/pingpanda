"""Resolving hosts and checking URLs asynchronously."""

from __future__ import annotations

import asyncio
import math
import socket
import time
from urllib.parse import urlparse

import httpx

from tqdm import tqdm

from pingpanda.models import UrlResult

DEFAULT_TIMEOUT_SECONDS = 10.0
DEFAULT_MAX_CONCURRENT = 10
DEFAULT_RETRIES = 0
DEFAULT_RETRY_DELAY_SECONDS = 1.0
RETRYABLE_STATUS_CODES = frozenset({408, 429, 502, 503, 504})


# Function to resolve hostname to IP:Port
async def resolve_ip_and_port(url):
    try:
        parsed = urlparse(url)
        hostname = parsed.hostname
        scheme = parsed.scheme

        if not hostname:
            return "IP:Port Not Found"

        port = parsed.port if parsed.port is not None else (
            80 if scheme == "http" else 443
        )

        loop = asyncio.get_running_loop()

        addresses = await asyncio.wait_for(
            loop.getaddrinfo(
                hostname,
                port,
                type=socket.SOCK_STREAM,
            ),
            timeout=DEFAULT_TIMEOUT_SECONDS,
        )

        if not addresses:
            return "IP:Port Not Found"

        ip_address = addresses[0][4][0]

        if ":" in ip_address:
            return f"[{ip_address}]:{port}"

        return f"{ip_address}:{port}"

    except (OSError, ValueError, asyncio.TimeoutError):
        return "IP:Port Not Found"


def normalize_url(url):
    url = url.strip()
    if "://" not in url:
        url = "https://" + url
    return url


def _validate_retry_options(max_retries, retry_delay):
    if (
        isinstance(max_retries, bool)
        or not isinstance(max_retries, int)
        or max_retries < 0
    ):
        raise ValueError("max_retries must be a non-negative integer")
    if (
        isinstance(retry_delay, bool)
        or not isinstance(retry_delay, (int, float))
        or not math.isfinite(retry_delay)
    ):
        raise ValueError("retry_delay must be a non-negative number")
    if retry_delay < 0:
        raise ValueError("retry_delay must be a non-negative number")


def _is_retryable_exception(exc):
    return not isinstance(exc, httpx.TooManyRedirects)


async def check_url_status(
    session,
    url_id,
    url,
    max_retries=DEFAULT_RETRIES,
    retry_delay=DEFAULT_RETRY_DELAY_SECONDS,
):
    _validate_retry_options(max_retries, retry_delay)
    url = normalize_url(url)
    started = time.perf_counter()
    attempts = 0

    while True:
        attempts += 1
        try:
            response = await asyncio.wait_for(
                session.get(
                    url,
                    follow_redirects=True,
                    timeout=httpx.Timeout(DEFAULT_TIMEOUT_SECONDS, read=None),
                ),
                timeout=DEFAULT_TIMEOUT_SECONDS,
            )
        except (httpx.RequestError, asyncio.TimeoutError) as exc:
            if attempts <= max_retries and (
                not isinstance(exc, httpx.RequestError)
                or _is_retryable_exception(exc)
            ):
                await asyncio.sleep(retry_delay * 2 ** (attempts - 1))
                continue

            elapsed = time.perf_counter() - started
            return UrlResult(
                url_id,
                url,
                None,
                elapsed,
                None,
                "IP:Port Not Found",
                None,
                attempts,
            )

        if response.status_code in RETRYABLE_STATUS_CODES and attempts <= max_retries:
            await response.aclose()
            await asyncio.sleep(retry_delay * 2 ** (attempts - 1))
            continue

        final_url = str(response.url)
        original_ip_port = await resolve_ip_and_port(url)
        redirect_ip_port = (
            await resolve_ip_and_port(final_url)
            if final_url != url
            else None
        )
        redirect_to = final_url if final_url != url else None

        elapsed = time.perf_counter() - started
        return UrlResult(
            url_id,
            url,
            response.status_code,
            elapsed,
            redirect_to,
            original_ip_port,
            redirect_ip_port,
            attempts,
        )


async def check_all(
    urls,
    initial_results=None,
    on_result=None,
    max_concurrent=DEFAULT_MAX_CONCURRENT,
    max_retries=DEFAULT_RETRIES,
    retry_delay=DEFAULT_RETRY_DELAY_SECONDS,
):
    """Check unfinished URLs with bounded concurrency.

    URL IDs always refer to the original input order. Existing checkpoint
    results are retained and are not requested again.
    """
    if (
        isinstance(max_concurrent, bool)
        or not isinstance(max_concurrent, int)
        or max_concurrent <= 0
    ):
        raise ValueError("max_concurrent must be a positive integer")
    _validate_retry_options(max_retries, retry_delay)

    urls = list(urls)
    results = dict(initial_results or {})

    for url_id, result in results.items():
        if (
            isinstance(url_id, bool)
            or not isinstance(url_id, int)
            or not 0 <= url_id < len(urls)
            or result.url_id != url_id
            or result.url != normalize_url(urls[url_id])
        ):
            raise ValueError(f"Initial result {url_id!r} does not match the URL list.")

    pending = [
        (url_id, url)
        for url_id, url in enumerate(urls)
        if url_id not in results
    ]

    if not pending:
        return dict(sorted(results.items()))

    url_iterator = iter(pending)
    worker_count = min(max_concurrent, len(pending))

    progress = tqdm(
        total=len(urls),
        initial=len(results),
        desc="Checking URLs",
    ) if len(urls) > 1 else None

    tasks = []

    try:
        async with httpx.AsyncClient() as session:

            async def worker():
                while True:
                    item = next(url_iterator, None)
                    if item is None:
                        return

                    url_id, url = item
                    result = await check_url_status(
                        session,
                        url_id,
                        url,
                        max_retries=max_retries,
                        retry_delay=retry_delay,
                    )
                    results[result.url_id] = result

                    if on_result is not None:
                        on_result(dict(results))

                    if progress is not None:
                        progress.update(1)

            tasks = [
                asyncio.create_task(worker())
                for _ in range(worker_count)
            ]

            await asyncio.gather(*tasks)

    except BaseException:
        for task in tasks:
            if not task.done():
                task.cancel()

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        raise

    finally:
        if progress is not None:
            progress.close()

    return dict(sorted(results.items()))
