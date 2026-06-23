---
type: 'REST Tool'
title: 'get_posts'
route: 'rest'
endpoint: 'GET https://jsonplaceholder.typicode.com/posts'
description: 'List all posts or filter by userId'
when_to_use: 'when you need to read existing posts'
tags: ['jsonplaceholder', 'rest', 'read']
timestamp: '2026-06-22T00:00:00Z'
---
# get_posts
## Parameters
- userId (query param, optional): filter by author
## Bash example
```
curl https://jsonplaceholder.typicode.com/posts?userId=1
```
## Returns
Array of `{id, title, body, userId}`