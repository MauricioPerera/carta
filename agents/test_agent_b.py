"""Tests for Agent B CLI.

Both tests drive the CLIs as subprocesses (no foreground processes). The full
flow establishes Agent B's identity in-process first so that the first agent
*subprocess* is `agent_a` (per the T5 spec), then runs `agent_b` to consume.
"""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import uuid

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_AGENT_A = os.path.join(_REPO_ROOT, "agents", "agent_a.py")
_AGENT_B = os.path.join(_REPO_ROOT, "agents", "agent_b.py")
_POSTAL = os.path.join(_REPO_ROOT, ".postal")
_USERS = os.path.join(_POSTAL, "users")
_MESSAGES = os.path.join(_POSTAL, "messages")


def _clean_postal():
    """Remove .postal/users and .postal/messages so each test run is fresh."""
    for sub in ("users", "messages"):
        p = os.path.join(_POSTAL, sub)
        if os.path.isdir(p):
            shutil.rmtree(p, ignore_errors=True)


def _load_agent_b_module():
    """Import agents/agent_b.py as a module (to call _ensure_identity in-process)."""
    spec = importlib.util.spec_from_file_location("agent_b_under_test", _AGENT_B)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _run(agent_path):
    return subprocess.run(
        [sys.executable, agent_path],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_agent_b_full_flow():
    _clean_postal()
    # Establish Agent B's identity in-process (writes .postal/users/agent-b.json
    # with both keys) so agent_a can encrypt to Agent B's real pubkey. This is
    # setup, not an agent run — the first agent subprocess below is agent_a.
    agent_b_mod = _load_agent_b_module()
    agent_b_mod._ensure_identity()
    assert os.path.isfile(os.path.join(_USERS, "agent-b.json"))

    try:
        # 1. Agent A publishes (first agent subprocess).
        r_a = _run(_AGENT_A)
        assert r_a.returncode == 0, (
            f"agent_a exited {r_a.returncode}\nstdout={r_a.stdout}\nstderr={r_a.stderr}"
        )
        assert "message_id=" in r_a.stdout

        # 2. Agent B consumes.
        r_b = _run(_AGENT_B)
        assert r_b.returncode == 0, (
            f"agent_b exited {r_b.returncode}\nstdout={r_b.stdout}\nstderr={r_b.stderr}"
        )
        assert "CONTEXT REPRODUCED" in r_b.stdout, (
            f"expected CONTEXT REPRODUCED\nstdout={r_b.stdout}\nstderr={r_b.stderr}"
        )
    finally:
        pass


def test_agent_b_detects_invalid_signature():
    _clean_postal()
    # Create an Agent A identity (pubkey-only) so agent_b can load from_pubkey.
    from postal import generate_keypair, Identity, save_identity

    priv_a, pub_a = generate_keypair()
    save_identity(Identity(id="agent-a", private_key=priv_a, public_key=pub_a), _POSTAL)

    # Write a corrupt message addressed to agent-b with an invalid signature.
    corrupt = {
        "id": str(uuid.uuid4()),
        "from": "agent-a",
        "to": "agent-b",
        "okf_snapshot_sha": "0" * 64,
        "ccdd_contract_sha": "1" * 64,
        "payload": "deadbeef",
        "ephemeral_pubkey": "deadbeef",
        "signature": "deadbeef",  # invalid → verification must fail
        "timestamp": "2026-06-22T00:00:00+00:00",
    }
    os.makedirs(_MESSAGES, exist_ok=True)
    with open(os.path.join(_MESSAGES, f"{corrupt['id']}.json"), "w", encoding="utf-8") as f:
        json.dump(corrupt, f, indent=2, sort_keys=True)

    try:
        r_b = _run(_AGENT_B)
        assert r_b.returncode == 0, (
            f"agent_b exited {r_b.returncode}\nstdout={r_b.stdout}\nstderr={r_b.stderr}"
        )
        assert "POSTAL SIGNATURE INVALID" in r_b.stdout, (
            f"expected POSTAL SIGNATURE INVALID\nstdout={r_b.stdout}\nstderr={r_b.stderr}"
        )
    finally:
        pass