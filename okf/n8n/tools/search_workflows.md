---
type: 'MCP Tool'
title: 'search_workflows'
group: 'workflow_management'
description: 'Searches workflows with optional filters; returns a preview of each.'
when_to_use: 'When you need to find a workflow by name or description, or locate its ID before updating/executing/archiving it.'
tags: ['n8n', 'mcp', 'workflow_management']
timestamp: '2026-06-22T00:00:00Z'
route: 'rest'
endpoint: 'GET https://api.n8n.co/api/v1/workflows'
---
# search_workflows
## Key parameters
- query: string (optional) — filter by name or description
- projectId: string (optional) — filter by project
- limit: number (optional) — maximum to return (max 200)
## Usage example
```
search_workflows(query='email webhook')
```
## Don't use when
- You already have the ID and want the details → get_workflow_details
- You are looking for nodes, not workflows → search_nodes