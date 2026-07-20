"""Rate limiting dedicado para el canje de invite_code de comisiones (A0.7).

El `invite_code` es de 6 chars sobre un alfabeto de 30 símbolos (~887M
combinaciones). Sin un freno dedicado, un atacante autenticado puede probar
códigos a lo bruto contra `POST /api/v1/comisiones/join` hasta caer dentro de
una comisión ajena. El rate-limit global del api-gateway (300/min por usuario)
es demasiado laxo para cortar un ataque de fuerza bruta enfocado.

Algoritmo: sliding window por contador con TTL en Redis — el mismo patrón que
`api-gateway/services/rate_limit.py` (que no es un paquete compartido, por eso
se replica acá en vez de importarlo cross-app). Cada intento incrementa un
contador con expiración igual al tamaño de la ventana; si supera el tope se
rechaza con 429.

Dos dimensiones independientes, ambas deben pasar:

  1. **Actor** (`user_id`, fallback IP): cuenta TODOS los intentos de canje del
     mismo actor. Es la defensa principal — un actor no puede exceder
     `actor_config.max_requests` intentos por ventana. Un alumno legítimo hace
     1 intento (o 2-3 si tipea mal), muy por debajo del tope.

  2. **Código** (el `invite_code` tipeado): cuenta SOLO los intentos FALLIDOS
     (código inválido). Corta la fuerza bruta distribuida sobre un mismo código
     desde muchas cuentas. Contar solo fallos evita el falso positivo del
     arranque de clase, donde N alumnos pegan el código CORRECTO en el mismo
     minuto — esos aciertos NO tocan el bucket del código.

Falla ABIERTA: si Redis no responde, se permite el intento (con warning) para
no bloquear inscripciones legítimas por una caída de infraestructura. El
control de fuerza bruta degrada; la disponibilidad del flujo legítimo no.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Awaitable
from dataclasses import dataclass
from typing import Protocol

logger = logging.getLogger(__name__)


class _RedisLike(Protocol):
    # Firmas `def ... -> Awaitable[T]` (no `async def`) a propósito: el
    # cliente real (redis.asyncio.Redis) declara sus métodos así — devuelven
    # Awaitable[T], no Coroutine[Any, Any, T] — para soportar el mismo código
    # en variantes sync/async. `async def` exigiría Coroutine específicamente
    # e incompatibilizaría la conformance estructural con el stub real.
    # `get` amplía a `bytes | str | None` porque el cliente real puede
    # devolver bytes según `decode_responses`; el caller sólo lo compara con
    # `None`, así que la ampliación es segura.
    def incr(self, key: str, /) -> Awaitable[int]: ...
    def expire(self, key: str, seconds: int, /) -> Awaitable[bool]: ...
    def ttl(self, key: str, /) -> Awaitable[int]: ...
    def get(self, key: str, /) -> Awaitable[bytes | str | None]: ...


@dataclass(frozen=True)
class RateLimitConfig:
    window_seconds: int
    max_requests: int


@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    current: int
    limit: int
    retry_after_seconds: int | None = None


# Política por defecto (override por env en config.py):
#   - Actor: 10 intentos / 60s. Un alumno legítimo entra a la primera; 10/min
#     deja margen para tipeos y corta la fuerza bruta en seco.
#   - Código: 20 fallos / 300s. Solo fallos → los aciertos del arranque de
#     clase no cuentan; 20 códigos errados sobre el mismo código en 5 min es
#     inequívocamente un ataque.
DEFAULT_ACTOR_CONFIG = RateLimitConfig(window_seconds=60, max_requests=10)
DEFAULT_CODE_CONFIG = RateLimitConfig(window_seconds=300, max_requests=20)


class InviteJoinRateLimiter:
    """Limiter de dos buckets (actor + código) sobre Redis con fail-open."""

    def __init__(
        self,
        redis: _RedisLike,
        *,
        actor_config: RateLimitConfig = DEFAULT_ACTOR_CONFIG,
        code_config: RateLimitConfig = DEFAULT_CODE_CONFIG,
        key_prefix: str = "ratelimit:invite_join",
    ) -> None:
        self.redis = redis
        self.actor_config = actor_config
        self.code_config = code_config
        self.key_prefix = key_prefix

    def _window_key(self, bucket: str, principal: str, config: RateLimitConfig) -> str:
        window_start = int(time.time()) // config.window_seconds * config.window_seconds
        return f"{self.key_prefix}:{bucket}:{principal}:{window_start}"

    async def _hit(self, bucket: str, principal: str, config: RateLimitConfig) -> RateLimitResult:
        """Consume un slot del bucket. Fail-open ante error de Redis."""
        key = self._window_key(bucket, principal, config)
        try:
            current = await self.redis.incr(key)
            if current == 1:
                # +5s de margen para que el TTL no expire justo antes del check.
                await self.redis.expire(key, config.window_seconds + 5)
            if current > config.max_requests:
                ttl = await self.redis.ttl(key)
                retry = ttl if ttl > 0 else config.window_seconds
                return RateLimitResult(False, current, config.max_requests, retry)
            return RateLimitResult(True, current, config.max_requests)
        except Exception as exc:
            logger.warning(
                "rate-limit de invite_join no disponible (fail-open)",
                extra={"bucket": bucket, "error": str(exc)},
            )
            return RateLimitResult(True, 0, config.max_requests)

    async def check_actor(self, actor: str) -> RateLimitResult:
        """Registra y evalúa un intento de canje del `actor` (user_id | IP)."""
        return await self._hit("actor", actor, self.actor_config)

    async def code_is_exhausted(self, code: str) -> RateLimitResult:
        """Peek (sin incrementar) del bucket de fallos del `code`.

        Devuelve `allowed=False` si el código ya acumuló demasiados fallos en la
        ventana — ahí se corta la fuerza bruta distribuida ANTES de resolverlo.
        """
        config = self.code_config
        key = self._window_key("code", code, config)
        try:
            raw = await self.redis.get(key)
            current = int(raw) if raw is not None else 0
            if current >= config.max_requests:
                ttl = await self.redis.ttl(key)
                retry = ttl if ttl > 0 else config.window_seconds
                return RateLimitResult(False, current, config.max_requests, retry)
            return RateLimitResult(True, current, config.max_requests)
        except Exception as exc:
            logger.warning(
                "rate-limit (code peek) de invite_join no disponible (fail-open)",
                extra={"error": str(exc)},
            )
            return RateLimitResult(True, 0, config.max_requests)

    async def register_code_failure(self, code: str) -> RateLimitResult:
        """Cuenta un intento FALLIDO (código inválido) contra el bucket del código."""
        return await self._hit("code", code, self.code_config)


def actor_principal(user_id: str | None, client_host: str | None) -> str:
    """Deriva el principal del actor: user_id si está autenticado, si no la IP."""
    if user_id:
        return f"u:{user_id}"
    return f"ip:{client_host or 'unknown'}"
