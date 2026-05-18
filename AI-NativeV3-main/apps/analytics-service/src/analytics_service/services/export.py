"""Singleton del ExportJobStore y el ExportWorker del analytics-service.

F8: el `data_source_factory` ahora puede usar `RealCohortDataSource` si
las credenciales de DB están configuradas. Si no, cae al stub (para
desarrollo local sin infra).
"""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from functools import lru_cache
from uuid import UUID

from platform_ops import ExportJobStore, ExportWorker

logger = logging.getLogger(__name__)


@dataclass
class _StubDataSource:
    """DataSource que devuelve data vacía. Fallback cuando no hay DB real."""

    tenant_id: UUID

    async def list_episodes_in_comision(self, comision_id, since):
        return []

    async def list_events_for_episode(self, episode_id):
        return []

    async def get_current_classification(self, episode_id):
        return None


@lru_cache(maxsize=1)
def get_job_store() -> ExportJobStore:
    """Singleton del store."""
    return ExportJobStore()


def get_worker_salt() -> str:
    """Salt de anonimización para el worker, desde env var.

    Default dev (solo testing). Producción DEBE setear EXPORT_WORKER_SALT.
    """
    return os.environ.get(
        "EXPORT_WORKER_SALT",
        "default_dev_salt_change_in_production_please",
    )


# ── Factory que elige real vs stub ────────────────────────────────────


def _real_data_source_enabled() -> bool:
    """True si las URLs de DB real están seteadas en Settings."""
    from analytics_service.config import settings

    return bool(settings.ctr_store_url and settings.classifier_db_url)


def data_source_factory(tenant_id: UUID):
    """Factory que el worker llama por cada job.

    En F8: si hay URLs de DB reales, devuelve un adaptador que abre
    sesiones + setea RLS. Si no, devuelve el stub. Esto permite que el
    mismo binario corra en dev (sin DBs) y en prod (con DBs) sin tocar
    código, solo cambiando env vars.
    """
    if not _real_data_source_enabled():
        logger.debug("usando _StubDataSource (env vars DB no configuradas)")
        return _StubDataSource(tenant_id=tenant_id)

    # Import late para no tirar ImportError en dev
    from platform_ops import RealCohortDataSource, set_tenant_rls
    from sqlalchemy.ext.asyncio import async_sessionmaker

    class _RealDataSourceAdapter:
        """Adaptador que abre sesiones on-demand por request del worker.

        Usa pools compartidos via lru_cache del engine.
        """

        def __init__(self, tenant_id: UUID) -> None:
            self.tenant_id = tenant_id

        async def _with_sessions(self, fn):
            ctr_engine = _get_ctr_engine()
            cls_engine = _get_classifier_engine()
            ctr_maker = async_sessionmaker(ctr_engine, expire_on_commit=False)
            cls_maker = async_sessionmaker(cls_engine, expire_on_commit=False)
            async with ctr_maker() as ctr_s, cls_maker() as cls_s:
                await set_tenant_rls(ctr_s, self.tenant_id)
                await set_tenant_rls(cls_s, self.tenant_id)
                ds = RealCohortDataSource(ctr_s, cls_s, self.tenant_id)
                return await fn(ds)

        async def list_episodes_in_comision(self, comision_id, since):
            return await self._with_sessions(
                lambda ds: ds.list_episodes_in_comision(comision_id, since)
            )

        async def list_events_for_episode(self, episode_id):
            return await self._with_sessions(lambda ds: ds.list_events_for_episode(episode_id))

        async def get_current_classification(self, episode_id):
            return await self._with_sessions(lambda ds: ds.get_current_classification(episode_id))

    return _RealDataSourceAdapter(tenant_id)


@lru_cache(maxsize=1)
def _get_ctr_engine():
    from sqlalchemy.ext.asyncio import create_async_engine

    from analytics_service.config import settings

    return create_async_engine(
        settings.ctr_store_url,
        pool_size=5,
        max_overflow=10,
        pool_pre_ping=True,
    )


@lru_cache(maxsize=1)
def _get_classifier_engine():
    from sqlalchemy.ext.asyncio import create_async_engine

    from analytics_service.config import settings

    return create_async_engine(
        settings.classifier_db_url,
        pool_size=5,
        max_overflow=10,
        pool_pre_ping=True,
    )


_worker: ExportWorker | None = None
_worker_task: asyncio.Task | None = None


async def start_worker() -> None:
    """Se llama desde el lifespan del analytics-service al startup."""
    global _worker, _worker_task
    if _worker is not None:
        return  # ya iniciado

    _worker = ExportWorker(
        store=get_job_store(),
        data_source_factory=data_source_factory,
        salt=get_worker_salt(),
    )
    _worker_task = asyncio.create_task(_worker.run_forever())
    if _real_data_source_enabled():
        logger.info("export_worker_started with real DB adapter")
    else:
        logger.info("export_worker_started with stub (dev mode)")


async def stop_worker() -> None:
    """Se llama desde el lifespan al shutdown."""
    global _worker, _worker_task
    if _worker is None:
        return
    _worker.stop()
    if _worker_task is not None:
        try:
            await asyncio.wait_for(_worker_task, timeout=5.0)
        except TimeoutError:
            _worker_task.cancel()
    _worker = None
    _worker_task = None
