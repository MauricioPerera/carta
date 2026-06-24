"""CLI smoke tests: ``python -m carta --help`` and ``python -m carta init --help``."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def _run(args: list[str]) -> subprocess.CompletedProcess:
    repo_root = str(Path(__file__).resolve().parents[1])
    env = dict(os.environ)
    env["PYTHONPATH"] = repo_root + os.pathsep + env.get("PYTHONPATH", "")
    return subprocess.run(
        [sys.executable, "-m", "carta", *args],
        capture_output=True,
        text=True,
        cwd=repo_root,
        env=env,
    )


def test_carta_help():
    res = _run(["--help"])
    assert res.returncode == 0, res.stdout + res.stderr
    assert "run" in res.stdout


def test_carta_init_help():
    res = _run(["init", "--help"])
    assert res.returncode == 0, res.stdout + res.stderr
    assert "init" in res.stdout