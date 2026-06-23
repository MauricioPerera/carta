---
type: 'REST Tool'
title: 'get_user'
route: 'rest'
endpoint: 'GET https://jsonplaceholder.typicode.com/users/{id}'
description: 'Get user data by ID'
when_to_use: 'when you need information about the author of a post'
tags: ['jsonplaceholder', 'rest', 'read']
timestamp: '2026-06-22T00:00:00Z'
---
# get_user
## Parameters
- id (path param): user ID
## Bash example
```
curl https://jsonplaceholder.typicode.com/users/1
```
## Returns
Object `{id, name, username, email, ...}`