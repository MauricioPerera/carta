"""Tests for the reference MCP executors.

The real ``mcp`` package is required for the roundtrip test; if it is not
installed the whole module is skipped via ``pytest.importorskip`` so CI without
the optional dependency stays green. ``test_missing_dep_message`` runs
unconditionally and simulates the missing-dependency path.
"""
from __future__ import annotations

import os
import sys
import textwrap

import pytest

# NOTE: no module-level importorskip here. ``test_missing_dep_message`` must
# always run (it simulates the missing dependency), so the SDK-dependent
# importorskip is applied INSIDE the roundtrip test only. Importing
# ``carta.mcp_executor`` itself is always safe: the ``mcp`` package is imported
# lazily inside the executor functions.
from carta.mcp_executor import stdio_mcp_executor, _MISSING_DEP_MSG  # noqa: E402

_SERVER_SRC = textwrap.dedent(
    """\
    from mcp.server.fastmcp import FastMCP

    mcp = FastMCP("echo-server")


    @mcp.tool()
    def echo(text: str) -> str:
        '''Echo back the received text.'''
        return text


    if __name__ == "__main__":
        mcp.run()
    """
)


@pytest.fixture()
def echo_server(tmp_path):
    """Write a minimal FastMCP stdio server to a temp file; return its path."""
    server_path = tmp_path / "echo_server.py"
    server_path.write_text(_SERVER_SRC, encoding="utf-8")
    yield str(server_path)


def test_stdio_executor_roundtrip(echo_server):
    """Real roundtrip: spawn the echo server, call its 'echo' tool over stdio."""
    pytest.importorskip("mcp")  # SDK required for a real roundtrip.
    exec_mcp = stdio_mcp_executor(sys.executable, [echo_server])
    res = exec_mcp("echo", {"text": "hola"})
    assert res["ok"] is True, f"executor returned error: {res}"
    # 'hola' must appear somewhere in the JSON-serializable result.
    assert "hola" in repr(res["result"])
    # The text extractor should surface it directly.
    assert res["result"]["text"] == "hola"
    assert res["result"]["isError"] is False


def test_missing_dep_message(monkeypatch):
    """When 'mcp' is not importable, the executor raises a clear ImportError.

    Runs regardless of whether ``mcp`` is installed: we force the import to
    fail by poisoning ``sys.modules['mcp']`` (a value of ``None`` makes the
    builtin import machinery raise ``ImportError``).
    """
    monkeypatch.setitem(sys.modules, "mcp", None)
    # Also poison the already-imported submodules so the lazy import inside
    # the async helper cannot sneak through a cached parent.
    for key in list(sys.modules):
        if key == "mcp" or key.startswith("mcp."):
            monkeypatch.setitem(sys.modules, key, None)

    exec_mcp = stdio_mcp_executor(sys.executable, ["unused.py"])
    with pytest.raises(ImportError) as excinfo:
        exec_mcp("echo", {"text": "x"})
    assert "pip install mcp" in str(excinfo.value)
    assert _MISSING_DEP_MSG in str(excinfo.value)