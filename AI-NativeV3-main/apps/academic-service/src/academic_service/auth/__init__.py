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
    owner_filter,
    require_role,
)

__all__ = [
    "User",
    "check_permission",
    "get_current_user",
    "get_db",
    "get_enforcer",
    "owner_filter",
    "require_permission",
    "require_role",
]
