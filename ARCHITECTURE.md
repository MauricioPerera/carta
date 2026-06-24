# Architecture

Carta separates the three things an agent needs to use an external capability,
and assigns each to the cheapest mechanism that can do the job:

| Concern        | Question it answers                  | Mechanism in Carta            | Needs a server? |
| -------------- | ------------------------------------ | ----------------------------- | --------------- |
| **Discovery**  | What can I do, and how?              | OKF docs in a git repo        | No              |
| **Selection**  | Which of those do I need *now*?      | `tool_selector` (local)       | No              |
| **Execution**  | Do it.                               | `bash` executor (REST) or MCP | Only to run it  |
| **Governance** | Am I allowed to?                     | CCDD contracts + allowlist    | No              |
| **Audit**      | What context did I act on?           | Postal (signed, over git)     | No              |

The insight: **MCP couples discovery and execution into one always-on server.**
Carta decouples them. Discovery and selection happen offline against a git
checkout; only the final execution call touches the network.

## Components

```
carta/                       # Installable package
├── selector.py        # Selection: task text -> minimal relevant docs
├── client.py          # CartaClient: select + route + execute
├── agent.py           # CartaAgent: full loop against an OpenAI-compatible model
├── init.py            # carta init: scaffold a governed agent dev-team
├── flow.py            # carta flow: decompose -> implement -> integrate pipeline
├── complexity.py      # Deterministic AST complexity budget
├── config.py          # Global config (~/.carta/config.yaml)
├── openapi_to_okf.py  # Generate a catalog from an OpenAPI spec
├── mcp_executor.py    # Bridge for route: mcp (optional `mcp` dependency)
└── bash/              # Execution: sandboxed shell (Python port of just-bash)
    ├── executor.py    #   Bash.exec() with allowlist + audit hooks
    ├── allowlist.py   #   reads CCDD execution policy
    ├── sandbox.py     #   timeout + output caps
    └── audit.py       #   append-only execution log

okf/                # Discovery: capabilities as markdown + YAML frontmatter
├── n8n/            #   provider with an MCP server (route: mcp | rest)
└── jsonplaceholder/#   provider with REST only, no server (route: rest)
postal/             # Audit/transport: ECDSA-signed, ECDH-encrypted messages (optional)
.ccdd/              # Governance: per-agent contracts (permissions, budgets)
```

## Discovery — OKF

Each capability is one markdown file with YAML frontmatter:

```yaml
---
type: REST Tool
title: create_post
route: rest                                  # rest | mcp
endpoint: POST https://api.example.com/posts
description: Create a new post
when_to_use: when you need to publish new content
tags: [example, rest, write]
---
## Parameters
- title: string
## Example
curl -X POST https://api.example.com/posts -d '{"title":"hi"}'
```

`route` tells the executor *how* to run it. A provider that has an MCP server
marks its intelligence tools (`validate`, `search`, `suggest`) as `route: mcp`
and leaves CRUD as `route: rest`. A provider with only a REST API marks
everything `route: rest` — and never has to run a server at all.

## Selection — tool_selector

Loading every tool definition into the prompt is what saturates small models.
`carta.selector` scores skill and tool docs against the task text and returns
only the relevant subset.

```
$ python -m carta.selector "create a workflow from a webhook" --provider n8n
selected ~5/30 docs · ~1.5k tokens · ~1/5 of the full-catalog baseline
# exact figures depend on the catalog; savings scale with its size
```

This is RAG for tool documentation, but the index is plain files in git —
no vector DB, no embedding server, works offline.

## Execution — bash (or MCP)

`bash.Bash.exec()` runs a command in a sandboxed shell. It is a Python port of
[just-bash](https://github.com/vercel-labs/just-bash): isolated env per call,
shared filesystem across calls, timeout and output caps.

- **`route: rest`** → the agent runs the `curl` from the OKF doc. No client
  library, no protocol.
- **`route: mcp`** → the agent calls an existing MCP server for capabilities
  that have no REST equivalent (schema validation, node search, sampling).

Both routes pass through the same allowlist and audit log.

## Governance — CCDD

A CCDD contract declares what an agent may do, including an execution policy the
allowlist enforces before any command runs:

```yaml
execution:
  allowed_commands: [curl, python, git]
  allowed_urls: [https://api.example.com]
  timeout: 30
```

A command outside the allowlist is refused and the refusal is recorded.

## Audit — Postal

Postal turns "what context did the agent act on?" into a verifiable fact. Each
message is ECDSA-signed and carries `okf_snapshot_sha` and `ccdd_contract_sha`,
so any party can later prove which exact version of the knowledge and contract
an agent used. Messages live in git — the transport survives the producer going
offline, and the history is immutable and reproducible.

The snapshot SHA comes in two grains: `postal.compute_dir_sha` hashes a whole
catalog (full audit, but hydrates every blob), while `carta.selector.selection_sha`
hashes only the docs a task selected — letting an edge consumer version exactly the
context it used over a sparse partial clone without pulling the rest (~84% fewer
bytes on the n8n catalog; see [benchmarks/](benchmarks/)).

## Staleness — runtime drift check

A checked-out OKF catalog is a snapshot. If the upstream OpenAPI spec changes
and nobody regenerates the catalog, an agent silently runs against obsolete
instructions — no warning. `carta.staleness.check_catalog` closes that gap: the
generator (`carta.openapi_to_okf`) stamps `source_spec` + `source_spec_sha` +
`generated_at` into `index.md` when it runs; the staleness check re-fetches the
spec, hashes its bytes, and compares against the recorded SHA. `CartaClient.
check_freshness(provider=..., fetcher=...)` resolves the catalog the same way
`select` does and runs the check over that dir.

This is **opt-in** and never runs automatically — the default offline behavior
is unchanged. Honest limits:

- It detects drift **catalog-vs-spec**, not **spec-vs-reality**. A `fresh`
  result means the catalog matches the spec, not that the spec matches the
  running service.
- It requires `source_spec` to be fetchable. Catalogs without provenance
  (hand-written ones like `okf/n8n`) return `unknown`.
- It costs one network call per check. Inject a `fetcher` to stay offline.

## Orchestration — carta flow

On top of discovery/execution, Carta scaffolds a governed agent dev-team
(`carta init`) and runs a verified-implementation pipeline (`carta flow`) that
turns a spec into code a small model wrote and a deterministic gate proved.

The pipeline is the CCDD discipline made runnable: never implement a whole
package in one shot. Decompose into atomic units, freeze a property-test oracle
per unit, and iterate each unit against a deterministic gate.

```
decompose  spec -> one frozen property-test file per atomic unit
           gate: tests parse  ·  attest: independent spec review  ·  freeze (lock)
implement  foreach frozen test -> implement its module(s)
           per-unit pytest gate  ·  complexity budget  ·  retries  ·  escalation
integrate  assemble package exports -> gate on the FULL suite
```

Layered verification, deterministic-first (zero LLM tokens) then probabilistic:

- **Shell gate** (`gate:`) — exit 0 to pass; retried, failure fed into the prompt.
- **Complexity budget** (`budget:`) — pure-AST limits; over-budget forces a refactor.
- **Freeze + verify_frozen** — once an oracle passes, lock it (sha256); the
  implementer cannot weaken it. A failed gate is never frozen (stays winnable).
- **Escalation** (`gate_escalate_model`) — spend a stronger model only when the
  deterministic gate proves the cheap one could not pass.
- **Attestation** (`attest:`) — a deterministic gate proves tests *run*; it cannot
  prove they are *right*. An independent reviewer (or a human, CCDD R6) checks the
  oracle for fidelity and coverage against the spec before freezing.

The runtime is LLM-agnostic (any OpenAI-compatible endpoint over `urllib`, with
streaming, network retries, and native `tool_calls` support) and orchestrator-
agnostic (during development the orchestrator role was filled by Claude,
Perplexity, and Antigravity). Full reference: [FLOW.md](FLOW.md).

## Where MCP is still the right tool

Carta covers discovery, selection, execution, governance and audit without a
running server — roughly the 80% of MCP use cases that are request/response over
stable capabilities. MCP remains the better choice for:

- **Sub-second real-time** — git fetch latency is seconds, not milliseconds.
- **Sampling** — the server asking the model for inference mid-operation requires
  a live server by definition.
- **Existing ecosystems** — if a maintained MCP server already exists, point your
  OKF docs at it (`route: mcp`) instead of reimplementing it.

Carta is a complement, not a replacement: it lowers the cost of exposing an API
to agents from "build and operate a server" to "publish a git repo."
