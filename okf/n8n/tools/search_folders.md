---
type: 'MCP Tool'
title: 'search_folders'
group: 'organization'
description: 'Searches folders within a project; partial case-insensitive filtering by name.'
when_to_use: 'When you are going to create a workflow in a specific folder and need its folderId.'
tags: ['n8n', 'mcp', 'organization']
timestamp: '2026-06-22T00:00:00Z'
route: 'rest'
endpoint: 'GET https://api.n8n.co/api/v1/folders'
---
# search_folders
## Key parameters
- projectId: string — project to search in (required; look it up with search_projects)
- query: string (optional) — filter by name
- limit: number (optional) — maximum to return (max 100)
## Usage example
```
search_folders(projectId='p1', query='marketing')
# → folderId to pass to create_workflow_from_code(folderId=...)
```
## Don't use when
- You don't know the projectId → search_projects first
- You want to search workflows, not folders → search_workflows