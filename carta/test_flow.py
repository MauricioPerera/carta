"""Tests for carta.flow (``carta flow`` declarative pipeline)."""
from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from carta.flow import load_flow, run_flow


_VALID_SPEC_YAML = textwrap.dedent(
    """
    id: {agent_id}
    model:
      base_url: http://localhost:1234/v1
      name: glm-5.2:cloud
      timeout: 30
      max_steps: 4
    knowledge: []
    """
).strip()


def _write_spec(specs_dir: Path, agent_id: str) -> Path:
    """Write a minimal valid agent.yaml for ``agent_id`` into specs_dir."""
    specs_dir.mkdir(parents=True, exist_ok=True)
    p = specs_dir / f"{agent_id}.yaml"
    p.write_text(_VALID_SPEC_YAML.format(agent_id=agent_id), encoding="utf-8")
    return p


def make_specs(tmp_path, agents=("spec-agent", "coder-agent", "tester-agent")) -> Path:
    """Create an agent-specs/ dir with valid YAMLs for the given agents."""
    specs_dir = tmp_path / "agent-specs"
    for a in agents:
        _write_spec(specs_dir, a)
    return specs_dir


def _write_flow(tmp_path: Path, content: str, name: str = "flow.yaml") -> str:
    p = tmp_path / name
    p.write_text(content, encoding="utf-8")
    return str(p)


# --- load_flow ---------------------------------------------------------------


def test_load_flow_valid(tmp_path):
    content = textwrap.dedent(
        """
        id: fix-and-test
        stages:
          - id: a
            agent: spec-agent
            task: "do {input}"
          - id: b
            agent: coder-agent
            task: "fix {input}"
        """
    ).strip()
    path = _write_flow(tmp_path, content)
    flow = load_flow(path)
    assert flow["id"] == "fix-and-test"
    assert len(flow["stages"]) == 2


def test_load_flow_missing_id(tmp_path):
    content = textwrap.dedent(
        """
        stages:
          - id: a
            agent: spec-agent
            task: "do {input}"
        """
    ).strip()
    path = _write_flow(tmp_path, content)
    with pytest.raises(ValueError):
        load_flow(path)


def test_load_flow_empty_stages(tmp_path):
    content = textwrap.dedent(
        """
        id: fix-and-test
        stages: []
        """
    ).strip()
    path = _write_flow(tmp_path, content)
    with pytest.raises(ValueError):
        load_flow(path)


def test_load_flow_stage_missing_agent(tmp_path):
    content = textwrap.dedent(
        """
        id: fix-and-test
        stages:
          - id: a
            task: "do {input}"
        """
    ).strip()
    path = _write_flow(tmp_path, content)
    with pytest.raises(ValueError):
        load_flow(path)


# --- run_flow ----------------------------------------------------------------


def _patch_run(monkeypatch, returns):
    """Monkeypatch CartaAgent.run to return from a list/sequence of dicts.

    Also neutralizes ``CartaAgent.__init__`` so construction does not require
    a real catalog path / model endpoint — only ``run`` is exercised.
    """
    from carta import agent as agent_mod

    calls = {"count": 0}

    def _fake_init(self, *args, **kwargs):
        pass

    def _fake_run(self, task, provider=None, max_steps=8):
        calls["count"] += 1
        if isinstance(returns, list):
            return returns[calls["count"] - 1]
        return returns

    monkeypatch.setattr(agent_mod.CartaAgent, "__init__", _fake_init)
    monkeypatch.setattr(agent_mod.CartaAgent, "run", _fake_run)
    return calls


def test_run_flow_single_stage(tmp_path, monkeypatch):
    specs_dir = make_specs(tmp_path, ("spec-agent",))
    content = textwrap.dedent(
        """
        id: single
        stages:
          - id: describe
            agent: spec-agent
            task: "describe {input}"
        """
    ).strip()
    flow = load_flow(_write_flow(tmp_path, content))

    _patch_run(monkeypatch, {"answer": "found bugs", "steps": []})

    result = run_flow(flow, str(specs_dir), initial_input="myfile.py")

    assert result["stages_run"] == 1
    assert result["final_answer"] == "found bugs"
    assert result["context"]["input"] == "myfile.py"


def test_run_flow_context_passes(tmp_path, monkeypatch):
    specs_dir = make_specs(tmp_path, ("spec-agent", "coder-agent"))
    content = textwrap.dedent(
        """
        id: two
        stages:
          - id: analyze
            agent: spec-agent
            task: "find bugs in {input}"
            output_key: fixes
          - id: implement
            agent: coder-agent
            task: "fix {fixes}"
        """
    ).strip()
    flow = load_flow(_write_flow(tmp_path, content))

    _patch_run(
        monkeypatch,
        [
            {"answer": "bug list", "steps": []},
            {"answer": "code written", "steps": []},
        ],
    )

    result = run_flow(flow, str(specs_dir), initial_input="app.py")

    # The second stage task must contain the interpolated "bug list".
    assert "bug list" in result["results"][1]["task"]
    assert result["final_answer"] == "code written"
    assert result["context"]["fixes"] == "bug list"


def test_run_flow_missing_variable(tmp_path, monkeypatch):
    specs_dir = make_specs(tmp_path, ("spec-agent",))
    content = textwrap.dedent(
        """
        id: bad
        stages:
          - id: fix
            agent: spec-agent
            task: "fix {undefined_key}"
        """
    ).strip()
    flow = load_flow(_write_flow(tmp_path, content))

    # Even if run were callable, it must not be reached.
    _patch_run(monkeypatch, {"answer": "should not happen", "steps": []})

    with pytest.raises(ValueError):
        run_flow(flow, str(specs_dir))


def test_run_flow_missing_spec(tmp_path):
    specs_dir = make_specs(tmp_path, ("spec-agent",))  # no ghost-agent.yaml
    content = textwrap.dedent(
        """
        id: ghost
        stages:
          - id: a
            agent: ghost-agent
            task: "do {input}"
        """
    ).strip()
    flow = load_flow(_write_flow(tmp_path, content))

    with pytest.raises(FileNotFoundError):
        run_flow(flow, str(specs_dir), initial_input="x")


def test_run_flow_three_stages(tmp_path, monkeypatch):
    specs_dir = make_specs(tmp_path, ("spec-agent", "coder-agent", "tester-agent"))
    content = textwrap.dedent(
        """
        id: three
        stages:
          - id: analyze
            agent: spec-agent
            task: "analyze {input}"
            output_key: fixes
          - id: implement
            agent: coder-agent
            task: "implement {fixes}"
            output_key: code
          - id: verify
            agent: tester-agent
            task: "verify {code}"
            output_key: test_results
        """
    ).strip()
    flow = load_flow(_write_flow(tmp_path, content))

    _patch_run(
        monkeypatch,
        [
            {"answer": "fixes-a", "steps": [{"x": 1}]},
            {"answer": "code-b", "steps": [{"x": 2}]},
            {"answer": "tests-c", "steps": [{"x": 3}]},
        ],
    )

    result = run_flow(flow, str(specs_dir), initial_input="file.py")

    assert result["stages_run"] == 3
    assert result["context"]["fixes"] == "fixes-a"
    assert result["context"]["code"] == "code-b"
    assert result["context"]["test_results"] == "tests-c"
    assert result["final_answer"] == "tests-c"


# --- gate --------------------------------------------------------------------


def _patch_gate(monkeypatch, exit_codes: list[int]):
    """Monkeypatch carta.local.local_run_command with scripted exit codes."""
    import carta.local as local_mod

    _codes = iter(exit_codes)
    gate_calls = {"count": 0}

    def _fake(command, cwd=None, timeout=30):
        gate_calls["count"] += 1
        try:
            code = next(_codes)
        except StopIteration:
            code = 0
        # Mirror local_run_command's real contract: status under "returncode".
        if code == 0:
            return {"ok": True, "stdout": "all good", "stderr": "", "returncode": 0}
        return {"ok": False, "stdout": "", "stderr": "FAILED: 1 error", "returncode": code}

    monkeypatch.setattr(local_mod, "local_run_command", _fake)
    return gate_calls


def test_load_flow_gate_string(tmp_path):
    """load_flow accepts a stage with a string gate command."""
    content = textwrap.dedent(
        """
        id: gated
        stages:
          - id: code
            agent: coder-agent
            task: "write {input}"
            gate: "pytest tests/ -q"
        """
    ).strip()
    flow = load_flow(_write_flow(tmp_path, content))
    assert flow["stages"][0]["gate"] == "pytest tests/ -q"


def test_load_flow_gate_non_string_rejected(tmp_path):
    """load_flow rejects a non-string gate value."""
    content = textwrap.dedent(
        """
        id: bad
        stages:
          - id: code
            agent: coder-agent
            task: "write {input}"
            gate: 42
        """
    ).strip()
    with pytest.raises(ValueError, match="gate"):
        load_flow(_write_flow(tmp_path, content))


def test_gate_passes_first_attempt(tmp_path, monkeypatch):
    """Gate exit_code=0 on first attempt: agent runs once, result has gate.passed=True."""
    specs_dir = make_specs(tmp_path, ("coder-agent",))
    content = textwrap.dedent(
        """
        id: gated
        stages:
          - id: code
            agent: coder-agent
            task: "write {input}"
            gate: "pytest tests/ -q"
        """
    ).strip()
    flow = load_flow(_write_flow(tmp_path, content))

    agent_calls = _patch_run(monkeypatch, {"answer": "wrote it", "steps": []})
    gate_calls = _patch_gate(monkeypatch, [0])

    result = run_flow(flow, str(specs_dir), initial_input="task")

    assert agent_calls["count"] == 1
    assert gate_calls["count"] == 1
    assert result["results"][0]["gate"]["passed"] is True


def test_gate_fails_then_retries(tmp_path, monkeypatch):
    """Gate fails once then passes: agent runs twice (initial + 1 retry)."""
    specs_dir = make_specs(tmp_path, ("coder-agent",))
    content = textwrap.dedent(
        """
        id: gated
        stages:
          - id: code
            agent: coder-agent
            task: "write {input}"
            gate: "pytest tests/ -q"
            gate_retries: 1
        """
    ).strip()
    flow = load_flow(_write_flow(tmp_path, content))

    agent_calls = _patch_run(
        monkeypatch,
        [{"answer": "v1", "steps": []}, {"answer": "v2 fixed", "steps": []}],
    )
    gate_calls = _patch_gate(monkeypatch, [1, 0])  # fail, then pass

    result = run_flow(flow, str(specs_dir), initial_input="task")

    assert agent_calls["count"] == 2
    assert gate_calls["count"] == 2
    assert result["results"][0]["gate"]["passed"] is True
    assert result["final_answer"] == "v2 fixed"


def test_gate_exhausted_retries(tmp_path, monkeypatch):
    """All retries exhausted: gate.passed=False, flow continues."""
    specs_dir = make_specs(tmp_path, ("coder-agent",))
    content = textwrap.dedent(
        """
        id: gated
        stages:
          - id: code
            agent: coder-agent
            task: "write {input}"
            gate: "pytest tests/ -q"
            gate_retries: 1
        """
    ).strip()
    flow = load_flow(_write_flow(tmp_path, content))

    _patch_run(monkeypatch, [{"answer": "v1", "steps": []}, {"answer": "v2", "steps": []}])
    _patch_gate(monkeypatch, [1, 1])  # both fail

    result = run_flow(flow, str(specs_dir), initial_input="task")

    assert result["results"][0]["gate"]["passed"] is False
    assert "FAILED" in result["results"][0]["gate"]["output"]


def test_gate_escalate_runs_stronger_agent(tmp_path, monkeypatch):
    """Cheap model exhausts retries → escalate once; gate passes on escalation."""
    specs_dir = make_specs(tmp_path, ("coder-agent", "reviewer-agent"))
    content = textwrap.dedent(
        """
        id: gated
        stages:
          - id: code
            agent: coder-agent
            task: "write {input}"
            gate: "pytest tests/ -q"
            gate_retries: 1
            gate_escalate: reviewer-agent
        """
    ).strip()
    flow = load_flow(_write_flow(tmp_path, content))

    runs = _patch_run(
        monkeypatch,
        [
            {"answer": "v1", "steps": []},
            {"answer": "v2", "steps": []},
            {"answer": "escalated fix", "steps": []},
        ],
    )
    gates = _patch_gate(monkeypatch, [1, 1, 0])  # fail, fail, then escalation passes

    result = run_flow(flow, str(specs_dir), initial_input="task")

    assert runs["count"] == 3, "expected 2 cheap attempts + 1 escalation"
    assert gates["count"] == 3
    assert result["results"][0]["gate"]["passed"] is True
    assert result["final_answer"] == "escalated fix"


def test_gate_escalate_skipped_when_gate_passes(tmp_path, monkeypatch):
    """If the cheap model passes, the stronger agent is never invoked."""
    specs_dir = make_specs(tmp_path, ("coder-agent", "reviewer-agent"))
    content = textwrap.dedent(
        """
        id: gated
        stages:
          - id: code
            agent: coder-agent
            task: "write {input}"
            gate: "pytest tests/ -q"
            gate_retries: 2
            gate_escalate: reviewer-agent
        """
    ).strip()
    flow = load_flow(_write_flow(tmp_path, content))

    runs = _patch_run(monkeypatch, [{"answer": "v1", "steps": []}])
    _patch_gate(monkeypatch, [0])  # passes first attempt

    result = run_flow(flow, str(specs_dir), initial_input="task")

    assert runs["count"] == 1, "escalation must not run when cheap model passes"
    assert result["results"][0]["gate"]["passed"] is True


def test_gate_escalate_model_reruns_same_agent(tmp_path, monkeypatch):
    """gate_escalate_model re-runs the same agent role with a stronger model."""
    specs_dir = make_specs(tmp_path, ("coder-agent",))
    content = textwrap.dedent(
        """
        id: gated
        stages:
          - id: code
            agent: coder-agent
            task: "write {input}"
            gate: "pytest tests/ -q"
            gate_retries: 0
            gate_escalate_model: big-model:cloud
        """
    ).strip()
    flow = load_flow(_write_flow(tmp_path, content))

    from carta import agent as agent_mod

    models_used = []

    def fake_init(self, *args, **kwargs):
        models_used.append(kwargs.get("model"))

    runs = {"n": 0}

    def fake_run(self, task, provider=None, max_steps=8):
        runs["n"] += 1
        return {"answer": f"v{runs['n']}", "steps": []}

    monkeypatch.setattr(agent_mod.CartaAgent, "__init__", fake_init)
    monkeypatch.setattr(agent_mod.CartaAgent, "run", fake_run)
    _patch_gate(monkeypatch, [1, 0])  # cheap fails, escalated passes

    result = run_flow(flow, str(specs_dir), initial_input="task")

    # first attempt used the spec's model, escalation used the override
    assert "big-model:cloud" in models_used
    assert result["results"][0]["gate"]["passed"] is True


def test_load_flow_gate_escalate_must_be_string(tmp_path):
    content = textwrap.dedent(
        """
        id: f
        stages:
          - id: a
            agent: coder-agent
            task: "t"
            gate_escalate: 5
        """
    ).strip()
    with pytest.raises(ValueError, match="'gate_escalate' must be an agent-id string"):
        load_flow(_write_flow(tmp_path, content))


def test_gate_output_in_context(tmp_path, monkeypatch):
    """After gate failure gate_output is available in context for subsequent stages."""
    specs_dir = make_specs(tmp_path, ("coder-agent", "tester-agent"))
    content = textwrap.dedent(
        """
        id: gated
        stages:
          - id: code
            agent: coder-agent
            task: "write {input}"
            gate: "pytest tests/ -q"
            gate_retries: 0
          - id: fix
            agent: tester-agent
            task: "fix based on: {gate_output}"
        """
    ).strip()
    flow = load_flow(_write_flow(tmp_path, content))

    _patch_run(monkeypatch, [{"answer": "v1", "steps": []}, {"answer": "fixed", "steps": []}])
    _patch_gate(monkeypatch, [1])  # gate fails, 0 retries

    result = run_flow(flow, str(specs_dir), initial_input="task")

    assert "gate_output" in result["context"]
    assert "FAILED" in result["results"][1]["task"]


def test_agent_spec_base_url_used_when_no_override(tmp_path, monkeypatch):
    """run_flow uses each agent-spec's base_url when --base-url is not passed."""
    specs_dir = make_specs(tmp_path, ("spec-agent",))
    # Override the spec to use a distinctive URL
    spec_file = specs_dir / "spec-agent.yaml"
    spec_file.write_text(
        _VALID_SPEC_YAML.format(agent_id="spec-agent").replace(
            "http://localhost:1234/v1", "http://custom-host:9999/v1"
        ),
        encoding="utf-8",
    )
    content = textwrap.dedent(
        """
        id: url-test
        stages:
          - id: plan
            agent: spec-agent
            task: "plan {input}"
        """
    ).strip()
    flow = load_flow(_write_flow(tmp_path, content))

    from carta import agent as agent_mod

    captured = {}

    def fake_init(self, *args, **kwargs):
        captured["base_url"] = kwargs.get("base_url")

    def fake_run(self, task, provider=None, max_steps=8):
        return {"answer": "done", "steps": []}

    monkeypatch.setattr(agent_mod.CartaAgent, "__init__", fake_init)
    monkeypatch.setattr(agent_mod.CartaAgent, "run", fake_run)

    run_flow(flow, str(specs_dir))  # no base_url passed

    assert captured["base_url"] == "http://custom-host:9999/v1"


def test_cli_base_url_overrides_agent_spec(tmp_path, monkeypatch):
    """--base-url CLI arg overrides the agent-spec's base_url."""
    specs_dir = make_specs(tmp_path, ("spec-agent",))
    content = textwrap.dedent(
        """
        id: url-override
        stages:
          - id: plan
            agent: spec-agent
            task: "plan {input}"
        """
    ).strip()
    flow = load_flow(_write_flow(tmp_path, content))

    from carta import agent as agent_mod

    captured = {}

    def fake_init(self, *args, **kwargs):
        captured["base_url"] = kwargs.get("base_url")

    def fake_run(self, task, provider=None, max_steps=8):
        return {"answer": "done", "steps": []}

    monkeypatch.setattr(agent_mod.CartaAgent, "__init__", fake_init)
    monkeypatch.setattr(agent_mod.CartaAgent, "run", fake_run)

    run_flow(flow, str(specs_dir), base_url="http://override:5000/v1")

    assert captured["base_url"] == "http://override:5000/v1"


def test_no_gate_no_gate_key_in_result(tmp_path, monkeypatch):
    """Stage without gate produces no 'gate' key in its result record."""
    specs_dir = make_specs(tmp_path, ("spec-agent",))
    content = textwrap.dedent(
        """
        id: no-gate
        stages:
          - id: plan
            agent: spec-agent
            task: "plan {input}"
        """
    ).strip()
    flow = load_flow(_write_flow(tmp_path, content))
    _patch_run(monkeypatch, {"answer": "done", "steps": []})

    result = run_flow(flow, str(specs_dir), initial_input="x")

    assert "gate" not in result["results"][0]


# --- gate contract (no mock — real local_run_command) ------------------------


def test_gate_real_command_pass_and_fail(tmp_path, monkeypatch):
    """_verify_stage uses local_run_command's real 'returncode' contract.

    Regression guard: flow.py previously read a nonexistent 'exit_code' key, so
    a passing pytest gate was always treated as a failure. This test runs real
    shell commands (no mock) to lock the contract.
    """
    from carta.flow import _verify_stage

    monkeypatch.chdir(tmp_path)
    (tmp_path / "pass.py").write_text("import sys; sys.exit(0)\n", encoding="utf-8")
    (tmp_path / "fail.py").write_text("import sys; sys.exit(1)\n", encoding="utf-8")

    # Bare "python" (no backslashes) so shlex.split is portable; real flow gates
    # use "python -m pytest ..." which is likewise backslash-free.
    ok, _ = _verify_stage(
        gate_cmd="python pass.py",
        verify_frozen=False,
        frozen={},
        budget=None,
        budget_paths="src",
    )
    assert ok is True

    ok, out = _verify_stage(
        gate_cmd="python fail.py",
        verify_frozen=False,
        frozen={},
        budget=None,
        budget_paths="src",
    )
    assert ok is False


# --- CCDD: freeze / verify_frozen / budget -----------------------------------


def test_load_flow_freeze_must_be_string(tmp_path):
    content = textwrap.dedent(
        """
        id: f
        stages:
          - id: a
            agent: spec-agent
            task: "t"
            freeze: 123
        """
    ).strip()
    with pytest.raises(ValueError, match="'freeze' must be a path string"):
        load_flow(_write_flow(tmp_path, content))


def test_load_flow_budget_must_be_int_mapping(tmp_path):
    content = textwrap.dedent(
        """
        id: f
        stages:
          - id: a
            agent: coder-agent
            task: "t"
            budget:
              cyclomatic_max: "lots"
        """
    ).strip()
    with pytest.raises(ValueError, match="budget 'cyclomatic_max'"):
        load_flow(_write_flow(tmp_path, content))


def test_load_flow_verify_frozen_must_be_bool(tmp_path):
    content = textwrap.dedent(
        """
        id: f
        stages:
          - id: a
            agent: coder-agent
            task: "t"
            verify_frozen: "yes"
        """
    ).strip()
    with pytest.raises(ValueError, match="'verify_frozen' must be a boolean"):
        load_flow(_write_flow(tmp_path, content))


def test_freeze_records_hashes(tmp_path, monkeypatch):
    """A stage with freeze: locks its output files; result lists them."""
    specs_dir = make_specs(tmp_path, ("spec-agent",))
    (tmp_path / "tests" / "frozen").mkdir(parents=True)
    (tmp_path / "tests" / "frozen" / "test_x.py").write_text(
        "def test_ok():\n    assert True\n", encoding="utf-8"
    )
    content = textwrap.dedent(
        """
        id: ccdd
        stages:
          - id: oracle
            agent: spec-agent
            task: "author {input}"
            freeze: tests/frozen
        """
    ).strip()
    flow = load_flow(_write_flow(tmp_path, content))
    _patch_run(monkeypatch, {"answer": "wrote tests", "steps": []})
    monkeypatch.chdir(tmp_path)

    result = run_flow(flow, str(specs_dir), initial_input="spec")

    frozen = result["results"][0]["frozen"]
    assert any("test_x.py" in p for p in frozen)


def test_freeze_skipped_when_gate_fails(tmp_path, monkeypatch):
    """A stage whose gate fails must NOT freeze its (broken) output.

    Regression: freezing a non-parsing oracle made the downstream gate
    unwinnable because verify_frozen then forbids fixing it.
    """
    specs_dir = make_specs(tmp_path, ("spec-agent",))
    (tmp_path / "tests" / "frozen").mkdir(parents=True)
    (tmp_path / "tests" / "frozen" / "test_x.py").write_text(
        "def test( syntax error\n", encoding="utf-8"
    )
    content = textwrap.dedent(
        """
        id: ccdd
        stages:
          - id: oracle
            agent: spec-agent
            task: "author {input}"
            gate: "python -m compileall -q tests/frozen"
            gate_retries: 0
            freeze: tests/frozen
        """
    ).strip()
    flow = load_flow(_write_flow(tmp_path, content))
    _patch_run(monkeypatch, {"answer": "wrote broken tests", "steps": []})
    monkeypatch.chdir(tmp_path)

    result = run_flow(flow, str(specs_dir), initial_input="spec")

    rec = result["results"][0]
    assert rec["gate"]["passed"] is False
    assert rec["frozen"] == [], "broken oracle must not be frozen"


def test_verify_frozen_detects_tampering(tmp_path, monkeypatch):
    """If the coder stage modifies a frozen file, the gate fails hard."""
    specs_dir = make_specs(tmp_path, ("spec-agent", "coder-agent"))
    frozen_dir = tmp_path / "tests" / "frozen"
    frozen_dir.mkdir(parents=True)
    oracle_file = frozen_dir / "test_x.py"
    oracle_file.write_text("def test_ok():\n    assert True\n", encoding="utf-8")

    content = textwrap.dedent(
        """
        id: ccdd
        stages:
          - id: oracle
            agent: spec-agent
            task: "author {input}"
            freeze: tests/frozen
          - id: implement
            agent: coder-agent
            task: "implement {input}"
            verify_frozen: true
            gate_retries: 0
        """
    ).strip()
    flow = load_flow(_write_flow(tmp_path, content))
    monkeypatch.chdir(tmp_path)

    from carta import agent as agent_mod

    calls = {"count": 0}

    def _fake_init(self, *a, **k):
        pass

    def _fake_run(self, task, provider=None, max_steps=8):
        calls["count"] += 1
        # On the implement stage (2nd call), tamper with the frozen oracle.
        if calls["count"] == 2:
            oracle_file.write_text(
                "def test_ok():\n    assert False  # weakened\n", encoding="utf-8"
            )
        return {"answer": "done", "steps": []}

    monkeypatch.setattr(agent_mod.CartaAgent, "__init__", _fake_init)
    monkeypatch.setattr(agent_mod.CartaAgent, "run", _fake_run)

    result = run_flow(flow, str(specs_dir), initial_input="spec")

    impl = result["results"][1]
    assert impl["gate"]["passed"] is False
    assert "TAMPERED" in impl["gate"]["output"]


def test_verify_frozen_passes_when_untouched(tmp_path, monkeypatch):
    """verify_frozen with intact files and no other gate → passes."""
    specs_dir = make_specs(tmp_path, ("spec-agent", "coder-agent"))
    frozen_dir = tmp_path / "tests" / "frozen"
    frozen_dir.mkdir(parents=True)
    (frozen_dir / "test_x.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")

    content = textwrap.dedent(
        """
        id: ccdd
        stages:
          - id: oracle
            agent: spec-agent
            task: "author {input}"
            freeze: tests/frozen
          - id: implement
            agent: coder-agent
            task: "implement {input}"
            verify_frozen: true
        """
    ).strip()
    flow = load_flow(_write_flow(tmp_path, content))
    _patch_run(monkeypatch, {"answer": "done", "steps": []})
    monkeypatch.chdir(tmp_path)

    result = run_flow(flow, str(specs_dir), initial_input="spec")

    assert result["results"][1]["gate"]["passed"] is True


def test_budget_violation_fails_gate(tmp_path, monkeypatch):
    """A function over the complexity budget fails the stage gate."""
    specs_dir = make_specs(tmp_path, ("coder-agent",))
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "big.py").write_text(
        "def f(a, b, c, d, e, f, g):\n    return a\n", encoding="utf-8"
    )
    content = textwrap.dedent(
        """
        id: ccdd
        stages:
          - id: implement
            agent: coder-agent
            task: "implement {input}"
            gate_retries: 0
            budget:
              params_max: 4
            budget_paths: src
        """
    ).strip()
    flow = load_flow(_write_flow(tmp_path, content))
    _patch_run(monkeypatch, {"answer": "done", "steps": []})
    monkeypatch.chdir(tmp_path)

    result = run_flow(flow, str(specs_dir), initial_input="spec")

    gate = result["results"][0]["gate"]
    assert gate["passed"] is False
    assert "COMPLEXITY BUDGET" in gate["output"]


def test_budget_pass(tmp_path, monkeypatch):
    """A function within budget passes the stage gate."""
    specs_dir = make_specs(tmp_path, ("coder-agent",))
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "ok.py").write_text(
        "def f(x):\n    return x + 1\n", encoding="utf-8"
    )
    content = textwrap.dedent(
        """
        id: ccdd
        stages:
          - id: implement
            agent: coder-agent
            task: "implement {input}"
            budget:
              params_max: 4
              cyclomatic_max: 10
            budget_paths: src
        """
    ).strip()
    flow = load_flow(_write_flow(tmp_path, content))
    _patch_run(monkeypatch, {"answer": "done", "steps": []})
    monkeypatch.chdir(tmp_path)

    result = run_flow(flow, str(specs_dir), initial_input="spec")

    assert result["results"][0]["gate"]["passed"] is True


# --- attest (adversarial oracle review, CCDD R6 analog) ----------------------


def test_load_flow_attest_must_be_string(tmp_path):
    content = textwrap.dedent(
        """
        id: f
        stages:
          - id: a
            agent: spec-agent
            task: "author {input}"
            attest: 1
        """
    ).strip()
    with pytest.raises(ValueError, match="'attest' must be"):
        load_flow(_write_flow(tmp_path, content))


def _patch_run_by_agent(monkeypatch, answers_by_model):
    """Patch CartaAgent so its answer depends on the model it was built with.

    ``answers_by_model`` maps a substring of the model name to the answer text.
    Lets a test distinguish the author agent from the attest (reviewer) agent.
    """
    from carta import agent as agent_mod

    calls = {"count": 0, "models": []}

    def _init(self, *a, **k):
        self._model = k.get("model", "")
        calls["models"].append(self._model)

    def _run(self, task, provider=None, max_steps=8):
        calls["count"] += 1
        for key, ans in answers_by_model.items():
            if key in (self._model or ""):
                return {"answer": ans, "steps": []}
        return {"answer": "ok", "steps": []}

    monkeypatch.setattr(agent_mod.CartaAgent, "__init__", _init)
    monkeypatch.setattr(agent_mod.CartaAgent, "run", _run)
    return calls


def test_attest_pass_allows_freeze(tmp_path, monkeypatch):
    """When the reviewer attests PASS, the oracle is frozen."""
    specs_dir = make_specs(tmp_path, ("spec-agent", "reviewer-agent"))
    # give the two agents distinct model names
    (specs_dir / "spec-agent.yaml").write_text(
        _VALID_SPEC_YAML.format(agent_id="spec-agent").replace(
            "glm-5.2:cloud", "author-model"),
        encoding="utf-8")
    (specs_dir / "reviewer-agent.yaml").write_text(
        _VALID_SPEC_YAML.format(agent_id="reviewer-agent").replace(
            "glm-5.2:cloud", "reviewer-model"),
        encoding="utf-8")
    (tmp_path / "tests" / "frozen").mkdir(parents=True)
    (tmp_path / "tests" / "frozen" / "t.py").write_text("def test(): assert 1\n", encoding="utf-8")
    content = textwrap.dedent(
        """
        id: ccdd
        stages:
          - id: decompose
            agent: spec-agent
            task: "author {input}"
            attest: reviewer-agent
            freeze: tests/frozen
        """
    ).strip()
    flow = load_flow(_write_flow(tmp_path, content))
    _patch_run_by_agent(monkeypatch, {"reviewer-model": "Looks good.\nATTEST: PASS"})
    monkeypatch.chdir(tmp_path)

    result = run_flow(flow, str(specs_dir), initial_input="SPEC.md")

    rec = result["results"][0]
    assert rec["gate"]["passed"] is True
    assert rec["frozen"]  # froze because attestation passed


def test_attest_fail_blocks_freeze_and_retries(tmp_path, monkeypatch):
    """When the reviewer attests FAIL, the oracle is NOT frozen and the author retries."""
    specs_dir = make_specs(tmp_path, ("spec-agent", "reviewer-agent"))
    (specs_dir / "spec-agent.yaml").write_text(
        _VALID_SPEC_YAML.format(agent_id="spec-agent").replace(
            "glm-5.2:cloud", "author-model"),
        encoding="utf-8")
    (specs_dir / "reviewer-agent.yaml").write_text(
        _VALID_SPEC_YAML.format(agent_id="reviewer-agent").replace(
            "glm-5.2:cloud", "reviewer-model"),
        encoding="utf-8")
    (tmp_path / "tests" / "frozen").mkdir(parents=True)
    (tmp_path / "tests" / "frozen" / "t.py").write_text("def test(): assert 1\n", encoding="utf-8")
    content = textwrap.dedent(
        """
        id: ccdd
        stages:
          - id: decompose
            agent: spec-agent
            task: "author {input}"
            attest: reviewer-agent
            gate_retries: 1
            freeze: tests/frozen
        """
    ).strip()
    flow = load_flow(_write_flow(tmp_path, content))
    # reviewer always rejects → author re-runs, freeze never happens
    calls = _patch_run_by_agent(
        monkeypatch,
        {"reviewer-model": "test_x contradicts spec clause 96.\nATTEST: FAIL"},
    )
    monkeypatch.chdir(tmp_path)

    result = run_flow(flow, str(specs_dir), initial_input="SPEC.md")

    rec = result["results"][0]
    assert rec["gate"]["passed"] is False
    assert rec["frozen"] == []  # broken oracle not frozen
    assert "ATTESTATION FAILED" in rec["gate"]["output"]
    # author ran twice (initial + 1 retry), reviewer ran twice too
    assert calls["count"] == 4


def test_console_attest_reads_yes_no(monkeypatch):
    """The default console attestation maps y/yes → True, else False."""
    import carta.flow as flow_mod

    monkeypatch.setattr("builtins.input", lambda *_a: "y")
    assert flow_mod._console_attest("s", "spec.md", "tests/frozen", ["a.py"]) is True
    monkeypatch.setattr("builtins.input", lambda *_a: "n")
    assert flow_mod._console_attest("s", "spec.md", "tests/frozen", ["a.py"]) is False
    # EOF (no tty / piped) defaults to reject — never freeze unreviewed
    def _eof(*_a):
        raise EOFError
    monkeypatch.setattr("builtins.input", _eof)
    assert flow_mod._console_attest("s", "spec.md", "tests/frozen", []) is False


def test_attest_human_approve_freezes(tmp_path, monkeypatch):
    """attest: human + on_attest approving → oracle frozen, no reviewer LLM."""
    specs_dir = make_specs(tmp_path, ("spec-agent",))
    (tmp_path / "tests" / "frozen").mkdir(parents=True)
    (tmp_path / "tests" / "frozen" / "t.py").write_text("def test(): assert 1\n", encoding="utf-8")
    content = textwrap.dedent(
        """
        id: ccdd
        stages:
          - id: decompose
            agent: spec-agent
            task: "author {input}"
            attest: human
            freeze: tests/frozen
        """
    ).strip()
    flow = load_flow(_write_flow(tmp_path, content))
    _patch_run(monkeypatch, {"answer": "wrote tests", "steps": []})
    monkeypatch.chdir(tmp_path)

    seen = {}

    def approve(stage_id, spec, target, files):
        seen["stage"] = stage_id
        seen["files"] = files
        return True

    result = run_flow(flow, str(specs_dir), initial_input="SPEC.md", on_attest=approve)

    assert seen["stage"] == "decompose"
    assert any("t.py" in f for f in seen["files"])
    rec = result["results"][0]
    assert rec["gate"]["passed"] is True
    assert rec["frozen"]  # human approved → frozen


def test_attest_human_reject_blocks_freeze(tmp_path, monkeypatch):
    """attest: human + on_attest rejecting → not frozen, author retries."""
    specs_dir = make_specs(tmp_path, ("spec-agent",))
    (tmp_path / "tests" / "frozen").mkdir(parents=True)
    (tmp_path / "tests" / "frozen" / "t.py").write_text("def test(): assert 1\n", encoding="utf-8")
    content = textwrap.dedent(
        """
        id: ccdd
        stages:
          - id: decompose
            agent: spec-agent
            task: "author {input}"
            attest: human
            gate_retries: 1
            freeze: tests/frozen
        """
    ).strip()
    flow = load_flow(_write_flow(tmp_path, content))
    runs = _patch_run(monkeypatch, {"answer": "wrote tests", "steps": []})
    monkeypatch.chdir(tmp_path)

    calls = {"n": 0}

    def reject(stage_id, spec, target, files):
        calls["n"] += 1
        return False

    result = run_flow(flow, str(specs_dir), initial_input="SPEC.md", on_attest=reject)

    rec = result["results"][0]
    assert rec["gate"]["passed"] is False
    assert rec["frozen"] == []  # rejected → not frozen
    assert calls["n"] == 2  # asked on initial + 1 retry
    assert runs["count"] == 2  # author re-ran after rejection


def test_attest_inconclusive_treated_as_fail(tmp_path, monkeypatch):
    """A reviewer reply with no ATTEST verdict is treated as failure (safe default)."""
    specs_dir = make_specs(tmp_path, ("spec-agent", "reviewer-agent"))
    (specs_dir / "spec-agent.yaml").write_text(
        _VALID_SPEC_YAML.format(agent_id="spec-agent").replace(
            "glm-5.2:cloud", "author-model"),
        encoding="utf-8")
    (specs_dir / "reviewer-agent.yaml").write_text(
        _VALID_SPEC_YAML.format(agent_id="reviewer-agent").replace(
            "glm-5.2:cloud", "reviewer-model"),
        encoding="utf-8")
    (tmp_path / "tests" / "frozen").mkdir(parents=True)
    (tmp_path / "tests" / "frozen" / "t.py").write_text("def test(): assert 1\n", encoding="utf-8")
    content = textwrap.dedent(
        """
        id: ccdd
        stages:
          - id: decompose
            agent: spec-agent
            task: "author {input}"
            attest: reviewer-agent
            gate_retries: 0
            freeze: tests/frozen
        """
    ).strip()
    flow = load_flow(_write_flow(tmp_path, content))
    _patch_run_by_agent(monkeypatch, {"reviewer-model": "I am not sure about this."})
    monkeypatch.chdir(tmp_path)

    result = run_flow(flow, str(specs_dir), initial_input="SPEC.md")

    rec = result["results"][0]
    assert rec["gate"]["passed"] is False
    assert rec["frozen"] == []


# --- foreach (CCDD decomposition) --------------------------------------------


def test_load_flow_foreach_must_be_string(tmp_path):
    content = textwrap.dedent(
        """
        id: f
        stages:
          - id: a
            agent: coder-agent
            task: "impl {item[name]}"
            foreach: 123
        """
    ).strip()
    with pytest.raises(ValueError, match="'foreach' must be"):
        load_flow(_write_flow(tmp_path, content))


def test_foreach_runs_once_per_manifest_item(tmp_path, monkeypatch):
    """A foreach stage fans out one gated unit per JSON-manifest item."""
    specs_dir = make_specs(tmp_path, ("coder-agent",))
    manifest = tmp_path / "units.json"
    manifest.write_text(
        '[{"name": "a", "test": "t_a.py"}, {"name": "b", "test": "t_b.py"}]',
        encoding="utf-8",
    )
    content = textwrap.dedent(
        """
        id: ccdd
        stages:
          - id: implement
            agent: coder-agent
            foreach: units.json
            task: "implement {item[name]} tested by {item[test]}"
            gate: "pytest {item[test]} -q"
            gate_retries: 0
        """
    ).strip()
    flow = load_flow(_write_flow(tmp_path, content))

    seen_tasks = []
    seen_gates = []

    from carta import agent as agent_mod
    import carta.local as local_mod

    def fake_init(self, *a, **k):
        pass

    def fake_run(self, task, provider=None, max_steps=8):
        seen_tasks.append(task)
        return {"answer": "ok", "steps": []}

    def fake_gate(command, cwd=None, timeout=30):
        seen_gates.append(command)
        return {"ok": True, "stdout": "", "stderr": "", "returncode": 0}

    monkeypatch.setattr(agent_mod.CartaAgent, "__init__", fake_init)
    monkeypatch.setattr(agent_mod.CartaAgent, "run", fake_run)
    monkeypatch.setattr(local_mod, "local_run_command", fake_gate)
    monkeypatch.chdir(tmp_path)

    result = run_flow(flow, str(specs_dir), initial_input="spec")

    # one agent run + one gate per item, with per-item interpolation
    assert len(seen_tasks) == 2
    assert any("implement a tested by t_a.py" in t for t in seen_tasks)
    assert any("implement b tested by t_b.py" in t for t in seen_tasks)
    assert "pytest t_a.py -q" in seen_gates
    assert "pytest t_b.py -q" in seen_gates
    rec = result["results"][0]
    assert rec["gate"]["passed"] is True
    assert len(rec["units"]) == 2


def test_foreach_gate_fails_one_unit(tmp_path, monkeypatch):
    """If one unit's gate fails, the stage gate is not fully passed."""
    specs_dir = make_specs(tmp_path, ("coder-agent",))
    (tmp_path / "units.json").write_text(
        '[{"name": "a", "test": "t_a.py"}, {"name": "b", "test": "t_b.py"}]',
        encoding="utf-8",
    )
    content = textwrap.dedent(
        """
        id: ccdd
        stages:
          - id: implement
            agent: coder-agent
            foreach: units.json
            task: "impl {item[name]}"
            gate: "pytest {item[test]} -q"
            gate_retries: 0
        """
    ).strip()
    flow = load_flow(_write_flow(tmp_path, content))

    from carta import agent as agent_mod
    import carta.local as local_mod

    def fake_init(self, *a, **k):
        pass

    def fake_run(self, task, provider=None, max_steps=8):
        return {"answer": "ok", "steps": []}

    def fake_gate(command, cwd=None, timeout=30):
        # unit a passes, unit b fails
        code = 0 if "t_a.py" in command else 1
        return {"ok": code == 0, "stdout": "", "stderr": "boom", "returncode": code}

    monkeypatch.setattr(agent_mod.CartaAgent, "__init__", fake_init)
    monkeypatch.setattr(agent_mod.CartaAgent, "run", fake_run)
    monkeypatch.setattr(local_mod, "local_run_command", fake_gate)
    monkeypatch.chdir(tmp_path)

    result = run_flow(flow, str(specs_dir), initial_input="spec")

    rec = result["results"][0]
    assert rec["gate"]["passed"] is False
    passed = [u for u in rec["units"] if u["gate_passed"]]
    assert len(passed) == 1


def test_foreach_scalar_items(tmp_path, monkeypatch):
    """foreach over scalar items interpolates {item} directly."""
    specs_dir = make_specs(tmp_path, ("coder-agent",))
    (tmp_path / "units.json").write_text('["alpha", "beta", "gamma"]', encoding="utf-8")
    content = textwrap.dedent(
        """
        id: ccdd
        stages:
          - id: implement
            agent: coder-agent
            foreach: units.json
            task: "impl {item}"
        """
    ).strip()
    flow = load_flow(_write_flow(tmp_path, content))

    from carta import agent as agent_mod

    tasks = []

    def fake_init(self, *a, **k):
        pass

    def fake_run(self, task, provider=None, max_steps=8):
        tasks.append(task)
        return {"answer": "ok", "steps": []}

    monkeypatch.setattr(agent_mod.CartaAgent, "__init__", fake_init)
    monkeypatch.setattr(agent_mod.CartaAgent, "run", fake_run)
    monkeypatch.chdir(tmp_path)

    result = run_flow(flow, str(specs_dir), initial_input="x")

    assert tasks == ["impl alpha", "impl beta", "impl gamma"]
    assert len(result["results"][0]["units"]) == 3


def test_load_manifest_missing_raises(tmp_path, monkeypatch):
    """A foreach source that is neither a context key nor a file errors clearly."""
    from carta.flow import _load_manifest

    monkeypatch.chdir(tmp_path)
    with pytest.raises(FileNotFoundError, match="foreach source"):
        _load_manifest("nope.json", {})


def test_load_manifest_glob(tmp_path, monkeypatch):
    """glob: source returns the sorted matching file paths."""
    from carta.flow import _load_manifest

    frozen = tmp_path / "tests" / "frozen"
    frozen.mkdir(parents=True)
    (frozen / "test_b.py").write_text("", encoding="utf-8")
    (frozen / "test_a.py").write_text("", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    items = _load_manifest("glob:tests/frozen/test_*.py", {})
    assert len(items) == 2
    assert items[0].endswith("test_a.py")  # sorted
    assert items[1].endswith("test_b.py")


def test_load_manifest_glob_no_match_raises(tmp_path, monkeypatch):
    from carta.flow import _load_manifest

    monkeypatch.chdir(tmp_path)
    with pytest.raises(FileNotFoundError, match="matched no files"):
        _load_manifest("glob:tests/frozen/test_*.py", {})


def test_foreach_glob_runs_per_file(tmp_path, monkeypatch):
    """A foreach glob stage runs one gated unit per matching test file."""
    specs_dir = make_specs(tmp_path, ("coder-agent",))
    frozen = tmp_path / "tests" / "frozen"
    frozen.mkdir(parents=True)
    (frozen / "test_x.py").write_text("def test_x(): assert True\n", encoding="utf-8")
    (frozen / "test_y.py").write_text("def test_y(): assert True\n", encoding="utf-8")
    content = textwrap.dedent(
        """
        id: ccdd
        stages:
          - id: implement
            agent: coder-agent
            foreach: "glob:tests/frozen/test_*.py"
            task: "implement what {item} imports"
            gate: "pytest {item} -q"
            gate_retries: 0
        """
    ).strip()
    flow = load_flow(_write_flow(tmp_path, content))

    from carta import agent as agent_mod
    import carta.local as local_mod

    tasks, gates = [], []

    def fake_init(self, *a, **k):
        pass

    def fake_run(self, task, provider=None, max_steps=8):
        tasks.append(task)
        return {"answer": "ok", "steps": []}

    def fake_gate(command, cwd=None, timeout=30):
        gates.append(command)
        return {"ok": True, "stdout": "", "stderr": "", "returncode": 0}

    monkeypatch.setattr(agent_mod.CartaAgent, "__init__", fake_init)
    monkeypatch.setattr(agent_mod.CartaAgent, "run", fake_run)
    monkeypatch.setattr(local_mod, "local_run_command", fake_gate)
    monkeypatch.chdir(tmp_path)

    result = run_flow(flow, str(specs_dir), initial_input="spec")

    assert len(tasks) == 2
    assert any("test_x.py" in g for g in gates)
    assert any("test_y.py" in g for g in gates)
    assert result["results"][0]["gate"]["passed"] is True


# --- CLI & example -----------------------------------------------------------


def _run_cli(args: list[str]) -> subprocess.CompletedProcess:
    repo_root = str(Path(__file__).resolve().parents[1])
    env = dict(os.environ)
    env["PYTHONPATH"] = repo_root + os.pathsep + env.get("PYTHONPATH", "")
    return subprocess.run(
        [sys.executable, "-m", "carta", *args],
        capture_output=True,
        text=True,
        cwd=repo_root,
        env=env,
    )


def test_flow_cli_help():
    res = _run_cli(["flow", "--help"])
    assert res.returncode == 0, res.stdout + res.stderr
    assert "stages" in res.stdout


def test_example_flow_parseable():
    repo_root = Path(__file__).resolve().parents[1]
    path = repo_root / "examples" / "fix-and-test.flow.yaml"
    flow = load_flow(str(path))  # must not raise
    assert flow["id"] == "fix-and-test"
    assert len(flow["stages"]) == 3