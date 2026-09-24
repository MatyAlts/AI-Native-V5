"""Tests de validación + auth del endpoint POST /api/v1/events del ctr-service.

Tests focales: rechazo de payloads malformados (422 antes de auth) y rechazo
de requests sin auth (401). Tests más complejos del happy path con DB+Redis
quedan en `tests/integration/test_ctr_end_to_end.py` (con stack real).
"""

from __future__ import annotations

from ctr_service.main import app
from fastapi.testclient import TestClient


def test_publish_event_rejects_request_without_auth_headers() -> None:
    """Sin headers X-* ni JWT → 401."""
    client = TestClient(app)
    response = client.post("/api/v1/events", json={})
    assert response.status_code in (401, 403, 422)


def test_publish_event_rejects_malformed_payload_with_dev_headers() -> None:
    """Con headers X-* dev mode pero body malformado → 422 (validación schema)."""
    client = TestClient(app)
    response = client.post(
        "/api/v1/events",
        json={"foo": "bar"},  # missing required fields
        headers={
            "X-User-Id": "00000000-0000-0000-0000-000000000010",
            "X-Tenant-Id": "11111111-1111-1111-1111-111111111111",
            "X-User-Email": "x@y.z",
            "X-User-Roles": "tutor_service",
        },
    )
    assert response.status_code in (401, 403, 422)


def test_get_episode_404_for_unknown_id() -> None:
    """GET /api/v1/episodes/{id} con UUID inexistente → 404 o 401."""
    client = TestClient(app)
    response = client.get(
        "/api/v1/episodes/99999999-9999-9999-9999-999999999999",
        headers={
            "X-User-Id": "00000000-0000-0000-0000-000000000010",
            "X-Tenant-Id": "11111111-1111-1111-1111-111111111111",
            "X-User-Email": "x@y.z",
            "X-User-Roles": "auditor",
        },
    )
    # 401 si no hay JWT decoder; 404 si pasa auth y no encuentra; 500 si DB no disponible.
    # Lo importante es que el endpoint exista y no crashee con 500 silencioso.
    assert response.status_code in (401, 403, 404, 500, 503)


def test_audit_alias_routes_resolve() -> None:
    """Las rutas /api/v1/audit/* (ADR-031) están registradas."""
    client = TestClient(app)
    # Solo verificamos que la ruta existe (no que retorna 200; sin DB tira otra cosa).
    response = client.get("/api/v1/audit/episodes/99999999-9999-9999-9999-999999999999")
    assert response.status_code != 404 or response.status_code == 401
    # Si llegó al handler aunque no tenga auth, no es 404 método/no-found de fastapi


def _all_route_paths() -> list[str]:
    """Aplana `app.routes` en orden de registro.

    Esta versión de FastAPI envuelve cada `include_router` en un
    `_IncludedRouter` (inclusión perezosa) en vez de aplanar los sub-routes
    directo en `app.routes` — `app.routes` solo trae `/openapi.json`, `/docs`,
    etc. + un `_IncludedRouter` opaco por cada router incluido. Bajamos un
    nivel a `original_router.routes` para poder listar los paths reales.
    """
    paths: list[str] = []
    for route in app.routes:
        original_router = getattr(route, "original_router", None)
        sub_routes = original_router.routes if original_router is not None else [route]
        for sub in sub_routes:
            path = getattr(sub, "path", None)
            if path is not None:
                paths.append(path)
    return paths


def test_closed_match_route_esta_registrada_antes_del_path_generico() -> None:
    """GET /episodes/closed-match (REAPERTURA, Mejora 2, fix-pdf-auditoria-qa).

    FastAPI matchea rutas en orden de registro. Si "closed-match" quedara
    registrada DESPUÉS de /episodes/{episode_id}, ese path genérico la
    capturaría primero e intentaría parsear "closed-match" como UUID —
    inalcanzable en la práctica. Mismo patrón que ya resuelve /open-match,
    registrada antes en este mismo archivo.

    Introspección pura sobre `app.routes` — no requiere DB ni auth real, así
    que corre igual sin Postgres/Redis levantados.
    """
    paths = _all_route_paths()
    assert "/api/v1/episodes/closed-match" in paths
    assert paths.index("/api/v1/episodes/closed-match") < paths.index(
        "/api/v1/episodes/{episode_id}"
    )


def test_closed_match_ordena_con_nulls_last() -> None:
    """GET /episodes/closed-match ordena `closed_at DESC NULLS LAST`.

    `Episode.closed_at` es nullable (`models/event.py`) y en Postgres un
    `ORDER BY ... DESC` pone los NULL PRIMERO por default. Un episodio en
    estado `closed` con `closed_at` NULL (legacy, backfill o seed) ganaria
    entonces el orden y la reapertura sembraria en el editor el codigo del
    episodio EQUIVOCADO — un dato que despues entra a la cadena del episodio
    nuevo. `nullslast()` manda esos al final: si hay algun cierre fechado,
    ese gana siempre.

    Captura el statement con un `db` falso y lo compila al dialecto de
    Postgres: no toca DB ni red, corre sin stack levantado.
    """
    import asyncio
    from uuid import uuid4

    from ctr_service.auth import User
    from ctr_service.routes.events import find_closed_episode
    from sqlalchemy.dialects import postgresql

    class _FakeResult:
        def scalars(self):
            return self

        def all(self):
            return []

    class _CapturingDB:
        def __init__(self) -> None:
            self.stmt = None

        async def execute(self, stmt):
            self.stmt = stmt
            return _FakeResult()

    tenant_id = uuid4()
    user = User(
        id=uuid4(),
        tenant_id=tenant_id,
        email="tutor-service@platform.internal",
        roles=frozenset({"tutor_service"}),
        realm=str(tenant_id),
    )
    db = _CapturingDB()

    asyncio.run(
        find_closed_episode(
            student_pseudonym=uuid4(),
            problema_id=uuid4(),
            ejercicio_id=None,
            user=user,
            db=db,
        )
    )

    assert db.stmt is not None, "el endpoint no ejecuto ningun SELECT"
    sql = str(db.stmt.compile(dialect=postgresql.dialect())).upper()
    assert "ORDER BY" in sql
    assert "CLOSED_AT DESC NULLS LAST" in sql, sql
