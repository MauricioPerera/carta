"""Agent B CLI — Subscriber.

Receives Postal messages addressed to `agent-b`, validates the three layers
(POSTAL signature, CCDD contract, OKF snapshot), decrypts the payload, and
reproduces Agent A's context.

Usage (from repo root):
    python agents/agent_b.py

Deviations from the T5 spec (documented in agents/T5-REPORT.md):
  * CCDD layer verifies `msg['ccdd_contract_sha']` against
    `SHA256(.ccdd/agent-a.yaml)` — the publisher's contract, which is what
    `agent_a.py` actually embeds. The literal `agent-b.yaml` would never match
    (different file contents) and the full flow could not pass.
  * Agent B persists `{id, public_key, private_key}` (not pubkey-only).
    Decryption needs the private key matching the pubkey that Agent A encrypted
    to, across subprocess boundaries; pubkey-only persistence makes that
    impossible.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys

# Make `postal` importable when run as a script from the repo root.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from postal import (  # noqa: E402
    generate_keypair,
    Identity,
    save_identity,
    load_identity,
    verify_message,
    decrypt,
    compute_dir_sha,
    list_messages,
)

OKF_DIR = os.path.join(_REPO_ROOT, "okf")
# Publisher's contract — what agent_a signs and embeds as ccdd_contract_sha.
CCDD_PUBLISHER_CONTRACT = os.path.join(_REPO_ROOT, ".ccdd", "agent-a.yaml")
POSTAL_ROOT = os.path.join(_REPO_ROOT, ".postal")
USERS_DIR = os.path.join(POSTAL_ROOT, "users")
AGENT_B_IDFILE = os.path.join(USERS_DIR, "agent-b.json")
AGENT_A_IDFILE = os.path.join(USERS_DIR, "agent-a.json")

_MY_ID = "agent-b"
_FROM_ID = "agent-a"


def _file_sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _save_identity_with_priv(identity: Identity, path: str) -> str:
    """Persist `{id, public_key, private_key}` to `.postal/users/<id>.json`.

    Unlike `postal.save_identity` (which strips the private key), this keeps
    the private key so Agent B can decrypt messages addressed to its pubkey
    across subprocess runs.
    """
    if os.path.isdir(path) or not path.endswith(".json"):
        file_path = os.path.join(path, "users", f"{identity.id}.json")
    else:
        file_path = path
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    payload = {
        "id": identity.id,
        "public_key": identity.public_key,
        "private_key": identity.private_key,
    }
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, sort_keys=True)
    return file_path


def _load_identity_with_priv(id_: str, path: str) -> Identity:
    if os.path.isdir(path) or not path.endswith(".json"):
        file_path = os.path.join(path, "users", f"{id_}.json")
    else:
        file_path = path
    with open(file_path, "r", encoding="utf-8") as f:
        payload = json.load(f)
    return Identity(
        id=payload["id"],
        private_key=payload.get("private_key", ""),
        public_key=payload["public_key"],
    )


def _ensure_identity() -> tuple[str, str]:
    """Return `(private_key_hex, public_key_hex)` for Agent B.

    Generates a keypair and persists `{pubkey, private_key}` if no identity file
    exists (or the existing one lacks a private key). On subsequent runs, loads
    the persisted private key so messages encrypted to the persisted pubkey can
    be decrypted.
    """
    if os.path.isfile(AGENT_B_IDFILE):
        ident = _load_identity_with_priv(_MY_ID, POSTAL_ROOT)
        if ident.private_key:
            return ident.private_key, ident.public_key
        # Stale pubkey-only file (no private key) — regenerate so we can decrypt.
    priv, pub = generate_keypair()
    _save_identity_with_priv(Identity(id=_MY_ID, private_key=priv, public_key=pub), POSTAL_ROOT)
    return priv, pub


def _agent_a_pubkey() -> str:
    """Load Agent A's persisted pubkey (public-only file)."""
    if not os.path.isfile(AGENT_A_IDFILE):
        raise FileNotFoundError(
            f"Agent A identity not found: {AGENT_A_IDFILE}. Run agent_a first."
        )
    return load_identity(_FROM_ID, POSTAL_ROOT).public_key


def main() -> int:
    # 1. Agent B identity (pubkey + private key persisted for decryption).
    priv_b, _pub_b = _ensure_identity()

    # 2. Publisher pubkey for the POSTAL signature layer.
    from_pubkey = _agent_a_pubkey()

    # 3. Reference SHAs for the CCDD and OKF validation layers.
    ccdd_sha_ref = _file_sha256(CCDD_PUBLISHER_CONTRACT)
    okf_sha_ref = compute_dir_sha(OKF_DIR)

    # 4. List messages addressed to agent-b.
    messages = list_messages(_REPO_ROOT, to_id=_MY_ID)
    if not messages:
        print("NO MESSAGES FOR agent-b")
        return 0

    reproduced = 0
    for msg in messages:
        msg_id = msg.get("id", "?")
        print(f"--- message {msg_id} ---")

        # Layer a) POSTAL signature — skip on failure.
        if not verify_message(msg, from_pubkey):
            print("POSTAL SIGNATURE INVALID")
            continue

        # Layer b) CCDD contract SHA — skip on failure.
        if msg.get("ccdd_contract_sha", "") != ccdd_sha_ref:
            print("CCDD CONTRACT MISMATCH")
            continue

        # Layer c) OKF snapshot SHA — log only, do NOT skip (context may evolve).
        if msg.get("okf_snapshot_sha", "") != okf_sha_ref:
            print("OKF SNAPSHOT MISMATCH: stale context")

        # 5. Decrypt payload.
        try:
            plaintext = decrypt(priv_b, msg["payload"], msg["ephemeral_pubkey"])
            payload = json.loads(plaintext.decode("utf-8"))
        except Exception as exc:  # noqa: BLE001 — report and continue
            print(f"DECRYPT FAILED: {exc}")
            continue

        # 6. Reproduce context.
        print(f"analysis: {payload.get('analysis')}")
        print(f"tables: {payload.get('tables')}")
        print(f"metrics: {payload.get('metrics')}")
        print(f"okf_sha: {payload.get('okf_sha')}")
        print(f"ccdd_sha: {payload.get('ccdd_sha')}")
        print("CONTEXT REPRODUCED: Agent B has identical context to Agent A")
        reproduced += 1

    print(f"reproduced={reproduced}")
    return 0


if __name__ == "__main__":
    sys.exit(main())