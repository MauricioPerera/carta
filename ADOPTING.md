# Adopting Carta

Two audiences adopt Carta from opposite ends. If you own an API, you *publish* a
catalog. If you build agents, you *consume* one. Neither side runs new
infrastructure for the common case.

---

## If you own an API (provider)

Goal: make your API usable by agents without building and operating an MCP
server. You publish a git repo of capability docs; agents read it offline.

### 1. Publish an OKF catalog

A directory of markdown files, one per capability, plus skills that group them:

```
okf/
├── index.md          # what the API is, base_url
├── tools/            # one .md per endpoint/tool
└── skills/           # ordered sequences (e.g. "create-invoice")
```

Each tool doc is plain frontmatter + a usage example:

```yaml
---
type: REST Tool
title: create_charge
route: rest
endpoint: POST https://api.example.com/v1/charges
description: Create a charge
when_to_use: when you need to capture a payment
tags: [billing, write]
---
## Example
curl -X POST https://api.example.com/v1/charges -d '{"amount":1000,"currency":"usd"}'
```

You already have this information in your OpenAPI/MCP schema — **generate the
catalog from it**; it isn't manual work.

### 2. Mark each tool's `route`

Only you know which capabilities are plain HTTP and which need server-side
intelligence:

- `route: rest` + `endpoint:` — anything an agent can call with `curl`. No server.
- `route: mcp` — capabilities with no REST equivalent (schema validation,
  semantic search, sampling). These still need your MCP server.

Marking CRUD as `rest` makes the bulk of your API usable with zero server.

### 3. Keep it in sync (the one real commitment)

Add a CI step: when your tools change, regenerate the catalog and `git push`. The
catalog's content hash changes, so consumers can detect drift — the thing plain
MCP can't give you: a *versioned* "how to use it".

### What you gain / don't lose

- Any agent (down to a small local model) can use your API without saturating its
  context or running an MCP client.
- Your "how to use it" becomes versioned and auditable.
- You keep your MCP server for `validate`/`search`/sampling and real-time — Carta
  is a complement, not a replacement.

---

## If you build agents (consumer)

Goal: drive an API from an agent without an MCP client per provider and without
loading every tool definition into the prompt. This is a library import.

### 1. Get the catalogs

```bash
git clone https://github.com/example/carta-catalog okf/example
```

Discovery is now local and offline.

### 2. Use the client

The whole loop is packaged. Minimal case:

```python
from carta import CartaAgent

agent = CartaAgent(["okf/example"], model="qwen2.5-7b",
                   base_url="http://localhost:1234/v1")
agent.run("Create a charge for $10")
```

`CartaAgent` selects the minimal context per task, drives an OpenAI-compatible
model with a block protocol (one action per turn; fenced blocks for long code,
never code inside JSON), executes `rest` actions through the sandboxed `bash`
executor, and hands `mcp` actions to an `mcp_executor`.

For the lower-level pieces, use `CartaClient` (select + execute, no model) and
write your own loop.

### 3. MCP-route providers (optional)

If a catalog has `route: mcp` tools, install the optional dependency and pass a
bridge:

```bash
pip install -e ".[mcp]"     # or: pip install -r requirements-mcp.txt
```
```python
from carta import CartaAgent, stdio_mcp_executor

mcp = stdio_mcp_executor("npx", ["-y", "@example/mcp-server"])
agent = CartaAgent(["okf/example"], model="...", mcp_executor=mcp)
```

### 4. Optional governance and audit

- **CCDD** — a contract that allowlists which commands/URLs the agent may touch.
- **Postal** — signed records proving which catalog version the agent acted on.

Both are opt-in; you don't need them to get started.

### What you need, in one line

Clone the catalogs, `import carta`, call `CartaAgent.run`. REST providers need no
server; `mcp` providers need their server reachable.

---

## Honest limits

- Carta covers the request/response, stable-capability cases — roughly 80% of MCP
  usage. For **sub-second real-time** and **sampling** (the server calling the
  model mid-operation), MCP is still the right tool. See [ARCHITECTURE.md](ARCHITECTURE.md).
- The `rest` route is verified end-to-end against live APIs. The `mcp` bridge is
  verified against a minimal MCP server; point it at your provider's server to
  validate your specific case.
