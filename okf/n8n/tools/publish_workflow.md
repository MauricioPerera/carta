---
type: 'MCP Tool'
title: 'publish_workflow'
group: 'workflow_management'
description: 'Publishes (activates) a workflow so it becomes available for production execution.'
when_to_use: 'When the workflow is tested and you want it to run in production (creates an active version of the draft).'
tags: ['n8n', 'mcp', 'workflow_management']
timestamp: '2026-06-22T00:00:00Z'
route: 'rest'
endpoint: 'POST https://api.n8n.co/api/v1/workflows/{id}/activate'
---
# publish_workflow
## Key parameters
- workflowId: string — ID of the workflow to publish (required)
- versionId: string (optional) — specific version to publish; default: current draft
## Usage example
```
publish_workflow(workflowId='abc123')
```
## Don't use when
- You only want to test without activating → test_workflow
- You want to deactivate a published one → unpublish_workflow