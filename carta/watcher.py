"""T30 — ``carta watch``: poll-based swarm orchestrator.

Monitors every inbox of a Carta project and fires a
:class:`carta.agent.CartaAgent` automatically when a new Postal-style message
lands. Pure polling (``time.sleep``), no external dependencies, so the swarm
runs without a broker.

The public surface is three functions:

- :func:`find_agent_spec` — locate an agent's ``.yaml`` spec, trying the
  ``-agent`` suffix fallback when the bare id is not found.
- :func:`scan_pending` — scan ``<postal_dir>/inbox/`` and return the pending
  messages across all agent subdirectories, ordered by message timestamp.
- :func:`watch` — the orchestrator loop.
"""
from __future__ import annotations

import os


def find_agent_spec(agent_id: str, specs_dir: str) -> str | None:
    """Find the ``agent.yaml`` for ``agent_id`` under ``specs_dir``.

    Tries ``<agent_id>.yaml`` first. When ``agent_id`` does not already end in
    ``-agent``, also tries the ``<agent_id>-agent.yaml`` fallback. Returns the
    absolute path of the first match, or ``None`` when no spec exists.
    """
    cand = os.path.join(specs_dir, f"{agent_id}.yaml")
    if os.path.isfile(cand):
        return os.path.abspath(cand)
    if not agent_id.endswith("-agent"):
        cand = os.path.join(specs_dir, f"{agent_id}-agent.yaml")
        if os.path.isfile(cand):
            return os.path.abspath(cand)
    return None


def scan_pending(postal_dir: str) -> list[dict]:
    """Scan ``<postal_dir>/inbox/`` and return the pending messages.

    Each inbox subdirectory is treated as one agent's mailbox
    (``inbox/<agent_id>/``). :func:`carta.mailbox.list_unprocessed` is used per
    subdirectory so already-processed messages
    (``<postal_dir>/processed/<id>.json``) are skipped. Each returned item is
    ``{"agent_id": str, "message": dict, "path": str}`` and the list is sorted
    by the message ``timestamp`` field so messages are processed in order.

    Returns ``[]`` when the inbox directory does not exist or holds no pending
    messages.
    """
    from .mailbox import list_unprocessed

    inbox = os.path.join(postal_dir, "inbox")
    processed = os.path.join(postal_dir, "processed")
    if not os.path.isdir(inbox):
        return []

    out: list[dict] = []
    for name in sorted(os.listdir(inbox)):
        sub = os.path.join(inbox, name)
        if not os.path.isdir(sub):
            continue
        for msg in list_unprocessed(sub, processed):
            msg_id = msg.get("id")
            path = os.path.join(sub, f"{msg_id}.json") if msg_id else sub
            out.append({"agent_id": name, "message": msg, "path": path})
    out.sort(key=lambda it: it["message"].get("timestamp", "") or "")
    return out


def watch(
    project_dir: str,
    specs_dir: str = "agent-specs",
    postal_dir: str = ".postal",
    base_url: str = "http://localhost:1234/v1",
    poll_interval: float = 2.0,
    max_rounds: int = 50,
    idle_stop: int = 3,
    on_event=None,
) -> dict:
    """Orchestrate the swarm: fire a :class:`CartaAgent` per pending message.

    Parameters
    ----------
    project_dir:
        Root of the Carta project.
    specs_dir / postal_dir:
        Agent-specs and postal directories, relative to ``project_dir``.
    base_url:
        Model endpoint URL passed to every agent (overrides the spec's
        ``model.base_url`` so the orchestrator controls the endpoint).
    poll_interval:
        Seconds to sleep between polls when no messages are pending.
    max_rounds:
        Absolute cap on processing rounds (anti-loop).
    idle_stop:
        Consecutive idle rounds (no pending messages) before terminating.
    on_event:
        Optional ``callback(event_type: str, data: dict)`` for progress
        logging. Emitted events are ``"processed"`` and ``"skip"``.

    Returns
    ``{"rounds": int, "processed": list[str], "stopped_reason": str}`` where
    ``processed`` is the list of agent ids that ran and ``stopped_reason`` is
    ``"idle"`` or ``"max_rounds"``.

    All imports of :class:`CartaAgent`, :func:`load_agent_yaml` and the mailbox
    helpers are lazy (inside this function) to avoid circular imports.
    """
    import time

    from .agent import CartaAgent
    from .agent_yaml import load_agent_yaml
    from .mailbox import extract_task, mark_processed

    abs_project = os.path.abspath(project_dir)
    abs_specs = os.path.abspath(os.path.join(abs_project, specs_dir))
    abs_postal = os.path.abspath(os.path.join(abs_project, postal_dir))
    abs_processed = os.path.join(abs_postal, "processed")

    rounds = 0
    idle_count = 0
    processed: list[str] = []
    stopped_reason = "idle"

    def _msg_id(item: dict) -> str:
        msg = item["message"]
        mid = msg.get("id")
        if mid:
            return mid
        return os.path.splitext(os.path.basename(item["path"]))[0]

    while True:
        pending = scan_pending(abs_postal)

        if pending:
            idle_count = 0
            for item in pending:
                agent_id = item["agent_id"]
                message = item["message"]
                spec_path = find_agent_spec(agent_id, abs_specs)
                if spec_path is None:
                    if on_event:
                        on_event(
                            "skip",
                            {"agent_id": agent_id, "reason": "no spec found"},
                        )
                    mark_processed(
                        _msg_id(item),
                        abs_processed,
                        {"skipped": True, "reason": "no spec found"},
                    )
                    continue

                config = load_agent_yaml(spec_path)
                task = extract_task(message) or str(message)
                agent = CartaAgent(
                    catalogs=config.knowledge,
                    model=config.model["name"],
                    base_url=base_url,
                    timeout=config.model.get("timeout", 60),
                    agent_id=config.id,
                    postal_dir=abs_postal,
                )
                result = agent.run(
                    task, max_steps=config.model.get("max_steps", 8)
                )
                mark_processed(_msg_id(item), abs_processed, result)
                processed.append(config.id)
                if on_event:
                    on_event(
                        "processed",
                        {
                            "agent_id": config.id,
                            "task": task[:80],
                            "steps": len(result.get("steps", [])),
                        },
                    )
        else:
            idle_count += 1

        rounds += 1

        if not pending and idle_count >= idle_stop:
            stopped_reason = "idle"
            break
        if rounds >= max_rounds:
            stopped_reason = "max_rounds"
            break
        if not pending:
            time.sleep(poll_interval)

    return {
        "rounds": rounds,
        "processed": processed,
        "stopped_reason": stopped_reason,
    }