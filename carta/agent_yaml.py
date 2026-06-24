"""Declarative agent definition loaded from a YAML file in git.

This module reads an ``agent.yaml`` and turns it into an :class:`AgentConfig`
dataclass — a plain, dependency-free description of how to build a
:class:`carta.agent.CartaAgent` (model endpoint, OKF knowledge catalogs,
optional CCDD governance contract, optional Postal audit identity and
triggers).

No pydantic, no attrs — just :mod:`dataclasses` and the stdlib. YAML parsing
uses PyYAML (``import yaml``), available transitively via Postal.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional

import yaml


@dataclass
class AgentConfig:
    """Parsed ``agent.yaml`` content.

    ``model`` is kept as a plain dict (keys: ``base_url``, ``name``,
    ``timeout`` defaulting to 60, ``max_steps`` defaulting to 8) so the file
    stays the single source of truth and callers can ``.get`` optional keys.
    """

    id: str
    model: dict
    knowledge: list[str] = field(default_factory=list)
    governance: Optional[dict] = None
    postal: Optional[dict] = None
    triggers: list[dict] = field(default_factory=list)


def _require(mapping: dict, key: str, where: str) -> object:
    """Return ``mapping[key]`` or raise a clear ``ValueError``."""
    if key not in mapping or mapping[key] in (None, ""):
        raise ValueError(f"agent.yaml: missing required field {where}")
    return mapping[key]


def load_agent_yaml(path: str) -> AgentConfig:
    """Load and validate an ``agent.yaml`` file into :class:`AgentConfig`.

    Raises ``ValueError`` with a clear message when ``id``, ``model.base_url``
    or ``model.name`` are missing.
    """
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    if not isinstance(data, dict):
        raise ValueError("agent.yaml: top-level must be a mapping")

    agent_id = _require(data, "id", "id")
    model = _require(data, "model", "model")
    if not isinstance(model, dict):
        raise ValueError("agent.yaml: 'model' must be a mapping")
    _require(model, "base_url", "model.base_url")
    _require(model, "name", "model.name")

    # Resolve api_key: if the value starts with $ treat it as an env var name.
    if "api_key" in model and isinstance(model["api_key"], str):
        raw = model["api_key"]
        if raw.startswith("$"):
            env_name = raw[1:]
            model["api_key"] = os.environ.get(env_name, "")

    knowledge = data.get("knowledge") or []
    if not isinstance(knowledge, list):
        raise ValueError("agent.yaml: 'knowledge' must be a list of paths")

    governance = data.get("governance")
    postal = data.get("postal")
    triggers = data.get("triggers") or []
    if not isinstance(triggers, list):
        raise ValueError("agent.yaml: 'triggers' must be a list")

    return AgentConfig(
        id=agent_id,
        model=model,
        knowledge=list(knowledge),
        governance=governance if isinstance(governance, dict) else None,
        postal=postal if isinstance(postal, dict) else None,
        triggers=list(triggers),
    )


def load_postal_identity(config: AgentConfig):
    """Best-effort load of a Postal identity from ``config.postal``.

    Returns ``None`` silently when Postal is not importable, the ``identity``
    path is absent, or the file does not exist on disk.
    """
    postal = config.postal
    if not isinstance(postal, dict):
        return None
    identity_path = postal.get("identity")
    if not identity_path or not os.path.isfile(identity_path):
        return None
    try:
        from postal import load_identity  # local: postal package in this repo
    except ImportError:
        return None  # postal not installed — expected, do not log
    try:
        # ``load_identity(id, path)`` ignores ``id`` when ``path`` is a full
        # .json file path; the id is read from the file payload itself.
        return load_identity("", identity_path)
    except FileNotFoundError as _e:
        import logging

        logging.getLogger(__name__).warning(
            "postal identity file not found: %s", _e
        )
        return None
    except Exception as _e:
        import logging

        logging.getLogger(__name__).error(
            "postal identity load error: %s", _e
        )
        return None