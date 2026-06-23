"""Reference MCP executors for ``CartaAgent``.

These factories return a synchronous ``callable(tool: str, args: dict) -> dict``
suitable for passing as ``CartaAgent(mcp_executor=...)``. Each callable opens a
fresh MCP client session, calls one tool, closes the session, and returns a
plain dict so it fits into ``CartaAgent``'s synchronous loop.

The ``mcp`` package is an OPTIONAL dependency: it is imported lazily INSIDE the
factories, so importing this module (and ``carta`` itself) never fails when
``mcp`` is absent. The factories raise a clear ``ImportError`` at call time
instead.

Two transports are provided:

- :func:`stdio_mcp_executor` — launches a local MCP server as a subprocess and
  talks to it over stdio.
- :func:`http_mcp_executor` — connects to a remote MCP server exposing the
  streamable HTTP transport.

Return contract (both transports)::

    {'ok': True,  'result': <json-serializable>}   # success
    {'ok': False, 'error': str}                    # any failure
"""
from __future__ import annotations

import asyncio
from typing import Any, Callable

_MISSING_DEP_MSG = (
    "The 'mcp' package is required for MCP routes. Install: pip install mcp"
)


def _extract_content(result: Any) -> dict:
    """Reduce an MCP ``CallToolResult`` to a JSON-serializable dict.

    The SDK's content items are pydantic models with a ``type`` discriminator
    (``text``, ``image``, ``resource``). We pull out the human-relevant fields
    and also surface ``structuredContent`` when the server provides it.
    """
    items: list[Any] = []
    text_parts: list[str] = []
    for item in getattr(result, "content", []) or []:
        itype = getattr(item, "type", None)
        if itype == "text":
            text_parts.append(getattr(item, "text", ""))
            items.append({"type": "text", "text": getattr(item, "text", "")})
        elif itype == "image":
            items.append(
                {
                    "type": "image",
                    "mimeType": getattr(item, "mimeType", ""),
                    "data": getattr(item, "data", ""),
                }
            )
        elif itype == "resource":
            items.append({"type": "resource", "resource": getattr(item, "resource", None)})
        else:
            # Unknown content kind: dump its model representation if available.
            items.append({"type": itype, "raw": repr(item)})

    structured = getattr(result, "structuredContent", None)
    out: dict[str, Any] = {
        "content": items,
        "text": "\n".join(text_parts),
        "isError": bool(getattr(result, "isError", False)),
    }
    if structured is not None:
        out["structured"] = structured
    return out


async def _stdio_call(command: str, args: list[str], env: dict | None,
                      tool: str, arguments: dict) -> dict:
    from mcp import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client

    params = StdioServerParameters(command=command, args=args, env=env)
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool, arguments)
            return _extract_content(result)


async def _http_call(url: str, headers: dict | None,
                     tool: str, arguments: dict) -> dict:
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    async with streamablehttp_client(url, headers=headers) as (read, write, _get_id):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool, arguments)
            return _extract_content(result)


def stdio_mcp_executor(
    command: str,
    args: list[str] | None = None,
    env: dict | None = None,
) -> Callable[[str, dict], dict]:
    """Build a sync MCP executor that talks to a server over stdio.

    Parameters
    ----------
    command:
        Executable to launch (e.g. ``sys.executable`` or ``"npx"``).
    args:
        Argv for the executable (e.g. ``["server.py"]`` or
        ``["-y", "@modelcontextprotocol/server-..."]``).
    env:
        Optional environment override for the subprocess.

    Returns
    -------
    callable(tool, arguments) -> dict
        A synchronous function. Each call spawns a fresh server process,
        initializes the session, calls ``tool`` with ``arguments``, and returns
        ``{'ok': True, 'result': {...}}`` or ``{'ok': False, 'error': str}``.
    """
    arglist = list(args or [])

    def exec_mcp(tool: str, arguments: dict) -> dict:
        try:
            import mcp  # noqa: F401  — surface a clear error if missing
        except ImportError:
            raise ImportError(_MISSING_DEP_MSG) from None
        try:
            result = asyncio.run(
                _stdio_call(command, arglist, env, tool, arguments or {})
            )
            return {"ok": True, "result": result}
        except Exception as exc:  # noqa: BLE001 — bridge must not raise
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    return exec_mcp


def http_mcp_executor(
    url: str,
    headers: dict | None = None,
) -> Callable[[str, dict], dict]:
    """Build a sync MCP executor that talks to a server over streamable HTTP.

    Parameters
    ----------
    url:
        Endpoint URL of the remote MCP server.
    headers:
        Optional HTTP headers (e.g. ``{"Authorization": "Bearer ..."}``).

    Returns
    -------
    callable(tool, arguments) -> dict
        Synchronous function with the same return contract as
        :func:`stdio_mcp_executor`.
    """
    def exec_mcp(tool: str, arguments: dict) -> dict:
        try:
            import mcp  # noqa: F401
        except ImportError:
            raise ImportError(_MISSING_DEP_MSG) from None
        try:
            result = asyncio.run(
                _http_call(url, headers, tool, arguments or {})
            )
            return {"ok": True, "result": result}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    return exec_mcp