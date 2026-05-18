"""Tests del audit_router (ADR-031, D.4 / 2026-04-29).

Garantia central: los alias publicos `/api/v1/audit/episodes/{id}` y
`/api/v1/audit/episodes/{id}/verify` resuelven a las MISMAS funciones
handler que los endpoints legacy. Cero duplicacion de logica.

Si este test falla:
  - Alguien removio el audit_router de events.py o de main.py.
  - Alguien desregistro un alias del audit_router.
  - El api-gateway ROUTE_MAP /api/v1/audit dejo de apuntar al ctr-service.
"""

from __future__ import annotations

from ctr_service.main import app
from ctr_service.routes.events import (
    audit_router,
    get_episode,
    router,
    verify_episode_chain,
)


def _routes_by_path(app_routes) -> dict[tuple[str, frozenset[str]], object]:
    """Indexa las rutas registradas por (path, frozenset(methods)) -> endpoint."""
    out: dict[tuple[str, frozenset[str]], object] = {}
    for r in app_routes:
        endpoint = getattr(r, "endpoint", None)
        if endpoint is None:
            continue
        methods = frozenset(getattr(r, "methods", set()) or set())
        path = getattr(r, "path", None)
        if path is None:
            continue
        out[(path, methods)] = endpoint
    return out


def test_audit_get_episode_apunta_al_mismo_handler_que_legacy() -> None:
    """ADR-031: GET /api/v1/audit/episodes/{episode_id} reusa get_episode legacy."""
    indexed = _routes_by_path(app.routes)
    legacy_key = ("/api/v1/episodes/{episode_id}", frozenset({"GET"}))
    audit_key = ("/api/v1/audit/episodes/{episode_id}", frozenset({"GET"}))

    assert legacy_key in indexed, (
        "Endpoint legacy GET /api/v1/episodes/{id} no esta registrado — "
        "ROUTE_MAP del api-gateway depende de el via tutor-service."
    )
    assert audit_key in indexed, (
        "Alias GET /api/v1/audit/episodes/{id} no esta registrado en la app — "
        "verificar que main.py incluya `events.audit_router`."
    )

    legacy_handler = indexed[legacy_key]
    audit_handler = indexed[audit_key]
    assert legacy_handler is audit_handler is get_episode, (
        "Los handlers difieren — los aliases del audit_router deben apuntar "
        "a la MISMA funcion get_episode (cero duplicacion de logica)."
    )


def test_audit_verify_episode_apunta_al_mismo_handler_que_legacy() -> None:
    """ADR-031: POST /api/v1/audit/episodes/{id}/verify reusa verify_episode_chain."""
    indexed = _routes_by_path(app.routes)
    legacy_key = ("/api/v1/episodes/{episode_id}/verify", frozenset({"POST"}))
    audit_key = ("/api/v1/audit/episodes/{episode_id}/verify", frozenset({"POST"}))

    assert legacy_key in indexed
    assert audit_key in indexed

    legacy_handler = indexed[legacy_key]
    audit_handler = indexed[audit_key]
    assert legacy_handler is audit_handler is verify_episode_chain


def test_audit_router_solo_expone_aliases_de_lectura() -> None:
    """ADR-031: el audit_router NO expone POST /events ni endpoints de write.

    El web-admin solo audita (read + verify). Para publish del CTR se usa
    el path legacy `/api/v1/events` que es service-to-service (tutor → ctr).
    """
    audit_paths = {r.path for r in audit_router.routes if hasattr(r, "path")}
    # Esperamos solo las dos rutas de read/verify.
    assert audit_paths == {
        "/api/v1/audit/episodes/{episode_id}",
        "/api/v1/audit/episodes/{episode_id}/verify",
    }, (
        f"audit_router expone rutas inesperadas: {audit_paths}. "
        "Solo deberia exponer aliases READ-ONLY del CTR."
    )
    # El router legacy SIGUE incluyendo /events (write service-to-service).
    legacy_paths = {r.path for r in router.routes if hasattr(r, "path")}
    assert "/api/v1/events" in legacy_paths, (
        "El POST /api/v1/events del router legacy desaparecio — "
        "tutor-service depende de el para emitir eventos al CTR."
    )
