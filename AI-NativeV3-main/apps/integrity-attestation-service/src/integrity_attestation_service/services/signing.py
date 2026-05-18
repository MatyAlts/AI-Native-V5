"""Firma Ed25519 + buffer canonico para attestations (ADR-021).

Buffer canonico bit-exact (NO se modifica sin bumpear SCHEMA_VERSION):

    canonical = f"{episode_id}|{tenant_id}|{final_chain_hash}|{total_events}|{ts_episode_closed}|{schema_version}".encode("utf-8")

Reglas criticas:
- Separador: `|` (U+007C, sin espacios).
- Orden de campos FIJO (no alfabetico).
- `episode_id` y `tenant_id`: lowercase UUID con dashes.
- `final_chain_hash`: 64 hex chars lowercase.
- `total_events`: int decimal sin separadores.
- `ts_episode_closed`: ISO-8601 UTC con sufijo `Z` (no `+00:00`).
- `schema_version`: literal "1.0.0" en v1.
- Encoding: UTF-8 (ASCII puro en este caso).
- `ts_attested` NO entra en el buffer (es metadata, no firmable).

Cualquier desviacion ROMPE la verificacion. Test bit-exact en `test_signing.py`.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from uuid import UUID

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

SCHEMA_VERSION = "1.0.0"

# `signer_pubkey_id` de la dev key. Hardcodeado para failsafe en production.
# Calculado de `dev-public.pem` regenerada con seed `AI-NativeV3-DEV-ATTESTATION-KEY1`.
# Si cambia el seed, este valor debe actualizarse junto con los tests golden.
DEV_PUBKEY_ID = "26f7cf0749b5"  # golden, verificado por test_dev_pubkey_id_es_estable


_FINAL_CHAIN_HASH_LEN = 64


class DevKeyInProductionError(RuntimeError):
    """Failsafe: deploy con dev key en environment=production."""


def compute_canonical_buffer(
    episode_id: UUID | str,
    tenant_id: UUID | str,
    final_chain_hash: str,
    total_events: int,
    ts_episode_closed: str,
    schema_version: str = SCHEMA_VERSION,
) -> bytes:
    """Construye el buffer canonico bit-exact para firma."""
    if not isinstance(final_chain_hash, str) or len(final_chain_hash) != _FINAL_CHAIN_HASH_LEN:
        raise ValueError(f"final_chain_hash must be {_FINAL_CHAIN_HASH_LEN} chars hex")
    if any(c not in "0123456789abcdef" for c in final_chain_hash):
        raise ValueError("final_chain_hash must be lowercase hex")
    if total_events < 1:
        raise ValueError("total_events must be >= 1")
    if not isinstance(ts_episode_closed, str) or not ts_episode_closed.endswith("Z"):
        raise ValueError("ts_episode_closed must be ISO-8601 UTC ending with 'Z'")

    ep_str = str(episode_id).lower()
    tn_str = str(tenant_id).lower()

    canonical = (
        f"{ep_str}|{tn_str}|{final_chain_hash}|{total_events}|{ts_episode_closed}|{schema_version}"
    )
    return canonical.encode("utf-8")


def sign_buffer(private_key: Ed25519PrivateKey, canonical: bytes) -> str:
    """Firma el buffer canonico. Devuelve la firma como 128 hex chars (lowercase)."""
    signature = private_key.sign(canonical)
    return signature.hex()


def verify_buffer(public_key: Ed25519PublicKey, canonical: bytes, signature_hex: str) -> bool:
    """Verifica una firma. Devuelve True si valida, False si falla."""
    try:
        public_key.verify(bytes.fromhex(signature_hex), canonical)
    except Exception:  # InvalidSignature, ValueError de hex invalido, etc.
        return False
    return True


def compute_signer_pubkey_id(public_key: Ed25519PublicKey) -> str:
    """SHA-256[:12] de los bytes raw de la pubkey (32 bytes Ed25519).

    No es secreto. Usado para identificar que clave firmo cada attestation,
    permitiendo rotacion: el log queda con el pubkey_id viejo, el verificador
    busca la pubkey correspondiente en su llavero.
    """
    raw = public_key.public_bytes(encoding=Encoding.Raw, format=PublicFormat.Raw)
    return hashlib.sha256(raw).hexdigest()[:12]


def load_private_key(path: Path) -> Ed25519PrivateKey:
    """Carga clave privada Ed25519 desde PEM (PKCS8, sin password)."""
    pem = path.read_bytes()
    key = serialization.load_pem_private_key(pem, password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise TypeError(f"Expected Ed25519PrivateKey, got {type(key).__name__}")
    return key


def load_public_key(path: Path) -> Ed25519PublicKey:
    """Carga clave publica Ed25519 desde PEM."""
    pem = path.read_bytes()
    key = serialization.load_pem_public_key(pem)
    if not isinstance(key, Ed25519PublicKey):
        raise TypeError(f"Expected Ed25519PublicKey, got {type(key).__name__}")
    return key


def load_keypair_with_failsafe(
    private_path: Path,
    public_path: Path,
    environment: str,
) -> tuple[Ed25519PrivateKey, Ed25519PublicKey, str]:
    """Carga el keypair y aplica failsafe contra deploy con dev key en produccion.

    Devuelve (private_key, public_key, signer_pubkey_id).

    Raises:
        DevKeyInProductionError: si environment=='production' y la pubkey
            activa coincide con la dev key conocida (DEV_PUBKEY_ID).
    """
    private_key = load_private_key(private_path)
    public_key = load_public_key(public_path)
    pubkey_id = compute_signer_pubkey_id(public_key)

    if environment == "production" and pubkey_id == DEV_PUBKEY_ID:
        raise DevKeyInProductionError(
            f"Refusing to start: dev key (pubkey_id={pubkey_id}) detected with "
            f"environment=production. Set ATTESTATION_PRIVATE_KEY_PATH and "
            f"ATTESTATION_PUBLIC_KEY_PATH to institutional keys."
        )

    return private_key, public_key, pubkey_id
