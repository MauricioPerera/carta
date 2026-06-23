---
type: 'MCP Tool'
title: 'rename_data_table'
group: 'data_tables'
description: 'Renames an existing data table.'
when_to_use: 'When the table name changed meaning and you want to update it without recreating the table.'
tags: ['n8n', 'mcp', 'data_tables']
timestamp: '2026-06-22T00:00:00Z'
route: 'rest'
endpoint: 'PATCH https://api.n8n.co/api/v1/data-tables/{id}'
---
# rename_data_table
## Key parameters
- dataTableId: string — table ID (required)
- projectId: string — table project (required)
- name: string — new name (must remain unique within the project)
## Usage example
```
rename_data_table(dataTableId='t1', projectId='p1', name='qualified_leads')
```
## Don't use when
- You want to rename a column, not the table → rename_data_table_column
- You want to create a new table with a different name → create_data_table