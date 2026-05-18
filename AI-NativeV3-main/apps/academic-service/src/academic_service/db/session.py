"""Setup de SQLAlchemy async con manejo de contexto de tenant para RLS.

CRÍTICO: toda query debe ejecutarse dentro de una sesión con el
tenant_id seteado en current_setting('app.current_tenant'). El helper
`get_session` de FastAPI hace esto automáticamente si se usa con el
dependency `TenantContext` que extrae el tenant del JWT.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from decimal import Decimal
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from academic_service.config import settings

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def _json_default(obj: object) -> object:
    """Custom JSON encoder para columnas JSONB.

    Los criterios de rúbrica usan `Decimal` para `peso` (precision exacta vs
    float). El default `json.dumps` no serializa Decimal — convertimos a float
    cuando viaja a Postgres JSONB. Idem UUID por consistencia (algunos JSONB
    pueden contener IDs anidados).
    """
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, UUID):
        return str(obj)
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def _json_serializer(value: object) -> str:
    return json.dumps(value, default=_json_default)


def get_engine() -> AsyncEngine:
    """Engine async singleton."""
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            settings.academic_db_url,
            pool_size=10,
            max_overflow=5,
            pool_pre_ping=True,
            echo=settings.db_echo,
            json_serializer=_json_serializer,
        )
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            get_engine(),
            expire_on_commit=False,
        )
    return _session_factory


@asynccontextmanager
async def tenant_session(tenant_id: UUID) -> AsyncIterator[AsyncSession]:
    """Abre una sesión con el tenant_id seteado en current_setting.

    Toda query dentro de este bloque ve solo filas del tenant activo.
    Las writes también rebotan contra la policy RLS.
    """
    factory = get_session_factory()
    async with factory() as session:
        # SET LOCAL es scoped a la transacción
        await session.execute(
            text("SELECT set_config('app.current_tenant', :t, true)"),
            {"t": str(tenant_id)},
        )
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


@asynccontextmanager
async def superadmin_session() -> AsyncIterator[AsyncSession]:
    """Sesión sin RLS — solo para superadmin.

    Setea el tenant al valor especial '00000000-...' que NINGUNA fila
    tiene, efectivamente devolviendo vacío. Para real bypass se usa
    conexión con rol privilegiado separado.
    """
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
