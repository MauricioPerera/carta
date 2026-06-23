---
type: 'MCP Tool'
title: 'prepare_test_pin_data'
group: 'execution'
description: 'Generates JSON Schemas of the expected output for each node that needs pin data for test_workflow.'
when_to_use: 'Before calling test_workflow, to know what data shape to simulate in triggers/nodes with credentials/HTTP.'
tags: ['n8n', 'mcp', 'execution']
timestamp: '2026-06-22T00:00:00Z'
route: 'rest'
endpoint: 'POST https://api.n8n.co/api/v1/workflows/{id}/pin-data'
---
# prepare_test_pin_data
## Key parameters
- workflowId: string — ID of the workflow to test (required)
## Usage example
```
prepare_test_pin_data(workflowId='abc123')
# → returns schemas; you generate realistic data and pass it to test_workflow
```
## Don't use when
- You already know the data shape and want to build pinData directly → test_workflow
- The workflow has no nodes that require pin data (Set/If/Code) → just test_workflow