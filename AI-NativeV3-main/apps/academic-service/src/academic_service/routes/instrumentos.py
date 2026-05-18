"""Endpoints de los 3 instrumentos del diseño cuasi-experimental.

Cierran P2-1, P2-2, P2-3 del PlanMejora.md (esqueleto tecnico).

Estructura:
- /api/v1/instrumentos/cuestionario-ia   (P2-2)
    - POST           — estudiante registra respuesta (idempotente por version)
    - GET /me        — estudiante consulta su propia respuesta vigente
    - GET /catalogo  — frontend obtiene items para renderizar form
- /api/v1/instrumentos/pretest-autoeficacia  (P2-1)
    - POST, GET /me, GET /catalogo
- /api/v1/instrumentos/transferencia  (P2-3)
    - POST           — estudiante envia respuesta a un test_id
    - GET /me        — lista intentos del estudiante
    - GET /catalogo  — lista los 3-5 problemas

Las lecturas agregadas (por cohorte, con k-anonymity gate) viven en el
`analytics-service` para no acoplar academic-service a logica analitica.

ADR de respaldo: ADR-053 + ADR-001 (RLS) + invariante MIN_STUDENTS_FOR_QUARTILES=5.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import Integer, case, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from academic_service.auth import User, get_db, require_permission
from academic_service.models.instrumentos import (
    RespuestaCuestionarioIA,
    RespuestaPretestAutoeficacia,
    RespuestaTestTransferencia,
)
from academic_service.schemas.instrumentos import (
    CuestionarioIACreate,
    CuestionarioIAOut,
    PretestAutoeficaciaCreate,
    PretestAutoeficaciaOut,
    TestTransferenciaCreate,
    TestTransferenciaOut,
)
from academic_service.services.instrumentos_content import (
    CUESTIONARIO_IA_ITEMS,
    PRETEST_AUTOEFICACIA_ITEMS,
    TEST_TRANSFERENCIA_PROBLEMS,
    compute_pretest_autoeficacia_scores,
    evaluate_test_transferencia_answer,
    get_test_by_id,
    validate_cuestionario_ia_responses,
    validate_pretest_autoeficacia_responses,
)


# ============================================================================
# CUESTIONARIO IA (P2-2)
# ============================================================================

cuestionario_ia_router = APIRouter(
    prefix="/api/v1/instrumentos/cuestionario-ia", tags=["instrumentos"]
)


@cuestionario_ia_router.get("/catalogo")
async def get_cuestionario_ia_catalogo(
    user: User = Depends(require_permission("instrumento_cuestionario_ia", "read")),
) -> dict[str, Any]:
    """Devuelve catalogo de items del cuestionario para renderizar form.

    El catalogo es publico para cualquier usuario autenticado del tenant.
    Version y items vienen embedded — el frontend NO necesita versionar.
    """
    _ = user
    return {
        "instrument_version": "cuestionario-ia-v0.1.0-draft",
        "items": CUESTIONARIO_IA_ITEMS,
        "draft_notice": (
            "Este instrumento esta en estado DRAFT pendiente de validacion "
            "coautoral (Ana Garis) + aprobacion comite etico UNSL. Los items "
            "actuales son placeholders para validar el flujo backend + frontend "
            "end-to-end."
        ),
    }


@cuestionario_ia_router.post(
    "",
    response_model=CuestionarioIAOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_cuestionario_ia(
    data: CuestionarioIACreate,
    user: User = Depends(require_permission("instrumento_cuestionario_ia", "create")),
    db: AsyncSession = Depends(get_db),
) -> CuestionarioIAOut:
    """Estudiante registra su respuesta al cuestionario IA.

    Idempotente por (tenant, comision, student, version): si ya existe una
    respuesta para esta combinacion, devuelve 409 Conflict en lugar de duplicar.
    """
    # Validar contenido de respuestas contra catalogo
    errors = validate_cuestionario_ia_responses(data.responses)
    if errors:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"validation_errors": errors},
        )

    obj = RespuestaCuestionarioIA(
        tenant_id=user.tenant_id,
        comision_id=data.comision_id,
        student_pseudonym=data.student_pseudonym,
        instrument_version=data.instrument_version,
        responses=data.responses,
    )
    db.add(obj)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Ya existe una respuesta para este estudiante en esta version del "
                "instrumento. Si necesitas re-responder, bumpear instrument_version."
            ),
        ) from exc
    await db.refresh(obj)
    return CuestionarioIAOut.model_validate(obj)


@cuestionario_ia_router.get("/me", response_model=CuestionarioIAOut | None)
async def get_my_cuestionario_ia(
    comision_id: UUID,
    instrument_version: str = "cuestionario-ia-v0.1.0-draft",
    user: User = Depends(require_permission("instrumento_cuestionario_ia", "read")),
    db: AsyncSession = Depends(get_db),
) -> CuestionarioIAOut | None:
    """Estudiante consulta su propia respuesta vigente.

    El `student_pseudonym` viene del User autenticado para evitar que un
    estudiante consulte la respuesta de otro (defensa en profundidad ademas de RLS).
    """
    stmt = select(RespuestaCuestionarioIA).where(
        RespuestaCuestionarioIA.tenant_id == user.tenant_id,
        RespuestaCuestionarioIA.comision_id == comision_id,
        RespuestaCuestionarioIA.student_pseudonym == user.id,
        RespuestaCuestionarioIA.instrument_version == instrument_version,
    )
    result = await db.execute(stmt)
    obj = result.scalar_one_or_none()
    return CuestionarioIAOut.model_validate(obj) if obj else None


# ============================================================================
# PRETEST AUTOEFICACIA (P2-1)
# ============================================================================

pretest_router = APIRouter(
    prefix="/api/v1/instrumentos/pretest-autoeficacia", tags=["instrumentos"]
)


@pretest_router.get("/catalogo")
async def get_pretest_catalogo(
    user: User = Depends(require_permission("instrumento_pretest_autoeficacia", "read")),
) -> dict[str, Any]:
    """Devuelve catalogo de items del pretest para renderizar form Likert 1-7."""
    _ = user
    return {
        "instrument_version": "lishinski-2016-es-utn-v0.1.0-draft",
        "items": PRETEST_AUTOEFICACIA_ITEMS,
        "scale": {"min": 1, "max": 7, "type": "likert"},
        "draft_notice": (
            "Pretest basado en Lishinski et al. (2016) CS Self-Efficacy Scale, "
            "adaptacion al castellano rioplatense v0.1.0-draft. Items pendientes "
            "de revision coautoral (Garis) + comite etico UNSL. La adaptacion "
            "completa son 28 items; este draft expone 12 para validar el flujo "
            "end-to-end."
        ),
    }


@pretest_router.post(
    "",
    response_model=PretestAutoeficaciaOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_pretest_autoeficacia(
    data: PretestAutoeficaciaCreate,
    user: User = Depends(require_permission("instrumento_pretest_autoeficacia", "create")),
    db: AsyncSession = Depends(get_db),
) -> PretestAutoeficaciaOut:
    """Estudiante registra respuesta al pretest. Calcula scores server-side."""
    errors = validate_pretest_autoeficacia_responses(data.responses)
    if errors:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"validation_errors": errors},
        )

    total_score, subscale_scores = compute_pretest_autoeficacia_scores(data.responses)

    obj = RespuestaPretestAutoeficacia(
        tenant_id=user.tenant_id,
        comision_id=data.comision_id,
        student_pseudonym=data.student_pseudonym,
        instrument_version=data.instrument_version,
        responses=data.responses,
        total_score=total_score,
        subscale_scores=subscale_scores,
    )
    db.add(obj)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Ya existe una respuesta para este estudiante en esta version del "
                "pretest. Si necesitas re-responder, bumpear instrument_version."
            ),
        ) from exc
    await db.refresh(obj)
    return PretestAutoeficaciaOut.model_validate(obj)


@pretest_router.get("/me", response_model=PretestAutoeficaciaOut | None)
async def get_my_pretest_autoeficacia(
    comision_id: UUID,
    instrument_version: str = "lishinski-2016-es-utn-v0.1.0-draft",
    user: User = Depends(require_permission("instrumento_pretest_autoeficacia", "read")),
    db: AsyncSession = Depends(get_db),
) -> PretestAutoeficaciaOut | None:
    """Estudiante consulta su propia respuesta vigente al pretest."""
    stmt = select(RespuestaPretestAutoeficacia).where(
        RespuestaPretestAutoeficacia.tenant_id == user.tenant_id,
        RespuestaPretestAutoeficacia.comision_id == comision_id,
        RespuestaPretestAutoeficacia.student_pseudonym == user.id,
        RespuestaPretestAutoeficacia.instrument_version == instrument_version,
    )
    result = await db.execute(stmt)
    obj = result.scalar_one_or_none()
    return PretestAutoeficaciaOut.model_validate(obj) if obj else None


# ============================================================================
# TEST DE TRANSFERENCIA (P2-3)
# ============================================================================

transferencia_router = APIRouter(
    prefix="/api/v1/instrumentos/transferencia", tags=["instrumentos"]
)


@transferencia_router.get("/catalogo")
async def get_transferencia_catalogo(
    user: User = Depends(require_permission("instrumento_test_transferencia", "read")),
) -> dict[str, Any]:
    """Devuelve catalogo de problemas de transferencia para renderizar."""
    _ = user
    # Sanitizar: NO devolvemos `expected_solution_pattern` ni `expected_answer`
    # al cliente para no filtrar la solucion. El estudiante recibe solo el enunciado.
    sanitized = [
        {k: v for k, v in problem.items() if k not in {"expected_solution_pattern", "expected_answer"}}
        for problem in TEST_TRANSFERENCIA_PROBLEMS
    ]
    return {
        "instrument_version": "transfer-test-v0.1.0-draft",
        "problems": sanitized,
        "draft_notice": (
            "Test de transferencia v0.1.0-draft. Contenido pendiente de validacion "
            "por catedra UNSL. Esqueleto con 3 problemas placeholder para validar "
            "flujo end-to-end; el set final son 5 problemas (ver "
            "docs/research/diseno-test-transfer.md)."
        ),
    }


@transferencia_router.post(
    "",
    response_model=TestTransferenciaOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_test_transferencia(
    data: TestTransferenciaCreate,
    user: User = Depends(require_permission("instrumento_test_transferencia", "create")),
    db: AsyncSession = Depends(get_db),
) -> TestTransferenciaOut:
    """Estudiante envia respuesta a un problema del test de transferencia.

    Aplica al grupo experimental y al grupo de comparacion. Server-side
    evalua si la respuesta es correcta contra la solucion canonica.

    Idempotente por (tenant, comision, student, test_id, version): cada
    problema se responde una sola vez por estudiante por version del test.
    """
    # Validar que el test_id existe en el catalogo
    test_def = get_test_by_id(data.test_id)
    if not test_def:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"test_id desconocido: {data.test_id}",
        )

    # Evaluar correctitud server-side (placeholder hasta que catedra apruebe)
    correct = evaluate_test_transferencia_answer(data.test_id, data.response_detail)

    obj = RespuestaTestTransferencia(
        tenant_id=user.tenant_id,
        comision_id=data.comision_id,
        student_pseudonym=data.student_pseudonym,
        instrument_version=data.instrument_version,
        group_assignment=data.group_assignment,
        test_id=data.test_id,
        correct_answer=correct,
        time_taken_seconds=data.time_taken_seconds,
        response_detail=data.response_detail,
    )
    db.add(obj)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Ya existe una respuesta de este estudiante para este test_id en "
                "esta version. Si la catedra autoriza re-intento, bumpear instrument_version."
            ),
        ) from exc
    await db.refresh(obj)
    return TestTransferenciaOut.model_validate(obj)


@transferencia_router.get("/me", response_model=list[TestTransferenciaOut])
async def list_my_transferencia(
    comision_id: UUID,
    instrument_version: str = "transfer-test-v0.1.0-draft",
    user: User = Depends(require_permission("instrumento_test_transferencia", "read")),
    db: AsyncSession = Depends(get_db),
) -> list[TestTransferenciaOut]:
    """Estudiante lista sus intentos del test de transferencia (puede haber varios test_id)."""
    stmt = (
        select(RespuestaTestTransferencia)
        .where(
            RespuestaTestTransferencia.tenant_id == user.tenant_id,
            RespuestaTestTransferencia.comision_id == comision_id,
            RespuestaTestTransferencia.student_pseudonym == user.id,
            RespuestaTestTransferencia.instrument_version == instrument_version,
        )
        .order_by(RespuestaTestTransferencia.submitted_at.asc())
    )
    result = await db.execute(stmt)
    objs = result.scalars().all()
    return [TestTransferenciaOut.model_validate(o) for o in objs]


# ============================================================================
# COHORT SUMMARY ENDPOINTS (docente / docente_admin)
# Aplican gate de k-anonymity: si N de estudiantes con respuesta < umbral,
# devuelven `insufficient_data: true` y degradan gracilmente.
# ============================================================================

# Mismo umbral que cii_alerts (RN-131): no exponer distribuciones sobre
# cohortes <5 estudiantes para prevenir reidentificacion individual.
MIN_STUDENTS_FOR_COHORT_SUMMARY = 5


@cuestionario_ia_router.get("/{comision_id}/summary")
async def get_cuestionario_ia_cohort_summary(
    comision_id: UUID,
    instrument_version: str = "cuestionario-ia-v0.1.0-draft",
    user: User = Depends(require_permission("instrumento_cuestionario_ia", "read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Agregado anonimizado por cohorte del cuestionario IA previa.

    K-anonymity gate: si N < 5 estudiantes con respuesta, devuelve
    `insufficient_data: true` sin exponer distribuciones.

    Esta version v0.1.0 devuelve unicamente conteo total de respondientes
    + porcentaje de cobertura sobre la cohorte. Analisis por item con
    distribuciones llega en una version posterior cuando el catalogo de
    items este validado coautoralmente.
    """
    # Contar estudiantes con respuesta vigente
    stmt = select(func.count(RespuestaCuestionarioIA.id)).where(
        RespuestaCuestionarioIA.tenant_id == user.tenant_id,
        RespuestaCuestionarioIA.comision_id == comision_id,
        RespuestaCuestionarioIA.instrument_version == instrument_version,
    )
    n_responses = (await db.execute(stmt)).scalar_one()
    if n_responses < MIN_STUDENTS_FOR_COHORT_SUMMARY:
        return {
            "insufficient_data": True,
            "n_responses": n_responses,
            "k_anonymity_threshold": MIN_STUDENTS_FOR_COHORT_SUMMARY,
            "message": (
                f"Cohorte tiene {n_responses} respondiente(s); se requieren "
                f"al menos {MIN_STUDENTS_FOR_COHORT_SUMMARY} para exponer "
                "distribuciones (k-anonymity, paper §7.3 principio 1 + RN-131)."
            ),
        }
    return {
        "insufficient_data": False,
        "n_responses": n_responses,
        "instrument_version": instrument_version,
        "k_anonymity_threshold": MIN_STUDENTS_FOR_COHORT_SUMMARY,
        # Analisis por item DEFERIDO hasta validacion coautoral del catalogo
        # — no exponer distribuciones de items que pueden cambiar.
        "by_item_distribution_status": "deferred_pending_validation",
    }


@pretest_router.get("/{comision_id}/summary")
async def get_pretest_cohort_summary(
    comision_id: UUID,
    instrument_version: str = "lishinski-2016-es-utn-v0.1.0-draft",
    user: User = Depends(require_permission("instrumento_pretest_autoeficacia", "read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Agregado anonimizado por cohorte del pretest autoeficacia.

    K-anonymity gate identico al cuestionario IA. Cuando hay >=5 respuestas,
    expone score promedio + score promedio por sub-escala. No expone scores
    individuales bajo ninguna circunstancia.
    """
    stmt = select(
        func.count(RespuestaPretestAutoeficacia.id),
        func.avg(RespuestaPretestAutoeficacia.total_score),
    ).where(
        RespuestaPretestAutoeficacia.tenant_id == user.tenant_id,
        RespuestaPretestAutoeficacia.comision_id == comision_id,
        RespuestaPretestAutoeficacia.instrument_version == instrument_version,
    )
    row = (await db.execute(stmt)).one()
    n_responses, avg_total = row[0], row[1]
    if n_responses < MIN_STUDENTS_FOR_COHORT_SUMMARY:
        return {
            "insufficient_data": True,
            "n_responses": n_responses,
            "k_anonymity_threshold": MIN_STUDENTS_FOR_COHORT_SUMMARY,
            "message": (
                f"Cohorte tiene {n_responses} respondiente(s); se requieren "
                f"al menos {MIN_STUDENTS_FOR_COHORT_SUMMARY} para exponer "
                "scores agregados (k-anonymity)."
            ),
        }
    return {
        "insufficient_data": False,
        "n_responses": n_responses,
        "instrument_version": instrument_version,
        "k_anonymity_threshold": MIN_STUDENTS_FOR_COHORT_SUMMARY,
        "avg_total_score": float(avg_total) if avg_total is not None else None,
        # Subscale aggregation deferida hasta confirmar formula scoring final
        # con Garis (compute_pretest_autoeficacia_scores es v0.1.0-draft).
        "subscale_aggregation_status": "deferred_pending_validation",
    }


@transferencia_router.get("/{comision_id}/summary")
async def get_transferencia_cohort_summary(
    comision_id: UUID,
    instrument_version: str = "transfer-test-v0.1.0-draft",
    user: User = Depends(require_permission("instrumento_test_transferencia", "read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Agregado del test de transferencia por cohorte y grupo (experimental vs comparison).

    K-anonymity gate aplicado POR GRUPO: cada grupo necesita >=5 respondientes
    para que se expongan sus metricas. Si experimental tiene 8 y comparison
    tiene 3, solo experimental expone metricas; comparison reporta
    insufficient_data y queda fuera de la comparacion en este reporte.
    """
    # Conteo de estudiantes UNICOS por grupo (no respuestas — un estudiante
    # puede tener varios test_id, pero cuenta como 1 estudiante).
    stmt = select(
        RespuestaTestTransferencia.group_assignment,
        func.count(func.distinct(RespuestaTestTransferencia.student_pseudonym)).label(
            "n_students"
        ),
        func.count(RespuestaTestTransferencia.id).label("n_attempts"),
        func.sum(
            case((RespuestaTestTransferencia.correct_answer.is_(True), 1), else_=0).cast(
                Integer
            )
        ).label("n_correct"),
    ).where(
        RespuestaTestTransferencia.tenant_id == user.tenant_id,
        RespuestaTestTransferencia.comision_id == comision_id,
        RespuestaTestTransferencia.instrument_version == instrument_version,
    ).group_by(RespuestaTestTransferencia.group_assignment)
    rows = (await db.execute(stmt)).all()

    by_group: dict[str, dict[str, Any]] = {}
    for row in rows:
        group, n_students, n_attempts, n_correct = (
            row.group_assignment,
            row.n_students,
            row.n_attempts,
            row.n_correct or 0,
        )
        if n_students < MIN_STUDENTS_FOR_COHORT_SUMMARY:
            by_group[group] = {
                "insufficient_data": True,
                "n_students": n_students,
                "k_anonymity_threshold": MIN_STUDENTS_FOR_COHORT_SUMMARY,
            }
        else:
            by_group[group] = {
                "insufficient_data": False,
                "n_students": n_students,
                "n_attempts": n_attempts,
                "n_correct": int(n_correct),
                "accuracy": round(int(n_correct) / n_attempts, 3) if n_attempts > 0 else 0.0,
            }
    return {
        "instrument_version": instrument_version,
        "k_anonymity_threshold": MIN_STUDENTS_FOR_COHORT_SUMMARY,
        "by_group": by_group,
    }
