---
type: 'MCP Tool'
title: 'add_data_table_rows'
group: 'data_tables'
description: 'Inserts rows into an existing table; each row is a column→value object.'
when_to_use: 'When the table and its columns already exist and you want to load data (max 1000 rows per call).'
tags: ['n8n', 'mcp', 'data_tables']
timestamp: '2026-06-22T00:00:00Z'
route: 'rest'
endpoint: 'POST https://api.n8n.co/api/v1/data-tables/{id}/rows'
---
# add_data_table_rows
## Key parameters
- dataTableId: string — table ID (required)
- projectId: string — table project (required)
- rows: object[] — array of {column: value}; values string | number | boolean | null; max 1000 per call
## Usage example
```
add_data_table_rows(dataTableId='t1', projectId='p1', rows=[{email:'a@b.com', score:5}, {email:'c@d.com', score:9}])
```
## Don't use when
- The target column does not exist yet → add_data_table_column first
- You don't know the dataTableId → search_data_tables