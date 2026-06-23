---
type: 'Skill'
title: 'manage-data'
description: 'Operate n8n data tables: create, modify columns, insert rows, search.'
tools_needed: ['search_projects', 'search_data_tables', 'create_data_table', 'add_data_table_column', 'add_data_table_rows', 'rename_data_table', 'rename_data_table_column', 'delete_data_table_column']
tags: ['n8n', 'skill']
timestamp: '2026-06-22T00:00:00Z'
---
# manage-data
## When to use this skill
When the task is to persist structured data inside n8n: create tables, evolve their schema (add/rename/delete columns), or load rows.
## Tool sequence
1. search_projects → why first: you need the projectId for almost everything in this group.
2. (if the table exists) search_data_tables → what it adds: locates the dataTableId. If it doesn't exist → create_data_table.
3. create_data_table / add_data_table_column / rename_data_table_column / delete_data_table_column → how the schema evolves.
4. add_data_table_rows → how data is loaded (requires the columns to already exist).
## Example task
'Save leads with email and score in a new table under the marketing project'
→ search_projects(query='marketing') → projectId
→ create_data_table(projectId='p1', name='leads', columns=[{name:'email', type:'string'},{name:'score', type:'number'}])
→ add_data_table_rows(dataTableId='t1', projectId='p1', rows=[{email:'a@b.com', score:5}])
## Don't use when
- The data lives in a workflow, not in a table → skill create-workflow
- You only want to organize workflows into folders → skill organize-projects