"""AES-GCM encryption helper compartido para el storage at-rest de BYOK.

ADR-038 (Sec 5 epic ai-native-completion-and-byok): las API keys de BYOK se
persisten encriptadas en `byok_keys.encrypted_value` con AES-256-GCM. La
master key vive como env var `BYOK_MASTER_KEY` (32 bytes base64) en el pod
del ai-gateway. Rotacion procedural via runbook (no automatica).

API:
    encrypted = encrypt(plaintext_bytes, master_key)
    plaintext = decrypt(encrypted, master_key)

Implementacion:
- AES-GCM provee confidencialidad + integridad (AEAD): tampering del
  ciphertext lanza `cryptography.exceptions.InvalidTag` al decrypt.
- Nonce de 12 bytes generado fresh por encryption (reuso de nonce con
  misma key compromete catastroficamente AES-GCM).
- Output binario empaquetado: `nonce (12) || ciphertext_with_tag` —
  estructura plana, facil de almacenar como BYTEA en Postgres.

NO loguea plaintext ni la master key. Si necesitas debug, hashea con
sha256 los bytes y comparti el hash, NO el valor.
"""

from __future__ import annotations

import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

NONCE_SIZE = 12  # AES-GCM standard
MASTER_KEY_SIZE = 32  # AES-256


class CryptoError(Exception):
    """Error de la API publica de este modulo (wraps InvalidTag, ValueError)."""


def encrypt(plaintext: bytes, master_key: bytes) -> bytes:
    """Encripta `plaintext` con `master_key`. Devuelve `nonce || ciphertext+tag`.

    El nonce se genera fresh cada vez (12 bytes random). Reusarlo con la
    misma master_key destruye la seguridad de AES-GCM.
    """
    if len(master_key) != MASTER_KEY_SIZE:
        raise CryptoError(
            f"master_key debe ser exactamente {MASTER_KEY_SIZE} bytes "
            f"(recibido {len(master_key)} bytes). "
            f"Generar con: os.urandom({MASTER_KEY_SIZE}) o openssl rand 32"
        )
    if not isinstance(plaintext, bytes):
        raise CryptoError(f"plaintext debe ser bytes, recibido {type(plaintext).__name__}")

    aesgcm = AESGCM(master_key)
    nonce = os.urandom(NONCE_SIZE)
    ct_with_tag = aesgcm.encrypt(nonce, plaintext, associated_data=None)
    return nonce + ct_with_tag


def decrypt(encrypted: bytes, master_key: bytes) -> bytes:
    """Inverso de `encrypt`. Lanza `CryptoError` ante tampering o key incorrecta.

    Espera `encrypted` con el formato `nonce (12) || ciphertext+tag` que
    produce `encrypt`. Si los bytes fueron alterados o la master_key no
    coincide, AES-GCM lanza `InvalidTag` y lo convertimos a `CryptoError`.
    """
    if len(master_key) != MASTER_KEY_SIZE:
        raise CryptoError(
            f"master_key debe ser exactamente {MASTER_KEY_SIZE} bytes "
            f"(recibido {len(master_key)} bytes)"
        )
    if not isinstance(encrypted, bytes):
        raise CryptoError(f"encrypted debe ser bytes, recibido {type(encrypted).__name__}")
    if len(encrypted) < NONCE_SIZE + 16:
        # 16 bytes es el tag GCM minimo
        raise CryptoError(
            f"encrypted demasiado corto ({len(encrypted)} bytes); minimo {NONCE_SIZE + 16}"
        )

    nonce = encrypted[:NONCE_SIZE]
    ct_with_tag = encrypted[NONCE_SIZE:]
    aesgcm = AESGCM(master_key)
    try:
        return aesgcm.decrypt(nonce, ct_with_tag, associated_data=None)
    except Exception as exc:  # cryptography.exceptions.InvalidTag y similares
        # NO incluir master_key ni ciphertext en el mensaje del error
        raise CryptoError("Decryption fallo: tampering detectado o master key incorrecta") from exc


def generate_master_key() -> bytes:
    """Genera 32 bytes random para usar como master key.

    En produccion: usar `openssl rand -base64 32` y guardar como env var.
    Esta funcion existe para tests y bootstrap inicial.
    """
    return os.urandom(MASTER_KEY_SIZE)
