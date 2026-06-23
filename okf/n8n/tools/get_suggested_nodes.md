---
type: 'MCP Tool'
title: 'get_suggested_nodes'
group: 'nodes'
description: 'Returns curated node recommendations for workflow technique categories.'
when_to_use: 'When you know the technique (chatbot, notification, scheduling, data_transformation, etc.) but not which concrete nodes to use.'
tags: ['n8n', 'mcp', 'nodes']
timestamp: '2026-06-22T00:00:00Z'
route: 'mcp'
---
# get_suggested_nodes
## Key parameters
- categories: string[] — one or more of: chatbot, notification, scheduling, data_transformation, data_persistence, data_extraction, document_processing, form_input, content_generation, triage, scraping_and_research
## Usage example
```
get_suggested_nodes(categories=['notification'])
```
## Don't use when
- You are looking for a concrete service by name → search_nodes
- You already have the nodeIds → get_node_types