# Carta

[![CI](https://github.com/MauricioPerera/carta/actions/workflows/ci.yml/badge.svg)](https://github.com/MauricioPerera/carta/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)

**Expose an API to AI agents by publishing a git repo — not by running a server.**

Carta is a serverless pattern for giving agents *discovery*, *governance*, and
*audit* over external capabilities. Capability docs live as markdown in git, an
agent selects only what a task needs, and execution happens over plain HTTP
(`curl`) or an existing MCP server. No always-on process to expose your API.

> Status: experimental. Core (discovery/selection/execution) plus an agent
> dev-team pipeline that turns a spec into verified code (`carta flow`), under a
> CI-gated test suite. The runtime is LLM-agnostic (any OpenAI-compatible
> endpoint); during development it was driven by several orchestrators (Claude,
> Perplexity, Antigravity) over Ollama Cloud models. The spec is v0 and will change.

---

## Why

The Model Context Protocol couples two separate things into one always-on
server: **discovery** ("what tools exist and how do I call them") and
**execution** ("run this tool"). That coupling has two costs:

1. **Every provider must build and operate a server** to be agent-usable.
2. **Every tool definition is loaded into the prompt**, which saturates the
   context window of small models before they can reason. n8n's 25 tools alone
   are ~8k tokens.

Carta decouples them:

| Concern    | Carta                         | Needs a server? |
| ---------- | ----------------------------- | --------------- |
| Discovery  | markdown docs in a git repo   | No              |
| Selection  | local scorer, far fewer tokens on large catalogs | No   |
| Execution  | `curl` (REST) or MCP          | Only to run it  |
| Governance | CCDD contracts + allowlist    | No              |
| Audit      | signed messages over git      | No              |

Discovery and selection run offline against a git checkout. Only the final
execution call touches the network.

## How it works

```
1. tool_selector("create a workflow from a webhook")
   → reads okf/n8n/*.md, returns ~5 relevant docs (~1.5k tok, ~1/5 of the full catalog)

2. agent reads those docs → decides which tools to call

3. route: rest  → bash.exec("curl -X POST https://api.../workflows -d {...}")
   route: mcp   → call an existing MCP server (validate, search, suggest)

4. every call passes the CCDD allowlist and is recorded in an audit log;
   Postal can sign the result with the OKF + contract SHAs it acted on
```

A capability is one markdown file:

```yaml
---
type: REST Tool
title: create_post
route: rest
endpoint: POST https://jsonplaceholder.typicode.com/posts
description: Create a new post
when_to_use: when you need to publish new content
tags: [example, rest, write]
---
## Example
curl -X POST https://jsonplaceholder.typicode.com/posts -d '{"title":"hi","userId":1}'
```

## Building software with an agent team

Carta can also scaffold a **governed agent dev-team** and run a **verified
implementation pipeline**: give it a spec, get back code a small model wrote and a
deterministic gate proved correct.

```bash
carta config set api_key sk-your-key      # once per machine
carta config set preset ollama-cloud
carta init . --name my-project            # team + CCDD flow, in a dir with a spec
carta flow flows/example.flow.yaml --input SPEC.md
python -m pytest tests/frozen/ -q         # verify it yourself
```

The generated flow is the CCDD discipline made runnable — decompose the spec into
atomic units, freeze a property-test oracle per unit, and let a small model
iterate against a deterministic gate one piece at a time:

```
decompose  → strong model writes one frozen property-test file per unit
             (gate: tests parse · attest: independent spec review · freeze)
implement  → one atomic, gated implementation per unit (foreach)
             (per-unit pytest gate · complexity budget · escalation if it fails)
integrate  → assemble the package; gate on the FULL suite
```

This is **LLM-agnostic** (any OpenAI-compatible endpoint). During development the
orchestrator role was filled by several different agents (Claude, Perplexity,
Antigravity) while small models (`glm-5.2` + `kimi-k2.7-code`) did the coding.
See **[FLOW.md](FLOW.md)** for the
full pipeline, every stage field, and the two oracle-attestation modes
(automated reviewer vs. human R6 sign-off).

## Quickstart

Requirements: Python 3.10+ and `bash` on PATH (Git Bash or WSL on Windows).

```bash
git clone https://github.com/MauricioPerera/carta
cd carta
pip install -e .                 # core; add ".[mcp,audit]" for the MCP route + Postal

# Select context for a task (offline, no server)
python -m carta.selector "create a workflow from a webhook" --provider n8n
#  → ~5/30 docs · ~1.5k tokens · ~1/5 of the full-catalog baseline
#    (savings scale with catalog size; a tiny catalog may select everything)

# Run an agent end-to-end against a real REST API, no MCP server involved
python agents/agent_rest.py
#  → TASK COMPLETE - route: rest - no MCP server required

pytest    # full suite, CI-gated on 3.10/3.11/3.12
```

Carta is not on PyPI yet — install from a clone with `pip install -e .`.

## What's in the box

| Path             | Role                                                            |
| ---------------- | -------------------------------------------------------------- |
| `carta/`         | Reusable client: `CartaClient` (select + execute) and `CartaAgent` (full loop). |
| `okf/`           | Capability catalogs (markdown + YAML). Two providers included. |
| `carta/selector.py` | Task text → minimal relevant docs.                         |
| `carta/init.py`  | `carta init` — scaffold a governed agent dev-team + CCDD flow. |
| `carta/flow.py`  | `carta flow` — declarative pipeline: decompose → implement (foreach) → integrate, with gates, budget, escalation, freeze, attestation. |
| `carta/complexity.py` | Deterministic AST complexity budget (cyclomatic / nesting / params / lines). |
| `carta/config.py` | Global config at `~/.carta/config.yaml` (api_key / preset / base_url). |
| `carta/bash/`    | Sandboxed executor — a Python port of [just-bash](https://github.com/vercel-labs/just-bash), with allowlist + audit. |
| `carta/openapi_to_okf.py` | Generate a catalog from an OpenAPI spec.              |
| `postal/`        | ECDSA-signed, ECDH-encrypted messages over git.               |
| `.ccdd/`         | Per-agent governance contracts (permissions, budgets, allowlist). |
| `examples/`      | Worked examples, one per route (REST and MCP).                 |
| `benchmarks/`    | Reproducible measurements (e.g. selective vs full-catalog hashing). |

### CLI commands

| Command | Purpose |
| ------- | ------- |
| `carta init <dir>` | Scaffold an agent dev-team (`--preset`, `--api-key`, `--name`). |
| `carta flow <flow.yaml> --input <spec>` | Run the verified-implementation pipeline. |
| `carta run <agent.yaml> [--task …]` | Run one agent, or process its mailbox. |
| `carta route <catalog> --task …` | Pick the best agent for a task and run it. |
| `carta watch [dir]` | Poll inboxes and auto-run agents on new messages. |
| `carta config set\|get\|list\|unset` | Manage the global `~/.carta/config.yaml`. |
| `carta install-skill` | Install the `/carta-setup` Claude Code skill. |

See [ARCHITECTURE.md](ARCHITECTURE.md) for the full design.

## Examples

| Example | Route | Needs a server? |
| ------- | ----- | --------------- |
| [JSONPlaceholder — publish a post](examples/README.md#rest--jsonplaceholder) | `rest` | No |
| [n8n — build a workflow](examples/n8n/README.md) | `mcp` | Yes (n8n MCP) |

The n8n example shows a small local model building a real workflow from trimmed
context (~1.5k tokens vs ~7.9k), validated and created with no manual JSON import.

## Using Carta as a client

Adopting Carta as an agent builder is a library import, not a server to run:

```python
from carta import CartaAgent

agent = CartaAgent(["okf/n8n"], model="qwen2.5-7b",
                   base_url="http://localhost:1234/v1")
result = agent.run("Create a workflow that emails me when a webhook arrives")
```

`CartaAgent` selects the minimal context per task, drives an OpenAI-compatible
model with a block protocol (one action per turn; fenced blocks for long code,
never code inside JSON), and executes `rest` actions through the sandboxed
executor. `mcp` actions are handed to an optional `mcp_executor` bridge. For the
lower-level pieces use `CartaClient`. See [carta/README.md](carta/README.md).

## Where MCP is still the right tool

Carta is a **complement, not a replacement**. It covers the request/response,
stable-capability cases — roughly 80% of real MCP usage — without a running
server. MCP remains the better choice for:

- **Sub-second real-time** — git fetch latency is seconds, not milliseconds.
- **Sampling** — the server asking the model for inference mid-call needs a live
  server by definition.
- **Existing ecosystems** — if a maintained MCP server already exists, point your
  OKF docs at it with `route: mcp` instead of reimplementing it.

## Background

Carta builds on three open ideas and ties them together:

- **OKF** — the [Open Knowledge Format](https://cloud.google.com/blog/products/data-analytics/how-the-open-knowledge-format-can-improve-data-sharing)
  pattern: knowledge as portable markdown + frontmatter.
- **[CCDD](https://github.com/MauricioPerera/ccdd)** — Context Contract-Driven
  Development: governance for what an agent may do.
- **[Postal](https://github.com/MauricioPerera/postal)** — signed, append-only
  events over git.

## Adopting

Guides for both sides — publishing a catalog (API owners) and consuming one
(agent builders) — are in [ADOPTING.md](ADOPTING.md).

## Contributing

New provider catalogs are the most useful contribution and need no code — just
markdown. See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

[MIT](LICENSE) © Mauricio Perera
