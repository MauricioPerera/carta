---
type: 'MCP Tool'
title: 'get_workflow_details'
group: 'workflow_management'
description: 'Gets detailed information about a specific workflow, including triggers.'
when_to_use: 'When you need to inspect the definition or triggers of a workflow before updating, executing, or archiving it.'
tags: ['n8n', 'mcp', 'workflow_management']
timestamp: '2026-06-22T00:00:00Z'
route: 'rest'
endpoint: 'GET https://api.n8n.co/api/v1/workflows/{id}'
---
# get_workflow_details
## Key parameters
- workflowId: string — ID of the workflow to inspect (required)
## Usage example
```
get_workflow_details(workflowId='abc123')
```
## Don't use when
- You don't know the ID → search_workflows
- You want to see the result of a run → get_execution