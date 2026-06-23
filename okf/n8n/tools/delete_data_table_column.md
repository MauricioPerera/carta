---
type: 'MCP Tool'
title: 'delete_data_table_column'
group: 'data_tables'
description: 'Deletes a column from a data table (permanently removes the column and all its data).'
when_to_use: 'When a column no longer makes sense and you want to remove it permanently.'
tags: ['n8n', 'mcp', 'data_tables']
timestamp: '2026-06-22T00:00:00Z'
route: 'rest'
endpoint: 'DELETE https://api.n8n.co/api/v1/data-tables/{id}/columns/{colId}'
---
# delete_data_table_column
## Key parameters
- dataTableId: string — table ID (required)
- projectId: string — table project (required)
- columnId: string — ID of the column to delete (required; not the name)
## Usage example
```
delete_data_table_column(dataTableId='t1', projectId='p1', columnId='col3')
```
## Don't use when
- You only want to change the name → rename_data_table_column
- You want to keep the data but remove the table from the flow → there is no archive for tables; simply stop using it