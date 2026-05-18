"""Autenticación y autorización del content-service."""

from content_service.auth.dependencies import (
    MATERIAL_UPLOAD_ROLES,
    RETRIEVAL_ROLES,
    User,
    get_current_user,
    get_db,
    require_role,
)

__all__ = [
    "MATERIAL_UPLOAD_ROLES",
    "RETRIEVAL_ROLES",
    "User",
    "get_current_user",
    "get_db",
    "require_role",
]
