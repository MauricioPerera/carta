---
type: tool
title: Write File
route: local
tool: write_file
description: Write content to a local file, creating directories as needed
when_to_use: Use when you need to write or overwrite a file on the local filesystem
tags: [file, local, write]
body:
  args:
    path: string
    content: string
    mkdir: boolean (optional, default true)
---