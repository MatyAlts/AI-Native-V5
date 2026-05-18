"""Métricas custom de ai-gateway emitidas via OTel SDK.

Cardinality rule: `student_pseudonym`/`episode_id`/`prompt_id` PROHIBIDOS.
Las labels permitidas acá son `tenant_id`, `provider`, `kind` (input/output),
`reason` (fallback), `feature`.

ADR-039 (Sec 13.1-13.2 epic ai-native-completion-and-byok): contadores BYOK
NUNCA llevan `scope_id` (UUID) como label — explosion de cardinality. Se usa
`resolved_scope` (enum acotado: materia | tenant | env_fallback | none).
"""

from __future__ import annotations

from platform_observability import get_meter

_meter = get_meter("ai-gateway")

# Tokens consumidos por proveedor — incluye al mock (declarado como dato del
# piloto en el dashboard 3).
ai_gateway_tokens_total = _meter.create_counter(
    "ai_gateway_tokens_total",
    description="Tokens consumidos por requests al ai-gateway (input/output).",
    unit="1",
)

# Budget remanente USD por tenant — gauge (UpDownCounter para que pueda subir
# cuando se resetea mensualmente y bajar al consumir).
ai_gateway_budget_remaining_usd = _meter.create_up_down_counter(
    "ai_gateway_budget_remaining_usd",
    description="Budget USD restante del tenant en el período actual.",
    unit="USD",
)

# Latencia del request al provider externo (excluye cache hits).
ai_gateway_request_duration_seconds = _meter.create_histogram(
    "ai_gateway_request_duration_seconds",
    description="Latencia de requests al provider LLM (excluye cache hits).",
    unit="s",
)

# Fallback events — cuando el provider primario falla y se cae al secundario.
ai_gateway_fallback_total = _meter.create_counter(
    "ai_gateway_fallback_total",
    description="Eventos de fallback al provider secundario.",
    unit="1",
)

# Cache hit rate components.
ai_gateway_cache_hits_total = _meter.create_counter(
    "ai_gateway_cache_hits_total",
    description="Requests respondidos desde cache.",
    unit="1",
)

ai_gateway_requests_total = _meter.create_counter(
    "ai_gateway_requests_total",
    description="Total de requests recibidos por el ai-gateway.",
    unit="1",
)

# ── BYOK metrics (Sec 13.1-13.2, ADR-039) ─────────────────────────────────

# Uso de keys BYOK por scope. Labels: provider, scope_type (tenant|materia|...),
# resolved_scope (lo mismo, redundante por compat con dashboard ya planeado).
# NO scope_id — cardinality budget.
byok_key_usage_total = _meter.create_counter(
    "byok_key_usage_total",
    description="Veces que se uso una BYOK key por scope.",
    unit="1",
)

# Resolucion del resolver jerarquico. resolved_scope ∈ {materia,tenant,env_fallback,none}.
byok_key_resolution_total = _meter.create_counter(
    "byok_key_resolution_total",
    description="Resoluciones de BYOK keys agrupadas por scope final.",
    unit="1",
)

# Latencia del resolver (lookup DB + decrypt). SLO p99 < 50ms.
byok_key_resolution_duration_seconds = _meter.create_histogram(
    "byok_key_resolution_duration_seconds",
    description="Latencia del resolver BYOK (DB lookup + decrypt).",
    unit="s",
)


__all__ = [
    "ai_gateway_budget_remaining_usd",
    "ai_gateway_cache_hits_total",
    "ai_gateway_fallback_total",
    "ai_gateway_request_duration_seconds",
    "ai_gateway_requests_total",
    "ai_gateway_tokens_total",
    "byok_key_resolution_duration_seconds",
    "byok_key_resolution_total",
    "byok_key_usage_total",
]
