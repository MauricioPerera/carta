# Building software with an agent team (`carta flow`)

Beyond discovery/execution, Carta can scaffold a **governed agent dev-team** and
run a **verified implementation pipeline**: hand it a spec, get back code that a
small model wrote and a deterministic gate proved correct.

This is the CCDD discipline made runnable: never ask a small model to implement a
whole package at once. Decompose the spec into atomic units, freeze a
property-test oracle per unit, and let the model iterate against a deterministic
gate — one small, verifiable piece at a time.

It is **LLM-agnostic**: the runtime talks to any OpenAI-compatible endpoint over
`urllib` (Ollama Cloud, LM Studio, …). It has been driven end-to-end by Claude,
Perplexity, and Antigravity as the *orchestrator*, delegating the actual coding
to small models (e.g. `glm-5.2` + `kimi-k2.7-code` on Ollama Cloud).

---

## Quickstart

```bash
pip install carta

# One-time, machine-wide: store an API key + preset, reused by every project
carta config set api_key sk-your-ollama-key
carta config set preset ollama-cloud

# In a directory that contains only a spec (e.g. SPEC.md):
carta init . --name my-project          # scaffolds the team + CCDD flow
carta flow flows/example.flow.yaml --input SPEC.md
python -m pytest tests/frozen/ -q       # verify the result yourself
```

`carta config` persists to `~/.carta/config.yaml`. With a key stored, `carta init`
needs no flags — it writes agent-specs referencing `$OLLAMA_API_KEY` (the literal
key is never embedded in project files) and injects it at runtime.

Presets (`--preset` or `carta config set preset`):

| Preset         | spec / coder / tester / reviewer                                | endpoint               |
| -------------- | --------------------------------------------------------------- | ---------------------- |
| `ollama-cloud` | `glm-5.2` / `kimi-k2.7-code` / `qwen3.5` / `nemotron-3-ultra` (`:cloud`) | `https://ollama.com/v1` |
| `ollama-local` | `qwen2.5` / `qwen2.5-coder:7b` / `qwen2.5` / `qwen2.5`          | `http://localhost:11434/v1` |

---

## What `carta init` scaffolds

A self-describing repo (`CLAUDE.md` documents it for any agent that opens it):

```
agents/skills/     OKF catalog of the agents (the router selects among them)
agent-specs/       per-agent config: model, knowledge, timeout, max_steps, CCDD
.ccdd/             governance contracts per agent (can / cannot / credentials)
.okf/tools/        local tools (route: local): read_file, write_file, list_dir, …
flows/             declarative pipelines (carta flow)
conftest.py        puts src/ on sys.path so the pytest gate can import the code
.postal/           signed audit receipts + inter-agent mailboxes
```

`max_steps` is sized by each role's I/O (one step = one tool call): the **spec**
agent authors the whole oracle (~40), the **reviewer** reads every test to attest
(~30), the **coder** is atomic per unit (~30).

---

## The CCDD pipeline

The generated `flows/example.flow.yaml` has three stages:

```yaml
stages:
  - id: decompose          # strong model authors the oracle
    agent: spec-agent
    task: "read {input}; write one frozen property-test file per atomic unit"
    gate: python -m compileall -q tests/frozen   # tests must parse
    attest: reviewer-agent                        # independent spec review (below)
    freeze: tests/frozen                          # lock the oracle once approved

  - id: implement          # one atomic, gated implementation per unit
    agent: coder-agent
    foreach: glob:tests/frozen/test_*.py          # fan out over the frozen tests
    task: "read {item}; implement the module(s) it imports under src/"
    verify_frozen: true                           # coder may not edit the oracle
    gate: python -m pytest {item} -x -q           # per-unit gate
    gate_retries: 2
    gate_escalate_model: glm-5.2:cloud            # escalate if the cheap model fails
    budget: {cyclomatic_max: 15, nesting_max: 4, params_max: 6, lines_max: 80}
    budget_paths: src

  - id: integrate          # composition gate over the full suite
    agent: coder-agent
    task: "create the package __init__ exports so the WHOLE suite imports"
    verify_frozen: true
    gate: python -m pytest tests/frozen/ -q
    gate_retries: 2
```

Why this shape is reliable where a single "implement everything" stage is not:
a failure is localized to one small unit, the gate is deterministic (zero LLM
tokens), and the model iterates against it — exactly how CCDD's
`run_ephemeral_agent` + `run_integration_gate` keep a small executor trustworthy.

---

## Stage fields

| Field                 | Meaning |
| --------------------- | ------- |
| `agent`               | agent-spec under `--specs-dir` to run this stage. |
| `task`                | prompt template; `{input}`, prior `output_key`s, and `{item[...]}` (foreach) interpolate. |
| `output_key`          | store this stage's answer in the context under this key. |
| `gate`                | shell command; exit 0 = pass. Deterministic, zero tokens. `{item}` interpolates under foreach. |
| `gate_retries`        | re-runs on gate failure, injecting the failure into the prompt (default 1). |
| `gate_escalate_model` | on exhausted retries, re-run the **same** role with a stronger model (keeps its CCDD write permission). |
| `gate_escalate`       | alternatively hand off to a different agent (custom rosters with a senior-coder role). |
| `budget`              | per-function complexity limits (`cyclomatic_max`, `nesting_max`, `params_max`, `lines_max`), pure-AST, deterministic. |
| `budget_paths`        | dir/file the budget applies to (default `src`). |
| `foreach`             | fan out one gated unit per item: `glob:<pattern>` (file paths), a context key holding a list, or a JSON-manifest path. |
| `freeze`              | after the gate passes, lock these files (sha256). Skipped if the gate failed — never freeze a broken oracle. |
| `verify_frozen`       | fail the gate if any frozen file changed (the implementer can't weaken the oracle). |
| `attest`              | review the oracle before freezing (see below). |

All gate checks run in order **frozen-integrity → shell gate → budget**; the
first failure wins and is fed into the retry.

---

## Oracle attestation (`attest`)

A deterministic gate proves the tests *run*; it cannot prove they are *right*. A
test that asserts the wrong value — contradicting the spec — would freeze and drag
the implementation into being wrong too. Attestation closes that gap by reviewing
the oracle on **two axes** before freezing:

- **Fidelity** — does any assertion contradict the spec?
- **Coverage** — does every spec-mandated metric/rule have a test?

A wrong *or* incomplete oracle is rejected and re-authored. Two modes:

| `attest:` value   | Behaviour |
| ----------------- | --------- |
| `<agent>` (e.g. `reviewer-agent`) | An **independent** model (not the author) reviews and answers `ATTEST: PASS` / `ATTEST: FAIL`. Automated, unattended. Acts as strong *pressure* toward full coverage; LLM-vs-LLM judgment does not always converge to a clean PASS. |
| `human`           | **CCDD R6**: the flow pauses, shows the spec + the to-be-frozen tests, and a person approves or rejects. Deterministic; pauses unattended runs. Use for a hard guarantee. |

For `attest: human` in code, pass `run_flow(..., on_attest=callback)` where
`callback(stage_id, spec, target, files) -> bool`; the CLI default prompts on
stdin (EOF → reject, so an unattended run never freezes unreviewed).

---

## Resilience

- **Streaming** — model calls use SSE; the timeout is per-chunk, so long
  completions never expire while tokens flow.
- **Network retries** — transient failures (read timeouts, dropped connections,
  5xx) are retried with backoff; 4xx (e.g. a bad API key) are not.
- **Native tool calls** — models that emit OpenAI `tool_calls` (code models like
  kimi) and models that emit the action as text (glm) are both supported.

---

## Bootstrapping a fresh agent

Install the `/carta-setup` skill so any Claude Code session can configure a
project hands-off:

```bash
carta install-skill            # copies the skill into ~/.claude/skills/
```

Or give any orchestrator this one instruction in a directory with only a spec:

> Install carta if missing (`pip install carta`). Check for a global API key with
> `carta config get api_key`; if `(not set)`, ask for it and `carta config set
> api_key <key>`. Run `carta init . --name <dir>`. Find the `.md` spec. Run
> `carta flow flows/example.flow.yaml --input <spec>`. Then `python -m pytest
> tests/ -q` and report.
