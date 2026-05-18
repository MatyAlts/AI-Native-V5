"""Observabilidad de academic-service.

Wrapper sobre el package compartido `platform-observability`. Mantiene
la API setup_observability(app) para no romper main.py, pero toda la
lógica (OTel + structlog + auto-instrumentación) está en el package
único para evitar duplicación entre servicios.
"""

from fastapi import FastAPI
from platform_observability import setup_observability as _setup

from academic_service.config import settings


def setup_observability(app: FastAPI) -> None:
    """Configura observabilidad para este servicio."""
    _setup(
        app=app,
        service_name=settings.service_name,
        environment=getattr(settings, "environment", "development"),
        log_level=getattr(settings, "log_level", "info"),
        log_format=getattr(settings, "log_format", "json"),
        otel_endpoint=getattr(settings, "otel_endpoint", "http://127.0.0.1:4317"),
        sentry_dsn=getattr(settings, "sentry_dsn", ""),
    )
