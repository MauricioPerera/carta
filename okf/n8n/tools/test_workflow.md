---
type: 'MCP Tool'
title: 'test_workflow'
group: 'execution'
description: 'Tests a workflow using pin data to bypass external services (triggers, credentials, HTTP are simulated).'
when_to_use: 'When you want to validate a workflow logic without touching real services (logical nodes like Set/If/Code run normally).'
tags: ['n8n', 'mcp', 'execution']
timestamp: '2026-06-22T00:00:00Z'
route: 'rest'
endpoint: 'POST https://api.n8n.co/api/v1/workflows/{id}/test'
---
# test_workflow
## Key parameters
- workflowId: string — ID of the workflow to test (required)
- pinData: object — per-node pin data; keys = node names, values = arrays of items wrapped in {"json": {...}}
- triggerNodeName: string (optional) — trigger node to start from
## Usage example
```
test_workflow(workflowId='abc123', pinData={'Gmail':[{'json':{'subject':'test'}}]})
```
## Don't use when
- You don't have pin data yet → prepare_test_pin_data first
- You want to run against real services → execute_workflow