---
type: 'Skill'
title: 'Publish and read content'
route: 'rest'
description: 'Create posts and verify they were saved correctly'
tools_needed: ['create_post', 'get_posts', 'get_user']
tags: ['jsonplaceholder', 'skill']
timestamp: '2026-06-22T00:00:00Z'
---
# Publish and read content
## When to use this skill
When the task is to publish a new post and confirm it exists in the API.
It demonstrates the full REST route without an MCP server: all tools run
with `curl` against `https://jsonplaceholder.typicode.com`.
## Sequence
1. `get_user` → verify the userId exists (GET /users/{id})
2. `create_post` → publish the content (POST /posts)
3. `get_posts?userId=X` → verify it appears (GET /posts?userId=X)
## Note
JSONPlaceholder is a *fake* API: the POST returns the created object with `id: 101`
but does not actually persist it, so step 3 returns the original posts.
The point of the skill is to exercise the `rest` route (curl + audit), not persistence.