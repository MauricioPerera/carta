---
type: 'MCP Tool'
title: 'validate_workflow'
group: 'validation'
description: 'Validates n8n Workflow SDK code: parses it into a workflow and reports errors.'
when_to_use: 'ALWAYS before create_workflow_from_code or update_workflow. Iterate until it returns valid.'
tags: ['n8n', 'mcp', 'validation']
timestamp: '2026-06-22T00:00:00Z'
route: 'mcp'
---
# validate_workflow
## Key parameters
- code: string — full TypeScript/JavaScript code with the workflow SDK export (required)
## Usage example
```
validate_workflow(code=<ts_with_export>)
# → valid: returns the workflow JSON; invalid: returns errors to fix
```
## Don't use when
- You want to save the already-validated workflow → create_workflow_from_code
- You need node parameters before writing the code → get_node_types
- You don't yet know the SDK syntax → get_sdk_reference