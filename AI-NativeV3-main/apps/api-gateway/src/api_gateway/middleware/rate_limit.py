"""Middleware FastAPI del rate limiter del api-gateway."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

import redis.asyncio as redis
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from api_gateway.services.rate_limit import (
    RateLimiter,
    config_for_path,
    principal_from_request,
)

logger = logging.getLogger(__name__)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Aplica rate limit basado en principal + path.

    Rutas exentas (health, metrics, raíz) pasan sin chequear.
    """

    EXEMPT_PATHS = ("/health", "/metrics", "/", "/docs", "/openapi.json", "/redoc")

    def __init__(self, app: Any, redis_client: redis.Redis) -> None:
        super().__init__(app)
        # RateLimiter declara un protocol _RedisLike más estricto que el typed
        # stub de redis-py; en runtime ambos implementan los métodos requeridos.
        self.limiter = RateLimiter(redis_client)  # type: ignore[arg-type]

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        path = request.url.path
        if path in self.EXEMPT_PATHS or path.startswith("/health"):
            return await call_next(request)

        principal = principal_from_request(
            user_id=request.headers.get("x-user-id"),
            tenant_id=request.headers.get("x-tenant-id"),
            client_host=request.client.host if request.client else None,
        )
        config = config_for_path(path)

        try:
            result = await self.limiter.check(principal, config)
        except Exception:
            # Fail-open: si Redis falla, no bloquear requests legítimos
            logger.exception("rate_limiter_failed")
            return await call_next(request)

        if not result.allowed:
            return JSONResponse(
                status_code=429,
                content={
                    "detail": f"Rate limit excedido: {result.current}/{result.limit} "
                    f"en ventana de {config.window_seconds}s",
                    "retry_after_seconds": result.retry_after_seconds,
                },
                headers={
                    "Retry-After": str(result.retry_after_seconds or config.window_seconds),
                    "X-RateLimit-Limit": str(result.limit),
                    "X-RateLimit-Remaining": "0",
                },
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(result.limit)
        response.headers["X-RateLimit-Remaining"] = str(max(0, result.limit - result.current))
        return response
