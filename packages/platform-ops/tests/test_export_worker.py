"""Tests del ExportWorker + ExportJobStore."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from platform_ops.export_worker import (
    ExportJob,
    ExportJobStore,
    ExportWorker,
    JobStatus,
)


@dataclass
class FakeCohortDataSource:
    """Data source que devuelve datos ligeramente configurables."""

    episodes_to_return: list[dict] = field(default_factory=list)
    fail_on_list: bool = False

    async def list_episodes_in_comision(self, comision_id, since):
        if self.fail_on_list:
            raise RuntimeError("simulated DB error")
        return self.episodes_to_return

    async def list_events_for_episode(self, episode_id):
        return []

    async def get_current_classification(self, episode_id):
        return None


def _make_job(
    status: JobStatus = JobStatus.PENDING,
    tenant_id: UUID | None = None,
) -> ExportJob:
    return ExportJob(
        job_id=uuid4(),
        status=status,
        comision_id=uuid4(),
        requested_by_user_id=uuid4(),
        requested_at=datetime.now(UTC),
        tenant_id=tenant_id or uuid4(),
        period_days=30,
        include_prompts=False,
        salt_hash="x" * 16,
        cohort_alias="TEST",
    )


# ── ExportJobStore ────────────────────────────────────────────────────


async def test_enqueue_y_get() -> None:
    store = ExportJobStore()
    job = _make_job()
    await store.enqueue(job)

    retrieved = await store.get(job.job_id)
    assert retrieved is not None
    assert retrieved.job_id == job.job_id


async def test_next_pending_respeta_orden_fifo() -> None:
    store = ExportJobStore()
    job1 = _make_job()
    job2 = _make_job()
    await store.enqueue(job1)
    await store.enqueue(job2)

    first = await store.next_pending()
    second = await store.next_pending()
    assert first.job_id == job1.job_id
    assert second.job_id == job2.job_id
    assert await store.next_pending() is None


async def test_next_pending_omite_jobs_no_pending() -> None:
    store = ExportJobStore()
    job = _make_job(status=JobStatus.PENDING)
    await store.enqueue(job)

    # Cambiar status antes de que el worker consuma
    job.status = JobStatus.RUNNING
    await store.update(job)

    # next_pending debe omitirlo
    assert await store.next_pending() is None


async def test_list_recent_filtra_por_tenant() -> None:
    store = ExportJobStore()
    tenant_a = uuid4()
    tenant_b = uuid4()
    await store.enqueue(_make_job(tenant_id=tenant_a))
    await store.enqueue(_make_job(tenant_id=tenant_a))
    await store.enqueue(_make_job(tenant_id=tenant_b))

    items_a = await store.list_recent(tenant_id=tenant_a)
    assert len(items_a) == 2
    for job in items_a:
        assert job.tenant_id == tenant_a


async def test_cleanup_old_elimina_completados_viejos() -> None:
    store = ExportJobStore()
    old_job = _make_job(status=JobStatus.SUCCEEDED)
    old_job.completed_at = datetime.now(UTC) - timedelta(days=2)
    await store.enqueue(old_job)

    recent_job = _make_job(status=JobStatus.SUCCEEDED)
    recent_job.completed_at = datetime.now(UTC)
    await store.enqueue(recent_job)

    pending_job = _make_job(status=JobStatus.PENDING)
    await store.enqueue(pending_job)

    deleted = await store.cleanup_old(ttl=timedelta(days=1))
    assert deleted == 1
    # El viejo ya no está
    assert await store.get(old_job.job_id) is None
    # Los otros siguen
    assert await store.get(recent_job.job_id) is not None
    assert await store.get(pending_job.job_id) is not None


# ── ExportWorker ─────────────────────────────────────────────────────


async def test_worker_procesa_job_pending() -> None:
    store = ExportJobStore()
    job = _make_job()
    await store.enqueue(job)

    data_source = FakeCohortDataSource()  # vacío
    worker = ExportWorker(
        store=store,
        data_source_factory=lambda _tid: data_source,
        salt="test_salt_for_research_123456",
    )
    processed = await worker.run_once()
    assert processed is True

    updated = await store.get(job.job_id)
    assert updated.status == JobStatus.SUCCEEDED
    assert updated.started_at is not None
    assert updated.completed_at is not None
    assert updated.result_payload is not None
    assert updated.result_payload["schema_version"] == "1.0.0"


async def test_worker_marca_failed_si_data_source_falla() -> None:
    store = ExportJobStore()
    job = _make_job()
    await store.enqueue(job)

    data_source = FakeCohortDataSource(fail_on_list=True)
    worker = ExportWorker(
        store=store,
        data_source_factory=lambda _tid: data_source,
        salt="test_salt_for_research_123456",
    )
    processed = await worker.run_once()
    assert processed is True

    updated = await store.get(job.job_id)
    assert updated.status == JobStatus.FAILED
    assert updated.error is not None
    assert "simulated DB error" in updated.error


async def test_worker_run_once_sin_jobs_devuelve_false() -> None:
    store = ExportJobStore()
    worker = ExportWorker(
        store=store,
        data_source_factory=lambda _tid: FakeCohortDataSource(),
        salt="test_salt_for_research_123456",
    )
    processed = await worker.run_once()
    assert processed is False


async def test_worker_run_forever_se_puede_detener() -> None:
    store = ExportJobStore()
    worker = ExportWorker(
        store=store,
        data_source_factory=lambda _tid: FakeCohortDataSource(),
        salt="test_salt_for_research_123456",
        poll_interval_seconds=0.01,  # rápido para el test
    )

    task = asyncio.create_task(worker.run_forever())
    await asyncio.sleep(0.05)  # darle un poco de tiempo
    worker.stop()
    await asyncio.wait_for(task, timeout=1.0)
    # No debe haber crasheado


async def test_job_serializable_a_dict() -> None:
    import json

    job = _make_job()
    job.started_at = datetime.now(UTC)
    d = job.to_dict()
    # Debe ser serializable
    serialized = json.dumps(d)
    parsed = json.loads(serialized)
    assert parsed["status"] == "pending"
    assert "job_id" in parsed
    # No expone result_payload (se descarga separado)
    assert "result_payload" not in d
