---
type: 'OKF Index'
title: 'Carta Catalog Index'
description: 'Root index of the OKF catalog: knowledge docs and provider tool/skill catalogs available to agents.'
tags: ['catalog', 'index']
timestamp: '2026-06-22T00:00:00Z'
---

# OKF Catalog

This directory holds [Open Knowledge Format](https://cloud.google.com/blog/products/data-analytics/how-the-open-knowledge-format-can-improve-data-sharing)
documents — plain markdown with YAML frontmatter — that agents read for
discovery. There are two kinds of docs here, and Carta treats them the same way.

## Provider tool catalogs

Capabilities an agent can *execute*, grouped by provider. Each tool doc carries a
`route` (`rest` or `mcp`) and, for REST, an `endpoint`. Skills bundle tools into
ordered sequences.

- [n8n](n8n/index.md) — workflow automation. 25 tools across 5 skills; intelligence
  tools (`validate`, `search`, `suggest`) use `route: mcp`, CRUD uses `route: rest`.
- [jsonplaceholder](jsonplaceholder/index.md) — a public REST API with **no MCP
  server**. Every tool is `route: rest`; the provider only had to publish these docs.

## Knowledge docs

Domain knowledge an agent can *reference* — the original OKF use case. The sample
below is the analytics dataset used by the Postal context-reproducibility demo
(`agents/agent_a.py` → `agents/agent_b.py`).

### Tables
- [orders](tables/orders.md) — id, customer_id, total, created_at
- [customers](tables/customers.md) — id, name, email, country
- [products](tables/products.md) — id, name, price, category

### Metrics
- [revenue](metrics/revenue.md) — monthly sum of sales
- [user_count](metrics/user_count.md) — daily active users
