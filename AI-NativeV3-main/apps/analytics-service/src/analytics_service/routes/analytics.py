"""Endpoints analíticos del piloto UTN.

POST /api/v1/analytics/kappa            calcula Cohen's Kappa de un batch de ratings
GET  /api/v1/analytics/cohort/export    descarga dataset académico anonimizado
"""

from __future__ import annotations

import logging
import time
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, status
from platform_ops import (
    ALERTS_VERSION,
    MIN_STUDENTS_FOR_QUARTILES,
    KappaRating,
    compute_alerts_payload,
    compute_cohen_kappa,
    compute_cohort_quartiles_payload,
)
from pydantic import BaseModel, Field

from analytics_service.db import get_academic_engine, get_classifier_engine, get_ctr_engine
from analytics_service.metrics import (
    classifier_kappa_rolling,
    classifier_kappa_rolling_last_update_unix_seconds,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/analytics", tags=["analytics"])


async def get_tenant_id(x_tenant_id: str | None = Header(default=None)) -> UUID:
    if not x_tenant_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="X-Tenant-Id header required",
        )
    try:
        return UUID(x_tenant_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-Tenant-Id must be a valid UUID",
        )


async def get_user_id(x_user_id: str | None = Header(default=None)) -> UUID:
    if not x_user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="X-User-Id header required",
        )
    try:
        return UUID(x_user_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-User-Id must be a valid UUID",
        )


async def assert_comision_member(
    user_id: UUID, comision_id: UUID, tenant_id: UUID
) -> None:
    """Lanza 403 si `user_id` no es docente asignado a `comision_id`.

    El análisis se aísla por comisión: en prod todos los docentes comparten
    un tenant fijo, así que la RLS por tenant NO los separa — el aislamiento
    lo da la asignación `usuarios_comision` (academic_main). Sin academic_db
    configurado (dev/stub) el guard es no-op. Ver docs/filtrado-teacher-plan.md.
    """
    from platform_ops import set_tenant_rls
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from analytics_service.config import settings

    if not settings.enforce_comision_access or not settings.academic_db_url:
        return
    engine = get_academic_engine()
    async with async_sessionmaker(engine, expire_on_commit=False)() as s:
        await set_tenant_rls(s, tenant_id)
        row = (
            await s.execute(
                text(
                    "SELECT 1 FROM usuarios_comision "
                    "WHERE comision_id = :c AND user_id = :u "
                    "AND deleted_at IS NULL LIMIT 1"
                ),
                {"c": str(comision_id), "u": str(user_id)},
            )
        ).first()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tenes acceso al analisis de esta comision.",
        )


async def require_comision_access(
    comision_id: UUID,
    x_user_id: str | None = Header(default=None),
    tenant_id: UUID = Depends(get_tenant_id),
) -> None:
    """Dependency: exige que el caller sea docente de `comision_id`.

    FastAPI resuelve `comision_id` del path (cohort/*) o del query
    (student/* lo pasan como query param) del endpoint. Aísla todo el
    análisis por comisión. Para endpoints con `comision_id` en el body
    (export) se llama a `assert_comision_member` a mano.

    Enforcement gateado por `settings.enforce_comision_access` (True en
    prod por default; los tests unit lo ponen en False vía conftest para
    no tener que simular gateway ni sembrar membresía en la DB).
    """
    from analytics_service.config import settings

    if not settings.enforce_comision_access:
        return
    if not x_user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="X-User-Id header required",
        )
    try:
        user_id = UUID(x_user_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-User-Id must be a valid UUID",
        )
    await assert_comision_member(user_id, comision_id, tenant_id)


# ── Kappa endpoint ────────────────────────────────────────────────────


class KappaRatingIn(BaseModel):
    episode_id: str
    rater_a: Literal["delegacion_pasiva", "apropiacion_superficial", "apropiacion_reflexiva"]
    rater_b: Literal["delegacion_pasiva", "apropiacion_superficial", "apropiacion_reflexiva"]


class KappaRequest(BaseModel):
    ratings: list[KappaRatingIn] = Field(..., min_length=1, max_length=10000)
    # Optional cohort tag — si está presente, se actualiza el gauge
    # `classifier_kappa_rolling{cohort=...}` para visualización en Grafana
    # dashboard 5. Sin él, el κ se computa pero no se grafica longitudinalmente.
    cohort_id: UUID | None = None


class KappaResponse(BaseModel):
    kappa: float
    n_episodes: int
    observed_agreement: float
    expected_agreement: float
    interpretation: str
    per_class_agreement: dict[str, float]
    confusion_matrix: dict[str, dict[str, int]]


@router.post("/kappa", response_model=KappaResponse)
async def compute_kappa(
    req: KappaRequest,
    tenant_id: UUID = Depends(get_tenant_id),
    user_id: UUID = Depends(get_user_id),
) -> KappaResponse:
    """Calcula Cohen's Kappa sobre un batch de ratings.

    Los ratings vienen del frontend (docente revisa N episodios
    clasificados y marca si concuerda o no). El response incluye
    la interpretación de Landis & Koch + matriz de confusión para
    identificar clases problemáticas.

    Este endpoint es clave para el capítulo de validación empírica
    de la tesis.
    """
    ratings = [
        KappaRating(
            episode_id=r.episode_id,
            rater_a=r.rater_a,
            rater_b=r.rater_b,
        )
        for r in req.ratings
    ]
    try:
        result = compute_cohen_kappa(ratings)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    response = KappaResponse(
        kappa=result.kappa,
        n_episodes=result.n_episodes,
        observed_agreement=result.observed_agreement,
        expected_agreement=result.expected_agreement,
        interpretation=result.interpretation,
        per_class_agreement=result.per_class_agreement,
        confusion_matrix=result.confusion_matrix,
    )

    logger.info(
        "kappa_computed tenant_id=%s user_id=%s n_episodes=%d kappa=%s interpretation=%s",
        tenant_id,
        user_id,
        response.n_episodes,
        response.kappa,
        response.interpretation,
    )

    # Métrica: si el request trae cohort_id, actualizar los gauges para el
    # dashboard 5 (κ rolling). UpDownCounter — para "set value" emitimos
    # delta vs valor previo, simulado con add(value) que en práctica refleja
    # acumulado. En el período del piloto basta para visualización.
    if req.cohort_id is not None:
        cohort_label = {"window": "7d", "cohort": str(req.cohort_id)}
        classifier_kappa_rolling.add(response.kappa, cohort_label)
        classifier_kappa_rolling_last_update_unix_seconds.add(
            time.time(), {"cohort": str(req.cohort_id)}
        )

    return response


# ── Cohort export endpoint ─────────────────────────────────────────────
# El export real requiere acceso a varias DBs (episodes, events, classifications).
# Este endpoint es un stub que documenta la API; la integración con el
# data_source real se hace en F7.


class CohortExportRequest(BaseModel):
    comision_id: UUID
    period_days: int = Field(default=90, ge=1, le=365)
    include_prompts: bool = False
    salt: str = Field(
        ...,
        min_length=16,
        description="Salt de anonimización (16+ chars). Investigadores con el mismo salt pueden cross-referenciar.",
    )
    cohort_alias: str = "COHORT"


class ExportJobResponse(BaseModel):
    job_id: str
    status: str
    message: str


@router.post(
    "/cohort/export", response_model=ExportJobResponse, status_code=status.HTTP_202_ACCEPTED
)
async def export_cohort(
    req: CohortExportRequest,
    tenant_id: UUID = Depends(get_tenant_id),
    user_id: UUID = Depends(get_user_id),
) -> ExportJobResponse:
    """Encola un job de export académico anonymizado.

    F7: la implementación real encola contra el `ExportJobStore`
    global del analytics-service, y el worker lo consume en background.
    El investigador hace polling a `/cohort/export/{job_id}/status` y
    descarga con `/cohort/export/{job_id}/download` cuando está listo.

    Aislamiento por comisión: solo un docente asignado a `req.comision_id`
    puede exportar su dataset (el `comision_id` viene en el body, así que
    el guard se llama a mano). `assert_comision_member` se auto-gatea por
    `settings.enforce_comision_access` (no-op en tests).
    """
    await assert_comision_member(user_id, req.comision_id, tenant_id)

    import hashlib
    from datetime import UTC, datetime
    from uuid import uuid4

    from platform_ops import ExportJob, JobStatus

    from analytics_service.services.export import get_job_store

    # Hash del salt para trazabilidad sin exponer el salt en claro
    salt_hash = hashlib.sha256(req.salt.encode()).hexdigest()[:16]

    job = ExportJob(
        job_id=uuid4(),
        status=JobStatus.PENDING,
        comision_id=req.comision_id,
        requested_by_user_id=user_id,
        requested_at=datetime.now(UTC),
        tenant_id=tenant_id,
        period_days=req.period_days,
        include_prompts=req.include_prompts,
        salt_hash=salt_hash,
        cohort_alias=req.cohort_alias,
    )

    store = get_job_store()
    await store.enqueue(job)

    return ExportJobResponse(
        job_id=str(job.job_id),
        status=job.status.value,
        message=(
            f"Export encolado. Polling: GET /cohort/export/{job.job_id}/status | "
            f"Descarga: GET /cohort/export/{job.job_id}/download"
        ),
    )


@router.get("/cohort/export/{job_id}/status")
async def get_export_status(job_id: UUID) -> dict:
    """Estado actual del export job."""
    from analytics_service.services.export import get_job_store

    store = get_job_store()
    job = await store.get(job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Job {job_id} no encontrado"
        )
    return job.to_dict()


@router.get("/cohort/export/{job_id}/download")
async def download_export(job_id: UUID) -> dict:
    """Descarga el dataset exportado si el job está succeeded.

    En producción (F8+), esto devolvería un redirect a una URL firmada
    de S3/MinIO. En F7 devolvemos el payload inline (ok para datasets
    de ~MB; para 100+ MB conviene migrar a storage externo).
    """
    from platform_ops import JobStatus

    from analytics_service.services.export import get_job_store

    store = get_job_store()
    job = await store.get(job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Job {job_id} no encontrado"
        )

    if job.status in (JobStatus.PENDING, JobStatus.RUNNING):
        raise HTTPException(
            status_code=status.HTTP_425_TOO_EARLY,
            detail=f"Job aún no terminado (estado: {job.status.value}). "
            f"Hacé polling al endpoint /status.",
        )
    if job.status == JobStatus.FAILED:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Job falló: {job.error}",
        )
    if job.result_payload is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Job succeeded pero sin payload (bug).",
        )

    return job.result_payload


# ── Progresión longitudinal (F7) ───────────────────────────────────────


class TrajectoryPoint(BaseModel):
    episode_id: str
    classified_at: str
    appropriation: str


class StudentTrajectoryOut(BaseModel):
    student_pseudonym: str
    n_episodes: int
    first_classification: str | None
    last_classification: str | None
    max_appropriation_reached: str | None
    progression_label: str  # "mejorando" | "estable" | "empeorando" | "insuficiente"
    tercile_means: tuple[float, float, float] | None
    points: list[TrajectoryPoint]


class CohortProgressionOut(BaseModel):
    comision_id: UUID
    n_students: int
    n_students_with_enough_data: int
    mejorando: int
    estable: int
    empeorando: int
    insuficiente: int
    net_progression_ratio: float
    trajectories: list[StudentTrajectoryOut]


# ── Cache TTL en proceso para progression ─────────────────────────────
# `build_trajectories` + `summarize_cohort` es CPU-bound y serializa todas las
# requests (informe Fase 5: throughput clavado en ~8 req/s). Memoizamos el
# resultado por (tenant, comision) con TTL corto. In-process a propósito:
# analytics-service es instancia única en el piloto y NO usa Redis — meterlo
# acá solo para esto sería sumar dependencia + modo de falla. Si se escala a
# múltiples réplicas, migrar a un cache compartido (Redis).
_PROGRESSION_CACHE_TTL_SEC = 60.0
_progression_cache: dict[tuple[str, str], tuple[float, CohortProgressionOut]] = {}


def _progression_cache_get(key: tuple[str, str]) -> CohortProgressionOut | None:
    entry = _progression_cache.get(key)
    if entry is None:
        return None
    cached_at, value = entry
    if time.monotonic() - cached_at > _PROGRESSION_CACHE_TTL_SEC:
        _progression_cache.pop(key, None)
        return None
    return value


def _progression_cache_set(key: tuple[str, str], value: CohortProgressionOut) -> None:
    _progression_cache[key] = (time.monotonic(), value)


@router.get(
    "/cohort/{comision_id}/progression",
    response_model=CohortProgressionOut,
)
async def get_cohort_progression(
    comision_id: UUID,
    tenant_id: UUID = Depends(get_tenant_id),
    _comision_access: None = Depends(require_comision_access),
) -> CohortProgressionOut:
    """Analiza la progresión longitudinal de los estudiantes de una cohorte.

    Resultado:
      - Cada estudiante con su trayectoria de clasificaciones + etiqueta
        de progresión ("mejorando" si último tercio > primero)
      - Resumen agregado con `net_progression_ratio` (indicador de cohorte)

    F8: si las env vars `CTR_STORE_URL` + `CLASSIFIER_DB_URL` están
    configuradas, usa el adaptador real con RLS por tenant. Si no, cae a
    un stub vacío (modo dev).
    """
    # Cache TTL por (tenant, comision). El guard de acceso ya corrió arriba
    # (Depends), así que un hit no saltea autorización.
    cache_key = (str(tenant_id), str(comision_id))
    cached = _progression_cache_get(cache_key)
    if cached is not None:
        return cached

    from platform_ops import build_trajectories, summarize_cohort

    from analytics_service.services.export import (
        _real_data_source_enabled,
    )

    if _real_data_source_enabled():
        from platform_ops import RealLongitudinalDataSource, set_tenant_rls
        from sqlalchemy.ext.asyncio import async_sessionmaker

        ctr_engine = get_ctr_engine()
        cls_engine = get_classifier_engine()
        ctr_maker = async_sessionmaker(ctr_engine, expire_on_commit=False)
        cls_maker = async_sessionmaker(cls_engine, expire_on_commit=False)
        async with ctr_maker() as ctr_s, cls_maker() as cls_s:
            await set_tenant_rls(ctr_s, tenant_id)
            await set_tenant_rls(cls_s, tenant_id)
            ds = RealLongitudinalDataSource(ctr_s, cls_s, tenant_id)
            # build_trajectories acepta cualquier objeto con
            # `list_classifications_grouped_by_student` (duck-typed); el
            # protocol _DataSource es interno al paquete platform-ops.
            trajectories = await build_trajectories(ds, comision_id)  # type: ignore[arg-type]
    else:
        # Stub para dev
        class _LongitudinalAdapter:
            async def list_classifications_grouped_by_student(self, comision_id):
                return {}

        trajectories = await build_trajectories(_LongitudinalAdapter(), comision_id)  # type: ignore[arg-type]

    summary = summarize_cohort(comision_id, trajectories)

    result = CohortProgressionOut(
        comision_id=comision_id,
        n_students=summary.n_students,
        n_students_with_enough_data=summary.n_students_with_enough_data,
        mejorando=summary.mejorando,
        estable=summary.estable,
        empeorando=summary.empeorando,
        insuficiente=summary.insuficiente,
        net_progression_ratio=summary.net_progression_ratio,
        trajectories=[
            StudentTrajectoryOut(
                student_pseudonym=t.student_pseudonym,
                n_episodes=t.n_episodes,
                first_classification=t.first_classification,
                last_classification=t.last_classification,
                max_appropriation_reached=t.max_appropriation_reached(),
                progression_label=t.progression_label(),
                tercile_means=t.tercile_means(),
                points=[
                    TrajectoryPoint(
                        episode_id=str(p.episode_id),
                        classified_at=p.classified_at.isoformat().replace("+00:00", "Z"),
                        appropriation=p.appropriation,
                    )
                    for p in t.points
                ],
            )
            for t in trajectories
        ],
    )
    _progression_cache_set(cache_key, result)
    return result


# ── Etiquetador N1-N4 por evento (ADR-020) ────────────────────────────


class NLevelDistributionOut(BaseModel):
    """Distribución de tiempo y eventos por nivel analítico N1-N4.

    Componente C3.2 de la tesis (Sección 6.4). El etiquetador deriva el nivel
    en lectura — NO está almacenado en el payload del evento (preserva
    reproducibilidad bit-a-bit del self_hash).
    """

    episode_id: str
    labeler_version: str
    distribution_seconds: dict[str, float]
    distribution_ratio: dict[str, float]
    total_events_per_level: dict[str, int]


@router.get(
    "/episode/{episode_id}/n-level-distribution",
    response_model=NLevelDistributionOut,
)
async def get_n_level_distribution(
    episode_id: UUID,
    tenant_id: UUID = Depends(get_tenant_id),
    user_id: UUID = Depends(get_user_id),
) -> NLevelDistributionOut:
    """Distribución de tiempo por nivel N1-N4 para un episodio (ADR-020).

    El etiquetador (`event_labeler.py`) aplica reglas de primer orden sobre
    `event_type` + `payload.origin` (para `edicion_codigo`). Las reglas son
    versionables vía `LABELER_VERSION` — bumpear re-etiqueta históricos sin
    tocar el CTR.

    Modo dev (sin CTR_STORE_URL): devuelve distribución vacía con
    `labeler_version`. Coherente con `/cohort/{id}/progression`.

    Modo real: lee eventos del CTR con RLS por tenant; 404 si el episodio
    no existe o no tiene eventos en este tenant.
    """
    # Import del labeler vía sys.path (mismo patrón que /ab-test-profiles)
    import sys
    from pathlib import Path

    classifier_src = Path(__file__).parent.parent.parent.parent.parent / "classifier-service/src"
    if str(classifier_src) not in sys.path:
        sys.path.insert(0, str(classifier_src))

    try:
        from classifier_service.services.event_labeler import n_level_distribution
    except ImportError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"event_labeler no disponible: {e}",
        )

    from analytics_service.services.export import _real_data_source_enabled

    if not _real_data_source_enabled():
        # Modo dev: distribución vacía. El labeler_version igual viaja.
        empty = n_level_distribution([])
        return NLevelDistributionOut(episode_id=str(episode_id), **empty)

    # Modo real: lectura del CTR con RLS por tenant.
    # Late import del modelo Event (evita ciclos en testing).
    from ctr_service.models import Event
    from platform_ops import set_tenant_rls
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker

    ctr_engine = get_ctr_engine()
    ctr_maker = async_sessionmaker(ctr_engine, expire_on_commit=False)
    async with ctr_maker() as ctr_s:
        await set_tenant_rls(ctr_s, tenant_id)
        stmt = (
            select(Event)
            .where(Event.episode_id == episode_id)
            .where(Event.tenant_id == tenant_id)  # doble filtro (defensivo)
            .order_by(Event.seq.asc())
        )
        result = await ctr_s.execute(stmt)
        events = [
            {
                "seq": ev.seq,
                "event_type": ev.event_type,
                "ts": ev.ts.isoformat().replace("+00:00", "Z") if ev.ts else None,
                "payload": ev.payload or {},
            }
            for ev in result.scalars().all()
        ]

    if not events:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Episode {episode_id} no encontrado o sin eventos en este tenant",
        )

    distribution = n_level_distribution(events)
    logger.info(
        "n_level_distribution_computed tenant_id=%s user_id=%s episode_id=%s "
        "n_events=%d labeler_version=%s",
        tenant_id,
        user_id,
        episode_id,
        sum(distribution["total_events_per_level"].values()),
        distribution["labeler_version"],
    )
    return NLevelDistributionOut(episode_id=str(episode_id), **distribution)


# ── CII evolution longitudinal por estudiante (ADR-018) ──────────────


class CIIEvolutionTemplateOut(BaseModel):
    """Slope longitudinal de un estudiante sobre un template específico."""

    template_id: UUID
    n_episodes: int
    scores_ordinal: list[int]
    slope: float | None
    insufficient_data: bool


class CIIEvolutionUnidadOut(BaseModel):
    """Slope longitudinal de un estudiante agrupado por Unidad tematica (AD-4, AD-6).

    Paralelo a CIIEvolutionTemplateOut pero usando unidad_id como eje de
    agrupacion. Habilita trazabilidad cuando template_id=NULL (pilotos sin
    TareaPracticaTemplate configurados).
    """

    unidad_id: str  # UUID str o "sin_unidad" para TPs huerfanas
    unidad_nombre: str
    n_episodes: int
    scores_ordinal: list[int]
    slope: float | None
    insufficient_data: bool


class CIIEvolutionLongitudinalOut(BaseModel):
    """Distribución de evolution longitudinal de un estudiante (ADR-018).

    Componente operacional de la Sección 15.4 de la tesis. Cada entry de
    `evolution_per_template` es un slope ordinal sobre `APPROPRIATION_ORDINAL`
    (0=delegacion, 1=superficial, 2=reflexiva). Slope > 0 = mejora
    longitudinal en ese problema lógico.

    `evolution_per_unidad` es el agrupamiento tematico paralelo (AD-4, AD-6).
    Default [] para BC — callers que solo leen `evolution_per_template` no
    se ven afectados.
    """

    student_pseudonym: str
    comision_id: str
    n_groups_evaluated: int
    n_groups_insufficient: int
    n_episodes_total: int
    evolution_per_template: list[CIIEvolutionTemplateOut]
    evolution_per_unidad: list[CIIEvolutionUnidadOut] = []
    mean_slope: float | None
    sufficient_data: bool
    labeler_version: str


@router.get(
    "/student/{student_pseudonym}/cii-evolution-longitudinal",
    response_model=CIIEvolutionLongitudinalOut,
)
async def get_cii_evolution_longitudinal(
    student_pseudonym: UUID,
    comision_id: UUID,
    tenant_id: UUID = Depends(get_tenant_id),
    user_id: UUID = Depends(get_user_id),
    _comision_access: None = Depends(require_comision_access),
) -> CIIEvolutionLongitudinalOut:
    """CII evolution longitudinal del estudiante en una comisión (ADR-018).

    Agrupa episodios cerrados del estudiante por `TareaPractica.template_id`
    (problemas análogos definidos por ADR-016). Para cada grupo con N>=3
    calcula el slope de la regresión lineal sobre `APPROPRIATION_ORDINAL`
    ordenados por `classified_at`.

    Modo dev (sin DBs configuradas): devuelve estructura vacía con 200,
    coherente con `/cohort/{id}/progression` y `/n-level-distribution`.

    Modo real: triple cross-DB (CTR + classifier + academic) con RLS por
    tenant. La query está limitada a la comisión para acotar el scope —
    para análisis cross-comisión hay que llamar el endpoint N veces, una
    por comisión del estudiante.
    """
    from platform_ops import compute_cii_evolution_longitudinal

    from analytics_service.services.export import _real_data_source_enabled

    if not _real_data_source_enabled():
        # Modo dev: estructura vacía con labeler_version
        empty = compute_cii_evolution_longitudinal([])
        return CIIEvolutionLongitudinalOut(
            student_pseudonym=str(student_pseudonym),
            comision_id=str(comision_id),
            **empty,
        )

    # Modo real: 3 sesiones (ctr + classifier + academic) con RLS
    from platform_ops import RealLongitudinalDataSource, set_tenant_rls
    from sqlalchemy.ext.asyncio import async_sessionmaker

    ctr_engine = get_ctr_engine()
    cls_engine = get_classifier_engine()
    acad_engine = get_academic_engine()
    async with (
        async_sessionmaker(ctr_engine, expire_on_commit=False)() as ctr_s,
        async_sessionmaker(cls_engine, expire_on_commit=False)() as cls_s,
        async_sessionmaker(acad_engine, expire_on_commit=False)() as acad_s,
    ):
        await set_tenant_rls(ctr_s, tenant_id)
        await set_tenant_rls(cls_s, tenant_id)
        await set_tenant_rls(acad_s, tenant_id)
        ds = RealLongitudinalDataSource(ctr_s, cls_s, tenant_id)
        classifications = await ds.list_classifications_with_templates_for_student(
            student_pseudonym=student_pseudonym,
            comision_id=comision_id,
            academic_session=acad_s,
        )

        # Resolver unidad_id → nombre para los grupos de unidad.
        # Recopilar los unidad_ids no-None de las classifications.
        from uuid import UUID as _UUID

        unidad_ids_raw = {
            c["unidad_id"] for c in classifications if c.get("unidad_id") is not None
        }
        unidad_ids = [_UUID(str(uid)) for uid in unidad_ids_raw]
        unidad_map = await ds.list_unidades_by_ids(
            unidad_ids=unidad_ids,
            academic_session=acad_s,
        )

    distribution = compute_cii_evolution_longitudinal(classifications, unidad_map=unidad_map)
    logger.info(
        "cii_evolution_longitudinal_computed tenant_id=%s user_id=%s "
        "student_pseudonym=%s comision_id=%s n_episodes_total=%d "
        "n_groups_evaluated=%d mean_slope=%s labeler_version=%s "
        "n_unidad_groups=%d",
        tenant_id,
        user_id,
        student_pseudonym,
        comision_id,
        distribution["n_episodes_total"],
        distribution["n_groups_evaluated"],
        distribution["mean_slope"],
        distribution["labeler_version"],
        len(distribution.get("evolution_per_unidad", [])),
    )
    return CIIEvolutionLongitudinalOut(
        student_pseudonym=str(student_pseudonym),
        comision_id=str(comision_id),
        **distribution,
    )


# ── Listado de episodios cerrados del estudiante (drill-down nav) ────


class StudentEpisodeOut(BaseModel):
    episode_id: str
    problema_id: str
    tarea_codigo: str | None
    tarea_titulo: str | None
    template_id: str | None
    opened_at: str | None
    closed_at: str | None
    events_count: int
    appropriation: str | None
    classified_at: str | None


class StudentEpisodesOut(BaseModel):
    student_pseudonym: str
    comision_id: str
    n_episodes: int
    episodes: list[StudentEpisodeOut]


@router.get(
    "/student/me/episodes",
    response_model=StudentEpisodesOut,
)
async def get_my_episodes(
    comision_id: UUID,
    tenant_id: UUID = Depends(get_tenant_id),
    user_id: UUID = Depends(get_user_id),
) -> StudentEpisodesOut:
    """Episodios cerrados del PROPIO alumno autenticado (sin gate de docente).

    El `me` enforza que el alumno solo vea SUS episodios: `student_pseudonym`
    se deriva del JWT (`user_id`), no se acepta por path. Así el web-student no
    tiene que pegar al endpoint de docente `/student/{id}/episodes` (que le da
    403 y le filtra el UUID en la URL — F-08). DEBE quedar registrado ANTES de
    la ruta `/student/{student_pseudonym}/episodes` o FastAPI captura "me" como
    path param y tira 422.
    """
    from analytics_service.services.export import _real_data_source_enabled

    if not _real_data_source_enabled():
        return StudentEpisodesOut(
            student_pseudonym=str(user_id),
            comision_id=str(comision_id),
            n_episodes=0,
            episodes=[],
        )

    from platform_ops import RealLongitudinalDataSource, set_tenant_rls
    from sqlalchemy.ext.asyncio import async_sessionmaker

    ctr_engine = get_ctr_engine()
    cls_engine = get_classifier_engine()
    acad_engine = get_academic_engine()
    async with (
        async_sessionmaker(ctr_engine, expire_on_commit=False)() as ctr_s,
        async_sessionmaker(cls_engine, expire_on_commit=False)() as cls_s,
        async_sessionmaker(acad_engine, expire_on_commit=False)() as acad_s,
    ):
        await set_tenant_rls(ctr_s, tenant_id)
        await set_tenant_rls(cls_s, tenant_id)
        await set_tenant_rls(acad_s, tenant_id)
        ds = RealLongitudinalDataSource(ctr_s, cls_s, tenant_id)
        episodes = await ds.list_episodes_with_classifications_for_student(
            student_pseudonym=user_id,
            comision_id=comision_id,
            academic_session=acad_s,
        )

    logger.info(
        "my_episodes_listed tenant_id=%s user_id=%s comision_id=%s n_episodes=%d",
        tenant_id,
        user_id,
        comision_id,
        len(episodes),
    )
    return StudentEpisodesOut(
        student_pseudonym=str(user_id),
        comision_id=str(comision_id),
        n_episodes=len(episodes),
        episodes=[StudentEpisodeOut(**e) for e in episodes],
    )


@router.get(
    "/student/{student_pseudonym}/episodes",
    response_model=StudentEpisodesOut,
)
async def get_student_episodes(
    student_pseudonym: UUID,
    comision_id: UUID,
    tenant_id: UUID = Depends(get_tenant_id),
    user_id: UUID = Depends(get_user_id),
    _comision_access: None = Depends(require_comision_access),
) -> StudentEpisodesOut:
    """Listado de episodios CERRADOS del estudiante con classification + template_id.

    Para que el frontend muestre dropdown de episodios en lugar de exigir
    pegar UUIDs (ADR-022 — drill-down navegacional).
    """
    from analytics_service.services.export import _real_data_source_enabled

    if not _real_data_source_enabled():
        return StudentEpisodesOut(
            student_pseudonym=str(student_pseudonym),
            comision_id=str(comision_id),
            n_episodes=0,
            episodes=[],
        )

    from platform_ops import RealLongitudinalDataSource, set_tenant_rls
    from sqlalchemy.ext.asyncio import async_sessionmaker

    ctr_engine = get_ctr_engine()
    cls_engine = get_classifier_engine()
    acad_engine = get_academic_engine()
    async with (
        async_sessionmaker(ctr_engine, expire_on_commit=False)() as ctr_s,
        async_sessionmaker(cls_engine, expire_on_commit=False)() as cls_s,
        async_sessionmaker(acad_engine, expire_on_commit=False)() as acad_s,
    ):
        await set_tenant_rls(ctr_s, tenant_id)
        await set_tenant_rls(cls_s, tenant_id)
        await set_tenant_rls(acad_s, tenant_id)
        ds = RealLongitudinalDataSource(ctr_s, cls_s, tenant_id)
        episodes = await ds.list_episodes_with_classifications_for_student(
            student_pseudonym=student_pseudonym,
            comision_id=comision_id,
            academic_session=acad_s,
        )

    logger.info(
        "student_episodes_listed tenant_id=%s user_id=%s student_pseudonym=%s "
        "comision_id=%s n_episodes=%d",
        tenant_id,
        user_id,
        student_pseudonym,
        comision_id,
        len(episodes),
    )
    return StudentEpisodesOut(
        student_pseudonym=str(student_pseudonym),
        comision_id=str(comision_id),
        n_episodes=len(episodes),
        episodes=[StudentEpisodeOut(**e) for e in episodes],
    )


# ── Cuartiles agregados de cohorte (ADR-022, privacidad-safe) ─────────


class CohortCIIQuartilesOut(BaseModel):
    """Cuartiles agregados de los `mean_slope` longitudinales de la cohorte.

    NO expone slopes individuales — solo Q1/Q2/Q3/min/max/mean/std agregados.
    Si la cohorte tiene <5 estudiantes con slope no-null, devuelve
    `insufficient_data: true` (privacidad — cohortes muy chicas son
    des-anonimizables vía cuartiles).
    """

    comision_id: str
    labeler_version: str
    min_students_for_quartiles: int
    n_students_evaluated: int
    insufficient_data: bool
    q1: float | None
    median: float | None
    q3: float | None
    min: float | None
    max: float | None
    mean: float | None
    stdev: float | None


@router.get(
    "/cohort/{comision_id}/cii-quartiles",
    response_model=CohortCIIQuartilesOut,
)
async def get_cohort_cii_quartiles(
    comision_id: UUID,
    tenant_id: UUID = Depends(get_tenant_id),
    user_id: UUID = Depends(get_user_id),
    _comision_access: None = Depends(require_comision_access),
) -> CohortCIIQuartilesOut:
    """Cuartiles agregados del PROGRESO de la cohorte (ADR-022, revisado 2026-06-10).

    El "valor por alumno" es el delta de su apropiación (último tercio - primer
    tercio sobre todos sus episodios), NO el slope por template — el piloto ya no
    usa plantillas. Misma señal que `/cohort/{id}/progression`. NO expone valores
    individuales. <5 estudiantes con datos → `insufficient_data: true` (k-anonymity).
    """
    from platform_ops import compute_cohort_quartiles_payload

    from analytics_service.services.export import _real_data_source_enabled

    if not _real_data_source_enabled():
        empty = compute_cohort_quartiles_payload([])
        return CohortCIIQuartilesOut(comision_id=str(comision_id), **empty)

    # Vuelta de rosca (2026-06-10): el cuartil ANTES dependía del slope longitudinal
    # POR TEMPLATE (>=3 episodios del mismo template). Como el piloto ya no usa
    # plantillas, daba siempre 0 estudiantes evaluados. Ahora cuartilizamos sobre el
    # PROGRESO GENERAL del alumno (delta primer->ultimo tercio de su apropiación, sobre
    # TODOS sus episodios), la misma señal que usa /cohort/{id}/progression.
    from platform_ops import (
        RealLongitudinalDataSource,
        build_trajectories,
        set_tenant_rls,
    )
    from sqlalchemy.ext.asyncio import async_sessionmaker

    ctr_engine = get_ctr_engine()
    cls_engine = get_classifier_engine()
    async with (
        async_sessionmaker(ctr_engine, expire_on_commit=False)() as ctr_s,
        async_sessionmaker(cls_engine, expire_on_commit=False)() as cls_s,
    ):
        await set_tenant_rls(ctr_s, tenant_id)
        await set_tenant_rls(cls_s, tenant_id)
        ds = RealLongitudinalDataSource(ctr_s, cls_s, tenant_id)
        trajectories = await build_trajectories(ds, comision_id)  # type: ignore[arg-type]

    student_slopes: list[float] = []
    for t in trajectories:
        terciles = t.tercile_means()  # None si <3 episodios
        if terciles is not None:
            first, _mid, last = terciles
            student_slopes.append(last - first)

    payload = compute_cohort_quartiles_payload(student_slopes)
    logger.info(
        "cohort_cii_quartiles_computed tenant_id=%s user_id=%s comision_id=%s "
        "n_students_evaluated=%d insufficient_data=%s",
        tenant_id,
        user_id,
        comision_id,
        payload["n_students_evaluated"],
        payload["insufficient_data"],
    )
    return CohortCIIQuartilesOut(comision_id=str(comision_id), **payload)


# ── Alertas longitudinales del estudiante (ADR-022) ───────────────────


class StudentAlertOut(BaseModel):
    code: str
    severity: Literal["low", "medium", "high"]
    title: str
    detail: str
    threshold_used: str
    z_score: float | None = None


class StudentAlertsOut(BaseModel):
    student_pseudonym: str
    comision_id: str
    labeler_version: str
    student_slope: float | None
    cohort_stats: dict[str, Any]
    quartile: Literal["Q1", "Q2", "Q3", "Q4"] | None
    alerts: list[StudentAlertOut]
    n_alerts: int
    highest_severity: Literal["low", "medium", "high"] | None


@router.get(
    "/student/{student_pseudonym}/alerts",
    response_model=StudentAlertsOut,
)
async def get_student_alerts(
    student_pseudonym: UUID,
    comision_id: UUID,
    tenant_id: UUID = Depends(get_tenant_id),
    user_id: UUID = Depends(get_user_id),
    _comision_access: None = Depends(require_comision_access),
) -> StudentAlertsOut:
    """Alertas longitudinales del estudiante vs. cohorte (ADR-022, audit G7).

    Compara `mean_slope` del estudiante con la distribución agregada de la
    cohorte y emite alertas si está >1σ debajo de la media o en Q1.
    Modo dev devuelve estructura vacía sin alertas.
    """
    from platform_ops import compute_alerts_payload, compute_cohort_quartiles_payload

    from analytics_service.services.export import _real_data_source_enabled

    if not _real_data_source_enabled():
        empty_cohort = compute_cohort_quartiles_payload([])
        empty_alerts = compute_alerts_payload(None, empty_cohort)
        return StudentAlertsOut(
            student_pseudonym=str(student_pseudonym),
            comision_id=str(comision_id),
            **empty_alerts,
        )

    from platform_ops import (
        RealLongitudinalDataSource,
        compute_cii_evolution_longitudinal,
        set_tenant_rls,
    )
    from sqlalchemy.ext.asyncio import async_sessionmaker

    ctr_engine = get_ctr_engine()
    cls_engine = get_classifier_engine()
    acad_engine = get_academic_engine()
    student_slope: float | None = None
    cohort_slopes: list[float] = []
    async with (
        async_sessionmaker(ctr_engine, expire_on_commit=False)() as ctr_s,
        async_sessionmaker(cls_engine, expire_on_commit=False)() as cls_s,
        async_sessionmaker(acad_engine, expire_on_commit=False)() as acad_s,
    ):
        await set_tenant_rls(ctr_s, tenant_id)
        await set_tenant_rls(cls_s, tenant_id)
        await set_tenant_rls(acad_s, tenant_id)
        ds = RealLongitudinalDataSource(ctr_s, cls_s, tenant_id)

        # 1. Slope del estudiante target
        student_classifications = await ds.list_classifications_with_templates_for_student(
            student_pseudonym=student_pseudonym,
            comision_id=comision_id,
            academic_session=acad_s,
        )
        student_evolution = compute_cii_evolution_longitudinal(student_classifications)
        student_slope = student_evolution["mean_slope"]

        # 2. Slopes de toda la cohorte (para cuartiles)
        from ctr_service.models import Episode
        from sqlalchemy import select

        ep_stmt = (
            select(Episode.student_pseudonym)
            .where(Episode.comision_id == comision_id)
            .where(Episode.tenant_id == tenant_id)
            .distinct()
        )
        students_result = await ctr_s.execute(ep_stmt)
        student_ids = [row.student_pseudonym for row in students_result.all()]
        for sid in student_ids:
            cls = await ds.list_classifications_with_templates_for_student(
                student_pseudonym=sid,
                comision_id=comision_id,
                academic_session=acad_s,
            )
            evo = compute_cii_evolution_longitudinal(cls)
            if evo["mean_slope"] is not None:
                cohort_slopes.append(evo["mean_slope"])

    cohort_stats = compute_cohort_quartiles_payload(cohort_slopes)
    alerts_payload = compute_alerts_payload(student_slope, cohort_stats)
    logger.info(
        "student_alerts_computed tenant_id=%s user_id=%s student_pseudonym=%s "
        "comision_id=%s n_alerts=%d highest_severity=%s",
        tenant_id,
        user_id,
        student_pseudonym,
        comision_id,
        alerts_payload["n_alerts"],
        alerts_payload["highest_severity"],
    )
    return StudentAlertsOut(
        student_pseudonym=str(student_pseudonym),
        comision_id=str(comision_id),
        **alerts_payload,
    )


# ── Alerts summary agregado por cohorte (ADR-022, KPI del HomeView) ───


class CohortAlertsSummaryCounts(BaseModel):
    """Conteo de estudiantes por tipo de alerta para la cohorte.

    Cada campo cuenta estudiantes distintos con la alerta indicada (no
    eventos). `students_with_any_alert` es count distinct de estudiantes
    con al menos una de las 3 alertas (NO es la suma — un mismo estudiante
    puede acumular regresion_vs_cohorte + bottom_quartile + slope_negativo).
    """

    regresion_vs_cohorte: int
    bottom_quartile: int
    slope_negativo_significativo: int
    students_with_any_alert: int


class CohortAlertsSummaryOut(BaseModel):
    """Agregación a nivel cohorte de las alertas individuales (ADR-022).

    Sirve como KPI "alertas por cohorte" del HomeView del web-teacher.
    Itera por estudiante, computa `get_student_alerts` por dentro y
    cuenta cuántos estudiantes tienen cada tipo de alerta.

    Privacy gate: si la cohorte tiene `n_students_evaluated <
    MIN_STUDENTS_FOR_QUARTILES (5)`, devuelve `insufficient_data: true`
    con `alerts_summary: null` — sin counts. Las alertas individuales
    dependen de cohort stats que también requieren N≥5, entonces el
    gate se preserva consistente con `/cohort/{id}/cii-quartiles` y
    `/student/{id}/alerts`.
    """

    comision_id: str
    n_students_evaluated: int
    min_students_threshold: int
    insufficient_data: bool
    alerts_summary: CohortAlertsSummaryCounts | None
    labeler_version: str


@router.get(
    "/cohort/{comision_id}/alerts-summary",
    response_model=CohortAlertsSummaryOut,
)
async def get_cohort_alerts_summary(
    comision_id: UUID,
    periodo_id: UUID | None = None,
    tenant_id: UUID = Depends(get_tenant_id),
    user_id: UUID = Depends(get_user_id),
    _comision_access: None = Depends(require_comision_access),
) -> CohortAlertsSummaryOut:
    """Resumen agregado de alertas predictivas por cohorte (ADR-022).

    Cierra el gap UI doble identificado en auditoría (2026-05-17):
    `HomeView.tsx` declaraba este endpoint como pendiente y el KPI
    "alertas" caía a `null` permanente. Este endpoint NO duplica lógica
    de `cii_alerts.py` — itera por estudiantes y reusa el cómputo que
    ya se hace en `/student/{id}/alerts`.

    El parámetro `periodo_id` queda declarado para consistencia con otros
    endpoints (governance/events, adversarial-events) pero por ahora la
    cohorte `comision_id` ya define el scope temporal/académico. Mantenerlo
    en signature evita un breaking change si el filtro se cierra a futuro.

    Modo dev (sin DBs): devuelve `n_students_evaluated=0` +
    `insufficient_data=true` + `alerts_summary=null`, consistente con
    el resto de los endpoints de cohorte.
    """
    from analytics_service.services.export import _real_data_source_enabled

    if not _real_data_source_enabled():
        return CohortAlertsSummaryOut(
            comision_id=str(comision_id),
            n_students_evaluated=0,
            min_students_threshold=MIN_STUDENTS_FOR_QUARTILES,
            insufficient_data=True,
            alerts_summary=None,
            labeler_version=ALERTS_VERSION,
        )

    from platform_ops import (
        RealLongitudinalDataSource,
        compute_cii_evolution_longitudinal,
        set_tenant_rls,
    )
    from sqlalchemy.ext.asyncio import async_sessionmaker

    ctr_engine = get_ctr_engine()
    cls_engine = get_classifier_engine()
    acad_engine = get_academic_engine()

    # Paso 1: recopilar slopes por estudiante (1 pasada para cohort stats
    # + n_students_evaluated). Paso 2: si N≥5, computar alertas individuales
    # y agregar por tipo.
    student_slope_pairs: list[tuple[UUID, float]] = []
    async with (
        async_sessionmaker(ctr_engine, expire_on_commit=False)() as ctr_s,
        async_sessionmaker(cls_engine, expire_on_commit=False)() as cls_s,
        async_sessionmaker(acad_engine, expire_on_commit=False)() as acad_s,
    ):
        await set_tenant_rls(ctr_s, tenant_id)
        await set_tenant_rls(cls_s, tenant_id)
        await set_tenant_rls(acad_s, tenant_id)
        ds = RealLongitudinalDataSource(ctr_s, cls_s, tenant_id)

        from ctr_service.models import Episode
        from sqlalchemy import select

        ep_stmt = (
            select(Episode.student_pseudonym)
            .where(Episode.comision_id == comision_id)
            .where(Episode.tenant_id == tenant_id)
            .distinct()
        )
        students_result = await ctr_s.execute(ep_stmt)
        student_ids = [row.student_pseudonym for row in students_result.all()]

        for sid in student_ids:
            cls = await ds.list_classifications_with_templates_for_student(
                student_pseudonym=sid,
                comision_id=comision_id,
                academic_session=acad_s,
            )
            evo = compute_cii_evolution_longitudinal(cls)
            if evo["mean_slope"] is not None:
                student_slope_pairs.append((sid, evo["mean_slope"]))

    cohort_slopes = [slope for _sid, slope in student_slope_pairs]
    cohort_stats = compute_cohort_quartiles_payload(cohort_slopes)
    n_evaluated = len(cohort_slopes)

    # Privacy gate (k-anonymity): cohort_stats lleva `insufficient_data`
    # cuando N < MIN_STUDENTS_FOR_QUARTILES. Sin cohort stats no se pueden
    # computar 2/3 alertas (regresion_vs_cohorte, bottom_quartile dependen
    # de mean+stdev+cuartiles). Devolvemos null sin counts, consistente
    # con el shape de `/cohort/{id}/cii-quartiles`.
    if cohort_stats.get("insufficient_data"):
        logger.info(
            "cohort_alerts_summary_insufficient tenant_id=%s user_id=%s "
            "comision_id=%s n_students_evaluated=%d threshold=%d",
            tenant_id,
            user_id,
            comision_id,
            n_evaluated,
            MIN_STUDENTS_FOR_QUARTILES,
        )
        return CohortAlertsSummaryOut(
            comision_id=str(comision_id),
            n_students_evaluated=n_evaluated,
            min_students_threshold=MIN_STUDENTS_FOR_QUARTILES,
            insufficient_data=True,
            alerts_summary=None,
            labeler_version=ALERTS_VERSION,
        )

    # Agregar conteos por código de alerta (cuenta estudiantes distintos).
    count_regresion = 0
    count_bottom = 0
    count_slope_neg = 0
    count_any = 0
    for _sid, slope in student_slope_pairs:
        alerts_payload = compute_alerts_payload(slope, cohort_stats)
        codes = {a["code"] for a in alerts_payload["alerts"]}
        if not codes:
            continue
        count_any += 1
        if "regresion_vs_cohorte" in codes:
            count_regresion += 1
        if "bottom_quartile" in codes:
            count_bottom += 1
        if "slope_negativo_significativo" in codes:
            count_slope_neg += 1

    summary = CohortAlertsSummaryCounts(
        regresion_vs_cohorte=count_regresion,
        bottom_quartile=count_bottom,
        slope_negativo_significativo=count_slope_neg,
        students_with_any_alert=count_any,
    )

    logger.info(
        "cohort_alerts_summary_computed tenant_id=%s user_id=%s "
        "comision_id=%s n_students_evaluated=%d students_with_any_alert=%d "
        "regresion=%d bottom_quartile=%d slope_neg=%d",
        tenant_id,
        user_id,
        comision_id,
        n_evaluated,
        count_any,
        count_regresion,
        count_bottom,
        count_slope_neg,
    )

    return CohortAlertsSummaryOut(
        comision_id=str(comision_id),
        n_students_evaluated=n_evaluated,
        min_students_threshold=MIN_STUDENTS_FOR_QUARTILES,
        insufficient_data=False,
        alerts_summary=summary,
        labeler_version=ALERTS_VERSION,
    )


# ── Eventos adversos por cohorte (ADR-019, agregación al docente) ────


class AdversarialRecentEventOut(BaseModel):
    episode_id: str
    student_pseudonym: str
    ts: str
    category: str
    severity: int
    pattern_id: str
    matched_text: str


class AdversarialTopStudentOut(BaseModel):
    student_pseudonym: str
    n_events: int


class CohortAdversarialEventsOut(BaseModel):
    """Agregado de eventos `intento_adverso_detectado` para una cohorte."""

    comision_id: str
    n_events_total: int
    counts_by_category: dict[str, int]
    counts_by_severity: dict[str, int]
    counts_by_student: dict[str, int]
    top_students_by_n_events: list[AdversarialTopStudentOut]
    recent_events: list[AdversarialRecentEventOut]


@router.get(
    "/cohort/{comision_id}/adversarial-events",
    response_model=CohortAdversarialEventsOut,
)
async def get_cohort_adversarial_events(
    comision_id: UUID,
    facultad_id: UUID | None = None,
    materia_id: UUID | None = None,
    periodo_id: UUID | None = None,
    tenant_id: UUID = Depends(get_tenant_id),
    user_id: UUID = Depends(get_user_id),
    _comision_access: None = Depends(require_comision_access),
) -> CohortAdversarialEventsOut:
    """Agregado de eventos adversos para visibilidad pedagógica del docente.

    Lee eventos `intento_adverso_detectado` (ADR-019, RN-129) de los episodios
    de una comisión, los agrega por categoría/severidad/estudiante, y devuelve
    los más recientes con `matched_text` truncado a 200 chars.

    Modo dev: estructura vacía con 200. Modo real: cross-DB CTR con RLS.

    Query params opcionales (epic ai-native-completion-and-byok / Sec 12):
    `facultad_id`, `materia_id`, `periodo_id` quedan declarados pero el caller
    canónico hoy ignora los filtros — la cohort {comision_id} ya define el
    scope. El endpoint cross-cohort que SÍ los aplica es
    `GET /api/v1/analytics/governance/events`.
    """
    from platform_ops import aggregate_adversarial_events

    from analytics_service.services.export import _real_data_source_enabled

    if not _real_data_source_enabled():
        empty = aggregate_adversarial_events([])
        return CohortAdversarialEventsOut(comision_id=str(comision_id), **empty)

    from platform_ops import RealLongitudinalDataSource, set_tenant_rls
    from sqlalchemy.ext.asyncio import async_sessionmaker

    ctr_engine = get_ctr_engine()
    cls_engine = get_classifier_engine()
    async with (
        async_sessionmaker(ctr_engine, expire_on_commit=False)() as ctr_s,
        async_sessionmaker(cls_engine, expire_on_commit=False)() as cls_s,
    ):
        await set_tenant_rls(ctr_s, tenant_id)
        await set_tenant_rls(cls_s, tenant_id)
        ds = RealLongitudinalDataSource(ctr_s, cls_s, tenant_id)
        events = await ds.list_adversarial_events_by_comision(comision_id)

    aggregated = aggregate_adversarial_events(events)
    logger.info(
        "cohort_adversarial_events_computed tenant_id=%s user_id=%s "
        "comision_id=%s n_events=%d n_categories=%d",
        tenant_id,
        user_id,
        comision_id,
        aggregated["n_events_total"],
        len(aggregated["counts_by_category"]),
    )
    return CohortAdversarialEventsOut(comision_id=str(comision_id), **aggregated)


# ── Integridad del episodio (foco + clipboard) ─────────────────────────


class IntegrityRecentEventOut(BaseModel):
    """Un evento de integridad (cambio de pestaña / clipboard bloqueado)."""

    episode_id: str
    student_pseudonym: str
    ts: str
    event_type: str  # "pestana_perdida" | "pestana_recuperada" | "copia_intentada" | "pega_intentada"
    payload: dict  # shape específico por event_type — el frontend formatea


class IntegrityTopStudentOut(BaseModel):
    student_pseudonym: str
    n_events: int


class CohortIntegrityEventsOut(BaseModel):
    """Agregado de eventos de integridad para una cohorte."""

    comision_id: str
    n_events_total: int
    counts_by_type: dict[str, int]
    counts_by_student: dict[str, int]
    top_students_by_n_events: list[IntegrityTopStudentOut]
    recent_events: list[IntegrityRecentEventOut]


@router.get(
    "/cohort/{comision_id}/integrity-events",
    response_model=CohortIntegrityEventsOut,
)
async def get_cohort_integrity_events(
    comision_id: UUID,
    tenant_id: UUID = Depends(get_tenant_id),
    user_id: UUID = Depends(get_user_id),
    _comision_access: None = Depends(require_comision_access),
) -> CohortIntegrityEventsOut:
    """Agregado de eventos de integridad del episodio (foco + clipboard).

    Cubre los 4 event_types side-channel:
      - `pestana_perdida` / `pestana_recuperada` (foco del browser)
      - `copia_intentada` / `pega_intentada` (clipboard bloqueado en Monaco)

    A diferencia de `intento_adverso_detectado` (prompt-based, ADR-019),
    no hay categoria/severity uniformes — cada tipo tiene su payload.
    El frontend renderiza por tipo.
    """
    from analytics_service.services.export import _real_data_source_enabled

    empty = {
        "n_events_total": 0,
        "counts_by_type": {},
        "counts_by_student": {},
        "top_students_by_n_events": [],
        "recent_events": [],
    }
    if not _real_data_source_enabled():
        return CohortIntegrityEventsOut(comision_id=str(comision_id), **empty)

    from platform_ops import RealLongitudinalDataSource, set_tenant_rls
    from sqlalchemy.ext.asyncio import async_sessionmaker

    ctr_engine = get_ctr_engine()
    cls_engine = get_classifier_engine()
    async with (
        async_sessionmaker(ctr_engine, expire_on_commit=False)() as ctr_s,
        async_sessionmaker(cls_engine, expire_on_commit=False)() as cls_s,
    ):
        await set_tenant_rls(ctr_s, tenant_id)
        await set_tenant_rls(cls_s, tenant_id)
        ds = RealLongitudinalDataSource(ctr_s, cls_s, tenant_id)
        events = await ds.list_integrity_events_by_comision(comision_id)

    # Agregacion inline (simpler than the adversarial one — solo 4 types).
    counts_by_type: dict[str, int] = {}
    counts_by_student: dict[str, int] = {}
    for ev in events:
        counts_by_type[ev["event_type"]] = counts_by_type.get(ev["event_type"], 0) + 1
        sp = ev["student_pseudonym"]
        counts_by_student[sp] = counts_by_student.get(sp, 0) + 1

    top_students = [
        IntegrityTopStudentOut(student_pseudonym=sp, n_events=n)
        for sp, n in sorted(counts_by_student.items(), key=lambda x: -x[1])[:10]
    ]

    logger.info(
        "cohort_integrity_events_computed tenant_id=%s user_id=%s "
        "comision_id=%s n_events=%d",
        tenant_id,
        user_id,
        comision_id,
        len(events),
    )
    return CohortIntegrityEventsOut(
        comision_id=str(comision_id),
        n_events_total=len(events),
        counts_by_type=counts_by_type,
        counts_by_student=counts_by_student,
        top_students_by_n_events=top_students,
        recent_events=[IntegrityRecentEventOut(**ev) for ev in events],
    )


# ── A/B testing de profiles (F7) ───────────────────────────────────────


class ABTestRequest(BaseModel):
    """Request para A/B testing de profiles contra gold standard humano."""

    episodes: list[dict]  # [{"episode_id": str, "events": [...], "human_label": str}]
    profiles: list[dict]  # [{"name": str, "version": str, "thresholds": {...}}]


class ProfileComparisonOut(BaseModel):
    profile_name: str
    profile_version: str
    profile_hash: str
    kappa: float
    interpretation: str
    predictions: dict[str, str]


class ABTestResponse(BaseModel):
    n_episodes: int
    winner_by_kappa: str | None
    results: list[ProfileComparisonOut]


@router.post("/ab-test-profiles", response_model=ABTestResponse)
async def ab_test_profiles(
    req: ABTestRequest,
    tenant_id: UUID = Depends(get_tenant_id),
    user_id: UUID = Depends(get_user_id),
) -> ABTestResponse:
    """Compara múltiples reference_profiles del clasificador contra un
    gold standard de etiquetado humano.

    Caso de uso: al calibrar el árbol N4 con datos reales del piloto,
    el investigador provee N episodios con etiqueta humana, pasa 2+
    profiles candidatos, y obtiene Kappa de cada uno. El ganador es el
    profile que más se acerca al juicio humano.

    Formato del episodio:
        {
            "episode_id": "ep_123",
            "events": [{ev1}, {ev2}, ...],
            "human_label": "apropiacion_reflexiva"
        }

    HU-088 audit trail: emite `ab_test_profiles_completed` por structlog
    (config global del servicio vía `platform_observability`). No persiste
    en tabla `audit_log` — la decisión es interpretación de "Los resultados
    quedan en AuditLog" como log estructurado a Loki/Grafana, dado que el
    endpoint es infra de investigación, no CRUD académico bajo compliance
    bit-exact. Ver entrada HU-088 en `BUGS-PILOTO.md`.
    """
    import sys
    from pathlib import Path

    # Permitir importar classifier-service en runtime
    classifier_src = Path(__file__).parent.parent.parent.parent.parent / "classifier-service/src"
    if str(classifier_src) not in sys.path:
        sys.path.insert(0, str(classifier_src))

    try:
        from classifier_service.services.pipeline import (
            classify_episode_from_events,
            compute_classifier_config_hash,
        )
    except ImportError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"classifier-service module no disponible: {e}",
        )

    from platform_ops import EpisodeForComparison, compare_profiles

    # Validar input
    if len(req.episodes) < 2:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Se requieren al menos 2 episodios para calcular Kappa",
        )
    if len(req.profiles) < 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Al menos 1 profile es requerido",
        )

    episodes = [
        EpisodeForComparison(
            episode_id=e["episode_id"],
            events=e["events"],
            human_label=e["human_label"],
        )
        for e in req.episodes
    ]

    try:
        report = compare_profiles(
            episodes=episodes,
            profiles=req.profiles,
            classify_fn=classify_episode_from_events,
            compute_hash_fn=compute_classifier_config_hash,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    # HU-088 audit trail: log estructurado del A/B testing (no se persiste a DB).
    kappa_per_profile = {r.profile_name: r.kappa.kappa for r in report.results}
    config_hash_per_profile = {r.profile_name: r.profile_hash for r in report.results}
    logger.info(
        "ab_test_profiles_completed tenant_id=%s user_id=%s "
        "n_episodes_compared=%d n_profiles_compared=%d "
        "winner_profile_name=%s kappa_per_profile=%s classifier_config_hash=%s",
        tenant_id,
        user_id,
        report.n_episodes,
        len(report.results),
        report.winner_by_kappa,
        kappa_per_profile,
        config_hash_per_profile,
    )

    return ABTestResponse(
        n_episodes=report.n_episodes,
        winner_by_kappa=report.winner_by_kappa,
        results=[
            ProfileComparisonOut(
                profile_name=r.profile_name,
                profile_version=r.profile_version,
                profile_hash=r.profile_hash,
                kappa=r.kappa.kappa,
                interpretation=r.interpretation,
                predictions=r.predictions,
            )
            for r in report.results
        ],
    )


# ── Governance Events cross-cohort (Sec 12 epic ai-native-completion) ──


class GovernanceEventOut(BaseModel):
    """Evento adverso individual para la vista institucional cross-cohort."""

    episode_id: str
    student_pseudonym: str
    comision_id: str
    ts: str
    category: str
    severity: int
    pattern_id: str
    matched_text: str


class GovernanceEventsResponse(BaseModel):
    """Response paginada del endpoint governance/events.

    Pagination cursor-based (mismo patron que ProgressionView): el cliente
    pasa `cursor` para la siguiente pagina. Cuando `cursor_next` es None,
    no hay mas datos.
    """

    events: list[GovernanceEventOut]
    cursor_next: str | None = None
    n_total_estimate: int
    counts_by_category: dict[str, int]
    counts_by_severity: dict[str, int]
    filters_applied: dict[str, str | None]


@router.get(
    "/governance/events",
    response_model=GovernanceEventsResponse,
)
async def get_governance_events(
    facultad_id: UUID | None = None,
    materia_id: UUID | None = None,
    periodo_id: UUID | None = None,
    severity_min: int | None = None,
    severity_max: int | None = None,
    category: str | None = None,
    cursor: str | None = None,
    limit: int = 100,
    tenant_id: UUID = Depends(get_tenant_id),
    user_id: UUID = Depends(get_user_id),
) -> GovernanceEventsResponse:
    """Vista institucional cross-cohort de eventos adversos (ADR-019, RN-129).

    Solo lectura. Sin tabla nueva — agrega los `intento_adverso_detectado` del
    CTR aplicando filtros opcionales (facultad/materia/periodo/severidad/categoria).
    Pagination cursor-based para soportar miles de eventos a nivel facultad.

    Modo dev: estructura vacia con 200. Modo real: cross-DB CTR con RLS.

    Casbin: el caller debe ser `superadmin` o `docente_admin` — enforced en
    api-gateway/casbin policies (governance:read).
    """
    from analytics_service.services.export import _real_data_source_enabled

    filters_applied: dict[str, str | None] = {
        "facultad_id": str(facultad_id) if facultad_id else None,
        "materia_id": str(materia_id) if materia_id else None,
        "periodo_id": str(periodo_id) if periodo_id else None,
        "severity_min": str(severity_min) if severity_min is not None else None,
        "severity_max": str(severity_max) if severity_max is not None else None,
        "category": category,
    }

    if not _real_data_source_enabled():
        # Stub mode: estructura vacia consistente con la response real.
        return GovernanceEventsResponse(
            events=[],
            cursor_next=None,
            n_total_estimate=0,
            counts_by_category={},
            counts_by_severity={},
            filters_applied=filters_applied,
        )

    from platform_ops import RealLongitudinalDataSource, set_tenant_rls
    from sqlalchemy.ext.asyncio import async_sessionmaker

    ctr_engine = get_ctr_engine()
    cls_engine = get_classifier_engine()
    async with (
        async_sessionmaker(ctr_engine, expire_on_commit=False)() as ctr_s,
        async_sessionmaker(cls_engine, expire_on_commit=False)() as cls_s,
    ):
        await set_tenant_rls(ctr_s, tenant_id)
        await set_tenant_rls(cls_s, tenant_id)
        ds = RealLongitudinalDataSource(ctr_s, cls_s, tenant_id)
        # NOTA: list_governance_events_cross_cohort es un metodo nuevo del
        # data source — debe filtrar por academic_main JOIN para resolver
        # facultad_id/materia_id/periodo_id desde Comision/Materia/Periodo.
        # Si el metodo no existe (compat dev), caemos a list por comision sin
        # filtros de facultad — el frontend muestra el subset disponible.
        list_fn = getattr(ds, "list_governance_events_cross_cohort", None)
        if list_fn is None:
            events_raw: list[dict] = []
        else:
            events_raw = await list_fn(
                facultad_id=facultad_id,
                materia_id=materia_id,
                periodo_id=periodo_id,
                severity_min=severity_min,
                severity_max=severity_max,
                category=category,
                cursor=cursor,
                limit=limit,
            )

    events_out = [
        GovernanceEventOut(
            episode_id=str(e["episode_id"]),
            student_pseudonym=str(e["student_pseudonym"]),
            comision_id=str(e["comision_id"]),
            ts=str(e["ts"]),
            category=str(e["category"]),
            severity=int(e["severity"]),
            pattern_id=str(e["pattern_id"]),
            matched_text=str(e["matched_text"]),
        )
        for e in events_raw
    ]

    counts_by_category: dict[str, int] = {}
    counts_by_severity: dict[str, int] = {}
    for ev in events_out:
        counts_by_category[ev.category] = counts_by_category.get(ev.category, 0) + 1
        counts_by_severity[str(ev.severity)] = counts_by_severity.get(str(ev.severity), 0) + 1

    cursor_next: str | None = None
    if len(events_out) == limit and events_out:
        # Cursor opaco = ultimo ts visto (orden DESC por ts en el datasource)
        cursor_next = events_out[-1].ts

    logger.info(
        "governance_events_listed tenant_id=%s user_id=%s "
        "facultad_id=%s materia_id=%s periodo_id=%s n_events=%d category_filter=%s",
        tenant_id,
        user_id,
        facultad_id,
        materia_id,
        periodo_id,
        len(events_out),
        category,
    )

    return GovernanceEventsResponse(
        events=events_out,
        cursor_next=cursor_next,
        n_total_estimate=len(events_out),
        counts_by_category=counts_by_category,
        counts_by_severity=counts_by_severity,
        filters_applied=filters_applied,
    )


# ── Historial de reflexiones metacognitivas del estudiante (ADR-035) ──


class ReflectionAnswers(BaseModel):
    """Las 3 respuestas libres del cuestionario `reflection/v1.0.0` (ADR-035)."""

    que_aprendiste: str
    dificultad_encontrada: str
    que_haria_distinto: str


class ReflectionEntryOut(BaseModel):
    """Una reflexion completada vinculada a su episodio + TP de origen."""

    episode_id: str
    problema_id: str
    tarea_codigo: str | None
    tarea_titulo: str | None
    closed_at: str | None
    reflected_at: str  # ts del evento reflexion_completada (post-cierre)
    prompt_version: str
    tiempo_completado_ms: int
    answers: ReflectionAnswers


class MyReflectionsResponse(BaseModel):
    """Listado paginado (cursor-based) de las reflexiones del estudiante autenticado.

    El path canónico es `/student/me/reflections` — el `me` enforza que el
    filtro por `student_pseudonym` se hace **siempre** con el `X-User-Id`
    autoritativo del api-gateway, sin path param manipulable por el cliente.
    """

    student_pseudonym: str
    n_returned: int
    has_more: bool
    cursor_next: str | None
    reflections: list[ReflectionEntryOut]


@router.get(
    "/student/me/reflections",
    response_model=MyReflectionsResponse,
)
async def get_my_reflections(  # noqa: PLR0915  # endpoint complejo: query + parsing cursor + filtros doble defensivos
    limit: int = 20,
    cursor: str | None = None,
    tenant_id: UUID = Depends(get_tenant_id),
    user_id: UUID = Depends(get_user_id),
) -> MyReflectionsResponse:
    """Listado del historial de reflexiones metacognitivas del estudiante (ADR-035).

    Cierra el gap: hasta hoy la reflexion solo era visible inmediatamente
    post-cierre dentro de EpisodePage.tsx. Ahora el estudiante puede revisar
    todas sus reflexiones pasadas.

    Filtro autoritativo por `X-User-Id` (api-gateway) — el estudiante SOLO
    ve sus propias reflexiones. RLS de Postgres ya filtra por tenant.

    Keyset pagination por `ts` del evento (orden DESC). Cursor opaco = ISO
    string del `ts` del ultimo evento devuelto.

    Modo dev (sin DBs configuradas): devuelve lista vacia con 200,
    coherente con el resto de endpoints de analytics.

    Privacy:
      - Las reflexiones siguen excluidas del feature extraction del classifier
        (ADR-027, _EXCLUDED_FROM_FEATURES). Este endpoint es solo lectura,
        no afecta la clasificacion N4 ni el classifier_config_hash.
      - El export academico (`academic_export.py`) sigue redactando los 3
        campos por default — este endpoint NO bypassea ese gate, es un canal
        independiente del export para el propio dueño de la reflexion.
    """
    # Cap defensivo del limit: protege contra payloads enormes
    limit = max(limit, 1)
    limit = min(limit, 100)

    from analytics_service.services.export import _real_data_source_enabled

    if not _real_data_source_enabled():
        # Modo dev: estructura vacia.
        return MyReflectionsResponse(
            student_pseudonym=str(user_id),
            n_returned=0,
            has_more=False,
            cursor_next=None,
            reflections=[],
        )

    from datetime import datetime as _datetime

    # Parseo del cursor opaco: si viene, debe ser ISO datetime UTC.
    cursor_dt: _datetime | None = None
    if cursor:
        try:
            cursor_str = cursor[:-1] + "+00:00" if cursor.endswith("Z") else cursor
            cursor_dt = _datetime.fromisoformat(cursor_str)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="cursor invalido: debe ser ISO-8601 UTC",
            )

    from platform_ops import set_tenant_rls
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker

    ctr_engine = get_ctr_engine()
    acad_engine = get_academic_engine()
    ctr_maker = async_sessionmaker(ctr_engine, expire_on_commit=False)
    acad_maker = async_sessionmaker(acad_engine, expire_on_commit=False)
    async with ctr_maker() as ctr_s, acad_maker() as acad_s:
        await set_tenant_rls(ctr_s, tenant_id)
        await set_tenant_rls(acad_s, tenant_id)

        # Late imports (modelos viven en otros servicios)
        from academic_service.models.operacional import TareaPractica
        from ctr_service.models import Episode, Event

        # Query: JOIN Event (reflexion_completada) con Episode para
        # asegurar que el episodio sea del estudiante autenticado.
        # Doble filtro (RLS + WHERE explicito) es el patron defensivo
        # de ADR-007.
        stmt = (
            select(Event, Episode)
            .join(Episode, Episode.id == Event.episode_id)
            .where(Event.event_type == "reflexion_completada")
            .where(Event.tenant_id == tenant_id)
            .where(Episode.tenant_id == tenant_id)
            .where(Episode.student_pseudonym == user_id)
            .order_by(Event.ts.desc())
        )
        if cursor_dt is not None:
            stmt = stmt.where(Event.ts < cursor_dt)
        # Pedimos limit+1 para detectar si hay mas paginas sin un count
        # adicional.
        stmt = stmt.limit(limit + 1)
        result = await ctr_s.execute(stmt)
        rows = result.all()

        has_more = len(rows) > limit
        visible_rows = rows[:limit]

        # Resolver titulos/codigos de TPs en un solo query batch
        problema_ids = list({row.Episode.problema_id for row in visible_rows})
        tarea_map: dict[UUID, tuple[str | None, str | None]] = {}
        if problema_ids:
            tp_stmt = (
                select(TareaPractica.id, TareaPractica.codigo, TareaPractica.titulo)
                .where(TareaPractica.id.in_(problema_ids))
                .where(TareaPractica.tenant_id == tenant_id)
            )
            tp_result = await acad_s.execute(tp_stmt)
            for tp_id, tp_codigo, tp_titulo in tp_result.all():
                tarea_map[tp_id] = (tp_codigo, tp_titulo)

    reflections: list[ReflectionEntryOut] = []
    last_ts: _datetime | None = None
    for row in visible_rows:
        ev = row.Event
        ep = row.Episode
        payload = ev.payload or {}
        codigo, titulo = tarea_map.get(ep.problema_id, (None, None))
        reflections.append(
            ReflectionEntryOut(
                episode_id=str(ep.id),
                problema_id=str(ep.problema_id),
                tarea_codigo=codigo,
                tarea_titulo=titulo,
                closed_at=ep.closed_at.isoformat().replace("+00:00", "Z") if ep.closed_at else None,
                reflected_at=ev.ts.isoformat().replace("+00:00", "Z"),
                prompt_version=str(payload.get("prompt_version", "reflection/v1.0.0")),
                tiempo_completado_ms=int(payload.get("tiempo_completado_ms", 0)),
                answers=ReflectionAnswers(
                    que_aprendiste=str(payload.get("que_aprendiste", "")),
                    dificultad_encontrada=str(payload.get("dificultad_encontrada", "")),
                    que_haria_distinto=str(payload.get("que_haria_distinto", "")),
                ),
            )
        )
        last_ts = ev.ts

    cursor_next = None
    if has_more and last_ts is not None:
        cursor_next = last_ts.isoformat().replace("+00:00", "Z")

    logger.info(
        "my_reflections_listed tenant_id=%s user_id=%s n_returned=%d has_more=%s",
        tenant_id,
        user_id,
        len(reflections),
        has_more,
    )

    return MyReflectionsResponse(
        student_pseudonym=str(user_id),
        n_returned=len(reflections),
        has_more=has_more,
        cursor_next=cursor_next,
        reflections=reflections,
    )
