"""Engines de DB compartidos a nivel proceso.

Antes cada endpoint de analytics creaba (y `dispose()`-aba) sus propios engines
por request. Eso rotaba el pool de conexiones de Postgres en cada llamada y,
bajo carga, agotaba `max_connections` (informe Fase 5: 96-98/100 conexiones,
49% de requests con 500). Estos getters memoizados crean **un engine por URL
para todo el proceso**, reusando el pool entre requests.

El aislamiento multi-tenant (RLS) sigue intacto: `set_tenant_rls` hace
`SET LOCAL app.current_tenant` por sesión/transacción, no por engine — un engine
compartido reparte conexiones del pool y cada sesión setea su tenant.

Mismo patrón que `services/export.py` (`@lru_cache` + pool_size=5/max_overflow=10).
"""

from __future__ import annotations

from functools import lru_cache

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from analytics_service.config import settings


def _make(url: str) -> AsyncEngine:
    return create_async_engine(
        url,
        # Pool chico: analytics tiene 3 engines (ctr+classifier+academic) y comparte
        # el Postgres (max_connections=100) con ~10 servicios. 2 idle + overflow.
        pool_size=2,
        max_overflow=3,
        pool_pre_ping=True,
    )


@lru_cache(maxsize=1)
def get_ctr_engine() -> AsyncEngine:
    return _make(settings.ctr_store_url)


@lru_cache(maxsize=1)
def get_classifier_engine() -> AsyncEngine:
    return _make(settings.classifier_db_url)


@lru_cache(maxsize=1)
def get_academic_engine() -> AsyncEngine:
    return _make(settings.academic_db_url)


async def dispose_all() -> None:
    """Cierra los engines cacheados. Llamar en el shutdown del servicio."""
    for getter in (get_ctr_engine, get_classifier_engine, get_academic_engine):
        if getter.cache_info().currsize:
            await getter().dispose()
        getter.cache_clear()
