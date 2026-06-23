---
type: 'MCP Tool'
title: 'search_nodes'
group: 'nodes'
description: 'Search n8n nodes by service, trigger type, or utility; returns IDs and discriminators.'
when_to_use: 'First step to assemble a workflow: discover which nodes exist for the services/techniques you need.'
tags: ['n8n', 'mcp', 'nodes']
timestamp: '2026-06-22T00:00:00Z'
route: 'mcp'
---
# search_nodes
## Key parameters
- queries: string[] — service names (gmail, slack), trigger types (schedule trigger, webhook) or utilities (set, if, merge, code)
## Usage example
```
search_nodes(queries=['gmail', 'schedule trigger'])
# → returns nodeIds + discriminators (resource/operation/mode) for get_node_types
```
## Don't use when
- You want curated suggestions by technique → get_suggested_nodes
- You already have the nodeIds and need the exact parameters → get_node_types