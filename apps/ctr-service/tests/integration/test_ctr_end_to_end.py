"""Tests de integración end-to-end del ctr-service.

Requieren Docker. Levantan Postgres real, aplican las migraciones del
academic-service (para apply_tenant_rls) + ctr-service, ejercitan el
worker con Redis Streams real y verifican persistencia + RLS + cadena.

Skip automático si Docker no está disponible.
"""

from __future__ import annotations

import itertools
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from .conftest import requires_docker

pytestmark = [pytest.mark.integration, requires_docker]


@pytest.fixture(scope="module")
def pg_container():
    from testcontainers.postgres import PostgresContainer

    with PostgresContainer("postgres:16-alpine") as pg:
        yield pg


@pytest.fixture(scope="module")
def redis_container():
    from testcontainers.redis import RedisContainer

    with RedisContainer("redis:7-alpine") as r:
        yield r


@pytest.fixture(scope="module")
def pg_app_url(pg_container) -> str:
    """Setup one-shot del schema + función RLS + app_user. Devuelve la URL
    asyncpg del `app_user` (NOSUPERUSER NOBYPASSRLS).

    Es **sync** y usa psycopg2 internamente vía SQLAlchemy: así no toca
    el event loop async y no choca con la fixture function-scoped que
    crea el engine asyncpg para cada test.

    El user del testcontainer (`test`) es bootstrap superuser → exempt
    de RLS aun con FORCE. Por eso los tests deben conectar como `app_user`.
    """
    from sqlalchemy import create_engine

    superuser_url = pg_container.get_connection_url()  # postgresql+psycopg2
    su_engine = create_engine(superuser_url, future=True)
    with su_engine.begin() as conn:
        conn.execute(text('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"'))
        conn.execute(
            text("""
            CREATE OR REPLACE FUNCTION apply_tenant_rls(tbl regclass)
            RETURNS void AS $$
            BEGIN
                EXECUTE format('ALTER TABLE %s ENABLE ROW LEVEL SECURITY', tbl);
                EXECUTE format('ALTER TABLE %s FORCE ROW LEVEL SECURITY', tbl);
                EXECUTE format('DROP POLICY IF EXISTS tenant_isolation ON %s', tbl);
                EXECUTE format('
                    CREATE POLICY tenant_isolation ON %s
                    USING (tenant_id = current_setting(''app.current_tenant'')::uuid)
                ', tbl);
            END;
            $$ LANGUAGE plpgsql;
        """)
        )
        conn.execute(
            text("""
            DO $$ BEGIN
                IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_user') THEN
                    CREATE ROLE app_user WITH LOGIN PASSWORD 'app_pass'
                        NOSUPERUSER NOBYPASSRLS;
                END IF;
            END $$;
        """)
        )
        conn.execute(text("GRANT ALL ON SCHEMA public TO app_user"))

    from ctr_service.models import Base

    with su_engine.begin() as conn:
        Base.metadata.create_all(conn)
        for table in ("episodes", "events", "dead_letters"):
            conn.execute(text(f"ALTER TABLE {table} OWNER TO app_user"))
            conn.execute(text(f"SELECT apply_tenant_rls('{table}')"))
        conn.execute(
            text("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO app_user")
        )
        conn.execute(text("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO app_user"))
    su_engine.dispose()

    return superuser_url.replace("postgresql+psycopg2://", "postgresql+asyncpg://").replace(
        "test:test@", "app_user:app_pass@"
    )


@pytest.fixture
async def pg_engine(pg_app_url):
    """Engine asyncpg per-test. Function-scoped para no chocar con el
    event loop closed entre tests.

    También patchea el `get_engine()` / `get_session_factory()` globales
    de `ctr_service.db.session` para que `tenant_session()` (usado por el
    worker) apunte al testcontainer en vez de a `settings.ctr_db_url`.
    """
    engine = create_async_engine(pg_app_url, echo=False)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    from ctr_service.db import session as db_session_module

    prev_engine = db_session_module._engine
    prev_factory = db_session_module._session_factory
    db_session_module._engine = engine
    db_session_module._session_factory = factory

    try:
        yield engine
    finally:
        db_session_module._engine = prev_engine
        db_session_module._session_factory = prev_factory
        await engine.dispose()


@pytest.fixture
async def session_factory(pg_engine):
    return async_sessionmaker(pg_engine, expire_on_commit=False)


# ── Tests ──────────────────────────────────────────────────────────────


async def test_rls_bloquea_lecturas_cross_tenant(pg_engine, session_factory) -> None:
    """Un tenant no puede leer episodios de otro tenant aunque haga SELECT directo."""
    from ctr_service.models import Episode

    tenant_a = uuid4()
    tenant_b = uuid4()

    # Insertar episodio del tenant A (setear current_tenant correcto)
    async with session_factory() as s:
        await s.execute(
            text("SELECT set_config('app.current_tenant', :t, true)"),
            {"t": str(tenant_a)},
        )
        ep_a = Episode(
            id=uuid4(),
            tenant_id=tenant_a,
            comision_id=uuid4(),
            student_pseudonym=uuid4(),
            problema_id=uuid4(),
            prompt_system_hash="a" * 64,
            prompt_system_version="v1",
            classifier_config_hash="b" * 64,
            curso_config_hash="c" * 64,
        )
        s.add(ep_a)
        await s.commit()

    # Leer como tenant B: NO debería ver el episodio de A
    async with session_factory() as s:
        await s.execute(
            text("SELECT set_config('app.current_tenant', :t, true)"),
            {"t": str(tenant_b)},
        )
        from sqlalchemy import select

        result = await s.execute(select(Episode).where(Episode.id == ep_a.id))
        found = result.scalar_one_or_none()
        assert found is None, "RLS no bloqueó lectura cross-tenant"

    # Confirmación: leer como tenant A SÍ lo ve
    async with session_factory() as s:
        await s.execute(
            text("SELECT set_config('app.current_tenant', :t, true)"),
            {"t": str(tenant_a)},
        )
        from sqlalchemy import select

        result = await s.execute(select(Episode).where(Episode.id == ep_a.id))
        found = result.scalar_one_or_none()
        assert found is not None


async def test_worker_persiste_evento_con_cadena_correcta(
    pg_engine, session_factory, redis_container
) -> None:
    """End-to-end: publish → worker consume → persiste con chain_hash correcto."""
    import redis.asyncio as redis
    from ctr_service.services.producer import EventProducer
    from ctr_service.workers.partition_worker import (
        PartitionConfig,
        PartitionWorker,
    )

    redis_url = (
        f"redis://{redis_container.get_container_host_ip()}:"
        f"{redis_container.get_exposed_port(6379)}/0"
    )
    r = redis.from_url(redis_url, decode_responses=False)
    producer = EventProducer(r, num_partitions=1)

    tenant = uuid4()
    episode_id = uuid4()
    event = {
        "event_uuid": str(uuid4()),
        "episode_id": str(episode_id),
        "tenant_id": str(tenant),
        "seq": 0,
        "event_type": "episodio_abierto",
        "ts": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "payload": {
            "student_pseudonym": str(uuid4()),
            "problema_id": str(uuid4()),
            "comision_id": str(uuid4()),
            "curso_config_hash": "c" * 64,
        },
        "prompt_system_hash": "a" * 64,
        "prompt_system_version": "v1.0.0",
        "classifier_config_hash": "b" * 64,
    }

    # Publicar al stream
    await producer.publish(event)

    # Correr el worker brevemente
    worker = PartitionWorker(
        config=PartitionConfig(partition=0, block_ms=500),
        redis_client=r,
        session_factory=session_factory,
    )

    # Procesar un batch y salir
    await worker.ensure_consumer_group()
    await worker._process_batch()

    # Verificar persistencia
    from ctr_service.models import Episode, Event
    from sqlalchemy import select

    async with session_factory() as s:
        await s.execute(
            text("SELECT set_config('app.current_tenant', :t, true)"),
            {"t": str(tenant)},
        )
        ep = (await s.execute(select(Episode).where(Episode.id == episode_id))).scalar_one()
        assert ep.events_count == 1
        assert ep.last_chain_hash != "0" * 64  # ya avanzó

        events = (
            (
                await s.execute(
                    select(Event).where(Event.episode_id == episode_id).order_by(Event.seq)
                )
            )
            .scalars()
            .all()
        )
        assert len(events) == 1
        assert events[0].seq == 0
        assert events[0].chain_hash == ep.last_chain_hash

    await r.aclose()


async def test_evento_duplicado_es_idempotente(pg_engine, session_factory, redis_container) -> None:
    """Publicar el mismo event_uuid dos veces persiste una sola fila."""
    import redis.asyncio as redis
    from ctr_service.services.producer import EventProducer
    from ctr_service.workers.partition_worker import (
        PartitionConfig,
        PartitionWorker,
    )

    redis_url = (
        f"redis://{redis_container.get_container_host_ip()}:"
        f"{redis_container.get_exposed_port(6379)}/0"
    )
    r = redis.from_url(redis_url, decode_responses=False)
    producer = EventProducer(r, num_partitions=1)

    tenant = uuid4()
    episode_id = uuid4()
    event_uuid = str(uuid4())

    event = {
        "event_uuid": event_uuid,
        "episode_id": str(episode_id),
        "tenant_id": str(tenant),
        "seq": 0,
        "event_type": "episodio_abierto",
        "ts": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "payload": {
            "student_pseudonym": str(uuid4()),
            "problema_id": str(uuid4()),
            "comision_id": str(uuid4()),
        },
        "prompt_system_hash": "a" * 64,
        "prompt_system_version": "v1.0.0",
        "classifier_config_hash": "b" * 64,
    }

    # Publicar el mismo evento dos veces
    await producer.publish(event)
    await producer.publish(event)

    worker = PartitionWorker(
        config=PartitionConfig(partition=0, block_ms=500),
        redis_client=r,
        session_factory=session_factory,
    )
    await worker.ensure_consumer_group()
    await worker._process_batch()
    await worker._process_batch()

    # Verificar: una sola fila persistida
    from ctr_service.models import Event
    from sqlalchemy import func, select

    async with session_factory() as s:
        await s.execute(
            text("SELECT set_config('app.current_tenant', :t, true)"),
            {"t": str(tenant)},
        )
        count = (
            await s.execute(
                select(func.count(Event.id)).where(Event.event_uuid == UUID(event_uuid))
            )
        ).scalar_one()
        assert count == 1

    await r.aclose()


async def test_abandono_pausa_y_actividad_posterior_reanuda(
    pg_engine, session_factory, redis_container
) -> None:
    """ADR-055 (fix 2026-06-10 #2): episodio_abandonado → estado=paused;
    cualquier evento posterior (el alumno retomó) → estado=open de nuevo.
    La cadena sigue intacta y sin tipos de evento nuevos."""
    import redis.asyncio as redis
    from ctr_service.services.producer import EventProducer
    from ctr_service.workers.partition_worker import (
        PartitionConfig,
        PartitionWorker,
    )

    redis_url = (
        f"redis://{redis_container.get_container_host_ip()}:"
        f"{redis_container.get_exposed_port(6379)}/0"
    )
    r = redis.from_url(redis_url, decode_responses=False)
    producer = EventProducer(r, num_partitions=1)

    tenant = uuid4()
    episode_id = uuid4()

    def _event(seq: int, event_type: str, payload: dict) -> dict:
        return {
            "event_uuid": str(uuid4()),
            "episode_id": str(episode_id),
            "tenant_id": str(tenant),
            "seq": seq,
            "event_type": event_type,
            "ts": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "payload": payload,
            "prompt_system_hash": "a" * 64,
            "prompt_system_version": "v1.0.0",
            "classifier_config_hash": "b" * 64,
        }

    worker = PartitionWorker(
        config=PartitionConfig(partition=0, block_ms=500),
        redis_client=r,
        session_factory=session_factory,
    )
    await worker.ensure_consumer_group()

    from ctr_service.models import Episode
    from sqlalchemy import select

    async def _estado() -> str:
        async with session_factory() as s:
            await s.execute(
                text("SELECT set_config('app.current_tenant', :t, true)"),
                {"t": str(tenant)},
            )
            ep = (await s.execute(select(Episode).where(Episode.id == episode_id))).scalar_one()
            return ep.estado

    # seq=0: apertura → open
    await producer.publish(
        _event(
            0,
            "episodio_abierto",
            {
                "student_pseudonym": str(uuid4()),
                "problema_id": str(uuid4()),
                "comision_id": str(uuid4()),
                "curso_config_hash": "c" * 64,
            },
        )
    )
    await worker._process_batch()
    assert await _estado() == "open"

    # seq=1: abandono → paused
    await producer.publish(
        _event(
            1,
            "episodio_abandonado",
            {"reason": "beforeunload", "last_activity_seconds_ago": 0.0},
        )
    )
    await worker._process_batch()
    assert await _estado() == "paused"

    # seq=2: el alumno retomó y siguió trabajando → open de nuevo
    await producer.publish(
        _event(
            2,
            "edicion_codigo",
            {"snapshot": "print('volvi')", "origin": "typed"},
        )
    )
    await worker._process_batch()
    assert await _estado() == "open"

    # seq=3: cierre → closed (la pausa intermedia no altera el cierre normal)
    await producer.publish(
        _event(3, "episodio_cerrado", {"reason": "student_closed", "total_events": 4})
    )
    await worker._process_batch()
    assert await _estado() == "closed"

    # La cadena quedó íntegra: 4 eventos encadenados sin saltos de seq.
    from ctr_service.models import Event

    async with session_factory() as s:
        await s.execute(
            text("SELECT set_config('app.current_tenant', :t, true)"),
            {"t": str(tenant)},
        )
        events = (
            (
                await s.execute(
                    select(Event).where(Event.episode_id == episode_id).order_by(Event.seq)
                )
            )
            .scalars()
            .all()
        )
        assert [e.seq for e in events] == [0, 1, 2, 3]
        for prev, curr in itertools.pairwise(events):
            assert curr.prev_chain_hash == prev.chain_hash

    await r.aclose()


# ── Desincronizacion de seq (incidente 2026-08-24) ─────────────────────
#
# Produccion mostro este patron repetido durante horas sobre un mismo
# episodio, con el `recibido` creciendo y el `esperado` clavado:
#
#   ValueError: Seq inesperado: recibido=85 esperado=43 ...
#   ValueError: Seq inesperado: recibido=86 esperado=43 ...
#
# El sintoma para el alumno: pausa el ejercicio, vuelve, y el codigo que
# habia escrito no esta. Los tests que siguen caracterizan el
# comportamiento ACTUAL — documentan que hace hoy el sistema, no que
# deberia hacer. Sobre esa base se decide el arreglo.


def _seq_event(episode_id, tenant, seq: int, event_type: str, payload: dict) -> dict:
    """Evento CTR minimo valido para los tests de desincronizacion."""
    return {
        "event_uuid": str(uuid4()),
        "episode_id": str(episode_id),
        "tenant_id": str(tenant),
        "seq": seq,
        "event_type": event_type,
        "ts": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "payload": payload,
        "prompt_system_hash": "a" * 64,
        "prompt_system_version": "v1.0.0",
        "classifier_config_hash": "b" * 64,
    }


def _apertura_payload() -> dict:
    return {
        "student_pseudonym": str(uuid4()),
        "problema_id": str(uuid4()),
        "comision_id": str(uuid4()),
        "curso_config_hash": "c" * 64,
    }


async def test_seq_adelantado_queda_pending_y_nunca_llega_a_dlq(
    pg_engine, session_factory, redis_container
) -> None:
    """CARACTERIZACION: un evento con seq adelantado no se persiste, pero
    tampoco se reintenta ni termina en la DLQ.

    `_process_batch` lee el stream con ">" (solo mensajes nuevos), y no
    existe XAUTOCLAIM/XCLAIM en el servicio. Un mensaje que falla queda
    PENDING indefinidamente: `_get_attempts` nunca supera 1, nunca se
    alcanza MAX_ATTEMPTS y `_move_to_dlq` nunca corre.

    Consecuencia: el episodio NO se marca `integrity_compromised`, asi que
    la deteccion que el diseño promete no llega a materializarse.
    """
    import redis.asyncio as redis
    from ctr_service.models import Episode, Event
    from ctr_service.services.producer import EventProducer
    from ctr_service.workers.partition_worker import (
        MAX_ATTEMPTS,
        PartitionConfig,
        PartitionWorker,
    )

    redis_url = (
        f"redis://{redis_container.get_container_host_ip()}:"
        f"{redis_container.get_exposed_port(6379)}/0"
    )
    r = redis.from_url(redis_url, decode_responses=False)
    producer = EventProducer(r, num_partitions=1)

    tenant, episode_id = uuid4(), uuid4()
    worker = PartitionWorker(
        config=PartitionConfig(partition=0, block_ms=500),
        redis_client=r,
        session_factory=session_factory,
    )
    await worker.ensure_consumer_group()

    # seq=0: apertura, se persiste bien.
    await producer.publish(
        _seq_event(episode_id, tenant, 0, "episodio_abierto", _apertura_payload())
    )
    await worker._process_batch()

    # seq=5 con la cadena en 1: hueco. El worker levanta ValueError.
    await producer.publish(
        _seq_event(episode_id, tenant, 5, "edicion_codigo", {"snapshot": "x = 1", "origin": "typed"})
    )
    await worker._process_batch()

    # Aunque el loop siga girando, el mensaje fallido NO se vuelve a leer:
    # xreadgroup pide ">" y el pendiente no entra en esa lectura.
    for _ in range(MAX_ATTEMPTS + 2):
        await worker._process_batch()

    async with session_factory() as s:
        await s.execute(
            text("SELECT set_config('app.current_tenant', :t, true)"),
            {"t": str(tenant)},
        )
        events = (
            (await s.execute(select(Event).where(Event.episode_id == episode_id))).scalars().all()
        )
        ep = (await s.execute(select(Episode).where(Episode.id == episode_id))).scalar_one()

    # 1. El evento no se persistio.
    assert [e.seq for e in events] == [0]

    # 2. Quedo colgado en PENDING, no en la DLQ.
    pending = await r.xpending(worker.stream_key, worker.cfg.consumer_group)
    assert int(pending.get("pending", 0)) == 1, "el mensaje fallido deberia estar pendiente"
    assert await r.xlen(worker.cfg.dlq_stream) == 0, "nunca llega a la DLQ"

    # 3. Y por eso el episodio nunca se marca comprometido.
    assert ep.integrity_compromised is False
    assert ep.estado != "integrity_compromised"

    await r.aclose()


async def test_el_worker_acepta_el_seq_correcto_despues_de_rechazar_uno_adelantado(
    pg_engine, session_factory, redis_container
) -> None:
    """CARACTERIZACION: el rechazo no envenena la cadena del lado del worker.

    Si despues del seq adelantado llega el seq que la cadena espera, se
    persiste normalmente. Esto acota donde vive el problema: NO en la
    validacion del worker (que se comporta bien), sino aguas arriba, en
    quien asigna los seq — el contador Redis del tutor-service, que sigue
    incrementando sin enterarse de que Postgres los rechazo.
    """
    import redis.asyncio as redis
    from ctr_service.models import Event
    from ctr_service.services.producer import EventProducer
    from ctr_service.workers.partition_worker import PartitionConfig, PartitionWorker

    redis_url = (
        f"redis://{redis_container.get_container_host_ip()}:"
        f"{redis_container.get_exposed_port(6379)}/0"
    )
    r = redis.from_url(redis_url, decode_responses=False)
    producer = EventProducer(r, num_partitions=1)

    tenant, episode_id = uuid4(), uuid4()
    worker = PartitionWorker(
        config=PartitionConfig(partition=0, block_ms=500),
        redis_client=r,
        session_factory=session_factory,
    )
    await worker.ensure_consumer_group()

    await producer.publish(
        _seq_event(episode_id, tenant, 0, "episodio_abierto", _apertura_payload())
    )
    await worker._process_batch()

    # seq=9: adelantado, se rechaza.
    await producer.publish(
        _seq_event(episode_id, tenant, 9, "edicion_codigo", {"snapshot": "a", "origin": "typed"})
    )
    await worker._process_batch()

    # seq=1: el que la cadena espera. Debe entrar sin problema.
    await producer.publish(
        _seq_event(episode_id, tenant, 1, "edicion_codigo", {"snapshot": "b", "origin": "typed"})
    )
    await worker._process_batch()

    async with session_factory() as s:
        await s.execute(
            text("SELECT set_config('app.current_tenant', :t, true)"),
            {"t": str(tenant)},
        )
        events = (
            (
                await s.execute(
                    select(Event).where(Event.episode_id == episode_id).order_by(Event.seq)
                )
            )
            .scalars()
            .all()
        )

    assert [e.seq for e in events] == [0, 1], "el worker acepta el seq correcto tras el rechazo"
    for prev, curr in itertools.pairwise(events):
        assert curr.prev_chain_hash == prev.chain_hash

    await r.aclose()


async def test_el_codigo_del_alumno_desaparece_cuando_la_cadena_se_desincroniza(
    pg_engine, session_factory, redis_container
) -> None:
    """CARACTERIZACION del daño observable — el caso reportado en el piloto.

    El alumno escribe, la cadena se desincroniza, sigue escribiendo. Cada
    `edicion_codigo` recibe 202 Accepted, asi que el front cree que se
    guardo. Al pausar y retomar, el estado se reconstruye desde los
    eventos persistidos: el ultimo snapshot que sobrevive es el previo a
    la desincronizacion. Todo lo escrito despues no existe.
    """
    import redis.asyncio as redis
    from ctr_service.models import Event
    from ctr_service.services.producer import EventProducer
    from ctr_service.workers.partition_worker import PartitionConfig, PartitionWorker

    redis_url = (
        f"redis://{redis_container.get_container_host_ip()}:"
        f"{redis_container.get_exposed_port(6379)}/0"
    )
    r = redis.from_url(redis_url, decode_responses=False)
    producer = EventProducer(r, num_partitions=1)

    tenant, episode_id = uuid4(), uuid4()
    worker = PartitionWorker(
        config=PartitionConfig(partition=0, block_ms=500),
        redis_client=r,
        session_factory=session_factory,
    )
    await worker.ensure_consumer_group()

    await producer.publish(
        _seq_event(episode_id, tenant, 0, "episodio_abierto", _apertura_payload())
    )
    await worker._process_batch()

    # Lo ultimo que el alumno alcanzo a guardar antes de la desincronizacion.
    await producer.publish(
        _seq_event(
            episode_id,
            tenant,
            1,
            "edicion_codigo",
            {"snapshot": "def resolver():\n    pass", "origin": "student_typed"},
        )
    )
    await worker._process_batch()

    # A partir de aca el contador quedo adelantado: todo lo que sigue se
    # rechaza aunque el front reciba 202.
    for seq in (7, 8, 9):
        await producer.publish(
            _seq_event(
                episode_id,
                tenant,
                seq,
                "edicion_codigo",
                {
                    "snapshot": f"def resolver():\n    return {seq}  # trabajo real del alumno",
                    "origin": "student_typed",
                },
            )
        )
        await worker._process_batch()

    async with session_factory() as s:
        await s.execute(
            text("SELECT set_config('app.current_tenant', :t, true)"),
            {"t": str(tenant)},
        )
        events = (
            (
                await s.execute(
                    select(Event).where(Event.episode_id == episode_id).order_by(Event.seq)
                )
            )
            .scalars()
            .all()
        )

    # Reconstruccion equivalente a la de tutor-service `_build_episode_state`:
    # ultimo payload.snapshot entre los eventos de codigo persistidos.
    last_snapshot = None
    for e in events:
        if e.event_type in ("edicion_codigo", "codigo_ejecutado"):
            last_snapshot = (e.payload or {}).get("snapshot")

    assert [e.seq for e in events] == [0, 1], "los tres eventos posteriores no se persistieron"
    assert last_snapshot == "def resolver():\n    pass"
    assert "trabajo real del alumno" not in (last_snapshot or ""), (
        "el trabajo posterior a la desincronizacion no llega al estado reconstruido"
    )

    await r.aclose()
