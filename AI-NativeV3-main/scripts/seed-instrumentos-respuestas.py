"""Seed determinista de respuestas placeholder para los 3 instrumentos research.

Para que sirve
--------------
Crea respuestas de los 18 estudiantes del seed-3-comisiones a los 3 instrumentos
del diseno cuasi-experimental (P2-1 pretest autoeficacia, P2-2 cuestionario IA
previa, P2-3 test transferencia). Sirve para que el dashboard del web-teacher
muestre agregados reales (con N>=5 por comision, suficiente para pasar el
k-anonymity gate MIN_STUDENTS_FOR_COHORT_SUMMARY=5) sin tener que esperar a
que estudiantes reales completen los formularios.

ADR de respaldo: ADR-053.

Precondiciones
--------------
- Migracion 20260517_0001_instrumentos_research aplicada (3 tablas creadas).
- Seed seed-3-comisiones ejecutado previamente (provee comisiones + students).

Ejecucion
---------
    python scripts/seed-instrumentos-respuestas.py

Con env vars custom:
    ACADEMIC_DB_URL=... python scripts/seed-instrumentos-respuestas.py

Idempotencia
------------
INSERT ... ON CONFLICT DO NOTHING — re-correr es seguro. Para borrar y
re-insertar (ej. tras bumpear instrument_version), correr manualmente:
    DELETE FROM respuestas_cuestionario_ia WHERE tenant_id = '...';
    DELETE FROM respuestas_pretest_autoeficacia WHERE tenant_id = '...';
    DELETE FROM respuestas_test_transferencia WHERE tenant_id = '...';
"""

from __future__ import annotations

import asyncio
import json
import os
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

# ---------------------------------------------------------------------
# Constantes del piloto (deben coincidir con seed-3-comisiones.py)
# ---------------------------------------------------------------------

TENANT_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")

COMISIONES: list[dict] = [
    {
        "comision_id": UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        "codigo": "A",
        "students": [UUID(f"b1b1b1b1-000{i}-000{i}-000{i}-00000000000{i}") for i in range(1, 7)],
    },
    {
        "comision_id": UUID("bbbb0002-bbbb-bbbb-bbbb-bbbbbbbb0002"),
        "codigo": "B",
        "students": [UUID(f"b2b2b2b2-000{i}-000{i}-000{i}-00000000000{i}") for i in range(1, 7)],
    },
    {
        "comision_id": UUID("cccc0003-cccc-cccc-cccc-cccccccc0003"),
        "codigo": "C",
        "students": [UUID(f"b3b3b3b3-000{i}-000{i}-000{i}-00000000000{i}") for i in range(1, 7)],
    },
]

CUESTIONARIO_IA_VERSION = "cuestionario-ia-v0.1.0-draft"
PRETEST_VERSION = "lishinski-2016-es-utn-v0.1.0-draft"
TRANSFER_VERSION = "transfer-test-v0.1.0-draft"

# IDs de los 3 problemas placeholder del catalogo (instrumentos_content.py)
TRANSFER_TEST_IDS = ["transfer-01", "transfer-02", "transfer-03"]


# ---------------------------------------------------------------------
# Generadores de respuestas placeholder variadas por estudiante
# ---------------------------------------------------------------------


def cuestionario_ia_response_for(student_idx: int) -> dict:
    """Respuesta variada al cuestionario IA segun student_idx (0-5)."""
    uso_options = ["Nunca", "<1 mes", "1-6 meses", "6-12 meses", ">12 meses"]
    freq_options = ["Nunca", "Mensual", "Semanal", "Diario", "Multiples veces al dia"]
    delegacion_options = ["Nunca", "Pocas veces", "A veces", "Frecuentemente", "Casi siempre"]
    return {
        "uso_general_meses": uso_options[student_idx % len(uso_options)],
        "frecuencia_uso": freq_options[(student_idx + 1) % len(freq_options)],
        "tipos_tarea": (
            ["Generar codigo desde cero", "Depurar errores"]
            if student_idx % 2 == 0
            else ["Entender codigo ajeno", "Aprender conceptos nuevos"]
        ),
        "autopercepcion_dependencia": (student_idx % 5) + 1,  # 1-5
        "episodios_delegacion_previos": delegacion_options[student_idx % len(delegacion_options)],
        "verificacion_critica": ((student_idx + 2) % 5) + 1,  # 1-5
    }


def pretest_response_for(student_idx: int) -> tuple[dict, int, dict]:
    """Respuesta + total_score + subscale_scores al pretest segun student_idx (0-5).

    Likert 1-7. Cada estudiante tiene un nivel base (1-7) que aplica a todos los items
    con +/- 1 de variacion segun subscale.
    """
    base = ((student_idx % 7) + 1)  # 1-7
    items = [
        ("ind_01", base),
        ("ind_02", min(7, base + 1)),
        ("ind_03", base),
        ("comp_01", max(1, base - 1)),
        ("comp_02", base),
        ("comp_03", max(1, base - 1)),
        ("apr_01", min(7, base + 1)),
        ("apr_02", base),
        ("apr_03", min(7, base + 1)),
        ("per_01", base),
        ("per_02", min(7, base + 1)),
        ("per_03", base),
    ]
    responses = dict(items)
    total = sum(responses.values())
    # Promedios por sub-escala
    subscale_scores: dict = {
        "independencia": round((responses["ind_01"] + responses["ind_02"] + responses["ind_03"]) / 3, 2),
        "complejidad": round((responses["comp_01"] + responses["comp_02"] + responses["comp_03"]) / 3, 2),
        "aprendizaje": round((responses["apr_01"] + responses["apr_02"] + responses["apr_03"]) / 3, 2),
        "persistencia": round((responses["per_01"] + responses["per_02"] + responses["per_03"]) / 3, 2),
    }
    return responses, total, subscale_scores


def transfer_response_for(student_idx: int, test_id: str) -> tuple[bool, int, dict]:
    """Respuesta a un problema de transferencia.

    correct_answer: como instrumentos_content.evaluate_test_transferencia_answer
    devuelve False por default (placeholder hasta que catedra apruebe patrones),
    aca tambien devolvemos False — el seed refleja el estado de la evaluacion
    automatica vigente. Cuando la catedra apruebe patrones, este seed deberia
    bumpearse.

    time_taken_seconds: 60-300 segundos segun student_idx + test_id.
    """
    test_offset = {"transfer-01": 0, "transfer-02": 60, "transfer-03": 30}.get(test_id, 0)
    time_taken = 60 + (student_idx * 40) + test_offset  # 60-300
    return (
        False,  # placeholder — evaluacion automatica deferida
        time_taken,
        {
            "answer": f"# Respuesta placeholder de estudiante {student_idx + 1} a {test_id}\n"
                       f"def solucion(...): ...  # TODO contenido real cuando catedra apruebe",
            "submitted_via": "seed-instrumentos-respuestas.py",
        },
    )


# ---------------------------------------------------------------------
# Inserts
# ---------------------------------------------------------------------


SQL_INSERT_CUESTIONARIO_IA = text(
    """
    INSERT INTO respuestas_cuestionario_ia
        (tenant_id, comision_id, student_pseudonym, instrument_version, responses,
         submitted_at, created_at)
    VALUES (:tenant_id, :comision_id, :student_pseudonym, :instrument_version,
            CAST(:responses AS JSONB), :submitted_at, :created_at)
    ON CONFLICT (tenant_id, comision_id, student_pseudonym, instrument_version)
    DO NOTHING
    """
)

SQL_INSERT_PRETEST = text(
    """
    INSERT INTO respuestas_pretest_autoeficacia
        (tenant_id, comision_id, student_pseudonym, instrument_version, responses,
         total_score, subscale_scores, submitted_at, created_at)
    VALUES (:tenant_id, :comision_id, :student_pseudonym, :instrument_version,
            CAST(:responses AS JSONB), :total_score, CAST(:subscale_scores AS JSONB),
            :submitted_at, :created_at)
    ON CONFLICT (tenant_id, comision_id, student_pseudonym, instrument_version)
    DO NOTHING
    """
)

SQL_INSERT_TRANSFER = text(
    """
    INSERT INTO respuestas_test_transferencia
        (tenant_id, comision_id, student_pseudonym, instrument_version,
         group_assignment, test_id, correct_answer, time_taken_seconds,
         response_detail, submitted_at, created_at)
    VALUES (:tenant_id, :comision_id, :student_pseudonym, :instrument_version,
            :group_assignment, :test_id, :correct_answer, :time_taken_seconds,
            CAST(:response_detail AS JSONB), :submitted_at, :created_at)
    ON CONFLICT (tenant_id, comision_id, student_pseudonym, test_id, instrument_version)
    DO NOTHING
    """
)


async def seed() -> None:
    db_url = os.environ.get(
        "ACADEMIC_DB_URL",
        "postgresql+asyncpg://academic_user:academic_pass@127.0.0.1:5432/academic_main",
    )
    engine = create_async_engine(db_url, echo=False)
    now = datetime.now(UTC)

    total_cuestionario = 0
    total_pretest = 0
    total_transfer = 0

    async with engine.begin() as conn:
        for comision in COMISIONES:
            # Setear tenant_id para que la RLS policy permita los INSERTs
            await conn.execute(
                text("SET LOCAL app.current_tenant = :tenant_id"),
                {"tenant_id": str(TENANT_ID)},
            )
            for student_idx, student_pseudonym in enumerate(comision["students"]):
                # 1. Cuestionario IA
                cuestionario_responses = cuestionario_ia_response_for(student_idx)
                result = await conn.execute(
                    SQL_INSERT_CUESTIONARIO_IA,
                    {
                        "tenant_id": str(TENANT_ID),
                        "comision_id": str(comision["comision_id"]),
                        "student_pseudonym": str(student_pseudonym),
                        "instrument_version": CUESTIONARIO_IA_VERSION,
                        "responses": json.dumps(cuestionario_responses),
                        "submitted_at": now,
                        "created_at": now,
                    },
                )
                total_cuestionario += result.rowcount or 0

                # 2. Pretest autoeficacia
                responses, total_score, subscale_scores = pretest_response_for(student_idx)
                result = await conn.execute(
                    SQL_INSERT_PRETEST,
                    {
                        "tenant_id": str(TENANT_ID),
                        "comision_id": str(comision["comision_id"]),
                        "student_pseudonym": str(student_pseudonym),
                        "instrument_version": PRETEST_VERSION,
                        "responses": json.dumps(responses),
                        "total_score": total_score,
                        "subscale_scores": json.dumps(subscale_scores),
                        "submitted_at": now,
                        "created_at": now,
                    },
                )
                total_pretest += result.rowcount or 0

                # 3. Transferencia: 3 problemas por estudiante (todos como
                # experimental porque seed-3-comisiones no modela grupo
                # de comparacion sin CTR)
                for test_id in TRANSFER_TEST_IDS:
                    correct, time_taken, response_detail = transfer_response_for(
                        student_idx, test_id
                    )
                    result = await conn.execute(
                        SQL_INSERT_TRANSFER,
                        {
                            "tenant_id": str(TENANT_ID),
                            "comision_id": str(comision["comision_id"]),
                            "student_pseudonym": str(student_pseudonym),
                            "instrument_version": TRANSFER_VERSION,
                            "group_assignment": "experimental",
                            "test_id": test_id,
                            "correct_answer": correct,
                            "time_taken_seconds": time_taken,
                            "response_detail": json.dumps(response_detail),
                            "submitted_at": now,
                            "created_at": now,
                        },
                    )
                    total_transfer += result.rowcount or 0

    await engine.dispose()

    print(f"Seed instrumentos completado para tenant {TENANT_ID}:")
    print(f"  - Cuestionario IA: {total_cuestionario} respuestas insertadas")
    print(f"  - Pretest autoeficacia: {total_pretest} respuestas insertadas")
    print(f"  - Test transferencia: {total_transfer} respuestas insertadas (3 problemas x 18 estudiantes = 54 esperadas en primer run)")
    print(f"  (0 = ya existian via ON CONFLICT DO NOTHING; re-correr el script no duplica)")


if __name__ == "__main__":
    asyncio.run(seed())
