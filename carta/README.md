# carta — reusable OKF client + agent

Packages the OKF capability-discovery pattern (select a small context from a
catalog, then run the action along the route declared in each doc's
frontmatter: `rest` or `mcp`).

## CartaClient — discovery + select + execute (no model)

```python
from carta import CartaClient

client = CartaClient(["okf/n8n"])                 # or ["okf/n8n", "okf/jsonplaceholder"]
sel = client.select("create workflow webhook")    # -> {docs, context, tokens, baseline_tokens}
print(sel["tokens"], "<", sel["baseline_tokens"])

doc = sel["docs"][0]
print(client.route_of(doc))                        # 'rest' | 'mcp'

# REST action runs through the allowlisted bash executor:
print(client.execute({"route": "rest", "command": "curl -s https://api.example.com"}))
# MCP action is returned pending (the host / MCP server resolves it):
print(client.execute({"route": "mcp", "tool": "search_nodes", "args": {"queries": ["gmail"]}}))
```

### Versioning only what you used

`selection_sha` hashes just the selected docs — not the whole catalog — so you can
record which context an agent acted on without hydrating every blob (useful with a
sparse partial clone). `doc_sha` hashes a single file.

```python
from carta.selector import select_tools, selection_sha, doc_sha

docs = select_tools("create workflow webhook", okf_path="okf/n8n")
print(selection_sha(docs))        # deterministic over only those docs
```

On the n8n catalog this reads 5 of 31 files (~84% fewer bytes) than a full-directory
hash. Run `python benchmarks/bench_sha.py` to reproduce.

## CartaAgent — full loop against an OpenAI-compatible endpoint

```python
from carta import CartaAgent

def mcp(tool, args):           # your bridge to the MCP server (optional)
    ...

agent = CartaAgent(["okf/n8n"], model="qwen2.5-7b",
                   base_url="http://localhost:1234/v1", mcp_executor=mcp)
result = agent.run("Create a workflow that emails me when a webhook arrives")
print(result["status"], len(result["steps"]), result["context_tokens"])
```

The agent bakes in a **block protocol**: one action per turn — small JSON for
tool calls, fenced blocks for long payloads (never long code in JSON) — and the
parser tolerates the backslash line-continuations small models emit. No extra
dependencies: stdlib only.

## MCP route (optional)

For `route='mcp'` actions, pass a reference executor built on the official
`mcp` SDK. Requires `pip install -e ".[mcp]"` (the `mcp` package is an optional
dependency; `import carta` works without it).

```python
from carta import CartaAgent, stdio_mcp_executor

mcp = stdio_mcp_executor('npx', ['-y', '@modelcontextprotocol/server-...'])
agent = CartaAgent(['okf/n8n'], model='qwen2.5-7b',
                   base_url='http://localhost:1234/v1', mcp_executor=mcp)
result = agent.run('Create a workflow that emails me when a webhook arrives')
```

`http_mcp_executor(url, headers=...)` is available for remote servers exposing
the streamable HTTP transport. Both return `{'ok': True, 'result': ...}` or
`{'ok': False, 'error': str}` per call.

## Generate a catalog from OpenAPI

A provider can autogenerate its OKF catalog from an OpenAPI 3.0 spec instead
of hand-writing each `.md`:

```
python -m carta.openapi_to_okf <spec.json|yaml> <out_dir>
```

This writes one `route: rest` tool doc per operation under `<out_dir>/tools/`
plus an `<out_dir>/index.md`, in the same frontmatter style as the hand-made
catalogs. Programmatically:

```python
from carta import generate, load_spec

spec = load_spec("path/to/openapi.yaml")
result = generate(spec, "okf/myprovider")
# result = {'tools': [...], 'index': '...', 'out_dir': 'okf/myprovider'}
```

The output is directly consumable by `tool_selector` and `CartaClient`.