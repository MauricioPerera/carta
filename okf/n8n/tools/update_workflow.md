---
type: 'MCP Tool'
title: 'update_workflow'
group: 'workflow_management'
description: 'Updates an existing workflow in n8n from code validated with the SDK.'
when_to_use: 'When the workflow already exists (you have its ID) and you want to replace its definition with new validated code.'
tags: ['n8n', 'mcp', 'workflow_management']
timestamp: '2026-06-22T00:00:00Z'
route: 'rest'
endpoint: 'PUT https://api.n8n.co/api/v1/workflows/{id}'
---
# update_workflow
## Key parameters
- workflowId: string — ID of the workflow to update (required)
- code: string — new code validated with validate_workflow
- name: string (optional) — new name
- description: string (optional) — new description
## Usage example
```
update_workflow(workflowId='abc123', code=<validated_ts>)
```
## Don't use when
- You don't have the workflowId → look it up with search_workflows
- The workflow does not exist yet → create_workflow_from_code