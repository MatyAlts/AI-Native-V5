"""HU-017 (ronda de arreglos): el SQL real de `_is_comision_member` solo cuenta
asignaciones del usuario a esa comisión, no borradas y vigentes (`fecha_hasta`
nula o no vencida). La aceptación reemplaza este seam, así que acá se prueba el
texto y los parámetros que se ejecutan, con una sesión falsa.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest
from ctr_service.auth import dependencies as deps

TENANT = UUID("11111111-1111-1111-1111-111111111111")


class _Sesion:
    def __init__(self, fila: Any) -> None:
        self.fila = fila
        self.sql: list[tuple[str, dict[str, Any]]] = []

    async def execute(self, stmt: Any, params: dict[str, Any] | None = None) -> Any:
        self.sql.append((str(stmt), params or {}))
        fila = self.fila

        class _R:
            def first(self) -> Any:
                return fila

        return _R()

    async def __aenter__(self) -> _Sesion:
        return self

    async def __aexit__(self, *_a: Any) -> None:
        return None


def _con_sesion(monkeypatch: pytest.MonkeyPatch, fila: Any) -> tuple[_Sesion, list[UUID]]:
    import ctr_service.db as ctr_db
    import platform_ops
    import sqlalchemy.ext.asyncio as sa_async

    sesion = _Sesion(fila)
    rls: list[UUID] = []

    async def _rls(_s: Any, tenant_id: UUID) -> None:
        rls.append(tenant_id)

    monkeypatch.setattr(platform_ops, "set_tenant_rls", _rls)
    monkeypatch.setattr(ctr_db, "get_academic_engine", object)
    monkeypatch.setattr(sa_async, "async_sessionmaker", lambda *_a, **_k: lambda: sesion)
    return sesion, rls


async def test_sql_filtra_usuario_comision_borrado_y_vigencia(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sesion, rls = _con_sesion(monkeypatch, (1,))
    u, c = uuid4(), uuid4()
    assert await deps._is_comision_member(TENANT, u, c) is True
    assert rls == [TENANT]
    sql, params = sesion.sql[0]
    normal = " ".join(sql.split())
    assert "FROM usuarios_comision" in normal
    assert "user_id = :u" in normal
    assert "comision_id = :c" in normal
    assert "deleted_at IS NULL" in normal
    assert "(fecha_hasta IS NULL OR fecha_hasta >= CURRENT_DATE)" in normal
    assert params == {"c": str(c), "u": str(u)}


async def test_sin_fila_no_es_miembro(monkeypatch: pytest.MonkeyPatch) -> None:
    _con_sesion(monkeypatch, None)
    assert await deps._is_comision_member(TENANT, uuid4(), uuid4()) is False
