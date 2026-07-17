"""Atomicidad del contador de seq por episodio (FIX A — keystone).

El invariante duro de la cadena CTR es que el seq por episodio sea CONTIGUO y
sin huecos (el partition_worker valida `expected_seq == events_count`). Antes
del fix, `next_seq()` era un read-modify-write sobre el JSON de sesion
(`current = state.seq; state.seq += 1; set()`), NO atomico: dos coroutines
concurrentes sobre el mismo episodio leian el MISMO `state.seq` y reservaban el
MISMO seq → dos eventos con igual seq → hueco → dead-letter →
`integrity_compromised` PERMANENTE.

Estos tests corren a nivel SessionManager con fakeredis. El de eventos DISTINTOS
usa SOLO get/set/next_seq (metodos presentes antes y despues del fix), asi que
es portable: FALLA sin el fix (ambos devuelven el mismo seq) y PASA con el
(INCR atomico → seqs distintos y contiguos).
"""

from __future__ import annotations

import asyncio
from uuid import uuid4

import fakeredis.aioredis
import pytest
from tutor_service.services.session import (
    SeqReservationPendingError,
    SessionManager,
    SessionState,
)


@pytest.fixture
async def redis_client():
    client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    yield client
    await client.aclose()


def _make_state(episode_id):
    return SessionState(
        episode_id=episode_id,
        tenant_id=uuid4(),
        comision_id=uuid4(),
        student_pseudonym=uuid4(),
        seq=0,
        messages=[{"role": "system", "content": "prompt base"}],
        prompt_system_hash="a" * 64,
        prompt_system_version="v1.0.0",
        classifier_config_hash="b" * 64,
        curso_config_hash="c" * 64,
    )


async def test_dos_eventos_distintos_concurrentes_seqs_distintos_contiguos(redis_client):
    """QA keystone: dos eventos DISTINTOS concurrentes (asyncio.gather) sobre el
    mismo episodio reservan seqs DISTINTOS y CONTIGUOS.

    IMPORTANTE — reproduccion honesta de la race: fakeredis resuelve los awaits
    sin ceder al event loop, asi que un `gather` ingenuo correria las coroutines
    en serie y la race NUNCA se interleaveria (el `next_seq` viejo pasaria por
    accidente). Forzamos con un barrier a que AMBAS coroutines hagan su
    `get()` (leer state.seq=0) ANTES de que cualquiera reserve — que es
    exactamente el escenario real: dos requests cargaron el estado antes de que
    el primero avanzara el contador.

    Sin el fix (read-modify-write) ambas leen state.seq=0 y devuelven 0 →
    `sorted([a, b]) == [0, 0]` → FALLA. Con INCR atomico → {0, 1} → PASA.
    (Verificado: con el `next_seq` viejo parcheado, este test falla.)
    """
    mgr = SessionManager(redis_client)
    episode_id = uuid4()
    state = _make_state(episode_id)
    await mgr.set(state)

    reads = 0
    both_read = asyncio.Event()

    async def reserve() -> int:
        nonlocal reads
        # Cada "request" carga su propia copia del estado (como en produccion:
        # dos POST distintos hacen cada uno su sessions.get()).
        s = await mgr.get(episode_id)
        reads += 1
        if reads == 2:
            both_read.set()
        await both_read.wait()  # no reservar hasta que AMBAS hayan leido
        return await mgr.next_seq(s)

    a, b = await asyncio.gather(reserve(), reserve())

    assert sorted([a, b]) == [0, 1], f"seqs colisionaron o con hueco: {a=} {b=}"


async def test_mismo_event_uuid_concurrente_mismo_seq_sin_hueco(redis_client):
    """QA: dos emisiones con el MISMO event_uuid concurrentes → MISMO seq y sin
    hueco (el `emit` corre exactamente una vez, no se gasta un seq de mas)."""
    mgr = SessionManager(redis_client)
    episode_id = uuid4()
    state = _make_state(episode_id)
    await mgr.set(state)
    await mgr.init_seq_counter(episode_id, 0)

    key = str(uuid4())
    emit_seqs: list[int] = []

    async def emit() -> int:
        s = await mgr.get(episode_id)
        seq = await mgr.next_seq(s)
        emit_seqs.append(seq)
        return seq

    a, b = await asyncio.gather(
        mgr.reserve_or_get_seq(episode_id, key, emit),
        mgr.reserve_or_get_seq(episode_id, key, emit),
    )

    assert a == b, f"mismo event_uuid devolvio seqs distintos: {a=} {b=}"
    assert len(emit_seqs) == 1, "el emit corrio mas de una vez (duplicado / seq gastado)"

    # El siguiente evento real es CONTIGUO (no hay hueco por el seq del perdedor).
    nxt = await mgr.next_seq(await mgr.get(episode_id))
    assert nxt == a + 1


async def test_init_seq_counter_resume_arranca_del_max_persistido(redis_client):
    """Reanudar NO resetea a 0: init_seq_counter(events_count) hace que el
    proximo INCR reserve exactamente events_count (contiguo con la cadena)."""
    mgr = SessionManager(redis_client)
    episode_id = uuid4()
    state = _make_state(episode_id)
    await mgr.set(state)

    await mgr.init_seq_counter(episode_id, 5)  # 5 seqs ya persistidos (0..4)
    seq = await mgr.next_seq(await mgr.get(episode_id))
    assert seq == 5  # arranca del max ya persistido, no de 0


async def test_reserve_or_get_seq_sin_key_es_legacy(redis_client):
    """Sin idempotency_key el `emit` corre directo (sin dedup) — backwards-compat."""
    mgr = SessionManager(redis_client)
    episode_id = uuid4()
    state = _make_state(episode_id)
    await mgr.set(state)
    await mgr.init_seq_counter(episode_id, 0)

    calls = 0

    async def emit() -> int:
        nonlocal calls
        calls += 1
        return await mgr.next_seq(await mgr.get(episode_id))

    s0 = await mgr.reserve_or_get_seq(episode_id, None, emit)
    s1 = await mgr.reserve_or_get_seq(episode_id, None, emit)
    assert (s0, s1) == (0, 1)
    assert calls == 2


async def test_reserve_or_get_seq_libera_claim_si_emit_falla(redis_client):
    """Si `emit` falla, el claim se libera (HDEL) para que un reintento genuino
    pueda re-ganarlo — no queda PENDING atascado."""
    mgr = SessionManager(redis_client)
    episode_id = uuid4()
    state = _make_state(episode_id)
    await mgr.set(state)
    await mgr.init_seq_counter(episode_id, 0)

    key = str(uuid4())

    async def bad_emit() -> int:
        raise ValueError("episodio cerrado")

    with pytest.raises(ValueError):
        await mgr.reserve_or_get_seq(episode_id, key, bad_emit)

    # El claim se libero: un reintento con la MISMA key vuelve a ganar y emite.
    async def good_emit() -> int:
        return await mgr.next_seq(await mgr.get(episode_id))

    seq = await mgr.reserve_or_get_seq(episode_id, key, good_emit)
    assert seq == 0  # re-gano el claim y reservo (no quedo bloqueado en PENDING)


async def test_seq_reservation_pending_si_claim_no_resuelve(redis_client):
    """Perdedor que nunca ve el seq resuelto (ganador colgado) → SeqReservationPendingError
    (fail-safe: NO duplica ni inventa seq)."""
    mgr = SessionManager(redis_client)
    episode_id = uuid4()
    key = str(uuid4())
    # Simular un ganador que dejo el claim en PENDING y nunca lo resolvio.
    await mgr.redis.hset(mgr._seen_key(episode_id), key, "PENDING")

    async def emit() -> int:  # no deberia llamarse (perdimos el claim)
        raise AssertionError("emit no debe correr en el perdedor")

    with pytest.raises(SeqReservationPendingError):
        await mgr.reserve_or_get_seq(episode_id, key, emit)
