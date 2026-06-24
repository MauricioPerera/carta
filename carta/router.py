"""AgentRouter — use the OKF selector to pick the right ``agent.yaml`` for a task.

The router treats agent descriptors (OKF ``.md`` docs whose frontmatter carries
``type: agent`` and an ``agent_yaml`` path) as the selectable corpus and reuses
:class:`carta.client.CartaClient` unchanged: the same keyword/BM25/embedding
selector that picks tools now picks agents. Given a task, it routes to the
``agent.yaml`` declared in the best-matching doc's frontmatter and, unless
``dry_run`` is set, builds and runs that agent.

No new parser is introduced: the agents catalog is a plain OKF catalog dir
(``skills/`` with ``.md`` docs), so :meth:`CartaClient.select` works as-is.
"""
from __future__ import annotations

import os

from .agent import CartaAgent
from .agent_yaml import load_agent_yaml
from .client import CartaClient


class AgentRouter:
    """Select an agent for a task using the OKF selector, then run it.

    Parameters
    ----------
    agents_catalog:
        Path to an OKF catalog directory whose ``skills/`` holds agent
        descriptor ``.md`` files. Each descriptor's frontmatter must include an
        ``agent_yaml`` key pointing at a loadable ``agent.yaml``.
    base_url:
        OpenAI-compatible base URL forwarded to the selected agent when it runs.
    """

    def __init__(self, agents_catalog: str, base_url: str = "http://localhost:1234/v1"):
        self.agents_catalog = agents_catalog
        self.base_url = base_url
        # Reuse the existing selector: agent docs are just OKF skills whose
        # frontmatter happens to carry an ``agent_yaml`` pointer.
        self.client = CartaClient([agents_catalog])

    def route(self, task: str) -> str:
        """Return the path to the ``agent.yaml`` selected for ``task``.

        Raises ``ValueError`` when no agent doc matches the task, or when the
        selected doc's frontmatter has no ``agent_yaml`` key.
        """
        docs = self.client.select(task).get("docs") or []
        if not docs:
            raise ValueError(f"no agent docs matched task: {task!r}")
        doc = docs[0]
        fm = doc.get("frontmatter", {}) or {}
        agent_yaml = fm.get("agent_yaml")
        if not agent_yaml:
            raise ValueError(
                f"selected agent doc {doc.get('name')!r} has no 'agent_yaml' "
                "field in its frontmatter"
            )
        # Resolve relative paths against the project root (parent of agents catalog)
        if not os.path.isabs(agent_yaml):
            project_root = os.path.dirname(os.path.abspath(self.agents_catalog))
            candidate = os.path.join(project_root, agent_yaml)
            if os.path.exists(candidate):
                agent_yaml = candidate
        return agent_yaml

    def run(self, task: str, dry_run: bool = False) -> dict:
        """Route ``task`` to an agent and either run it or preview the routing.

        With ``dry_run=True`` returns ``{"routed_to", "agent_id", "task"}``
        without touching the model — useful for tests and CLI preview.

        With ``dry_run=False`` builds the selected :class:`CartaAgent` from the
        routed ``agent.yaml`` and returns its ``run()`` result augmented with
        ``routed_to`` and ``agent_id``.
        """
        agent_yaml_path = self.route(task)
        config = load_agent_yaml(agent_yaml_path)

        if dry_run:
            return {
                "routed_to": agent_yaml_path,
                "agent_id": config.id,
                "task": task,
            }

        agent = CartaAgent(
            catalogs=config.knowledge,
            model=config.model["name"],
            base_url=self.base_url,
            timeout=config.model.get("timeout", 60),
        )
        result = agent.run(task, max_steps=config.model.get("max_steps", 8))
        result["routed_to"] = agent_yaml_path
        result["agent_id"] = config.id
        return result