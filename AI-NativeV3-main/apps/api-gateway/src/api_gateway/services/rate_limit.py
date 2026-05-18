"""Rate limiting para el api-gateway usando sliding window en Redis.

Algoritmo: sliding log con Redis SET-EXPIRE.
  - Cada request del principal (user_id | tenant_id | ip) incrementa un
    contador con TTL igual al tamaño de ventana.
  - Si el contador supera `limit`, se rechaza con 429.

Configuración por tier de endpoint:
  - /api/v1/episodes/*/message — alto costo (LLM): 30 req/min por usuario
  - /api/v1/retrieve — medio costo: 60 req/min por usuario
  - Otros endpoints: 300 req/min por usuario (default)

Principal de rate limit:
  - Si hay X-User-Id → rate limit por usuario
  - Si no → por IP (fallback, menos efectivo contra abuso)
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Protocol

logger = logging.getLogger(__name__)


class _RedisLike(Protocol):
    async def incr(self, key: str) -> int: ...
    async def expire(self, key: str, seconds: int) -> bool: ...
    async def ttl(self, key: str) -> int: ...


@dataclass
class RateLimitConfig:
    window_seconds: int
    max_requests: int

    def __str__(self) -> str:
        return f"{self.max_requests}/{self.window_seconds}s"


@dataclass
class RateLimitResult:
    allowed: bool
    current: int
    limit: int
    retry_after_seconds: int | None = None


DEFAULT_LIMIT = RateLimitConfig(window_seconds=60, max_requests=300)

# Override por path prefix (del más específico al más genérico)
PATH_LIMITS: list[tuple[str, RateLimitConfig]] = [
    ("/api/v1/episodes", RateLimitConfig(window_seconds=60, max_requests=30)),
    # episodes incluye /message, /close, POST /episodes — todos consumen LLM o CTR
    ("/api/v1/retrieve", RateLimitConfig(window_seconds=60, max_requests=60)),
    ("/api/v1/classify_episode", RateLimitConfig(window_seconds=60, max_requests=20)),
]


def config_for_path(path: str) -> RateLimitConfig:
    """Devuelve el config más específico aplicable al path."""
    for prefix, config in PATH_LIMITS:
        if path.startswith(prefix):
            return config
    return DEFAULT_LIMIT


class RateLimiter:
    """Rate limiter con Redis. Sliding window por contador con TTL.

    Implementación simple y robusta: un key por (principal, ventana).
    Si se necesita precision exacta se puede migrar a sorted set.
    """

    def __init__(self, redis: _RedisLike, key_prefix: str = "ratelimit") -> None:
        self.redis = redis
        self.key_prefix = key_prefix

    def _key(self, principal: str, window_start: int) -> str:
        return f"{self.key_prefix}:{principal}:{window_start}"

    async def check(self, principal: str, config: RateLimitConfig) -> RateLimitResult:
        """Consume un slot. Devuelve si está permitido."""
        window_start = int(time.time()) // config.window_seconds * config.window_seconds
        key = self._key(principal, window_start)

        # Contador atómico + TTL en primer incremento
        current = await self.redis.incr(key)
        if current == 1:
            await self.redis.expire(key, config.window_seconds + 5)
            # margen extra para evitar TTLs que expiren justo antes del check

        if current > config.max_requests:
            ttl = await self.redis.ttl(key)
            retry = ttl if ttl > 0 else config.window_seconds
            return RateLimitResult(
                allowed=False,
                current=current,
                limit=config.max_requests,
                retry_after_seconds=retry,
            )

        return RateLimitResult(
            allowed=True,
            current=current,
            limit=config.max_requests,
        )


def principal_from_request(
    user_id: str | None,
    tenant_id: str | None,
    client_host: str | None,
) -> str:
    """Deriva el principal para rate-limiting.

    Orden de preferencia:
      1. user_id (identifica al usuario autenticado)
      2. tenant_id (si no hay user, al menos el tenant)
      3. IP (fallback, puede ser spoofeable detrás de proxy)
    """
    if user_id:
        return f"u:{user_id}"
    if tenant_id:
        return f"t:{tenant_id}"
    return f"ip:{client_host or 'unknown'}"
