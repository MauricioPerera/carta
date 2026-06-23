"""Postal audit receipts for CartaAgent runs.

Signs a deterministic JSON receipt over a run's outcome (task, selection SHA,
CCDD contract SHA, status) using the Postal ECDSA P-256 primitives, and writes
it to disk under a per-run audit directory.

Postal is an optional dependency: this module imports ``postal.crypto`` lazily
inside :func:`sign_run_receipt`, so ``import carta`` works without
``cryptography`` installed. Callers that pass a ``postal_identity`` are
expected to have Postal available.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone


def sign_run_receipt(
    identity,
    task: str,
    selection_sha: str,
    ccdd_sha: str,
    status: str,
    postal_dir: str = ".postal/audit",
) -> str:
    """Sign and save an audit receipt. Returns the file path written.

    Builds a receipt dict, canonicalizes it (sorted keys, compact JSON) for a
    deterministic signature, signs with the identity's private key via
    ``postal.crypto.sign``, appends the signature, and writes the receipt to
    ``postal_dir/<timestamp_compact>-<sha8>.json``.
    """
    receipt = {
        "agent_id": identity.id,
        "task": task,
        "selection_sha": selection_sha,
        "ccdd_sha": ccdd_sha,
        "status": status,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    canonical_bytes = json.dumps(
        receipt, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")

    from postal.crypto import sign

    sig = sign(identity.private_key, canonical_bytes)
    receipt["signature"] = sig

    os.makedirs(postal_dir, exist_ok=True)

    # timestamp_compact: strip ':', '-', '.' -> digits only, then insert a 'T'
    # between the date and time portions to keep it readable (e.g.
    # "20260623T120000"). Derived from the ISO timestamp actually written.
    digits = "".join(c for c in receipt["timestamp"] if c.isdigit())
    # digits = YYYYMMDDHHMMSSffffff -> YYYYMMDD T HHMMSS
    if len(digits) >= 14:
        timestamp_compact = f"{digits[:8]}T{digits[8:14]}"
    else:
        timestamp_compact = digits
    sha8 = (selection_sha or "00000000")[:8]

    filename = f"{timestamp_compact}-{sha8}.json"
    path = os.path.join(postal_dir, filename)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(receipt, f, indent=2, sort_keys=True)

    return path