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

import http.client
import json
import re
import time
import urllib.error
import urllib.request

from .client import CartaClient
from .selector import selection_sha

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
        postal_identity=None,
        audit_dir: str = ".postal/audit",
        agent_id: str = "unknown",
        postal_dir: str = ".postal",
        api_key: str | None = None,
    ):
        self.client = CartaClient(catalogs, contract=contract)
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.mcp_executor = mcp_executor
        self.timeout = timeout
        self.postal_identity = postal_identity
        self.postal_dir = audit_dir
        self.api_key = api_key or ""
        # T25/T32: swarm delegation config. ``_agent_id`` identifies this agent
        # as a sender; ``_postal_dir_base`` is the mailbox root used by the
        # ``route='internal'`` branch in :meth:`run`. Both are now explicit
        # constructor params so callers don't rely on post-init attribute
        # mutation (which failed silently when forgotten).
        self._agent_id = agent_id
        self._postal_dir_base = postal_dir

    # ------------------------------------------------------------------ chat
    _CHAT_RETRIES = 3  # transient-network retries per chat call

    def _chat(self, messages: list[dict]) -> str:
        """POST to ``base_url/chat/completions`` (streaming) and return the full text.

        Uses SSE streaming so the connection stays alive while the model generates.
        ``self.timeout`` is the per-chunk read timeout. Transient network failures
        (read timeouts, dropped connections, 5xx) are retried with backoff so a
        single blip during a long multi-stage flow does not kill the whole run.
        Client errors (4xx, e.g. a bad API key) are NOT retried.
        """
        url = f"{self.base_url}/chat/completions"
        body = json.dumps({
            "model": self.model,
            "messages": messages,
            "stream": True,
        }).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        last_exc: Exception | None = None
        for attempt in range(self._CHAT_RETRIES):
            req = urllib.request.Request(
                url, data=body, headers=headers, method="POST"
            )
            try:
                return self._stream_chat(req)
            except urllib.error.HTTPError as exc:
                # 4xx won't be fixed by retrying (bad key, malformed request).
                if 400 <= exc.code < 500:
                    raise RuntimeError(
                        f"chat request to {url} failed: HTTP {exc.code} {exc.reason}"
                    ) from exc
                last_exc = exc
            except (urllib.error.URLError, OSError, http.client.HTTPException) as exc:
                # URLError (incl. DNS), TimeoutError/ConnectionError (OSError),
                # IncompleteRead/RemoteDisconnected (HTTPException) → transient.
                last_exc = exc
            if attempt < self._CHAT_RETRIES - 1:
                time.sleep(2 * (attempt + 1))  # 2s, 4s backoff

        raise RuntimeError(
            f"chat request to {url} failed after {self._CHAT_RETRIES} attempts: "
            f"{last_exc}"
        ) from last_exc

    def _stream_chat(self, req: "urllib.request.Request") -> str:
        """Issue one streaming request and stitch the response into text.

        Raises on any transport error so :meth:`_chat` can decide whether to
        retry. Block-protocol: glm-style models emit the action as text content;
        code models (kimi) emit it under ``delta.tool_calls`` — both supported.
        """
        content_parts: list[str] = []
        tool_calls: dict[int, dict] = {}
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            for raw_line in resp:
                line = raw_line.decode("utf-8").strip()
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    chunk = json.loads(data)
                except json.JSONDecodeError:
                    continue
                delta = chunk.get("choices", [{}])[0].get("delta", {})
                piece = delta.get("content") or ""
                if piece:
                    content_parts.append(piece)
                for tc in delta.get("tool_calls") or []:
                    idx = tc.get("index", 0)
                    slot = tool_calls.setdefault(idx, {"name": "", "args": ""})
                    fn = tc.get("function") or {}
                    if fn.get("name"):
                        slot["name"] = fn["name"]
                    if fn.get("arguments"):
                        slot["args"] += fn["arguments"]

        text = "".join(content_parts)
        # If the model produced no text but did emit a native tool call,
        # synthesize the block-protocol JSON so _extract_action can parse it.
        if not text.strip() and tool_calls:
            first = tool_calls[min(tool_calls)]
            try:
                args_obj = json.loads(first["args"]) if first["args"] else {}
            except json.JSONDecodeError:
                args_obj = {}
            text = json.dumps({"tool": first["name"], "args": args_obj})

        return text

    # --------------------------------------------------------------- parsing
    def _parse_json_action(self, text: str) -> dict | None:
        """Return a tool-call dict parsed from ``text``, or ``None``.

        Tolerates backslash line-continuations. Only dicts that look like an
        action (carry ``tool``, ``route`` or ``command``) qualify, so a plain
        JSON data payload is not mistaken for a tool call.
        """
        normalized = _normalize_continuations(text)
        first_brace = normalized.find("{")
        if first_brace == -1:
            return None
        candidate = _extract_balanced_json(normalized, first_brace)
        if candidate is None:
            return None
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            return None
        if isinstance(parsed, dict) and (
            "tool" in parsed or "route" in parsed or "command" in parsed
        ):
            return parsed
        return None

    def _extract_action(self, text: str) -> dict:
        """Parse one model turn into an action descriptor.

        Returns one of:
        - ``{'kind': 'block', 'code': str}`` — a lone fenced payload block.
        - ``{'kind': 'action', ..., '_inline_block': str?}`` — a JSON tool call
          (carrying ``route``/``command`` or ``tool``/``args``). ``_inline_block``
          is present when the same turn also carried a separate payload fence
          (the block-protocol shape from the system prompt), so the caller can
          stitch it without a second round-trip.
        - ``{'kind': 'text', 'text': str}`` — no action detected; final answer.

        The tool call itself may be wrapped in a ```json fence (as the system
        prompt example shows). That fence must NOT be mistaken for the payload
        block — otherwise the tool-call JSON gets written as the file content.
        """
        if not text:
            return {"kind": "text", "text": ""}

        fences = _FENCE_RE.findall(text)

        # (a) Prefer a JSON action OUTSIDE any fence.
        action = self._parse_json_action(_FENCE_RE.sub("", text))
        action_fence_idx = None
        # (b) Otherwise, a fenced block that is itself a tool-call object.
        if action is None:
            for idx, blk in enumerate(fences):
                parsed = self._parse_json_action(blk)
                if parsed is not None:
                    action = parsed
                    action_fence_idx = idx
                    break

        if action is not None:
            result = {"kind": "action", **action}
            # Attach the first fence that is NOT the tool-call fence as payload.
            for idx, blk in enumerate(fences):
                if idx == action_fence_idx:
                    continue
                result["_inline_block"] = blk
                break
            return result

        # (c) No action: a lone fenced block is a payload (two-turn protocol).
        if fences:
            return {"kind": "block", "code": fences[0]}

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
        sha = selection_sha(sel["docs"])
        messages: list[dict] = [
            {"role": "system", "content": self._system_prompt(sel["context"])},
            {"role": "user", "content": task},
        ]
        steps: list[dict] = []
        status = "max_steps"
        _pending_block: str | None = None  # last fenced block awaiting tool stitching

        for i in range(max_steps):
            if i == max_steps - 1 and status == "max_steps":
                # Final step: prompt the model for a plain-text summary so
                # downstream callers (e.g. flow.py) always receive a non-empty
                # answer even when the agent ran out of steps mid-task.
                messages.append({
                    "role": "user",
                    "content": (
                        "Last step. Reply with a plain-text summary of what you "
                        "accomplished. No JSON, no code blocks."
                    ),
                })
            reply = self._chat(messages)
            action = self._extract_action(reply)
            messages.append({"role": "assistant", "content": reply})

            if action["kind"] == "text":
                steps.append({"step": i, "type": "final", "text": action["text"]})
                status = "done"
                break

            if action["kind"] == "block":
                # Long payload: store and ask the model to emit a tool call for it.
                code = action["code"]
                _pending_block = code
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

            # Block stitching: substitute the "see block below" marker in any arg
            # value with the captured fenced payload. Prefer the inline block
            # delivered in the SAME turn (tool call + payload fence together);
            # fall back to a pending block from the prior turn.
            stitch_block = action.pop("_inline_block", None)
            if stitch_block is None:
                stitch_block = _pending_block
            if stitch_block is not None:
                args = action.get("args") or {}
                for k, v in list(args.items()):
                    if isinstance(v, str) and "see block below" in v.lower():
                        args[k] = stitch_block
                action["args"] = args
                _pending_block = None

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
            elif route == "internal":
                tool = action.get("tool")
                args = action.get("args", {}) or {}
                if tool == "send_to_agent":
                    to = args.get("to") or args.get("agent_id", "")
                    task_msg = args.get("task", "")
                    if to and task_msg:
                        from .swarm import send_to_agent as _send

                        path = _send(
                            from_id=self._agent_id,
                            to_agent_id=to,
                            task=task_msg,
                            postal_dir=self._postal_dir_base,
                            identity=self.postal_identity,
                            selection_sha=sha,
                        )
                        steps.append(
                            {"step": i, "type": "send_to_agent", "to": to, "path": path}
                        )
                        messages.append(
                            {
                                "role": "user",
                                "content": (
                                    f"OBSERVATION: message deposited for {to} at {path}"
                                ),
                            }
                        )
                    else:
                        steps.append({"step": i, "type": "error", "action": action})
                        messages.append(
                            {
                                "role": "user",
                                "content": (
                                    "ERROR: send_to_agent requires 'to' and 'task' args"
                                ),
                            }
                        )
                else:
                    steps.append({"step": i, "type": "error", "action": action})
                    messages.append(
                        {
                            "role": "user",
                            "content": (
                                f"ERROR: unknown internal tool '{tool}'"
                            ),
                        }
                    )
            elif route == "local":
                tool = action.get("tool") or ""
                args = action.get("args") or {}
                from . import local as _local

                if tool == "read_file":
                    r = _local.local_read_file(args.get("path", ""))
                elif tool == "write_file":
                    r = _local.local_write_file(
                        args.get("path", ""),
                        args.get("content", ""),
                        mkdir=args.get("mkdir", True),
                    )
                elif tool == "append_file":
                    r = _local.local_append_file(
                        args.get("path", ""), args.get("content", "")
                    )
                elif tool == "list_dir":
                    r = _local.local_list_dir(args.get("path", "."))
                elif tool == "run_command":
                    r = _local.local_run_command(
                        args.get("command", ""),
                        cwd=args.get("cwd"),
                        timeout=args.get("timeout", 30),
                    )
                else:
                    r = {"ok": False, "error": f"unknown local tool: {tool!r}"}

                steps.append({"step": i, "type": "local", "tool": tool, "result": r})
                result_text = str(r)
                messages.append(
                    {"role": "user", "content": f"OBSERVATION:\n{result_text}"}
                )
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

        if self.postal_identity is not None:
            try:
                import hashlib
                import pathlib

                ccdd_sha = ""
                if self.client.contract:
                    try:
                        ccdd_sha = hashlib.sha256(
                            pathlib.Path(self.client.contract).read_bytes()
                        ).hexdigest()
                    except Exception:
                        ccdd_sha = ""
                from .postal_audit import sign_run_receipt

                sign_run_receipt(
                    self.postal_identity,
                    task,
                    sha,
                    ccdd_sha,
                    status,
                    self.postal_dir,
                )
            except Exception as _sign_err:
                import warnings

                warnings.warn(
                    f"postal audit signing failed (receipt unsigned): {_sign_err}",
                    RuntimeWarning,
                    stacklevel=2,
                )

        # T32: extract the final text answer from the last "final" step so
        # downstream callers (flow.py) get non-empty context between stages.
        answer = ""
        for step in reversed(steps):
            if step.get("type") == "final":
                answer = step.get("text", "")
                break

        return {
            "status": status,
            "steps": steps,
            "context_tokens": sel["tokens"],
            "selection_sha": sha,
            "answer": answer,
        }