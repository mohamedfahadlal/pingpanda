"""Tests for checkpoint persistence and validation."""

import json

import pytest

from pingpanda.checkpoint import (
    CheckpointError,
    load_checkpoint,
    save_checkpoint,
)


def test_checkpoint_round_trip_preserves_completed_results(tmp_path, make_result):
    urls = ["https://first.test", "second.test"]
    results = {
        0: make_result(url=urls[0], url_id=0, status=200),
        1: make_result(url="https://second.test", url_id=1, status=404),
    }
    path = tmp_path / "state" / "scan.json"

    save_checkpoint(path, urls, results)
    restored = load_checkpoint(path, urls)

    assert list(restored) == [0, 1]
    assert restored[0] == results[0]
    assert restored[1] == results[1]


def test_checkpoint_round_trip_preserves_attempt_count(tmp_path, make_result):
    urls = ["https://example.com"]
    result = make_result(url=urls[0], attempts=3)
    path = tmp_path / "scan.json"

    save_checkpoint(path, urls, {0: result})

    assert load_checkpoint(path, urls)[0].attempts == 3


def test_checkpoint_rejects_changed_or_reordered_input(tmp_path, make_result):
    urls = ["https://first.test", "https://second.test"]
    path = tmp_path / "scan.json"
    save_checkpoint(path, urls, {0: make_result(url=urls[0], url_id=0)})

    with pytest.raises(CheckpointError, match="different ordered URL list"):
        load_checkpoint(path, list(reversed(urls)))


def test_checkpoint_rejects_corrupt_json(tmp_path):
    path = tmp_path / "scan.json"
    path.write_text("{not-json", encoding="utf-8")

    with pytest.raises(CheckpointError, match="Could not read checkpoint"):
        load_checkpoint(path, ["https://example.com"])


def test_checkpoint_rejects_invalid_result_fields(tmp_path, make_result):
    urls = ["https://example.com"]
    path = tmp_path / "scan.json"
    save_checkpoint(path, urls, {0: make_result(url=urls[0], url_id=0)})

    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["completed"]["0"]["elapsed"] = float("nan")
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(CheckpointError, match="Invalid checkpoint result"):
        load_checkpoint(path, urls)


def test_checkpoint_rejects_unsupported_version(tmp_path):
    path = tmp_path / "scan.json"
    path.write_text(
        json.dumps(
            {
                "version": 999,
                "input_hash": "unused",
                "urls": ["https://example.com"],
                "completed": {},
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(CheckpointError, match="Unsupported checkpoint version"):
        load_checkpoint(path, ["https://example.com"])


def test_save_checkpoint_rejects_result_for_another_url(tmp_path, make_result):
    urls = ["https://example.com"]
    result = make_result(url="https://different.test", url_id=0)

    with pytest.raises(CheckpointError, match="does not match"):
        save_checkpoint(tmp_path / "scan.json", urls, {0: result})
