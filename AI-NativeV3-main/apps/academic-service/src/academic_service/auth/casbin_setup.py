"""Modelo Casbin RBAC-con-dominios (ADR-008).

Ver: https://casbin.org/docs/rbac-with-domains
"""

from __future__ import annotations

import functools
from dataclasses import dataclass
from pathlib import Path

import casbin
from casbin_sqlalchemy_adapter import Adapter
from fastapi import Depends, HTTPException, status

from academic_service.auth.dependencies import User, get_current_user
from academic_service.config import settings

# Modelo Casbin RBAC con dominios (tenant = universidad).
# - sub: user_id
# - dom: tenant_id
# - obj: recurso (ej. "comision:*", "rubrica:uuid")
# - act: acción (read, create, update, delete)
CASBIN_MODEL = """
[request_definition]
r = sub, dom, obj, act

[policy_definition]
p = sub, dom, obj, act

[role_definition]
g = _, _, _

[policy_effect]
e = some(where (p.eft == allow))

[matchers]
m = g(r.sub, p.sub, r.dom) && keyMatch(r.obj, p.obj) && r.act == p.act || r.sub == p.sub && keyMatch(r.dom, p.dom) && keyMatch(r.obj, p.obj) && r.act == p.act
"""


@dataclass
class Permission:
    resource: str
    action: str


@functools.lru_cache(maxsize=1)
def get_enforcer() -> casbin.Enforcer:
    """Enforcer singleton con adapter SQLAlchemy (sync).

    Casbin no tiene async adapter maduro aún; la llamada de enforcement
    es lo suficientemente rápida (in-memory tras el load inicial) como
    para usarlo sync dentro de endpoints async.
    """
    model_path = Path(__file__).parent / "casbin_model.conf"
    if not model_path.exists():
        model_path.write_text(CASBIN_MODEL)

    # Adapter sync, OK para lectura
    db_url = settings.academic_db_url.replace("+asyncpg", "")
    from academic_service.models.transversal import CasbinRule

    adapter = Adapter(db_url, db_class=CasbinRule, create_all_models=False)
    enforcer = casbin.Enforcer(str(model_path), adapter)
    enforcer.load_policy()
    return enforcer


def check_permission(user: User, resource: str, action: str) -> bool:
    """Chequea si el user tiene permiso para (resource, action) en su tenant."""
    if "superadmin" in user.roles:
        return True

    enforcer = get_enforcer()
    obj = resource if ":" in resource else f"{resource}:*"
    for role in user.roles:
        if enforcer.enforce(f"role:{role}", str(user.tenant_id), obj, action):
            return True
    return False


def require_permission(resource: str, action: str):
    """Decorator-style dependency para FastAPI."""

    async def checker(user: User = Depends(get_current_user)) -> User:
        if not check_permission(user, resource, action):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Permiso denegado: se requiere {action} sobre {resource} "
                    f"(roles actuales: {', '.join(user.roles) or 'ninguno'})"
                ),
            )
        return user

    return checker
