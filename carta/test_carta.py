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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])