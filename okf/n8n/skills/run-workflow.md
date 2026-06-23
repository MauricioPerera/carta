---
type: 'Skill'
title: 'run-workflow'
description: 'Run an n8n workflow (real or tested with pin data) and inspect its result.'
tools_needed: ['execute_workflow', 'test_workflow', 'get_execution', 'prepare_test_pin_data']
tags: ['n8n', 'skill']
timestamp: '2026-06-22T00:00:00Z'
---
# run-workflow
## When to use this skill
When the task is to run an existing workflow and see what happens: real execution against services, or testing with pin data to validate logic without touching external services, and inspecting the result.
## Tool sequence
1. (if testing) prepare_test_pin_data → why first: tells you what data shape to simulate in triggers/nodes with credentials/HTTP.
2. test_workflow (with pinData) or execute_workflow (real, with executionMode) → what it adds: launches the run and returns an executionId (execute) or the direct result (test).
3. get_execution → how it closes: retrieves the status and per-node outputs of that execution.
## Example task
'Test workflow X without touching Gmail and show me the result'
→ prepare_test_pin_data(workflowId='abc123')
→ [you generate realistic pinData from the schemas]
→ test_workflow(workflowId='abc123', pinData={'Gmail':[{'json':{'subject':'test'}}]})
→ get_execution(workflowId='abc123', executionId='exec456', includeData=true)
## Don't use when
- The workflow doesn't exist yet → skill create-workflow
- You only want to know if it's published → get_workflow_details