"""Tests de crypto.py (ADR-038).

Cubre:
  - Round-trip encrypt/decrypt: plaintext == decrypt(encrypt(plaintext, key), key)
  - Tampering del ciphertext: flip de un byte lanza CryptoError
  - Master key incorrecta: lanza CryptoError
  - Nonce fresh por encryption: dos encrypts del mismo plaintext producen
    ciphertexts distintos
  - Master key de tamano incorrecto rechazado
  - Plaintext no-bytes rechazado
  - El helper NO loguea plaintext ni master key (capsys check)
"""

from __future__ import annotations

import logging
from io import StringIO

import pytest
from platform_ops.crypto import (
    CryptoError,
    decrypt,
    encrypt,
    generate_master_key,
)


def test_round_trip_encrypt_decrypt() -> None:
    """plaintext == decrypt(encrypt(plaintext, key), key)."""
    master_key = generate_master_key()
    plaintext = b"sk-ant-api03-AAAA1234567890ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    encrypted = encrypt(plaintext, master_key)
    decrypted = decrypt(encrypted, master_key)
    assert decrypted == plaintext


def test_round_trip_con_plaintext_vacio() -> None:
    """encrypt acepta bytes vacios (caso degenerado)."""
    master_key = generate_master_key()
    encrypted = encrypt(b"", master_key)
    assert decrypt(encrypted, master_key) == b""


def test_tampering_del_ciphertext_lanza_crypto_error() -> None:
    """Flip de un byte en el ciphertext detectado por la auth tag."""
    master_key = generate_master_key()
    plaintext = b"secret-api-key-do-not-reveal"
    encrypted = encrypt(plaintext, master_key)

    # Flip el ultimo byte (parte del auth tag)
    tampered = bytearray(encrypted)
    tampered[-1] ^= 0x01
    with pytest.raises(CryptoError, match="tampering detectado"):
        decrypt(bytes(tampered), master_key)


def test_master_key_incorrecta_lanza_crypto_error() -> None:
    """Decrypt con key distinta a la usada en encrypt => CryptoError."""
    key_a = generate_master_key()
    key_b = generate_master_key()
    encrypted = encrypt(b"plaintext", key_a)
    with pytest.raises(CryptoError, match="tampering detectado o master key incorrecta"):
        decrypt(encrypted, key_b)


def test_nonce_fresh_dos_encrypts_distintos() -> None:
    """Dos encrypts del mismo plaintext con la misma key NO producen el mismo
    ciphertext (cada encrypt usa nonce random nuevo)."""
    master_key = generate_master_key()
    plaintext = b"same-input-twice"
    enc1 = encrypt(plaintext, master_key)
    enc2 = encrypt(plaintext, master_key)
    assert enc1 != enc2
    # Ambos decryptan al mismo plaintext
    assert decrypt(enc1, master_key) == plaintext
    assert decrypt(enc2, master_key) == plaintext


def test_master_key_demasiado_corta_rechazada() -> None:
    with pytest.raises(CryptoError, match="exactamente 32 bytes"):
        encrypt(b"plaintext", b"x" * 16)
    with pytest.raises(CryptoError, match="exactamente 32 bytes"):
        decrypt(b"x" * 50, b"x" * 16)


def test_master_key_demasiado_larga_rechazada() -> None:
    with pytest.raises(CryptoError, match="exactamente 32 bytes"):
        encrypt(b"plaintext", b"x" * 64)


def test_plaintext_no_bytes_rechazado() -> None:
    master_key = generate_master_key()
    with pytest.raises(CryptoError, match="plaintext debe ser bytes"):
        encrypt("string-en-vez-de-bytes", master_key)  # type: ignore[arg-type]


def test_encrypted_demasiado_corto_rechazado() -> None:
    """Bytes < nonce+tag minimo => CryptoError sin pegar a AESGCM."""
    master_key = generate_master_key()
    with pytest.raises(CryptoError, match="demasiado corto"):
        decrypt(b"x" * 10, master_key)


def test_helper_no_loguea_plaintext_ni_master_key() -> None:
    """Defensa critica de privacidad: el modulo no debe escribir secrets a logs.

    Capturamos cualquier log que el modulo pudiera emitir y verificamos que
    no contiene los bytes secretos. Forzamos un error de tampering para
    asegurarnos de que el path de error tampoco lee.
    """
    sink = StringIO()
    handler = logging.StreamHandler(sink)
    handler.setLevel(logging.DEBUG)
    crypto_logger = logging.getLogger("platform_ops.crypto")
    root_logger = logging.getLogger()
    crypto_logger.addHandler(handler)
    root_logger.addHandler(handler)
    crypto_logger.setLevel(logging.DEBUG)
    root_logger.setLevel(logging.DEBUG)

    try:
        master_key = generate_master_key()
        plaintext = b"SUPERSECRET-DO-NOT-LEAK-XYZ"
        encrypted = encrypt(plaintext, master_key)
        decrypt(encrypted, master_key)

        # Forzar error de tampering
        tampered = bytearray(encrypted)
        tampered[-1] ^= 0xFF
        try:
            decrypt(bytes(tampered), master_key)
        except CryptoError:
            pass

        log_contents = sink.getvalue()
        assert b"SUPERSECRET" not in log_contents.encode()
        assert "SUPERSECRET" not in log_contents
        # Tampoco la master key (cualquier byte de ella en hex)
        assert master_key.hex() not in log_contents
    finally:
        crypto_logger.removeHandler(handler)
        root_logger.removeHandler(handler)
