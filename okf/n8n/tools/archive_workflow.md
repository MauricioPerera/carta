---
type: 'MCP Tool'
title: 'archive_workflow'
group: 'workflow_management'
description: 'Archives a workflow by its ID (removes it from the active view without deleting it).'
when_to_use: 'When you want to retire a workflow from use without permanently deleting it.'
tags: ['n8n', 'mcp', 'workflow_management']
timestamp: '2026-06-22T00:00:00Z'
route: 'rest'
endpoint: 'DELETE https://api.n8n.co/api/v1/workflows/{id}'
---
# archive_workflow
## Key parameters
- workflowId: string — ID of the workflow to archive (required)
## Usage example
```
archive_workflow(workflowId='abc123')
```
## Don't use when
- You want to stop production execution but keep it editable → unpublish_workflow
- You want to see details before archiving → get_workflow_details