# Carta

[![CI](https://github.com/MauricioPerera/carta/actions/workflows/ci.yml/badge.svg)](https://github.com/MauricioPerera/carta/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)

**Expose an API to AI agents by publishing a git repo — not by running a server.**

Carta is a serverless pattern for giving agents *discovery*, *governance*, and
*audit* over external capabilities. Capability docs live as markdown in git, an
agent selects only what a task needs, and execution happens over plain HTTP
(`curl`) or an existing MCP server. No always-on process to expose your API.

> Status: experimental. The core works end-to-end with 34 passing tests and two
> live demos (n8n and a public REST API), but the spec is v0 and will change.

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
| Selection  | local scorer, ~80% fewer tokens | No            |
| Execution  | `curl` (REST) or MCP          | Only to run it  |
| Governance | CCDD contracts + allowlist    | No              |
| Audit      | signed messages over git      | No              |

Discovery and selection run offline against a git checkout. Only the final
execution call touches the network.

## How it works

```
1. tool_selector("create a workflow from a webhook")
   → reads okf/n8n/*.md, returns the 5 relevant docs (1496 tok, 19% of baseline)

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

## Quickstart

Requirements: Python 3.10+ and `bash` on PATH (Git Bash or WSL on Windows).

```bash
git clone https://github.com/MauricioPerera/carta
cd carta
pip install -r requirements.txt

# Select context for a task (offline, no server)
python agents/tool_selector.py "create a workflow from a webhook" --provider n8n
#  → selected 5/30 docs · 1496 tokens · 18.9% of the 7902-token baseline

# Run an agent end-to-end against a real REST API, no MCP server involved
python agents/agent_rest.py
#  → TASK COMPLETE - route: rest - no MCP server required

pytest    # 34 passing
```

## What's in the box

| Path             | Role                                                            |
| ---------------- | -------------------------------------------------------------- |
| `carta/`         | Reusable client: `CartaClient` (select + execute) and `CartaAgent` (full loop). |
| `okf/`           | Capability catalogs (markdown + YAML). Two providers included. |
| `agents/tool_selector.py` | Task text → minimal relevant docs.                    |
| `bash/`          | Sandboxed executor — a Python port of [just-bash](https://github.com/vercel-labs/just-bash), with allowlist + audit. |
| `postal/`        | ECDSA-signed, ECDH-encrypted messages over git.               |
| `.ccdd/`         | Per-agent governance contracts (permissions, budgets, allowlist). |
| `examples/`      | Worked examples, one per route (REST and MCP).                 |

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
