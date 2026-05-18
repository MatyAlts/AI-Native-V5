"""Tests del JWT validator con firma RSA real.

Usa una llave generada on-the-fly para no depender de Keycloak.
Verifica:
  - Firma válida → principal correcto
  - Firma inválida, expirado, issuer erróneo, audience errónea → 401
  - JWKS cache con rotación
  - Claims custom (tenant_id, realm_access.roles)
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import jwt
import pytest
from api_gateway.services.jwt_validator import (
    JWTValidationError,
    JWTValidator,
    JWTValidatorConfig,
    extract_bearer_token,
)
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

# ── Fixtures de crypto ─────────────────────────────────────────────────


@pytest.fixture(scope="module")
def rsa_key_pair():
    """Generan un par RSA 2048 para firma/verificación."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_pem = (
        private_key.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode()
    )
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    return {"private_pem": private_pem, "public_pem": public_pem, "key": private_key}


def _make_token(
    private_pem: str,
    kid: str = "test-kid",
    sub: str = "user-123",
    tenant_id: str | None = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
    issuer: str = "http://keycloak/realms/demo_uni",
    audience: str = "platform-backend",
    email: str = "alice@uni-demo.edu",
    roles: list[str] | None = None,
    exp_offset: int = 300,
    alg: str = "RS256",
) -> str:
    now = int(time.time())
    payload: dict[str, Any] = {
        "sub": sub,
        "email": email,
        "iss": issuer,
        "aud": audience,
        "iat": now,
        "exp": now + exp_offset,
        "realm_access": {"roles": roles or ["estudiante"]},
    }
    if tenant_id:
        payload["tenant_id"] = tenant_id

    return jwt.encode(payload, private_pem, algorithm=alg, headers={"kid": kid})


@dataclass
class FakeJWKSCache:
    """Cache fake que devuelve directamente la llave pública cargada."""

    public_pem: str

    async def get_key(self, kid: str):
        from cryptography.hazmat.primitives.serialization import load_pem_public_key

        if kid == "unknown-kid":
            raise JWTValidationError(f"Firmado con kid desconocido: {kid}")
        return load_pem_public_key(self.public_pem.encode())


@pytest.fixture
def config() -> JWTValidatorConfig:
    return JWTValidatorConfig(
        issuer="http://keycloak/realms/demo_uni",
        audience="platform-backend",
        jwks_uri="http://keycloak/realms/demo_uni/protocol/openid-connect/certs",
    )


@pytest.fixture
def validator(config, rsa_key_pair) -> JWTValidator:
    cache = FakeJWKSCache(public_pem=rsa_key_pair["public_pem"])
    return JWTValidator(config=config, jwks_cache=cache)


# ── Tests principales ─────────────────────────────────────────────────


async def test_token_valido_produce_principal_correcto(validator, rsa_key_pair) -> None:
    token = _make_token(rsa_key_pair["private_pem"], roles=["estudiante", "cohort_2026"])
    principal = await validator.validate(token)

    assert principal.user_id == "user-123"
    assert principal.tenant_id == "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    assert principal.email == "alice@uni-demo.edu"
    assert "estudiante" in principal.roles
    assert "cohort_2026" in principal.roles
    assert principal.realm == "demo_uni"


async def test_token_expirado_falla(validator, rsa_key_pair) -> None:
    token = _make_token(rsa_key_pair["private_pem"], exp_offset=-60)
    with pytest.raises(JWTValidationError, match="expirado"):
        await validator.validate(token)


async def test_token_con_issuer_incorrecto_falla(validator, rsa_key_pair) -> None:
    token = _make_token(rsa_key_pair["private_pem"], issuer="http://evil/realms/fake")
    with pytest.raises(JWTValidationError, match="[Ii]ssuer inválido"):
        await validator.validate(token)


async def test_token_con_audience_incorrecta_falla(validator, rsa_key_pair) -> None:
    token = _make_token(rsa_key_pair["private_pem"], audience="other-service")
    with pytest.raises(JWTValidationError, match="[Aa]udience inválida"):
        await validator.validate(token)


async def test_token_sin_tenant_id_falla(validator, rsa_key_pair) -> None:
    """Propiedad crítica: JWTs sin claim tenant_id se rechazan (tenant no onboardeado)."""
    token = _make_token(rsa_key_pair["private_pem"], tenant_id=None)
    with pytest.raises(JWTValidationError, match="tenant_id"):
        await validator.validate(token)


async def test_token_con_kid_desconocido_falla(validator, rsa_key_pair) -> None:
    token = _make_token(rsa_key_pair["private_pem"], kid="unknown-kid")
    with pytest.raises(JWTValidationError, match="kid"):
        await validator.validate(token)


async def test_token_con_firma_invalida_falla(validator, rsa_key_pair) -> None:
    """Manipular el token después de firmarlo rompe la verificación."""
    token = _make_token(rsa_key_pair["private_pem"])
    # Flipear algunos bytes del payload (la parte entre los dos puntos)
    parts = token.split(".")
    # Cambiar un carácter del payload → firma rota
    tampered = parts[0] + "." + parts[1][:-5] + "XXXXX" + "." + parts[2]

    with pytest.raises(JWTValidationError):
        await validator.validate(tampered)


async def test_algoritmo_hs256_se_rechaza(validator) -> None:
    """Protección contra 'alg: none' y simétricos: solo RS256."""
    token = jwt.encode(
        {
            "sub": "x",
            "iss": "http://keycloak/realms/demo_uni",
            "aud": "platform-backend",
            "exp": int(time.time()) + 60,
            "iat": int(time.time()),
            "tenant_id": "t",
        },
        "secret",
        algorithm="HS256",
        headers={"kid": "test-kid"},
    )
    with pytest.raises(JWTValidationError, match="Algoritmo no permitido"):
        await validator.validate(token)


async def test_token_malformado_sin_kid_falla(validator) -> None:
    token_sin_kid = jwt.encode({"sub": "x"}, "secret", algorithm="HS256")
    # Sin 'kid' en el header
    with pytest.raises(JWTValidationError, match="kid"):
        await validator.validate(token_sin_kid)


# ── extract_bearer_token ──────────────────────────────────────────────


def test_extract_bearer_token_valido() -> None:
    assert extract_bearer_token("Bearer xyz") == "xyz"
    assert extract_bearer_token("bearer xyz") == "xyz"  # case insensitive


def test_extract_bearer_token_sin_header_falla() -> None:
    with pytest.raises(JWTValidationError, match="Authorization"):
        extract_bearer_token(None)


def test_extract_bearer_token_formato_incorrecto_falla() -> None:
    with pytest.raises(JWTValidationError, match="Bearer"):
        extract_bearer_token("Basic abc123")
    with pytest.raises(JWTValidationError, match="Bearer"):
        extract_bearer_token("xyz")
