---
type: 'MCP Tool'
title: 'get_sdk_reference'
group: 'nodes'
description: 'Returns the n8n Workflow SDK documentation: patterns, expression syntax, functions, rules.'
when_to_use: 'FIRST step when building workflows: learn the SDK patterns and rules before writing code.'
tags: ['n8n', 'mcp', 'nodes']
timestamp: '2026-06-22T00:00:00Z'
route: 'mcp'
---
# get_sdk_reference
## Key parameters
- section: string (optional) — 'patterns' | 'expressions' | 'functions' | 'rules' | 'import' | 'guidelines' | 'design' | 'all' (default)
## Usage example
```
get_sdk_reference(section='guidelines')
get_sdk_reference(section='design')
```
## Don't use when
- You already know the SDK and only need a node's parameters → get_node_types
- You are discovering which nodes to use → search_nodes