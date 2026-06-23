---
type: 'MCP Tool'
title: 'get_node_types'
group: 'nodes'
description: 'Gets TypeScript type definitions for nodes: exact parameter names and structure.'
when_to_use: 'After search_nodes; before writing the workflow code. ESSENTIAL: guessing parameters produces invalid workflows.'
tags: ['n8n', 'mcp', 'nodes']
timestamp: '2026-06-22T00:00:00Z'
route: 'mcp'
---
# get_node_types
## Key parameters
- nodeIds: (string | object)[] — plain node IDs, or objects with discriminators (nodeId, resource, operation, mode, version) from search_nodes
## Usage example
```
get_node_types(nodeIds=[{nodeId:'n8n-nodes-base.gmail', operation:'send', resource:'message'}])
```
## Don't use when
- You don't yet know which nodes to use → search_nodes first
- You need SDK patterns, not node parameters → get_sdk_reference