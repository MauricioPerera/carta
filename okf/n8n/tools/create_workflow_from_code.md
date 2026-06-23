---
type: 'MCP Tool'
title: 'create_workflow_from_code'
group: 'workflow_management'
description: 'Creates an n8n workflow from TypeScript/JavaScript code validated with the n8n Workflow SDK.'
when_to_use: 'When you already validated the code with validate_workflow and want to persist the new workflow in n8n.'
tags: ['n8n', 'mcp', 'workflow_management']
timestamp: '2026-06-22T00:00:00Z'
route: 'rest'
endpoint: 'POST https://ardf.dev/api/v1/workflows'
---
# create_workflow_from_code
## Key parameters
- code: string — full workflow code with the SDK export (must pass validate_workflow first)
- name: string (optional) — workflow name; if omitted, uses the one from the code
- description: string (optional) — 1-2 sentences summarizing what it does
- projectId: string (optional) — target project; default: personal project
- folderId: string (optional) — target folder within the project
## Usage example
```
create_workflow_from_code(code=<validated_ts>, description='Sends an email when a webhook arrives')
```
## Don't use when
- The code hasn't passed validate_workflow yet → validate first
- The workflow already exists and you want to change it → update_workflow