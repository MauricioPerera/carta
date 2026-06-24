"""Tests for carta.vault — secure credential distribution."""
from __future__ import annotations

import json
import os

import pytest

from carta.vault import (
    CredentialStore,
    check_ccdd_allows_credential,
    handle_credential_request,
)


def _signed_request(requester_id, credential_name, priv_key, pub_key):
    """Build a Postal-signed credential request message."""
    fields = {
        "type": "credential_request",
        "requester_id": requester_id,
        "credential_name": credential_name,
    }
    from postal import crypto

    msg_bytes = json.dumps(fields, sort_keys=True).encode("utf-8")
    return {
        **fields,
        "requester_pubkey": pub_key,
        "signature": crypto.sign(priv_key, msg_bytes),
    }


def _write_ccdd(path, allowed):
    with open(path, "w", encoding="utf-8") as f:
        f.write("agent: requester-agent\nproject: p\n")
        f.write("can: []\ncannot: []\n")
        f.write("credentials_allowed:\n")
        for c in allowed:
            f.write(f"  - {c}\n")


# --- CredentialStore --------------------------------------------------------

def test_credential_store_get():
    store = CredentialStore({"DB_READ": "postgres://localhost/db"})
    assert store.get("DB_READ") == "postgres://localhost/db"


def test_credential_store_missing():
    store = CredentialStore({"DB_READ": "postgres://localhost/db"})
    assert store.get("MISSING") is None


def test_credential_store_from_env(monkeypatch):
    monkeypatch.setenv("CARTA_CRED_APIKEY", "abc")
    monkeypatch.setenv("CARTA_CRED_DB_READ", "postgres://x")
    monkeypatch.setenv("UNRELATED_VAR", "ignore")
    store = CredentialStore.from_env()
    assert store.get("APIKEY") == "abc"
    assert store.get("DB_READ") == "postgres://x"
    assert store.get("UNRELATED_VAR") is None


# --- check_ccdd_allows_credential -------------------------------------------

def test_check_ccdd_allows(tmp_path):
    p = tmp_path / "req.yaml"
    _write_ccdd(str(p), ["DB_READ"])
    assert check_ccdd_allows_credential(str(p), "DB_READ") is True
    assert check_ccdd_allows_credential(str(p), "DB_WRITE") is False


def test_check_ccdd_denies_missing_field(tmp_path):
    p = tmp_path / "req.yaml"
    p.write_text("agent: r\nproject: p\ncan: []\ncannot: []\n", encoding="utf-8")
    assert check_ccdd_allows_credential(str(p), "DB_READ") is False


def test_check_ccdd_missing_file(tmp_path):
    assert check_ccdd_allows_credential(str(tmp_path / "nope.yaml"), "DB_READ") is False


# --- handle_credential_request ----------------------------------------------

def test_handle_request_denied_not_in_ccdd(tmp_path):
    pytest.importorskip("postal")
    from postal import crypto

    priv, pub = crypto.generate_keypair()
    ccdd_dir = tmp_path / "ccdd"
    ccdd_dir.mkdir()
    _write_ccdd(str(ccdd_dir / "req-agent.yaml"), [])  # nothing allowed
    store = CredentialStore({"DB_READ": "postgres://secret"})
    vault = {"id": "vault-agent", "private_key": priv}
    req = _signed_request("req-agent", "DB_READ", priv, pub)
    res = handle_credential_request(
        req, store, str(ccdd_dir), vault, postal_dir=str(tmp_path / "postal")
    )
    assert res["granted"] is False
    assert res["reason"] == "not in CCDD"


def test_handle_request_denied_invalid_sig(tmp_path):
    pytest.importorskip("postal")
    from postal import crypto

    priv, pub = crypto.generate_keypair()
    ccdd_dir = tmp_path / "ccdd"
    ccdd_dir.mkdir()
    _write_ccdd(str(ccdd_dir / "req-agent.yaml"), ["DB_READ"])
    store = CredentialStore({"DB_READ": "postgres://secret"})
    vault = {"id": "vault-agent", "private_key": priv}
    req = _signed_request("req-agent", "DB_READ", priv, pub)
    req["signature"] = "00" * 64  # garbage signature
    res = handle_credential_request(
        req, store, str(ccdd_dir), vault, postal_dir=str(tmp_path / "postal")
    )
    assert res["granted"] is False
    assert res["reason"] == "invalid signature"


def test_handle_request_granted(tmp_path):
    pytest.importorskip("postal")
    from postal import crypto

    priv, pub = crypto.generate_keypair()
    ccdd_dir = tmp_path / "ccdd"
    ccdd_dir.mkdir()
    _write_ccdd(str(ccdd_dir / "req-agent.yaml"), ["DB_READ"])
    postal_dir = tmp_path / "postal"
    store = CredentialStore({"DB_READ": "postgres://secret"})
    vault = {"id": "vault-agent", "private_key": priv}
    req = _signed_request("req-agent", "DB_READ", priv, pub)
    res = handle_credential_request(
        req, store, str(ccdd_dir), vault, postal_dir=str(postal_dir)
    )
    assert res["granted"] is True
    assert res["reason"] == "ok"
    assert res["path"] and os.path.isfile(res["path"])
    # response landed in the requester's inbox
    assert "inbox" in res["path"] and "req-agent" in res["path"]
    # an audit receipt was written
    audits = list((postal_dir / "audit").glob("*.json"))
    assert len(audits) == 1
    with open(audits[0], "r", encoding="utf-8") as f:
        receipt = json.load(f)
    assert receipt["vault_agent_id"] == "vault-agent"
    assert receipt["requester_id"] == "req-agent"
    assert receipt["credential_name"] == "DB_READ"
    assert receipt["granted"] is True
    assert receipt["signature"]


def test_handle_request_response_encrypted(tmp_path):
    pytest.importorskip("postal")
    from postal import crypto

    priv, pub = crypto.generate_keypair()
    ccdd_dir = tmp_path / "ccdd"
    ccdd_dir.mkdir()
    _write_ccdd(str(ccdd_dir / "req-agent.yaml"), ["DB_READ"])
    store = CredentialStore({"DB_READ": "postgres://secret"})
    vault = {"id": "vault-agent", "private_key": priv}
    req = _signed_request("req-agent", "DB_READ", priv, pub)
    res = handle_credential_request(
        req, store, str(ccdd_dir), vault, postal_dir=str(tmp_path / "postal")
    )
    assert res["granted"] is True
    with open(res["path"], "r", encoding="utf-8") as f:
        raw = f.read()
    response_msg = json.loads(raw)
    # the plaintext must NOT appear in clear in the response file
    assert "postgres://secret" not in raw
    # the requester can decrypt the encrypted_value back to the secret
    decrypted = crypto.decrypt(
        priv,
        response_msg["encrypted_value"],
        response_msg["ephemeral_pubkey_hex"],
    )
    assert decrypted.decode("utf-8") == "postgres://secret"