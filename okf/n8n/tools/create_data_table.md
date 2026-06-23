---
type: 'MCP Tool'
title: 'create_data_table'
group: 'data_tables'
description: 'Creates a new data table in a project, with the specified columns.'
when_to_use: 'When you need a new table to persist workflow data inside n8n.'
tags: ['n8n', 'mcp', 'data_tables']
timestamp: '2026-06-22T00:00:00Z'
route: 'rest'
endpoint: 'POST https://api.n8n.co/api/v1/data-tables'
---
# create_data_table
## Key parameters
- projectId: string — project where to create the table (required; look it up with search_projects)
- name: string — unique name within the project (required)
- columns: {name, type}[] — at least one; type ∈ string | number | boolean | date; name pattern ^[a-zA-Z][a-zA-Z0-9_]*$ (max 63)
## Usage example
```
create_data_table(projectId='p1', name='leads', columns=[{name:'email', type:'string'}, {name:'score', type:'number'}])
```
## Don't use when
- The table already exists and you want to add data → add_data_table_rows (with its dataTableId)
- You don't know the projectId → search_projects