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
    "stdio_mcp_executor",
    "http_mcp_executor",
    "generate",
    "load_spec",
    "openapi_to_okf",
]


def __getattr__(name):
    """Lazy, optional-dependency-safe exports.

    The reference MCP executors live in :mod:`carta.mcp_executor` and only need
    the ``mcp`` package when actually called. We expose them here without
    importing them eagerly so ``import carta`` still works when ``mcp`` is not
    installed.
    """
    if name in ("stdio_mcp_executor", "http_mcp_executor"):
        from . import mcp_executor

        return getattr(mcp_executor, name)
    if name in ("generate", "load_spec", "openapi_to_okf"):
        from . import openapi_to_okf

        if name == "openapi_to_okf":
            return openapi_to_okf
        return getattr(openapi_to_okf, name)
    raise AttributeError(f"module 'carta' has no attribute {name!r}")