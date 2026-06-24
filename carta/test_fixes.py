"""T32 — regression tests for the post-analysis critical/high fixes.

Covers:
- Part A: ``CartaAgent.run()`` returns an ``answer`` key (extracted from the
  last ``"final"`` step) so :mod:`carta.flow` gets non-empty context.
- Part D: ``local_append_file`` error shape includes ``path``.
- Part F: :func:`carta.flow.run_flow` raises a ``ValueError`` that names the
  undefined variable AND lists the available context variables.
- Part E: ``CartaAgent`` accepts ``agent_id`` / ``postal_dir`` constructor
  params, and :func:`carta.watcher.watch` passes ``agent_id`` to the
  constructor (not via post-init mutation).

Note on ``catalogs``: ``CartaClient`` rejects an empty catalog list, so the
``CartaAgent`` construction tests use the repo's real ``okf/n8n`` catalog (the
same offline pattern as ``test_carta``/``test_postal_audit``/``test_swarm``).
The flow tests monkeypatch ``CartaAgent.__init__`` to a no-op, so ``catalogs``
is never exercised there.
"""
from __future__ import annotations

import json
import os
import textwrap

import pytest

from carta.agent import CartaAgent
from carta.local import local_append_file
from carta.flow import load_flow, run_flow

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_N8N = os.path.join(_REPO_ROOT, "okf", "n8n")


# --------------------------------------------------------------------------- #
# Part A — run() returns answer
# --------------------------------------------------------------------------- #
def test_agent_run_returns_answer_key(monkeypatch):
    """run() result carries a non-empty ``answer`` extracted from the reply."""
    agent = CartaAgent([_N8N], model="test", base_url="http://localhost:1")

    def fake_chat(self, messages):  # noqa: ANN001
        return "the final answer is visible here"

    monkeypatch.setattr(CartaAgent, "_chat", fake_chat)

    result = agent.run("do something and finish")
    assert "answer" in result, "run() must return an 'answer' key"
    assert result["answer"], "answer must be non-empty"


def test_agent_run_answer_from_last_text_step(monkeypatch):
    """answer comes from the last 'final' step, ignoring earlier REST steps."""
    agent = CartaAgent([_N8N], model="test", base_url="http://localhost:1")

    replies = iter(
        [
            '{"route":"rest","command":"echo hola"}',
            "respuesta final",
        ]
    )

    def fake_chat(self, messages):  # noqa: ANN001
        return next(replies)

    monkeypatch.setattr(CartaAgent, "_chat", fake_chat)

    result = agent.run("do a rest call then answer")
    assert result["answer"] == "respuesta final"


# --------------------------------------------------------------------------- #
# Part D — local_append_file error shape
# --------------------------------------------------------------------------- #
def test_local_append_error_has_path(tmp_path):
    """A failed append returns ok=False AND includes the ``path`` key."""
    target = str(tmp_path / "missing_subdir" / "archivo.txt")
    res = local_append_file(target, "contenido")
    assert res["ok"] is False
    assert "path" in res, "append error must include 'path'"
    assert res["path"] == target


# --------------------------------------------------------------------------- #
# Part F — flow undefined variable error
# --------------------------------------------------------------------------- #
_MINIMAL_SPEC = textwrap.dedent(
    """
    id: spec-agent
    model:
      base_url: http://localhost:1234/v1
      name: m
    knowledge: []
    """
).strip()


def _write_spec(specs_dir, agent_id):
    specs_dir.mkdir(parents=True, exist_ok=True)
    p = specs_dir / f"{agent_id}.yaml"
    p.write_text(_MINIMAL_SPEC, encoding="utf-8")
    return p


def _patch_run_noop(monkeypatch, returns):
    """Replace CartaAgent.__init__/run so flow construction never hits network."""
    from carta import agent as agent_mod

    def _fake_init(self, *args, **kwargs):
        pass

    def _fake_run(self, task, provider=None, max_steps=8):
        return returns

    monkeypatch.setattr(agent_mod.CartaAgent, "__init__", _fake_init)
    monkeypatch.setattr(agent_mod.CartaAgent, "run", _fake_run)


def test_flow_undefined_variable_raises(tmp_path, monkeypatch):
    """A stage referencing an undefined variable raises ValueError naming it."""
    specs_dir = tmp_path / "agent-specs"
    _write_spec(specs_dir, "spec-agent")
    flow = load_flow(
        _write_flow(
            tmp_path,
            textwrap.dedent(
                """
                id: bad
                stages:
                  - id: fix
                    agent: spec-agent
                    task: "fix {undefined_key}"
                """
            ).strip(),
        )
    )

    _patch_run_noop(monkeypatch, {"answer": "x", "steps": []})

    with pytest.raises(ValueError) as excinfo:
        run_flow(flow, str(specs_dir))
    assert "undefined_key" in str(excinfo.value)


def test_flow_error_message_lists_available(tmp_path, monkeypatch):
    """The ValueError also lists the available context variables."""
    specs_dir = tmp_path / "agent-specs"
    _write_spec(specs_dir, "spec-agent")
    flow = load_flow(
        _write_flow(
            tmp_path,
            textwrap.dedent(
                """
                id: bad
                stages:
                  - id: fix
                    agent: spec-agent
                    task: "fix {undefined_key}"
                """
            ).strip(),
        )
    )

    _patch_run_noop(monkeypatch, {"answer": "x", "steps": []})

    with pytest.raises(ValueError) as excinfo:
        run_flow(flow, str(specs_dir), initial_input="hello")
    assert "Available variables" in str(excinfo.value)


def _write_flow(tmp_path, content, name="flow.yaml"):
    p = tmp_path / name
    p.write_text(content, encoding="utf-8")
    return str(p)


# --------------------------------------------------------------------------- #
# Part E — CartaAgent constructor params + watcher wiring
# --------------------------------------------------------------------------- #
# --------------------------------------------------------------------------- #
# max_steps summary prompt
# --------------------------------------------------------------------------- #
def test_max_steps_injects_summary_prompt(monkeypatch):
    """On the last available step the agent injects a 'Last step' summary prompt."""
    agent = CartaAgent([_N8N], model="test", base_url="http://localhost:1")

    calls = []

    def fake_chat(self, messages):
        calls.append([m["content"] for m in messages if m["role"] == "user"])
        if len(calls) == 1:
            # First turn: return a tool-like action to stay in the loop
            return '{"route":"rest","command":"echo hello"}'
        # Second (last) turn: return a plain-text summary
        return "I wrote hello.py and it works."

    monkeypatch.setattr(CartaAgent, "_chat", fake_chat)

    result = agent.run("do something", max_steps=2)

    # The last user message before the second _chat call must contain "Last step"
    last_turn_user_msgs = calls[1]
    assert any("Last step" in m for m in last_turn_user_msgs), (
        f"Expected 'Last step' prompt in last turn user messages: {last_turn_user_msgs}"
    )
    assert result["answer"] == "I wrote hello.py and it works."
    assert result["status"] == "done"


# --------------------------------------------------------------------------- #
# api_key → Authorization header
# --------------------------------------------------------------------------- #
def test_agent_sends_auth_header_when_api_key_set(monkeypatch):
    """CartaAgent._chat() sends Authorization: Bearer when api_key is set."""
    agent = CartaAgent([_N8N], model="test", base_url="http://localhost:1", api_key="sk-test")

    captured = {}

    import urllib.request as _urllib_req

    def fake_urlopen(req, timeout=None):
        captured["auth"] = req.get_header("Authorization")

        class _FakeResp:
            def __iter__(self):
                import json as _j
                yield b'data: ' + _j.dumps({"choices": [{"delta": {"content": "done"}}]}).encode() + b'\n'
                yield b'data: [DONE]\n'
            def __enter__(self):
                return self
            def __exit__(self, *a):
                pass

        return _FakeResp()

    monkeypatch.setattr(_urllib_req, "urlopen", fake_urlopen)
    agent._chat([{"role": "user", "content": "hi"}])
    assert captured.get("auth") == "Bearer sk-test"


def test_agent_no_auth_header_without_api_key(monkeypatch):
    """CartaAgent._chat() omits Authorization when api_key is empty."""
    agent = CartaAgent([_N8N], model="test", base_url="http://localhost:1")

    captured = {}
    import urllib.request as _urllib_req

    def fake_urlopen(req, timeout=None):
        captured["auth"] = req.get_header("Authorization")

        class _FakeResp:
            def __iter__(self):
                import json as _j
                yield b'data: ' + _j.dumps({"choices": [{"delta": {"content": "done"}}]}).encode() + b'\n'
                yield b'data: [DONE]\n'
            def __enter__(self):
                return self
            def __exit__(self, *a):
                pass

        return _FakeResp()

    monkeypatch.setattr(_urllib_req, "urlopen", fake_urlopen)
    agent._chat([{"role": "user", "content": "hi"}])
    assert captured.get("auth") is None


def test_chat_retries_transient_network_error(monkeypatch):
    """A transient TimeoutError is retried, not fatal; the second try succeeds."""
    import json as _j
    import urllib.request as _urllib_req

    agent = CartaAgent([_N8N], model="test", base_url="http://localhost:1")
    monkeypatch.setattr(agent, "_CHAT_RETRIES", 3, raising=False)
    # avoid real backoff sleeps
    import carta.agent as _agent_mod
    monkeypatch.setattr(_agent_mod.time, "sleep", lambda *_a: None)

    calls = {"n": 0}

    def fake_urlopen(req, timeout=None):
        calls["n"] += 1
        if calls["n"] == 1:
            raise TimeoutError("read timed out")  # not a URLError subclass

        class _FakeResp:
            def __iter__(self):
                yield b"data: " + _j.dumps({"choices": [{"delta": {"content": "recovered"}}]}).encode() + b"\n"
                yield b"data: [DONE]\n"
            def __enter__(self):
                return self
            def __exit__(self, *a):
                pass

        return _FakeResp()

    monkeypatch.setattr(_urllib_req, "urlopen", fake_urlopen)
    out = agent._chat([{"role": "user", "content": "hi"}])
    assert out == "recovered"
    assert calls["n"] == 2  # failed once, succeeded on retry


def test_chat_does_not_retry_4xx(monkeypatch):
    """A 4xx HTTPError (e.g. bad API key) is raised immediately, not retried."""
    import urllib.error as _urllib_err
    import urllib.request as _urllib_req

    agent = CartaAgent([_N8N], model="test", base_url="http://localhost:1")
    import carta.agent as _agent_mod
    monkeypatch.setattr(_agent_mod.time, "sleep", lambda *_a: None)

    calls = {"n": 0}

    def fake_urlopen(req, timeout=None):
        calls["n"] += 1
        raise _urllib_err.HTTPError(
            "http://x", 401, "Unauthorized", hdrs=None, fp=None
        )

    monkeypatch.setattr(_urllib_req, "urlopen", fake_urlopen)
    import pytest as _pytest
    with _pytest.raises(RuntimeError, match="401"):
        agent._chat([{"role": "user", "content": "hi"}])
    assert calls["n"] == 1  # no retry on client error


def test_chat_synthesizes_action_from_native_tool_calls(monkeypatch):
    """_chat converts native delta.tool_calls (kimi-style) into protocol JSON.

    Code models emit the action in delta.tool_calls with empty content. _chat
    must turn that into ``{"tool": ..., "args": {...}}`` so _extract_action can
    parse it; otherwise the agent sees empty text and stops doing nothing.
    """
    import json as _j
    import urllib.request as _urllib_req

    agent = CartaAgent([_N8N], model="test", base_url="http://localhost:1")

    def fake_urlopen(req, timeout=None):
        class _FakeResp:
            def __iter__(self):
                # name + first arg fragment, then the rest of the arguments
                yield b"data: " + _j.dumps({"choices": [{"delta": {"tool_calls": [
                    {"index": 0, "function": {"name": "read_file", "arguments": '{"path":'}}
                ]}}]}).encode() + b"\n"
                yield b"data: " + _j.dumps({"choices": [{"delta": {"tool_calls": [
                    {"index": 0, "function": {"arguments": '"tests/frozen"}'}}
                ]}}]}).encode() + b"\n"
                yield b"data: [DONE]\n"
            def __enter__(self):
                return self
            def __exit__(self, *a):
                pass

        return _FakeResp()

    monkeypatch.setattr(_urllib_req, "urlopen", fake_urlopen)
    out = agent._chat([{"role": "user", "content": "hi"}])
    parsed = _j.loads(out)
    assert parsed["tool"] == "read_file"
    assert parsed["args"] == {"path": "tests/frozen"}


def test_chat_prefers_content_over_tool_calls(monkeypatch):
    """When the model emits text content, _chat returns it verbatim."""
    import json as _j
    import urllib.request as _urllib_req

    agent = CartaAgent([_N8N], model="test", base_url="http://localhost:1")

    def fake_urlopen(req, timeout=None):
        class _FakeResp:
            def __iter__(self):
                yield b"data: " + _j.dumps({"choices": [{"delta": {"content": "all done"}}]}).encode() + b"\n"
                yield b"data: [DONE]\n"
            def __enter__(self):
                return self
            def __exit__(self, *a):
                pass

        return _FakeResp()

    monkeypatch.setattr(_urllib_req, "urlopen", fake_urlopen)
    assert agent._chat([{"role": "user", "content": "hi"}]) == "all done"


def test_carta_agent_accepts_agent_id():
    """agent_id kwarg is stored on _agent_id without raising."""
    agent = CartaAgent([_N8N], model="test", base_url="http://x", agent_id="my-agent")
    assert agent._agent_id == "my-agent"


def test_carta_agent_accepts_postal_dir():
    """postal_dir kwarg is stored on _postal_dir_base without raising."""
    agent = CartaAgent([_N8N], model="test", base_url="http://x", postal_dir="/custom/postal")
    assert agent._postal_dir_base == "/custom/postal"


def test_watcher_passes_agent_id_to_agent(tmp_path, monkeypatch):
    """watch() passes agent_id=<config.id> to the CartaAgent constructor."""
    from carta import agent as agent_mod
    from carta.watcher import watch

    inbox = tmp_path / ".postal" / "inbox" / "coder-agent"
    inbox.mkdir(parents=True)
    (inbox / "1700000000-msg1.json").write_text(
        json.dumps(
            {
                "id": "msg1",
                "task": "build X",
                "from": "spec-agent",
                "to": "coder-agent",
                "timestamp": "2024-01-01T00:00:00",
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / ".postal" / "processed").mkdir(parents=True)

    specs = tmp_path / "agent-specs"
    _write_spec(specs, "coder-agent")
    # The watcher's spec parser reads model.name; ensure it is present.
    (specs / "coder-agent.yaml").write_text(
        textwrap.dedent(
            """
            id: coder-agent
            model:
              base_url: http://localhost:1234/v1
              name: test-model
            knowledge: []
            """
        ).strip(),
        encoding="utf-8",
    )

    captured = {}

    def fake_init(self, *args, **kwargs):
        captured.update(kwargs)

    def fake_run(self, task, max_steps=8, provider=None):
        return {"steps": [], "answer": "done", "status": "done"}

    monkeypatch.setattr(agent_mod.CartaAgent, "__init__", fake_init)
    monkeypatch.setattr(agent_mod.CartaAgent, "run", fake_run)

    watch(str(tmp_path), poll_interval=0, idle_stop=1, max_rounds=50)

    assert captured.get("agent_id") == "coder-agent"