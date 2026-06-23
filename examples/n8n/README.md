# n8n example — build a workflow (route: mcp)

Goal: have an agent build a real n8n workflow —
**Webhook (POST `/lead`) → Edit Fields (Set) `received = true` → Respond to Webhook** —
using Carta's trimmed context instead of loading every n8n tool into the prompt.

n8n's intelligence tools (`validate_workflow`, `search_nodes`, `get_node_types`,
`get_sdk_reference`) have no REST equivalent, so this example uses `route: mcp`:
discovery and selection still run **locally and offline** against `okf/n8n/`, and
only those tool calls are proxied to a running [n8n MCP server](https://github.com/n8nio).

## 1. Select context (local, no server)

```bash
python -m carta.selector "create a workflow webhook set field respond" --provider n8n
```
```
Selected docs (5/30):
  okf/n8n/skills/create-workflow.md
  okf/n8n/tools/create_workflow_from_code.md
  okf/n8n/tools/validate_workflow.md
  okf/n8n/tools/search_nodes.md
  okf/n8n/tools/update_workflow.md
~1532 context tokens · 18.9% of the 7902-token baseline
```

Instead of ~7.9k tokens of tool definitions, the model gets ~1.5k tokens of
exactly the docs this task needs. This is the difference between a small model
stalling and a small model planning.

## 2. Follow the skill sequence

The selected `create-workflow` skill prescribes the order. The host executes each
tool against the n8n MCP and feeds the result back to the model:

1. `get_sdk_reference` — learn the SDK patterns
2. `search_nodes(["webhook","set","respond to webhook"])` — find node ids
3. `get_node_types([...])` — get exact parameter names (don't guess)
4. write the SDK code
5. `validate_workflow(code)` — parse + check, iterate until valid
6. `create_workflow_from_code(code)` — persist to n8n

## 3. Result

The validated workflow this loop produces is [`lead-capture.ts`](lead-capture.ts)
(3 nodes, `validate_workflow` → `{valid: true, nodeCount: 3}`), created in n8n
with no manual JSON import.

## Notes from a real run

- A small local coder model (~12B) followed the whole tool sequence on its own —
  the point of the trimmed context. Where it struggled was **emitting long code
  inside a JSON tool-call envelope**; having it return a fenced ```ts block``` and
  letting the host call the tool fixed that.
- Codegen precision is model-dependent: a stronger coder produced valid SDK code
  in one shot, while a 4-bit 12B needed validator feedback to converge.
- Discovery/selection (steps 1 and the `tool_selector` call) never needed a server —
  only the MCP tool calls do.
