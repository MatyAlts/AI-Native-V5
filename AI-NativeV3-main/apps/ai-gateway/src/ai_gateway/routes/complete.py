"""Endpoints del ai-gateway.

POST /api/v1/complete    → completion (sync, JSON)
POST /api/v1/stream      → SSE de completion streaming
GET  /api/v1/budget      → estado actual del budget del tenant
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from uuid import UUID

import redis.asyncio as redis
from fastapi import APIRouter, Depends, Header, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ai_gateway.config import settings
from ai_gateway.metrics import (
    ai_gateway_budget_remaining_usd,
    ai_gateway_cache_hits_total,
    ai_gateway_fallback_total,
    ai_gateway_request_duration_seconds,
    ai_gateway_requests_total,
    ai_gateway_tokens_total,
)
from ai_gateway.providers.base import (
    AnthropicProvider,
    BaseProvider,
    CompletionRequest,
    GeminiProvider,
    MistralProvider,
    OpenAIProvider,
    get_provider,
)
from ai_gateway.services.budget_and_cache import BudgetTracker, ResponseCache
from ai_gateway.services.byok import (
    increment_env_fallback_usage,
    increment_usage,
    resolve_byok_key,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["ai-gateway"])


# ── Resiliencia del streaming LLM ───────────────────────────────────
# Gemini (y otros) tiran 503 "model overloaded" en picos, AUN en tier pago. Si
# el stream se cortaba a la mitad, el caller veía un token suelto (ej. "M"). Para
# evitarlo: buffereamos la respuesta entera con reintentos y SOLO la emitimos
# cuando está completa — el alumno recibe todo o un error limpio, nunca basura.

_RETRIABLE_MARKERS = (
    "503", "500", "502", "504", "429", "unavailable", "overloaded",
    "high demand", "timeout", "timed out", "rate limit", "temporarily",
    "connection", "reset", "deadline", "resource_exhausted",
)


def _is_retriable(exc: Exception) -> bool:
    msg = str(exc).lower()
    return any(m in msg for m in _RETRIABLE_MARKERS)


async def _collect_stream(provider: BaseProvider, req: CompletionRequest) -> str:
    """Consume el stream del provider y devuelve el texto COMPLETO buffereado."""
    parts: list[str] = []
    async for chunk in provider.stream_complete(req):
        parts.append(chunk)
    return "".join(parts)


async def _collect_with_retry(
    provider: BaseProvider, req: CompletionRequest, max_attempts: int
) -> str:
    """Junta la respuesta completa reintentando errores transitorios.

    Como buffereamos (no emitimos hasta tener todo), un 503 a mitad de stream se
    reintenta de cero sin que el alumno haya visto nada. Solo reintenta errores
    transitorios (503/timeout/etc.); los permanentes fallan rápido.
    """
    last_err: Exception | None = None
    for attempt in range(max_attempts):
        try:
            return await _collect_stream(provider, req)
        except Exception as exc:
            last_err = exc
            if not _is_retriable(exc) or attempt == max_attempts - 1:
                raise
            backoff = 0.6 * (2**attempt)
            logger.warning(
                "llm_stream_retry attempt=%d/%d model=%s backoff=%.1fs err=%s",
                attempt + 1, max_attempts, req.model, backoff, exc,
            )
            await asyncio.sleep(backoff)
    raise last_err if last_err else RuntimeError("stream failed")


def _emit_text_chunks(text: str, size: int = 48):
    """Parte el texto completo en chunks para re-emitir con efecto de tipeo,
    preservando TODOS los caracteres (incluidos saltos de línea)."""
    for i in range(0, len(text), size):
        yield text[i : i + size]


_redis_client: redis.Redis | None = None


def _get_redis() -> redis.Redis:
    global _redis_client
    if _redis_client is None:
        # Resiliencia del cliente de budget+cache (path del tutor bajo carga):
        # health_check_interval evita usar una conexión colgada sin avisar;
        # retry_on_timeout + connect_timeout cortan cuelgues en reconexión.
        # NOTA: esto NO afecta el readiness del servicio — ese usa check_redis()
        # con su propia conexión. El "degraded" pre-existente del ai-gateway es
        # el check non-critical de llm_provider en modo mock, no Redis.
        _redis_client = redis.from_url(
            settings.redis_url,
            decode_responses=True,
            health_check_interval=30,
            retry_on_timeout=True,
            socket_connect_timeout=5,
        )
    return _redis_client


# ── Schemas ─────────────────────────────────────────────────────────


class Message(BaseModel):
    role: str = Field(pattern=r"^(system|user|assistant)$")
    content: str


class CompleteRequest(BaseModel):
    messages: list[Message]
    model: str
    feature: str  # "tutor" | "classifier" | "evaluation" | "tp_generator" | ...
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(default=1024, ge=1, le=8192)
    # Sec 6 epic ai-native-completion-and-byok / ADR-040: opcional. Cuando esta
    # presente, el resolver BYOK busca key con scope=materia primero. Si esta
    # ausente, fallback a scope=tenant (metrica `byok_key_resolution_total`
    # con label `resolved_scope="tenant_fallback_no_materia"`). NO breaking —
    # callers viejos siguen funcionando, solo no se benefician del scope
    # materia para BYOK.
    materia_id: UUID | None = Field(default=None)
    response_format: dict[str, str] | None = Field(default=None)


class CompleteResponse(BaseModel):
    content: str
    model: str
    provider: str
    feature: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    cache_hit: bool
    budget_status: dict


class BudgetOut(BaseModel):
    tenant_id: UUID
    feature: str
    month: str
    used_usd: float
    limit_usd: float
    remaining_usd: float
    exceeded: bool


# ── Auth minimal ────────────────────────────────────────────────────


@dataclass(frozen=True)
class ServiceCaller:
    tenant_id: UUID
    caller: str  # "tutor-service" | "classifier-service" | ...


async def get_caller(
    x_tenant_id: str = Header(),
    x_caller: str = Header(),
) -> ServiceCaller:
    """Los clientes del ai-gateway son OTROS servicios de la plataforma,
    no usuarios finales. Se autentican con service account (en F5 con mTLS
    o JWT de cliente). Por ahora headers X-* son suficientes."""
    return ServiceCaller(tenant_id=UUID(x_tenant_id), caller=x_caller)


# ── BYOK → Provider helpers ──────────────────────────────────────────

_MODEL_TO_PROVIDER: dict[str, str] = {
    "claude": "anthropic",
    "mistral": "mistral",
    "codestral": "mistral",
    "gpt": "openai",
    "gemini": "gemini",
    "gemma": "gemini",
}


def _infer_provider_name(model: str) -> str:
    model_lower = model.lower()
    for prefix, prov in _MODEL_TO_PROVIDER.items():
        if prefix in model_lower:
            return prov
    return "anthropic"


def _make_provider(provider_name: str, api_key: str) -> BaseProvider:
    if provider_name == "anthropic":
        return AnthropicProvider(api_key=api_key)
    if provider_name == "mistral":
        return MistralProvider(api_key=api_key)
    if provider_name == "openai":
        return OpenAIProvider(api_key=api_key)
    if provider_name == "gemini":
        return GeminiProvider(api_key=api_key)
    return AnthropicProvider(api_key=api_key)


# ── Endpoints ────────────────────────────────────────────────────────


@router.post("/complete", response_model=CompleteResponse)
async def complete(
    req: CompleteRequest,
    caller: ServiceCaller = Depends(get_caller),
) -> CompleteResponse:
    """Completion síncrona. Aplica budget + caché antes de llamar al provider."""
    redis_client = _get_redis()
    tracker = BudgetTracker(redis_client)
    cache = ResponseCache(redis_client)

    # Métrica: cada request entra al counter total (denominador del cache hit rate).
    ai_gateway_requests_total.add(1, {"feature": req.feature})

    # 1. Check budget (el límite se toma de la config del tenant; por ahora,
    # un default global. En F4 se consulta academic-service por el límite
    # específico del tenant/feature).
    limit = settings.default_monthly_budget_usd
    status_info = await tracker.check(caller.tenant_id, req.feature, limit)
    if status_info.exceeded:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"Budget excedido para {caller.tenant_id}/{req.feature}: "
                f"gastado ${status_info.used_usd:.2f} de ${limit:.2f}"
            ),
        )

    # 2. Armar request interno
    internal_req = CompletionRequest(
        messages=[m.model_dump() for m in req.messages],
        model=req.model,
        temperature=req.temperature,
        max_tokens=req.max_tokens,
        response_format=req.response_format,
    )

    # 3. Cache check
    cached = await cache.get(internal_req)
    if cached:
        # Métrica: cache hit (numerador del cache hit rate).
        ai_gateway_cache_hits_total.add(1, {"feature": req.feature})
        logger.info(
            "cache_hit tenant=%s feature=%s model=%s",
            caller.tenant_id,
            req.feature,
            req.model,
        )
        return CompleteResponse(
            content=cached.content,
            model=cached.model,
            provider=cached.provider,
            feature=req.feature,
            input_tokens=cached.input_tokens,
            output_tokens=cached.output_tokens,
            cost_usd=0.0,
            cache_hit=True,
            budget_status={
                "used_usd": status_info.used_usd,
                "limit_usd": status_info.limit_usd,
                "remaining_usd": status_info.remaining_usd,
            },
        )

    # 4. Resolver provider: BYOK/env key → provider dinámico, fallback → get_provider()
    resolved = await resolve_byok_key(
        tenant_id=caller.tenant_id,
        provider=_infer_provider_name(req.model),
        materia_id=req.materia_id,
    )
    if resolved and resolved.plaintext:
        provider = _make_provider(resolved.provider, resolved.plaintext)
        logger.info(
            "byok_resolved tenant=%s scope=%s provider=%s key_id=%s",
            caller.tenant_id,
            resolved.scope_resolved,
            resolved.provider,
            resolved.key_id,
        )
    else:
        provider = get_provider()

    _provider_start = time.perf_counter()
    try:
        response = await provider.complete(internal_req)
    except Exception as e:
        ai_gateway_fallback_total.add(1, {"reason": "provider_error"})
        logger.exception("provider_error")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"LLM provider error: {e}",
        )

    # Métrica: latencia del request al provider real (excluye cache hits).
    ai_gateway_request_duration_seconds.record(
        time.perf_counter() - _provider_start,
        {"provider": response.provider},
    )

    # 5. Cache + budget charge + audit usage por key
    await cache.set(internal_req, response)
    new_total = await tracker.charge(caller.tenant_id, req.feature, response.cost_usd)

    # Audit trail: si el resolver encontró una key DB real (no env_fallback),
    # incrementar contadores en `byok_keys_usage` para auditoría doctoral
    # de costos por episodio. UPSERT por (key_id, yyyymm). Idempotente bajo
    # carga concurrente. Best-effort: si falla, NO bloqueamos la respuesta
    # del LLM al caller (degradación graceful para no perder UX por audit).
    if resolved is not None and resolved.key_id is not None:
        try:
            await increment_usage(
                tenant_id=caller.tenant_id,
                key_id=resolved.key_id,
                tokens_input=response.input_tokens,
                tokens_output=response.output_tokens,
                cost_usd=response.cost_usd,
            )
        except Exception:
            logger.exception("byok_increment_usage_failed key_id=%s", resolved.key_id)
    elif resolved is not None and resolved.scope_resolved == "env_fallback":
        # Gap auditoría doctoral 2026-05-07: cuando el resolver cae al
        # env_fallback (key global del env, no del docente), igual hay que
        # registrar el uso en `byok_keys_usage` contra una BYOKKey sentinel
        # determinista por (tenant, provider). Same best-effort guard que
        # arriba — si falla, NO bloqueamos la respuesta al caller.
        try:
            await increment_env_fallback_usage(
                tenant_id=caller.tenant_id,
                provider=resolved.provider,
                tokens_input=response.input_tokens,
                tokens_output=response.output_tokens,
                cost_usd=response.cost_usd,
            )
        except Exception:
            logger.exception(
                "byok_increment_env_fallback_usage_failed tenant=%s provider=%s",
                caller.tenant_id,
                resolved.provider,
            )

    # Métricas: tokens consumidos + budget remaining.
    tenant_label = str(caller.tenant_id)
    ai_gateway_tokens_total.add(
        response.input_tokens,
        {"provider": response.provider, "kind": "input", "tenant_id": tenant_label},
    )
    ai_gateway_tokens_total.add(
        response.output_tokens,
        {"provider": response.provider, "kind": "output", "tenant_id": tenant_label},
    )
    # Budget remaining como delta — el gauge se construye con UpDownCounter
    # (descontamos el cost_usd de este request).
    ai_gateway_budget_remaining_usd.add(-response.cost_usd, {"tenant_id": tenant_label})

    return CompleteResponse(
        content=response.content,
        model=response.model,
        provider=response.provider,
        feature=req.feature,
        input_tokens=response.input_tokens,
        output_tokens=response.output_tokens,
        cost_usd=response.cost_usd,
        cache_hit=False,
        budget_status={
            "used_usd": new_total,
            "limit_usd": limit,
            "remaining_usd": max(0.0, limit - new_total),
        },
    )


@router.post("/stream")
async def stream_complete(
    req: CompleteRequest,
    caller: ServiceCaller = Depends(get_caller),
):
    """SSE streaming. El caller recibe chunks de texto en tiempo real.

    Cada evento es un JSON en el formato:
        data: {"type": "token", "content": "..."}
        data: {"type": "done", "usage": {...}}
    """
    redis_client = _get_redis()
    tracker = BudgetTracker(redis_client)
    limit = settings.default_monthly_budget_usd

    status_info = await tracker.check(caller.tenant_id, req.feature, limit)
    if status_info.exceeded:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Budget excedido",
        )

    internal_req = CompletionRequest(
        messages=[m.model_dump() for m in req.messages],
        model=req.model,
        temperature=req.temperature,
        max_tokens=req.max_tokens,
        stream=True,
    )

    resolved = await resolve_byok_key(
        tenant_id=caller.tenant_id,
        provider=_infer_provider_name(req.model),
        materia_id=req.materia_id,
    )
    if resolved and resolved.plaintext:
        provider = _make_provider(resolved.provider, resolved.plaintext)
        logger.info(
            "byok_stream_resolved tenant=%s scope=%s provider=%s key_id=%s",
            caller.tenant_id,
            resolved.scope_resolved,
            resolved.provider,
            resolved.key_id,
        )
    else:
        provider = get_provider()

    # Capturar el provider name efectivo (anthropic|mistral|mock|...). El
    # SDK de streaming no expone usage final en el mismo objeto que el
    # iterator de chunks, asi que aproximamos por char-count (mismo criterio
    # que la estimacion de cost previa). El campo `provider` viaja exacto.
    effective_provider_name = (
        resolved.provider
        if (resolved and resolved.plaintext)
        else getattr(provider, "name", "mock")
    )
    # Aproximacion grosera de input tokens basada en el largo de los messages
    # (~4 chars por token, heuristica estandar). Para Anthropic real el usage
    # exacto requeriria capturarlo via `stream.get_final_message().usage`
    # post-iteracion, lo cual no expone el contrato actual de `BaseProvider`.
    # Para BYOK auditing usamos los mejores valores disponibles — el `complete`
    # sincrono sigue siendo la fuente precisa.
    approx_input_tokens = sum(len(m.get("content", "")) for m in internal_req.messages) // 4

    async def event_stream():
        # Buffer + retry: juntamos la respuesta ENTERA con reintentos antes de
        # emitir nada. Así un 503 transitorio de Gemini no le deja al alumno un
        # token suelto ("M") — recibe la respuesta completa o un error limpio.
        full_text: str | None = None
        try:
            full_text = await _collect_with_retry(
                provider, internal_req, settings.llm_stream_max_attempts
            )
        except Exception as primary_err:
            # Fallback a un modelo secundario si está configurado.
            fb_model = settings.llm_fallback_model
            if fb_model and fb_model != internal_req.model:
                ai_gateway_fallback_total.add(1, {"reason": "stream_model_fallback"})
                logger.warning(
                    "llm_stream_fallback primary=%s fallback=%s err=%s",
                    internal_req.model, fb_model, primary_err,
                )
                try:
                    full_text = await _collect_with_retry(
                        provider,
                        replace(internal_req, model=fb_model),
                        settings.llm_stream_max_attempts,
                    )
                except Exception:
                    logger.exception("llm_stream_fallback_failed")
            if full_text is None:
                logger.exception("llm_stream_failed model=%s", internal_req.model)
                yield (
                    "data: "
                    + json.dumps(
                        {
                            "type": "error",
                            "message": (
                                "El tutor está sobrecargado en este momento. "
                                "Reintentá en unos segundos."
                            ),
                        }
                    )
                    + "\n\n"
                )
                return

        # Re-emitimos la respuesta completa en chunks (efecto tipeo) + done.
        total_chars = len(full_text)
        for chunk in _emit_text_chunks(full_text):
            yield f"data: {json.dumps({'type': 'token', 'content': chunk})}\n\n"
        approx_output_tokens = total_chars // 4
        est_cost = total_chars / 4 / 1_000_000 * 5.0  # ~$5/M output tokens
        await tracker.charge(caller.tenant_id, req.feature, est_cost)
        # Backlog QA 2026-05-07: incluir `provider`, `tokens_input`,
        # `tokens_output` en el `done` event SSE para que el tutor-service
        # pueda persistirlos en el payload de `tutor_respondio`.
        done_payload = {
            "type": "done",
            "estimated_cost_usd": est_cost,
            "provider": effective_provider_name,
            "tokens_input": approx_input_tokens,
            "tokens_output": approx_output_tokens,
        }
        yield f"data: {json.dumps(done_payload)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/budget", response_model=BudgetOut)
async def get_budget(
    feature: str,
    caller: ServiceCaller = Depends(get_caller),
) -> BudgetOut:
    redis_client = _get_redis()
    tracker = BudgetTracker(redis_client)
    limit = settings.default_monthly_budget_usd
    status_info = await tracker.check(caller.tenant_id, feature, limit)
    return BudgetOut(
        tenant_id=caller.tenant_id,
        feature=feature,
        month=datetime.now(UTC).strftime("%Y-%m"),
        used_usd=status_info.used_usd,
        limit_usd=status_info.limit_usd,
        remaining_usd=status_info.remaining_usd,
        exceeded=status_info.exceeded,
    )
