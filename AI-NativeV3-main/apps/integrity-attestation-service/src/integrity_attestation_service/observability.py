"""Observabilidad del integrity-attestation-service.

Wrapper sobre `platform-observability` (paquete compartido del workspace).
"""

from fastapi import FastAPI
from platform_observability import setup_observability as _setup

from integrity_attestation_service.config import settings


def setup_observability(app: FastAPI) -> None:
    _setup(
        app=app,
        service_name=settings.service_name,
        environment=settings.environment,
        log_level=settings.log_level,
        log_format=settings.log_format,
        otel_endpoint=settings.otel_endpoint,
        sentry_dsn=settings.sentry_dsn,
    )
