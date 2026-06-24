"""Tests for T23: mailbox mode helpers in carta.mailbox."""
from __future__ import annotations

import json
from pathlib import Path

from carta.mailbox import extract_task, list_unprocessed, mark_processed


def _write(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj), encoding="utf-8")


def test_list_unprocessed_empty(tmp_path):
    mailbox = tmp_path / "inbox"
    mailbox.mkdir()
    processed = tmp_path / "processed"
    assert list_unprocessed(str(mailbox), str(processed)) == []


def test_list_unprocessed_filters_processed(tmp_path):
    mailbox = tmp_path / "inbox"
    processed = tmp_path / "processed"
    mailbox.mkdir()
    _write(mailbox / "a.json", {"id": "a", "task": "do a"})
    _write(mailbox / "b.json", {"id": "b", "task": "do b"})
    _write(mailbox / "c.json", {"id": "c", "task": "do c"})
    # Mark "b" as already processed.
    _write(processed / "b.json", {"message_id": "b", "result": {"status": "ok"}})
    msgs = list_unprocessed(str(mailbox), str(processed))
    ids = sorted(m["id"] for m in msgs)
    assert ids == ["a", "c"]


def test_mark_processed_creates_file(tmp_path):
    processed = tmp_path / "processed"
    path = mark_processed("msg1", str(processed), {"status": "ok", "steps": 2})
    p = Path(path)
    assert p.exists()
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data["message_id"] == "msg1"
    assert "processed_at" in data and data["processed_at"]
    assert data["result"] == {"status": "ok", "steps": 2}


def test_extract_task_direct():
    assert extract_task({"task": "haz X"}) == "haz X"


def test_extract_task_from_plaintext_json():
    msg = {"plaintext": '{"task":"haz X"}'}
    assert extract_task(msg) == "haz X"


def test_extract_task_none():
    assert extract_task({"plaintext": "no json here"}) is None
    assert extract_task({}) is None