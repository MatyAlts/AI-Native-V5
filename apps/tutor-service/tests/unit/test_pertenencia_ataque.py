"""Ataque al gate de pertenencia del episodio: lo que `sesion_del_emisor` NO fija.

Complementa `test_pertenencia_del_episodio.py` (que fija el 403 con la sesion
VIVA) atacando los bordes que ese archivo deja abiertos. Tres frentes:

**1. Exhaustividad por construccion.** El agujero original nacio de que cada
emisor hacia su propio `self.sessions.get()` y nadie tenia la lista completa.
Un archivo de tests que enumera nueve rutas a mano hereda ese mismo modo de
falla: la ruta numero diez se agrega y ningun test se pone rojo.
`test_ninguna_ruta_de_escritura_queda_fuera_de_la_matriz` le pide las rutas al
`APIRouter` de verdad y falla si aparece una que esta matriz no cubre.

**2. El heal legitimo, para los NUEVE emisores.** Cerrar el agujero con un 403
para todo el mundo tambien lo cierra, y rompe el producto. La suite del fix
prueba el heal (sesion vencida + dueño correcto -> 202) SOLO en `run-tests`;
los otros ocho pasan por el mismo `_emitir_con_heal` y no tenian nada. Un gate
que devolviera 403 ante `state is None` pasaria los tests de ataque del fix y
dejaria sin trabajar a todo alumno al que se le vencio el TTL de 6h.

**3. La identidad que el deploy emite DE VERDAD.** El api-gateway le pone
`clerk_base_roles = "estudiante,docente"` a TODO usuario logueado
(`api_gateway/config.py`) y despues PISA el header entrante con
`",".join(sorted(principal.roles))` (`jwt_auth.py`). Los fixtures de
`test_pertenencia_del_episodio.py` arman al atacante con `X-User-Roles:
"estudiante"` a secas — una identidad que produccion nunca emite. Acá el
atacante viene con los DOS roles, que es la unica forma de probar que el gate
mira propiedad y no rol. Ver el write-up canonico en
`apps/evaluation-service/tests/unit/test_scope_con_roles_de_produccion.py`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import fakeredis.aioredis
import pytest
from fastapi.testclient import TestClient
from tutor_service.services.clients import PromptConfig, RetrievalResult
from tutor_service.services.session import SessionManager
from tutor_service.services.tutor_core import TUTOR_SERVICE_USER_ID, TutorCore

PROMPT_HASH = "abc" + "0" * 61

# Lo que el gateway inyecta HOY para CUALQUIER usuario logueado con Clerk.
# Un fixture de un solo rol no prueba nada en este deploy.
ROLES_DE_PRODUCCION = "docente,estudiante"


# ── Dobles ────────────────────────────────────────────────────────────


class _FakeGov:
    async def get_prompt(self, name: str, version: str) -> PromptConfig:
        return PromptConfig(name=name, version=version, content="prompt-sistema", hash=PROMPT_HASH)


class _FakeContent:
    async def retrieve(
        self,
        query: str,
        comision_id: UUID,
        top_k: int,
        tenant_id: UUID,
        caller_id: UUID,
        materia_id: UUID | None = None,
    ) -> RetrievalResult:
        return RetrievalResult(chunks=[], chunks_used_hash="d" * 64, latency_ms=1.0)


class _FakeAI:
    async def stream(
        self,
        messages: list[dict],
        model: str,
        tenant_id: UUID,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        materia_id: UUID | None = None,
    ) -> AsyncIterator[dict]:
        yield {"type": "chunk", "content": "respuesta"}


class _FakeCTR:
    def __init__(self) -> None:
        self.published_events: list[dict[str, Any]] = []
        self.episodes: dict[str, dict] = {}

    async def publish_event(self, event: dict, tenant_id: UUID, caller_id: UUID) -> str:
        self.published_events.append(event)
        return f"msg-{len(self.published_events)}"

    async def get_episode(self, episode_id: UUID, tenant_id: UUID, caller_id: UUID) -> dict | None:
        return self.episodes.get(str(episode_id))

    async def find_open_episode(
        self,
        tenant_id: UUID,
        caller_id: UUID,
        student_pseudonym: UUID,
        problema_id: UUID,
        ejercicio_id: UUID | None = None,
    ) -> dict | None:
        return None


def _ts(seq: int) -> str:
    return datetime(2026, 8, 27, 12, 0, seq, tzinfo=UTC).isoformat().replace("+00:00", "Z")


def _episodio_persistido(
    episode_id: UUID,
    tenant_id: UUID,
    student_id: UUID,
    *,
    estado: str = "open",
) -> dict:
    comision_id = uuid4()
    problema_id = uuid4()
    return {
        "id": str(episode_id),
        "tenant_id": str(tenant_id),
        "comision_id": str(comision_id),
        "student_pseudonym": str(student_id),
        "problema_id": str(problema_id),
        "estado": estado,
        "opened_at": _ts(0),
        "closed_at": _ts(1) if estado == "closed" else None,
        "events_count": 1,
        "last_chain_hash": "e" * 64,
        "integrity_compromised": False,
        "prompt_system_hash": PROMPT_HASH,
        "classifier_config_hash": "b" * 64,
        "curso_config_hash": "c" * 64,
        "events": [
            {
                "event_uuid": str(uuid4()),
                "episode_id": str(episode_id),
                "seq": 0,
                "event_type": "episodio_abierto",
                "ts": _ts(0),
                "payload": {
                    "student_pseudonym": str(student_id),
                    "problema_id": str(problema_id),
                    "comision_id": str(comision_id),
                    "curso_config_hash": "c" * 64,
                    "model": "claude-haiku-test",
                    # El codigo del alumno vive en la cadena: es lo que el GET
                    # devuelve como `last_code_snapshot`.
                },
                "prompt_system_hash": PROMPT_HASH,
                "prompt_system_version": "v1.0.0",
                "classifier_config_hash": "b" * 64,
            },
            {
                "event_uuid": str(uuid4()),
                "episode_id": str(episode_id),
                "seq": 1,
                "event_type": "edicion_codigo",
                "ts": _ts(1),
                "payload": {"snapshot": "SECRETO_DE_LA_VICTIMA = 42", "diff_chars": 10},
                "prompt_system_hash": PROMPT_HASH,
                "prompt_system_version": "v1.0.0",
                "classifier_config_hash": "b" * 64,
            },
        ],
    }


# ── Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture
async def redis_client():
    client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    yield client
    await client.aclose()


@pytest.fixture
def fake_ctr() -> _FakeCTR:
    return _FakeCTR()


@pytest.fixture
def tutor(redis_client, fake_ctr) -> TutorCore:
    return TutorCore(
        governance=_FakeGov(),
        content=_FakeContent(),
        ai_gateway=_FakeAI(),
        ctr=fake_ctr,
        sessions=SessionManager(redis_client),
    )


@pytest.fixture
def http(monkeypatch, tutor: TutorCore):
    from tutor_service import main
    from tutor_service.routes import episodes as episodes_module

    monkeypatch.setattr(episodes_module, "_get_tutor", lambda: tutor)
    monkeypatch.setattr(episodes_module, "_get_ctr_client", lambda: tutor.ctr)
    return TestClient(main.app)


def _headers(user_id: UUID, tenant_id: UUID, roles: str = ROLES_DE_PRODUCCION) -> dict[str, str]:
    return {
        "X-User-Id": str(user_id),
        "X-Tenant-Id": str(tenant_id),
        "X-User-Email": "alguien@utn.edu.ar",
        "X-User-Roles": roles,
    }


class _Escenario:
    def __init__(self, episode_id: UUID, victima: UUID, tenant_victima: UUID) -> None:
        self.episode_id = episode_id
        self.victima = victima
        self.tenant_victima = tenant_victima
        self.atacante = uuid4()
        self.tenant_atacante = uuid4()

    @property
    def h_atacante(self) -> dict[str, str]:
        return _headers(self.atacante, self.tenant_victima)

    @property
    def h_atacante_otro_tenant(self) -> dict[str, str]:
        return _headers(self.atacante, self.tenant_atacante)

    @property
    def h_victima(self) -> dict[str, str]:
        return _headers(self.victima, self.tenant_victima)

    @property
    def h_service_account(self) -> dict[str, str]:
        return _headers(TUTOR_SERVICE_USER_ID, self.tenant_victima)


@pytest.fixture
async def escenario(tutor: TutorCore, fake_ctr: _FakeCTR) -> _Escenario:
    victima = uuid4()
    tenant = uuid4()
    episode_id = await tutor.open_episode(
        tenant_id=tenant,
        comision_id=uuid4(),
        student_pseudonym=victima,
        problema_id=uuid4(),
        curso_config_hash="c" * 64,
        classifier_config_hash="b" * 64,
    )
    fake_ctr.episodes[str(episode_id)] = _episodio_persistido(
        episode_id, tenant, victima, estado="open"
    )
    fake_ctr.published_events.clear()  # ignorar el episodio_abierto
    return _Escenario(episode_id, victima, tenant)


# ── La matriz de escritores ───────────────────────────────────────────

# (sufijo de ruta, body, status esperado para el DUEÑO con sesion viva).
# `/message` devuelve 200 (SSE) y `/close` + `/abandoned` 204; el resto 202.
_ESCRITORES: list[tuple[str, dict[str, Any], int]] = [
    (
        "run-tests",
        {
            "test_count_total": 10,
            "test_count_passed": 10,
            "test_count_failed": 0,
            "tests_publicos": 10,
            "tests_hidden": 0,
            "ejecucion_ms": 412,
        },
        202,
    ),
    ("events/codigo_ejecutado", {"code": "print(1)", "duration_ms": 12.0}, 202),
    ("events/edicion_codigo", {"snapshot": "x = 1", "diff_chars": 5}, 202),
    ("events/lectura_enunciado", {"duration_seconds": 30.0}, 202),
    ("events/anotacion_creada", {"contenido": "reflexion fabricada"}, 202),
    ("events/pestana_perdida", {"trigger": "blur"}, 202),
    ("events/pestana_recuperada", {"tiempo_fuera_segundos": 4.0}, 202),
    ("events/copia_intentada", {"seleccion_chars": 10}, 202),
    ("events/pega_intentada", {"contenido_longitud": 10, "contenido_preview": "x"}, 202),
    ("message", {"content": "hola"}, 200),
    ("close", {"reason": "student_closed"}, 204),
    ("abandoned", {"reason": "explicit", "last_activity_seconds_ago": 0.0}, 204),
]

# Los nueve `/events/*` + `run-tests`: los que pasan por `_emitir_con_heal` y
# devuelven 202. Es el subconjunto sobre el que se prueba el auto-heal.
_EMISORES_CON_HEAL = [(r, b) for r, b, code in _ESCRITORES if code == 202]

_IDS = [r for r, _, _ in _ESCRITORES]

# Rutas POST con `{episode_id}` que la matriz NO cubre, con el motivo. Si una
# sale de esta lista y de `_ESCRITORES` a la vez, el guard de exhaustividad
# falla — que es el punto.
_FUERA_DE_LA_MATRIZ = {
    # No emite evento al CTR: reconstruye la sesion Redis. Su gate de dueño es
    # anterior a este fix y tiene cobertura propia en `test_resume_episode.py`.
    "/api/v1/episodes/{episode_id}/resume",
    # Post-cierre, no pasa por la sesion Redis: tiene sus propios tests abajo.
    "/api/v1/episodes/{episode_id}/reflection",
}


def test_ninguna_ruta_de_escritura_queda_fuera_de_la_matriz() -> None:
    """El guard contra el modo de falla que produjo el agujero original.

    Nueve `if` copiados fueron nueve oportunidades de que uno quedara atras, y
    exactamente eso paso. Una lista de rutas escrita a mano en un test tiene la
    misma forma: la ruta numero catorce se agrega, nadie toca este archivo y el
    emisor nuevo entra sin gate y sin test rojo.

    Este test le pregunta al `APIRouter` de produccion, no a una constante.
    """
    from tutor_service.routes import episodes as episodes_module

    del_router = {
        r.path
        for r in episodes_module.router.routes
        if "POST" in (getattr(r, "methods", None) or set()) and "{episode_id}" in r.path
    }
    cubiertas = {f"/api/v1/episodes/{{episode_id}}/{ruta}" for ruta, _, _ in _ESCRITORES}
    sin_cubrir = del_router - cubiertas - _FUERA_DE_LA_MATRIZ

    assert sin_cubrir == set(), (
        f"rutas POST sobre un episodio ajeno que ningun test de pertenencia ataca: "
        f"{sorted(sin_cubrir)}. Agregalas a `_ESCRITORES` o justificalas en "
        f"`_FUERA_DE_LA_MATRIZ`."
    )


# ── 1. El atacante, con la identidad que el gateway emite de verdad ────


@pytest.mark.parametrize("ruta,body,_ok", _ESCRITORES, ids=_IDS)
def test_atacante_con_los_dos_roles_de_produccion_es_403(
    http: TestClient, fake_ctr: _FakeCTR, escenario: _Escenario, ruta: str, body: dict, _ok: int
) -> None:
    """`X-User-Roles: "docente,estudiante"` — lo que el gateway pone SIEMPRE.

    Un docente autenticado tampoco escribe en la cadena de un alumno: la
    trazabilidad N4 pierde sentido si el evento pudo escribirlo alguien que no
    es el alumno. Y como el gateway le da rol `docente` a todo el mundo, un
    gate que hiciera una excepcion por rol seria una excepcion para cualquiera.
    """
    resp = http.post(
        f"/api/v1/episodes/{escenario.episode_id}/{ruta}",
        json=body,
        headers=escenario.h_atacante,
    )
    assert resp.status_code == 403, f"{ruta} status {resp.status_code}: {resp.text[:200]}"
    assert fake_ctr.published_events == [], f"{ruta} appendeo: {fake_ctr.published_events}"


@pytest.mark.parametrize("ruta,body,_ok", _ESCRITORES, ids=_IDS)
def test_atacante_de_otro_tenant_es_403(
    http: TestClient, fake_ctr: _FakeCTR, escenario: _Escenario, ruta: str, body: dict, _ok: int
) -> None:
    """Cross-tenant: el evento salia firmado con el tenant de la VICTIMA.

    `sesion_del_emisor` no compara tenants a proposito (el `student_pseudonym`
    ya lo subsume). Esto fija que esa decision efectivamente cubre el caso.
    """
    resp = http.post(
        f"/api/v1/episodes/{escenario.episode_id}/{ruta}",
        json=body,
        headers=escenario.h_atacante_otro_tenant,
    )
    assert resp.status_code == 403, f"{ruta} status {resp.status_code}: {resp.text[:200]}"
    assert fake_ctr.published_events == []


@pytest.mark.parametrize("ruta,body,esperado", _ESCRITORES, ids=_IDS)
def test_el_dueño_con_sesion_viva_sigue_pasando(
    http: TestClient,
    fake_ctr: _FakeCTR,
    escenario: _Escenario,
    ruta: str,
    body: dict,
    esperado: int,
) -> None:
    """La otra mitad: un 403 universal tambien pasa los dos tests de arriba."""
    resp = http.post(
        f"/api/v1/episodes/{escenario.episode_id}/{ruta}",
        json=body,
        headers=escenario.h_victima,
    )
    assert resp.status_code == esperado, f"{ruta} le rompio el camino al dueño: {resp.text[:200]}"
    assert fake_ctr.published_events != [], f"{ruta} no escribio nada para el dueño"


# ── 2. El auto-heal legitimo, para los NUEVE emisores con heal ────────


@pytest.mark.parametrize("ruta,body", _EMISORES_CON_HEAL, ids=[r for r, _ in _EMISORES_CON_HEAL])
async def test_sesion_vencida_y_dueño_correcto_sigue_sanando(
    http: TestClient,
    tutor: TutorCore,
    fake_ctr: _FakeCTR,
    escenario: _Escenario,
    ruta: str,
    body: dict,
) -> None:
    """El TTL de 6h se vencio y el alumno sigue trabajando: 202, no 403.

    Esta es la mitad que un "fix" perezoso rompe. `sesion_del_emisor` devuelve
    `None` —no 403— cuando no hay sesion, justamente para que
    `_emitir_con_heal` pueda distinguir "recuperable" de "definitivo". Si la
    ausencia empezara a salir como `EpisodioAjenoError`, el heal dejaria de
    correr para los nueve emisores a la vez y el alumno perderia el evento.

    La suite del fix prueba esto SOLO en `run-tests`; los otros nueve comparten
    el mismo `_emitir_con_heal` y no tenian nada que lo fijara.
    """
    await tutor.sessions.delete(escenario.episode_id)

    resp = http.post(
        f"/api/v1/episodes/{escenario.episode_id}/{ruta}",
        json=body,
        headers=escenario.h_victima,
    )

    assert resp.status_code == 202, f"{ruta} rompio el auto-heal del dueño: {resp.text[:200]}"
    assert len(fake_ctr.published_events) == 1, (
        f"{ruta} emitio {len(fake_ctr.published_events)} eventos tras el heal: "
        f"{[e['event_type'] for e in fake_ctr.published_events]}"
    )
    assert await tutor.sessions.get(escenario.episode_id) is not None, (
        f"{ruta} contesto 202 pero no dejo la sesion reconstruida"
    )


@pytest.mark.parametrize("ruta,body", _EMISORES_CON_HEAL, ids=[r for r, _ in _EMISORES_CON_HEAL])
async def test_sesion_vencida_y_atacante_no_resucita_la_sesion_de_la_victima(
    http: TestClient,
    tutor: TutorCore,
    fake_ctr: _FakeCTR,
    escenario: _Escenario,
    ruta: str,
    body: dict,
) -> None:
    """El heal es un escritor de estado, y el atacante no puede dispararlo.

    `resume_episode` reconstruye la sesion con TTL de 6h y repone el contador
    de seq. Que un tercero pueda hacerlo sobre el episodio de otro no escribe
    en la cadena, pero refresca `last_activity_at` y desarma la idempotencia
    del `abandonment_worker` (ADR-025), que esta fundada en que la sesion NO
    exista. Es el mismo daño (b) que el fix del orden de los guards describe,
    por otra puerta.
    """
    await tutor.sessions.delete(escenario.episode_id)

    resp = http.post(
        f"/api/v1/episodes/{escenario.episode_id}/{ruta}",
        json=body,
        headers=escenario.h_atacante,
    )

    assert resp.status_code == 403, f"{ruta} status {resp.status_code}: {resp.text[:200]}"
    assert await tutor.sessions.get(escenario.episode_id) is None, (
        f"{ruta}: el atacante le resucito la sesion a la victima"
    )
    assert fake_ctr.published_events == []


@pytest.mark.parametrize("ruta,body", _EMISORES_CON_HEAL, ids=[r for r, _ in _EMISORES_CON_HEAL])
async def test_el_episodio_ajeno_NO_gatilla_el_heal(
    http: TestClient,
    tutor: TutorCore,
    fake_ctr: _FakeCTR,
    escenario: _Escenario,
    ruta: str,
    body: dict,
    monkeypatch,
) -> None:
    """El tipo de `EpisodioAjenoError` es load-bearing, y nada lo fijaba.

    El docstring de la excepcion declara la razon de ser de que herede de
    `HTTPException` y NO de `ValueError`: «`_emitir_con_heal` trata TODO
    `ValueError` como sesion ausente y arranca el heal. Un episodio ajeno no
    es una sesion que falte: sanarlo no arregla nada y cuesta una lectura de
    la cadena entera del otro alumno.»

    Ese contrato es invisible desde el status code. Con la sesion de la
    victima VIVA, si la excepcion tambien fuera `ValueError` el flujo seria:
    `_emitir_con_heal` la atrapa -> llama `resume_episode` con el `user_id`
    del atacante -> ese `resume_episode` valida dueño y devuelve 403 ->
    `_emitir_con_heal` lo re-propaga. **El status final sigue siendo 403** y
    la cadena sigue intacta, asi que todos los tests de pertenencia —los del
    fix y los de arriba— pasan igual. Lo unico que cambia es que cada request
    ajeno se lleva por delante un `get_episode` completo de la victima:
    amplificacion gratis para quien tenga un `episode_id` y ganas de hacer
    ruido, y una lectura de datos ajenos que no tenia por que ocurrir.

    Verificado con un mutante: cambiar la firma a
    `class EpisodioAjenoError(HTTPException, ValueError)` deja pasar TODA la
    suite salvo los dos tests de `reflection`. Este test es el que lo mata en
    los nueve emisores con heal.
    """
    llamadas: list[UUID] = []

    async def _espia(*, episode_id: UUID, tenant_id: UUID, user_id: UUID):
        llamadas.append(episode_id)
        raise AssertionError("el heal no deberia correr sobre un episodio ajeno")

    monkeypatch.setattr(tutor, "resume_episode", _espia)

    resp = http.post(
        f"/api/v1/episodes/{escenario.episode_id}/{ruta}",
        json=body,
        headers=escenario.h_atacante,
    )

    assert resp.status_code == 403, f"{ruta} status {resp.status_code}: {resp.text[:200]}"
    assert llamadas == [], (
        f"{ruta}: el episodio ajeno gatillo el heal. `EpisodioAjenoError` volvio a ser "
        f"atrapable como `ValueError` — revisá su clase base."
    )
    assert fake_ctr.published_events == []


@pytest.mark.parametrize("ruta,body,_ok", _ESCRITORES, ids=_IDS)
def test_el_403_no_es_un_oraculo_sobre_el_dueño(
    http: TestClient, escenario: _Escenario, ruta: str, body: dict, _ok: int
) -> None:
    """El detalle del 403 no puede nombrar al dueño ni a su tenant.

    El propio `EpisodioAjenoError` justifica su mensaje generico: «El detalle
    NO nombra al dueño ni dice si el episodio existe: el `episode_id` es un
    UUID no adivinable, y un mensaje distinto por caso lo convertiria en
    oraculo». Es una decision de privacidad —los `student_pseudonym` son el
    identificador del alumno en la tesis— y no habia nada que la sostuviera:
    agregarle `dueno={state.student_pseudonym}` al detalle para "debuggear
    mejor" pasaba la suite entera.
    """
    resp = http.post(
        f"/api/v1/episodes/{escenario.episode_id}/{ruta}",
        json=body,
        headers=escenario.h_atacante,
    )
    assert resp.status_code == 403
    cuerpo = resp.text
    assert str(escenario.victima) not in cuerpo, f"{ruta}: el 403 filtro el dueño"
    assert str(escenario.tenant_victima) not in cuerpo, f"{ruta}: el 403 filtro el tenant"
    assert str(escenario.episode_id) not in cuerpo, (
        f"{ruta}: el 403 confirma que el episodio existe repitiendo su id"
    )


# ── 3. Episodio inexistente: 404/409, nunca 403 (no es un oraculo) ────


@pytest.mark.parametrize("ruta,body", _EMISORES_CON_HEAL, ids=[r for r, _ in _EMISORES_CON_HEAL])
def test_episodio_inexistente_no_es_403(
    http: TestClient, fake_ctr: _FakeCTR, ruta: str, body: dict
) -> None:
    """Un `episode_id` que no existe no puede contestar 403.

    Si lo hiciera, el codigo de respuesta seria un oraculo de existencia:
    404 = no existe, 403 = existe y es de otro. El detalle del
    `EpisodioAjenoError` esta deliberadamente redactado para no serlo; el
    status tiene que acompañar.
    """
    resp = http.post(
        f"/api/v1/episodes/{uuid4()}/{ruta}",
        json=body,
        headers=_headers(uuid4(), uuid4()),
    )
    assert resp.status_code in (404, 409), f"{ruta} status {resp.status_code}: {resp.text[:200]}"
    assert fake_ctr.published_events == []


# ── 4. El service-account, que atraviesa el gate por diseño ───────────


@pytest.mark.parametrize("ruta,body,esperado", _ESCRITORES, ids=_IDS)
def test_el_service_account_atraviesa_el_gate_en_TODOS_los_emisores(
    http: TestClient,
    fake_ctr: _FakeCTR,
    escenario: _Escenario,
    ruta: str,
    body: dict,
    esperado: int,
) -> None:
    """Documenta el alcance REAL de la excepcion `TUTOR_SERVICE_USER_ID`.

    El fix la justifica por el `abandonment_worker` y el `distraction_worker`,
    que emiten `episodio_abandonado` — UN emisor. Pero la excepcion vive dentro
    de `sesion_del_emisor`, asi que aplica a los DIEZ (los nueve de arriba mas
    el abandono), y no distingue llamada
    en proceso de request HTTP: cualquier caller que llegue con
    `X-User-Id: 00000000-0000-0000-0000-000000000010` escribe en la cadena de
    cualquier alumno, con el `student_pseudonym` de la victima.

    En produccion no es explotable desde un browser: el api-gateway PISA
    `X-User-Id` con el `sub` del JWT validado (`jwt_auth.py`), y ningun JWT de
    Clerk trae ese UUID. Es explotable desde cualquier cosa que hable con el
    tutor-service sin pasar por el gateway (la red interna: execution-service,
    ctr-service, un pod comprometido) y en cualquier deploy con
    `dev_trust_headers` prendido, donde los headers X-* pasan sin reescribir.

    Este test NO afirma que este bien. Fija el comportamiento vigente para que
    achicarlo —comparar contra la sesion solo en `record_episodio_abandonado`,
    o exigir el `X-Internal-Service-Token` que `run-tests` ya sabe verificar—
    se vea como un cambio deliberado y no como una regresion.
    """
    resp = http.post(
        f"/api/v1/episodes/{escenario.episode_id}/{ruta}",
        json=body,
        headers=escenario.h_service_account,
    )
    assert resp.status_code == esperado, (
        f"{ruta}: el service-account dejo de pasar (status {resp.status_code}). "
        f"Si el cambio fue a proposito, actualiza este test y revisa que el "
        f"abandonment_worker siga cerrando episodios inactivos."
    )
    assert fake_ctr.published_events != []


# ── 5. `reflexion_completada`: la misma regla contra la cadena ────────


def _reflexion() -> dict:
    return {
        "que_aprendiste": "nada",
        "dificultad_encontrada": "nada",
        "que_haria_distinto": "nada",
        "tiempo_completado_ms": 1000,
    }


def test_reflexion_de_otro_tenant_no_escribe(http: TestClient, fake_ctr: _FakeCTR) -> None:
    """El caso cross-tenant de la reflexion, que el fix no cubre con un test.

    `record_reflexion_completada` valida tenant PRIMERO (404) y dueño despues
    (403). El status distinto es correcto —el CTR ni siquiera devuelve el
    episodio de otro tenant— pero lo que importa es lo mismo: nada entra a la
    cadena.
    """
    victima, tenant = uuid4(), uuid4()
    episode_id = uuid4()
    fake_ctr.episodes[str(episode_id)] = _episodio_persistido(
        episode_id, tenant, victima, estado="closed"
    )
    resp = http.post(
        f"/api/v1/episodes/{episode_id}/reflection",
        json=_reflexion(),
        headers=_headers(uuid4(), uuid4()),  # otro alumno, otro tenant
    )
    assert resp.status_code in (403, 404), f"status {resp.status_code}: {resp.text[:200]}"
    assert fake_ctr.published_events == []


def test_el_dueño_sigue_pudiendo_reflexionar(http: TestClient, fake_ctr: _FakeCTR) -> None:
    """La mitad viva: sin esto, un 403 universal en `reflection` pasaria el de arriba."""
    victima, tenant = uuid4(), uuid4()
    episode_id = uuid4()
    fake_ctr.episodes[str(episode_id)] = _episodio_persistido(
        episode_id, tenant, victima, estado="closed"
    )
    resp = http.post(
        f"/api/v1/episodes/{episode_id}/reflection",
        json=_reflexion(),
        headers=_headers(victima, tenant),
    )
    assert resp.status_code == 202, resp.text[:300]
    assert [e["event_type"] for e in fake_ctr.published_events] == ["reflexion_completada"]


def test_la_reflexion_ajena_no_se_cuela_por_el_estado_del_episodio(
    http: TestClient, fake_ctr: _FakeCTR
) -> None:
    """El orden importa: dueño ANTES que estado.

    Si el chequeo de dueño corriera despues del de `estado != "closed"`, un
    episodio ajeno todavia abierto contestaria 409 ("no esta cerrado") y el
    atacante aprenderia el estado del episodio de otro. Peor: cualquier
    reordenamiento futuro que mueva el gate abajo del todo lo deja emitir.
    """
    victima, tenant = uuid4(), uuid4()
    episode_id = uuid4()
    fake_ctr.episodes[str(episode_id)] = _episodio_persistido(
        episode_id, tenant, victima, estado="open"
    )
    resp = http.post(
        f"/api/v1/episodes/{episode_id}/reflection",
        json=_reflexion(),
        headers=_headers(uuid4(), tenant),  # mismo tenant, otro alumno
    )
    assert resp.status_code == 403, (
        f"el episodio ajeno contesto {resp.status_code} en vez de 403: {resp.text[:200]}"
    )
    assert fake_ctr.published_events == []


# ── 6. El camino que NO pasa por el gate: el replay de idempotencia ───


@pytest.mark.parametrize("tenant_propio", [False, True], ids=["mismo-tenant", "otro-tenant"])
async def test_el_replay_de_idempotency_key_ya_pasa_por_el_gate(
    http: TestClient, fake_ctr: _FakeCTR, escenario: _Escenario, tenant_propio: bool
) -> None:
    """FIXEADO el 2026-08-28. Antes habia un camino que salteaba el gate.

    Este test nacio afirmando el comportamiento ROTO, para documentar el
    agujero con codigo en vez de con un parrafo. El fix lo puso rojo, que era
    exactamente la señal acordada, y aca quedo convertido: mismo escenario,
    mismo ataque, assert invertido. El analisis se conserva porque explica
    POR QUE el gate esta donde esta, y eso es lo que impide que alguien lo
    "simplifique" devolviendolo adentro del emit.

    El gate vivia DENTRO del `emit`. La ruta no lo llama directo: llama a
    `_emitir_con_heal` -> `_idempotent_seq` -> `SessionManager.reserve_or_get_seq`,
    y ese metodo **decide antes de correr `emit`**:

        won = await self.redis.hsetnx(seen_key, idempotency_key, PENDING)
        if won: ... emit() ...          <- unico camino con gate
        # perdedor: HGET y devuelve el seq guardado, sin llamar a emit()

    O sea: si la `Idempotency-Key` ya fue usada en ESE episodio, el request
    devolvia 202 con el `seq` de la victima y `sesion_del_emisor` **nunca
    corria**. Valia igual para un alumno de otro tenant — el `seen_key` esta
    indexado solo por `episode_id`.

    Lo que NO pasaba: no entraba nada a la cadena (por eso ese assert sigue).
    Lo que SI pasaba:
      - El endpoint contestaba 202 donde su docstring promete 403.
      - El atacante confirma que el episodio existe y que esa key se uso.
      - Se lleva el `seq` exacto — o sea cuantos eventos tenia la cadena de
        la victima en ese momento. Contando seqs se reconstruye su ritmo de
        trabajo, que es justo el dato que el CTR existe para proteger.

    Explotabilidad: hay que conocer DOS uuid4 (el `episode_id` y el
    `event_uuid` que el ctr-client usa de key). No se adivinan. Pero ninguno
    es secreto por diseño: el `episode_id` vive en el `localStorage` del
    alumno y en las URLs que pega, y la key viaja en un header de cada POST —
    visible en un HAR, en una maquina compartida o en una extension.

    Lo estructural es peor que el caso: **cualquier authz que se ponga dentro
    de `emit` tiene este mismo punto ciego**, porque el corto-circuito de
    idempotencia es anterior. El lugar correcto para el gate de pertenencia
    en las rutas `/events/*` es ANTES de `_emitir_con_heal`, como ya esta en
    `/message` y `/close`.

    El fix: `await _get_tutor().sesion_del_emisor(episode_id, user.id)` como
    primera linea de `_emitir_con_heal`, o sea ANTES del `_idempotent_seq`.
    Ahi y no en la ruta que lo descubrio, porque asi lo heredan los nueve
    emisores que pasan por ese wrapper. Es el mismo lugar del que ya colgaban
    `/message` y `/close`.
    """
    ruta = "events/edicion_codigo"
    body = {"snapshot": "x = 1", "diff_chars": 5}
    key = str(uuid4())

    r_victima = http.post(
        f"/api/v1/episodes/{escenario.episode_id}/{ruta}",
        json=body,
        headers=escenario.h_victima | {"Idempotency-Key": key},
    )
    assert r_victima.status_code == 202, r_victima.text
    eventos_tras_la_victima = len(fake_ctr.published_events)

    headers = escenario.h_atacante_otro_tenant if tenant_propio else escenario.h_atacante
    r_atacante = http.post(
        f"/api/v1/episodes/{escenario.episode_id}/{ruta}",
        json=body,
        headers=headers | {"Idempotency-Key": key},
    )

    assert r_atacante.status_code == 403, (
        f"el replay de un ajeno paso el gate: {r_atacante.status_code} {r_atacante.text[:200]}"
    )
    # Lo que se filtraba no era el evento —nunca entro uno— sino el seq: o sea
    # cuantos eventos tenia la cadena de la victima en ese momento.
    assert r_victima.json()["seq"] not in r_atacante.text, (
        "el 403 sigue devolviendo el seq de la victima: el leak cambio de forma"
    )
    # La mitad que SI se sostiene y no debe perderse cuando esto se arregle:
    # el replay no appendea nada a la cadena append-only.
    assert len(fake_ctr.published_events) == eventos_tras_la_victima, (
        "el replay del atacante appendeo a la cadena de la victima"
    )


# ── 7. La lectura: el gate cubre la escritura, no el GET ──────────────


def test_el_GET_del_episodio_ajeno_ya_no_devuelve_el_codigo_de_la_victima(
    http: TestClient, escenario: _Escenario
) -> None:
    """FIXEADO el 2026-08-28. Antes `GET /episodes/{id}` no miraba dueño.

    Nacio afirmando el comportamiento roto; el fix lo puso rojo y quedo
    convertido. El escenario y el analisis son los mismos: lo unico que
    cambia es que ahora el ataque falla.

    El handler validaba `tenant_id` y nada mas (`routes/episodes.py`,
    `get_episode_state`) — el mismo error de forma que `sesion_del_emisor`
    acaba de cerrar del lado de la escritura: "es de mi tenant" no es "es mio".
    Un compañero de tenant con el `episode_id` de otro se lleva su ultimo
    snapshot de codigo, su conversacion con el tutor y sus notas personales.

    Que el `episode_id` sea un UUID no adivinable NO alcanza: viaja en el
    `localStorage` del alumno, en las URLs que pega en el foro y en cualquier
    log del cliente.

    El fix es `str(ep["student_pseudonym"]) != str(user.id)` -> 403, sin
    excepcion por rol: con `clerk_base_roles = "estudiante,docente"` TODO
    usuario logueado tiene el rol `docente`, asi que un bypass por rol seria
    no tener gate. El panel del docente no se rompe porque no pasa por aca —
    lee episodios por `/api/v1/analytics/...` y `/api/v1/audit/episodes/...`.
    """
    resp = http.get(
        f"/api/v1/episodes/{escenario.episode_id}",
        headers=escenario.h_atacante,  # mismo tenant, NO es el dueño
    )
    assert resp.status_code == 403, (
        f"el episodio ajeno se leyo igual: {resp.status_code} {resp.text[:200]}"
    )
    # Y el codigo de la victima no viaja ni en el cuerpo del rechazo.
    assert "SECRETO_DE_LA_VICTIMA" not in resp.text


def test_el_GET_de_otro_tenant_si_esta_cortado(http: TestClient, escenario: _Escenario) -> None:
    """La mitad que si funciona, para no confundir "no hay gate" con "hay uno parcial"."""
    resp = http.get(
        f"/api/v1/episodes/{escenario.episode_id}",
        headers=escenario.h_atacante_otro_tenant,
    )
    assert resp.status_code in (403, 404), f"status {resp.status_code}: {resp.text[:200]}"
