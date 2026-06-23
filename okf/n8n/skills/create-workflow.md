---
type: 'Skill'
title: 'create-workflow'
description: 'Create or modify an n8n workflow from code, validating it and persisting it to n8n.'
tools_needed: ['get_sdk_reference', 'search_nodes', 'get_node_types', 'validate_workflow', 'create_workflow_from_code', 'update_workflow']
tags: ['n8n', 'skill']
timestamp: '2026-06-22T00:00:00Z'
---
# create-workflow
## When to use this skill
When the task is to assemble, edit, or replace an n8n workflow from code (TypeScript/JavaScript with the Workflow SDK). It covers the full flow: learn the SDK → discover nodes → get exact parameters → write code → validate → persist.
## Tool sequence
1. get_sdk_reference → why first: learn the SDK patterns, rules, and guidelines before writing a single line. Without this the code won't compile against the SDK.
2. search_nodes + get_node_types → what it adds: discover the nodes for the service/technique and get the exact parameter names. Guessing parameters produces invalid workflows.
3. validate_workflow → how it closes the code: parses and reports errors. Iterate until it passes.
4. create_workflow_from_code (or update_workflow if it exists) → how it persists: saves the validated workflow to n8n.
## Example task
'Create a workflow that sends an email when a webhook arrives'
→ get_sdk_reference(section='guidelines')
→ search_nodes(queries=['gmail','webhook'])
→ get_node_types(nodeIds=[{nodeId:'n8n-nodes-base.webhook'},{nodeId:'n8n-nodes-base.gmail', operation:'send', resource:'message'}])
→ [you write the TS code with the SDK export]
→ validate_workflow(code=<ts>) → fix until valid
→ create_workflow_from_code(code=<validated_ts>, description='Sends an email when a webhook arrives')
## Don't use when
- You only want to discover which nodes exist → skill find-nodes
- You want to run a workflow that already exists → skill run-workflow