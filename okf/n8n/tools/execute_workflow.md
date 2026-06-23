---
type: 'MCP Tool'
title: 'execute_workflow'
group: 'execution'
description: 'Executes a workflow by ID; returns the executionId immediately without waiting for it to finish.'
when_to_use: 'When you want to run a real workflow (manual or production) and get an ID to later inspect the result.'
tags: ['n8n', 'mcp', 'execution']
timestamp: '2026-06-22T00:00:00Z'
route: 'rest'
endpoint: 'POST https://api.n8n.co/api/v1/workflows/{id}/execute'
---
# execute_workflow
## Key parameters
- workflowId: string — ID of the workflow to execute (required)
- executionMode: 'manual' | 'production' — manual tests the current version; production runs the published one
- inputs: object (optional) — chatInput, formData, or webhookData depending on the trigger type
## Usage example
```
execute_workflow(workflowId='abc123', executionMode='manual', inputs={type:'chat', chatInput:'hi'})
```
## Don't use when
- You want to test with pin data without touching external services → test_workflow
- You need the execution result → get_execution with the executionId