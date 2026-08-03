"""Observabilidad del execution-service.

Wrapper sobre el package compartido `platform-observability`, igual que el
resto de los servicios: toda la logica (OTel + structlog + auto-instrumentacion)
vive en el package unico para no duplicarla por servicio.
"""

from fastapi import FastAPI
from platform_observability import setup_observability as _setup

from execution_service.config import settings


def setup_observability(app: FastAPI) -> None:
    """Configura observabilidad para este servicio."""
    _setup(
        app=app,
        service_name=settings.service_name,
        environment=settings.environment,
        log_level=settings.log_level,
        log_format=settings.log_format,
        otel_endpoint=settings.otel_endpoint,
        sentry_dsn=settings.sentry_dsn,
    )
