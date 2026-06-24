"""CLI entry point: ``python -m carta run <agent.yaml> [--task TEXT]``.

Builds a :class:`carta.agent.CartaAgent` from a declarative ``agent.yaml``
and either runs a one-shot task (printing the result as JSON) or reports the
active trigger mode.
"""
from __future__ import annotations

import argparse
import json
import sys

# Reconfigure stdout to UTF-8 on Windows where the default codec (cp1252)
# can't represent characters that models produce (arrows, bullets, etc.).
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Inject global config into env before any subcommand runs so that
# $OLLAMA_API_KEY references in agent-specs resolve without a shell export.
from .config import inject_env as _inject_env
_inject_env()

from .agent import CartaAgent
from .agent_yaml import AgentConfig, load_agent_yaml, load_postal_identity


def _build_agent(config: AgentConfig) -> CartaAgent:
    model = config.model
    contract_path = None
    if isinstance(config.governance, dict):
        contract_path = config.governance.get("contract")

    audit_dir = ".postal/audit"
    if isinstance(config.postal, dict) and config.postal.get("audit_dir"):
        audit_dir = config.postal["audit_dir"]

    postal_identity = load_postal_identity(config)

    return CartaAgent(
        catalogs=config.knowledge,
        model=model["name"],
        base_url=model["base_url"],
        contract=contract_path,
        postal_identity=postal_identity,
        audit_dir=audit_dir,
        timeout=model.get("timeout", 60),
        api_key=model.get("api_key") or "",
    )


def _has_mailbox_trigger(config: AgentConfig) -> bool:
    return any(
        isinstance(t, dict) and t.get("type") == "mailbox"
        for t in config.triggers
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m carta",
        usage="python -m carta run <agent_yaml> [--task TEXT]",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    run_p = sub.add_parser("run", help="run an agent from an agent.yaml file")
    run_p.add_argument("agent_yaml", help="path to agent.yaml")
    run_p.add_argument("--task", default=None, help="one-shot task text")

    route_p = sub.add_parser(
        "route",
        help="route a task to the best agent.yaml in a catalog and run it",
    )
    route_p.add_argument(
        "agents_catalog",
        help="dir with OKF agent docs (.md files under skills/)",
    )
    route_p.add_argument("--task", required=True, help="task text to route")
    route_p.add_argument(
        "--dry-run",
        action="store_true",
        help="print the routing decision without running the agent",
    )

    init_p = sub.add_parser(
        "init",
        help="scaffold a Carta dev-team project in <dir>",
    )
    init_p.add_argument("dir", help="target project directory")
    init_p.add_argument("--name", default="my-project", help="project name")
    init_p.add_argument(
        "--base-url",
        default="http://localhost:1234/v1",
        help="OpenAI-compatible model base URL (e.g. https://ollama.com/v1 for Ollama Cloud)",
    )
    init_p.add_argument(
        "--api-key",
        default="",
        dest="api_key",
        help=(
            "API key for the model endpoint. "
            "Use $VAR to read from an environment variable at runtime "
            "(e.g. --api-key '$OLLAMA_API_KEY'). "
            "Required for Ollama Cloud (https://ollama.com/settings/keys)."
        ),
    )
    init_p.add_argument(
        "--preset",
        default="",
        choices=["ollama-cloud", "ollama-local", ""],
        help=(
            "Apply a model preset per role. "
            "'ollama-cloud': glm-5.2 / kimi-k2.7-code / qwen3.5 / nemotron-3-ultra "
            "at https://ollama.com/v1. "
            "'ollama-local': qwen2.5-coder:7b at http://localhost:11434/v1."
        ),
    )

    flow_p = sub.add_parser(
        "flow",
        help="Run a declarative agent pipeline",
        description=(
            "Run a declarative agent pipeline (flow.yaml). Each of the "
            "stages runs an agent and passes its output as context to the "
            "next stage."
        ),
    )
    flow_p.add_argument("flow_yaml", help="Path to flow.yaml")
    flow_p.add_argument(
        "--input",
        default="",
        dest="initial_input",
        help="Initial {input} variable for the first stage",
    )
    flow_p.add_argument(
        "--specs-dir",
        default="agent-specs",
        help="Directory containing agent-specs (default: agent-specs)",
    )
    flow_p.add_argument(
        "--base-url",
        default=None,
        help="Override model base URL",
    )

    sub.add_parser(
        "install-skill",
        help="install the /carta-setup Claude Code skill into ~/.claude/skills/",
    )

    config_p = sub.add_parser(
        "config",
        help="get or set global Carta settings (~/.carta/config.yaml)",
    )
    config_sub = config_p.add_subparsers(dest="config_cmd", required=True)

    cfg_set = config_sub.add_parser("set", help="set a config value")
    cfg_set.add_argument("key", choices=["api_key", "base_url", "preset"])
    cfg_set.add_argument("value", help="value to store")

    cfg_get = config_sub.add_parser("get", help="print a config value")
    cfg_get.add_argument("key", choices=["api_key", "base_url", "preset"])

    config_sub.add_parser("list", help="list all stored config values")
    config_sub.add_parser("unset", help="remove a config value").add_argument(
        "key", choices=["api_key", "base_url", "preset"]
    )

    watch_p = sub.add_parser(
        "watch",
        help="monitor inboxes and auto-run agents",
    )
    watch_p.add_argument(
        "project_dir",
        nargs="?",
        default=".",
        help="project root (default: current dir)",
    )
    watch_p.add_argument(
        "--base-url", default="http://localhost:1234/v1"
    )
    watch_p.add_argument(
        "--poll",
        type=float,
        default=2.0,
        dest="poll_interval",
        help="seconds between polls (default: 2)",
    )
    watch_p.add_argument("--max-rounds", type=int, default=50)
    watch_p.add_argument("--specs-dir", default="agent-specs")

    args = parser.parse_args(argv)

    if args.command == "install-skill":
        return _run_install_skill()

    if args.command == "config":
        return _run_config(args)

    if args.command == "route":
        return _run_route(args)

    if args.command == "init":
        return _run_init(args)

    if args.command == "watch":
        return _run_watch(args)

    if args.command == "flow":
        return _run_flow(args)

    if args.command != "run":
        parser.print_help()
        return 1

    config = load_agent_yaml(args.agent_yaml)

    if args.task:
        agent = _build_agent(config)
        result = agent.run(
            args.task, max_steps=config.model.get("max_steps", 8)
        )
        print(json.dumps(result, indent=2))
        return 0

    if _has_mailbox_trigger(config):
        return _run_mailbox(config)

    parser.print_help()
    return 1


def _run_install_skill() -> int:
    """Copy the /carta-setup skill into ``~/.claude/skills/carta-setup/``."""
    import shutil
    from pathlib import Path

    skill_src = Path(__file__).parent / "skills" / "carta-setup.md"
    if not skill_src.exists():
        print(f"Error: skill file not found at {skill_src}")
        return 1

    dest_dir = Path.home() / ".claude" / "skills" / "carta-setup"
    dest_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(skill_src, dest_dir / "carta-setup.md")
    print(f"Skill installed: {dest_dir / 'carta-setup.md'}")
    print("Use /carta-setup in any Claude Code session to configure a project.")
    return 0


def _run_config(args) -> int:
    """``carta config set|get|list|unset``."""
    from .config import KNOWN_KEYS, get, load, set_value
    from .config import unset as _unset

    if args.config_cmd == "set":
        set_value(args.key, args.value)
        print(f"carta config: {args.key} set")
        return 0

    if args.config_cmd == "get":
        val = get(args.key)
        if val:
            # Mask api_key in output for safety
            display = val[:4] + "***" if args.key == "api_key" and len(val) > 4 else val
            print(display)
        else:
            print(f"(not set)")
        return 0

    if args.config_cmd == "list":
        cfg = load()
        if not cfg:
            print("(no config stored — use: carta config set <key> <value>)")
            return 0
        for key, desc in KNOWN_KEYS.items():
            val = cfg.get(key)
            if val is not None:
                display = val[:4] + "***" if key == "api_key" and len(val) > 4 else val
                print(f"  {key}: {display}")
        return 0

    if args.config_cmd == "unset":
        removed = _unset(args.key)
        print(f"carta config: {args.key} {'removed' if removed else 'was not set'}")
        return 0

    return 1


def _run_init(args) -> int:
    """``carta init <dir> [--name NAME] [--base-url URL] [--preset PRESET]``.

    Scaffolds a Carta dev-team repo (agents, agent-specs, .ccdd, .okf, .postal)
    via :func:`carta.init.init_project` and reports the file count.

    When ``--api-key`` is not provided, falls back to the value stored in
    ``~/.carta/config.yaml`` (set once with ``carta config set api_key …``).
    If a global key is found, agent-specs are written with ``api_key: $OLLAMA_API_KEY``
    so the literal key is never embedded in the project files.
    """
    from .config import get as _cfg_get
    from .init import init_project

    api_key = args.api_key
    if not api_key:
        stored = _cfg_get("api_key")
        if stored:
            # Use an env-var reference so the key is not hardcoded in files.
            api_key = "$OLLAMA_API_KEY"

    # Also fall back preset and base_url from global config when not given.
    preset = args.preset or _cfg_get("preset")
    base_url = args.base_url
    if base_url == "http://localhost:1234/v1":
        stored_url = _cfg_get("base_url")
        if stored_url:
            base_url = stored_url

    created = init_project(
        args.dir,
        name=args.name,
        base_url=base_url,
        api_key=api_key,
        preset=preset,
    )
    print(
        f"Initialized Carta project in {args.dir} "
        f"({len(created)} files created)"
    )
    return 0


def _run_watch(args) -> int:
    """``carta watch [project_dir] [--poll N] [--max-rounds N]``.

    Monitors every inbox under ``<project_dir>/.postal`` and auto-runs the
    matching agent for each pending message via :func:`carta.watcher.watch`.
    """
    from .watcher import watch as _watch

    def _on_event(evt: str, data: dict) -> None:
        if evt == "processed":
            print(
                f"[carta watch] {data['agent_id']}: {data['task']!r} "
                f"({data['steps']} steps)"
            )
        elif evt == "skip":
            print(f"[carta watch] SKIP {data['agent_id']}: {data['reason']}")

    result = _watch(
        args.project_dir,
        specs_dir=args.specs_dir,
        base_url=args.base_url,
        poll_interval=args.poll_interval,
        max_rounds=args.max_rounds,
        on_event=_on_event,
    )
    print(
        f"carta watch done: {result['rounds']} rounds, "
        f"{len(result['processed'])} processed, "
        f"stopped={result['stopped_reason']}"
    )
    return 0


def _run_flow(args) -> int:
    """``carta flow <flow.yaml> [--input TEXT] [--specs-dir DIR] [--base-url URL]``.

    Runs a declarative agent pipeline via :func:`carta.flow.run_flow`,
    printing per-stage progress and the final answer.
    """
    from .flow import load_flow, run_flow

    flow = load_flow(args.flow_yaml)
    print(
        f"[carta flow] Starting pipeline: {flow['id']} "
        f"({len(flow['stages'])} stages)"
    )

    def _on_stage(sid: str, status: str, data: dict) -> None:
        if status == "start":
            print(f"[carta flow] -> {sid}: {data['task']!r}")
        elif status == "done":
            print(
                f"[carta flow] OK {sid}: {data['answer']!r} "
                f"({data['steps']} steps)"
            )
        elif status == "gate_pass":
            unit = f" [{data['item']}]" if data.get("item") else ""
            print(f"[carta flow]   gate PASS {sid}{unit} (attempt {data['attempt']})")
        elif status == "gate_fail":
            snippet = data["output"][:120].replace("\n", " ")
            unit = f" [{data['item']}]" if data.get("item") else ""
            print(
                f"[carta flow]   gate FAIL {sid}{unit} "
                f"(attempt {data['attempt']}): {snippet}"
            )
        elif status == "freeze":
            print(
                f"[carta flow]   froze {data['files']} file(s) under "
                f"{data['target']} {sid} (oracle locked)"
            )
        elif status == "freeze_skipped":
            print(
                f"[carta flow]   freeze SKIPPED {sid} "
                f"({data['target']}): {data['reason']}"
            )
        elif status == "escalate":
            print(
                f"[carta flow]   ESCALATING {sid} to stronger agent "
                f"'{data['agent']}' (cheap model exhausted retries)"
            )
        elif status == "foreach":
            print(
                f"[carta flow] -> {sid}: fanning out {data['count']} unit(s) "
                f"from {data['source']} (CCDD decomposition)"
            )
        elif status == "attest":
            print(
                f"[carta flow]   attesting {sid} oracle with '{data['agent']}' "
                f"({data['target']}) — adversarial spec review"
            )
        elif status == "attest_pass":
            print(f"[carta flow]   attest PASS {sid} (oracle faithful to spec)")
        elif status == "attest_fail":
            snippet = data["output"][:120].replace("\n", " ")
            print(f"[carta flow]   attest FAIL {sid}: {snippet}")

    result = run_flow(
        flow,
        args.specs_dir,
        initial_input=args.initial_input,
        base_url=args.base_url,
        on_stage=_on_stage,
    )
    print(
        f"[carta flow] Done. {result['stages_run']} stages. "
        f"Final answer: {result['final_answer']!r}"
    )
    return 0


def _run_route(args) -> int:
    """Route a task to the best agent.yaml in a catalog and run it (or preview).

    ``carta route <agents_catalog> --task TEXT [--dry-run]`` builds an
    :class:`carta.router.AgentRouter`, runs it, and prints the result as JSON.
    """
    from .router import AgentRouter

    router = AgentRouter(args.agents_catalog)
    result = router.run(args.task, dry_run=args.dry_run)
    print(json.dumps(result, indent=2))
    return 0


def _run_mailbox(config: AgentConfig) -> int:
    """Process pending messages from a Postal-style mailbox directory."""
    from .mailbox import extract_task, list_unprocessed, mark_processed

    postal = config.postal if isinstance(config.postal, dict) else {}
    mailbox_dir = postal.get("mailbox", ".postal/inbox")
    processed_dir = postal.get("processed_dir", ".postal/processed")

    msgs = list_unprocessed(mailbox_dir, processed_dir)
    if not msgs:
        print("No pending messages.")
        return 0

    agent = _build_agent(config)
    max_steps = config.model.get("max_steps", 8)

    count = 0
    for msg in msgs:
        msg_id = msg.get("id") or _stem_from_filename(msg, mailbox_dir)
        task = extract_task(msg)
        if task is None:
            print(f"skip {msg_id}: no task field")
            mark_processed(msg_id, processed_dir, {"skipped": True})
            count += 1
            continue
        print(f"Processing {msg_id}: {task[:60]}")
        result = agent.run(task, max_steps=max_steps)
        mark_processed(msg_id, processed_dir, result)
        print(f"  -> {result['status']}")
        count += 1

    print(f"Processed {count} messages.")
    return 0


def _stem_from_filename(msg: dict, mailbox_dir: str) -> str:
    """Recover the file stem for a message lacking an ``id`` field.

    Scans ``mailbox_dir`` and returns the stem of the first ``.json`` file
    whose parsed content equals ``msg``. Falls back to ``"unknown"``.
    """
    import json
    import os

    if not os.path.isdir(mailbox_dir):
        return "unknown"
    for name in sorted(os.listdir(mailbox_dir)):
        if not name.endswith(".json"):
            continue
        try:
            with open(os.path.join(mailbox_dir, name), "r", encoding="utf-8") as f:
                if json.load(f) == msg:
                    return os.path.splitext(name)[0]
        except (OSError, ValueError):
            continue
    return "unknown"


if __name__ == "__main__":
    sys.exit(main())