"""Contrato del `seq` entre tutor-service y ctr-service.

Cada servicio tiene su suite y las dos estan en verde, pero ninguna cruza
la frontera: los tests del tutor usan un CTR mockeado con `events_count`
fijo, y los del ctr publican eventos con el `seq` escrito a mano. El
incidente del 2026-08-24 vivio exactamente en ese hueco.

Aca no hay mocks de ninguno de los dos lados. El `seq` lo asigna el
`SessionManager` real del tutor contra Redis real, y lo valida el
`PartitionWorker` real del ctr contra Postgres real — que es como corren en
produccion.

El contrato bajo prueba:

    tutor:  seq = INCR tutor:seq:{episode_id} - 1
    ctr:    persiste si y solo si seq == episodes.events_count

Dos contadores distintos que deben coincidir siempre, sin que ninguno de
los dos sepa del otro.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import select, text

from .conftest import requires_docker

pytestmark = [pytest.mark.integration, requires_docker]


def _evento(state, seq: int, event_type: str, payload: dict) -> dict:
    return {
        "event_uuid": str(uuid4()),
        "episode_id": str(state.episode_id),
        "tenant_id": str(state.tenant_id),
        "seq": seq,
        "event_type": event_type,
        "ts": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "payload": payload,
        "prompt_system_hash": "a" * 64,
        "prompt_system_version": "v1.0.0",
        "classifier_config_hash": "b" * 64,
    }


def _apertura(state) -> dict:
    return {
        "student_pseudonym": str(state.student_pseudonym),
        "problema_id": str(uuid4()),
        "comision_id": str(state.comision_id),
        "curso_config_hash": "c" * 64,
    }


async def _armar(redis_container, session_factory):
    """Devuelve (redis, producer, worker, sessions, state) con ambos lados reales."""
    import redis.asyncio as redis
    from ctr_service.services.producer import EventProducer
    from ctr_service.workers.partition_worker import PartitionConfig, PartitionWorker
    from tutor_service.services.session import SessionManager, SessionState

    url = (
        f"redis://{redis_container.get_container_host_ip()}:"
        f"{redis_container.get_exposed_port(6379)}/0"
    )
    r = redis.from_url(url, decode_responses=False)
    producer = EventProducer(r, num_partitions=1)
    worker = PartitionWorker(
        config=PartitionConfig(
            partition=0,
            block_ms=500,
            claim_min_idle_ms=0,
            dlq_stream=f"ctr.dead.{uuid4().hex[:8]}",
        ),
        redis_client=r,
        session_factory=session_factory,
    )
    await worker.ensure_consumer_group()

    # El SessionManager del tutor necesita strings, el worker del ctr bytes.
    sessions = SessionManager(redis.from_url(url, decode_responses=True))
    state = SessionState(
        episode_id=uuid4(),
        tenant_id=uuid4(),
        comision_id=uuid4(),
        student_pseudonym=uuid4(),
    )
    return r, producer, worker, sessions, state


async def _events_count(session_factory, state) -> int:
    from ctr_service.models import Episode

    async with session_factory() as s:
        await s.execute(
            text("SELECT set_config('app.current_tenant', :t, true)"),
            {"t": str(state.tenant_id)},
        )
        ep = (
            await s.execute(select(Episode).where(Episode.id == state.episode_id))
        ).scalar_one_or_none()
        return int(ep.events_count) if ep else 0


async def _seqs_persistidos(session_factory, state) -> list[int]:
    from ctr_service.models import Event

    async with session_factory() as s:
        await s.execute(
            text("SELECT set_config('app.current_tenant', :t, true)"),
            {"t": str(state.tenant_id)},
        )
        rows = (
            (
                await s.execute(
                    select(Event).where(Event.episode_id == state.episode_id).order_by(Event.seq)
                )
            )
            .scalars()
            .all()
        )
        return [e.seq for e in rows]


async def test_los_dos_contadores_avanzan_juntos_en_el_flujo_normal(
    pg_engine, session_factory, redis_container
) -> None:
    """Happy path cruzando la frontera: el seq que asigna el tutor es
    exactamente el que el ctr espera, evento tras evento.

    Es el test que ninguna de las dos suites hacia: la del tutor comprueba
    que INCR es atomico, la del ctr que la validacion rechaza huecos, pero
    nadie verificaba que un contador produzca lo que el otro exige.
    """
    r, producer, worker, sessions, state = await _armar(redis_container, session_factory)

    await sessions.init_seq_counter(state.episode_id, 0)

    seq = await sessions.next_seq(state)
    assert seq == 0
    await producer.publish(_evento(state, seq, "episodio_abierto", _apertura(state)))
    await worker._process_batch()

    for i in range(1, 6):
        seq = await sessions.next_seq(state)
        assert seq == await _events_count(session_factory, state), (
            "el seq que asigna el tutor debe ser el que el ctr espera"
        )
        await producer.publish(
            _evento(state, seq, "edicion_codigo", {"snapshot": f"x = {i}", "origin": "typed"})
        )
        await worker._process_batch()

    assert await _seqs_persistidos(session_factory, state) == [0, 1, 2, 3, 4, 5]

    await r.aclose()
    await sessions.redis.aclose()


async def test_un_evento_perdido_desincroniza_los_contadores_y_el_heal_los_realinea(
    pg_engine, session_factory, redis_container
) -> None:
    """El ciclo completo del incidente, de punta a punta y sin mocks.

    Un evento no llega al stream (fallo de publicacion, red, reinicio). El
    contador del tutor ya lo conto, el del ctr no. Desde ese momento cada
    evento nuevo nace con un seq que la cadena no acepta: el alumno escribe
    y nada se guarda.

    Al agotar los intentos el worker manda el evento a la DLQ, marca el
    episodio e invalida la sesion del tutor. Reponer el contador desde
    `events_count` — que es lo que hace `resume_episode` — realinea las dos
    puntas y el episodio vuelve a aceptar eventos.
    """
    from tutor_service.services.session import SEQ_KEY_PREFIX

    r, producer, worker, sessions, state = await _armar(redis_container, session_factory)

    await sessions.init_seq_counter(state.episode_id, 0)
    seq = await sessions.next_seq(state)
    await producer.publish(_evento(state, seq, "episodio_abierto", _apertura(state)))
    await worker._process_batch()
    assert await _events_count(session_factory, state) == 1

    # El tutor reserva un seq y el evento NUNCA llega al stream.
    perdido = await sessions.next_seq(state)
    assert perdido == 1

    # Desde aca los contadores divergen: el tutor va uno adelante.
    siguiente = await sessions.next_seq(state)
    assert siguiente == 2
    assert await _events_count(session_factory, state) == 1

    await producer.publish(
        _evento(state, siguiente, "edicion_codigo", {"snapshot": "trabajo real", "origin": "typed"})
    )
    for _ in range(5):
        await worker._process_batch()

    # No entro, y todo lo que el alumno escriba despues correria la misma
    # suerte mientras los contadores sigan desalineados.
    assert await _seqs_persistidos(session_factory, state) == [0]
    assert await r.xlen(worker.cfg.dlq_stream) == 1

    # El worker repuso el contador del tutor por su cuenta — no hay que
    # reanudar a mano ni esperar a que el alumno recargue. Es el heal real:
    # nadie del lado del tutor intervino en este bloque.
    assert int(await r.get(f"{SEQ_KEY_PREFIX}{state.episode_id}")) == await _events_count(
        session_factory, state
    )

    recuperado = await sessions.next_seq(state)
    assert recuperado == 1, "el contador vuelve a producir el seq que la cadena espera"

    await producer.publish(
        _evento(
            state, recuperado, "edicion_codigo", {"snapshot": "sigo trabajando", "origin": "typed"}
        )
    )
    await worker._process_batch()

    assert await _seqs_persistidos(session_factory, state) == [0, 1], (
        "tras el heal el episodio vuelve a aceptar eventos"
    )
    assert await r.exists(f"{SEQ_KEY_PREFIX}{state.episode_id}") == 1

    await r.aclose()
    await sessions.redis.aclose()


async def test_contador_perdido_arranca_en_cero_y_la_cadena_lo_rechaza(
    pg_engine, session_factory, redis_container
) -> None:
    """Si la key del contador desaparece (expiro, Redis reinicio), `INCR`
    sobre una key ausente devuelve 1 y `next_seq` entrega seq=0.

    Sobre un episodio con historia eso es un seq que la cadena ya uso. El
    evento se rechaza — el append-only no se falsea para aceptarlo — y la
    unica salida es reponer el contador desde `events_count`.
    """
    from tutor_service.services.session import SEQ_KEY_PREFIX

    r, producer, worker, sessions, state = await _armar(redis_container, session_factory)

    await sessions.init_seq_counter(state.episode_id, 0)
    for i in range(3):
        seq = await sessions.next_seq(state)
        tipo = "episodio_abierto" if i == 0 else "edicion_codigo"
        payload = _apertura(state) if i == 0 else {"snapshot": f"v{i}", "origin": "typed"}
        await producer.publish(_evento(state, seq, tipo, payload))
        await worker._process_batch()
    assert await _events_count(session_factory, state) == 3

    # Se pierde el contador.
    await sessions.redis.delete(f"{SEQ_KEY_PREFIX}{state.episode_id}")

    revivido = await sessions.next_seq(state)
    assert revivido == 0, "INCR sobre key ausente arranca de cero"

    await producer.publish(
        _evento(state, revivido, "edicion_codigo", {"snapshot": "se pierde", "origin": "typed"})
    )
    for _ in range(5):
        await worker._process_batch()

    assert await _seqs_persistidos(session_factory, state) == [0, 1, 2]
    assert await r.xlen(worker.cfg.dlq_stream) == 1

    await r.aclose()
    await sessions.redis.aclose()
