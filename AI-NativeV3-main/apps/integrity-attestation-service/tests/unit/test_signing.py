"""Tests del modulo signing (ADR-021).

Tests bit-exact del buffer canonico + firma Ed25519 + failsafe production.
Estos tests son la red de seguridad para que cualquier reimplementacion
(otro lenguaje, otra version del servicio) produzca firmas COMPATIBLES con
las del piloto.
"""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

import pytest
from integrity_attestation_service.services.signing import (
    DEV_PUBKEY_ID,
    SCHEMA_VERSION,
    DevKeyInProductionError,
    compute_canonical_buffer,
    compute_signer_pubkey_id,
    load_keypair_with_failsafe,
    load_private_key,
    load_public_key,
    sign_buffer,
    verify_buffer,
)

# Paths a las dev keys (las del repo, regeneradas con seed `AI-NativeV3-DEV-ATTESTATION-KEY1`)
_SERVICE_ROOT = Path(__file__).resolve().parent.parent.parent
_DEV_PRIVATE = _SERVICE_ROOT / "dev-keys" / "dev-private.pem"
_DEV_PUBLIC = _SERVICE_ROOT / "dev-keys" / "dev-public.pem"


# Caso golden — input conocido, output bit-exact.
_GOLDEN_EPISODE = "11111111-2222-3333-4444-555555555555"
_GOLDEN_TENANT = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
_GOLDEN_HASH = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
_GOLDEN_TOTAL = 42
_GOLDEN_TS = "2026-04-27T10:30:00Z"
_GOLDEN_BUFFER = (
    b"11111111-2222-3333-4444-555555555555|"
    b"aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee|"
    b"0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef|"
    b"42|"
    b"2026-04-27T10:30:00Z|"
    b"1.0.0"
)
_GOLDEN_BUFFER_LEN = 168
_GOLDEN_SIGNATURE = (
    "6333bee99497b90645662e4ea46589a5358eb05d1354e54b8e932f8a875f0c29"
    "314b0af3727eda0cadea072eea5e5e04c4dc25cdd94b77e51398c17546ad1606"
)


# ---------------------------------------------------------------------------
# Buffer canonico
# ---------------------------------------------------------------------------


def test_buffer_canonico_es_bit_exact_para_caso_golden() -> None:
    """El buffer canonico es la base de TODA verificacion. Cualquier cambio
    en orden de campos, separadores, o formato de timestamp rompe verificacion
    contra logs historicos del piloto."""
    buf = compute_canonical_buffer(
        episode_id=_GOLDEN_EPISODE,
        tenant_id=_GOLDEN_TENANT,
        final_chain_hash=_GOLDEN_HASH,
        total_events=_GOLDEN_TOTAL,
        ts_episode_closed=_GOLDEN_TS,
    )
    assert buf == _GOLDEN_BUFFER
    assert len(buf) == _GOLDEN_BUFFER_LEN


def test_buffer_canonico_acepta_uuid_object_y_string_indistintamente() -> None:
    """`str(UUID)` y la string directa producen el mismo buffer."""
    from_str = compute_canonical_buffer(
        episode_id=_GOLDEN_EPISODE,
        tenant_id=_GOLDEN_TENANT,
        final_chain_hash=_GOLDEN_HASH,
        total_events=_GOLDEN_TOTAL,
        ts_episode_closed=_GOLDEN_TS,
    )
    from_uuid = compute_canonical_buffer(
        episode_id=UUID(_GOLDEN_EPISODE),
        tenant_id=UUID(_GOLDEN_TENANT),
        final_chain_hash=_GOLDEN_HASH,
        total_events=_GOLDEN_TOTAL,
        ts_episode_closed=_GOLDEN_TS,
    )
    assert from_str == from_uuid


def test_buffer_canonico_normaliza_uuid_a_lowercase() -> None:
    """UUIDs con uppercase de input → buffer con lowercase. Defensa contra
    inconsistencias de serializacion entre clientes."""
    buf = compute_canonical_buffer(
        episode_id=_GOLDEN_EPISODE.upper(),
        tenant_id=_GOLDEN_TENANT.upper(),
        final_chain_hash=_GOLDEN_HASH,
        total_events=_GOLDEN_TOTAL,
        ts_episode_closed=_GOLDEN_TS,
    )
    assert buf == _GOLDEN_BUFFER


def test_buffer_canonico_falla_con_hash_largo_incorrecto() -> None:
    with pytest.raises(ValueError, match="64 chars"):
        compute_canonical_buffer(
            episode_id=_GOLDEN_EPISODE,
            tenant_id=_GOLDEN_TENANT,
            final_chain_hash="abc",  # too short
            total_events=_GOLDEN_TOTAL,
            ts_episode_closed=_GOLDEN_TS,
        )


def test_buffer_canonico_falla_con_hash_uppercase() -> None:
    """Hash debe ser lowercase hex — coherente con CTR self_hash y chain_hash."""
    upper_hash = _GOLDEN_HASH.upper()
    with pytest.raises(ValueError, match="lowercase hex"):
        compute_canonical_buffer(
            episode_id=_GOLDEN_EPISODE,
            tenant_id=_GOLDEN_TENANT,
            final_chain_hash=upper_hash,
            total_events=_GOLDEN_TOTAL,
            ts_episode_closed=_GOLDEN_TS,
        )


def test_buffer_canonico_falla_con_total_events_cero() -> None:
    """Episodio cerrado tiene al menos 1 evento (el `episodio_cerrado` mismo)."""
    with pytest.raises(ValueError, match="total_events"):
        compute_canonical_buffer(
            episode_id=_GOLDEN_EPISODE,
            tenant_id=_GOLDEN_TENANT,
            final_chain_hash=_GOLDEN_HASH,
            total_events=0,
            ts_episode_closed=_GOLDEN_TS,
        )


def test_buffer_canonico_falla_con_ts_sin_sufijo_z() -> None:
    """`ts_episode_closed` debe terminar en Z, no `+00:00`. Coherente con el
    formato del CTR (`event.ts.isoformat().replace('+00:00', 'Z')`)."""
    with pytest.raises(ValueError, match="ending with 'Z'"):
        compute_canonical_buffer(
            episode_id=_GOLDEN_EPISODE,
            tenant_id=_GOLDEN_TENANT,
            final_chain_hash=_GOLDEN_HASH,
            total_events=_GOLDEN_TOTAL,
            ts_episode_closed="2026-04-27T10:30:00+00:00",
        )


def test_schema_version_es_la_v1_documentada_en_adr() -> None:
    """Si bumpea, hay que documentar el ADR sucesor + actualizar este test."""
    assert SCHEMA_VERSION == "1.0.0"


# ---------------------------------------------------------------------------
# Firma + verificacion
# ---------------------------------------------------------------------------


def test_firma_golden_es_bit_exact() -> None:
    """Ed25519 es deterministico (RFC 8032): mismo (priv_key, msg) → misma firma.
    Si este test falla, alguien rompio: la dev key, el buffer canonico, o el
    algoritmo de firma. Cualquiera de los tres es un BC-break grave."""
    priv = load_private_key(_DEV_PRIVATE)
    buf = compute_canonical_buffer(
        episode_id=_GOLDEN_EPISODE,
        tenant_id=_GOLDEN_TENANT,
        final_chain_hash=_GOLDEN_HASH,
        total_events=_GOLDEN_TOTAL,
        ts_episode_closed=_GOLDEN_TS,
    )
    sig = sign_buffer(priv, buf)
    assert sig == _GOLDEN_SIGNATURE
    assert len(sig) == 128  # 64 bytes en hex


def test_verify_roundtrip_ok() -> None:
    """Firma producida por sign() debe validar con verify() y la pubkey correspondiente."""
    priv = load_private_key(_DEV_PRIVATE)
    pub = load_public_key(_DEV_PUBLIC)
    buf = b"hello-world-bytes"
    sig = sign_buffer(priv, buf)
    assert verify_buffer(pub, buf, sig) is True


def test_verify_falla_con_firma_alterada() -> None:
    pub = load_public_key(_DEV_PUBLIC)
    # Tomamos la firma golden y le cambiamos un caracter — sigue siendo hex valido pero firma otro msg
    tampered = "0" + _GOLDEN_SIGNATURE[1:]
    assert verify_buffer(pub, _GOLDEN_BUFFER, tampered) is False


def test_verify_falla_con_buffer_alterado() -> None:
    """Si un atacante reemplaza el buffer (ej. cambia final_chain_hash), la firma vieja no valida."""
    pub = load_public_key(_DEV_PUBLIC)
    tampered_buffer = _GOLDEN_BUFFER.replace(b"42", b"43")
    assert verify_buffer(pub, tampered_buffer, _GOLDEN_SIGNATURE) is False


def test_verify_falla_con_signature_no_hex() -> None:
    """Defensa contra input invalido (corrupcion del JSONL, etc.)."""
    pub = load_public_key(_DEV_PUBLIC)
    assert verify_buffer(pub, _GOLDEN_BUFFER, "not-hex-at-all") is False


def test_firma_es_deterministica() -> None:
    """Dos llamadas a sign() con mismo input dan misma firma."""
    priv = load_private_key(_DEV_PRIVATE)
    buf = b"test-determinism"
    assert sign_buffer(priv, buf) == sign_buffer(priv, buf)


# ---------------------------------------------------------------------------
# Pubkey id
# ---------------------------------------------------------------------------


def test_dev_pubkey_id_es_estable() -> None:
    """Si esto falla, alguien regenero las dev keys con un seed distinto.
    Hay que actualizar DEV_PUBKEY_ID en signing.py + tests dependientes."""
    pub = load_public_key(_DEV_PUBLIC)
    assert compute_signer_pubkey_id(pub) == DEV_PUBKEY_ID


def test_signer_pubkey_id_tiene_12_hex_chars() -> None:
    pub = load_public_key(_DEV_PUBLIC)
    pubkey_id = compute_signer_pubkey_id(pub)
    assert len(pubkey_id) == 12
    assert all(c in "0123456789abcdef" for c in pubkey_id)


# ---------------------------------------------------------------------------
# Failsafe contra deploy con dev key en produccion
# ---------------------------------------------------------------------------


def test_load_keypair_failsafe_dev_key_en_dev_es_ok() -> None:
    priv, pub, pubkey_id = load_keypair_with_failsafe(
        private_path=_DEV_PRIVATE,
        public_path=_DEV_PUBLIC,
        environment="development",
    )
    assert pubkey_id == DEV_PUBKEY_ID
    assert priv is not None
    assert pub is not None


def test_load_keypair_failsafe_dev_key_en_production_falla() -> None:
    """Defensa contra deploy accidental del dev key en piloto UNSL."""
    with pytest.raises(DevKeyInProductionError, match="dev key"):
        load_keypair_with_failsafe(
            private_path=_DEV_PRIVATE,
            public_path=_DEV_PUBLIC,
            environment="production",
        )


def test_load_private_key_falla_con_archivo_inexistente() -> None:
    with pytest.raises(FileNotFoundError):
        load_private_key(Path("/nonexistent/path/key.pem"))
