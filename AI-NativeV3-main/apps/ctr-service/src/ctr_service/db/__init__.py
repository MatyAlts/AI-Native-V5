"""Acceso a DB del ctr-service."""

from ctr_service.db.session import (
    get_academic_engine,
    get_engine,
    get_session_factory,
    tenant_session,
)

__all__ = [
    "get_academic_engine",
    "get_engine",
    "get_session_factory",
    "tenant_session",
]
