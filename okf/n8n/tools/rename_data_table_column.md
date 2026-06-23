---
type: 'MCP Tool'
title: 'rename_data_table_column'
group: 'data_tables'
description: 'Renames a column of a data table.'
when_to_use: 'When a column exists and you want to change its name without losing the data it contains.'
tags: ['n8n', 'mcp', 'data_tables']
timestamp: '2026-06-22T00:00:00Z'
route: 'rest'
endpoint: 'PATCH https://api.n8n.co/api/v1/data-tables/{id}/columns/{colId}'
---
# rename_data_table_column
## Key parameters
- dataTableId: string — table ID (required)
- projectId: string — table project (required)
- columnId: string — ID of the column to rename (required; not the current name)
- name: string — new name (same pattern rules)
## Usage example
```
rename_data_table_column(dataTableId='t1', projectId='p1', columnId='col2', name='email_address')
```
## Don't use when
- You want to delete the column → delete_data_table_column
- You want to add a new column → add_data_table_column