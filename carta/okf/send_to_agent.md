---
type: tool
title: Send to Agent
route: internal
name: send_to_agent
description: Delegate a subtask to a specialized agent asynchronously via the shared mailbox
when_to_use: Use when the current task requires expertise from another agent. The other agent will process it on its next run.
tags: [delegation, async, swarm, internal]
---
# send_to_agent

Delegate a subtask to another agent by dropping a message into its mailbox.
The recipient processes it on its next run; the caller does not block.

## Parameters
- to: string — the destination agent id (its inbox folder name)
- task: string — the subtask to perform, phrased as an instruction

## Usage example
```
{"tool":"send_to_agent","route":"internal","args":{"to":"calendar-agent","task":"schedule meeting with Jane tomorrow 2pm"}}
```

## Returns
A JSON receipt is written to `.postal/inbox/<to>/<timestamp>-<msgid>.json`.
The caller observes `OBSERVATION: message deposited for <to> at <path>`.

## Don't use when
- You can do the work yourself with the tools already selected
- You need a synchronous answer within this same run (use an MCP/rest tool instead)