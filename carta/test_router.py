"""Tests T24: AgentRouter — route a task to the right agent.yaml."""
import os

import yaml

from carta.router import AgentRouter


def _write_md(path, fm: dict, body: str = "") -> None:
    """Write a .md doc with YAML frontmatter + body to ``path``."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fm_text = yaml.safe_dump(fm, sort_keys=False, default_flow_style=False).strip()
    path.write_text(f"---\n{fm_text}\n---\n{body}\n", encoding="utf-8")


def _write_agent_yaml(path, agent_id: str) -> None:
    """Write a minimal valid agent.yaml (no real catalogs)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"id: {agent_id}\n"
        "model:\n"
        "  base_url: http://localhost:1234/v1\n"
        "  name: glm-5.2:cloud\n",
        encoding="utf-8",
    )


def _build_three_agents(tmp_path) -> dict:
    """Create a catalog with legal/calendar/finance agent docs + agent.yaml files.

    Returns a mapping ``name -> absolute agent.yaml path``.
    """
    skills = tmp_path / "skills"
    paths = {}
    specs = {
        "legal-agent": {
            "title": "Legal Agent",
            "description": "Review and analyze contracts and legal documents",
            "when_to_use": "Use when reviewing contracts, agreements, or legal clauses",
            "tags": ["legal", "contract", "law"],
            "body": "This agent reviews contracts, agreements and legal documents. "
                    "Use it for any legal task involving a contract.",
            "subdir": "legal",
        },
        "calendar-agent": {
            "title": "Calendar Agent",
            "description": "Schedule meetings and manage calendar events",
            "when_to_use": "Use to schedule a meeting or manage calendar events",
            "tags": ["calendar", "meeting", "schedule"],
            "body": "This agent schedules meetings and manages calendar events. "
                    "Use it for any calendar or meeting task.",
            "subdir": "calendar",
        },
        "finance-agent": {
            "title": "Finance Agent",
            "description": "Manage budgets, expenses, and invoices",
            "when_to_use": "Use for budgets, expenses, invoices, and finance tasks",
            "tags": ["finance", "budget", "invoice"],
            "body": "This agent manages budgets, expenses, and invoices. "
                    "Use it for any finance task.",
            "subdir": "finance",
        },
    }
    for name, spec in specs.items():
        agent_yaml = tmp_path / spec["subdir"] / "agent.yaml"
        _write_agent_yaml(agent_yaml, name)
        paths[name] = str(agent_yaml)
        _write_md(
            skills / f"{name}.md",
            {
                "type": "agent",
                "title": spec["title"],
                "route": "carta",
                "agent_yaml": str(agent_yaml),
                "description": spec["description"],
                "when_to_use": spec["when_to_use"],
                "tags": spec["tags"],
            },
            body=spec["body"],
        )
    return paths


def test_route_selects_agent(tmp_path):
    paths = _build_three_agents(tmp_path)
    router = AgentRouter(str(tmp_path))
    selected = router.route("review this contract")
    assert selected == paths["legal-agent"], (
        f"expected legal-agent, got {selected}"
    )
    print("OK test_route_selects_agent:", os.path.basename(os.path.dirname(selected)))


def test_route_selects_calendar(tmp_path):
    paths = _build_three_agents(tmp_path)
    router = AgentRouter(str(tmp_path))
    selected = router.route("schedule a meeting")
    assert selected == paths["calendar-agent"], (
        f"expected calendar-agent, got {selected}"
    )
    print("OK test_route_selects_calendar:", os.path.basename(os.path.dirname(selected)))


def test_route_no_docs(tmp_path):
    # Empty catalog: no skills/ dir at all.
    router = AgentRouter(str(tmp_path))
    try:
        router.route("anything")
    except ValueError as exc:
        assert "no agent docs matched" in str(exc), f"unexpected msg: {exc}"
        print("OK test_route_no_docs:", exc)
        return
    raise AssertionError("expected ValueError for empty catalog")


def test_route_missing_agent_yaml_field(tmp_path):
    # A doc that matches the task but has no agent_yaml in frontmatter.
    skills = tmp_path / "skills"
    _write_md(
        skills / "helper-agent.md",
        {
            "type": "agent",
            "title": "Helper Agent",
            "route": "carta",
            "description": "Review and analyze contracts",
            "when_to_use": "Use when reviewing contracts",
            "tags": ["legal", "contract"],
        },
        body="Reviews contracts and legal documents.",
    )
    router = AgentRouter(str(tmp_path))
    try:
        router.route("review this contract")
    except ValueError as exc:
        assert "agent_yaml" in str(exc), f"unexpected msg: {exc}"
        print("OK test_route_missing_agent_yaml_field:", exc)
        return
    raise AssertionError("expected ValueError for missing agent_yaml field")


def test_run_dry_run(tmp_path):
    paths = _build_three_agents(tmp_path)
    router = AgentRouter(str(tmp_path))
    result = router.run("review this contract", dry_run=True)
    assert result["routed_to"] == paths["legal-agent"], result
    assert result["agent_id"] == "legal-agent", result
    assert result["task"] == "review this contract", result
    # No LLM-side keys should leak into a dry-run result.
    assert set(result.keys()) == {"routed_to", "agent_id", "task"}, result
    print("OK test_run_dry_run:", result)


if __name__ == "__main__":
    import tempfile

    for fn in [
        test_route_selects_agent,
        test_route_selects_calendar,
        test_route_no_docs,
        test_route_missing_agent_yaml_field,
        test_run_dry_run,
    ]:
        with tempfile.TemporaryDirectory() as d:
            from pathlib import Path

            fn(Path(d))
    print("\nALL TESTS OK")