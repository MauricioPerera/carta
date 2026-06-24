"""vault-agent: secure credential distribution with CCDD governance.

The vault is the only agent that holds credentials in the clear. Other agents
request credentials via a Postal-signed message; the vault verifies the
signature, checks the requester's CCDD contract allows the credential, and
returns the value encrypted to the requester's public key (only the requester
can decrypt it). Every access is recorded as a signed audit receipt.
"""
from __future__ import annotations

import datetime as _dt
import json
import os


class CredentialStore:
    """In-memory map of credential name -> secret value."""

    def __init__(self, credentials: dict[str, str]):
        self.credentials = credentials

    def get(self, name: str) -> str | None:
        return self.credentials.get(name)

    @classmethod
    def from_env(cls, prefix: str = "CARTA_CRED_") -> "CredentialStore":
        """Load environment variables with ``prefix`` as credentials.

        ``CARTA_CRED_API_KEY=abc`` -> ``{"API_KEY": "abc"}``.
        """
        import os

        creds = {
            k[len(prefix):]: v
            for k, v in os.environ.items()
            if k.startswith(prefix)
        }
        return cls(creds)


def check_ccdd_allows_credential(ccdd_path: str, credential_name: str) -> bool:
    """Read the requester's CCDD YAML and check ``credentials_allowed``.

    Returns ``False`` if the file does not exist, fails to parse, or does not
    list ``credential_name`` under ``credentials_allowed``.
    """
    try:
        import yaml

        with open(ccdd_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        allowed = data.get("credentials_allowed", [])
        return credential_name in allowed
    except Exception:
        return False


def _now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


def _now_fs() -> str:
    """Filesystem-safe timestamp for filenames (UTC, second precision)."""
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%S%f")


def _signed_request_bytes(request_msg: dict) -> bytes:
    """Canonical bytes of the request fields covered by the signature."""
    payload = {
        k: request_msg.get(k)
        for k in ("type", "requester_id", "credential_name")
    }
    return json.dumps(payload, sort_keys=True).encode("utf-8")


def handle_credential_request(
    request_msg: dict,
    store: CredentialStore,
    ccdd_dir: str,
    vault_identity,
    postal_dir: str = ".postal",
) -> dict:
    """Process a credential request. Returns ``{granted, reason, path}``.

    ``vault_identity`` is a mapping with ``id`` (agent id) and ``private_key``
    (Postal private key hex) used to sign the response.
    """
    try:
        from postal import crypto
    except Exception:
        return {"granted": False, "reason": "postal not available", "path": None}

    requester_id = request_msg.get("requester_id")
    credential_name = request_msg.get("credential_name")
    requester_pubkey = request_msg.get("requester_pubkey")
    signature = request_msg.get("signature")

    # 2. Verify the request signature with the requester's public key.
    if not (requester_pubkey and signature) or not crypto.verify(
        requester_pubkey, _signed_request_bytes(request_msg), signature
    ):
        return {"granted": False, "reason": "invalid signature", "path": None}

    # 3. Check the requester's CCDD allows this credential.
    ccdd_path = os.path.join(ccdd_dir, f"{requester_id}.yaml")
    if not check_ccdd_allows_credential(ccdd_path, credential_name):
        return {"granted": False, "reason": "not in CCDD", "path": None}

    # 4. Look up the credential value.
    value = store.get(credential_name)
    if value is None:
        return {"granted": False, "reason": "credential not found", "path": None}

    # 5. Encrypt the value to the requester's public key.
    enc = crypto.encrypt(requester_pubkey, value.encode("utf-8"))

    # 6. Build the signed response message.
    timestamp = _now_iso()
    response_msg = {
        "type": "credential_response",
        "credential_name": credential_name,
        "encrypted_value": enc["ciphertext_hex"],
        "ephemeral_pubkey_hex": enc["ephemeral_pubkey_hex"],
        "granted_by": vault_identity["id"],
        "timestamp": timestamp,
    }
    resp_bytes = json.dumps(response_msg, sort_keys=True).encode("utf-8")
    response_msg["signature"] = crypto.sign(vault_identity["private_key"], resp_bytes)

    # 7. Drop the response in the requester's inbox.
    inbox_dir = os.path.join(postal_dir, "inbox", requester_id)
    os.makedirs(inbox_dir, exist_ok=True)
    ts_fs = _now_fs()
    response_path = os.path.join(inbox_dir, f"{ts_fs}-vault.json")
    with open(response_path, "w", encoding="utf-8") as f:
        json.dump(response_msg, f, indent=2)

    # 8. Write the signed audit receipt.
    audit_dir = os.path.join(postal_dir, "audit")
    os.makedirs(audit_dir, exist_ok=True)
    audit = {
        "vault_agent_id": vault_identity["id"],
        "requester_id": requester_id,
        "credential_name": credential_name,
        "granted": True,
        "timestamp": timestamp,
        "signature": response_msg["signature"],
    }
    cred_tag = (credential_name or "")[:8]
    audit_path = os.path.join(audit_dir, f"{ts_fs}-vault-{cred_tag}.json")
    with open(audit_path, "w", encoding="utf-8") as f:
        json.dump(audit, f, indent=2)

    # 9. Done.
    return {"granted": True, "reason": "ok", "path": response_path}