"""Autenticación y autorización del content-service."""

from content_service.auth.dependencies import (
    CONTENT_OVERSIGHT_ROLES,
    MATERIAL_UPLOAD_ROLES,
    RETRIEVAL_ROLES,
    User,
    assert_materia_upload_access,
    assert_material_owner,
    get_current_user,
    get_db,
    require_role,
)

__all__ = [
    "CONTENT_OVERSIGHT_ROLES",
    "MATERIAL_UPLOAD_ROLES",
    "RETRIEVAL_ROLES",
    "User",
    "assert_materia_upload_access",
    "assert_material_owner",
    "get_current_user",
    "get_db",
    "require_role",
]
