---
type: 'Skill'
title: 'find-nodes'
description: 'Discover which n8n nodes to use for a task and get their exact parameters.'
tools_needed: ['search_nodes', 'get_suggested_nodes', 'get_node_types']
tags: ['n8n', 'skill']
timestamp: '2026-06-22T00:00:00Z'
---
# find-nodes
## When to use this skill
When the task is exploratory: which nodes exist for a service/technique, what parameters they accept, what alternatives there are. This is the discovery phase BEFORE writing workflow code.
## Tool sequence
1. search_nodes (or get_suggested_nodes if you start from a technique category) → why first: obtains the candidate nodeIds and their discriminators (resource/operation/mode).
2. get_node_types → what it adds: turns those nodeIds into TypeScript type definitions with the exact parameters.
3. (optional) get_suggested_nodes → how it closes: if search_nodes didn't give enough signal, the curated per-category suggestions complete the picture.
## Example task
'Which nodes can I use to send scheduled notifications'
→ get_suggested_nodes(categories=['notification','scheduling'])
→ search_nodes(queries=['slack','schedule trigger'])
→ get_node_types(nodeIds=[{nodeId:'n8n-nodes-base.slack', operation:'send', resource:'message'},{nodeId:'n8n-nodes-base.scheduleTrigger'}])
## Don't use when
- You already know which nodes to use and want to assemble the full workflow → skill create-workflow
- You only need the SDK syntax → get_sdk_reference directly