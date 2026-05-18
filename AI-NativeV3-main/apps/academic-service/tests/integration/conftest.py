"""Fixtures compartidos para tests de integración del academic-service.

Por ahora expone usuarios mock por tenant que distintos tests reusan
(`test_comision_periodo_cerrado.py`, futuros tests RBAC). El pattern es
el mismo que `test_facultades_crud.py` y `test_soft_delete.py` definen
inline; centralizarlo acá evita duplicación y errores de collection
cuando un test omite la definición.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from academic_service.auth.dependencies import User


@pytest.fixture
def tenant_a_id() -> UUID:
    return UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")


@pytest.fixture
def tenant_b_id() -> UUID:
    return UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")


@pytest.fixture
def user_docente_admin_a(tenant_a_id: UUID) -> User:
    """Docente-admin del tenant A (UNSL demo).

    Mismo shape que el fixture inline de `test_facultades_crud.py`. Se
    centraliza acá para que `test_comision_periodo_cerrado.py` y
    cualquier test futuro lo puedan consumir sin redefinirlo.
    """
    return User(
        id=uuid4(),
        tenant_id=tenant_a_id,
        email="admin-a@unsl.edu.ar",
        roles=frozenset({"docente_admin"}),
        realm=str(tenant_a_id),
    )


@pytest.fixture
def user_docente_admin_b(tenant_b_id: UUID) -> User:
    """Docente-admin del tenant B (otro tenant — para tests de RLS/aislamiento)."""
    return User(
        id=uuid4(),
        tenant_id=tenant_b_id,
        email="admin-b@otra.edu.ar",
        roles=frozenset({"docente_admin"}),
        realm=str(tenant_b_id),
    )
