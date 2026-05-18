"""Validador de JWT con JWKS cache.

En producción el api-gateway valida cada request verificando la firma
del JWT emitido por Keycloak. El JWKS (JSON Web Key Set) del realm se
cachea en memoria con TTL configurable.

Flujo:
  1. Extraer bearer token del header Authorization
  2. Parsear header sin verificar para obtener `kid` (key id)
  3. Buscar la llave en JWKS cache; si no está o es stale, refrescar
  4. Verificar firma con la llave correcta
  5. Validar claims: exp, iss, aud
  6. Extraer `sub`, `email`, `realm_access.roles`, `tenant_id` custom claim
  7. Inyectar como headers X-* a servicios downstream

Errores → 401 con mensaje descriptivo.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

import httpx
import jwt

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ValidatedPrincipal:
    """Principal validado extraído del JWT."""

    user_id: str
    tenant_id: str
    email: str
    roles: frozenset[str]
    realm: str
    raw_claims: dict[str, Any]


@dataclass
class JWTValidatorConfig:
    issuer: str  # ej "http://keycloak:8080/realms/demo_uni"
    audience: str  # ej "platform-backend"
    jwks_uri: str  # ej "http://keycloak:8080/realms/demo_uni/protocol/openid-connect/certs"
    jwks_cache_ttl_seconds: int = 300  # 5 min default
    leeway_seconds: int = 10  # tolerancia de clock skew
    allow_insecure_debug: bool = False  # solo dev/CI


class JWTValidationError(Exception):
    """Excepción base para fallos de validación."""

    def __init__(self, message: str, status_code: int = 401) -> None:
        super().__init__(message)
        self.status_code = status_code


class JWKSCache:
    """Cache simple de JWKS con TTL + refresh forzado on kid miss.

    Rota automáticamente: si viene un JWT firmado con una llave nueva
    (kid desconocido), se refresca el JWKS inmediatamente antes de fallar.
    """

    def __init__(self, config: JWTValidatorConfig) -> None:
        self.config = config
        self._cache: dict[str, Any] = {}
        self._fetched_at: float = 0.0

    async def get_key(self, kid: str) -> Any:
        """Obtiene la PyJWK para el kid dado, refrescando si hace falta."""
        if self._is_stale() or kid not in self._cache:
            await self._refresh()

        if kid not in self._cache:
            # Segundo intento: force-refresh por si apenas rotó Keycloak
            await self._refresh(force=True)

        if kid not in self._cache:
            raise JWTValidationError(f"Firmado con kid desconocido: {kid}")

        return self._cache[kid]

    def _is_stale(self) -> bool:
        return (time.time() - self._fetched_at) > self.config.jwks_cache_ttl_seconds

    async def _refresh(self, force: bool = False) -> None:
        if not force and not self._is_stale() and self._cache:
            return

        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(self.config.jwks_uri)
            r.raise_for_status()
            jwks = r.json()

        from jwt.algorithms import RSAAlgorithm

        new_cache: dict[str, Any] = {}
        for key_data in jwks.get("keys", []):
            kid = key_data.get("kid")
            kty = key_data.get("kty")
            if not kid or kty != "RSA":
                continue
            try:
                key = RSAAlgorithm.from_jwk(key_data)
                new_cache[kid] = key
            except Exception as e:
                logger.warning("Failed to parse JWK kid=%s: %s", kid, e)

        self._cache = new_cache
        self._fetched_at = time.time()
        logger.debug("JWKS refreshed: %d keys cached", len(new_cache))


class JWTValidator:
    """Valida JWTs emitidos por Keycloak."""

    def __init__(self, config: JWTValidatorConfig, jwks_cache: JWKSCache | None = None) -> None:
        self.config = config
        self.jwks_cache = jwks_cache or JWKSCache(config)

    async def validate(self, token: str) -> ValidatedPrincipal:
        """Valida un token y devuelve el principal.

        Raises:
            JWTValidationError con detalle del fallo.
        """
        # 1. Parsear header sin verificar para obtener kid y alg
        try:
            unverified_header = jwt.get_unverified_header(token)
        except jwt.InvalidTokenError as e:
            raise JWTValidationError(f"Token malformado: {e}") from e

        kid = unverified_header.get("kid")
        alg = unverified_header.get("alg", "")
        if not kid:
            raise JWTValidationError("Token sin 'kid' en header")
        if alg != "RS256":
            raise JWTValidationError(f"Algoritmo no permitido: {alg}")

        # 2. Obtener llave pública del JWKS
        key = await self.jwks_cache.get_key(kid)

        # 3. Verificar firma + claims estándar
        try:
            claims = jwt.decode(
                token,
                key=key,
                algorithms=["RS256"],
                audience=self.config.audience,
                issuer=self.config.issuer,
                leeway=self.config.leeway_seconds,
                options={
                    "require": ["exp", "iat", "iss", "sub"],
                    "verify_exp": True,
                    "verify_iat": True,
                    "verify_iss": True,
                    "verify_aud": True,
                    "verify_signature": True,
                },
            )
        except jwt.ExpiredSignatureError:
            raise JWTValidationError("Token expirado")
        except jwt.InvalidAudienceError:
            raise JWTValidationError(f"Audience inválida; se esperaba {self.config.audience}")
        except jwt.InvalidIssuerError:
            raise JWTValidationError(f"Issuer inválido; se esperaba {self.config.issuer}")
        except jwt.InvalidTokenError as e:
            raise JWTValidationError(f"Token inválido: {e}") from e

        # 4. Extraer claims custom
        return self._build_principal(claims)

    def _build_principal(self, claims: dict) -> ValidatedPrincipal:
        # Keycloak pone los roles del realm en `realm_access.roles`
        realm_access = claims.get("realm_access") or {}
        roles = frozenset(realm_access.get("roles", []))

        # tenant_id es un claim custom que configura el admin al onboarding
        # (el mapper en Keycloak agrega claim "tenant_id" al token).
        tenant_id = claims.get("tenant_id")
        if not tenant_id:
            raise JWTValidationError("Token sin claim 'tenant_id' (tenant not onboarded?)")

        return ValidatedPrincipal(
            user_id=claims["sub"],
            tenant_id=tenant_id,
            email=claims.get("email", ""),
            roles=roles,
            realm=claims.get("iss", "").rstrip("/").split("/")[-1],
            raw_claims=claims,
        )


def extract_bearer_token(authorization_header: str | None) -> str:
    """Extrae el token del header Authorization."""
    if not authorization_header:
        raise JWTValidationError("Falta header Authorization")
    parts = authorization_header.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise JWTValidationError("Formato de Authorization debe ser: Bearer <token>")
    return parts[1]
