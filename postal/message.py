"""Postal message: build & verify signed+encrypted envelopes."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from . import crypto


SIGNED_FIELDS = (
    "id", "from", "to", "okf_snapshot_sha", "ccdd_contract_sha",
    "payload", "ephemeral_pubkey", "timestamp",
)


def _canonical(message: dict) -> bytes:
    """Deterministic serialization of the signed fields (signature excluded)."""
    payload = {k: message.get(k, "") for k in SIGNED_FIELDS}
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def build_message(
    from_id: str,
    to_pubkey: str,
    plaintext: bytes,
    okf_sha: str,
    ccdd_sha: str,
    private_key: str,
    to_id: str = "",
) -> dict:
    """Build a signed, encrypted Postal message dict.

    `to_id` is the recipient agent_id; it is set on the 'to' field BEFORE signing
    so the signature covers the recipient. Defaults to "" for backward compat.
    """
    enc = crypto.encrypt(to_pubkey, plaintext)
    msg = {
        "id": str(uuid.uuid4()),
        "from": from_id,
        "to": to_id,
        "okf_snapshot_sha": okf_sha,
        "ccdd_contract_sha": ccdd_sha,
        "payload": enc["ciphertext_hex"],
        "ephemeral_pubkey": enc["ephemeral_pubkey_hex"],
        "signature": "",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    msg["signature"] = crypto.sign(private_key, _canonical(msg))
    return msg


def verify_message(message: dict, from_pubkey: str) -> bool:
    """Verify the message signature against from_pubkey. Returns bool."""
    try:
        sig = message.get("signature", "")
        if not sig:
            return False
        check = dict(message)
        check["signature"] = ""
        return crypto.verify(from_pubkey, _canonical(check), sig)
    except Exception:
        return False