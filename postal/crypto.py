"""Postal crypto primitives: ECDSA P-256 signing + ECDH+AES-256-GCM encryption."""
from __future__ import annotations

import os
import json
import base64
from typing import Dict

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.exceptions import InvalidSignature, InvalidKey


def generate_keypair() -> tuple[str, str]:
    """Generate an ECDSA P-256 keypair.

    Returns:
        (private_key_pem_hex, public_key_pem_hex)
    """
    priv = ec.generate_private_key(ec.SECP256R1())
    pub = priv.public_key()
    priv_pem = priv.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    pub_pem = pub.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return priv_pem.hex(), pub_pem.hex()


def _load_private(priv_hex: str):
    return serialization.load_pem_private_key(bytes.fromhex(priv_hex), password=None)


def _load_public(pub_hex: str):
    return serialization.load_pem_public_key(bytes.fromhex(pub_hex))


def sign(private_key: str, message_bytes: bytes) -> str:
    """Sign message_bytes with ECDSA P-256 -> signature_hex (DER)."""
    priv = _load_private(private_key)
    sig = priv.sign(message_bytes, ec.ECDSA(hashes.SHA256()))
    return sig.hex()


def verify(public_key: str, message_bytes: bytes, signature_hex: str) -> bool:
    """Verify signature_hex over message_bytes with public_key. Returns bool."""
    try:
        pub = _load_public(public_key)
        pub.verify(bytes.fromhex(signature_hex), message_bytes, ec.ECDSA(hashes.SHA256()))
        return True
    except (InvalidSignature, InvalidKey, ValueError, Exception):
        return False


def _derive_shared_key(priv, peer_pub) -> bytes:
    """ECDH -> HKDF-SHA256 -> 32-byte AES key."""
    shared = priv.exchange(ec.ECDH(), peer_pub)
    return HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=b"postal-ecdh-aes256gcm",
    ).derive(shared)


def encrypt(recipient_pubkey: str, plaintext_bytes: bytes) -> Dict[str, str]:
    """ECDH + AES-256-GCM.

    Returns: {'ciphertext_hex', 'ephemeral_pubkey_hex'}
    Ciphertext includes the 12-byte nonce prefix (IV) as required by AESGCM.
    """
    recipient_pub = _load_public(recipient_pubkey)
    ephemeral_priv = ec.generate_private_key(ec.SECP256R1())
    ephemeral_pub_pem = ephemeral_priv.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    key = _derive_shared_key(ephemeral_priv, recipient_pub)
    nonce = os.urandom(12)
    aesgcm = AESGCM(key)
    ct = aesgcm.encrypt(nonce, plaintext_bytes, None)
    return {
        "ciphertext_hex": (nonce + ct).hex(),
        "ephemeral_pubkey_hex": ephemeral_pub_pem.hex(),
    }


def decrypt(private_key: str, ciphertext_hex: str, ephemeral_pubkey_hex: str) -> bytes:
    """Decrypt ciphertext_hex (nonce||ct) using ECDH with ephemeral pubkey."""
    priv = _load_private(private_key)
    ephemeral_pub = _load_public(ephemeral_pubkey_hex)
    key = _derive_shared_key(priv, ephemeral_pub)
    blob = bytes.fromhex(ciphertext_hex)
    nonce, ct = blob[:12], blob[12:]
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(nonce, ct, None)