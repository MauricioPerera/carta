"""Tests for T25: swarm delegation via send_to_agent.

Covers the pure helper in :mod:`carta.swarm` and the ``route='internal'``
branch wired into :meth:`CartaAgent.run`. No network: the agent test mocks
``CartaAgent._chat`` with scripted replies (same pattern as
``test_carta.py`` / ``test_postal_audit.py``).
"""
from __future__ import annotations

import json
import os

import pytest

from carta import CartaAgent
from carta.swarm import send_to_agent

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_N8N = os.path.join(_REPO_ROOT, "okf", "n8n")


# --------------------------------------------------------------------------- #
# Pure helper
# --------------------------------------------------------------------------- #
def test_send_creates_file(tmp_path):
    """send_to_agent writes a JSON file under inbox/<to>/."""
    path = send_to_agent("a", "b", "do the thing", postal_dir=str(tmp_path))
    assert os.path.isfile(path), f"file not written: {path}"
    assert os.path.dirname(path) == os.path.join(str(tmp_path), "inbox", "b")


def test_send_message_fields(tmp_path):
    """The written message has id/from/to/task/timestamp and no signature."""
    path = send_to_agent("alice", "bob", "schedule it", postal_dir=str(tmp_path))
    with open(path, "r", encoding="utf-8") as f:
        msg = json.load(f)
    for field in ("id", "from", "to", "task", "timestamp"):
        assert field in msg, f"missing field {field!r}: {msg}"
    assert msg["from"] == "alice"
    assert msg["to"] == "bob"
    assert msg["task"] == "schedule it"
    assert "signature" not in msg, "unsigned message must not carry a signature"


def test_send_signed(tmp_path):
    """With an identity, the message carries a verifiable signature."""
    pytest.importorskip("postal")
    from postal.crypto import generate_keypair, verify
    from postal.identity import Identity

    priv, pub = generate_keypair()
    identity = Identity(id="alice", private_key=priv, public_key=pub)

    path = send_to_agent(
        "alice",
        "bob",
        "sign me",
        postal_dir=str(tmp_path),
        identity=identity,
        selection_sha="abc123",
    )
    with open(path, "r", encoding="utf-8") as f:
        msg = json.load(f)

    assert "signature" in msg, "signed message must carry a signature"
    assert msg["selection_sha"] == "abc123"

    payload = {k: msg[k] for k in sorted(msg) if k != "signature"}
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    assert verify(pub, canonical, msg["signature"]), "signature did not verify"


def test_send_agent_specific_inbox(tmp_path):
    """Messages to different recipients land in separate inbox folders."""
    p_b = send_to_agent("a", "b", "for b", postal_dir=str(tmp_path))
    p_c = send_to_agent("a", "c", "for c", postal_dir=str(tmp_path))
    assert os.path.dirname(p_b) == os.path.join(str(tmp_path), "inbox", "b")
    assert os.path.dirname(p_c) == os.path.join(str(tmp_path), "inbox", "c")
    assert os.path.isfile(p_b) and os.path.isfile(p_c)


# --------------------------------------------------------------------------- #
# Agent loop integration
# --------------------------------------------------------------------------- #
def test_agent_run_send_to_agent(monkeypatch, tmp_path):
    """run() executes route='internal' send_to_agent and writes the file."""
    agent = CartaAgent([_N8N], model="stub")
    agent._agent_id = "orchestrator"
    agent._postal_dir_base = str(tmp_path)

    replies = iter(
        [
            '{"tool":"send_to_agent","route":"internal","args":{"to":"calendar-agent","task":"schedule meeting"}}',
            "done",
        ]
    )

    def fake_chat(self, messages):  # noqa: ANN001
        return next(replies)

    monkeypatch.setattr(CartaAgent, "_chat", fake_chat)

    result = agent.run("delegate the meeting scheduling")
    send_steps = [s for s in result["steps"] if s.get("type") == "send_to_agent"]
    assert len(send_steps) == 1, f"expected one send_to_agent step: {result['steps']}"
    step = send_steps[0]
    assert step["to"] == "calendar-agent"
    assert os.path.isfile(step["path"]), f"deposited file missing: {step['path']}"

    with open(step["path"], "r", encoding="utf-8") as f:
        msg = json.load(f)
    assert msg["to"] == "calendar-agent"
    assert msg["task"] == "schedule meeting"
    assert msg["from"] == "orchestrator"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])