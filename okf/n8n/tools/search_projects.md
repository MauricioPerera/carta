---
type: 'MCP Tool'
title: 'search_projects'
group: 'organization'
description: 'Searches projects accessible by the user; partial case-insensitive filtering by name.'
when_to_use: 'First organization step: locate the projectId before creating workflows, tables, or searching folders.'
tags: ['n8n', 'mcp', 'organization']
timestamp: '2026-06-22T00:00:00Z'
route: 'rest'
endpoint: 'GET https://api.n8n.co/api/v1/projects'
---
# search_projects
## Key parameters
- query: string (optional) — filter by name (partial match, case-insensitive)
- type: 'personal' | 'team' (optional) — filter by project type
- limit: number (optional) — maximum to return (max 100)
## Usage example
```
search_projects(query='marketing', type='team')
# → projectId to pass to create_data_table, search_folders, create_workflow_from_code, etc.
```
## Don't use when
- You are looking for folders within a known project → search_folders
- You are looking for workflows by name → search_workflows