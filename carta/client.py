"""CartaClient — discovery + selection + execution, with no model of its own.

The client wraps the :mod:`carta.selector` and :mod:`carta.bash` modules so the
OKF pattern (select a small context, then run the action along its route) can be
reused without re-assembling the wiring each time.

It intentionally contains NO language-model logic: that lives in
``carta.agent.CartaAgent``. The client is safe to use on its own for scripted
or deterministic flows.
"""
from __future__ import annotations

import os

# Repo root, used to resolve relative catalog paths (e.g. ``okf/n8n``) when the
# caller's cwd does not contain them. Editable installs point ``__file__`` at
# the source tree, so this still resolves to the repo root.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

from carta.selector import (  # noqa: E402
    count_tokens,
    format_context,
    load_okf_index,
    select_tools,
)


def _resolve_path(path: str) -> str:
    """Return ``path`` if it exists as-is, otherwise resolve it against the
    repo root. Lets callers pass either ``okf/n8n`` or an absolute path."""
    if os.path.exists(path):
        return path
    joined = os.path.join(_REPO_ROOT, path)
    if os.path.exists(joined):
        return joined
    # Fall back to the original so downstream errors are about the real input.
    return path


class CartaClient:
    """Discovery + select + execute over one or more OKF catalogs.

    Parameters
    ----------
    catalogs:
        List of paths to OKF catalog dirs (e.g. ``['okf/n8n']`` or
        ``['okf/n8n', 'okf/jsonplaceholder']``). Relative paths resolve against
        the repo root when the cwd does not contain them.
    contract:
        Optional path to a ``.ccdd`` YAML contract. When provided, its
        ``execution`` block seeds the bash allowlist.
    """

    def __init__(self, catalogs: list[str], contract: str | None = None):
        if isinstance(catalogs, str):
            catalogs = [catalogs]
        if not catalogs:
            raise ValueError("CartaClient requires at least one catalog path")
        self.catalogs = [_resolve_path(c) for c in catalogs]
        self.contract = contract
        self._bash = None
        self._bash_error: str | None = None
        self._init_bash()

    # ------------------------------------------------------------------ bash
    def _init_bash(self) -> None:
        """Build the Bash executor + allowlist. Fails soft: if the bash module
        is unavailable we keep going and report a clear error at execute time."""
        try:
            from carta.bash import Allowlist, Bash  # noqa: WPS433  (lazy by design)
        except Exception as exc:  # pragma: no cover - environment-dependent
            self._bash_error = f"bash executor unavailable: {exc!r}"
            return

        allowlist = None
        if self.contract:
            try:
                allowlist = Allowlist.load_from_ccdd(self.contract)
            except Exception as exc:  # pragma: no cover - bad contract path
                self._bash_error = f"allowlist load failed: {exc!r}"
                return
        self._bash = Bash(allowlist=allowlist)

    # -------------------------------------------------------------- catalogs
    def _catalog_name(self, catalog: str) -> str:
        return os.path.basename(os.path.normpath(catalog))

    def _pick_catalog(self, task: str, provider: str | None) -> str:
        """Choose which catalog to select from.

        - One catalog: use it.
        - ``provider`` given: match the catalog whose dir name equals it.
        - Otherwise: pick the catalog whose name shares the most tokens with
          the task; tie-break by order.
        """
        if len(self.catalogs) == 1:
            return self.catalogs[0]
        if provider:
            for cat in self.catalogs:
                if self._catalog_name(cat) == provider:
                    return cat
        task_tokens = set(task.lower().split())
        best, best_score = self.catalogs[0], -1
        for cat in self.catalogs:
            name_tokens = set(self._catalog_name(cat).lower().split("-"))
            score = len(task_tokens & name_tokens)
            if score > best_score:
                best, best_score = cat, score
        return best

    # ----------------------------------------------------------- staleness
    def check_freshness(self, task: str = "", provider: str | None = None, fetcher=None) -> dict:
        """Check the staleness of the chosen catalog against its source spec.

        Resolves the catalog the same way :meth:`select` chooses one
        (single catalog, ``provider`` match, or token overlap with ``task``)
        and delegates to :func:`carta.staleness.check_catalog` over that dir.

        This is opt-in and never runs automatically — the default offline
        behavior of the client is unchanged. Pass a ``fetcher`` to stay off
        the network (see :mod:`carta.staleness`).
        """
        from carta.staleness import check_catalog

        catalog = self._pick_catalog(task, provider)
        return check_catalog(catalog, fetcher=fetcher)

    # --------------------------------------------------------------- select
    def select(self, task: str, provider: str | None = None, max_docs: int = 5) -> dict:
        """Select relevant docs for ``task`` and build the trimmed context.

        Returns ``{'docs': [...], 'context': str, 'tokens': int,
        'baseline_tokens': int}`` where ``tokens`` is the trimmed context size
        and ``baseline_tokens`` is the size of the full catalog concatenated.
        """
        catalog = self._pick_catalog(task, provider)
        docs = select_tools(task, okf_path=catalog, max_docs=max_docs)
        context = format_context(docs)
        tokens = count_tokens(context)

        idx = load_okf_index(catalog)
        all_docs = idx["skills"] + idx["tools"]
        baseline_tokens = count_tokens(format_context(all_docs)) if all_docs else 0

        return {
            "docs": docs,
            "context": context,
            "tokens": tokens,
            "baseline_tokens": baseline_tokens,
        }

    # --------------------------------------------------------------- routes
    def route_of(self, doc: dict) -> str:
        """Return the route declared in a doc's frontmatter.

        Recognised values: ``'rest'``, ``'mcp'``, ``'local'``, ``'internal'``.
        Defaults to ``'mcp'`` for docs that declare no route (e.g. n8n skill
        docs, which inherit the MCP route of their provider).
        """
        fm = doc.get("frontmatter", {}) or {}
        route = fm.get("route")
        if route in ("rest", "mcp", "local", "internal"):
            return route
        return "mcp"

    # ------------------------------------------------------------- execute
    def execute_rest(self, command: str) -> dict:
        """Run a shell command through the allowlisted bash executor.

        Returns ``{stdout, stderr, exit_code, blocked, audit_id}``. If the bash
        executor is unavailable, returns a blocked error result instead of
        raising.
        """
        if self._bash is None:
            return {
                "stdout": "",
                "stderr": self._bash_error or "bash executor not initialized",
                "exit_code": 1,
                "blocked": True,
                "audit_id": None,
            }
        res = self._bash.exec(command)
        return {
            "stdout": res.get("stdout", ""),
            "stderr": res.get("stderr", ""),
            "exit_code": res.get("exit_code"),
            "blocked": res.get("blocked", False),
            "audit_id": res.get("audit_id"),
        }

    def execute(self, action: dict) -> dict:
        """Execute one action along its declared route.

        ``action = {'route':'rest','command':'curl ...'}`` runs the command via
        :meth:`execute_rest`.

        ``action = {'route':'mcp','tool':'...','args':{...}}`` does NOT execute
        directly: the MCP server is an external process the host owns, so we
        return ``{'pending_mcp': True, 'tool':..., 'args':...}`` for the host
        (or a ``mcp_executor`` callable in :class:`CartaAgent`) to resolve.
        """
        route = action.get("route")
        if route == "rest":
            return self.execute_rest(action.get("command", ""))
        if route == "mcp":
            return {
                "pending_mcp": True,
                "tool": action.get("tool"),
                "args": action.get("args", {}) or {},
            }
        return {
            "stdout": "",
            "stderr": f"unknown route: {route!r}",
            "exit_code": 1,
            "blocked": True,
            "audit_id": None,
        }