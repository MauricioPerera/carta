"""Tests for carta.init and the ``carta init`` CLI subcommand."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import yaml

from carta.agent_yaml import load_agent_yaml
from carta.init import AGENT_ROLES, LOCAL_TOOL_DOCS, PRESETS, init_project


def test_init_creates_dirs(tmp_path):
    init_project(str(tmp_path))
    for sub in ("agents", "agent-specs", ".ccdd", ".okf", ".postal"):
        assert (tmp_path / sub).is_dir(), f"missing dir: {sub}"
    for keep in ("inbox", "audit", "processed"):
        assert (tmp_path / ".postal" / keep / ".gitkeep").is_file()


def test_init_agent_yaml_loadable(tmp_path):
    init_project(str(tmp_path))
    for role in AGENT_ROLES:
        path = tmp_path / "agent-specs" / f"{role}-agent.yaml"
        cfg = load_agent_yaml(str(path))
        assert cfg.id == f"{role}-agent"
        assert cfg.model["base_url"] == "http://localhost:1234/v1"
        assert cfg.governance["contract"] == f".ccdd/{role}.yaml"
        assert any(t.get("type") == "mailbox" for t in cfg.triggers)


def test_init_ccdd_valid_yaml(tmp_path):
    init_project(str(tmp_path), name="test-proj")
    for role, spec in AGENT_ROLES.items():
        path = tmp_path / ".ccdd" / f"{role}.yaml"
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        assert data["agent"] == f"{role}-agent"
        assert data["project"] == "test-proj"
        assert isinstance(data["can"], list) and data["can"]
        assert isinstance(data["cannot"], list) and data["cannot"]
        assert data["can"] == spec["ccdd"]["can"]
        assert data["cannot"] == spec["ccdd"]["cannot"]


def test_init_returns_paths(tmp_path):
    created = init_project(str(tmp_path))
    assert isinstance(created, list) and created
    # 4 roles * (md + yaml + ccdd) + 1 tools md + 5 local tool docs
    # + 1 example flow + 1 conftest + 1 CLAUDE.md + 3 gitkeep = 24
    assert len(created) == 4 * 3 + 1 + 5 + 1 + 1 + 1 + 3
    for p in created:
        assert os.path.exists(p)


def test_init_writes_okf_agent_docs(tmp_path):
    init_project(str(tmp_path))
    for role in AGENT_ROLES:
        path = tmp_path / "agents" / "skills" / f"{role}-agent.md"
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        assert content.startswith("---\n")
        fm, _body = content[4:].split("---", 1)
        data = yaml.safe_load(fm)
        assert data["type"] == "agent"
        assert data["agent_yaml"] == f"agent-specs/{role}-agent.yaml"
    assert (tmp_path / ".okf" / "project-tools.md").is_file()


def test_init_creates_claude_md(tmp_path):
    init_project(str(tmp_path), name="test-proj")
    claude_md = tmp_path / "CLAUDE.md"
    assert claude_md.is_file()
    content = claude_md.read_text(encoding="utf-8")
    assert content.startswith("# CLAUDE.md")
    assert "test-proj" in content


def test_claude_md_contains_commands(tmp_path):
    init_project(str(tmp_path))
    content = (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")
    assert "carta route" in content
    assert "carta run" in content


def test_claude_md_lists_agents(tmp_path):
    init_project(str(tmp_path))
    content = (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")
    for role in ("spec", "coder", "tester", "reviewer"):
        assert f"{role}-agent" in content


def test_init_creates_local_tool_docs(tmp_path):
    init_project(str(tmp_path))
    tools_dir = tmp_path / ".okf" / "tools"
    assert tools_dir.is_dir()
    for tool_name in LOCAL_TOOL_DOCS:
        assert (tools_dir / f"{tool_name}.md").is_file(), f"missing {tool_name}.md"


def test_local_tool_docs_have_route_local(tmp_path):
    init_project(str(tmp_path))
    tools_dir = tmp_path / ".okf" / "tools"
    for tool_name in LOCAL_TOOL_DOCS:
        content = (tools_dir / f"{tool_name}.md").read_text(encoding="utf-8")
        assert "route: local" in content, f"{tool_name}.md missing 'route: local'"


def test_init_creates_example_flow(tmp_path):
    init_project(str(tmp_path))
    flow_file = tmp_path / "flows" / "example.flow.yaml"
    assert flow_file.is_file()


def test_example_flow_has_stages(tmp_path):
    init_project(str(tmp_path), name="myproj")
    flow_file = tmp_path / "flows" / "example.flow.yaml"
    data = yaml.safe_load(flow_file.read_text(encoding="utf-8"))
    assert "id" in data
    assert "myproj" in data["id"]
    assert isinstance(data.get("stages"), list) and len(data["stages"]) >= 2


def test_example_flow_interpolates(tmp_path):
    """Each generated stage task resolves cleanly with format_map (no leftover
    unescaped braces, no KeyError). The decompose stage takes {input}; the
    implement stage takes {item[...]}."""
    init_project(str(tmp_path))
    flow_file = tmp_path / "flows" / "example.flow.yaml"
    data = yaml.safe_load(flow_file.read_text(encoding="utf-8"))

    decompose = next(s for s in data["stages"] if s["id"] == "decompose")
    rendered = decompose["task"].format_map({"input": "SPEC.md"})
    assert "SPEC.md" in rendered
    assert "{{" not in rendered and "}}" not in rendered  # JSON braces unescaped

    impl = next(s for s in data["stages"] if s["id"] == "implement")
    item = "tests/frozen/test_u.py"  # glob items are file-path strings
    rendered_impl = impl["task"].format_map({"item": item})
    assert "tests/frozen/test_u.py" in rendered_impl
    # the per-item gate also interpolates the item's test path
    assert "tests/frozen/test_u.py" in impl["gate"].format_map({"item": item})


def test_example_flow_is_ccdd_decomposed_shape(tmp_path):
    """The generated flow is the CCDD decomposition: decompose → foreach → integrate."""
    init_project(str(tmp_path))
    flow_file = tmp_path / "flows" / "example.flow.yaml"
    data = yaml.safe_load(flow_file.read_text(encoding="utf-8"))
    by_id = {s["id"]: s for s in data["stages"]}

    # 1. decompose: strong model authors per-unit tests, frozen
    dec = by_id["decompose"]
    assert dec["agent"] == "spec-agent"
    assert dec["freeze"] == "tests/frozen"
    assert "compileall" in dec["gate"]  # syntax gate before freezing
    # adversarial oracle review by an INDEPENDENT agent before freeze
    assert dec["attest"] == "reviewer-agent"
    assert dec["attest"] != dec["agent"]  # author must not attest itself

    # 2. implement: fan out one gated atomic unit per frozen test file (glob)
    impl = by_id["implement"]
    assert impl["foreach"].startswith("glob:tests/frozen/")
    assert impl["verify_frozen"] is True
    assert "{item}" in impl["gate"]
    assert isinstance(impl["budget"], dict) and impl["budget"]["cyclomatic_max"] > 0
    assert impl["gate_escalate_model"]

    # 3. integrate: composition gate over the FULL suite
    integ = by_id["integrate"]
    assert "tests/frozen/" in integ["gate"]
    assert "item" not in integ["gate"]  # full-suite, not per-item


def test_max_steps_sized_by_role_io(tmp_path):
    """max_steps reflects each role's I/O: the spec authors the whole oracle and
    the reviewer reads every test to attest, so both need more steps than the
    atomic per-unit coder. All roles exceed the trivial 8-step default."""
    init_project(str(tmp_path))
    spec = load_agent_yaml(str(tmp_path / "agent-specs" / "spec-agent.yaml"))
    coder = load_agent_yaml(str(tmp_path / "agent-specs" / "coder-agent.yaml"))
    reviewer = load_agent_yaml(str(tmp_path / "agent-specs" / "reviewer-agent.yaml"))
    # the oracle author needs the most (writes one test file per unit)
    assert spec.model["max_steps"] >= 30
    # the attestation reviewer must read spec + every frozen test file
    assert reviewer.model["max_steps"] >= 30
    # the per-unit coder still needs more than the trivial default
    assert coder.model["max_steps"] >= 20


def test_init_creates_conftest(tmp_path):
    """conftest.py at root puts src/ on sys.path for the pytest gate."""
    init_project(str(tmp_path))
    conftest = tmp_path / "conftest.py"
    assert conftest.is_file()
    content = conftest.read_text(encoding="utf-8")
    assert "src" in content
    assert "sys.path" in content


def test_conftest_makes_src_importable(tmp_path, monkeypatch):
    """Executing the generated conftest inserts an existing src/ into sys.path."""
    import sys

    init_project(str(tmp_path))
    (tmp_path / "src").mkdir(exist_ok=True)
    (tmp_path / "src" / "mymod.py").write_text("VALUE = 42\n", encoding="utf-8")

    conftest = tmp_path / "conftest.py"
    src_path = str(tmp_path / "src")
    ns = {"__file__": str(conftest)}
    exec(compile(conftest.read_text(encoding="utf-8"), str(conftest), "exec"), ns)
    try:
        assert src_path in sys.path
    finally:
        if src_path in sys.path:
            sys.path.remove(src_path)


def test_example_flow_implement_has_gate(tmp_path):
    """The implement stage ships with a pytest gate and retries."""
    init_project(str(tmp_path))
    flow_file = tmp_path / "flows" / "example.flow.yaml"
    data = yaml.safe_load(flow_file.read_text(encoding="utf-8"))
    impl = next(s for s in data["stages"] if s["id"] == "implement")
    assert "pytest" in impl["gate"]
    assert impl["gate_retries"] >= 1


def test_preset_ollama_cloud_sets_models(tmp_path):
    """ollama-cloud preset assigns cloud models and sets base_url."""
    init_project(str(tmp_path), preset="ollama-cloud")
    preset = PRESETS["ollama-cloud"]
    for role in AGENT_ROLES:
        path = tmp_path / "agent-specs" / f"{role}-agent.yaml"
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert data["model"]["name"] == preset[role], (
            f"{role}-agent model should be {preset[role]!r}"
        )
        assert data["model"]["base_url"] == preset["base_url"]


def test_preset_ollama_cloud_explicit_base_url_wins(tmp_path):
    """Explicit --base-url overrides the preset's base_url."""
    custom_url = "https://my.proxy/v1"
    init_project(str(tmp_path), preset="ollama-cloud", base_url=custom_url)
    for role in AGENT_ROLES:
        path = tmp_path / "agent-specs" / f"{role}-agent.yaml"
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert data["model"]["base_url"] == custom_url


def test_preset_ollama_local_sets_models(tmp_path):
    """ollama-local preset assigns local models."""
    init_project(str(tmp_path), preset="ollama-local")
    preset = PRESETS["ollama-local"]
    for role in AGENT_ROLES:
        path = tmp_path / "agent-specs" / f"{role}-agent.yaml"
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert data["model"]["name"] == preset[role]
        assert data["model"]["base_url"] == preset["base_url"]


def test_preset_unknown_ignored(tmp_path):
    """Unknown preset is silently ignored — default models apply."""
    init_project(str(tmp_path), preset="nonexistent-preset")
    for role, spec in AGENT_ROLES.items():
        path = tmp_path / "agent-specs" / f"{role}-agent.yaml"
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert data["model"]["name"] == spec["model"]


def test_preset_with_api_key(tmp_path):
    """Preset + api_key writes api_key into every agent-spec."""
    init_project(str(tmp_path), preset="ollama-cloud", api_key="$OLLAMA_API_KEY")
    for role in AGENT_ROLES:
        path = tmp_path / "agent-specs" / f"{role}-agent.yaml"
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert data["model"]["api_key"] == "$OLLAMA_API_KEY"


def test_claude_md_mentions_flow(tmp_path):
    init_project(str(tmp_path))
    content = (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")
    assert "carta flow" in content


def test_cli_init(tmp_path):
    repo_root = str(Path(__file__).resolve().parents[1])
    env = dict(os.environ)
    env["PYTHONPATH"] = repo_root + os.pathsep + env.get("PYTHONPATH", "")
    target = tmp_path / "site"
    res = subprocess.run(
        [sys.executable, "-m", "carta", "init", str(target), "--name", "test"],
        capture_output=True,
        text=True,
        cwd=repo_root,
        env=env,
    )
    assert res.returncode == 0, res.stdout + res.stderr
    assert "Initialized Carta project" in res.stdout
    for sub in ("agents", "agent-specs", ".ccdd", ".okf", ".postal"):
        assert (target / sub).is_dir()