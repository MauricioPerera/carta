---
type: 'REST Tool'
title: 'create_post'
route: 'rest'
endpoint: 'POST https://jsonplaceholder.typicode.com/posts'
description: 'Create a new post'
when_to_use: 'when you need to publish new content'
tags: ['jsonplaceholder', 'rest', 'write']
timestamp: '2026-06-22T00:00:00Z'
---
# create_post
## Parameters
- title: string
- body: string
- userId: int
## Bash example
```
curl -X POST https://jsonplaceholder.typicode.com/posts \
  -H 'Content-Type: application/json' \
  -d '{"title":"test","body":"hello","userId":1}'
```
## Returns
`{id, title, body, userId}` — id assigned by the server (101 for the first fake post).