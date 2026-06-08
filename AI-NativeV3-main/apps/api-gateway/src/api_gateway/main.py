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
from api_gateway.services.jwt_validator import ClerkJWTValidator


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
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── JWT validation (F5) ─────────────────────────────────────────────
# El validator se construye solo si hay issuer configurado. Si no, el
# middleware corre en modo dev_trust_headers (acepta X-* tal cual vienen).
_jwt_validator: JWTValidator | None = None
if settings.jwt_issuer:
    _validator_config = JWTValidatorConfig(
        issuer=settings.jwt_issuer,
        audience=settings.jwt_audience,
        jwks_uri=settings.jwt_jwks_uri,
        jwks_cache_ttl_seconds=settings.jwt_jwks_cache_ttl,
    )
    if settings.auth_provider == "clerk":
        _jwt_validator = ClerkJWTValidator(
            config=_validator_config,
            fixed_tenant_id=settings.demo_tenant_id,
            base_roles=frozenset(
                r.strip() for r in settings.clerk_base_roles.split(",") if r.strip()
            ),
        )
    else:
        _jwt_validator = JWTValidator(config=_validator_config)

app.add_middleware(
    JWTMiddleware,
    validator=_jwt_validator,
    dev_trust_headers=settings.dev_trust_headers,
    demo_user_id=settings.demo_user_id,
    demo_tenant_id=settings.demo_tenant_id,
    demo_user_email=settings.demo_user_email,
    demo_user_roles=settings.demo_user_roles,
    demo_user_realm=settings.demo_user_realm,
)

# ── Rate limit (F4) ─────────────────────────────────────────────────
_rate_limit_redis = redis.from_url(
    settings.rate_limit_redis_url,
    decode_responses=True,
    # Resiliencia (FIX-20): el rate limit no debe romperse por una conexión colgada.
    health_check_interval=30,
    retry_on_timeout=True,
    socket_keepalive=True,
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
app.include_router(health.api_router)
app.include_router(proxy.router)


@app.get("/")
async def root() -> dict[str, str]:
    return {
        "service": "api-gateway",
        "version": "0.1.0",
        "status": "operational",
    }
