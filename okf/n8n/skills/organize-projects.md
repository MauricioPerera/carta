---
type: 'Skill'
title: 'organize-projects'
description: 'Organize workflows into projects and folders, and manage their lifecycle (publish/unpublish/archive).'
tools_needed: ['search_projects', 'search_folders', 'publish_workflow', 'unpublish_workflow', 'archive_workflow']
tags: ['n8n', 'skill']
timestamp: '2026-06-22T00:00:00Z'
---
# organize-projects
## When to use this skill
When the task is structural/organizational: place workflows in projects/folders, or control their lifecycle (active in production, paused, archived).
## Tool sequence
1. search_projects → why first: locates the projectId to operate on.
2. search_folders → what it adds: locates the folderId inside the project if you want to place the workflow in a folder.
3. publish_workflow / unpublish_workflow / archive_workflow → how it closes: controls the workflow lifecycle according to its desired state.
## Example task
'Put workflow X in production inside the marketing folder of the growth project'
→ search_projects(query='growth') → projectId
→ search_folders(projectId='p1', query='marketing') → folderId
→ (you create/locate the workflow; if new, create_workflow_from_code with projectId+folderId)
→ publish_workflow(workflowId='abc123')
## Don't use when
- You want to create/edit the workflow code → skill create-workflow
- You want to run it → skill run-workflow