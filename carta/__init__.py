"""Carta — reusable client + agent for the OKF capability-discovery pattern.

Packages the pattern that was previously assembled by hand: select relevant
OKF docs for a task, then execute the resulting action along the route
(`rest` or `mcp`) declared in each doc's frontmatter.
"""
from .client import CartaClient
from .agent import CartaAgent

__all__ = ["CartaClient", "CartaAgent"]