"""Smoke — invariants del ROUTE_MAP del api-gateway.

Atrapa la clase de bug que hoy nadie ve hasta runtime: si un servicio destino
del ROUTE_MAP se renombra, se mueve de puerto, o se borra, el endpoint queda
inalcanzable desde frontend SIN señal hasta que un usuario real pega.

Estrategia:
  - Importa el `ROUTE_MAP` real del modulo del api-gateway (NO duplica).
  - Por cada `(prefix, target_url)`, hace `GET {target_url}/health` y assertea
    status 200/503 (200=ready, 503=degraded — ambos significan "el servicio
    existe y responde", que es lo que valida este smoke).
  - Skipea servicios que by-design NO viven en local (ver SKIP_TARGETS).

NO chequea el routing del gateway — eso lo cubre `test_smoke_health.py::
test_api_gateway_routes_to_academic_via_proxy`. Acá validamos sólo que cada
target del dict apunta a algo vivo.

Excluidos del ROUTE_MAP by-design (CLAUDE.md / ADRs 030, 031, 038, 039, 041):
  - identity-service, enrollment-service: deprecated (ADRs 030, 041) — NO
    aparecen en el dict, no hay nada que skipear.
  - governance-service, integrity-attestation-service: completamente
    excluidos del ROUTE_MAP — si APARECEN en el dict, es bug. Si NO
    aparecen, el test no los toca.

Servicios con exposición parcial (sí van en el dict, sí los chequeamos):
  - ctr-service via /api/v1/audit/* (ADR-031 D.4)
  - ai-gateway via /api/v1/byok/* (ADRs 038/039)
"""

from __future__ import annotations

import httpx
import pytest

from api_gateway.routes.proxy import ROUTE_MAP  # type: ignore[import-not-found]

# Targets que existen en el ROUTE_MAP pero by-design NO se levantan en piloto
# local (viven en infra institucional separada). Si alguno de estos está en
# el dict, lo skipeamos con mensaje claro — NO falla el smoke.
#
# `integrity-attestation-service` (:8012) corre en VPS UNSL en piloto real.
# RN-128 declara la attestation eventualmente consistente y no bloqueante.
# Hoy NO está en el ROUTE_MAP (verificado), pero si alguien lo agrega, el
# skip aplicará automáticamente por puerto.
SKIP_TARGETS_BY_PORT: dict[int, str] = {
    8012: (
        "integrity-attestation-service vive en VPS UNSL en piloto real "
        "(RN-128, ADR-021). No se levanta en local."
    ),
}


def _route_map_entries() -> list[tuple[str, str]]:
    """Lista determinística de (prefix, target_url) para parametrizar."""
    return sorted(ROUTE_MAP.items())


@pytest.mark.smoke
def test_route_map_no_esta_vacio() -> None:
    """El ROUTE_MAP debe tener al menos una entrada — guardrail estructural."""
    assert len(ROUTE_MAP) > 0, "ROUTE_MAP vacío — el gateway no enrutaría nada"


@pytest.mark.smoke
def test_route_map_targets_son_urls_validas() -> None:
    """Todos los target URLs del ROUTE_MAP deben ser strings http(s)://."""
    for prefix, target in ROUTE_MAP.items():
        assert isinstance(target, str), (
            f"target del prefix {prefix!r} no es string: {target!r}"
        )
        assert target.startswith(("http://", "https://")), (
            f"target del prefix {prefix!r} no es URL http(s): {target!r}"
        )


@pytest.mark.smoke
@pytest.mark.parametrize(
    "prefix,target",
    _route_map_entries(),
    ids=[f"{p}->{t}" for p, t in _route_map_entries()],
)
def test_route_map_target_health_responde(prefix: str, target: str) -> None:
    """Cada target del ROUTE_MAP debe responder /health con 200 o 503.

    200 = ready. 503 = degraded (alguna dep cayó pero el servicio responde).
    Ambos significan "el binario existe en ese puerto". Cualquier otra cosa
    (connection refused, 404, 5xx que no sea 503) es señal de que el target
    está roto, renombrado, o el puerto cambió sin actualizar el ROUTE_MAP.
    """
    # Skip targets by-design no levantados en local
    target_url = target.rstrip("/")
    for skip_port, reason in SKIP_TARGETS_BY_PORT.items():
        if f":{skip_port}" in target_url:
            pytest.skip(
                f"prefix={prefix!r} → {target_url} skipeado: {reason}"
            )

    health_url = f"{target_url}/health"
    try:
        resp = httpx.get(health_url, timeout=3.0)
    except httpx.ConnectError as exc:
        pytest.fail(
            f"ROUTE_MAP[{prefix!r}] = {target_url} — connection refused. "
            f"El servicio no está levantado o cambió de puerto sin actualizar "
            f"el ROUTE_MAP. Error: {exc}"
        )
    except Exception as exc:  # noqa: BLE001
        pytest.fail(
            f"ROUTE_MAP[{prefix!r}] = {target_url} — error inesperado en "
            f"GET {health_url}: {type(exc).__name__}: {exc}"
        )

    if resp.status_code not in (200, 503):
        pytest.fail(
            f"ROUTE_MAP[{prefix!r}] = {target_url} — GET /health respondió "
            f"{resp.status_code} (esperado 200 ready / 503 degraded). "
            f"Body: {resp.text[:300]}"
        )
