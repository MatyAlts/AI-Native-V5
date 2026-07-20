"""Worker async de exportación académica.

El endpoint `POST /analytics/cohort/export` acepta un job; este worker
lo ejecuta en background. El resultado se guarda en un blob store con
firma; el investigador descarga con un link TTL-limitado.

Arquitectura simple sin external queue broker (suficiente para el
volumen del piloto: 1-2 exports/día por docente):

  1. El endpoint crea un `ExportJob` con estado `pending` en Redis.
  2. Un task asyncio consume jobs `pending` y los ejecuta.
  3. El worker actualiza el estado: `running` → `succeeded` | `failed`.
  4. Endpoint GET /status/{job_id} devuelve el estado actual.
  5. Endpoint GET /download/{job_id} devuelve el dataset si succeeded.

Para volúmenes mayores se puede migrar a Celery/RQ; la interfaz
pública del job store se mantiene.
"""

from __future__ import annotations

import asyncio
import logging
import traceback
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any
from uuid import UUID

from platform_ops.academic_export import AcademicExporter

logger = logging.getLogger(__name__)


class JobStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


@dataclass
class ExportJob:
    """Estado de un job de export."""

    job_id: UUID
    status: JobStatus
    comision_id: UUID
    requested_by_user_id: UUID
    requested_at: datetime
    tenant_id: UUID
    period_days: int
    include_prompts: bool
    salt_hash: str  # hash del salt, no el salt en claro
    cohort_alias: str

    started_at: datetime | None = None
    completed_at: datetime | None = None
    error: str | None = None
    # Payload serializado del dataset cuando status == succeeded
    # (en prod podría ser una URL a S3 en su lugar)
    result_payload: dict[str, Any] | None = None

    def to_dict(self) -> dict:
        return {
            "job_id": str(self.job_id),
            "status": self.status.value,
            "comision_id": str(self.comision_id),
            "requested_by_user_id": str(self.requested_by_user_id),
            "tenant_id": str(self.tenant_id),
            "requested_at": self.requested_at.isoformat().replace("+00:00", "Z"),
            "period_days": self.period_days,
            "include_prompts": self.include_prompts,
            "salt_hash": self.salt_hash,
            "cohort_alias": self.cohort_alias,
            "started_at": self.started_at.isoformat().replace("+00:00", "Z")
            if self.started_at
            else None,
            "completed_at": self.completed_at.isoformat().replace("+00:00", "Z")
            if self.completed_at
            else None,
            "error": self.error,
            # No incluimos result_payload en el resumen; se descarga separado
        }


class ExportJobStore:
    """In-memory job store para F7. Intercambiable por Redis en prod.

    Uso thread-safe via asyncio.Lock para coordinar entre worker y
    endpoints.
    """

    def __init__(self) -> None:
        self._jobs: dict[UUID, ExportJob] = {}
        self._pending: list[UUID] = []
        self._lock = asyncio.Lock()

    async def enqueue(self, job: ExportJob) -> None:
        async with self._lock:
            self._jobs[job.job_id] = job
            self._pending.append(job.job_id)

    async def get(self, job_id: UUID) -> ExportJob | None:
        async with self._lock:
            return self._jobs.get(job_id)

    async def next_pending(self) -> ExportJob | None:
        async with self._lock:
            while self._pending:
                job_id = self._pending.pop(0)
                job = self._jobs.get(job_id)
                if job and job.status == JobStatus.PENDING:
                    return job
            return None

    async def update(self, job: ExportJob) -> None:
        async with self._lock:
            self._jobs[job.job_id] = job

    async def list_recent(self, tenant_id: UUID | None = None, limit: int = 20) -> list[ExportJob]:
        async with self._lock:
            items = list(self._jobs.values())
        if tenant_id:
            items = [j for j in items if j.tenant_id == tenant_id]
        items.sort(key=lambda j: j.requested_at, reverse=True)
        return items[:limit]

    async def cleanup_old(self, ttl: timedelta = timedelta(days=1)) -> int:
        """Elimina jobs completados más viejos que ttl. Devuelve cuántos borró."""
        now = datetime.now(UTC)
        async with self._lock:
            to_delete = [
                jid
                for jid, j in self._jobs.items()
                if j.status in (JobStatus.SUCCEEDED, JobStatus.FAILED)
                and j.completed_at
                and (now - j.completed_at) > ttl
            ]
            for jid in to_delete:
                del self._jobs[jid]
            return len(to_delete)


# ── Worker ─────────────────────────────────────────────────────────────


class ExportWorker:
    """Worker que consume jobs pending y los ejecuta.

    El worker necesita un `data_source_factory` porque el dataset real
    se construye desde la DB del classifier-service + ctr-service. La
    factory recibe el tenant_id y devuelve el data_source apropiado
    (que internamente abre sesiones con RLS correcto).
    """

    def __init__(
        self,
        store: ExportJobStore,
        data_source_factory: Callable[[UUID], Any],
        salt: str,
        poll_interval_seconds: float = 1.0,
    ) -> None:
        self.store = store
        self.data_source_factory = data_source_factory
        self.salt = salt
        self.poll_interval = poll_interval_seconds
        self._running = False

    async def run_once(self) -> bool:
        """Procesa un job si hay pending. Devuelve True si procesó algo."""
        job = await self.store.next_pending()
        if job is None:
            return False

        job.status = JobStatus.RUNNING
        job.started_at = datetime.now(UTC)
        await self.store.update(job)

        try:
            logger.info("export_starting job_id=%s comision=%s", job.job_id, job.comision_id)
            data_source = self.data_source_factory(job.tenant_id)
            exporter = AcademicExporter(
                data_source=data_source,
                salt=self.salt,
                cohort_alias=job.cohort_alias,
            )
            dataset = await exporter.export_cohort(
                comision_id=job.comision_id,
                period_days=job.period_days,
                include_prompts=job.include_prompts,
            )

            job.result_payload = dataset.to_dict()
            job.status = JobStatus.SUCCEEDED
            job.completed_at = datetime.now(UTC)
            await self.store.update(job)
            logger.info("export_succeeded job_id=%s", job.job_id)

        except Exception as e:
            tb = traceback.format_exc()
            logger.error("export_failed job_id=%s: %s\n%s", job.job_id, e, tb)
            job.status = JobStatus.FAILED
            job.completed_at = datetime.now(UTC)
            job.error = f"{type(e).__name__}: {e}"
            await self.store.update(job)

        return True

    async def run_forever(self) -> None:
        """Loop del worker — correr como background task en el analytics-service."""
        self._running = True
        logger.info("export_worker_started")
        try:
            while self._running:
                processed = await self.run_once()
                if not processed:
                    await asyncio.sleep(self.poll_interval)
        finally:
            logger.info("export_worker_stopped")

    def stop(self) -> None:
        self._running = False


__all__ = [
    "ExportJob",
    "ExportJobStore",
    "ExportWorker",
    "JobStatus",
]
