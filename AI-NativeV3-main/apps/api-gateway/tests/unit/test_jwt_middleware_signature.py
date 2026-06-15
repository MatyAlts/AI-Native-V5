"""Tests del JWTMiddleware: inyección de la firma HMAC del gateway.

Verifica el lado EMISOR del fix de defensa en profundidad: cuando hay
`gateway_shared_secret` configurado, el gateway agrega `x-gateway-signature`
y `x-gateway-ts` a los headers X-* autoritativos, y esa firma valida con el
secreto compartido. Con secreto vacío, no agrega nada (comportamiento legacy).
"""

from __future__ import annotations

from dataclasses import dataclass

from api_gateway.middleware.jwt_auth import JWTMiddleware
from platform_observability import verify_gateway_signature
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

SECRET = "gateway-secret-para-tests"
USER_ID = "b1b1b1b1-0001-0001-0001-000000000001"
TENANT_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"


@dataclass(frozen=True)
class _FakePrincipal:
    user_id: str
    tenant_id: str
    email: str
    roles: frozenset[str]
    realm: str


class _FakeValidator:
    """Validator stub que devuelve un principal fijo sin tocar Keycloak."""

    async def validate(self, token: str) -> _FakePrincipal:
        return _FakePrincipal(
            user_id=USER_ID,
            tenant_id=TENANT_ID,
            email="alumno@demo-uni.edu",
            roles=frozenset({"docente", "estudiante"}),
            realm="demo_uni",
        )


async def _echo(request):
    """Endpoint downstream que devuelve los headers que recibió."""
    return JSONResponse({k.lower(): v for k, v in request.headers.items()})


def _build_client(secret: str) -> TestClient:
    app = Starlette(routes=[Route("/echo", _echo)])
    app.add_middleware(
        JWTMiddleware,
        validator=_FakeValidator(),
        gateway_shared_secret=secret,
    )
    return TestClient(app)


def test_inyecta_signature_y_ts_con_secreto() -> None:
    client = _build_client(SECRET)
    resp = client.get("/echo", headers={"authorization": "Bearer faketoken"})
    assert resp.status_code == 200
    headers = resp.json()

    assert "x-gateway-signature" in headers
    assert "x-gateway-ts" in headers
    # roles inyectados = sorted, csv
    assert headers["x-user-roles"] == "docente,estudiante"

    # La firma inyectada valida con el secreto compartido y el payload inyectado.
    assert verify_gateway_signature(
        SECRET,
        headers["x-user-id"],
        headers["x-tenant-id"],
        headers["x-user-roles"],
        headers["x-gateway-ts"],
        headers["x-gateway-signature"],
    )


def test_sin_secreto_no_inyecta_firma() -> None:
    """Secreto vacío => comportamiento legacy: no agrega headers de firma."""
    client = _build_client("")
    resp = client.get("/echo", headers={"authorization": "Bearer faketoken"})
    assert resp.status_code == 200
    headers = resp.json()
    assert "x-gateway-signature" not in headers
    assert "x-gateway-ts" not in headers


def test_purga_firma_forjada_por_cliente() -> None:
    """Un cliente que manda x-gateway-signature/ts forjados es purgado.

    El gateway recompone la firma con el principal real; si un atacante mandara
    una firma propia, queda descartada y reemplazada por la auténtica.
    """
    client = _build_client(SECRET)
    resp = client.get(
        "/echo",
        headers={
            "authorization": "Bearer faketoken",
            "x-gateway-signature": "deadbeef",
            "x-gateway-ts": "1",
            "x-user-roles": "superadmin",  # intento de escalación
        },
    )
    assert resp.status_code == 200
    headers = resp.json()
    assert headers["x-gateway-signature"] != "deadbeef"
    assert headers["x-gateway-ts"] != "1"
    # los roles forjados fueron reemplazados por los del principal real
    assert headers["x-user-roles"] == "docente,estudiante"
    assert verify_gateway_signature(
        SECRET,
        headers["x-user-id"],
        headers["x-tenant-id"],
        headers["x-user-roles"],
        headers["x-gateway-ts"],
        headers["x-gateway-signature"],
    )
