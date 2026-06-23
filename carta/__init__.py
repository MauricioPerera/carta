"""Carta — reusable client + agent for the OKF capability-discovery pattern.

Packages the pattern that was previously assembled by hand: select relevant
OKF docs for a task, then execute the resulting action along the route
(`rest` or `mcp`) declared in each doc's frontmatter.
"""
from .client import CartaClient
from .agent import CartaAgent

__all__ = [
    "CartaClient",
    "CartaAgent",
    "select_tools",
    "load_okf_index",
    "format_context",
    "Bash",
    "Allowlist",
    "AuditLog",
    "SharedFilesystem",
    "stdio_mcp_executor",
    "http_mcp_executor",
    "generate",
    "load_spec",
    "openapi_to_okf",
]


def __getattr__(name):
    """Lazy, optional-dependency-safe exports.

    The reference MCP executors live in :mod:`carta.mcp_executor` and only need
    the ``mcp`` package when actually called. The selector and bash symbols are
    also exposed lazily so ``import carta`` stays light. Everything here is
    imported on first attribute access rather than eagerly.
    """
    if name in ("stdio_mcp_executor", "http_mcp_executor"):
        from . import mcp_executor

        return getattr(mcp_executor, name)
    if name in ("generate", "load_spec", "openapi_to_okf"):
        from . import openapi_to_okf

        if name == "openapi_to_okf":
            return openapi_to_okf
        return getattr(openapi_to_okf, name)
    if name in ("select_tools", "load_okf_index", "format_context"):
        from . import selector

        return getattr(selector, name)
    if name in ("Bash", "Allowlist", "AuditLog", "SharedFilesystem"):
        from . import bash

        return getattr(bash, name)
    raise AttributeError(f"module 'carta' has no attribute {name!r}")