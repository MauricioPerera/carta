"""``carta init`` — scaffold a Carta dev-team repository.

:func:`init_project` materializes a complete Carta project layout for a
default development team (spec → coder → tester → reviewer). Each role gets:

* an OKF agent doc under ``agents/`` so the :class:`carta.router.AgentRouter`
  can select it,
* a declarative ``agent-specs/<role>-agent.yaml`` consumed by
  :func:`carta.agent_yaml.load_agent_yaml`,
* a CCDD governance contract under ``.ccdd/<role>.yaml``.

It also drops a placeholder OKF tool catalog (``.okf/``) and the Postal
mailbox/audit/processed directories.
"""
from __future__ import annotations

import os

PRESETS: dict[str, dict[str, str]] = {
    "ollama-cloud": {
        "spec": "glm-5.2:cloud",
        "coder": "kimi-k2.7-code:cloud",
        "tester": "qwen3.5:cloud",
        "reviewer": "nemotron-3-ultra:cloud",
        "base_url": "https://ollama.com/v1",
    },
    "ollama-local": {
        "spec": "qwen2.5:7b",
        "coder": "qwen2.5-coder:7b",
        "tester": "qwen2.5:7b",
        "reviewer": "qwen2.5:7b",
        "base_url": "http://localhost:11434/v1",
    },
}

LOCAL_TOOL_DOCS: dict[str, str] = {
    "read_file": (
        "---\n"
        "type: tool\n"
        "title: Read File\n"
        "route: local\n"
        "tool: read_file\n"
        "description: Read the contents of a local file without an external CLI\n"
        "when_to_use: Use when you need to read a file from the local filesystem\n"
        "tags: [file, local, read]\n"
        "body:\n"
        "  args:\n"
        "    path: string\n"
        "---\n"
    ),
    "write_file": (
        "---\n"
        "type: tool\n"
        "title: Write File\n"
        "route: local\n"
        "tool: write_file\n"
        "description: Write content to a local file, creating directories as needed\n"
        "when_to_use: Use when you need to write or overwrite a file on the local filesystem\n"
        "tags: [file, local, write]\n"
        "body:\n"
        "  args:\n"
        "    path: string\n"
        "    content: string\n"
        "    mkdir: boolean (optional, default true)\n"
        "---\n"
    ),
    "append_file": (
        "---\n"
        "type: tool\n"
        "title: Append File\n"
        "route: local\n"
        "tool: append_file\n"
        "description: Append content to an existing file or create it if missing\n"
        "when_to_use: Use when you need to add lines to a log, report, or existing file\n"
        "tags: [file, local, append]\n"
        "body:\n"
        "  args:\n"
        "    path: string\n"
        "    content: string\n"
        "---\n"
    ),
    "list_dir": (
        "---\n"
        "type: tool\n"
        "title: List Directory\n"
        "route: local\n"
        "tool: list_dir\n"
        "description: List entries in a local directory\n"
        "when_to_use: Use when you need to explore the project structure or find files\n"
        "tags: [file, local, list, directory]\n"
        "body:\n"
        "  args:\n"
        "    path: string\n"
        "---\n"
    ),
    "run_command": (
        "---\n"
        "type: tool\n"
        "title: Run Command\n"
        "route: local\n"
        "tool: run_command\n"
        "description: Run a shell command in a subprocess and return stdout/stderr\n"
        "when_to_use: Use to run tests, linters, or build tools when no MCP is available\n"
        "tags: [command, local, shell, run]\n"
        "body:\n"
        "  args:\n"
        "    command: string\n"
        "    cwd: string (optional)\n"
        "    timeout: integer (optional, default 30)\n"
        "---\n"
    ),
}

AGENT_ROLES = {
    "spec": {
        "title": "Spec Agent",
        "model": "claude-sonnet-4-6",
        "description": "Decomposes project requirements into atomic tasks and sends them to the coder",
        "when_to_use": "When a new feature or requirement needs to be broken down into implementation tasks",
        "tags": ["spec", "requirements", "decomposition"],
        "body": (
            "# Spec Agent\n"
            "Analyzes requirements, features, and user stories. Decomposes them into atomic "
            "implementation tasks. Use when planning a new feature, defining scope, breaking down "
            "requirements, writing specifications, or decomposing a project into tasks.\n\n"
            "## Keywords\n"
            "plan, spec, requirement, feature, story, decompose, define, scope, design, architecture, "
            "breakdown, task, project, analyze, describe, what to build"
        ),
        "ccdd": {
            "can": ["read_requirements", "write_tasks", "send_to_agent"],
            "cannot": ["write_code", "run_tests", "push_to_main", "approve_pr"],
            "credentials_allowed": [],
        },
    },
    "coder": {
        "title": "Coder Agent",
        "model": "qwen2.5-coder:7b",
        "description": "Implements code based on spec tasks. Never sees the tester context.",
        "when_to_use": "When a task spec is ready and code needs to be written",
        "tags": ["code", "implementation", "development"],
        "body": (
            "# Coder Agent\n"
            "Writes, implements, and develops production code from a task specification. Use when "
            "you need to implement a feature, write a function, build a module, fix a bug, refactor "
            "code, or develop any software component.\n\n"
            "## Keywords\n"
            "implement, code, write, develop, build, create, fix, refactor, program, function, "
            "class, module, feature, component, checkout, payment, api, endpoint, service, library"
        ),
        "ccdd": {
            "can": ["write_code", "read_spec", "run_linter", "send_to_agent"],
            "cannot": ["write_tests", "push_to_main", "approve_pr", "modify_spec"],
            "credentials_allowed": ["DB_READ"],
        },
    },
    "tester": {
        "title": "Tester Agent",
        "model": "glm-5.2:cloud",
        "description": "Writes tests against the spec only. Never reads the coder reasoning.",
        "when_to_use": "When code has been written and independent tests are needed",
        "tags": ["tests", "qa", "verification"],
        "body": (
            "# Tester Agent\n"
            "Writes independent tests against the specification, without knowledge of implementation "
            "details. Use when you need to write tests, unit tests, integration tests, verify "
            "behavior, check correctness, or perform quality assurance on code.\n\n"
            "## Keywords\n"
            "test, tests, unit test, integration test, pytest, assert, verify, check, qa, quality, "
            "coverage, spec compliance, behavior, validation, test suite, test case, mock, fixture"
        ),
        "ccdd": {
            "can": ["write_tests", "read_spec", "read_code", "run_tests", "send_to_agent"],
            "cannot": ["modify_source", "push_to_main", "approve_pr"],
            "credentials_allowed": ["DB_READ"],
        },
    },
    "reviewer": {
        "title": "Reviewer Agent",
        "model": "glm-5.2:cloud",
        "description": "Reviews spec + code + test results. Final gate before merge.",
        "when_to_use": "When code and tests are ready and a final quality gate is needed",
        "tags": ["review", "gate", "approval"],
        "body": (
            "# Reviewer Agent\n"
            "Reviews the full deliverable: spec, code, and test results. Acts as the final quality "
            "gate before merge or deployment. Use when you need to review a pull request, approve or "
            "reject changes, evaluate code quality, audit an implementation, or make a merge decision.\n\n"
            "## Keywords\n"
            "review, approve, reject, merge, pull request, pr, gate, audit, evaluate, quality, "
            "lgtm, feedback, comment, check, final, decision, sign off, validate, accept"
        ),
        "ccdd": {
            "can": ["read_all", "approve", "reject", "comment"],
            "cannot": ["write_code", "write_tests", "push_to_main"],
            "credentials_allowed": [],
        },
    },
}


def _frontmatter(fields: dict) -> str:
    """Render a YAML frontmatter block from an ordered dict of fields."""
    lines = ["---"]
    for key, value in fields.items():
        lines.append(f"{key}: {_yaml_value(value)}")
    lines.append("---")
    return "\n".join(lines) + "\n"


def _yaml_value(value) -> str:
    """Serialize a scalar or list for an inline frontmatter line."""
    if isinstance(value, list):
        return "[" + ", ".join(str(v) for v in value) + "]"
    return str(value)


def _agent_md(role: str, spec: dict) -> str:
    """OKF agent doc (frontmatter + keyword body) for the router corpus."""
    fm = _frontmatter({
        "type": "agent",
        "title": spec["title"],
        "route": "carta",
        "agent_yaml": f"agent-specs/{role}-agent.yaml",
        "description": spec["description"],
        "when_to_use": spec["when_to_use"],
        "tags": spec["tags"],
    })
    return fm + "\n" + spec["body"] + "\n"


_ROLE_TIMEOUT = {
    "spec": 120,
    "coder": 300,
    "tester": 180,
    "reviewer": 180,
}

# Each agent step is one tool call (read_file / write_file / ...). Steps are
# sized by how much I/O a role's turn actually does, NOT as an arbitrary cap:
#   - spec authors the WHOLE oracle (one test file per unit, ~15-20 files) in the
#     decompose stage → needs the most steps, else it plateaus half-covered and
#     the coverage attestation can never converge to PASS (freeze gets skipped).
#   - reviewer ATTESTS by reading the spec + EVERY frozen test file → must have
#     enough steps to read them all, or its coverage judgment is partial.
#   - coder is atomic per unit (read one test file, write its module) → modest.
_ROLE_MAX_STEPS = {
    "spec": 40,
    "coder": 30,
    "tester": 20,
    "reviewer": 30,
}


def _agent_yaml(role: str, spec: dict, base_url: str, api_key: str = "") -> str:
    """Declarative agent.yaml for ``python -m carta run`` / the router."""
    api_key_line = f"  api_key: {api_key}\n" if api_key else ""
    timeout = _ROLE_TIMEOUT.get(role, 120)
    max_steps = _ROLE_MAX_STEPS.get(role, 8)
    return (
        f"id: {role}-agent\n"
        f"model:\n"
        f"  base_url: {base_url}\n"
        f"  name: {spec['model']}\n"
        f"{api_key_line}"
        f"  timeout: {timeout}\n"
        f"  max_steps: {max_steps}\n"
        f"knowledge:\n"
        f"  - .okf/\n"
        f"governance:\n"
        f"  contract: .ccdd/{role}.yaml\n"
        f"postal:\n"
        f"  audit_dir: .postal/audit/\n"
        f"  mailbox: .postal/inbox/{role}-agent/\n"
        f"triggers:\n"
        f"  - type: mailbox\n"
    )


def _ccdd_yaml(role: str, spec: dict, name: str) -> str:
    """CCDD governance contract listing can/cannot lists."""
    can = spec["ccdd"]["can"]
    cannot = spec["ccdd"]["cannot"]
    allowed = spec["ccdd"].get("credentials_allowed", [])
    lines = [
        f"agent: {role}-agent",
        f"project: {name}",
        "can:",
    ]
    lines += [f"  - {item}" for item in can]
    lines.append("cannot:")
    lines += [f"  - {item}" for item in cannot]
    if allowed:
        lines.append("credentials_allowed:")
        lines += [f"  - {c}" for c in allowed]
    else:
        lines.append("credentials_allowed: []")
    return "\n".join(lines) + "\n"


def _project_tools_md() -> str:
    """Placeholder OKF tool catalog for the project."""
    return _frontmatter({
        "type": "tool",
        "title": "Project Tools",
        "description": "Shared project tools catalog for the Carta dev team",
    })


def _example_flow_yaml(name: str, escalate_model: str = "") -> str:
    """Render a starter ``flows/example.flow.yaml`` for ``carta flow``.

    Pass the spec file path via ``--input``:
        carta flow flows/example.flow.yaml --input SPEC.md

    This is the CCDD *decomposed* shape, mirroring how the ccdd-complexity gate
    keeps a small model reliable: never ask it to implement a whole package at
    once. Instead:

      1. decompose — a strong model reads the spec and writes one frozen
         property-test FILE per atomic unit under tests/frozen/. The whole frozen
         dir is locked (the oracle).
      2. implement — fan out (foreach glob) one gated unit per frozen test file.
         Each unit is atomic: the coder implements the module(s) that ONE test
         file imports, iterated against its own gate, escalated once if needed.
         Units are derived from the test files on disk — no manifest to forget.
      3. integrate — assemble the package (the __init__ exports) and run the
         FULL suite as the composition gate.

    Atomic-and-gated is why the small model is reliable: a failure is localized
    to one small unit, not lost in a monolithic implement step.
    """
    escalate_line = (
        f"    gate_escalate_model: {escalate_model}\n" if escalate_model else ""
    )
    return (
        f"id: {name}-flow\n"
        "stages:\n"
        "  # 1. Strong model decomposes the spec into atomic units, writing ONE\n"
        "  #    frozen property-test file per unit. The frozen dir is then locked.\n"
        "  - id: decompose\n"
        "    agent: spec-agent\n"
        "    task: |\n"
        "      Use read_file with path='{input}' to read the project spec.\n"
        "      Break the spec into ATOMIC units (one cohesive function/class each).\n"
        "      For EACH unit, use write_file to write pytest property-tests to a\n"
        "      separate file tests/frozen/test_<unit>.py that any correct\n"
        "      implementation must pass. Each test file must import from the src/\n"
        "      module you expect for that unit (e.g. from <pkg>.<unit> import ...).\n"
        "      Do NOT implement the solution — write only the test files.\n"
        "    gate: python -m compileall -q tests/frozen\n"
        "    gate_retries: 2\n"
        "    # Oracle review before freezing, on TWO axes — fidelity (no assertion\n"
        "    # contradicts the spec) AND coverage (every spec-mandated metric/rule\n"
        "    # has a test). A wrong OR incomplete oracle is re-authored.\n"
        "    #   attest: reviewer-agent  -> automated adversarial model (default)\n"
        "    #   attest: human           -> CCDD R6: a person approves before freeze\n"
        "    #                              (deterministic; pauses unattended runs)\n"
        "    attest: reviewer-agent\n"
        "    freeze: tests/frozen\n"
        "\n"
        "  # 2. Fan out one atomic, gated implement per frozen test file. Units are\n"
        "  #    discovered from disk (glob) — robust, no manifest to forget.\n"
        "  - id: implement\n"
        "    agent: coder-agent\n"
        "    foreach: glob:tests/frozen/test_*.py\n"
        "    task: |\n"
        "      Use read_file to read the frozen test file {item}. Identify the src/\n"
        "      module(s) it imports, then use write_file to create them so that test\n"
        "      file passes. Do NOT modify anything under tests/frozen/.\n"
        "      Keep functions small (a complexity budget is enforced).\n"
        "    verify_frozen: true\n"
        "    gate: python -m pytest {item} -x -q\n"
        "    gate_retries: 2\n"
        + escalate_line
        + "    budget:\n"
        "      cyclomatic_max: 15\n"
        "      nesting_max: 4\n"
        "      params_max: 6\n"
        "      lines_max: 80\n"
        "    budget_paths: src\n"
        "\n"
        "  # 3. Composition gate: assemble the package and run the FULL suite.\n"
        "  - id: integrate\n"
        "    agent: coder-agent\n"
        "    task: |\n"
        "      Use list_dir on src/ to see the implemented modules. Create the\n"
        "      package __init__.py files exporting the public API the frozen tests\n"
        "      import, so the WHOLE suite imports and passes. Do NOT modify\n"
        "      tests/frozen/. Fix only composition/wiring issues.\n"
        "    verify_frozen: true\n"
        "    gate: python -m pytest tests/frozen/ -q\n"
        "    gate_retries: 2\n"
        + escalate_line
    )


def _conftest_py() -> str:
    """Render a root ``conftest.py`` that adds ``src/`` to ``sys.path``.

    The coder-agent writes implementation code under ``src/`` and tests under
    ``tests/``. pytest does not put ``src/`` on the import path automatically,
    so without this the pytest gate (``python -m pytest tests/``) fails on
    ModuleNotFoundError and the gate retries are wasted on a path issue rather
    than a real test failure.
    """
    return (
        '"""Pytest bootstrap: make src/ importable from tests/."""\n'
        "import os\n"
        "import sys\n"
        "\n"
        "_SRC = os.path.join(os.path.dirname(__file__), \"src\")\n"
        "if os.path.isdir(_SRC) and _SRC not in sys.path:\n"
        "    sys.path.insert(0, _SRC)\n"
    )


def _claude_md(name: str, roles: list[str]) -> str:
    """Render the project ``CLAUDE.md`` bootstrap doc.

    Lists each role as ``- **<role>-agent** (`agent-specs/<role>-agent.yaml`)``
    so a fresh Carta repo is self-describing for any Claude Code session that
    opens it.
    """
    agents_block = "\n".join(
        f"- **{role}-agent** (`agent-specs/{role}-agent.yaml`)" for role in roles
    )
    return (
        f"# CLAUDE.md — {name} usa Carta\n"
        "\n"
        "Este proyecto coordona agentes via Carta.\n"
        "Carta es un protocolo (no un framework): OKF para descubrir capabilities,\n"
        "CCDD para gobernanza por agente, Postal para mensajeria asincrona firmada.\n"
        "\n"
        "## Instalar Carta\n"
        "```\n"
        "pip install carta\n"
        "# o desde el repo fuente:\n"
        "pip install -e /ruta/a/carta\n"
        "```\n"
        "\n"
        "## Modelo requerido\n"
        "Los agentes necesitan un modelo con soporte de Tools (7B+ recomendado).\n"
        "\n"
        "**Ollama Cloud** (recomendado — no requiere GPU, todos los modelos soportan Tools):\n"
        "```\n"
        "# 1. Crear cuenta y API key en https://ollama.com/settings/keys\n"
        "export OLLAMA_API_KEY=sk-...\n"
        "# 2. Inicializar con el preset ollama-cloud:\n"
        "carta init . --preset ollama-cloud --api-key '$OLLAMA_API_KEY'\n"
        "# Asigna automaticamente: spec=glm-5.2, coder=kimi-k2.7-code,\n"
        "#   tester=qwen3.5, reviewer=nemotron-3-ultra\n"
        "```\n"
        "\n"
        "**Ollama local** (requiere GPU 7B+):\n"
        "```\n"
        "ollama pull qwen2.5-coder:7b\n"
        "carta init . --preset ollama-local\n"
        "```\n"
        "\n"
        "**Modelos cloud recomendados por rol** (https://ollama.com/search?c=cloud):\n"
        "- spec-agent: `glm-5.2:cloud` — long-horizon tasks, Tools+Thinking\n"
        "- coder-agent: `kimi-k2.7-code:cloud` — code-focused, 1M context\n"
        "- tester-agent: `qwen3.5:cloud` — flexible, Tools\n"
        "- reviewer-agent: `nemotron-3-ultra:cloud` — agent workflows, Tools+Thinking\n"
        "\n"
        "## Comandos\n"
        "```\n"
        "# Elegir el agente correcto para una tarea y correrlo:\n"
        'carta route agents/ --task "describe la tarea aqui"\n'
        "\n"
        "# Preview sin correr el LLM:\n"
        'carta route agents/ --task "describe la tarea" --dry-run\n'
        "\n"
        "# Correr un agente especifico:\n"
        'carta run agent-specs/<rol>-agent.yaml --task "describe la tarea"\n'
        "\n"
        "# Procesar mensajes pendientes en el mailbox:\n"
        "carta run agent-specs/<rol>-agent.yaml\n"
        "\n"
        "# Correr el pipeline completo pasando el archivo de spec como input:\n"
        "carta flow flows/example.flow.yaml --input SPEC.md\n"
        "# El stage 'plan' lee el spec con read_file y genera un plan.\n"
        "# El stage 'implement' escribe src/ y tests/, gateado por pytest.\n"
        "```\n"
        "\n"
        "## Estructura del proyecto\n"
        "```\n"
        "agents/skills/     -> catalogo OKF de agentes (el router los selecciona)\n"
        "agent-specs/       -> definicion de cada agente (model, knowledge, CCDD)\n"
        ".ccdd/             -> contratos de gobernanza por agente (can/cannot/credentials_allowed)\n"
        ".okf/tools/        -> tools locales (route: local) disponibles para todos los agentes\n"
        "flows/             -> pipelines declarativos (carta flow)\n"
        ".postal/inbox/     -> mensajes pendientes entre agentes (por agente: inbox/<id>/)\n"
        ".postal/audit/     -> recibos firmados de cada accion\n"
        ".postal/processed/ -> registro de mensajes ya procesados\n"
        "```\n"
        "\n"
        "## Agentes disponibles\n"
        f"{agents_block}\n"
        "\n"
        "## Reglas del enjambre\n"
        "- Cada agente corre un turno a la vez — no hay agentes vivos simultaneamente\n"
        "- Para delegar trabajo a otro agente: usa send_to_agent durante tu run()\n"
        "- Cada accion queda en .postal/audit/ como recibo ECDSA firmado\n"
        "- El CCDD de tu rol define que puedes y no puedes hacer\n"
        "- Los tools locales (read_file, write_file, list_dir, etc.) estan en .okf/tools/\n"
        "\n"
        "## Flujo tipico\n"
        "```\n"
        'carta route agents/ --task "nueva feature: ..."\n'
        "  -> spec-agent descompone\n"
        "  -> tester-agent escribe tests (sin ver el codigo)\n"
        "  -> coder-agent implementa (sin ver el razonamiento del tester)\n"
        "  -> reviewer-agent aprueba\n"
        "```\n"
    )


def init_project(
    project_dir: str,
    name: str = "my-project",
    base_url: str = "http://localhost:1234/v1",
    api_key: str = "",
    preset: str = "",
) -> list[str]:
    """Create a full Carta dev-team repo layout under ``project_dir``.

    ``preset`` is an optional key from :data:`PRESETS` (e.g.
    ``'ollama-cloud'``). When set, the preset overrides ``base_url`` and
    assigns the recommended model per role. ``api_key`` and an explicit
    ``base_url`` always take precedence over the preset.

    Returns the list of file paths created (directories are created as a
    side effect). Existing files are overwritten; the layout is idempotent.
    """
    preset_cfg = PRESETS.get(preset, {})
    # Preset provides base_url only when the caller didn't override it.
    resolved_base_url = base_url
    if preset_cfg and base_url == "http://localhost:1234/v1":
        resolved_base_url = preset_cfg.get("base_url", base_url)
    created: list[str] = []

    subdirs = [
        "agents/skills",
        "agent-specs",
        ".ccdd",
        ".okf",
        ".okf/tools",
        "flows",
        ".postal/inbox",
        ".postal/audit",
        ".postal/processed",
    ]
    for sub in subdirs:
        os.makedirs(os.path.join(project_dir, sub), exist_ok=True)

    for role, spec in AGENT_ROLES.items():
        agent_md = os.path.join(project_dir, "agents", "skills", f"{role}-agent.md")
        with open(agent_md, "w", encoding="utf-8") as f:
            f.write(_agent_md(role, spec))
        created.append(agent_md)

        # Preset overrides the model name per role when no explicit base_url
        # was provided by the caller (base_url == default).
        role_spec = dict(spec)
        if preset_cfg and role in preset_cfg:
            role_spec = dict(spec, model=preset_cfg[role])

        yaml_path = os.path.join(
            project_dir, "agent-specs", f"{role}-agent.yaml"
        )
        with open(yaml_path, "w", encoding="utf-8") as f:
            f.write(_agent_yaml(role, role_spec, resolved_base_url, api_key=api_key))
        created.append(yaml_path)

        ccdd_path = os.path.join(project_dir, ".ccdd", f"{role}.yaml")
        with open(ccdd_path, "w", encoding="utf-8") as f:
            f.write(_ccdd_yaml(role, spec, name))
        created.append(ccdd_path)

    tools_md = os.path.join(project_dir, ".okf", "project-tools.md")
    with open(tools_md, "w", encoding="utf-8") as f:
        f.write(_project_tools_md())
    created.append(tools_md)

    for tool_name, content in LOCAL_TOOL_DOCS.items():
        p = os.path.join(project_dir, ".okf", "tools", f"{tool_name}.md")
        with open(p, "w", encoding="utf-8") as f:
            f.write(content)
        created.append(p)

    # Escalation model = the strongest reasoning model in the roster (the spec
    # role). The coder role escalates to it (same role, so write_code stays
    # permitted) only when its gate fails. Skip when it equals the coder model.
    spec_model = (
        preset_cfg.get("spec")
        if preset_cfg
        else AGENT_ROLES["spec"]["model"]
    )
    coder_model = (
        preset_cfg.get("coder")
        if preset_cfg
        else AGENT_ROLES["coder"]["model"]
    )
    escalate_model = spec_model if spec_model and spec_model != coder_model else ""

    flow_path = os.path.join(project_dir, "flows", "example.flow.yaml")
    with open(flow_path, "w", encoding="utf-8") as f:
        f.write(_example_flow_yaml(name, escalate_model=escalate_model))
    created.append(flow_path)

    # conftest.py puts src/ on sys.path so the pytest gate can import the
    # code the coder-agent writes under src/. Without this the gate fails on
    # ModuleNotFoundError and burns all its retries on a path problem, not a
    # real test failure.
    conftest_path = os.path.join(project_dir, "conftest.py")
    with open(conftest_path, "w", encoding="utf-8") as f:
        f.write(_conftest_py())
    created.append(conftest_path)

    claude_md_path = os.path.join(project_dir, "CLAUDE.md")
    with open(claude_md_path, "w", encoding="utf-8") as f:
        f.write(_claude_md(name, list(AGENT_ROLES.keys())))
    created.append(claude_md_path)

    for keep in (
        ".postal/inbox/.gitkeep",
        ".postal/audit/.gitkeep",
        ".postal/processed/.gitkeep",
    ):
        keep_path = os.path.join(project_dir, keep)
        with open(keep_path, "w", encoding="utf-8") as f:
            f.write("")
        created.append(keep_path)

    return created