"""Observabilidad unificada para todos los servicios de la plataforma.

Responsabilidades:
  1. Configurar OTel tracing con OTLP exporter.
  2. Configurar OTel metrics con OTLP exporter (push push push).
  3. Instrumentar automáticamente: FastAPI (traces + metrics HTTP), httpx, SQLAlchemy, Redis.
  4. Propagar contexto (trace_id/span_id) a llamadas outbound HTTP.
  5. Configurar structlog con campos de traza en cada log line.
  6. Capturar errores críticos con Sentry si hay DSN.

Uso:
    from platform_observability import setup_observability

    app = FastAPI(...)
    setup_observability(
        app,
        service_name="tutor-service",
        environment="production",
        otel_endpoint="http://otel-collector:4317",
    )

Esto hace que cada request HTTP entrante cree un span root, y cualquier
llamada outbound (httpx, DB, Redis) se conecte como span hijo, con el
trace_id propagándose vía header `traceparent` (W3C Trace Context).

Adicionalmente, FastAPIInstrumentor emite métricas HTTP automáticas
(`http_server_requests_total`, `http_server_duration_seconds_bucket`) que
viajan por OTLP push al Collector, junto con cualquier métrica custom
emitida via `get_meter(__name__).create_counter(...)` etc.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any


@dataclass
class ObservabilityConfig:
    service_name: str
    environment: str = "development"
    log_level: str = "info"
    log_format: str = "json"
    otel_endpoint: str = "http://localhost:4317"
    otel_enabled: bool = True
    sentry_dsn: str = ""
    # Intervalo de export de métricas al OTel Collector (default 60s — alineado
    # con el scrape interval de Prometheus, evita doble buffering).
    metrics_export_interval_millis: int = 60000


def setup_observability(
    app: Any = None, config: ObservabilityConfig | None = None, **kwargs
) -> None:
    """Configura observabilidad completa.

    Si `app` es una FastAPI, la instrumenta. Si no, solo configura
    tracing + metrics globales (útil para workers headless).

    Parámetros extra por kwargs (service_name, environment, ...) se
    pasan al ObservabilityConfig por conveniencia.
    """
    if config is None:
        config = ObservabilityConfig(**kwargs)

    _setup_logging(config)

    if config.otel_enabled and _can_import_otel():
        # Metrics ANTES de tracing — así FastAPIInstrumentor puede recibir
        # el meter_provider global cuando se invoca dentro de _setup_tracing.
        _setup_metrics(config)
        _setup_tracing(config, app)

    if config.sentry_dsn:
        _setup_sentry(config)


def setup_metrics(config: ObservabilityConfig | None = None, **kwargs) -> None:
    """Configura SOLO metrics (sin tracing/logging/sentry).

    Pensado para casos donde un servicio o worker quiere emisión de métricas
    OTLP sin el resto del stack. La invocación normal (servicios FastAPI del
    piloto) usa `setup_observability()` que ya llama internamente a esta.
    """
    if config is None:
        config = ObservabilityConfig(**kwargs)
    _setup_metrics(config)


def _can_import_otel() -> bool:
    try:
        import opentelemetry  # noqa: F401

        return True
    except ImportError:
        return False


def _setup_logging(config: ObservabilityConfig) -> None:
    """Configura structlog con trace context en cada log line."""
    try:
        import structlog
    except ImportError:
        # Sin structlog, usar logging estándar
        logging.basicConfig(
            level=getattr(logging, config.log_level.upper(), logging.INFO),
            format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        )
        return

    processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        _add_trace_context,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]
    if config.log_format == "json":
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer())

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, config.log_level.upper(), logging.INFO)
        ),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def _add_trace_context(logger: Any, method_name: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    """Inyecta trace_id y span_id en cada log line cuando hay span activo."""
    try:
        from opentelemetry import trace

        span = trace.get_current_span()
        if span is None:
            return event_dict
        ctx = span.get_span_context()
        if ctx.trace_id != 0:
            event_dict["trace_id"] = f"{ctx.trace_id:032x}"
            event_dict["span_id"] = f"{ctx.span_id:016x}"
    except Exception:
        pass
    return event_dict


def _setup_metrics(config: ObservabilityConfig) -> None:
    """Configura MeterProvider con OTLPMetricExporter push al Collector.

    NO expone endpoint /metrics por servicio — todo viaja por OTLP gRPC al
    Collector ya wireado en infrastructure/observability/otel-collector-config.yaml.

    Cardinalidad: el código que emite métricas DEBE respetar la lista cerrada
    de labels permitidas (ver openspec/specs/metrics-instrumentation-otlp/spec.md).
    `student_pseudonym`, `episode_id`, `user_id` y cualquier UUID per-instancia
    están PROHIBIDOS — explotaría Prometheus en cardinalidad y expondría
    correlation cross-metric (privacidad).
    """
    try:
        from opentelemetry import metrics
        from opentelemetry.sdk.metrics import MeterProvider
        from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
        from opentelemetry.sdk.resources import SERVICE_NAME, Resource
    except ImportError:
        # SDK metrics no disponible — degradar silenciosamente. get_meter()
        # devuelve un noop que no rompe el código que llame a create_counter().
        return

    resource = Resource.create(
        {
            SERVICE_NAME: config.service_name,
            "deployment.environment": config.environment,
        }
    )

    try:
        from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import (
            OTLPMetricExporter,
        )

        exporter = OTLPMetricExporter(endpoint=config.otel_endpoint, insecure=True)
        reader = PeriodicExportingMetricReader(
            exporter,
            export_interval_millis=config.metrics_export_interval_millis,
        )
        provider = MeterProvider(resource=resource, metric_readers=[reader])
    except ImportError:
        # Sin exporter OTLP, MeterProvider sin readers — métricas se crean
        # pero no se exportan. El código del servicio sigue funcionando.
        provider = MeterProvider(resource=resource)

    metrics.set_meter_provider(provider)


def _setup_tracing(config: ObservabilityConfig, app: Any) -> None:
    """Configura OTel tracing + instrumenta libs disponibles.

    Si _setup_metrics() ya corrió, `metrics.get_meter_provider()` devuelve el
    MeterProvider configurado y FastAPIInstrumentor lo recibe vía argument
    para emitir métricas HTTP auto.
    """
    from opentelemetry import trace
    from opentelemetry.sdk.resources import SERVICE_NAME, Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    # Resource con metadata del servicio
    resource = Resource.create(
        {
            SERVICE_NAME: config.service_name,
            "deployment.environment": config.environment,
        }
    )

    provider = TracerProvider(resource=resource)

    # Exporter OTLP (solo si endpoint está configurado y la lib está disponible)
    try:
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
            OTLPSpanExporter,
        )

        exporter = OTLPSpanExporter(endpoint=config.otel_endpoint, insecure=True)
        provider.add_span_processor(BatchSpanProcessor(exporter))
    except ImportError:
        # Si el exporter no está disponible, tracing funciona sin export
        pass

    trace.set_tracer_provider(provider)

    # Propagator W3C Trace Context (default, explicitado por robustez)
    from opentelemetry.propagate import set_global_textmap
    from opentelemetry.trace.propagation.tracecontext import (
        TraceContextTextMapPropagator,
    )

    set_global_textmap(TraceContextTextMapPropagator())

    # Instrumentar FastAPI si hay app — pasamos meter_provider para que la
    # auto-instrumentación HTTP (http_server_requests_total / duration_seconds)
    # vaya por el mismo provider que setup_metrics() configuró.
    if app is not None:
        try:
            from opentelemetry import metrics as _metrics_api
            from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

            FastAPIInstrumentor.instrument_app(
                app,
                tracer_provider=provider,
                meter_provider=_metrics_api.get_meter_provider(),
            )
        except ImportError:
            pass
        except TypeError:
            # Versiones viejas de FastAPIInstrumentor no aceptan meter_provider —
            # caer al instrument básico sin métricas HTTP. Las métricas custom
            # del piloto siguen funcionando, solo se pierden las HTTP auto.
            try:
                from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

                FastAPIInstrumentor.instrument_app(app)
            except ImportError:
                pass

    # Auto-instrumentar libs populares (opt-in)
    _try_instrument_httpx()
    _try_instrument_sqlalchemy()
    _try_instrument_redis()


def _try_instrument_httpx() -> None:
    """Instrumenta httpx para propagar trace context en llamadas outbound."""
    try:
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

        HTTPXClientInstrumentor().instrument()
    except ImportError:
        pass


def _try_instrument_sqlalchemy() -> None:
    try:
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

        SQLAlchemyInstrumentor().instrument()
    except ImportError:
        pass


def _try_instrument_redis() -> None:
    try:
        from opentelemetry.instrumentation.redis import RedisInstrumentor

        RedisInstrumentor().instrument()
    except ImportError:
        pass


def _setup_sentry(config: ObservabilityConfig) -> None:
    """Captura errores críticos a Sentry."""
    try:
        import sentry_sdk

        sentry_sdk.init(
            dsn=config.sentry_dsn,
            environment=config.environment,
            traces_sample_rate=0.0,  # Usamos OTel para traces, Sentry solo errores
            profiles_sample_rate=0.0,
            release=os.environ.get("SERVICE_VERSION", "unknown"),
        )
    except ImportError:
        pass


# ── Helpers para usar en código de negocio ─────────────────────────────


def get_tracer(name: str):
    """Obtiene un tracer para crear spans manuales.

    Uso:
        tracer = get_tracer(__name__)
        with tracer.start_as_current_span("mi_operacion", attributes={"foo": "bar"}):
            do_stuff()
    """
    try:
        from opentelemetry import trace

        return trace.get_tracer(name)
    except ImportError:
        return _NoopTracer()


def get_meter(name: str):
    """Obtiene un meter para crear métricas custom (Counter, Histogram, Gauge).

    Uso:
        meter = get_meter(__name__)
        events_total = meter.create_counter(
            "ctr_events_total",
            description="Eventos CTR escritos al stream",
            unit="1",
        )
        events_total.add(1, {"tenant_id": tenant_id, "event_type": event_type})

    REGLA DE CARDINALIDAD: las labels permitidas son una lista cerrada
    documentada en openspec/specs/metrics-instrumentation-otlp/spec.md.
    `student_pseudonym`, `episode_id`, `user_id`, y cualquier UUID
    per-instancia están PROHIBIDAS — usalas en el plano API
    (analytics-service endpoints), NO en métricas Prometheus.
    """
    try:
        from opentelemetry import metrics

        return metrics.get_meter(name)
    except ImportError:
        return _NoopMeter()


class _NoopTracer:
    """Fallback si OTel no está disponible (tests offline)."""

    def start_as_current_span(self, name: str, **kwargs):
        from contextlib import nullcontext

        return nullcontext()


class _NoopMeter:
    """Fallback si OTel SDK metrics no está disponible.

    Las llamadas a create_counter/create_histogram/create_gauge devuelven
    objetos noop cuyo .add()/.record() es no-op. Permite que el código del
    servicio funcione aunque metrics no esté wireado (tests offline, etc.).
    """

    def create_counter(self, *args, **kwargs):
        return _NoopInstrument()

    def create_histogram(self, *args, **kwargs):
        return _NoopInstrument()

    def create_up_down_counter(self, *args, **kwargs):
        return _NoopInstrument()

    def create_gauge(self, *args, **kwargs):
        return _NoopInstrument()

    def create_observable_gauge(self, *args, **kwargs):
        return _NoopInstrument()


class _NoopInstrument:
    def add(self, *args, **kwargs):
        pass

    def record(self, *args, **kwargs):
        pass

    def set(self, *args, **kwargs):
        pass


from platform_observability.health import (
    DEFAULT_HTTP_CACHE_TTL_SEC,
    DEFAULT_TIMEOUT_SEC,
    CheckResult,
    HealthResponse,
    assemble_readiness,
    check_http,
    check_postgres,
    check_redis,
)

__all__ = [
    "DEFAULT_HTTP_CACHE_TTL_SEC",
    "DEFAULT_TIMEOUT_SEC",
    "CheckResult",
    "HealthResponse",
    "ObservabilityConfig",
    "assemble_readiness",
    "check_http",
    "check_postgres",
    "check_redis",
    "get_meter",
    "get_tracer",
    "setup_metrics",
    "setup_observability",
]
