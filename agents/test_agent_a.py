"""Test for Agent A CLI: runs it as a subprocess and checks it publishes."""
import os
import shutil
import subprocess
import sys

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_AGENT = os.path.join(_REPO_ROOT, "agents", "agent_a.py")
_POSTAL = os.path.join(_REPO_ROOT, ".postal")


def _clean_postal():
    """Remove .postal/users and .postal/messages so each test run is fresh."""
    for sub in ("users", "messages"):
        p = os.path.join(_POSTAL, sub)
        if os.path.isdir(p):
            shutil.rmtree(p, ignore_errors=True)


def test_agent_a_runs():
    _clean_postal()
    try:
        result = subprocess.run(
            [sys.executable, _AGENT],
            cwd=_REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert result.returncode == 0, (
            f"agent_a exited {result.returncode}\nstdout={result.stdout}\nstderr={result.stderr}"
        )
        # stdout must report the three identifiers
        assert "message_id=" in result.stdout
        assert "okf_sha=" in result.stdout
        assert "ccdd_sha=" in result.stdout

        # .postal/messages/ must contain at least one .json
        msgs_dir = os.path.join(_POSTAL, "messages")
        assert os.path.isdir(msgs_dir), "messages dir was not created"
        jsons = [n for n in os.listdir(msgs_dir) if n.endswith(".json")]
        assert len(jsons) > 0, "no message files were written"
    finally:
        pass