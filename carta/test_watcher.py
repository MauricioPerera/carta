"""Tests for T30: ``carta watch`` swarm orchestrator (carta.watcher)."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from carta.watcher import find_agent_spec, scan_pending, watch


# ----------------------------------------------------------------- helpers
def _write(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj), encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _coder_spec(tmp_path: Path) -> Path:
    """Write a minimal valid agent-spec for ``coder-agent`` under tmp_path."""
    spec = tmp_path / "agent-specs" / "coder-agent.yaml"
    spec.parent.mkdir(parents=True, exist_ok=True)
    spec.write_text(
        "\n".join(
            [
                "id: coder-agent",
                "model:",
                "  base_url: http://localhost:1234/v1",
                "  name: test-model",
                "knowledge: []",
                "triggers: [{type: mailbox}]",
            ]
        ),
        encoding="utf-8",
    )
    return spec


# ----------------------------------------------------------- find_agent_spec
def test_find_agent_spec_found(tmp_path):
    specs = tmp_path / "agent-specs"
    specs.mkdir()
    (specs / "coder-agent.yaml").write_text("id: coder-agent\n", encoding="utf-8")
    result = find_agent_spec("coder-agent", str(specs))
    assert result is not None
    assert os.path.isabs(result)
    assert os.path.basename(result) == "coder-agent.yaml"


def test_find_agent_spec_fallback(tmp_path):
    specs = tmp_path / "agent-specs"
    specs.mkdir()
    (specs / "coder-agent.yaml").write_text("id: coder-agent\n", encoding="utf-8")
    # "coder" does not end in -agent, so the -agent fallback is tried.
    result = find_agent_spec("coder", str(specs))
    assert result is not None
    assert os.path.basename(result) == "coder-agent.yaml"


def test_find_agent_spec_missing(tmp_path):
    specs = tmp_path / "agent-specs"
    specs.mkdir()
    assert find_agent_spec("unknown", str(specs)) is None


# ------------------------------------------------------------- scan_pending
def test_scan_pending_empty(tmp_path):
    inbox = tmp_path / ".postal" / "inbox"
    inbox.mkdir(parents=True)
    assert scan_pending(str(tmp_path / ".postal")) == []


def test_scan_pending_one_message(tmp_path):
    inbox = tmp_path / ".postal" / "inbox" / "coder-agent"
    _write(
        inbox / "1700000000-msg1.json",
        {
            "id": "msg1",
            "task": "build X",
            "from": "spec-agent",
            "to": "coder-agent",
            "timestamp": "2024-01-01T00:00:00",
        },
    )
    items = scan_pending(str(tmp_path / ".postal"))
    assert len(items) == 1
    assert items[0]["agent_id"] == "coder-agent"
    assert items[0]["message"]["id"] == "msg1"
    assert "path" in items[0]


def test_scan_pending_orders_by_timestamp(tmp_path):
    inbox = tmp_path / ".postal" / "inbox" / "coder-agent"
    _write(
        inbox / "b.json",
        {"id": "b", "task": "two", "timestamp": "2024-02-01T00:00:00"},
    )
    _write(
        inbox / "a.json",
        {"id": "a", "task": "one", "timestamp": "2024-01-01T00:00:00"},
    )
    items = scan_pending(str(tmp_path / ".postal"))
    ids = [it["message"]["id"] for it in items]
    assert ids == ["a", "b"]


# ------------------------------------------------------------------- watch
def test_watch_idle_stops(tmp_path):
    (tmp_path / ".postal" / "inbox").mkdir(parents=True)
    result = watch(
        str(tmp_path), idle_stop=1, poll_interval=0, max_rounds=50
    )
    assert result == {"stopped_reason": "idle", "rounds": 1, "processed": []}


def test_watch_processes_message(tmp_path, monkeypatch):
    inbox = tmp_path / ".postal" / "inbox" / "coder-agent"
    _write(
        inbox / "1700000000-msg1.json",
        {
            "id": "msg1",
            "task": "build X",
            "from": "spec-agent",
            "to": "coder-agent",
            "timestamp": "2024-01-01T00:00:00",
        },
    )
    (tmp_path / ".postal" / "processed").mkdir(parents=True)
    _coder_spec(tmp_path)

    # Avoid any real LLM call: short-circuit CartaAgent construction and run.
    monkeypatch.setattr(
        "carta.agent.CartaAgent.__init__",
        lambda self, **kw: None,
    )
    monkeypatch.setattr(
        "carta.agent.CartaAgent.run",
        lambda self, task, max_steps=8, provider=None: {
            "steps": [],
            "answer": "done",
        },
    )

    result = watch(str(tmp_path), poll_interval=0, idle_stop=1, max_rounds=50)
    assert result["stopped_reason"] == "idle"
    assert "coder-agent" in result["processed"]
    processed_file = tmp_path / ".postal" / "processed" / "msg1.json"
    assert processed_file.exists()
    payload = json.loads(processed_file.read_text(encoding="utf-8"))
    assert payload["message_id"] == "msg1"


def test_watch_skip_unknown_agent(tmp_path):
    inbox = tmp_path / ".postal" / "inbox" / "ghost-agent"
    _write(
        inbox / "1700000000-g1.json",
        {
            "id": "ghost-1",
            "task": "boo",
            "from": "spec-agent",
            "to": "ghost-agent",
            "timestamp": "2024-01-01T00:00:00",
        },
    )
    (tmp_path / ".postal" / "processed").mkdir(parents=True)
    # No agent-specs/ghost-agent.yaml exists.
    result = watch(str(tmp_path), poll_interval=0, idle_stop=1, max_rounds=50)
    assert result["stopped_reason"] == "idle"
    assert result["processed"] == []
    assert (tmp_path / ".postal" / "processed" / "ghost-1.json").exists()


def test_watch_max_rounds(tmp_path, monkeypatch):
    # scan_pending always reports one pending message; mark_processed is a no-op
    # so the same message would otherwise loop forever.
    monkeypatch.setattr(
        "carta.watcher.scan_pending",
        lambda postal_dir: [
            {
                "agent_id": "coder-agent",
                "message": {"id": "loop", "task": "again"},
                "path": "x/loop.json",
            }
        ],
    )
    monkeypatch.setattr(
        "carta.mailbox.mark_processed",
        lambda message_id, processed_dir, result: None,
    )
    result = watch(
        str(tmp_path), max_rounds=3, poll_interval=0, idle_stop=1
    )
    assert result["stopped_reason"] == "max_rounds"
    assert result["rounds"] == 3


def test_watch_cli_help():
    proc = subprocess.run(
        [sys.executable, "-m", "carta", "watch", "--help"],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    assert "poll" in proc.stdout.lower()