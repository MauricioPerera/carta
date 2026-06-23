---
type: 'MCP Tool'
title: 'unpublish_workflow'
group: 'workflow_management'
description: 'Unpublishes (deactivates) a workflow so it is no longer available in production.'
when_to_use: 'When you want to pause an active workflow without archiving or deleting it.'
tags: ['n8n', 'mcp', 'workflow_management']
timestamp: '2026-06-22T00:00:00Z'
route: 'rest'
endpoint: 'POST https://api.n8n.co/api/v1/workflows/{id}/deactivate'
---
# unpublish_workflow
## Key parameters
- workflowId: string — ID of the workflow to unpublish (required)
## Usage example
```
unpublish_workflow(workflowId='abc123')
```
## Don't use when
- You want to retire it entirely without deleting → archive_workflow
- You want it to run in production again → publish_workflow