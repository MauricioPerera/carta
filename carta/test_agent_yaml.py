"""Tests for carta.agent_yaml and the `python -m carta` CLI."""
from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path

from carta.agent_yaml import AgentConfig, load_agent_yaml

_VALID_YAML = textwrap.dedent(
    """
    id: test-agent
    model:
      base_url: http://localhost:1234/v1
      name: glm-5.2:cloud
      timeout: 30
      max_steps: 4
    knowledge:
      - okf/n8n/
    governance:
      contract: .ccdd/agent-a.yaml
    postal:
      identity: .postal/users/me.json
      audit_dir: .postal/audit
    triggers:
      - type: manual
      - type: mailbox
    """
).strip()


def _write(tmp_path: Path, content: str) -> str:
    p = tmp_path / "agent.yaml"
    p.write_text(content, encoding="utf-8")
    return str(p)


def test_load_valid(tmp_path):
    path = _write(tmp_path, _VALID_YAML)
    cfg = load_agent_yaml(path)
    assert isinstance(cfg, AgentConfig)
    assert cfg.id == "test-agent"
    assert cfg.model["base_url"] == "http://localhost:1234/v1"
    assert cfg.model["name"] == "glm-5.2:cloud"
    assert cfg.model["timeout"] == 30
    assert cfg.model["max_steps"] == 4
    assert cfg.knowledge == ["okf/n8n/"]
    assert cfg.governance["contract"] == ".ccdd/agent-a.yaml"
    assert cfg.postal["identity"] == ".postal/users/me.json"
    assert cfg.postal["audit_dir"] == ".postal/audit"
    assert len(cfg.triggers) == 2
    assert cfg.triggers[0]["type"] == "manual"


def test_load_minimal(tmp_path):
    minimal = "id: mini\nmodel:\n  base_url: http://x/v1\n  name: m\n"
    path = _write(tmp_path, minimal)
    cfg = load_agent_yaml(path)
    assert cfg.id == "mini"
    assert cfg.model["name"] == "m"
    assert cfg.knowledge == []
    assert cfg.governance is None
    assert cfg.postal is None
    assert cfg.triggers == []


def test_missing_id(tmp_path):
    path = _write(tmp_path, "model:\n  base_url: http://x/v1\n  name: m\n")
    try:
        load_agent_yaml(path)
    except ValueError as exc:
        assert "id" in str(exc)
    else:
        raise AssertionError("expected ValueError for missing id")


def test_missing_model_name(tmp_path):
    path = _write(tmp_path, "id: x\nmodel:\n  base_url: http://x/v1\n")
    try:
        load_agent_yaml(path)
    except ValueError as exc:
        assert "model.name" in str(exc)
    else:
        raise AssertionError("expected ValueError for missing model.name")


def test_api_key_literal(tmp_path):
    """api_key as a literal string is stored as-is in model dict."""
    content = (
        "id: a\nmodel:\n  base_url: http://x/v1\n  name: m\n"
        "  api_key: sk-abc123\n"
    )
    cfg = load_agent_yaml(_write(tmp_path, content))
    assert cfg.model["api_key"] == "sk-abc123"


def test_api_key_env_var(tmp_path, monkeypatch):
    """api_key starting with $ is resolved from the environment at load time."""
    monkeypatch.setenv("TEST_CARTA_KEY", "resolved-key-xyz")
    content = (
        "id: a\nmodel:\n  base_url: http://x/v1\n  name: m\n"
        "  api_key: $TEST_CARTA_KEY\n"
    )
    cfg = load_agent_yaml(_write(tmp_path, content))
    assert cfg.model["api_key"] == "resolved-key-xyz"


def test_api_key_env_var_missing(tmp_path, monkeypatch):
    """Unset env var resolves to empty string (no crash)."""
    monkeypatch.delenv("NONEXISTENT_CARTA_KEY", raising=False)
    content = (
        "id: a\nmodel:\n  base_url: http://x/v1\n  name: m\n"
        "  api_key: $NONEXISTENT_CARTA_KEY\n"
    )
    cfg = load_agent_yaml(_write(tmp_path, content))
    assert cfg.model["api_key"] == ""


def test_no_api_key(tmp_path):
    """Agent spec without api_key has no api_key key in model dict."""
    content = "id: a\nmodel:\n  base_url: http://x/v1\n  name: m\n"
    cfg = load_agent_yaml(_write(tmp_path, content))
    assert "api_key" not in cfg.model


def test_cli_no_task_no_mailbox(tmp_path):
    yaml_path = _write(
        tmp_path,
        "id: cli-agent\nmodel:\n  base_url: http://x/v1\n  name: m\n"
        "triggers:\n  - type: manual\n",
    )
    repo_root = str(Path(__file__).resolve().parents[1])
    env = dict(os.environ)
    env["PYTHONPATH"] = repo_root + os.pathsep + env.get("PYTHONPATH", "")
    res = subprocess.run(
        [sys.executable, "-m", "carta", "run", yaml_path],
        capture_output=True,
        text=True,
        cwd=repo_root,
        env=env,
    )
    assert res.returncode == 1, res.stdout + res.stderr


def test_cli_mailbox_mode_message(tmp_path):
    yaml_path = _write(
        tmp_path,
        "id: mb-agent\nmodel:\n  base_url: http://x/v1\n  name: m\n"
        "triggers:\n  - type: mailbox\n",
    )
    repo_root = str(Path(__file__).resolve().parents[1])
    env = dict(os.environ)
    env["PYTHONPATH"] = repo_root + os.pathsep + env.get("PYTHONPATH", "")
    res = subprocess.run(
        [sys.executable, "-m", "carta", "run", yaml_path],
        capture_output=True,
        text=True,
        cwd=repo_root,
        env=env,
    )
    assert res.returncode == 0, res.stdout + res.stderr
    # No --task + mailbox trigger + empty/non-existent inbox -> no pending.
    assert "No pending messages." in res.stdout