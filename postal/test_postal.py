"""Postal adapter tests."""
import os
import json
import shutil
import tempfile

import pytest

from postal import (
    generate_keypair,
    sign,
    verify,
    encrypt,
    decrypt,
    Identity,
    save_identity,
    load_identity,
    build_message,
    verify_message,
    compute_dir_sha,
    save_message,
    list_messages,
)


def test_sign_verify():
    priv, pub = generate_keypair()
    msg = b"hello postal"
    sig = sign(priv, msg)
    assert isinstance(sig, str)
    assert verify(pub, msg, sig) is True
    assert verify(pub, b"tampered", sig) is False
    assert verify(pub, msg, "00" * 32) is False


def test_encrypt_decrypt():
    priv_a, pub_a = generate_keypair()
    priv_b, pub_b = generate_keypair()
    plaintext = b"secret payload for B"
    enc = encrypt(pub_b, plaintext)
    assert "ciphertext_hex" in enc and "ephemeral_pubkey_hex" in enc
    assert enc["ciphertext_hex"] != plaintext.hex()
    dec = decrypt(priv_b, enc["ciphertext_hex"], enc["ephemeral_pubkey_hex"])
    assert dec == plaintext
    # wrong key fails
    with pytest.raises(Exception):
        decrypt(priv_a, enc["ciphertext_hex"], enc["ephemeral_pubkey_hex"])


def test_build_and_verify_message():
    priv_a, pub_a = generate_keypair()
    priv_b, pub_b = generate_keypair()
    okf_sha = "a" * 64
    ccdd_sha = "b" * 64
    msg = build_message("agent-a", pub_b, b"hi from A", okf_sha, ccdd_sha, priv_a)
    assert msg["from"] == "agent-a"
    assert msg["okf_snapshot_sha"] == okf_sha
    assert msg["ccdd_contract_sha"] == ccdd_sha
    assert msg["signature"]
    assert verify_message(msg, pub_a) is True
    # tamper -> invalid
    bad = json.loads(json.dumps(msg))
    bad["payload"] = "deadbeef"
    assert verify_message(bad, pub_a) is False
    # wrong pubkey -> invalid
    assert verify_message(msg, pub_b) is False


def test_compute_dir_sha_deterministic():
    d = tempfile.mkdtemp()
    try:
        os.makedirs(os.path.join(d, "sub"))
        with open(os.path.join(d, "a.txt"), "w") as f:
            f.write("alpha")
        with open(os.path.join(d, "sub", "b.txt"), "w") as f:
            f.write("beta")
        s1 = compute_dir_sha(d)
        s2 = compute_dir_sha(d)
        assert s1 == s2
        assert len(s1) == 64
        # content change -> different sha
        with open(os.path.join(d, "a.txt"), "w") as f:
            f.write("ALPHA")
        assert compute_dir_sha(d) != s1
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_identity_roundtrip():
    priv, pub = generate_keypair()
    ident = Identity(id="agent-x", private_key=priv, public_key=pub)
    d = tempfile.mkdtemp()
    try:
        p = save_identity(ident, d)
        assert os.path.exists(p)
        # disk file must NOT contain private key
        with open(p) as f:
            disk = json.load(f)
        assert "private_key" not in disk
        assert disk["public_key"] == pub
        loaded = load_identity("agent-x", d)
        assert loaded.id == "agent-x"
        assert loaded.public_key == pub
        assert loaded.private_key == ""
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_save_and_list_messages():
    priv_a, pub_a = generate_keypair()
    priv_b, pub_b = generate_keypair()
    repo = tempfile.mkdtemp()
    try:
        msg = build_message("agent-a", pub_b, b"x", "1" * 64, "2" * 64, priv_a)
        msg["to"] = "agent-b"
        p = save_message(msg, repo)
        assert os.path.exists(p)
        listed = list_messages(repo, "agent-b")
        assert len(listed) == 1
        assert listed[0]["id"] == msg["id"]
        assert list_messages(repo, "agent-c") == []
    finally:
        shutil.rmtree(repo, ignore_errors=True)