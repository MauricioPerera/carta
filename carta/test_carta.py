"""Tests for the carta package (T12).

No network, no LM Studio. The agent loop is driven by monkeypatching
``CartaAgent._chat`` with scripted replies.
"""
from __future__ import annotations

import os

import pytest

from carta import CartaAgent, CartaClient

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_N8N = os.path.join(_REPO_ROOT, "okf", "n8n")
_JP = os.path.join(_REPO_ROOT, "okf", "jsonplaceholder")


# --------------------------------------------------------------------------- #
# CartaClient.select / route_of / execute
# --------------------------------------------------------------------------- #
def test_client_select():
    """Select returns trimmed context (tokens < baseline) with the right skill."""
    client = CartaClient([_N8N])
    res = client.select("create workflow webhook")
    assert res["docs"], "expected non-empty docs"
    names = [d["name"] for d in res["docs"]]
    assert "create-workflow" in names, f"missing create-workflow: {names}"
    assert res["tokens"] < res["baseline_tokens"], (
        f"trimmed tokens {res['tokens']} not < baseline {res['baseline_tokens']}"
    )


def test_client_route_of():
    """route_of reads the frontmatter route for both rest and mcp docs."""
    client = CartaClient([_N8N])
    # search_nodes is an mcp tool in okf/n8n.
    mcp_doc = next(d for d in client.select("search nodes")["docs"] if d["name"] == "search_nodes")
    assert client.route_of(mcp_doc) == "mcp", "search_nodes should be mcp"

    # create_workflow_from_code is a rest tool in okf/n8n.
    rest_doc = next(
        d for d in client.select("create workflow from code")["docs"]
        if d["name"] == "create_workflow_from_code"
    )
    assert client.route_of(rest_doc) == "rest", "create_workflow_from_code should be rest"


def test_route_of_local():
    """route_of returns 'local' for a doc declaring route: local."""
    client = CartaClient([_N8N])
    doc = {"frontmatter": {"route": "local"}, "name": "fake_local"}
    assert client.route_of(doc) == "local"


def test_route_of_internal():
    """route_of returns 'internal' for a doc declaring route: internal."""
    client = CartaClient([_N8N])
    doc = {"frontmatter": {"route": "internal"}, "name": "fake_internal"}
    assert client.route_of(doc) == "internal"


def test_route_of_unknown_defaults_mcp():
    """route_of defaults to 'mcp' for an unrecognised route value."""
    client = CartaClient([_N8N])
    doc = {"frontmatter": {"route": "carta"}, "name": "fake"}
    assert client.route_of(doc) == "mcp"


def test_route_of_missing_defaults_mcp():
    """route_of defaults to 'mcp' when no route key is present."""
    client = CartaClient([_N8N])
    doc = {"frontmatter": {}, "name": "fake"}
    assert client.route_of(doc) == "mcp"


def test_client_execute_rest():
    """execute_rest runs an allowlisted echo command and captures stdout."""
    client = CartaClient([_N8N])
    res = client.execute({"route": "rest", "command": "echo hola"})
    assert res["exit_code"] == 0, f"echo failed: {res}"
    assert "hola" in res["stdout"], f"stdout missing 'hola': {res}"
    assert res["blocked"] is False


def test_client_execute_mcp_pending():
    """MCP actions are not executed here; they come back as pending."""
    client = CartaClient([_N8N])
    res = client.execute({"route": "mcp", "tool": "validate_workflow", "args": {}})
    assert res["pending_mcp"] is True
    assert res["tool"] == "validate_workflow"
    assert res["args"] == {}


# --------------------------------------------------------------------------- #
# CartaAgent._extract_action
# --------------------------------------------------------------------------- #
def test_agent_extract_action_block():
    """A fenced code block is extracted as kind='block' with its code."""
    agent = CartaAgent([_N8N], model="stub")
    text = "Here is the workflow:\n```typescript\nconst wf = {};\n```\nDone."
    action = agent._extract_action(text)
    assert action["kind"] == "block", action
    assert "const wf = {};" in action["code"], action


def test_agent_extract_action_json():
    """A JSON tool call is extracted, tolerating backslash line-continuations."""
    agent = CartaAgent([_N8N], model="stub")
    # Note the trailing backslash before the newline: the small-model failure
    # mode we normalize.
    text = '{"tool":"search_nodes",\\\n "args":{"queries":["gmail"]}}'
    action = agent._extract_action(text)
    assert action["kind"] == "action", action
    assert action["tool"] == "search_nodes", action
    assert action["args"] == {"queries": ["gmail"]}, action


def test_agent_extract_action_json_fenced_with_payload():
    """Tool call wrapped in a ```json fence + a separate payload fence.

    Regression: previously the ```json fence was captured as the payload block,
    so the tool-call JSON got stitched into the file content. Now the fenced
    tool call is parsed as the action and the OTHER fence is the inline payload.
    """
    agent = CartaAgent([_N8N], model="stub")
    text = (
        "```json\n"
        '{"tool": "write_file", "args": {"path": "t.py", "content": "see block below"}}\n'
        "```\n"
        "```python\n"
        "def test_ok():\n    assert True\n"
        "```\n"
    )
    action = agent._extract_action(text)
    assert action["kind"] == "action", action
    assert action["tool"] == "write_file", action
    assert "def test_ok()" in action["_inline_block"], action
    # the tool-call JSON must NOT leak into the payload
    assert "write_file" not in action["_inline_block"], action


def test_agent_extract_action_plain_json_with_payload_fence():
    """Plain (unfenced) tool call followed by a payload fence."""
    agent = CartaAgent([_N8N], model="stub")
    text = (
        '{"tool": "write_file", "args": {"path": "t.py", "content": "see block below"}}\n'
        "```python\n"
        "VALUE = 42\n"
        "```\n"
    )
    action = agent._extract_action(text)
    assert action["kind"] == "action", action
    assert action["tool"] == "write_file", action
    assert "VALUE = 42" in action["_inline_block"], action


def test_agent_extract_action_lone_block_unchanged():
    """A lone non-JSON fence is still a payload block (two-turn protocol)."""
    agent = CartaAgent([_N8N], model="stub")
    text = "```python\nprint('hi')\n```"
    action = agent._extract_action(text)
    assert action["kind"] == "block", action
    assert "print('hi')" in action["code"], action


# --------------------------------------------------------------------------- #
# CartaAgent.run (mocked _chat, no network)
# --------------------------------------------------------------------------- #
def test_agent_run_mocked(monkeypatch):
    """Two scripted turns: a rest echo action, then a plain 'done' answer."""
    agent = CartaAgent([_N8N], model="stub")

    replies = iter(
        [
            '{"route":"rest","command":"echo hola"}',
            "done",
        ]
    )

    def fake_chat(self, messages):  # noqa: ANN001 (matches _chat signature)
        return next(replies)

    monkeypatch.setattr(CartaAgent, "_chat", fake_chat)

    result = agent.run("echo hola and finish")
    assert result["status"] in ("done", "max_steps"), result
    rest_steps = [s for s in result["steps"] if s.get("type") == "rest"]
    assert rest_steps, f"expected a rest execution step, got: {result['steps']}"
    assert rest_steps[0]["exit_code"] == 0, rest_steps[0]
    assert result["context_tokens"] > 0


def test_agent_run_write_file_block_stitch(tmp_path, monkeypatch):
    """End-to-end regression of the workspace bug.

    The model emits, in ONE turn, a ```json-fenced write_file call (content="see
    block below") plus a ```python payload fence. The file on disk must contain
    the Python code — NOT the tool-call JSON.
    """
    # OKF doc making write_file a route: local tool.
    okf_dir = tmp_path / "okf"
    okf_dir.mkdir()
    (okf_dir / "write_file.md").write_text(
        "---\n"
        "type: tool\n"
        "title: Write File\n"
        "name: write_file\n"
        "route: local\n"
        "description: write a file to disk\n"
        "when_to_use: to save code\n"
        "tags: [local, io]\n"
        "---\n"
        "Write text to a path.\n",
        encoding="utf-8",
    )

    target = tmp_path / "out.py"
    agent = CartaAgent([str(okf_dir)], model="stub")

    # Pin selection to the write_file doc so the test exercises the run loop /
    # block-stitching path, not the selector's relevance tuning.
    write_doc = {"name": "write_file", "frontmatter": {"route": "local"}}
    monkeypatch.setattr(
        agent.client,
        "select",
        lambda task, provider=None: {
            "docs": [write_doc],
            "context": "write_file: route local",
            "tokens": 5,
            "baseline_tokens": 10,
        },
    )

    replies = iter(
        [
            "```json\n"
            '{"tool": "write_file", "args": {"path": "'
            + target.as_posix()
            + '", "content": "see block below"}}\n'
            "```\n"
            "```python\n"
            "def test_ok():\n    assert True\n"
            "```\n",
            "done",
        ]
    )

    def fake_chat(self, messages):  # noqa: ANN001
        return next(replies)

    monkeypatch.setattr(CartaAgent, "_chat", fake_chat)

    agent.run("write the test file")

    assert target.is_file(), "write_file did not create the target"
    content = target.read_text(encoding="utf-8")
    assert "def test_ok()" in content, content
    assert "see block below" not in content, content
    assert '"tool"' not in content, f"tool-call JSON leaked into file: {content}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])