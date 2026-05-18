"""Endpoints de liveness y readiness.

- /health/live  → siempre 200 si el proceso corre
- /health/ready → 200 si Redis (budget store) responde; 503 si no.
                  `llm_provider` es non-critical → degraded si la config
                  está rota.
                  `byok_resolver` es non-critical (Sec 5.6 epic ai-native-completion):
                  degrada cuando BYOK_ENABLED=true y la master key no esta
                  configurada (no rompe readiness — el resolver cae a env_fallback
                  igual). Solo escala a "error" si BYOK_ENABLED=true y NO hay
                  master key NI env fallback.
- /health      → alias de readiness por compatibilidad

Critical: `redis` (budget store).
Non-critical: `llm_provider`, `byok_resolver`.
"""

from __future__ import annotations

import asyncio
import os

from fastapi import APIRouter, Response, status
from platform_observability.health import (
    CheckResult,
    HealthResponse,
    assemble_readiness,
    check_redis,
)

from ai_gateway.config import settings

router = APIRouter(prefix="/health", tags=["health"])

VERSION = "0.1.0"


def _check_llm_provider() -> CheckResult:
    """Valida que la config del provider activo esté coherente.

    No pega al provider externo (no hay endpoint de health público gratuito).
    Solo verifica que si LLM_PROVIDER=anthropic, exista una API key.
    Modo mock siempre OK.
    """
    provider = os.environ.get("LLM_PROVIDER", "anthropic").lower()
    if provider == "mock":
        return CheckResult(ok=True, latency_ms=0)
    if provider == "anthropic":
        if not settings.anthropic_api_key:
            return CheckResult(
                ok=False, latency_ms=0, error="anthropic api key missing"
            )
        return CheckResult(ok=True, latency_ms=0)
    if provider == "mistral":
        if not settings.mistral_api_key:
            return CheckResult(
                ok=False, latency_ms=0, error="mistral api key missing"
            )
        return CheckResult(ok=True, latency_ms=0)
    return CheckResult(
        ok=False,
        latency_ms=0,
        error=f"unknown provider: {provider}",
    )


def _check_byok_resolver() -> CheckResult:
    """Sec 5.6 epic ai-native-completion-and-byok: salud del resolver BYOK.

    No toca la DB (eso lo cubre el redis check + el resolver real durante un
    request). Verifica que la configuracion sea consistente:

    - BYOK_ENABLED=False → ok (el resolver salta directo a env_fallback).
    - BYOK_ENABLED=True + master key valida → ok.
    - BYOK_ENABLED=True + master key ausente/invalida + env fallback presente
      → ok pero degraded (no podemos desencriptar pero hay backup).
    - BYOK_ENABLED=True + sin master key + sin env fallback → error.

    El check NO escala a critical aunque sea error — el resolver ya degrada
    a `none` y los handlers devuelven 503 en consecuencia. Aca solo informamos.
    """
    if not settings.byok_enabled:
        return CheckResult(ok=True, latency_ms=0)
    # Reuso `_get_master_key_bytes` para validar formato sin import circular.
    from ai_gateway.services.byok import _env_fallback_key, _get_master_key_bytes

    has_master = _get_master_key_bytes() is not None
    has_env = any(_env_fallback_key(p) for p in ("anthropic", "openai", "gemini", "mistral"))
    if has_master:
        return CheckResult(ok=True, latency_ms=0)
    if has_env:
        return CheckResult(
            ok=False,
            latency_ms=0,
            error="BYOK_MASTER_KEY missing — solo env fallback disponible",
        )
    return CheckResult(
        ok=False,
        latency_ms=0,
        error="BYOK_MASTER_KEY missing y sin env fallback — resolver inutil",
    )


@router.get("", response_model=HealthResponse)
@router.get("/ready", response_model=HealthResponse)
async def ready(response: Response) -> HealthResponse:
    redis_check, llm_check, byok_check = await asyncio.gather(
        check_redis(settings.redis_url),
        asyncio.to_thread(_check_llm_provider),
        asyncio.to_thread(_check_byok_resolver),
    )
    health, http_code = assemble_readiness(
        service="ai-gateway",
        version=VERSION,
        checks={
            "redis": redis_check,
            "llm_provider": llm_check,
            "byok_resolver": byok_check,
        },
        critical={"redis"},
    )
    response.status_code = http_code
    return health


@router.get("/live", status_code=status.HTTP_200_OK)
async def live() -> dict[str, str]:
    return {"status": "alive"}
