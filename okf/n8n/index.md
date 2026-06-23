---
type: 'MCP Server'
title: 'n8n MCP Tools Catalog'
description: 'OKF catalog of the 25 tools from the n8n MCP server, grouped into 5 skills for selective loading by a small model.'
tags: ['n8n', 'mcp', 'catalog']
timestamp: '2026-06-22T00:00:00Z'
resource: 'https://mcp.n8n.io'
---

# n8n MCP Tools

Catalog of the 25 tools exposed by the n8n MCP server to build workflows programmatically with the n8n Workflow SDK.

## Why this catalog exists

A small model that needs to operate n8n doesn't have to load all 25 tools (~5000 tokens) at once. Loading ONLY the relevant skill + its tool docs (~500 tokens) is enough for most tasks. This catalog indexes tools by group and by skill so the orchestrator can choose what to load.

## Groups (6)

| Group | Tools | Covers |
|-------|-------|------|
| workflow_management | 7 | create, update, archive, publish, unpublish, view, search workflows |
| execution | 4 | execute, test, inspect executions, prepare pin data |
| nodes | 4 | discover nodes, get types, suggestions, SDK reference |
| data_tables | 7 | create, modify, search data tables |
| organization | 2 | folders and projects |
| validation | 1 | validate workflow code before create/update |

## Skills (5) — what to load per task

| Skill | Required tools | Typical task |
|-------|-------------------|--------------|
| [create-workflow](skills/create-workflow.md) | validate_workflow, get_sdk_reference, create_workflow_from_code, update_workflow | create or modify a workflow from code |
| [find-nodes](skills/find-nodes.md) | search_nodes, get_node_types, get_suggested_nodes | discover which nodes to use and their parameters |
| [run-workflow](skills/run-workflow.md) | execute_workflow, get_execution, test_workflow, prepare_test_pin_data | run a workflow and see its result |
| [manage-data](skills/manage-data.md) | create_data_table, add_data_table_column, add_data_table_rows, delete_data_table_column, rename_data_table, rename_data_table_column, search_data_tables | operate data tables |
| [organize-projects](skills/organize-projects.md) | search_folders, search_projects, archive_workflow, publish_workflow, unpublish_workflow | organize workflows into folders/projects and lifecycle |

## How to choose

1. Identify the verb of the task: *create/edit* → create-workflow; *discover* → find-nodes; *run* → run-workflow; *persist data* → manage-data; *organize* → organize-projects.
2. Load the skill doc + the tool docs it lists in `tools_needed`.
3. Run the sequence indicated in the skill.

## Tools (25)

### workflow_management
- [create_workflow_from_code](tools/create_workflow_from_code.md)
- [update_workflow](tools/update_workflow.md)
- [archive_workflow](tools/archive_workflow.md)
- [publish_workflow](tools/publish_workflow.md)
- [unpublish_workflow](tools/unpublish_workflow.md)
- [get_workflow_details](tools/get_workflow_details.md)
- [search_workflows](tools/search_workflows.md)

### execution
- [execute_workflow](tools/execute_workflow.md)
- [test_workflow](tools/test_workflow.md)
- [get_execution](tools/get_execution.md)
- [prepare_test_pin_data](tools/prepare_test_pin_data.md)

### nodes
- [search_nodes](tools/search_nodes.md)
- [get_node_types](tools/get_node_types.md)
- [get_suggested_nodes](tools/get_suggested_nodes.md)
- [get_sdk_reference](tools/get_sdk_reference.md)

### data_tables
- [create_data_table](tools/create_data_table.md)
- [add_data_table_column](tools/add_data_table_column.md)
- [add_data_table_rows](tools/add_data_table_rows.md)
- [delete_data_table_column](tools/delete_data_table_column.md)
- [rename_data_table](tools/rename_data_table.md)
- [rename_data_table_column](tools/rename_data_table_column.md)
- [search_data_tables](tools/search_data_tables.md)

### organization
- [search_folders](tools/search_folders.md)
- [search_projects](tools/search_projects.md)

### validation
- [validate_workflow](tools/validate_workflow.md)