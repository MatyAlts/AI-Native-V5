"""Idempotencia server-side por Idempotency-Key (fix P-17).

Reproduce el escenario que dejaba episodios `integrity_compromised`:

  1. El ctr-client postea un evento (event_uuid=X) → el servidor asigna seq N,
     avanza el contador de sesión y publica al CTR.
  2. Se PIERDE el ACK (no el request). El servidor ya persistió.
  3. El ctr-client REINTENTA el MISMO evento (event_uuid=X).
  4. ANTES del fix: el servidor asignaba seq N+1 y avanzaba el contador → el
     siguiente evento real llegaba con seq N+2, dejando un hueco que el
     partition_worker no puede cerrar → `ValueError("Seq inesperado")` →
     dead-letter → `integrity_compromised=True` permanente.
  5. CON el fix: el reintento (mismo Idempotency-Key) devuelve el MISMO seq N,
     NO avanza el contador y NO re-publica al CTR. El siguiente evento real
     mantiene seq N+1 y la secuencia queda contigua → el worker no se envenena.

Estos tests corren a nivel ruta (TestClient) con fakeredis, sin worker real;
la aserción clave es que la secuencia de seqs publicados queda contigua (sin
hueco), que es exactamente la condición que el partition_worker exige.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import UUID, uuid4

import fakeredis.aioredis
import pytest
from fastapi.testclient import TestClient
from tutor_service.services.clients import PromptConfig, RetrievalResult
from tutor_service.services.session import SessionManager
from tutor_service.services.tutor_core import TutorCore

# ── Mocks mínimos de los clientes externos ────────────────────────────


class FakeGovernanceClient:
    async def get_prompt(self, name: str, version: str) -> PromptConfig:
        return PromptConfig(
            name=name, version=version, content="Eres un tutor socrático.", hash="abc" + "0" * 61
        )


class FakeContentClient:
    async def retrieve(
        self,
        query: str,
        comision_id: UUID,
        top_k: int,
        tenant_id: UUID,
        caller_id: UUID,
        materia_id: UUID | None = None,
    ) -> RetrievalResult:
        return RetrievalResult(chunks=[], chunks_used_hash="0" * 64, latency_ms=1.0)


class FakeAIGatewayClient:
    async def stream(
        self,
        messages: list[dict],
        model: str,
        tenant_id: UUID,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        materia_id: UUID | None = None,
    ) -> AsyncIterator[dict]:
        yield {"type": "chunk", "content": "ok"}


class FakeCTRClient:
    def __init__(self) -> None:
        self.published_events: list[dict] = []

    async def publish_event(self, event: dict, tenant_id: UUID, caller_id: UUID) -> str:
        self.published_events.append(event)
        return f"fake-msg-id-{len(self.published_events)}"


# ── Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture
async def redis_client():
    client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    yield client
    await client.aclose()


@pytest.fixture
def fake_ctr() -> FakeCTRClient:
    return FakeCTRClient()


@pytest.fixture
def tutor(redis_client, fake_ctr) -> TutorCore:
    return TutorCore(
        governance=FakeGovernanceClient(),
        content=FakeContentClient(),
        ai_gateway=FakeAIGatewayClient(),
        ctr=fake_ctr,
        sessions=SessionManager(redis_client),
    )


@pytest.fixture
def http_client(monkeypatch, fake_ctr: FakeCTRClient, redis_client):
    from tutor_service import main
    from tutor_service.routes import episodes as episodes_module

    fake_tutor = TutorCore(
        governance=FakeGovernanceClient(),
        content=FakeContentClient(),
        ai_gateway=FakeAIGatewayClient(),
        ctr=fake_ctr,
        sessions=SessionManager(redis_client),
    )
    monkeypatch.setattr(episodes_module, "_get_tutor", lambda: fake_tutor)
    yield TestClient(main.app), fake_tutor


def _student_headers(user_id: UUID, tenant_id: UUID, idempotency_key: str | None = None) -> dict:
    headers = {
        "X-User-Id": str(user_id),
        "X-Tenant-Id": str(tenant_id),
        "X-User-Email": "alumno@utn.edu.ar",
        "X-User-Roles": "estudiante",
    }
    if idempotency_key is not None:
        headers["Idempotency-Key"] = idempotency_key
    return headers


# ── Test principal: reproduce y previene el envenenamiento P-17 ────────


async def test_retry_mismo_event_uuid_no_avanza_contador(
    http_client, fake_ctr: FakeCTRClient
) -> None:
    """Reintento con el mismo Idempotency-Key devuelve el MISMO seq, no avanza
    el contador, no re-publica, y el siguiente evento real conserva la secuencia.
    """
    client, tutor = http_client
    tenant_id = uuid4()
    student_id = uuid4()
    episode_id = await tutor.open_episode(
        tenant_id=tenant_id,
        comision_id=uuid4(),
        student_pseudonym=student_id,
        problema_id=uuid4(),
        curso_config_hash="c" * 64,
        classifier_config_hash="b" * 64,
    )
    # seq=0: episodio_abierto ya publicado. Contador de sesión = 1.
    assert len(fake_ctr.published_events) == 1

    uuid_x = str(uuid4())

    # 1er POST de pestana_perdida con event_uuid=X → asigna seq 1.
    r1 = client.post(
        f"/api/v1/episodes/{episode_id}/events/pestana_perdida",
        json={"trigger": "visibilitychange"},
        headers=_student_headers(student_id, tenant_id, idempotency_key=uuid_x),
    )
    assert r1.status_code == 202
    assert r1.json()["seq"] == "1"
    assert len(fake_ctr.published_events) == 2  # abierto + pestana

    # 2do POST: MISMO event_uuid=X (reintento por ACK perdido) → mismo seq 1,
    # SIN avanzar el contador y SIN re-publicar al CTR.
    r2 = client.post(
        f"/api/v1/episodes/{episode_id}/events/pestana_perdida",
        json={"trigger": "visibilitychange"},
        headers=_student_headers(student_id, tenant_id, idempotency_key=uuid_x),
    )
    assert r2.status_code == 202
    assert r2.json()["seq"] == "1"  # idempotente: mismo seq que la primera vez
    assert len(fake_ctr.published_events) == 2  # NO se re-publicó

    # 3er POST: evento NUEVO real (edicion_codigo) con otro event_uuid → seq 2,
    # NO seq 3. Sin el fix habría sido seq 3 y el worker se envenenaría.
    r3 = client.post(
        f"/api/v1/episodes/{episode_id}/events/edicion_codigo",
        json={"snapshot": "x = 1", "diff_chars": 5, "language": "python"},
        headers=_student_headers(student_id, tenant_id, idempotency_key=str(uuid4())),
    )
    assert r3.status_code == 202
    assert r3.json()["seq"] == "2"
    assert len(fake_ctr.published_events) == 3

    # La secuencia de seqs publicados queda CONTIGUA (0,1,2) — exactamente lo
    # que el partition_worker exige (expected_seq = events_count). Sin hueco =
    # sin ValueError = sin dead-letter = sin integrity_compromised.
    seqs = [ev["seq"] for ev in fake_ctr.published_events]
    assert seqs == [0, 1, 2]


async def test_sin_idempotency_key_comportamiento_legacy(
    http_client, fake_ctr: FakeCTRClient
) -> None:
    """Sin header Idempotency-Key el comportamiento es el previo: cada POST
    avanza el contador (backwards-compat con callers que no lo mandan)."""
    client, tutor = http_client
    tenant_id = uuid4()
    student_id = uuid4()
    episode_id = await tutor.open_episode(
        tenant_id=tenant_id,
        comision_id=uuid4(),
        student_pseudonym=student_id,
        problema_id=uuid4(),
        curso_config_hash="c" * 64,
        classifier_config_hash="b" * 64,
    )

    r1 = client.post(
        f"/api/v1/episodes/{episode_id}/events/pestana_perdida",
        json={"trigger": "blur"},
        headers=_student_headers(student_id, tenant_id),  # sin Idempotency-Key
    )
    r2 = client.post(
        f"/api/v1/episodes/{episode_id}/events/pestana_perdida",
        json={"trigger": "blur"},
        headers=_student_headers(student_id, tenant_id),  # sin Idempotency-Key
    )
    assert r1.json()["seq"] == "1"
    assert r2.json()["seq"] == "2"  # sin dedup, avanza normal
    assert len(fake_ctr.published_events) == 3  # abierto + 2 pestanas


async def test_idempotency_keys_distintos_avanzan(http_client, fake_ctr: FakeCTRClient) -> None:
    """Dos eventos con Idempotency-Key DISTINTO son eventos distintos: ambos
    avanzan el contador (no se confunden con un reintento)."""
    client, tutor = http_client
    tenant_id = uuid4()
    student_id = uuid4()
    episode_id = await tutor.open_episode(
        tenant_id=tenant_id,
        comision_id=uuid4(),
        student_pseudonym=student_id,
        problema_id=uuid4(),
        curso_config_hash="c" * 64,
        classifier_config_hash="b" * 64,
    )

    r1 = client.post(
        f"/api/v1/episodes/{episode_id}/events/pestana_perdida",
        json={"trigger": "blur"},
        headers=_student_headers(student_id, tenant_id, idempotency_key=str(uuid4())),
    )
    r2 = client.post(
        f"/api/v1/episodes/{episode_id}/events/pestana_perdida",
        json={"trigger": "blur"},
        headers=_student_headers(student_id, tenant_id, idempotency_key=str(uuid4())),
    )
    assert r1.json()["seq"] == "1"
    assert r2.json()["seq"] == "2"
    assert len(fake_ctr.published_events) == 3


# ── Test a nivel SessionManager (unidad del storage de dedup) ──────────


async def test_session_manager_seen_roundtrip(redis_client) -> None:
    """get_seen_seq devuelve None para uuid nuevo; el mismo seq tras mark_seen."""
    mgr = SessionManager(redis_client)
    episode_id = uuid4()
    key = str(uuid4())

    assert await mgr.get_seen_seq(episode_id, key) is None
    await mgr.mark_seen(episode_id, key, 7)
    assert await mgr.get_seen_seq(episode_id, key) == 7
    # Otro uuid sigue siendo nuevo (aislamiento por key dentro del episodio).
    assert await mgr.get_seen_seq(episode_id, str(uuid4())) is None
    # Otro episodio no comparte el registro.
    assert await mgr.get_seen_seq(uuid4(), key) is None


# ── run-tests: el endpoint que no leia el header (BUG-8) ──────────────
#
# `POST /episodes/{id}/run-tests` declaraba `x_internal_service_token` y nada
# mas: el `Idempotency-Key` llegaba y se descartaba. Mientras `tests_ejecutados`
# se emitia con un fetch pelado eso pasaba desapercibido, pero con el evento
# migrado a la cola durable del `ctr-client` el reintento es rutina: la cola
# reenvia el MISMO `event_uuid` cuando pierde el ACK de una request que el
# servidor SI persistio.
#
# El dano NO es un hueco de seq —cada POST reservaba su propio seq y la cadena
# seguia verificando— sino un `tests_ejecutados` DE MAS. Y este evento no es
# uno cualquiera: el labeler v1.2.0 deriva N3 vs N4 de `tests_ejecutados`. Un
# duplicado puede cambiar como queda nivelado un episodio en los datos de la
# tesis sin que nada falle ni se rompa.
#
# Contrato verificado contra el emisor (`packages/ctr-client/src/index.ts`, rama
# `fix/editor-y-eventos-del-alumno`): manda el header literal `Idempotency-Key`
# con `event.event_uuid`, estable a traves de los reintentos, y rutea
# `tests_ejecutados` a `run-tests` via `RUTAS_POR_EVENTO`. Los tests usan ese
# nombre de header exacto — si el server leyera otro, el de abajo cae.

# El nombre del header, escrito una sola vez, tal cual lo manda el ctr-client.
_HEADER_IDEMPOTENCIA = "Idempotency-Key"


def _run_tests_body() -> dict:
    """Payload de una corrida real de Pyodide: 3 publicos, todos pasando."""
    return {
        "test_count_total": 3,
        "test_count_passed": 3,
        "test_count_failed": 0,
        "tests_publicos": 3,
        "tests_hidden": 0,
        "ejecucion_ms": 412,
    }


async def test_run_tests_reintento_con_misma_key_no_duplica_el_evento(
    http_client, fake_ctr: FakeCTRClient
) -> None:
    """Dos POST con el MISMO Idempotency-Key emiten UN solo `tests_ejecutados`.

    Es el reintento de la cola durable: el servidor persistio el primero y el
    ACK se perdio. Sin dedup quedan dos eventos identicos en la cadena y el
    labeler cuenta dos corridas donde hubo una.
    """
    client, tutor = http_client
    tenant_id = uuid4()
    student_id = uuid4()
    episode_id = await tutor.open_episode(
        tenant_id=tenant_id,
        comision_id=uuid4(),
        student_pseudonym=student_id,
        problema_id=uuid4(),
        curso_config_hash="c" * 64,
        classifier_config_hash="b" * 64,
    )
    uuid_x = str(uuid4())
    headers = _student_headers(student_id, tenant_id) | {_HEADER_IDEMPOTENCIA: uuid_x}

    r1 = client.post(
        f"/api/v1/episodes/{episode_id}/run-tests", json=_run_tests_body(), headers=headers
    )
    r2 = client.post(
        f"/api/v1/episodes/{episode_id}/run-tests", json=_run_tests_body(), headers=headers
    )

    assert r1.status_code == 202
    assert r2.status_code == 202
    assert r1.json()["seq"] == r2.json()["seq"] == "1", "el reintento devolvio otro seq"

    tipos = [ev["event_type"] for ev in fake_ctr.published_events]
    assert tipos.count("tests_ejecutados") == 1, f"el reintento duplico la corrida: {tipos}"

    # La cadena sigue contigua: el reintento no gasto un seq de mas.
    assert [ev["seq"] for ev in fake_ctr.published_events] == [0, 1]


async def test_run_tests_lee_el_header_con_el_nombre_que_manda_el_cliente(
    http_client, fake_ctr: FakeCTRClient
) -> None:
    """Anti-test-vacuo: el dedup depende del NOMBRE exacto del header.

    Si el server leyera otro nombre (o el cliente mandara otro), el fix no
    serviria de nada y el test de arriba pasaria igual siempre que ambos lados
    usaran el mismo nombre equivocado. Este fija la otra mitad: un header con
    nombre distinto NO deduplica, o sea que el endpoint efectivamente keyea por
    `Idempotency-Key` y no por "cualquier header que traiga un uuid".
    """
    client, tutor = http_client
    tenant_id = uuid4()
    student_id = uuid4()
    episode_id = await tutor.open_episode(
        tenant_id=tenant_id,
        comision_id=uuid4(),
        student_pseudonym=student_id,
        problema_id=uuid4(),
        curso_config_hash="c" * 64,
        classifier_config_hash="b" * 64,
    )
    uuid_x = str(uuid4())
    # Mismo valor, nombre equivocado.
    headers = _student_headers(student_id, tenant_id) | {"X-Event-Uuid": uuid_x}

    client.post(f"/api/v1/episodes/{episode_id}/run-tests", json=_run_tests_body(), headers=headers)
    client.post(f"/api/v1/episodes/{episode_id}/run-tests", json=_run_tests_body(), headers=headers)

    tipos = [ev["event_type"] for ev in fake_ctr.published_events]
    assert tipos.count("tests_ejecutados") == 2, (
        "el endpoint dedupica por un header que el ctr-client no manda"
    )


async def test_run_tests_keys_distintas_son_corridas_distintas(
    http_client, fake_ctr: FakeCTRClient
) -> None:
    """Dos corridas genuinas siguen siendo dos eventos.

    El alumno corre los tests, edita, y vuelve a correr: eso es exactamente la
    señal que el labeler necesita para N3/N4. El dedup no puede comersela.
    """
    client, tutor = http_client
    tenant_id = uuid4()
    student_id = uuid4()
    episode_id = await tutor.open_episode(
        tenant_id=tenant_id,
        comision_id=uuid4(),
        student_pseudonym=student_id,
        problema_id=uuid4(),
        curso_config_hash="c" * 64,
        classifier_config_hash="b" * 64,
    )
    base = _student_headers(student_id, tenant_id)

    r1 = client.post(
        f"/api/v1/episodes/{episode_id}/run-tests",
        json=_run_tests_body(),
        headers=base | {_HEADER_IDEMPOTENCIA: str(uuid4())},
    )
    r2 = client.post(
        f"/api/v1/episodes/{episode_id}/run-tests",
        json=_run_tests_body(),
        headers=base | {_HEADER_IDEMPOTENCIA: str(uuid4())},
    )

    assert r1.json()["seq"] == "1"
    assert r2.json()["seq"] == "2"
    tipos = [ev["event_type"] for ev in fake_ctr.published_events]
    assert tipos.count("tests_ejecutados") == 2


async def test_run_tests_sin_key_mantiene_comportamiento_legacy(
    http_client, fake_ctr: FakeCTRClient
) -> None:
    """Sin header, cada POST emite. El execution-service (ADR-060) no manda
    Idempotency-Key y no tiene por que cambiar."""
    client, tutor = http_client
    tenant_id = uuid4()
    student_id = uuid4()
    episode_id = await tutor.open_episode(
        tenant_id=tenant_id,
        comision_id=uuid4(),
        student_pseudonym=student_id,
        problema_id=uuid4(),
        curso_config_hash="c" * 64,
        classifier_config_hash="b" * 64,
    )
    headers = _student_headers(student_id, tenant_id)

    client.post(f"/api/v1/episodes/{episode_id}/run-tests", json=_run_tests_body(), headers=headers)
    client.post(f"/api/v1/episodes/{episode_id}/run-tests", json=_run_tests_body(), headers=headers)

    tipos = [ev["event_type"] for ev in fake_ctr.published_events]
    assert tipos.count("tests_ejecutados") == 2


async def test_run_tests_payload_invalido_no_se_queda_con_la_key(
    http_client, fake_ctr: FakeCTRClient
) -> None:
    """Un 422 libera el claim: el reintento corregido con la MISMA key emite.

    `reserve_or_get_seq` hace HDEL cuando el emit falla. Sin eso, un cliente que
    manda conteos inconsistentes y despues los corrige reusando el event_uuid
    quedaria mudo para siempre.
    """
    client, tutor = http_client
    tenant_id = uuid4()
    student_id = uuid4()
    episode_id = await tutor.open_episode(
        tenant_id=tenant_id,
        comision_id=uuid4(),
        student_pseudonym=student_id,
        problema_id=uuid4(),
        curso_config_hash="c" * 64,
        classifier_config_hash="b" * 64,
    )
    uuid_x = str(uuid4())
    headers = _student_headers(student_id, tenant_id) | {_HEADER_IDEMPOTENCIA: uuid_x}

    malo = _run_tests_body() | {"test_count_passed": 1}  # 1 + 0 != 3
    r_malo = client.post(f"/api/v1/episodes/{episode_id}/run-tests", json=malo, headers=headers)
    assert r_malo.status_code == 422

    r_bueno = client.post(
        f"/api/v1/episodes/{episode_id}/run-tests", json=_run_tests_body(), headers=headers
    )
    assert r_bueno.status_code == 202, "el claim quedo tomado por una request que no emitio"
    tipos = [ev["event_type"] for ev in fake_ctr.published_events]
    assert tipos.count("tests_ejecutados") == 1
