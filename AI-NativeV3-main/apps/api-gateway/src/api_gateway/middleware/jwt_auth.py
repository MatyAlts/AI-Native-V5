"""Middleware de validación JWT del api-gateway.

Flujo por request:
  1. Rutas exentas (health, docs) → pasa sin validar
  2. Si el header Authorization está presente → valida
  3. Si NO hay Authorization pero hay X-User-Id + X-Tenant-Id y
     `dev_trust_headers=True` → pasa (solo para desarrollo local)
  4. De lo contrario → 401

Al validar exitosamente:
  - Reemplaza headers X-* con los claims del JWT (no se puede confiar en
    X-* que vengan del cliente; el gateway los setea autoritativamente)
  - Agrega X-Request-Id si no existe
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from api_gateway.services.jwt_validator import (
    JWTValidationError,
    JWTValidator,
    extract_bearer_token,
)

logger = logging.getLogger(__name__)


class JWTMiddleware(BaseHTTPMiddleware):
    """Valida JWT y setea headers X-* autoritativamente downstream.

    CRÍTICO: este middleware es la única fuente de verdad de la identidad.
    Los servicios internos confían CIEGAMENTE en los headers X-* que vienen
    del api-gateway. Si este middleware se saltea o rompe, se rompe la
    autorización completa.
    """

    EXEMPT_PATHS = (
        "/",
        "/health",
        "/metrics",
        "/docs",
        "/openapi.json",
        "/redoc",
    )

    def __init__(
        self,
        app,
        validator: JWTValidator | None,
        dev_trust_headers: bool = False,
    ) -> None:
        super().__init__(app)
        self.validator = validator
        self.dev_trust_headers = dev_trust_headers

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        path = request.url.path
        if path in self.EXEMPT_PATHS or path.startswith("/health"):
            return await call_next(request)

        # Intentar JWT primero
        auth_header = request.headers.get("authorization")
        principal = None

        if auth_header:
            try:
                token = extract_bearer_token(auth_header)
                if self.validator is not None:
                    principal = await self.validator.validate(token)
                elif not self.dev_trust_headers:
                    return _error_response(
                        500,
                        "JWT validator no configurado pero se recibió un token",
                    )
                # validator=None + dev_trust_headers=True → ignorar Bearer,
                # caer al fallback X-* de dev
            except JWTValidationError as e:
                return _error_response(e.status_code, str(e))

        # Fallback a headers X-* si está en modo dev
        if principal is None and self.dev_trust_headers:
            x_user_id = request.headers.get("x-user-id")
            x_tenant_id = request.headers.get("x-tenant-id")
            if x_user_id and x_tenant_id:
                # Pasar sin modificar (dev trust)
                return await _add_request_id(request, call_next)

        if principal is None:
            return _error_response(401, "Autenticación requerida")

        # Reescribir headers X-* autoritativamente
        # (scope["headers"] es una lista de tuplas byte-encoded)
        headers = [
            (k, v)
            for k, v in request.scope["headers"]
            if k.lower()
            not in (
                b"x-user-id",
                b"x-tenant-id",
                b"x-user-email",
                b"x-user-roles",
                b"x-user-realm",
            )
        ]
        headers.extend(
            [
                (b"x-user-id", principal.user_id.encode()),
                (b"x-tenant-id", principal.tenant_id.encode()),
                (b"x-user-email", principal.email.encode()),
                (b"x-user-roles", ",".join(sorted(principal.roles)).encode()),
                (b"x-user-realm", principal.realm.encode()),
            ]
        )
        request.scope["headers"] = headers

        return await _add_request_id(request, call_next)


async def _add_request_id(request: Request, call_next: Callable) -> Response:
    """Inyecta X-Request-Id si no existe (ayuda a correlación en logs)."""
    request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
    response = await call_next(request)
    response.headers["x-request-id"] = request_id
    return response


def _error_response(status_code: int, detail: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"detail": detail},
        headers={"WWW-Authenticate": "Bearer"} if status_code == 401 else {},
    )
