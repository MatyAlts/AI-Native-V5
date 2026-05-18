"""Rate limit por usuario con slowapi (in-memory storage).

Protege al gateway contra runaway clients (ej. bug de useEffect en loop en
frontends) limitando requests/minuto por `X-User-Id`. Si no hay header,
fallback a IP remota. Storage es in-memory (suficiente para piloto local);
NO usar Redis acá para no duplicar el path con el `RateLimitMiddleware`
preexistente (que sí usa Redis y rules por path).

Caso documentado en CLAUDE.md: AcademicContextSelector con dep inestable en
useEffect generó 2146 req/60s desde un solo usuario antes del fix con
useCallback.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

logger = logging.getLogger(__name__)

from fastapi import Request
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.responses import JSONResponse, Response

from api_gateway.config import settings

# Paths exentos del rate limit por usuario. Health/metrics/docs NO deben
# limitarse porque (a) son llamados por probes/scrapers que comparten user_id
# o IP, y (b) bloquearlos rompe operación más de lo que protege.
_EXEMPT_PREFIXES: tuple[str, ...] = (
    "/health",
    "/metrics",
    "/docs",
    "/redoc",
    "/openapi.json",
)


def _user_or_ip_key(request: Request) -> str:
    """Key function: X-User-Id si vino, sino IP remota.

    Devuelve un prefijo distinguible para evitar colisiones entre buckets
    "por user_id" y "por IP" (un user_id por casualidad igual a una IP no
    debería compartir bucket).
    """
    user_id = request.headers.get("x-user-id")
    if user_id:
        return f"uid:{user_id}"
    return f"ip:{get_remote_address(request)}"


# Limiter global del módulo. `default_limits` aplica a todo request que pase
# por el `SlowAPIMiddleware` salvo que la ruta esté decorada con `@limiter.exempt`
# o que el filtro previo (en `should_apply`) la skipee.
limiter: Limiter = Limiter(
    key_func=_user_or_ip_key,
    default_limits=[settings.rate_limit_default],
    headers_enabled=True,
    # Storage por defecto = in-memory (`memory://`). Suficiente para piloto.
    # Cuando se quiera compartir estado entre réplicas, cambiar a Redis vía
    # `storage_uri="redis://..."` (NO hacer aún, es nice-to-have).
)


def rate_limit_exceeded_handler(
    request: Request,  # noqa: ARG001 — firma requerida por FastAPI exception handlers
    exc: RateLimitExceeded,
) -> Response:
    """Handler 429 con `Retry-After` en segundos.

    `exc.detail` viene como string tipo "100 per 1 minute". Calculamos
    `Retry-After` aproximado a la ventana del límite (60s para "/minute").
    """
    # slowapi expone el `Limit` violado en `exc.limit`. Su `.limit` es el
    # `RateLimitItem` con `.get_expiry()`. Default conservador: 60s.
    retry_after = 60
    limit_obj = getattr(exc, "limit", None)
    if limit_obj is not None:
        inner = getattr(limit_obj, "limit", None)
        if inner is not None and hasattr(inner, "get_expiry"):
            try:
                retry_after = int(inner.get_expiry())
            except Exception:  # noqa: BLE001
                retry_after = 60

    return JSONResponse(
        status_code=429,
        content={
            "detail": "Rate limit excedido para este usuario",
            "limit": str(exc.detail),
            "retry_after_seconds": retry_after,
        },
        headers={"Retry-After": str(retry_after)},
    )


def should_apply(request: Request) -> bool:
    """Filtro: aplicar rate limit solo a `/api/v1/*` y nunca a exentos."""
    path = request.url.path
    if any(path.startswith(p) for p in _EXEMPT_PREFIXES):
        return False
    return path.startswith("/api/v1/")


class UserRateLimitMiddleware:
    """ASGI middleware que delega al `limiter` global para rutas `/api/v1/*`.

    No usamos `SlowAPIMiddleware` directamente porque queremos:
      1. Filtrar por prefijo `/api/v1/` ANTES de tocar el limiter (cheaper).
      2. Exentar `/health*`, `/metrics`, `/docs`, etc. sin decorar cada ruta.

    Internamente llama a `limiter.limit(...)` reutilizando el storage
    in-memory configurado en el `Limiter` global.
    """

    def __init__(self, app: Callable[..., Awaitable[None]]) -> None:
        self.app = app

    async def __call__(self, scope: dict, receive: Callable, send: Callable) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive=receive)
        if not should_apply(request):
            await self.app(scope, receive, send)
            return

        # Chequeo manual contra el limiter usando la API de bajo nivel.
        # `limiter.limiter` es el `MovingWindowRateLimiter` interno de la lib
        # `limits`; lo usamos directo para no depender de decoradores por-ruta.
        key = _user_or_ip_key(request)
        # Tomamos el primer (y único) default limit configurado.
        parsed_limits = limiter._default_limits  # noqa: SLF001 — API interna estable en 0.1.x
        if not parsed_limits:
            await self.app(scope, receive, send)
            return

        # `_default_limits` es lista de `LimitGroup`; cada `LimitGroup` itera
        # a `Limit` (wrapper de slowapi). El `RateLimitItem` real que el
        # `FixedWindowRateLimiter.hit` necesita está en `limit_obj.limit`.
        for limit_group in parsed_limits:
            for limit_obj in limit_group:
                rate_limit_item = limit_obj.limit
                allowed = limiter.limiter.hit(rate_limit_item, key, request.url.path)
                if not allowed:
                    # `RateLimitExceeded.__init__` espera un `Limit` (no un
                    # `LimitGroup`): accede a `limit.limit` para extraer el
                    # `RateLimitItem` y armar el `detail`. Pasarle el group
                    # directo revienta con AttributeError.
                    exc = RateLimitExceeded(limit_obj)
                    response = rate_limit_exceeded_handler(request, exc)
                    await response(scope, receive, send)
                    return

        await self.app(scope, receive, send)
