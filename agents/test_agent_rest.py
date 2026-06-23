"""Tests T10 — Agent REST (ruta REST, sin MCP)."""
from __future__ import annotations

import os
import subprocess
import sys

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_AGENTS = os.path.join(_REPO_ROOT, "agents")
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from carta.selector import select_tools, _parse_frontmatter  # noqa: E402

JP_OKF = os.path.join(_REPO_ROOT, "okf", "jsonplaceholder")


def test_rest_agent_runs():
    """Corre agent_rest.py como subprocess; exit 0 y 'TASK COMPLETE' en stdout."""
    script = os.path.join(_AGENTS, "agent_rest.py")
    result = subprocess.run(
        [sys.executable, script],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, (
        f"agent_rest exit={result.returncode}\nstdout={result.stdout}\nstderr={result.stderr}"
    )
    assert "TASK COMPLETE" in result.stdout, f"falta TASK COMPLETE:\n{result.stdout}"
    assert "route: rest" in result.stdout
    assert "no MCP server required" in result.stdout
    print("OK test_rest_agent_runs: exit=0, TASK COMPLETE presente")


def test_route_detection():
    """create_post.md tiene route=rest en su frontmatter."""
    path = os.path.join(JP_OKF, "tools", "create_post.md")
    with open(path, encoding="utf-8") as f:
        text = f.read()
    fm, _body = _parse_frontmatter(text)
    assert fm.get("route") == "rest", f"expected route=rest, got {fm.get('route')!r}"
    print("OK test_route_detection: create_post route=rest")


def test_provider_flag():
    """tool_selector with provider=jsonplaceholder finds the publish-content skill."""
    docs = select_tools(
        "Publish a post titled OKF Demo and verify it exists",
        okf_path=JP_OKF,
    )
    names = [d["name"] for d in docs]
    assert "publish-content" in names, f"missing skill publish-content: {names}"
    # The skill pulls in the 3 tools
    for t in ("create_post", "get_posts", "get_user"):
        assert t in names, f"missing tool {t}: {names}"
    print("OK test_provider_flag:", names)


if __name__ == "__main__":
    test_route_detection()
    test_provider_flag()
    test_rest_agent_runs()
    print("\nTODOS LOS TESTS OK")