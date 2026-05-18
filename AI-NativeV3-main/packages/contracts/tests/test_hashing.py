"""Tests del hashing del CTR.

Verifica las propiedades críticas:
1. El hash es determinista
2. Cambiar un byte del evento cambia el hash
3. La cadena detecta manipulaciones
4. El génesis funciona correctamente
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from hypothesis import given
from hypothesis import strategies as st
from platform_contracts.ctr import (
    GENESIS_HASH,
    EpisodioAbierto,
    PromptEnviado,
    compute_chain_hash,
    compute_self_hash,
    verify_chain_integrity,
)
from platform_contracts.ctr.events import (
    EpisodioAbiertoPayload,
    PromptEnviadoPayload,
)

VALID_HASH = "a" * 64


def _make_episodio_abierto(episode_id: UUID, seq: int = 0) -> EpisodioAbierto:
    return EpisodioAbierto(
        event_uuid=uuid4(),
        episode_id=episode_id,
        tenant_id=uuid4(),
        seq=seq,
        ts=datetime(2026, 4, 20, 12, 0, 0, tzinfo=UTC),
        prompt_system_hash=VALID_HASH,
        prompt_system_version="1.0.0",
        classifier_config_hash=VALID_HASH,
        payload=EpisodioAbiertoPayload(
            student_pseudonym=uuid4(),
            problema_id=uuid4(),
            comision_id=uuid4(),
            curso_config_hash=VALID_HASH,
        ),
    )


def test_self_hash_is_deterministic() -> None:
    """Mismo evento → mismo hash, siempre."""
    event = _make_episodio_abierto(uuid4())
    h1 = compute_self_hash(event)
    h2 = compute_self_hash(event)
    assert h1 == h2
    assert len(h1) == 64
    assert all(c in "0123456789abcdef" for c in h1)


def test_self_hash_changes_with_payload() -> None:
    """Cambiar el payload cambia el hash."""
    event1 = _make_episodio_abierto(uuid4())
    event2 = event1.model_copy(
        update={"payload": event1.payload.model_copy(update={"curso_config_hash": "b" * 64})}
    )
    assert compute_self_hash(event1) != compute_self_hash(event2)


def test_chain_hash_uses_genesis_for_first() -> None:
    """El primer evento del episodio usa el génesis como prev."""
    event = _make_episodio_abierto(uuid4())
    self_h = compute_self_hash(event)
    chain_h = compute_chain_hash(self_h, None)

    # Mismo resultado que pasando GENESIS_HASH explícito
    assert chain_h == compute_chain_hash(self_h, GENESIS_HASH)


def test_chain_detects_manipulation() -> None:
    """Reordenar o modificar eventos rompe la cadena."""
    ep_id = uuid4()
    e0 = _make_episodio_abierto(ep_id, seq=0)
    e1 = PromptEnviado(
        event_uuid=uuid4(),
        episode_id=ep_id,
        tenant_id=e0.tenant_id,
        seq=1,
        ts=datetime(2026, 4, 20, 12, 0, 30, tzinfo=UTC),
        prompt_system_hash=VALID_HASH,
        prompt_system_version="1.0.0",
        classifier_config_hash=VALID_HASH,
        payload=PromptEnviadoPayload(
            content="¿Cómo enfoco este problema?",
            prompt_kind="epistemologica",
            chunks_used_hash=None,
        ),
    )

    self_0 = compute_self_hash(e0)
    chain_0 = compute_chain_hash(self_0, None)
    self_1 = compute_self_hash(e1)
    chain_1 = compute_chain_hash(self_1, chain_0)

    # Cadena íntegra
    valid, failing = verify_chain_integrity([(e0, self_0, chain_0), (e1, self_1, chain_1)])
    assert valid is True
    assert failing is None

    # Ahora manipulamos: cambiamos el payload de e1 pero dejamos los hashes viejos
    e1_tampered = e1.model_copy(
        update={"payload": e1.payload.model_copy(update={"content": "Resolvéme todo"})}
    )
    valid, failing = verify_chain_integrity([(e0, self_0, chain_0), (e1_tampered, self_1, chain_1)])
    assert valid is False
    assert failing == 1


def test_chain_detects_reordering() -> None:
    """Cambiar el orden de eventos rompe la verificación."""
    ep_id = uuid4()
    e0 = _make_episodio_abierto(ep_id, seq=0)
    self_0 = compute_self_hash(e0)
    chain_0 = compute_chain_hash(self_0, None)

    # Si alguien intenta hacer pasar al e0 como segundo evento de una cadena inventada,
    # el chain_hash no cuadra
    fake_prev = "f" * 64
    fake_chain = compute_chain_hash(self_0, fake_prev)
    assert fake_chain != chain_0


@given(payload_text=st.text(min_size=1, max_size=1000))
def test_any_payload_change_changes_hash(payload_text: str) -> None:
    """Property test: cualquier cambio textual en el payload cambia el hash."""
    ep_id = uuid4()
    e = PromptEnviado(
        event_uuid=uuid4(),
        episode_id=ep_id,
        tenant_id=uuid4(),
        seq=0,
        ts=datetime(2026, 4, 20, 12, 0, 0, tzinfo=UTC),
        prompt_system_hash=VALID_HASH,
        prompt_system_version="1.0.0",
        classifier_config_hash=VALID_HASH,
        payload=PromptEnviadoPayload(
            content=payload_text,
            prompt_kind="solicitud_directa",
            chunks_used_hash=None,
        ),
    )
    h1 = compute_self_hash(e)
    e_modified = e.model_copy(
        update={"payload": e.payload.model_copy(update={"content": payload_text + "x"})}
    )
    h2 = compute_self_hash(e_modified)
    assert h1 != h2


def test_genesis_hash_format() -> None:
    """El génesis es 64 ceros hexa (0x00... 32 bytes)."""
    assert GENESIS_HASH == "0" * 64
    assert len(GENESIS_HASH) == 64
