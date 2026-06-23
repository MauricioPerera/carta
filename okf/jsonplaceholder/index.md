---
type: 'API Index'
title: 'JSONPlaceholder API'
description: 'Public test REST API. Requires no auth and no MCP server.'
base_url: 'https://jsonplaceholder.typicode.com'
route: 'rest'
tags: ['rest', 'demo', 'no-mcp']
timestamp: '2026-06-22T00:00:00Z'
---

# JSONPlaceholder API

OKF catalog of a public test REST API (https://jsonplaceholder.typicode.com).
Unlike `okf/n8n/` (which documents an MCP server's tools), this provider
**does not mount any MCP server**: it exposes its API directly over HTTP and
the agent consumes it with `curl` via the Bash adapter.

## Why this catalog exists

It demonstrates the **REST route** of OKF: an API provider can enable agents
just by publishing an OKF repo (`.md` docs with `route: rest` + `endpoint:`
frontmatter), without writing or maintaining an MCP server. The orchestrator
reads the `route` field of each tool doc and decides whether to invoke the
tool over MCP or over HTTP.

## Tools (3)

- [get_posts](tools/get_posts.md) — GET /posts (list or filter by userId)
- [create_post](tools/create_post.md) — POST /posts (create a post)
- [get_user](tools/get_user.md) — GET /users/{id} (user data)

## Skills (1)

- [publish-content](skills/publish-content.md) — create a post and verify it exists

## How to choose

1. Read task → `get_posts` / `get_user`.
2. Write task → skill `publish-content` (sequence get_user → create_post → get_posts).
3. All tools are `route: rest` → they run with `curl`, no MCP.