---
type: 'MCP Tool'
title: 'add_data_table_column'
group: 'data_tables'
description: 'Adds a new column to an existing data table.'
when_to_use: 'When the table already exists and you need an additional field (you cannot do this when inserting rows if the column does not exist).'
tags: ['n8n', 'mcp', 'data_tables']
timestamp: '2026-06-22T00:00:00Z'
route: 'rest'
endpoint: 'POST https://api.n8n.co/api/v1/data-tables/{id}/columns'
---
# add_data_table_column
## Key parameters
- dataTableId: string — table ID (required; look it up with search_data_tables)
- projectId: string — table project (required)
- name: string — column name (same rules as in create_data_table)
- type: 'string' | 'number' | 'boolean' | 'date'
## Usage example
```
add_data_table_column(dataTableId='t1', projectId='p1', name='status', type='string')
```
## Don't use when
- You want to rename an existing column → rename_data_table_column
- You want to insert rows (the columns already exist) → add_data_table_rows