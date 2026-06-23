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
