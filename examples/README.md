# Examples

Two worked examples, one per execution route.

| Example | Route | Needs a server? | Run |
| ------- | ----- | --------------- | --- |
| [JSONPlaceholder — publish a post](#rest--jsonplaceholder) | `rest` | No | `python agents/agent_rest.py` |
| [n8n — build a workflow](n8n/README.md) | `mcp` | Yes (n8n MCP) | walkthrough |

## REST — JSONPlaceholder

The fully self-contained example: discovery, selection and execution all run
locally. The agent reads the trimmed OKF catalog, sees every tool is `route: rest`,
and executes the sequence with plain `curl` through the sandboxed `bash` executor.
No MCP server, no API key.

```bash
python agents/agent_rest.py
# → TASK COMPLETE - route: rest - no MCP server required
```

Source: [agents/agent_rest.py](../agents/agent_rest.py) · catalog: [okf/jsonplaceholder](../okf/jsonplaceholder)

## MCP — n8n

The example for capabilities that have no REST equivalent (schema validation,
node discovery). Discovery and selection still run locally and offline; only the
`route: mcp` tools are proxied to a running n8n MCP server. See
[n8n/README.md](n8n/README.md) for the full walkthrough and the validated
workflow it produces.
