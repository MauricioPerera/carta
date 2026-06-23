"""Agent A CLI — Publisher.

Reads the OKF, references the CCDD contract, builds a signed+encrypted Postal
message summarizing the OKF, and publishes it to .postal/messages/.

Usage (from repo root):
    python agents/agent_a.py
"""
from __future__ import annotations

import hashlib
import json
import os
import re
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
    build_message,
    save_message,
    compute_dir_sha,
)

OKF_DIR = os.path.join(_REPO_ROOT, "okf")
CCDD_CONTRACT = os.path.join(_REPO_ROOT, ".ccdd", "agent-a.yaml")
POSTAL_ROOT = os.path.join(_REPO_ROOT, ".postal")
USERS_DIR = os.path.join(POSTAL_ROOT, "users")
AGENT_A_IDFILE = os.path.join(USERS_DIR, "agent-a.json")
AGENT_B_IDFILE = os.path.join(USERS_DIR, "agent-b.json")

_FROM_ID = "agent-a"
_TO_ID = "agent-b"


def _title_of(md_path: str) -> str:
    """Extract `title:` from YAML frontmatter of an OKF .md file."""
    with open(md_path, "r", encoding="utf-8") as f:
        text = f.read()
    m = re.search(r"^title:\s*['\"]?(.*?)['\"]?\s*$", text, re.MULTILINE)
    return m.group(1) if m else os.path.splitext(os.path.basename(md_path))[0]


def _list_titles(subdir: str) -> list[str]:
    d = os.path.join(OKF_DIR, subdir)
    if not os.path.isdir(d):
        return []
    files = sorted(n for n in os.listdir(d) if n.endswith(".md"))
    return [_title_of(os.path.join(d, n)) for n in files]


def _file_sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _ensure_identity() -> tuple[str, str]:
    """Return (private_key_hex, public_key_hex) for Agent A.

    Generates a keypair and persists ONLY the pubkey to disk if no identity
    file exists. The private key is session-only (never written to disk).
    """
    if os.path.isfile(AGENT_A_IDFILE):
        loaded = load_identity(_FROM_ID, POSTAL_ROOT)
        # Private key is not on disk by design; we cannot sign with a stale
        # pubkey. Regenerate a fresh keypair and overwrite the pubkey so the
        # signature matches the persisted identity.
        priv, pub = generate_keypair()
        save_identity(Identity(id=_FROM_ID, private_key=priv, public_key=pub), POSTAL_ROOT)
        return priv, pub
    priv, pub = generate_keypair()
    save_identity(Identity(id=_FROM_ID, private_key=priv, public_key=pub), POSTAL_ROOT)
    return priv, pub


def _recipient_pubkey() -> str:
    """Agent B's pubkey if its identity exists, else a generated placeholder."""
    if os.path.isfile(AGENT_B_IDFILE):
        return load_identity(_TO_ID, POSTAL_ROOT).public_key
    _, pub = generate_keypair()  # placeholder pubkey; not persisted
    return pub


def main() -> dict:
    # 1. OKF snapshot SHA
    okf_sha = compute_dir_sha(OKF_DIR)

    # 2. CCDD contract SHA
    ccdd_sha = _file_sha256(CCDD_CONTRACT)

    # 3. Agent A identity (pubkey-only on disk)
    priv_a, _pub_a = _ensure_identity()

    # 4. Payload: OKF summary
    tables = _list_titles("tables")
    metrics = _list_titles("metrics")
    payload = {
        "analysis": f"Analysis of {len(tables)} tables and {len(metrics)} metrics",
        "tables": tables,
        "metrics": metrics,
        "okf_sha": okf_sha,
        "ccdd_sha": ccdd_sha,
    }

    # 6. Build + publish the signed/encrypted message
    to_pubkey = _recipient_pubkey()
    msg = build_message(
        from_id=_FROM_ID,
        to_id=_TO_ID,
        to_pubkey=to_pubkey,
        plaintext=json.dumps(payload).encode("utf-8"),
        okf_sha=okf_sha,
        ccdd_sha=ccdd_sha,
        private_key=priv_a,
    )

    # 7. Persist message
    save_message(msg, _REPO_ROOT)

    # 8. Report
    print(f"message_id={msg['id']}")
    print(f"okf_sha={okf_sha}")
    print(f"ccdd_sha={ccdd_sha}")
    return msg


if __name__ == "__main__":
    main()