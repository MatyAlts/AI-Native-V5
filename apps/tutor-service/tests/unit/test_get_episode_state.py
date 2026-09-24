"""Tests del endpoint GET /api/v1/episodes/{episode_id}.

Verifica que el wrapper en tutor-service:
  - reconstruye el `EpisodeStateResponse` con messages/notes/last_code
    a partir del `EpisodeWithEvents` que devuelve el ctr-service,
  - propaga 404 si el ctr-service no encuentra el episodio,
  - bloquea con 403 si el episodio pertenece a otro tenant (defensa en
    profundidad — RLS debería filtrarlo aguas abajo),
  - sigue devolviendo el estado aún si el episodio está cerrado (la UI
    lo muestra en modo lectura para review).

El CTRClient está mockeado con AsyncMock — no hay tráfico HTTP real.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from tutor_service.main import app
from tutor_service.routes import episodes as episodes_route

TENANT_HEADERS = {
    # Headers de service-account para bypassear el JWT (mismo path que
    # los frontends en dev — ver auth/dependencies.get_current_user).
    "X-User-Id": "11111111-1111-1111-1111-111111111111",
    "X-Tenant-Id": "22222222-2222-2222-2222-222222222222",
    "X-User-Email": "estudiante@test.local",
    "X-User-Roles": "estudiante",
}

USER_TENANT = UUID("22222222-2222-2222-2222-222222222222")
OTHER_TENANT = UUID("99999999-9999-9999-9999-999999999999")
# El dueño del episodio en el camino feliz: el MISMO que manda el request.
# Hasta el 2026-08-28 el helper le ponia un `uuid4()` al azar y el endpoint no
# miraba dueño, asi que "happy path" era en realidad un alumno leyendo el
# episodio de un desconocido — y pasaba.
USER_ID = UUID("11111111-1111-1111-1111-111111111111")


@pytest.fixture
async def client() -> AsyncClient:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.fixture
def ctr_mock(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    """Sustituye `_get_ctr_client()` por un AsyncMock.

    El endpoint `get_episode_state` lo llama para fetchar el episodio
    desde ctr-service. Con el mock no hace HTTP real.

    `find_closed_episode` (REAPERTURA, Mejora 2) default a `None` — "no hay
    episodio cerrado previo que matchee" — porque `AsyncMock()` sin configurar
    devuelve otro Mock truthy, y el código lo trataría como un match real
    (`closed_match["episode_id"]`) rompiendo todo test que no seteé esta
    rama explícitamente.
    """
    mock = AsyncMock()
    mock.find_closed_episode.return_value = None
    monkeypatch.setattr(episodes_route, "_get_ctr_client", lambda: mock)
    return mock


def _make_ctr_episode(
    *,
    episode_id: UUID,
    tenant_id: UUID,
    comision_id: UUID,
    problema_id: UUID,
    estado: str = "open",
    opened_at: datetime | None = None,
    closed_at: datetime | None = None,
    events: list[dict[str, Any]] | None = None,
    student_pseudonym: UUID | None = None,
) -> dict[str, Any]:
    """Construye el dict que el ctr-service devolvería en GET /episodes/{id}."""
    opened = opened_at or datetime.now(UTC)
    return {
        "id": str(episode_id),
        "tenant_id": str(tenant_id),
        "comision_id": str(comision_id),
        "student_pseudonym": str(student_pseudonym or USER_ID),
        "problema_id": str(problema_id),
        "estado": estado,
        "opened_at": opened.isoformat().replace("+00:00", "Z"),
        "closed_at": (closed_at.isoformat().replace("+00:00", "Z") if closed_at else None),
        "events_count": len(events or []),
        "last_chain_hash": "f" * 64,
        "integrity_compromised": False,
        "prompt_system_hash": "a" * 64,
        "classifier_config_hash": "b" * 64,
        "curso_config_hash": "c" * 64,
        "events": events or [],
    }


def _ev(
    seq: int, event_type: str, payload: dict[str, Any], ts: datetime | None = None
) -> dict[str, Any]:
    ts = ts or datetime.now(UTC)
    return {
        "event_uuid": str(uuid4()),
        "episode_id": str(uuid4()),
        "seq": seq,
        "event_type": event_type,
        "ts": ts.isoformat().replace("+00:00", "Z"),
        "payload": payload,
        "self_hash": "0" * 64,
        "chain_hash": "0" * 64,
        "prev_chain_hash": "0" * 64,
        "prompt_system_hash": "a" * 64,
        "prompt_system_version": "v1.0.0",
        "classifier_config_hash": "b" * 64,
        "persisted_at": ts.isoformat().replace("+00:00", "Z"),
    }


# ── Tests ────────────────────────────────────────────────────────────


async def test_get_episode_state_happy_path(client: AsyncClient, ctr_mock: AsyncMock) -> None:
    """Episodio abierto con prompts/respuestas/edición/nota → state
    reconstruído correctamente con todos los campos."""
    episode_id = uuid4()
    comision_id = uuid4()
    problema_id = uuid4()
    opened = datetime.now(UTC)

    events = [
        _ev(0, "episodio_abierto", {"problema_id": str(problema_id)}),
        _ev(1, "prompt_enviado", {"content": "¿cómo defino una función?"}),
        _ev(
            2,
            "tutor_respondio",
            {"content": "Una función se define con `def nombre():`"},
        ),
        _ev(3, "edicion_codigo", {"snapshot": "def hola():\n    pass\n"}),
        _ev(
            4,
            "codigo_ejecutado",
            {
                "code": "def hola():\n    print('hola')\n\nhola()\n",
                "stdout": "hola\n",
                "stderr": "",
                "duration_ms": 12.5,
            },
        ),
        # El shape REAL que emite `record_anotacion_creada` y que define
        # `AnotacionCreadaPayload`. Antes este fixture inventaba
        # `nota_personal` / `contenido`, que no existen en produccion: el
        # test pasaba porque el dato fabricado coincidia con un filtro roto,
        # mientras las notas de los alumnos nunca se reconstruian.
        _ev(5, "anotacion_creada", {"content": "Recordar usar print() siempre", "words": 4}),
    ]
    ctr_mock.get_episode.return_value = _make_ctr_episode(
        episode_id=episode_id,
        tenant_id=USER_TENANT,
        comision_id=comision_id,
        problema_id=problema_id,
        opened_at=opened,
        events=events,
    )

    resp = await client.get(f"/api/v1/episodes/{episode_id}", headers=TENANT_HEADERS)

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["episode_id"] == str(episode_id)
    assert data["tarea_practica_id"] == str(problema_id)
    assert data["comision_id"] == str(comision_id)
    assert data["estado"] == "open"
    assert data["closed_at"] is None
    # last_code_snapshot debe ser el del último evento de código (seq=4)
    assert data["last_code_snapshot"] == ("def hola():\n    print('hola')\n\nhola()\n")
    # 1 user + 1 assistant
    assert len(data["messages"]) == 2
    assert data["messages"][0]["role"] == "user"
    assert data["messages"][0]["content"] == "¿cómo defino una función?"
    assert data["messages"][1]["role"] == "assistant"
    assert "función" in data["messages"][1]["content"]
    # 1 nota personal
    assert len(data["notes"]) == 1
    assert data["notes"][0]["contenido"] == "Recordar usar print() siempre"

    # Verificamos que se llamó al ctr-service con el tenant correcto
    ctr_mock.get_episode.assert_awaited_once()
    call = ctr_mock.get_episode.await_args
    assert call.kwargs["episode_id"] == episode_id
    assert call.kwargs["tenant_id"] == USER_TENANT


async def test_get_episode_state_not_found_404(client: AsyncClient, ctr_mock: AsyncMock) -> None:
    """Si ctr-service responde 404 (CTRClient.get_episode → None),
    el wrapper también responde 404."""
    ctr_mock.get_episode.return_value = None

    resp = await client.get(f"/api/v1/episodes/{uuid4()}", headers=TENANT_HEADERS)

    assert resp.status_code == 404
    assert "no encontrado" in resp.json()["detail"]


async def test_get_episode_state_otro_tenant_403(client: AsyncClient, ctr_mock: AsyncMock) -> None:
    """Defensa en profundidad: si el ctr-service devuelve un episodio
    cuyo tenant_id no matchea con el del user, el wrapper bloquea con
    403 (RLS debería haberlo filtrado, pero por las dudas)."""
    episode_id = uuid4()
    ctr_mock.get_episode.return_value = _make_ctr_episode(
        episode_id=episode_id,
        tenant_id=OTHER_TENANT,  # distinto al del request
        comision_id=uuid4(),
        problema_id=uuid4(),
    )

    resp = await client.get(f"/api/v1/episodes/{episode_id}", headers=TENANT_HEADERS)

    assert resp.status_code == 403
    assert "tenant" in resp.json()["detail"].lower()


async def test_un_companiero_del_mismo_tenant_no_puede_leer_el_episodio(
    client: AsyncClient, ctr_mock: AsyncMock
) -> None:
    """El agujero real: el gate de tenant no separa alumnos entre si.

    En produccion TODOS los alumnos y docentes viven en el MISMO tenant
    (ADR-001: RLS aisla tenants, no comisiones). Asi que "es de mi tenant"
    no era una autorizacion: era casi una tautologia. Un compañero que
    conociera el `episode_id` se llevaba el ultimo snapshot de codigo, la
    conversacion entera con el tutor y las notas del episodio ajeno.

    El gate de ESCRITURA se cerro el 2026-08-28 (`sesion_del_emisor`) y este
    quedo atras — el mismo error de forma por el lado de la lectura.
    """
    episode_id = uuid4()
    ctr_mock.get_episode.return_value = _make_ctr_episode(
        episode_id=episode_id,
        tenant_id=USER_TENANT,  # MISMO tenant: es lo que hace real al ataque
        comision_id=uuid4(),
        problema_id=uuid4(),
        student_pseudonym=uuid4(),  # otro alumno
        events=[
            _ev(0, "episodio_abierto", {"problema_id": str(uuid4())}),
            _ev(1, "prompt_enviado", {"content": "no entiendo los punteros"}),
            _ev(2, "edicion_codigo", {"code_snapshot": "int main() { return 0; }"}),
        ],
    )

    resp = await client.get(f"/api/v1/episodes/{episode_id}", headers=TENANT_HEADERS)

    assert resp.status_code == 403
    # El detalle importa: 403 de tenant y 403 de dueño son causas distintas y
    # un test que compare solo el status pasa con el gate de dueño borrado.
    assert "dueño" in resp.json()["detail"]
    # Y lo que de verdad se estaba filtrando no viaja en el body.
    assert "punteros" not in resp.text
    assert "int main" not in resp.text


async def test_el_dueño_del_episodio_lo_lee_normal(
    client: AsyncClient, ctr_mock: AsyncMock
) -> None:
    """La otra mitad: cerrar por dueño no puede romper al dueño.

    Sin este test, "403 a todo el mundo" tambien cierra el agujero y rompe
    el recovery on-mount del alumno, que es para lo que existe el endpoint.
    """
    episode_id = uuid4()
    problema_id = uuid4()
    ctr_mock.get_episode.return_value = _make_ctr_episode(
        episode_id=episode_id,
        tenant_id=USER_TENANT,
        comision_id=uuid4(),
        problema_id=problema_id,
        student_pseudonym=USER_ID,  # el que manda el request
        events=[_ev(0, "episodio_abierto", {"problema_id": str(problema_id)})],
    )

    resp = await client.get(f"/api/v1/episodes/{episode_id}", headers=TENANT_HEADERS)

    assert resp.status_code == 200
    assert resp.json()["episode_id"] == str(episode_id)


async def test_get_episode_state_closed_episode_devuelve_estado(
    client: AsyncClient, ctr_mock: AsyncMock
) -> None:
    """Episodio cerrado: igual se devuelve el state (modo lectura)
    para que la UI muestre la conversación histórica al estudiante."""
    episode_id = uuid4()
    comision_id = uuid4()
    problema_id = uuid4()
    opened = datetime.now(UTC)
    closed = datetime.now(UTC)

    events = [
        _ev(0, "episodio_abierto", {"problema_id": str(problema_id)}),
        _ev(1, "prompt_enviado", {"content": "última pregunta"}),
        _ev(2, "tutor_respondio", {"content": "última respuesta"}),
        _ev(3, "episodio_cerrado", {"reason": "student_closed"}),
    ]
    ctr_mock.get_episode.return_value = _make_ctr_episode(
        episode_id=episode_id,
        tenant_id=USER_TENANT,
        comision_id=comision_id,
        problema_id=problema_id,
        estado="closed",
        opened_at=opened,
        closed_at=closed,
        events=events,
    )

    resp = await client.get(f"/api/v1/episodes/{episode_id}", headers=TENANT_HEADERS)

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["estado"] == "closed"
    assert data["closed_at"] is not None
    # La conversación histórica vino completa
    assert len(data["messages"]) == 2
    assert data["messages"][0]["content"] == "última pregunta"
    assert data["messages"][1]["content"] == "última respuesta"
    # No hubo código → snapshot None
    assert data["last_code_snapshot"] is None


# ── REAPERTURA (Mejora 2, fix-pdf-auditoria-qa) ────────────────────────
#
# Hasta este fix, reabrir un ejercicio cerrado ("Volver a abrir"/"Empezar")
# creaba un episodio NUEVO sin eventos propios, y el editor abría con el
# scaffold vacío — el código que el alumno tenía se perdía. La pausa nunca
# tuvo este bug porque reanuda el MISMO episodio. El fix es de SOLO LECTURA:
# si el episodio actual no trajo código propio, `get_episode_state` busca el
# último código del episodio CERRADO más reciente del mismo (alumno,
# problema, ejercicio) vía `ctr.find_closed_episode` y lo usa para sembrar
# `last_code_snapshot` — sin tocar el write path del CTR.


async def test_reapertura_hereda_codigo_del_episodio_cerrado_anterior(
    client: AsyncClient, ctr_mock: AsyncMock
) -> None:
    """Caso feliz: episodio reabierto sin código propio → trae el código X
    del episodio cerrado anterior, no el scaffold vacío."""
    new_episode_id = uuid4()
    old_episode_id = uuid4()
    comision_id = uuid4()
    problema_id = uuid4()

    new_ep = _make_ctr_episode(
        episode_id=new_episode_id,
        tenant_id=USER_TENANT,
        comision_id=comision_id,
        problema_id=problema_id,
        estado="open",
        events=[_ev(0, "episodio_abierto", {"problema_id": str(problema_id)})],
    )
    old_ep = _make_ctr_episode(
        episode_id=old_episode_id,
        tenant_id=USER_TENANT,
        comision_id=comision_id,
        problema_id=problema_id,
        estado="closed",
        events=[
            _ev(0, "episodio_abierto", {"problema_id": str(problema_id)}),
            _ev(1, "edicion_codigo", {"snapshot": "def resuelto():\n    return 42\n"}),
            _ev(2, "episodio_cerrado", {"reason": "student_closed"}),
        ],
    )

    async def _get_episode(episode_id: UUID, **_: Any) -> dict[str, Any]:
        return new_ep if episode_id == new_episode_id else old_ep

    ctr_mock.get_episode.side_effect = _get_episode
    ctr_mock.find_closed_episode.return_value = {
        "episode_id": str(old_episode_id),
        "estado": "closed",
        "problema_id": str(problema_id),
        "ejercicio_id": None,
    }

    resp = await client.get(f"/api/v1/episodes/{new_episode_id}", headers=TENANT_HEADERS)

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["episode_id"] == str(new_episode_id)
    assert data["last_code_snapshot"] == "def resuelto():\n    return 42\n"

    ctr_mock.find_closed_episode.assert_awaited_once()
    call = ctr_mock.find_closed_episode.await_args
    assert call.kwargs["student_pseudonym"] == USER_ID
    assert call.kwargs["problema_id"] == problema_id

    # No debe emitir ningún evento CTR nuevo (no `edicion_codigo` fantasma) —
    # el endpoint es de lectura pura, el write path queda intacto.
    ctr_mock.publish_event.assert_not_awaited()


async def test_reapertura_no_pisa_codigo_propio_ya_editado(
    client: AsyncClient, ctr_mock: AsyncMock
) -> None:
    """Borde/triangulación: si el episodio reabierto YA tiene una edición
    propia, esa gana — no se busca ni se pisa con el episodio cerrado
    anterior (evita perder trabajo nuevo del alumno)."""
    episode_id = uuid4()
    problema_id = uuid4()

    ctr_mock.get_episode.return_value = _make_ctr_episode(
        episode_id=episode_id,
        tenant_id=USER_TENANT,
        comision_id=uuid4(),
        problema_id=problema_id,
        estado="open",
        events=[
            _ev(0, "episodio_abierto", {"problema_id": str(problema_id)}),
            _ev(1, "edicion_codigo", {"snapshot": "codigo_nuevo_del_alumno()"}),
        ],
    )

    resp = await client.get(f"/api/v1/episodes/{episode_id}", headers=TENANT_HEADERS)

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["last_code_snapshot"] == "codigo_nuevo_del_alumno()"
    ctr_mock.find_closed_episode.assert_not_awaited()


async def test_reapertura_sin_episodio_cerrado_previo_no_rompe(
    client: AsyncClient, ctr_mock: AsyncMock
) -> None:
    """Sin match (primera vez que el alumno abre este ejercicio): sigue
    devolviendo `last_code_snapshot=None`, el scaffold del editor decide."""
    episode_id = uuid4()
    problema_id = uuid4()

    ctr_mock.get_episode.return_value = _make_ctr_episode(
        episode_id=episode_id,
        tenant_id=USER_TENANT,
        comision_id=uuid4(),
        problema_id=problema_id,
        estado="open",
        events=[_ev(0, "episodio_abierto", {"problema_id": str(problema_id)})],
    )
    ctr_mock.find_closed_episode.return_value = None

    resp = await client.get(f"/api/v1/episodes/{episode_id}", headers=TENANT_HEADERS)

    assert resp.status_code == 200, resp.text
    assert resp.json()["last_code_snapshot"] is None
    ctr_mock.find_closed_episode.assert_awaited_once()


async def test_reapertura_no_aplica_a_episodio_cerrado_en_lectura(
    client: AsyncClient, ctr_mock: AsyncMock
) -> None:
    """Un episodio que se está viendo en modo lectura (cerrado, sin código
    propio) no dispara el seed — la regla es sólo para reaperturas `open`."""
    episode_id = uuid4()
    problema_id = uuid4()

    ctr_mock.get_episode.return_value = _make_ctr_episode(
        episode_id=episode_id,
        tenant_id=USER_TENANT,
        comision_id=uuid4(),
        problema_id=problema_id,
        estado="closed",
        closed_at=datetime.now(UTC),
        events=[_ev(0, "episodio_abierto", {"problema_id": str(problema_id)})],
    )

    resp = await client.get(f"/api/v1/episodes/{episode_id}", headers=TENANT_HEADERS)

    assert resp.status_code == 200, resp.text
    assert resp.json()["last_code_snapshot"] is None
    ctr_mock.find_closed_episode.assert_not_awaited()
