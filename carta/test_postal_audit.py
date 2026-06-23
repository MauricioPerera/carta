"""Tests for T21: selection_sha in run() + Postal audit receipts.

Test 1 verifies the ``selection_sha`` field wired into ``CartaAgent.run()``'s
return value (using the same mocked-_chat pattern as ``test_carta.py``, no
network), plus a direct check that ``selection_sha`` over a real selection is
a 64-char hex digest.

Test 2 verifies :func:`carta.postal_audit.sign_run_receipt` writes a valid,
signed, verifiable JSON receipt. It is skipped when Postal (and therefore
``cryptography``) is not importable.
"""
from __future__ import annotations

import json
import os
import re

import pytest

from carta import CartaAgent
from carta.selector import select_tools, selection_sha

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_N8N = os.path.join(_REPO_ROOT, "okf", "n8n")

_HEX64 = re.compile(r"^[0-9a-f]{64}$")


# --------------------------------------------------------------------------- #
# Test 1 — run() returns selection_sha
# --------------------------------------------------------------------------- #
def test_run_returns_selection_sha(monkeypatch):
    """run() result carries a non-empty selection_sha string."""
    agent = CartaAgent([_N8N], model="stub")

    replies = iter(['{"route":"rest","command":"echo hola"}', "done"])

    def fake_chat(self, messages):  # noqa: ANN001
        return next(replies)

    monkeypatch.setattr(CartaAgent, "_chat", fake_chat)

    result = agent.run("echo hola and finish")
    assert "selection_sha" in result, "run() must return selection_sha"
    assert isinstance(result["selection_sha"], str)
    assert result["selection_sha"], "selection_sha must be non-empty"


def test_selection_sha_is_hex64():
    """selection_sha over a real selection is a 64-char lowercase hex digest."""
    docs = select_tools("create workflow webhook", okf_path=_N8N)
    sha = selection_sha(docs)
    assert _HEX64.match(sha), f"expected 64-char hex SHA-256, got: {sha!r}"


# --------------------------------------------------------------------------- #
# Test 2 — sign_run_receipt
# --------------------------------------------------------------------------- #
def test_sign_run_receipt(tmp_path):
    """sign_run_receipt writes a signed, verifiable JSON receipt."""
    pytest.importorskip("postal")
    from postal.crypto import verify, generate_keypair
    from postal.identity import Identity

    from carta.postal_audit import sign_run_receipt

    priv, pub = generate_keypair()
    identity = Identity(id="test-agent", private_key=priv, public_key=pub)

    path = sign_run_receipt(
        identity,
        task="test task",
        selection_sha="abc123",
        ccdd_sha="",
        status="done",
        postal_dir=str(tmp_path),
    )

    # File exists and is valid JSON with the expected fields.
    assert os.path.isfile(path), f"receipt file not written: {path}"
    with open(path, "r", encoding="utf-8") as f:
        receipt = json.load(f)

    for field in ("agent_id", "task", "selection_sha", "signature"):
        assert field in receipt, f"missing field {field!r}: {receipt}"
    assert receipt["agent_id"] == "test-agent"
    assert receipt["task"] == "test task"
    assert receipt["selection_sha"] == "abc123"

    # Verify the signature over the canonical (sorted, compact) receipt minus
    # the signature field itself.
    payload = {k: receipt[k] for k in sorted(receipt) if k != "signature"}
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    assert verify(pub, canonical, receipt["signature"]), "signature did not verify"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])