"""T25: Swarm delegation — one agent deposits work for another.

:func:`send_to_agent` is the pure helper behind the ``route='internal'``
action. It writes a Postal-style message JSON into the recipient's inbox so
the destination agent picks it up on its next mailbox run (see
:mod:`carta.mailbox`). No bash, no REST, no network: the sender just drops a
file under ``postal_dir/inbox/<to_agent_id>/``.

Postal is an optional dependency: ``postal.crypto.sign`` is imported lazily
inside :func:`send_to_agent`, so this module imports cleanly without
``cryptography`` installed. Signing only happens when the caller passes an
``identity``.
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone


def send_to_agent(
    from_id: str,
    to_agent_id: str,
    task: str,
    postal_dir: str = ".postal",
    identity=None,
    selection_sha: str = "",
) -> str:
    """Deposit a task message into ``<to_agent_id>``'s inbox. Returns the path.

    Builds ``{id, from, to, task, selection_sha, timestamp}`` (ISO UTC). When
    ``identity`` is given, the message is canonicalized (sorted keys, compact
    JSON) and signed with ``postal.crypto.sign``; the resulting ``signature``
    field is appended. The file is written to
    ``postal_dir/inbox/<to_agent_id>/<timestamp_compact>-<message_id>.json``
    using the same timestamp format as :mod:`carta.postal_audit`.
    """
    message_id = uuid.uuid4().hex[:8]
    timestamp = datetime.now(timezone.utc).isoformat()

    message = {
        "id": message_id,
        "from": from_id,
        "to": to_agent_id,
        "task": task,
        "selection_sha": selection_sha,
        "timestamp": timestamp,
    }

    if identity is not None:
        canonical_bytes = json.dumps(
            message, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        from postal.crypto import sign

        message["signature"] = sign(identity.private_key, canonical_bytes)

    inbox = os.path.join(postal_dir, "inbox", to_agent_id)
    os.makedirs(inbox, exist_ok=True)

    # timestamp_compact: digits only -> "YYYYMMDDTHHMMSS" (matches postal_audit).
    digits = "".join(c for c in timestamp if c.isdigit())
    if len(digits) >= 14:
        timestamp_compact = f"{digits[:8]}T{digits[8:14]}"
    else:
        timestamp_compact = digits

    filename = f"{timestamp_compact}-{message_id}.json"
    path = os.path.join(inbox, filename)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(message, f, indent=2, sort_keys=True)

    return path