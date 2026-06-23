---
type: 'MCP Tool'
title: 'search_data_tables'
group: 'data_tables'
description: 'Searches data tables accessible by the user; partial case-insensitive filtering by name.'
when_to_use: 'First step before operating an existing table: locate its dataTableId.'
tags: ['n8n', 'mcp', 'data_tables']
timestamp: '2026-06-22T00:00:00Z'
route: 'rest'
endpoint: 'GET https://api.n8n.co/api/v1/data-tables'
---
# search_data_tables
## Key parameters
- query: string (optional) — filter by name (partial match, case-insensitive)
- projectId: string (optional) — filter by project
- limit: number (optional) — maximum to return (max 100)
## Usage example
```
search_data_tables(query='lead')
# → returns dataTableId to pass to add_data_table_rows, rename_data_table, etc.
```
## Don't use when
- The table does not exist yet → create_data_table
- You are looking for projects or folders → search_projects / search_folders