---
type: tool
title: Run Command
route: local
tool: run_command
description: Run a shell command in a subprocess and return stdout/stderr
when_to_use: Use to run tests, linters, or build tools when no MCP is available
tags: [command, local, shell, run]
body:
  args:
    command: string
    cwd: string (optional)
    timeout: integer (optional, default 30)
---