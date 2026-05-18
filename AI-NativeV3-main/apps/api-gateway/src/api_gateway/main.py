"""api-gateway: entrada única con JWT validation, rate limit y proxy."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import redis.asyncio as redis
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from slowapi.errors import RateLimitExceeded

from api_gateway.config import settings
from api_gateway.middleware import (
    JWTMiddleware,
    RateLimitMiddleware,
    UserRateLimitMiddleware,
    user_rate_limit_exceeded_handler,
    user_rate_limiter,
)
from api_gateway.observability import setup_observability
from api_gateway.routes import health, proxy
from api_gateway.services import JWTValidator, JWTValidatorConfig


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    setup_observability(app)
    yield


app = FastAPI(
    title="api-gateway",
    description="Entrada única de la plataforma — JWT + rate limit + proxy",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── JWT validation (F5) ─────────────────────────────────────────────
# El validator se construye solo si hay issuer configurado. Si no, el
# middleware corre en modo dev_trust_headers (acepta X-* tal cual vienen).
_jwt_validator: JWTValidator | None = None
if settings.jwt_issuer:
    _jwt_validator = JWTValidator(
        config=JWTValidatorConfig(
            issuer=settings.jwt_issuer,
            audience=settings.jwt_audience,
            jwks_uri=settings.jwt_jwks_uri,
            jwks_cache_ttl_seconds=settings.jwt_jwks_cache_ttl,
        )
    )

app.add_middleware(
    JWTMiddleware,
    validator=_jwt_validator,
    dev_trust_headers=settings.dev_trust_headers,
)

# ── Rate limit (F4) ─────────────────────────────────────────────────
_rate_limit_redis = redis.from_url(
    settings.rate_limit_redis_url,
    decode_responses=True,
)
app.add_middleware(RateLimitMiddleware, redis_client=_rate_limit_redis)

# ── Rate limit por usuario (slowapi, in-memory) ─────────────────────
# Cap adicional contra runaway clients (ej. useEffect en loop). Por
# `X-User-Id` con fallback a IP; 100/min default; solo `/api/v1/*`.
# El middleware queda OFF cuando `rate_limit_enabled=False` (útil en tests).
if settings.rate_limit_enabled:
    app.state.limiter = user_rate_limiter
    app.add_exception_handler(RateLimitExceeded, user_rate_limit_exceeded_handler)
    app.add_middleware(UserRateLimitMiddleware)

app.include_router(health.router)
app.include_router(proxy.router)


@app.get("/")
async def root() -> dict[str, str]:
    return {
        "service": "api-gateway",
        "version": "0.1.0",
        "status": "operational",
    }
