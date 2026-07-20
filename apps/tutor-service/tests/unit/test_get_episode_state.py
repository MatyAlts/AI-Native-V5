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


@pytest.fixture
async def client() -> AsyncClient:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.fixture
def ctr_mock(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    """Sustituye `_get_ctr_client()` por un AsyncMock.

    El endpoint `get_episode_state` lo llama para fetchar el episodio
    desde ctr-service. Con el mock no hace HTTP real.
    """
    mock = AsyncMock()
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
) -> dict[str, Any]:
    """Construye el dict que el ctr-service devolvería en GET /episodes/{id}."""
    opened = opened_at or datetime.now(UTC)
    return {
        "id": str(episode_id),
        "tenant_id": str(tenant_id),
        "comision_id": str(comision_id),
        "student_pseudonym": str(uuid4()),
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
        _ev(5, "nota_personal", {"contenido": "Recordar usar print() siempre"}),
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
    assert data["notes"] == []
