"""Acceso a base de datos."""

from academic_service.db.session import (
    get_engine,
    get_session_factory,
    superadmin_session,
    tenant_session,
)

__all__ = [
    "get_engine",
    "get_session_factory",
    "superadmin_session",
    "tenant_session",
]
