---
type: 'MCP Tool'
title: 'get_execution'
group: 'execution'
description: 'Gets details of an execution by execution ID and workflow; by default metadata only.'
when_to_use: 'When you want to know the status or the result (per-node outputs) of an execution launched with execute_workflow.'
tags: ['n8n', 'mcp', 'execution']
timestamp: '2026-06-22T00:00:00Z'
route: 'rest'
endpoint: 'GET https://api.n8n.co/api/v1/executions/{id}'
---
# get_execution
## Key parameters
- workflowId: string — workflow ID (required)
- executionId: string — execution ID (required)
- includeData: boolean — true to include per-node inputs/outputs; default false (metadata only)
- nodeNames: string[] (optional) — filters to specific nodes when includeData=true
- truncateData: number (optional) — limits items per node output
## Usage example
```
get_execution(workflowId='abc123', executionId='exec456', includeData=true)
```
## Don't use when
- You only want to know if it finished → includeData=false (lighter)
- You want to inspect the workflow, not a run → get_workflow_details