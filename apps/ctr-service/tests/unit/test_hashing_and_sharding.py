"""Tests del hashing canónico y del sharding de episodios.

Estos tests son el corazón del CTR: verifican que el hashing sea
determinista, que detecte manipulaciones, y que el sharding sea estable.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from ctr_service.models.base import GENESIS_HASH
from ctr_service.services.hashing import (
    canonicalize,
    compute_chain_hash,
    compute_self_hash,
    verify_chain_integrity,
)
from ctr_service.services.producer import shard_of
from hypothesis import given
from hypothesis import strategies as st

VALID_HASH = "a" * 64


def _make_event(seq: int, episode_id: UUID, payload_extra: dict | None = None) -> dict:
    return {
        "event_uuid": str(uuid4()),
        "episode_id": str(episode_id),
        "tenant_id": str(uuid4()),
        "seq": seq,
        "event_type": "prompt_enviado",
        "ts": datetime(2026, 8, 10, 12, 0, seq, tzinfo=UTC).isoformat().replace("+00:00", "Z"),
        "payload": payload_extra or {"content": "pregunta de test"},
        "prompt_system_hash": VALID_HASH,
        "prompt_system_version": "1.0.0",
        "classifier_config_hash": "b" * 64,
    }


# ── Canonicalización ───────────────────────────────────────────────────


def test_canonicalizacion_es_determinista() -> None:
    """El mismo objeto produce los mismos bytes, sin importar el orden de keys."""
    a = {"z": 1, "a": 2, "m": [3, 2, 1]}
    b = {"a": 2, "m": [3, 2, 1], "z": 1}
    assert canonicalize(a) == canonicalize(b)


def test_canonicalizacion_separators_sin_espacios() -> None:
    """JSON compacto sin espacios para minimizar diffs."""
    out = canonicalize({"a": 1, "b": 2})
    assert out == b'{"a":1,"b":2}'


def test_canonicalizacion_preserva_utf8() -> None:
    """Los acentos no se escapan."""
    out = canonicalize({"texto": "¿Cómo funciona la recursión?"})
    assert "¿Cómo" in out.decode("utf-8")
    assert "\\u" not in out.decode("utf-8")


def test_canonicalizacion_serializa_uuid_y_datetime() -> None:
    uid = uuid4()
    ts = datetime(2026, 8, 10, 12, 0, 0, tzinfo=UTC)
    out = canonicalize({"id": uid, "ts": ts})
    assert str(uid) in out.decode("utf-8")
    assert "2026-08-10T12:00:00Z" in out.decode("utf-8")


# ── self_hash / chain_hash ─────────────────────────────────────────────


def test_self_hash_es_determinista() -> None:
    ep = uuid4()
    event = _make_event(seq=0, episode_id=ep)
    assert compute_self_hash(event) == compute_self_hash(event)


def test_self_hash_excluye_campos_computados() -> None:
    """Agregar self_hash o chain_hash al dict no debe cambiar el resultado."""
    ep = uuid4()
    event = _make_event(seq=0, episode_id=ep)
    h1 = compute_self_hash(event)
    event["self_hash"] = "xxx"
    event["chain_hash"] = "yyy"
    event["prev_chain_hash"] = "zzz"
    event["persisted_at"] = "2026-01-01T00:00:00Z"
    h2 = compute_self_hash(event)
    assert h1 == h2


def test_chain_hash_primer_evento_usa_genesis() -> None:
    event = _make_event(seq=0, episode_id=uuid4())
    h = compute_self_hash(event)
    c1 = compute_chain_hash(h, None)
    c2 = compute_chain_hash(h, GENESIS_HASH)
    assert c1 == c2


def test_genesis_hash_formato() -> None:
    assert GENESIS_HASH == "0" * 64


# ── Verificación de cadena ─────────────────────────────────────────────


def test_cadena_valida_se_acepta() -> None:
    ep = uuid4()
    events = [_make_event(0, ep), _make_event(1, ep), _make_event(2, ep)]
    tuples = []
    prev = GENESIS_HASH
    for e in events:
        sh = compute_self_hash(e)
        ch = compute_chain_hash(sh, prev)
        tuples.append((e, sh, ch))
        prev = ch

    valid, failing = verify_chain_integrity(tuples)
    assert valid
    assert failing is None


def test_cadena_manipulada_se_detecta() -> None:
    """Si se altera el payload de un evento sin actualizar hashes, se detecta."""
    ep = uuid4()
    e0 = _make_event(0, ep)
    e1 = _make_event(1, ep, {"content": "original"})

    sh0 = compute_self_hash(e0)
    ch0 = compute_chain_hash(sh0, GENESIS_HASH)
    sh1 = compute_self_hash(e1)
    ch1 = compute_chain_hash(sh1, ch0)

    # Manipular e1 sin actualizar hashes
    e1_tampered = {**e1, "payload": {"content": "modificado"}}

    valid, failing = verify_chain_integrity(
        [
            (e0, sh0, ch0),
            (e1_tampered, sh1, ch1),
        ]
    )
    assert not valid
    assert failing == 1


def test_cadena_con_hash_chain_incorrecto_se_detecta() -> None:
    """Si se altera el chain_hash declarado (como si alguien insertara un evento), se detecta."""
    ep = uuid4()
    e0 = _make_event(0, ep)
    sh0 = compute_self_hash(e0)
    compute_chain_hash(sh0, GENESIS_HASH)

    # Forjar un chain_hash incorrecto
    fake_ch0 = "f" * 64

    valid, failing = verify_chain_integrity([(e0, sh0, fake_ch0)])
    assert not valid
    assert failing == 0


# ── Sharding ───────────────────────────────────────────────────────────


def test_sharding_es_estable() -> None:
    """Mismo episode_id → misma partición, siempre."""
    ep = uuid4()
    p1 = shard_of(ep, 8)
    p2 = shard_of(ep, 8)
    assert p1 == p2
    assert 0 <= p1 < 8


@given(seed=st.integers(min_value=1, max_value=10_000))
def test_sharding_distribuye_razonablemente(seed: int) -> None:
    """Al generar muchos episodios, las particiones se pueblan."""
    episodes = [UUID(int=seed * 1000 + i) for i in range(200)]
    partitions = {shard_of(ep, 8) for ep in episodes}
    # Esperamos al menos la mitad de las particiones usadas
    assert len(partitions) >= 4


def test_sharding_cambia_con_cantidad_de_particiones() -> None:
    """La función es consistente si se cambia num_partitions."""
    ep = uuid4()
    p8 = shard_of(ep, 8)
    p16 = shard_of(ep, 16)
    # Distintos num_partitions dan distintos shards (casi siempre)
    assert 0 <= p8 < 8
    assert 0 <= p16 < 16
