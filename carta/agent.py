"""CartaAgent — full agent loop against an OpenAI-compatible chat endpoint.

Drives a ``CartaClient`` through a multi-step conversation with a model served
at ``base_url`` (e.g. LM Studio at ``http://localhost:1234/v1``). Uses only the
Python standard library (``urllib``) for HTTP so the package needs no extra
dependencies.

The system prompt bakes in a BLOCK PROTOCOL learned from small-model failures:
the model emits exactly ONE action per turn, either a small JSON object to
call a tool or a fenced code block to deliver a long payload (never long code
inside JSON). The parser tolerates backslash line-continuations, which is the
concrete failure mode observed in small models.
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request

from .client import CartaClient

# Block-protocol system prompt. Kept compact: small models obey short rules.
_SYSTEM_TEMPLATE = """\
You are a Carta agent. Use ONLY the provided OKF context to pick tools.

PROTOCOL (one action per turn, nothing else):
- To call a tool, emit a SMALL JSON object on its own:
    {{"route": "rest", "command": "curl -s ..."}}      # REST tool
    {{"tool": "<tool_name>", "args": {{...}}}}          # tool from context
- To deliver LONG code or a payload, emit a fenced block (NEVER put long code
  inside JSON):
    ```json
    {{"tool": "create_workflow_from_code", "args": {{"code": "see block below"}}}}
    ```
    ```typescript
    ...the long code here...
    ```
- When the task is complete, reply with a short plain-text summary (no JSON,
  no fence).

OKF CONTEXT:
{context}
"""

_FENCE_RE = re.compile(r"```(?:[a-zA-Z0-9_+.\-]*)\n(.*?)```", re.DOTALL)
_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)
_CONTINUATION_RE = re.compile(r"\\\r?\n")


def _normalize_continuations(text: str) -> str:
    """Join backslash line-continuations: ``foo,\\<newline>bar`` -> ``foo,bar``.

    Small models sometimes wrap JSON across lines with a trailing backslash;
    standard ``json.loads`` rejects the result. This normalization recovers
    the intended single-line JSON.
    """
    return _CONTINUATION_RE.sub("", text)


def _extract_balanced_json(text: str, start: int) -> str | None:
    """Return the substring from ``text[start]`` (a ``{``) through its matching
    ``}``, accounting for nested objects and string literals. ``None`` if no
    balanced object is found."""
    depth = 0
    in_str = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


class CartaAgent:
    """Agent loop: select context, chat with a model, execute actions, refeed.

    Parameters
    ----------
    catalogs:
        Forwarded to :class:`CartaClient`.
    model:
        Model name accepted by the chat endpoint.
    base_url:
        OpenAI-compatible base URL (default: LM Studio).
    contract:
        Optional ``.ccdd`` contract path, forwarded to :class:`CartaClient`.
    mcp_executor:
        Optional ``callable(tool, args) -> result`` used to resolve
        ``route='mcp'`` actions. When ``None``, MCP actions come back as
        ``status='pending_mcp'`` for the host to resolve.
    timeout:
        Per-request HTTP timeout in seconds.
    """

    def __init__(
        self,
        catalogs: list[str],
        model: str,
        base_url: str = "http://localhost:1234/v1",
        contract: str | None = None,
        mcp_executor=None,
        timeout: int = 60,
    ):
        self.client = CartaClient(catalogs, contract=contract)
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.mcp_executor = mcp_executor
        self.timeout = timeout

    # ------------------------------------------------------------------ chat
    def _chat(self, messages: list[dict]) -> str:
        """POST to ``base_url/chat/completions`` and return the assistant text.

        Uses only ``urllib`` from the stdlib. Raises on transport or HTTP
        errors so the caller can surface them.
        """
        url = f"{self.base_url}/chat/completions"
        body = json.dumps({"model": self.model, "messages": messages}).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise RuntimeError(f"chat request to {url} failed: {exc}") from exc
        return payload["choices"][0]["message"]["content"]

    # --------------------------------------------------------------- parsing
    def _extract_action(self, text: str) -> dict:
        """Parse one model turn into an action descriptor.

        Returns one of:
        - ``{'kind': 'block', 'code': str}`` — a fenced payload block.
        - ``{'kind': 'action', ...}`` — a JSON object (carrying whatever keys
          the model wrote: ``route``/``command`` or ``tool``/``args``).
        - ``{'kind': 'text', 'text': str}`` — no action detected; treated as a
          final answer.
        """
        if not text:
            return {"kind": "text", "text": ""}

        # (a) fenced code block — long payload delivery.
        m = _FENCE_RE.search(text)
        if m:
            return {"kind": "block", "code": m.group(1)}

        # (b) JSON action, tolerating backslash line-continuations.
        normalized = _normalize_continuations(text)
        first_brace = normalized.find("{")
        if first_brace != -1:
            candidate = _extract_balanced_json(normalized, first_brace)
            if candidate is not None:
                try:
                    parsed = json.loads(candidate)
                except json.JSONDecodeError:
                    parsed = None
                if isinstance(parsed, dict):
                    return {"kind": "action", **parsed}

        return {"kind": "text", "text": text}

    # --------------------------------------------------------------- helpers
    def _route_for_tool(self, tool: str, docs: list[dict]) -> str | None:
        """Look up a tool's route from the selected docs by name."""
        for doc in docs:
            if doc.get("name") == tool:
                return self.client.route_of(doc)
        return None

    def _build_rest_command(self, action: dict, docs: list[dict]) -> str:
        """Best-effort curl for a REST tool without an explicit ``command``.

        Looks up the tool's ``endpoint`` frontmatter; falls back to ``echo`` so
        the loop still produces an observable, safe result.
        """
        tool = action.get("tool")
        for doc in docs:
            if doc.get("name") == tool:
                fm = doc.get("frontmatter", {}) or {}
                endpoint = fm.get("endpoint")
                if endpoint:
                    return f"curl -s {endpoint}"
        return "echo carta:no-endpoint"

    def _system_prompt(self, context: str) -> str:
        return _SYSTEM_TEMPLATE.format(context=context)

    # ------------------------------------------------------------------- run
    def run(self, task: str, provider: str | None = None, max_steps: int = 8) -> dict:
        """Run the agent loop and return ``{status, steps, context_tokens}``.

        ``status`` is one of ``'done'``, ``'max_steps'``, or ``'pending_mcp'``.
        """
        sel = self.client.select(task, provider=provider)
        docs = sel["docs"]
        messages: list[dict] = [
            {"role": "system", "content": self._system_prompt(sel["context"])},
            {"role": "user", "content": task},
        ]
        steps: list[dict] = []
        status = "max_steps"

        for i in range(max_steps):
            reply = self._chat(messages)
            action = self._extract_action(reply)
            messages.append({"role": "assistant", "content": reply})

            if action["kind"] == "text":
                steps.append({"step": i, "type": "final", "text": action["text"]})
                status = "done"
                break

            if action["kind"] == "block":
                # Long payload: hand it back to the model as an observation so
                # the next turn can wrap it into a tool call or final answer.
                code = action["code"]
                steps.append({"step": i, "type": "block", "length": len(code)})
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            f"Received code block ({len(code)} chars). "
                            "Now emit the tool call that consumes it, or a final answer."
                        ),
                    }
                )
                continue

            # action kind: decide the route.
            route = action.get("route")
            if route is None and "tool" in action:
                route = self._route_for_tool(action["tool"], docs)

            if route == "rest":
                command = action.get("command") or self._build_rest_command(action, docs)
                res = self.client.execute({"route": "rest", "command": command})
                steps.append(
                    {
                        "step": i,
                        "type": "rest",
                        "command": command,
                        "exit_code": res.get("exit_code"),
                        "blocked": res.get("blocked"),
                    }
                )
                messages.append(
                    {"role": "user", "content": f"OBSERVATION:\n{json.dumps(res)}"}
                )
            elif route == "mcp":
                tool = action.get("tool")
                args = action.get("args", {}) or {}
                if self.mcp_executor is not None:
                    res = self.mcp_executor(tool, args)
                    steps.append({"step": i, "type": "mcp", "tool": tool})
                    messages.append(
                        {"role": "user", "content": f"OBSERVATION:\n{json.dumps(res)}"}
                    )
                else:
                    steps.append(
                        {"step": i, "type": "mcp_pending", "tool": tool, "args": args}
                    )
                    status = "pending_mcp"
                    break
            else:
                steps.append({"step": i, "type": "error", "action": action})
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            "ERROR: could not determine route for the last action. "
                            "Re-emit it as {\"route\":\"rest\",\"command\":...} or "
                            "{\"tool\":\"<name>\",\"args\":{...}}."
                        ),
                    }
                )

        return {"status": status, "steps": steps, "context_tokens": sel["tokens"]}