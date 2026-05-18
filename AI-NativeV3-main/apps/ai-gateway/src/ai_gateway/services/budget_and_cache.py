"""Budget tracking + caché de respuestas idempotentes.

Budget: por tenant + por feature. Si el gasto mensual supera el límite,
se rechazan requests hasta el próximo mes (o hasta que docente_admin
suba el límite).

Caché: para requests con `temperature=0` (determinista), guardamos el
resultado bajo `hash(input + model + params)`. En clasificación esto
ahorra ~40% de invocaciones.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from uuid import UUID

import redis.asyncio as redis

from ai_gateway.providers.base import CompletionRequest, CompletionResponse

logger = logging.getLogger(__name__)


@dataclass
class BudgetStatus:
    used_usd: float
    limit_usd: float
    remaining_usd: float
    exceeded: bool


class BudgetTracker:
    """Contabilidad de gasto por (tenant, feature) con Redis.

    Clave: `aigw:budget:{tenant_id}:{feature}:{YYYY-MM}` → float acumulado.
    Limit check se hace atómicamente antes de llamar al provider.
    """

    def __init__(self, redis_client: redis.Redis) -> None:
        self.redis = redis_client

    def _key(self, tenant_id: UUID, feature: str, month: str) -> str:
        return f"aigw:budget:{tenant_id}:{feature}:{month}"

    async def check(self, tenant_id: UUID, feature: str, limit_usd: float) -> BudgetStatus:
        from datetime import UTC, datetime

        month = datetime.now(UTC).strftime("%Y-%m")
        key = self._key(tenant_id, feature, month)
        used_str = await self.redis.get(key)
        used = float(used_str) if used_str else 0.0
        remaining = max(0.0, limit_usd - used)
        return BudgetStatus(
            used_usd=used,
            limit_usd=limit_usd,
            remaining_usd=remaining,
            exceeded=used >= limit_usd,
        )

    async def charge(self, tenant_id: UUID, feature: str, cost_usd: float) -> float:
        """Suma al contador. Devuelve el nuevo total."""
        from datetime import UTC, datetime

        month = datetime.now(UTC).strftime("%Y-%m")
        key = self._key(tenant_id, feature, month)
        new_total = await self.redis.incrbyfloat(key, cost_usd)
        # TTL de 35 días para que expire pasado el mes
        await self.redis.expire(key, 35 * 24 * 3600)
        return float(new_total)


class ResponseCache:
    """Caché de respuestas idempotentes (temperature=0).

    Solo cachea si `temperature=0` — en otros casos, cada invocación
    puede dar resultados distintos y cachear sería incorrecto.
    """

    def __init__(self, redis_client: redis.Redis, ttl_seconds: int = 7 * 24 * 3600) -> None:
        self.redis = redis_client
        self.ttl = ttl_seconds

    def _key(self, request: CompletionRequest) -> str:
        canonical = json.dumps(
            {
                "messages": request.messages,
                "model": request.model,
                "temperature": request.temperature,
                "max_tokens": request.max_tokens,
            },
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        )
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        return f"aigw:cache:{digest}"

    def _is_cacheable(self, request: CompletionRequest) -> bool:
        return request.temperature == 0.0 and not request.stream

    async def get(self, request: CompletionRequest) -> CompletionResponse | None:
        if not self._is_cacheable(request):
            return None
        raw = await self.redis.get(self._key(request))
        if raw is None:
            return None
        try:
            data = json.loads(raw)
            return CompletionResponse(**data, cache_hit=True)
        except Exception:
            return None

    async def set(self, request: CompletionRequest, response: CompletionResponse) -> None:
        if not self._is_cacheable(request):
            return
        # No guardar cache_hit en el blob (se setea al leer)
        payload = {
            "content": response.content,
            "model": response.model,
            "provider": response.provider,
            "input_tokens": response.input_tokens,
            "output_tokens": response.output_tokens,
            "cost_usd": response.cost_usd,
        }
        await self.redis.setex(
            self._key(request),
            self.ttl,
            json.dumps(payload),
        )
