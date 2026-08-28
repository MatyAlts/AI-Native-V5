"""Tests del endpoint POST /api/v1/episodes/{id}/events/edicion_codigo.

Crítico para CCD (Code-Discourse Coherence): sin estos eventos, el
clasificador no puede distinguir "tipeando/pensando" de "idle".

Cubre:
  1. Happy path — POST devuelve 202 con seq, CTR mock recibió payload correcto.
  2. Episodio cerrado/inexistente — POST devuelve 409.
  3. Snapshot demasiado grande (>50000 chars) — POST devuelve 422.
  4. diff_chars negativo — POST devuelve 422.
  5. Service method publica con user_id del estudiante (no service account).
  6. Service method asigna seq consecutivo respecto a otros eventos.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import UUID, uuid4

import fakeredis.aioredis
import pytest
from fastapi.testclient import TestClient
from tutor_service.services.clients import (
    PromptConfig,
    RetrievalResult,
)
from tutor_service.services.session import SessionManager
from tutor_service.services.tutor_core import TUTOR_SERVICE_USER_ID, TutorCore

# ── Mocks de los clientes externos ────────────────────────────────────


class FakeGovernanceClient:
    async def get_prompt(self, name: str, version: str) -> PromptConfig:
        return PromptConfig(
            name=name,
            version=version,
            content="Eres un tutor socrático.",
            hash="abc" + "0" * 61,
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
        # Backlog QA 2026-05-07: nuevo contrato — yieldea dicts.
        yield {"type": "chunk", "content": "ok"}


class FakeCTRClient:
    def __init__(self) -> None:
        self.published_events: list[dict] = []
        self.captured_callers: list[UUID] = []
        self.episodes: dict[str, dict] = {}

    async def publish_event(self, event: dict, tenant_id: UUID, caller_id: UUID) -> str:
        self.published_events.append(event)
        self.captured_callers.append(caller_id)
        return f"fake-msg-id-{len(self.published_events)}"

    async def get_episode(self, episode_id: UUID, tenant_id: UUID, caller_id: UUID) -> dict | None:
        """Lo consulta `resume_episode`, que es lo que corre cuando el handler
        de un evento no encuentra la sesión y tiene que reconstruirla."""
        return self.episodes.get(str(episode_id))


# ── Fixtures ────────────────────────────────────────────────────────


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


# ── Tests del service method (record_edicion_codigo) ─────────────────


async def test_edicion_codigo_publica_evento_con_seq_correcto(
    tutor: TutorCore, fake_ctr: FakeCTRClient
) -> None:
    """El evento se publica con el siguiente seq del episodio."""
    tenant_id = uuid4()
    # El emisor tiene que ser el DUEÑO del episodio: desde el gate de
    # pertenencia (`TutorCore.sesion_del_emisor`) un `user_id` cualquiera
    # sobre el episodio de otro alumno es 403, no un evento en su cadena.
    student_id = uuid4()
    episode_id = await tutor.open_episode(
        tenant_id=tenant_id,
        comision_id=uuid4(),
        student_pseudonym=student_id,
        problema_id=uuid4(),
        curso_config_hash="c" * 64,
        classifier_config_hash="b" * 64,
    )
    # seq=0: episodio_abierto

    seq = await tutor.record_edicion_codigo(
        episode_id=episode_id,
        snapshot="def foo():\n    return 42\n",
        diff_chars=10,
        language="python",
        user_id=student_id,
    )

    assert seq == 1
    assert len(fake_ctr.published_events) == 2
    ev = fake_ctr.published_events[1]
    assert ev["event_type"] == "edicion_codigo"
    assert ev["seq"] == 1
    assert ev["payload"]["snapshot"] == "def foo():\n    return 42\n"
    assert ev["payload"]["diff_chars"] == 10
    assert ev["payload"]["language"] == "python"


async def test_edicion_codigo_usa_user_id_del_estudiante_no_el_tutor(
    tutor: TutorCore, fake_ctr: FakeCTRClient
) -> None:
    """El evento se publica con el user_id del estudiante, no el service account."""
    student_id = uuid4()
    episode_id = await tutor.open_episode(
        tenant_id=uuid4(),
        comision_id=uuid4(),
        student_pseudonym=student_id,
        problema_id=uuid4(),
        curso_config_hash="c" * 64,
        classifier_config_hash="b" * 64,
    )
    # caller[0] = TUTOR_SERVICE_USER_ID (episodio_abierto)
    assert fake_ctr.captured_callers[0] == TUTOR_SERVICE_USER_ID

    await tutor.record_edicion_codigo(
        episode_id=episode_id,
        snapshot="x = 1",
        diff_chars=5,
        language="python",
        user_id=student_id,
    )
    # caller[1] = student_id (edicion_codigo)
    assert fake_ctr.captured_callers[1] == student_id
    assert fake_ctr.captured_callers[1] != TUTOR_SERVICE_USER_ID


async def test_edicion_codigo_episodio_cerrado_falla_value_error(
    tutor: TutorCore,
) -> None:
    """Después de cerrar el episodio, record_edicion_codigo levanta ValueError."""
    episode_id = await tutor.open_episode(
        tenant_id=uuid4(),
        comision_id=uuid4(),
        student_pseudonym=uuid4(),
        problema_id=uuid4(),
        curso_config_hash="c" * 64,
        classifier_config_hash="b" * 64,
    )
    await tutor.close_episode(episode_id)

    with pytest.raises(ValueError, match="no existe"):
        await tutor.record_edicion_codigo(
            episode_id=episode_id,
            snapshot="x = 1",
            diff_chars=1,
            language="python",
            user_id=uuid4(),
        )


# ── Tests del endpoint HTTP (POST /events/edicion_codigo) ────────────


@pytest.fixture
def http_client(monkeypatch, fake_ctr: FakeCTRClient, redis_client):
    """TestClient con dependencias del tutor-core mockeadas.

    Reemplaza el singleton _get_tutor para inyectar fakes.
    """
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
    # Compartir el tutor para que el test pueda preparar episodios
    yield TestClient(main.app), fake_tutor


def _episodio_en_ctr(episode_id, tenant_id, student_id, estado: str, events_count: int = 1) -> dict:
    """Lo que `resume_episode` consulta al CTR antes de reconstruir la sesión.

    Sin esto el fake devuelve `None` y todo cae en «episodio no encontrado»
    (404), sin distinguir un episodio CERRADO de uno INEXISTENTE — que es lo
    que estos tests dicen probar.
    """
    return {
        "id": str(episode_id),
        "tenant_id": str(tenant_id),
        "comision_id": str(uuid4()),
        "student_pseudonym": str(student_id),
        "problema_id": str(uuid4()),
        "estado": estado,
        "events_count": events_count,
        "prompt_system_hash": "a" * 64,
        "prompt_system_version": "v1.0.0",
        "classifier_config_hash": "b" * 64,
        "curso_config_hash": "c" * 64,
        "model": "fake-model",
        "events": [],
    }


def _student_headers(user_id: UUID, tenant_id: UUID) -> dict[str, str]:
    return {
        "X-User-Id": str(user_id),
        "X-Tenant-Id": str(tenant_id),
        "X-User-Email": "alumno@utn.edu.ar",
        "X-User-Roles": "estudiante",
    }


async def test_edicion_codigo_happy_path_returns_202(http_client, fake_ctr: FakeCTRClient) -> None:
    """POST /events/edicion_codigo devuelve 202 con seq y publica al CTR."""
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

    response = client.post(
        f"/api/v1/episodes/{episode_id}/events/edicion_codigo",
        json={
            "snapshot": "print('hola')",
            "diff_chars": 13,
            "language": "python",
        },
        headers=_student_headers(student_id, tenant_id),
    )
    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "accepted"
    assert body["seq"] == "1"

    # CTR recibió el evento con payload correcto
    edicion_events = [e for e in fake_ctr.published_events if e["event_type"] == "edicion_codigo"]
    assert len(edicion_events) == 1
    payload = edicion_events[0]["payload"]
    assert payload["snapshot"] == "print('hola')"
    assert payload["diff_chars"] == 13
    assert payload["language"] == "python"


async def test_edicion_codigo_episode_closed_falla_409(http_client, fake_ctr) -> None:
    """POST después de cerrar el episodio devuelve 409 Conflict."""
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
    await tutor.close_episode(episode_id)
    # El CTR lo conoce y lo reporta CERRADO: asi el 409 sale del estado
    # del episodio y no de que la sesion no exista.
    fake_ctr.episodes[str(episode_id)] = _episodio_en_ctr(
        episode_id, tenant_id, student_id, estado="closed"
    )

    response = client.post(
        f"/api/v1/episodes/{episode_id}/events/edicion_codigo",
        json={"snapshot": "x = 1", "diff_chars": 5, "language": "python"},
        headers=_student_headers(student_id, tenant_id),
    )
    assert response.status_code == 409
    # El motivo ahora es el ESTADO del episodio, no que falte la sesion: el
    # handler intento reconstruirla y `resume_episode` se nego porque esta
    # cerrado. Es la distincion que antes no se hacia.
    detalle = response.json()["detail"].lower()
    assert "closed" in detalle or "cerrado" in detalle


async def test_edicion_codigo_episode_inexistente_falla_404(http_client) -> None:
    """POST a un episode_id que nunca se abrió también devuelve 409."""
    client, _tutor = http_client
    response = client.post(
        f"/api/v1/episodes/{uuid4()}/events/edicion_codigo",
        json={"snapshot": "x = 1", "diff_chars": 5, "language": "python"},
        headers=_student_headers(uuid4(), uuid4()),
    )
    assert response.status_code == 404


async def test_edicion_codigo_snapshot_too_large_422(http_client) -> None:
    """Snapshot >50000 chars debe rechazarse con 422 antes de tocar el CTR."""
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

    response = client.post(
        f"/api/v1/episodes/{episode_id}/events/edicion_codigo",
        json={
            "snapshot": "x" * 50001,  # 1 char sobre el límite
            "diff_chars": 1,
            "language": "python",
        },
        headers=_student_headers(student_id, tenant_id),
    )
    assert response.status_code == 422


async def test_edicion_codigo_diff_chars_negativo_422(http_client) -> None:
    """diff_chars negativo debe rechazarse con 422."""
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

    response = client.post(
        f"/api/v1/episodes/{episode_id}/events/edicion_codigo",
        json={"snapshot": "x = 1", "diff_chars": -1, "language": "python"},
        headers=_student_headers(student_id, tenant_id),
    )
    assert response.status_code == 422


async def test_edicion_codigo_origin_se_propaga_al_payload(
    tutor: TutorCore, fake_ctr: FakeCTRClient
) -> None:
    """F6: si se pasa origin, llega al payload del evento; si es None se omite."""
    student_id = uuid4()
    episode_id = await tutor.open_episode(
        tenant_id=uuid4(),
        comision_id=uuid4(),
        student_pseudonym=student_id,
        problema_id=uuid4(),
        curso_config_hash="c" * 64,
        classifier_config_hash="b" * 64,
    )

    await tutor.record_edicion_codigo(
        episode_id=episode_id,
        snapshot="x = 1",
        diff_chars=5,
        language="python",
        user_id=student_id,
        origin="pasted_external",
    )
    pasted = next(
        e
        for e in fake_ctr.published_events
        if e["event_type"] == "edicion_codigo" and e["payload"].get("origin") == "pasted_external"
    )
    assert pasted["payload"]["origin"] == "pasted_external"

    await tutor.record_edicion_codigo(
        episode_id=episode_id,
        snapshot="y = 2",
        diff_chars=5,
        language="python",
        user_id=student_id,
        # origin omitido (default None) — no debe aparecer en el payload
    )
    no_origin_events = [
        e
        for e in fake_ctr.published_events
        if e["event_type"] == "edicion_codigo" and "origin" not in e["payload"]
    ]
    assert len(no_origin_events) >= 1


async def test_edicion_codigo_origin_via_http_endpoint(
    http_client, fake_ctr: FakeCTRClient
) -> None:
    """F6: el endpoint acepta `origin` y lo propaga; rechaza valores inválidos."""
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

    # Happy path: origin válido se acepta y propaga
    response = client.post(
        f"/api/v1/episodes/{episode_id}/events/edicion_codigo",
        json={
            "snapshot": "x = 1",
            "diff_chars": 5,
            "language": "python",
            "origin": "student_typed",
        },
        headers=_student_headers(student_id, tenant_id),
    )
    assert response.status_code == 202
    typed = next(
        e
        for e in fake_ctr.published_events
        if e["event_type"] == "edicion_codigo" and e["payload"].get("origin") == "student_typed"
    )
    assert typed["payload"]["origin"] == "student_typed"

    # Origin inválido → 422
    response = client.post(
        f"/api/v1/episodes/{episode_id}/events/edicion_codigo",
        json={
            "snapshot": "z = 3",
            "diff_chars": 5,
            "language": "python",
            "origin": "from_alien_planet",
        },
        headers=_student_headers(student_id, tenant_id),
    )
    assert response.status_code == 422


async def test_edicion_codigo_language_default_python(http_client, fake_ctr: FakeCTRClient) -> None:
    """Si no se manda `language`, debe defaultear a 'python'."""
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

    response = client.post(
        f"/api/v1/episodes/{episode_id}/events/edicion_codigo",
        json={"snapshot": "y = 2", "diff_chars": 5},
        headers=_student_headers(student_id, tenant_id),
    )
    assert response.status_code == 202
    edicion = [e for e in fake_ctr.published_events if e["event_type"] == "edicion_codigo"]
    assert edicion[0]["payload"]["language"] == "python"


# ── Tests del endpoint POST /events/anotacion_creada (AnotacionCreada) ─
#
# Crítico para CCD orphan ratio: sin la señal explícita de reflexión, los
# episodios reflexivos quedan marcados como huérfanos de evidencia.


async def test_anotacion_happy_path(http_client, fake_ctr: FakeCTRClient) -> None:
    """POST /events/anotacion_creada devuelve 202 con seq y publica al CTR
    con event_type=anotacion_creada y user_id del estudiante (no service account)."""
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

    contenido = "Aprendí que la recursión termina cuando hay caso base."
    response = client.post(
        f"/api/v1/episodes/{episode_id}/events/anotacion_creada",
        json={"contenido": contenido},
        headers=_student_headers(student_id, tenant_id),
    )
    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "accepted"
    assert body["seq"] == "1"

    # CTR recibió el evento con payload correcto y `words` calculado
    notas = [e for e in fake_ctr.published_events if e["event_type"] == "anotacion_creada"]
    assert len(notas) == 1
    payload = notas[0]["payload"]
    assert payload["content"] == contenido
    assert payload["words"] == len(contenido.split())

    # caller_id de la nota = student_id (no service account)
    nota_index = fake_ctr.published_events.index(notas[0])
    assert fake_ctr.captured_callers[nota_index] == student_id
    assert fake_ctr.captured_callers[nota_index] != TUTOR_SERVICE_USER_ID


async def test_anotacion_vacia_falla_422(http_client) -> None:
    """contenido vacío debe rechazarse con 422 (min_length=1)."""
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

    response = client.post(
        f"/api/v1/episodes/{episode_id}/events/anotacion_creada",
        json={"contenido": ""},
        headers=_student_headers(student_id, tenant_id),
    )
    assert response.status_code == 422


async def test_anotacion_solo_whitespace_falla_422(http_client) -> None:
    """contenido sólo whitespace debe rechazarse — no aporta señal de reflexión."""
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

    response = client.post(
        f"/api/v1/episodes/{episode_id}/events/anotacion_creada",
        json={"contenido": "   \n\t  "},
        headers=_student_headers(student_id, tenant_id),
    )
    assert response.status_code == 422


async def test_anotacion_demasiado_larga_falla_422(http_client) -> None:
    """contenido >5000 chars debe rechazarse con 422 antes de tocar el CTR."""
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

    response = client.post(
        f"/api/v1/episodes/{episode_id}/events/anotacion_creada",
        json={"contenido": "x" * 5001},  # 1 char sobre el límite
        headers=_student_headers(student_id, tenant_id),
    )
    assert response.status_code == 422


async def test_anotacion_episode_closed_falla_409(http_client, fake_ctr) -> None:
    """POST después de cerrar el episodio devuelve 409 Conflict."""
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
    await tutor.close_episode(episode_id)
    # El CTR lo conoce y lo reporta CERRADO: asi el 409 sale del estado
    # del episodio y no de que la sesion no exista.
    fake_ctr.episodes[str(episode_id)] = _episodio_en_ctr(
        episode_id, tenant_id, student_id, estado="closed"
    )

    response = client.post(
        f"/api/v1/episodes/{episode_id}/events/anotacion_creada",
        json={"contenido": "Reflexión post-cierre"},
        headers=_student_headers(student_id, tenant_id),
    )
    assert response.status_code == 409


async def test_anotacion_record_service_method_publica_seq_consecutivo(
    tutor: TutorCore, fake_ctr: FakeCTRClient
) -> None:
    """Service method directo: AsyncMock-style verificación de orden de seqs.

    Intercala anotacion_creada con codigo_ejecutado y confirma seqs
    consecutivos (mismo invariante que los demás eventos del CTR).
    """
    # Mock del session.delete para evitar la dependencia full open
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
    # seq=0: episodio_abierto

    seq_anot = await tutor.record_anotacion_creada(
        episode_id=episode_id,
        contenido="Mi primera reflexión",
        user_id=student_id,
    )
    # seq=1: anotacion_creada
    assert seq_anot == 1

    seq_code = await tutor.emit_codigo_ejecutado(
        episode_id=episode_id,
        user_id=student_id,
        payload={"code": "x=1", "stdout": "", "stderr": "", "duration_ms": 1.0},
    )
    # seq=2: codigo_ejecutado
    assert seq_code == 2

    seq_anot2 = await tutor.record_anotacion_creada(
        episode_id=episode_id,
        contenido="Segunda reflexión después del código",
        user_id=student_id,
    )
    # seq=3: anotacion_creada
    assert seq_anot2 == 3

    seqs = [ev["seq"] for ev in fake_ctr.published_events]
    types = [ev["event_type"] for ev in fake_ctr.published_events]
    assert seqs == [0, 1, 2, 3]
    assert types == [
        "episodio_abierto",
        "anotacion_creada",
        "codigo_ejecutado",
        "anotacion_creada",
    ]


async def test_anotacion_words_count_es_correcto(tutor: TutorCore, fake_ctr: FakeCTRClient) -> None:
    """`words` en el payload debe coincidir con len(contenido.split())."""
    student_id = uuid4()
    episode_id = await tutor.open_episode(
        tenant_id=uuid4(),
        comision_id=uuid4(),
        student_pseudonym=student_id,
        problema_id=uuid4(),
        curso_config_hash="c" * 64,
        classifier_config_hash="b" * 64,
    )

    contenido = "uno  dos\ttres\ncuatro cinco"  # 5 palabras (split colapsa whitespace)
    await tutor.record_anotacion_creada(
        episode_id=episode_id,
        contenido=contenido,
        user_id=student_id,
    )

    nota = next(e for e in fake_ctr.published_events if e["event_type"] == "anotacion_creada")
    assert nota["payload"]["words"] == 5
    assert nota["payload"]["content"] == contenido


# ── Tests del endpoint POST /events/lectura_enunciado (F5) ─────────────
#
# Crítico para N1 (Comprensión): mide tiempo de permanencia en el panel
# del enunciado. Sin esta señal, N1 queda casi sin evidencia observable.


async def test_lectura_enunciado_happy_path(http_client, fake_ctr: FakeCTRClient) -> None:
    """POST /events/lectura_enunciado devuelve 202 con seq, publica al CTR
    con event_type=lectura_enunciado y user_id del estudiante."""
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

    response = client.post(
        f"/api/v1/episodes/{episode_id}/events/lectura_enunciado",
        json={"duration_seconds": 42.5},
        headers=_student_headers(student_id, tenant_id),
    )
    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "accepted"
    assert body["seq"] == "1"

    lecturas = [e for e in fake_ctr.published_events if e["event_type"] == "lectura_enunciado"]
    assert len(lecturas) == 1
    assert lecturas[0]["payload"]["duration_seconds"] == 42.5
    # Caller debe ser el estudiante, no el service account del tutor
    idx = fake_ctr.published_events.index(lecturas[0])
    assert fake_ctr.captured_callers[idx] == student_id
    assert fake_ctr.captured_callers[idx] != TUTOR_SERVICE_USER_ID


async def test_lectura_enunciado_episodio_cerrado_409(http_client, fake_ctr) -> None:
    """POST después de cerrar el episodio devuelve 409."""
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
    await tutor.close_episode(episode_id)
    # El CTR lo conoce y lo reporta CERRADO: asi el 409 sale del estado
    # del episodio y no de que la sesion no exista.
    fake_ctr.episodes[str(episode_id)] = _episodio_en_ctr(
        episode_id, tenant_id, student_id, estado="closed"
    )

    response = client.post(
        f"/api/v1/episodes/{episode_id}/events/lectura_enunciado",
        json={"duration_seconds": 10},
        headers=_student_headers(student_id, tenant_id),
    )
    assert response.status_code == 409


async def test_lectura_enunciado_duration_negativa_422(http_client) -> None:
    """duration_seconds negativo debe rechazarse con 422."""
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

    response = client.post(
        f"/api/v1/episodes/{episode_id}/events/lectura_enunciado",
        json={"duration_seconds": -5},
        headers=_student_headers(student_id, tenant_id),
    )
    assert response.status_code == 422


async def test_lectura_enunciado_duration_demasiado_grande_422(
    http_client,
) -> None:
    """duration_seconds >86400 (un día) debe rechazarse — sanity cap."""
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

    response = client.post(
        f"/api/v1/episodes/{episode_id}/events/lectura_enunciado",
        json={"duration_seconds": 100_000},
        headers=_student_headers(student_id, tenant_id),
    )
    assert response.status_code == 422


async def test_evento_reconstruye_la_sesion_ausente_en_vez_de_rechazar(
    http_client, fake_ctr: FakeCTRClient
) -> None:
    """Si la sesión no está pero el episodio vive, el handler la reconstruye y
    el evento entra. No devuelve 409.

    Es la pieza que sostiene todo el heal, y la distinción importa más de lo
    que parece: el `ctr-client` trata cualquier 4xx que no sea 408/429 como
    definitivo y **descarta el evento de su cola**. Un 409 acá no sería «te
    aviso»: sería tirar el trabajo del alumno justo cuando el sistema está
    recuperándose de una desincronización.

    La sesión puede faltar por TTL vencido o porque el `partition_worker`
    intervino tras un evento que no entró en la cadena. En los dos casos el
    episodio sigue vivo y el alumno sigue escribiendo.
    """
    client, tutor = http_client
    tenant_id, student_id = uuid4(), uuid4()
    comision_id, problema_id = uuid4(), uuid4()

    episode_id = await tutor.open_episode(
        tenant_id=tenant_id,
        comision_id=comision_id,
        student_pseudonym=student_id,
        problema_id=problema_id,
        curso_config_hash="c" * 64,
        classifier_config_hash="b" * 64,
    )

    # El CTR conoce el episodio: sigue abierto, con la apertura persistida.
    fake_ctr.episodes[str(episode_id)] = {
        "id": str(episode_id),
        "tenant_id": str(tenant_id),
        "comision_id": str(comision_id),
        "student_pseudonym": str(student_id),
        "problema_id": str(problema_id),
        "estado": "open",
        "events_count": 1,
        "prompt_system_hash": "a" * 64,
        "prompt_system_version": "v1.0.0",
        "classifier_config_hash": "b" * 64,
        "curso_config_hash": "c" * 64,
        "model": "fake-model",
        "events": [],
    }

    # Desaparece la sesión: TTL vencido, o el worker la dejó sin contador
    # válido tras mandar un evento a la DLQ.
    await tutor.sessions.delete(episode_id)
    assert await tutor.sessions.get(episode_id) is None

    response = client.post(
        f"/api/v1/episodes/{episode_id}/events/edicion_codigo",
        json={"snapshot": "print('sigo trabajando')", "diff_chars": 22, "language": "python"},
        headers=_student_headers(student_id, tenant_id),
    )

    assert response.status_code == 202, (
        "sin el heal esto seria 409 y el ctr-client descartaria el evento"
    )

    # Y la sesión quedó reconstruida desde el `events_count` persistido, así
    # que el seq que se asignó es el que la cadena espera a continuación.
    assert response.json()["seq"] == "1"
    assert await tutor.sessions.get(episode_id) is not None

    edicion = [e for e in fake_ctr.published_events if e["event_type"] == "edicion_codigo"]
    assert len(edicion) == 1
    assert edicion[0]["payload"]["snapshot"] == "print('sigo trabajando')"
