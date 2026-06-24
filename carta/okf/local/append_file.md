---
type: tool
title: Append File
route: local
tool: append_file
description: Append content to an existing file or create it if missing
when_to_use: Use when you need to add lines to a log, report, or existing file
tags: [file, local, append]
body:
  args:
    path: string
    content: string
---