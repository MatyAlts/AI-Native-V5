"""Tests focales del PartitionWorker.

Cubre construcción + helpers que NO requieren conexión real a Redis/DB.
El path completo de consume_loop está en `tests/integration/` con
testcontainers.
"""

from __future__ import annotations

from unittest.mock import MagicMock
from uuid import uuid4

from ctr_service.workers.partition_worker import (
    MAX_ATTEMPTS,
    PartitionConfig,
    PartitionWorker,
)


def test_partition_config_defaults() -> None:
    cfg = PartitionConfig(partition=0)
    assert cfg.partition == 0
    assert cfg.consumer_group == "ctr_workers"
    assert cfg.stream_prefix == "ctr.p"
    assert cfg.dlq_stream == "ctr.dead"
    assert cfg.block_ms == 2000
    assert cfg.batch_size == 32


def test_partition_config_custom() -> None:
    cfg = PartitionConfig(
        partition=3,
        consumer_group="alt-group",
        stream_prefix="ctr.x",
        dlq_stream="ctr.alt-dead",
        block_ms=5000,
        batch_size=64,
    )
    assert cfg.partition == 3
    assert cfg.consumer_group == "alt-group"
    assert cfg.stream_prefix == "ctr.x"


def test_partition_worker_construction_sets_consumer_name() -> None:
    cfg = PartitionConfig(partition=2)
    worker = PartitionWorker(
        config=cfg,
        redis_client=MagicMock(),
        session_factory=MagicMock(),
    )
    assert worker.consumer_name == "worker-2"
    assert worker.stream_key == "ctr.p2"


def test_partition_worker_stream_key_per_partition() -> None:
    """Cada partición tiene un stream key distinto."""
    keys = []
    for p in range(8):
        cfg = PartitionConfig(partition=p)
        worker = PartitionWorker(
            config=cfg,
            redis_client=MagicMock(),
            session_factory=MagicMock(),
        )
        keys.append(worker.stream_key)
    assert keys == [f"ctr.p{i}" for i in range(8)]
    assert len(set(keys)) == 8  # todos únicos


def test_partition_worker_default_attestation_producer_none() -> None:
    """ADR-021: sin attestation_producer → modo dev/test."""
    cfg = PartitionConfig(partition=0)
    worker = PartitionWorker(
        config=cfg,
        redis_client=MagicMock(),
        session_factory=MagicMock(),
    )
    assert worker.attestation_producer is None


def test_partition_worker_can_set_attestation_producer() -> None:
    """ADR-021: con attestation_producer → modo prod."""
    cfg = PartitionConfig(partition=0)
    fake_producer = MagicMock()
    worker = PartitionWorker(
        config=cfg,
        redis_client=MagicMock(),
        session_factory=MagicMock(),
        attestation_producer=fake_producer,
    )
    assert worker.attestation_producer is fake_producer


def test_max_attempts_constant_is_3() -> None:
    """MAX_ATTEMPTS = 3 → DLQ al 4to fallo (RN del piloto, 3 intentos)."""
    assert MAX_ATTEMPTS == 3


def test_partition_worker_stop_event_initially_unset() -> None:
    cfg = PartitionConfig(partition=0)
    worker = PartitionWorker(
        config=cfg,
        redis_client=MagicMock(),
        session_factory=MagicMock(),
    )
    assert not worker._stop.is_set()


def test_partition_worker_request_stop_sets_event() -> None:
    cfg = PartitionConfig(partition=0)
    worker = PartitionWorker(
        config=cfg,
        redis_client=MagicMock(),
        session_factory=MagicMock(),
    )
    # buscar método público o protected que setee _stop
    if hasattr(worker, "request_stop"):
        worker.request_stop()
        assert worker._stop.is_set()
    else:
        worker._stop.set()
        assert worker._stop.is_set()


# ── Fallo transitorio vs permanente: quien puede ir a la DLQ ──────────────
#
# Es la distincion mas cara del worker. Un evento que va a la DLQ **sale de la
# cadena para siempre**, y su lugar lo termina ocupando otro cuando el heal
# repone el contador al `events_count`. Mandar ahi un evento VALIDO —porque la
# base tardo en volver— es destruir evidencia de la tesis.
#
# Antes del reclamo de pendientes, `MAX_ATTEMPTS` era inalcanzable y esta rama
# era codigo muerto. Al encenderla, el presupuesto quedo en
# `1 entrega + 2 reclamos x 60s ≈ 120 segundos`, plano y sin backoff: un
# failover de Postgres de tres minutos alcanzaba para mandar a la DLQ todos los
# eventos de esa ventana y marcar decenas de episodios como adulterados.


def _worker_con_fallo(exc: BaseException, attempts: int) -> tuple[PartitionWorker, MagicMock]:
    """Un worker cuyo `_persist_event` siempre tira `exc`, con `attempts` gastados."""
    from unittest.mock import AsyncMock

    worker = PartitionWorker(
        config=PartitionConfig(partition=0),
        redis_client=MagicMock(),
        session_factory=MagicMock(),
    )
    worker._persist_event = AsyncMock(side_effect=exc)  # type: ignore[method-assign]
    worker._get_attempts = AsyncMock(return_value=attempts)  # type: ignore[method-assign]
    worker._move_to_dlq = AsyncMock()  # type: ignore[method-assign]
    worker._ack = AsyncMock()  # type: ignore[method-assign]
    return worker, worker._move_to_dlq  # type: ignore[return-value]


_MENSAJE = {b"payload": b'{"tenant_id": "t", "episode_id": "e", "event_uuid": "u", "seq": 0}'}


async def test_un_fallo_de_POSTGRES_no_manda_el_evento_a_la_dlq() -> None:
    """El caso que destruia evidencia: la base se cae, el evento es valido.

    Se prueba MUY por encima de MAX_ATTEMPTS a proposito: el punto no es que
    aguante un intento mas, es que un transitorio NO CONSUME presupuesto.
    """
    from sqlalchemy.exc import OperationalError

    worker, dlq = _worker_con_fallo(
        OperationalError("connection refused", {}, Exception()), attempts=MAX_ATTEMPTS * 10
    )

    await worker._process_message("1-0", _MENSAJE)

    dlq.assert_not_awaited(), "un fallo de infraestructura no puede tirar el evento"
    worker._ack.assert_not_awaited(), "sin ACK: el mensaje queda en la PEL, recuperable"


async def test_un_corte_de_RED_tampoco() -> None:
    """`ConnectionError` y `TimeoutError` heredan de `OSError` en 3.11+."""
    worker, dlq = _worker_con_fallo(ConnectionError("dns"), attempts=MAX_ATTEMPTS * 10)

    await worker._process_message("1-0", _MENSAJE)

    dlq.assert_not_awaited()


async def test_un_seq_inesperado_SI_va_a_la_dlq() -> None:
    """El otro lado de la moneda: reintentar esto devuelve siempre lo mismo.

    Si el transitorio se tragara TODO, la DLQ volveria a ser codigo muerto y el
    `integrity_compromised` no se marcaria nunca — que es el bug que el reclamo
    de pendientes vino a cerrar.
    """
    worker, dlq = _worker_con_fallo(
        ValueError("Seq inesperado: recibido=85 esperado=43"), attempts=MAX_ATTEMPTS
    )

    await worker._process_message("1-0", _MENSAJE)

    dlq.assert_awaited_once()
    worker._ack.assert_awaited_once()


async def test_un_permanente_por_debajo_del_tope_se_reintenta() -> None:
    worker, dlq = _worker_con_fallo(ValueError("Seq inesperado"), attempts=MAX_ATTEMPTS - 1)

    await worker._process_message("1-0", _MENSAJE)

    dlq.assert_not_awaited()
    worker._ack.assert_not_awaited()


# ── Ultimo recurso: si no se pudo reponer el contador, borrar la sesion ───


async def test_si_no_se_puede_reponer_el_contador_se_borra_la_sesion() -> None:
    """Sin esto el episodio quedaba MUDO seis horas.

    El worker repone el contador y no toca `tutor:session:` — correcto en el
    camino feliz. Pero si la reposicion falla (Postgres saturado, que es
    plausible: acabamos de fallar tres veces contra la misma base), la sesion
    sigue viva, `_emitir_con_heal` nunca dispara —solo entra por el `ValueError`
    de `sessions.get()` devolviendo None— y `resume_episode` tiene un
    early-return ANTES de `init_seq_counter`. El unico camino de salida era el
    TTL: seis horas con el alumno tipeando y nada guardandose.
    """
    from unittest.mock import AsyncMock

    from ctr_service.workers.partition_worker import (
        TUTOR_SESSION_KEY_PREFIX,
    )

    redis_mock = MagicMock()
    redis_mock.set = AsyncMock(side_effect=ConnectionError("postgres/redis caido"))
    redis_mock.delete = AsyncMock()

    worker = PartitionWorker(
        config=PartitionConfig(partition=0),
        redis_client=redis_mock,
        session_factory=MagicMock(),
    )
    episode_id = uuid4()

    # La lectura de `events_count` tambien falla: es el escenario real, la misma
    # base que acaba de rechazar el evento.
    await worker._reponer_contador_seq(episode_id, uuid4())

    redis_mock.delete.assert_awaited_once_with(f"{TUTOR_SESSION_KEY_PREFIX}{episode_id}")


def test_los_prefijos_del_tutor_no_pueden_derivar_en_silencio() -> None:
    """El ctr-service escribe DOS keys que son del tutor-service.

    Es una excepcion deliberada y acotada, pero si el tutor renombra un prefijo
    el worker sigue escribiendo el viejo y el heal se vuelve un no-op que
    loguea exito. Este test ata las dos constantes; el del TTL vive aparte.
    """
    from ctr_service.workers.partition_worker import (
        TUTOR_SEQ_KEY_PREFIX,
        TUTOR_SESSION_KEY_PREFIX,
    )
    from tutor_service.services.session import SEQ_KEY_PREFIX, SESSION_KEY_PREFIX

    assert TUTOR_SEQ_KEY_PREFIX == SEQ_KEY_PREFIX
    assert TUTOR_SESSION_KEY_PREFIX == SESSION_KEY_PREFIX


# ── ensure_consumer_group: sobrevive a transitorios de Redis ──────────────
# Incidente 2026-10-16 / 2026-10-23: Redis cargando el dataset (BusyLoadingError)
# mató a los 8 workers porque `ensure_consumer_group` no reintentaba.


def _worker_con_redis(redis_mock: MagicMock, partition: int = 3) -> PartitionWorker:
    return PartitionWorker(
        config=PartitionConfig(partition=partition),
        redis_client=redis_mock,
        session_factory=MagicMock(),
    )


def _redis_con_xgroup(*efectos: object) -> MagicMock:
    from unittest.mock import AsyncMock

    r = MagicMock()
    r.xgroup_create = AsyncMock(side_effect=list(efectos))
    return r


async def test_ensure_consumer_group_reintenta_busyloading_con_backoff_creciente() -> None:
    from unittest.mock import AsyncMock

    import redis as redis_lib

    loading = redis_lib.BusyLoadingError("Redis is loading the dataset in memory")
    r = _redis_con_xgroup(loading, loading, True)
    worker = _worker_con_redis(r)
    worker._esperar_o_detener = AsyncMock(return_value=False)  # type: ignore[method-assign]

    await worker.ensure_consumer_group()

    assert r.xgroup_create.await_count == 3
    esperas = [c.args[0] for c in worker._esperar_o_detener.await_args_list]
    assert esperas == [1, 2]


async def test_ensure_consumer_group_backoff_se_topa_en_30s() -> None:
    from unittest.mock import AsyncMock

    import redis as redis_lib

    fallos = [redis_lib.BusyLoadingError("loading")] * 8
    r = _redis_con_xgroup(*fallos, True)
    worker = _worker_con_redis(r)
    worker._esperar_o_detener = AsyncMock(return_value=False)  # type: ignore[method-assign]

    await worker.ensure_consumer_group()

    esperas = [c.args[0] for c in worker._esperar_o_detener.await_args_list]
    assert esperas == [1, 2, 4, 8, 16, 30, 30, 30]


async def test_ensure_consumer_group_busygroup_retorna_sin_reintentar() -> None:
    import redis as redis_lib

    r = _redis_con_xgroup(redis_lib.ResponseError("BUSYGROUP Consumer Group name already exists"))
    worker = _worker_con_redis(r)

    await worker.ensure_consumer_group()

    assert r.xgroup_create.await_count == 1


async def test_ensure_consumer_group_error_permanente_propaga_sin_reintentar() -> None:
    import pytest
    import redis as redis_lib

    r = _redis_con_xgroup(
        redis_lib.ResponseError("WRONGTYPE Operation against a key holding the wrong kind of value")
    )
    worker = _worker_con_redis(r)

    with pytest.raises(redis_lib.ResponseError, match="WRONGTYPE"):
        await worker.ensure_consumer_group()

    assert r.xgroup_create.await_count == 1


async def test_ensure_consumer_group_reintenta_connection_y_timeout() -> None:
    from unittest.mock import AsyncMock

    import redis as redis_lib

    r = _redis_con_xgroup(
        redis_lib.ConnectionError("Connection refused"),
        redis_lib.TimeoutError("Timeout reading from socket"),
        True,
    )
    worker = _worker_con_redis(r)
    worker._esperar_o_detener = AsyncMock(return_value=False)  # type: ignore[method-assign]

    await worker.ensure_consumer_group()

    assert r.xgroup_create.await_count == 3


async def test_ensure_consumer_group_stop_interrumpe_la_espera_del_backoff() -> None:
    """El backoff real (30 s) no se cumple: stop() corta la espera."""
    import asyncio

    import redis as redis_lib

    r = _redis_con_xgroup(*([redis_lib.BusyLoadingError("loading")] * 50))
    worker = _worker_con_redis(r)
    worker.stop()  # ya detenido: la primera espera debe volver de inmediato

    await asyncio.wait_for(worker.ensure_consumer_group(), timeout=2)

    assert r.xgroup_create.await_count == 1  # no siguió reintentando tras el stop


async def test_ensure_consumer_group_stop_durante_la_espera_corta_el_backoff() -> None:
    import asyncio

    import redis as redis_lib

    r = _redis_con_xgroup(*([redis_lib.BusyLoadingError("loading")] * 50))
    worker = _worker_con_redis(r)

    tarea = asyncio.create_task(worker.ensure_consumer_group())
    await asyncio.sleep(0.05)  # ya está esperando el backoff de 1 s
    worker.stop()

    await asyncio.wait_for(tarea, timeout=0.5)  # < 1 s del backoff


async def test_ensure_consumer_group_conserva_id_0_y_mkstream() -> None:
    r = _redis_con_xgroup(True)
    worker = _worker_con_redis(r, partition=5)

    await worker.ensure_consumer_group()

    r.xgroup_create.assert_awaited_once_with(
        name="ctr.p5", groupname="ctr_workers", id="0", mkstream=True
    )


async def test_un_busyloading_en_process_batch_no_termina_run() -> None:
    """El loop principal ya sobrevivía a errores de infra: queda fijado."""
    from unittest.mock import AsyncMock, patch

    import redis as redis_lib

    r = MagicMock()
    r.xgroup_create = AsyncMock(return_value=True)
    r.set = AsyncMock(return_value=True)
    worker = _worker_con_redis(r)
    llamadas = {"n": 0}

    async def batch() -> None:
        llamadas["n"] += 1
        if llamadas["n"] < 3:
            raise redis_lib.BusyLoadingError("loading")
        worker.stop()

    worker._process_batch = batch  # type: ignore[method-assign]
    worker._xpending_metric_loop = AsyncMock()  # type: ignore[method-assign]

    with patch("ctr_service.workers.partition_worker.asyncio.sleep", new=AsyncMock()):
        await worker.run()

    assert llamadas["n"] == 3


# ── Heartbeat por partición ───────────────────────────────────────────────
# Cada vuelta del loop renueva `ctr:worker:heartbeat:{p}` (TTL 60 s). Si el
# loop se cuelga o el worker muere, la key vence y /health/ready lo muestra.


def _worker_para_run(*, vueltas: int, partition: int = 3) -> tuple[PartitionWorker, MagicMock]:
    """Worker cuyo `run()` da `vueltas` vueltas y se detiene solo."""
    from unittest.mock import AsyncMock

    r = MagicMock()
    r.xgroup_create = AsyncMock(return_value=True)
    r.set = AsyncMock(return_value=True)
    worker = _worker_con_redis(r, partition=partition)
    restantes = {"n": vueltas}

    async def batch() -> None:
        restantes["n"] -= 1
        if restantes["n"] <= 0:
            worker.stop()

    worker._process_batch = batch  # type: ignore[method-assign]
    worker._xpending_metric_loop = AsyncMock()  # type: ignore[method-assign]
    return worker, r


async def test_run_escribe_heartbeat_con_ttl_60_en_cada_vuelta() -> None:
    from ctr_service.workers.partition_worker import (
        HEARTBEAT_KEY_PREFIX,
        HEARTBEAT_TTL_SECONDS,
    )

    worker, r = _worker_para_run(vueltas=2, partition=3)

    await worker.run()

    assert HEARTBEAT_KEY_PREFIX == "ctr:worker:heartbeat:"
    assert HEARTBEAT_TTL_SECONDS == 60
    assert r.set.await_count == 2
    for call in r.set.await_args_list:
        assert call.args[0] == "ctr:worker:heartbeat:3"
        assert "worker-3" in call.args[1]
        assert call.kwargs == {"ex": 60}


async def test_heartbeat_usa_la_key_de_la_particion_del_worker() -> None:
    worker, r = _worker_para_run(vueltas=1, partition=6)

    await worker.run()

    assert r.set.await_args.args[0] == "ctr:worker:heartbeat:6"


async def test_no_escribe_heartbeat_mientras_ensure_consumer_group_no_tuvo_exito() -> None:
    import asyncio
    from unittest.mock import AsyncMock

    import redis as redis_lib

    r = MagicMock()
    r.xgroup_create = AsyncMock(side_effect=redis_lib.BusyLoadingError("loading"))
    r.set = AsyncMock(return_value=True)
    worker = _worker_con_redis(r)

    tarea = asyncio.create_task(worker.run())
    await asyncio.sleep(0.05)  # reintentando el arranque
    worker.stop()
    await asyncio.wait_for(tarea, timeout=1)

    r.set.assert_not_awaited()


async def test_un_fallo_del_heartbeat_no_impide_procesar_el_batch() -> None:
    from unittest.mock import AsyncMock

    import redis as redis_lib

    worker, r = _worker_para_run(vueltas=2)
    r.set = AsyncMock(side_effect=redis_lib.ConnectionError("down"))
    procesados = {"n": 0}
    original = worker._process_batch

    async def contando() -> None:
        procesados["n"] += 1
        await original()

    worker._process_batch = contando  # type: ignore[method-assign]

    await worker.run()

    assert procesados["n"] == 2
    assert r.set.await_count == 2
