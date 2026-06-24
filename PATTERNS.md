# Carta — Patterns beyond MCP

Carta started as a way to decouple capability discovery from execution,
reducing the context a small model needs to use an API. That is still its
primary use case. But the same primitives — OKF docs in git, Postal-signed
messages, a sandboxed executor — compose into patterns that have nothing to
do with MCP.

---

## Pattern 1: Durable Agent (async event processing)

The closest prior art is Cloudflare Durable Objects: a stateful unit that
hibernates, wakes on an incoming event, processes it, and goes back to sleep.
The Durable Agent pattern does the same thing with git as the durable store
and no proprietary runtime.

### The problem

An agent that needs to react to external events (a payment confirmed, a form
submitted, a CI run finished) has two bad options today:

- **Poll**: wake up every N seconds, call an API, check for new events.
  Wasteful, requires credentials, creates load.
- **Stay alive**: keep a long-running process listening for webhooks.
  Needs a server, a public IP, uptime monitoring.

### The pattern

```
External service     Minimal receiver         Git repo        Agent
(Stripe, GitHub,  →  (serverless fn,     →   (the mailbox) ← (wakes on
 any webhook)         ~15 lines)              git commit       trigger or
                      signs with Postal        = event          schedule)
```

1. The **receiver** is the only always-on component. It can be a serverless
   function (AWS Lambda, Cloudflare Worker, any VPS route). It does one thing:
   receive the HTTP POST, validate the source signature (e.g. Stripe's HMAC),
   commit a signed Postal message to git, return 200.

2. The **git repo** is the durable store. The commit log is the ordered event
   queue. Nothing is lost if the agent is offline — events accumulate.

3. The **agent** wakes on demand (cron, another webhook, manual trigger). It
   pulls the repo, reads unprocessed events (new commits since its last run),
   verifies each Postal signature, and processes them. It commits its output
   back to the same repo.

### What git gives you over a message broker

| Property | Kafka / SQS | Git + Postal |
|---|---|---|
| Durability | Yes | Yes |
| Ordered delivery | Yes | Yes (commit order) |
| Replay from any point | Kafka yes, SQS no | Yes (git log) |
| Cryptographic authorship | No | Yes (Postal ECDSA) |
| Infrastructure to run | Yes (cluster or managed) | A git host or local dir |
| Real-time throughput | High | Low (seconds per event) |

Git is not a replacement for Kafka at high throughput. It is a replacement
for the "I need durable, ordered, auditable events but I only get a few per
minute" case — which is most business logic.

### Concrete example: payment confirmation

```python
# receiver.py — runs as a serverless function
import hashlib, hmac, subprocess, json, os

def handler(event, context):
    # 1. verify Stripe's HMAC
    sig = event["headers"]["stripe-signature"]
    body = event["body"].encode()
    if not hmac.compare_digest(sig, compute_hmac(body, os.environ["STRIPE_SECRET"])):
        return {"statusCode": 400}

    # 2. write a Postal-signed event to git
    payload = json.loads(body)
    from postal import build_message, save_message
    msg = build_message(
        from_id="stripe-receiver",
        to_pubkey=AGENT_PUBKEY,
        plaintext=body,
        okf_sha="",   # no OKF context for raw events
        ccdd_sha="",
        private_key=RECEIVER_PRIVKEY,
        to_id="fulfillment-agent",
    )
    save_message(msg, repo_path=".")
    return {"statusCode": 200}
```

```python
# agent.py — runs on cron or trigger
from postal import list_messages, verify_message, load_identity

identity = load_identity("stripe-receiver", ".postal")
for msg in list_messages(".postal"):
    if verify_message(msg, identity.public_key):
        process_payment(msg)         # fulfill order, send email, etc.
        mark_processed(msg["id"])    # commit a "processed" record back
```

The agent never calls the Stripe API. It never needs Stripe credentials.
It reads events from git, verified to have come from the authorized receiver.

---

## Pattern 2: Async Agent-to-Agent

MCP and A2A (Google's Agent-to-Agent protocol) assume both agents are online
simultaneously. Many real workflows do not need that.

### When async is correct

- **Different schedules**: an agent in UTC-5 sends work to an agent in UTC+9.
- **Long-running tasks**: Agent A kicks off a task that takes 20 minutes.
  Holding an HTTP connection open is wasteful and fragile.
- **Human-in-the-loop gates**: a task must be reviewed before Agent B proceeds.
- **Cost batching**: accumulate 50 inference requests, process them in one
  cheap overnight run instead of 50 real-time calls.

### The pattern

```
Agent A                    Git repo               Agent B
  ↓                      (shared mailbox)            ↓
select context  →  Postal-signed task message  →  verify signature
compute sha        (task + selection_sha           verify selection_sha
sign receipt       + ccdd_sha + payload)           process task
                                                   write signed response
```

Each message carries `selection_sha` — the hash of the exact OKF docs Agent A
used to formulate the task. Agent B can verify it is responding to the same
version of the knowledge A was acting on. This is impossible in synchronous
HTTP protocols.

### Composing with A2A

Carta async and A2A are complementary:

```
1. Agent A clones Agent B's OKF catalog (offline, Carta)
2. Selects the 3 relevant tools out of 25 (Carta selector, ~81% fewer tokens)
3. If B is online: delegates via A2A (HTTP, real-time)
   If B is offline: deposits a Postal message in B's git repo (async)
4. Saves a signed receipt of what context was used (Carta/Postal)
```

The same agent code handles both transports; the OKF `route` field selects
which path to take.

---

## Pattern 3: Third-party event ingestion (no agent required on the write side)

The write side does not have to be an agent. Any system that can make an HTTP
request or run a CLI can deposit events into the git mailbox.

Examples:

| Source | Trigger | Receiver writes to git |
|---|---|---|
| Stripe | Payment confirmed | Order fulfillment event |
| GitHub | PR merged | Deployment trigger event |
| Calendly | Meeting booked | Meeting prep event |
| Any form | Submission | Lead processing event |
| IoT sensor | Threshold exceeded | Alert event |

The pattern is always the same: a minimal, stateless HTTP receiver validates
the source, signs the event with Postal, commits to git. The agent processes
on its own schedule.

**What this is:** event sourcing without a broker. Git is the log; Postal
signatures replace the broker's delivery guarantee with cryptographic proof
of authorship.

---

## Positioning

Carta covers a different quadrant than MCP or A2A:

```
                    Online (real-time)
                           │
          A2A, MCP ────────┤
                           │
  High infra ──────────────┼────────────── No infra
                           │
                           │──── Carta
                    Async (durable)
```

- **MCP**: discovery + execution, always-on server, real-time.
- **A2A**: agent orchestration, HTTP, real-time, both sides must be live.
- **Carta**: discovery offline, execution when needed, async-first, git as
  the durable substrate.

Carta is not trying to replace MCP or A2A. It fills the cases they don't:
offline consumers, async workflows, auditable decisions, and APIs whose owners
cannot or will not run a server.

---

## Pattern 4: Emergent Dev Team (spec-driven multi-agent development)

Single-agent development has a structural flaw: the agent that writes the code
also writes the tests. It cannot be impartial — it knows which shortcuts it
took, and its tests reflect the implementation, not the requirements.

Carta's swarm model fixes this architecturally, not by discipline.

### The team

```
User describes project to orchestrator (Claude)
  → orchestrator runs: carta init <project-dir> --name <name>
  → a full dev team is scaffolded in git, ready to run

spec-agent    (reads requirements, decomposes into atomic tasks)
     ↓ send_to_agent — only the task spec, never the code
tester-agent  (writes tests against the spec — never saw the coder's reasoning)
     ↓ send_to_agent — spec + tests
coder-agent   (implements until tests pass — Qwen or any coding-optimized model)
     ↓ send_to_agent — spec + code + test results
reviewer-agent (final gate — sees everything, wrote nothing)
```

### Why context isolation matters

The tester cannot bias its tests toward the implementation because it never had
the implementation context. The separation is physical: different agents, different
turns, different inboxes. The same model cannot be tester and coder simultaneously.

### CCDD contracts enforce roles

Each agent has a specific contract that defines what it is structurally allowed
to do:

```yaml
# .ccdd/coder.yaml
can: [write_code, read_spec, run_linter, send_to_agent]
cannot: [write_tests, push_to_main, approve_pr, modify_spec]

# .ccdd/tester.yaml
can: [write_tests, read_spec, read_code, run_tests, send_to_agent]
cannot: [modify_source, push_to_main, approve_pr]

# .ccdd/reviewer.yaml
can: [read_all, approve, reject, comment]
cannot: [write_code, write_tests, push_to_main]
```

The coder cannot approve its own PR even if the model tries. The tester cannot
modify source. These are not prompts — they are governance contracts, versioned
in git alongside the code they govern.

### The repository layout

```
project/
  agents/           ← OKF catalog (router selects which agent to load)
  agent-specs/      ← agent.yaml definitions (the "discs")
  .ccdd/            ← per-agent contracts
  .okf/             ← project tool catalog
  .postal/inbox/    ← async mailbox between agents
  .postal/audit/    ← signed receipts of every agent action
```

Bootstrap a full team with one command:

```
carta init my-project --name "payment-service"
```

### What the orchestrator does

The human (or Claude) describes the project once. The orchestrator:
1. Runs `carta init` to scaffold the team
2. Sends the first task to spec-agent via `carta run agent-specs/spec-agent.yaml --task "..."`
3. The chain runs by turns: spec → tester → coder → reviewer
4. If a new role is needed mid-project (e.g. a security auditor), the orchestrator
   creates a new `agent.yaml` + CCDD contract and adds it to the router catalog

The team is not fixed — it emerges from the project requirements.

### Comparison with existing frameworks

| Property | LangGraph / CrewAI | Carta Dev Team |
|---|---|---|
| Agents alive simultaneously | Yes (memory) | No (one at a time) |
| Context isolation between agents | Partial | Structural (separate inboxes) |
| Test independence from implementation | By discipline | By architecture |
| LLM per role | Usually same | Each agent picks its own |
| Audit trail | Logs | ECDSA-signed receipts |
| Team definition | Code | git (agent.yaml + CCDD) |
| New agent mid-project | Redeploy | `carta init` + add to catalog |

---

## Pattern 5: Cross-model specialization (protocol, not framework)

Every agent framework has its own conventions: `CLAUDE.md`, `.codex/`,
MCP servers, plugin directories. These are internal to one framework and
don't compose with others.

Carta is different: it is a coordination protocol that any agent can adopt
regardless of its underlying framework. An agent needs to know three things
to participate in the swarm:

1. Read OKF docs (discover which capabilities exist)
2. Read/write `.postal/` (send and receive tasks)
3. Respect its CCDD contract (what it is allowed to do)

The underlying model, language, or agent framework is irrelevant to Carta.

### Routing work to the right model

Different models have different cost/capability profiles. Routing tasks to
the cheapest model that can handle them reduces cost significantly:

```
Reasoning model (o3, R1, Opus)        — plans, decomposes, strategic decisions
     ↓ send_to_agent
Vision model (GPT-4V, Claude-3)       — evaluates screenshots, extracts visual data
     ↓ send_to_agent
Coding model (Qwen, Codestral)        — implements code, no reasoning overhead
     ↓ send_to_agent
Small/fast model (Haiku, Gemma)       — routing, summaries, trivial validation
```

A reasoning model (expensive) only plans. It delegates implementation to a
coding model (cheap). The coding model never spends tokens on strategy.
The vision model only runs when there is something to see.

### Concrete example: visual regression testing

```
CI trigger
  → vision-agent receives screenshot pair (before/after)
  → extracts: "button moved 4px left, color changed from #334 to #335"
  → send_to_agent("tester-agent", structured diff)

tester-agent (coding model)
  → receives structured visual diff (no image, no vision tokens)
  → writes regression test asserting pixel positions and colors
  → send_to_agent("reviewer-agent", test code)

reviewer-agent (reasoning model)
  → reviews: is this the right assertion? will it catch regressions?
  → approves or requests changes
```

The vision model never writes code. The coding model never looks at images.
The reasoning model never processes pixels. Each model does what costs it
the least.

### Framework independence

An agent running in Claude Code, Codex, Open Claw, or a plain Python script
participates in the same swarm as long as it can write to `.postal/inbox/`.
Carta does not own the agent — it provides the protocol.

```
Claude Code agent   ─┐
Codex agent         ─┤──→  .postal/inbox/  ←──  same swarm, different runtimes
Python script       ─┤
Any HTTP caller     ─┘
```

### Economic model

| Model tier | Token cost | Best for |
|---|---|---|
| Reasoning (o3, R1) | High | Planning, decomposition, review |
| Frontier (Opus, GPT-4) | Medium-high | Complex reasoning, vision |
| Mid (Sonnet, Qwen-72B) | Medium | General tasks |
| Coding (Codestral, Qwen-coder) | Low | Implementation |
| Small (Haiku, Gemma) | Very low | Routing, summaries |

Carta routes each subtask to the cheapest tier that can handle it.
A full software cycle (plan → implement → test → review) costs far less
than running every step through a reasoning model.
