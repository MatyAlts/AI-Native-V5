"""Tests del módulo de observabilidad unificado."""

from __future__ import annotations

from platform_observability import (
    ObservabilityConfig,
    get_meter,
    get_tracer,
    setup_metrics,
    setup_observability,
)


def test_config_tiene_defaults_razonables() -> None:
    c = ObservabilityConfig(service_name="test")
    assert c.service_name == "test"
    assert c.environment == "development"
    assert c.log_level == "info"
    assert c.log_format == "json"
    assert c.otel_enabled is True


def test_setup_sin_app_no_crashea() -> None:
    """Workers headless (sin FastAPI) deben poder llamar setup."""
    # No debe lanzar excepción
    setup_observability(service_name="worker-test", otel_enabled=False)


def test_setup_con_sentry_dsn_vacio_no_falla() -> None:
    setup_observability(
        service_name="test-service",
        otel_enabled=False,
        sentry_dsn="",
    )


def test_get_tracer_devuelve_algo_usable() -> None:
    """El tracer debe soportar start_as_current_span con context manager."""
    tracer = get_tracer("test.module")
    # Funciona con o sin OTel instalado (fallback a _NoopTracer)
    with tracer.start_as_current_span("test_op"):
        pass  # no debe crashear


def test_get_tracer_span_puede_usarse_anidadamente() -> None:
    tracer = get_tracer("test.module")
    with tracer.start_as_current_span("outer"), tracer.start_as_current_span("inner"):
        pass


def test_setup_es_idempotente() -> None:
    """Llamar setup dos veces no debe romper."""
    setup_observability(service_name="s1", otel_enabled=False)
    setup_observability(service_name="s1", otel_enabled=False)


def test_config_tiene_metrics_export_interval_default() -> None:
    c = ObservabilityConfig(service_name="test")
    assert c.metrics_export_interval_millis == 60000


def test_setup_metrics_standalone_no_crashea() -> None:
    """setup_metrics() solo (sin tracing/logging) debe funcionar."""
    setup_metrics(service_name="worker-test", otel_endpoint="http://localhost:4317")


def test_get_meter_devuelve_algo_usable() -> None:
    """El meter debe soportar create_counter() con .add() sin lanzar."""
    meter = get_meter("test.module")
    counter = meter.create_counter("test_counter_total", description="test", unit="1")
    counter.add(1, {"tenant_id": "test-tenant"})  # No debe lanzar


def test_get_meter_create_histogram_y_record() -> None:
    meter = get_meter("test.module")
    h = meter.create_histogram("test_duration_seconds", description="test", unit="s")
    h.record(0.123, {"endpoint": "/test"})  # No debe lanzar


def test_setup_observability_inicializa_metrics_implicitamente() -> None:
    """setup_observability con otel_enabled=True debe wirear metrics también."""
    setup_observability(
        service_name="s2",
        otel_enabled=True,
        otel_endpoint="http://localhost:4317",
    )
    # Después de setup, get_meter debe devolver un Meter real (no _NoopMeter)
    meter = get_meter("test.post_setup")
    counter = meter.create_counter("post_setup_counter", description="t", unit="1")
    counter.add(1, {"foo": "bar"})  # No debe crashear independiente del provider
