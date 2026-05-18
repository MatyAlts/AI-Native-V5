"""Autenticación y autorización."""

from academic_service.auth.casbin_setup import (
    check_permission,
    get_enforcer,
    require_permission,
)
from academic_service.auth.dependencies import (
    User,
    get_current_user,
    get_db,
    require_role,
)

__all__ = [
    "User",
    "check_permission",
    "get_current_user",
    "get_db",
    "get_enforcer",
    "require_permission",
    "require_role",
]
