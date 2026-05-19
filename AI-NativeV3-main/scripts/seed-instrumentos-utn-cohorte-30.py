"""Seed de respuestas de instrumentos para 18 de los 30 alumnos de UTN COM-1.

Para que se vea en el video:
- Cuestionario IA: 18 respuestas (de 30 alumnos)
- Pretest Autoeficacia: 18 respuestas
- Test Transferencia: 15 alumnos x 3 problemas = 45 entries

Hacer 18 (no 30) es mas realista para el escenario "alumnos opcionales que
respondieron en su tiempo libre". Supera k-anonymity (>=5) holgadamente.
"""

from __future__ import annotations

import asyncio
import json
import os
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

TENANT_UTN = UUID("7a7a143c-31f8-461b-be08-d86ac36b41a3")
COMISION_1 = UUID("7b18f4d8-24b7-4034-979e-1fd464939f0e")

# 18 de los 30 alumnos respondieron (los primeros 18, indices 1..18)
RESPONDIENTES_CUESTIONARIO = [
    UUID(f"c1c1c1c1-{i:04x}-{i:04x}-{i:04x}-{i:012x}") for i in range(1, 19)
]
RESPONDIENTES_PRETEST = [
    UUID(f"c1c1c1c1-{i:04x}-{i:04x}-{i:04x}-{i:012x}") for i in range(1, 19)
]
# 15 alumnos hicieron el test transferencia (mas exigente)
RESPONDIENTES_TRANSFER = [
    UUID(f"c1c1c1c1-{i:04x}-{i:04x}-{i:04x}-{i:012x}") for i in range(1, 16)
]

CUESTIONARIO_IA_VERSION = "cuestionario-ia-v0.1.0-draft"
PRETEST_VERSION = "lishinski-2016-es-utn-v0.1.0-draft"
TRANSFER_VERSION = "transfer-test-v0.1.0-draft"

TRANSFER_TEST_IDS = ["transfer-01", "transfer-02", "transfer-03"]


def cuestionario_ia_response_for(idx: int) -> dict:
    uso_options = ["Nunca", "<1 mes", "1-6 meses", "6-12 meses", ">12 meses"]
    freq_options = ["Nunca", "Mensual", "Semanal", "Diario", "Multiples veces al dia"]
    delegacion = ["Nunca", "Pocas veces", "A veces", "Frecuentemente", "Casi siempre"]
    return {
        "uso_general_meses": uso_options[idx % 5],
        "frecuencia_uso": freq_options[(idx + 1) % 5],
        "tipos_tarea": (
            ["Generar codigo desde cero", "Depurar errores"]
            if idx % 2 == 0
            else ["Entender codigo ajeno", "Aprender conceptos nuevos", "Refactor / optimizacion"]
        ),
        "autopercepcion_dependencia": (idx % 5) + 1,
        "episodios_delegacion_previos": delegacion[idx % 5],
        "verificacion_critica": ((idx + 2) % 5) + 1,
        "uso_no_programacion": freq_options[(idx + 2) % 5],
        "proyeccion_5_anos": ["Imposible — sera obligatoria", "Improbable", "Posible", "Probable — preferiria evitarla"][idx % 4],
    }


def pretest_response_for(idx: int) -> tuple[dict, int, dict]:
    base = (idx % 7) + 1  # 1..7
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
    subs = {
        "independencia": round((responses["ind_01"] + responses["ind_02"] + responses["ind_03"]) / 3, 2),
        "complejidad": round((responses["comp_01"] + responses["comp_02"] + responses["comp_03"]) / 3, 2),
        "aprendizaje": round((responses["apr_01"] + responses["apr_02"] + responses["apr_03"]) / 3, 2),
        "persistencia": round((responses["per_01"] + responses["per_02"] + responses["per_03"]) / 3, 2),
    }
    return responses, total, subs


def transfer_for(idx: int, test_id: str) -> tuple[bool, int, dict]:
    # 35% accuracy aprox (alumnos en mitad de curso, transfer es exigente)
    correct = (idx + hash(test_id)) % 100 < 35
    test_offset = {"transfer-01": 0, "transfer-02": 60, "transfer-03": 30}.get(test_id, 0)
    time_taken = 90 + (idx * 30) + test_offset  # 90-360s
    return correct, time_taken, {
        "answer": f"def solucion(...):  # alumno {idx + 1} para {test_id}\n    return None",
        "submitted_via": "seed-utn-instrumentos",
    }


async def main() -> None:
    academic_url = os.environ.get(
        "ACADEMIC_DB_URL",
        "postgresql+asyncpg://postgres:postgres@localhost:5432/academic_main",
    )
    engine = create_async_engine(academic_url, pool_size=2)
    now = datetime.now(UTC)

    try:
        async with engine.begin() as conn:
            await conn.execute(text("SET row_security = off"))

            # Limpieza previa
            await conn.execute(
                text(
                    "DELETE FROM respuestas_cuestionario_ia "
                    "WHERE tenant_id = :t AND comision_id = :c "
                    "AND student_pseudonym::text LIKE 'c1c1c1c1-%'"
                ),
                {"t": str(TENANT_UTN), "c": str(COMISION_1)},
            )
            await conn.execute(
                text(
                    "DELETE FROM respuestas_pretest_autoeficacia "
                    "WHERE tenant_id = :t AND comision_id = :c "
                    "AND student_pseudonym::text LIKE 'c1c1c1c1-%'"
                ),
                {"t": str(TENANT_UTN), "c": str(COMISION_1)},
            )
            await conn.execute(
                text(
                    "DELETE FROM respuestas_test_transferencia "
                    "WHERE tenant_id = :t AND comision_id = :c "
                    "AND student_pseudonym::text LIKE 'c1c1c1c1-%'"
                ),
                {"t": str(TENANT_UTN), "c": str(COMISION_1)},
            )

            # Cuestionario IA
            for idx, pseudo in enumerate(RESPONDIENTES_CUESTIONARIO):
                resp = cuestionario_ia_response_for(idx)
                submitted = now - timedelta(days=20 - idx % 10, hours=idx % 24)
                await conn.execute(
                    text(
                        "INSERT INTO respuestas_cuestionario_ia "
                        "(tenant_id, comision_id, student_pseudonym, instrument_version, "
                        " responses, submitted_at, created_at) "
                        "VALUES (:t, :c, :s, :v, CAST(:r AS JSONB), :sub, :cr)"
                    ),
                    {
                        "t": str(TENANT_UTN),
                        "c": str(COMISION_1),
                        "s": str(pseudo),
                        "v": CUESTIONARIO_IA_VERSION,
                        "r": json.dumps(resp),
                        "sub": submitted,
                        "cr": submitted,
                    },
                )

            # Pretest
            for idx, pseudo in enumerate(RESPONDIENTES_PRETEST):
                responses, total, subs = pretest_response_for(idx)
                submitted = now - timedelta(days=18 - idx % 8, hours=(idx + 2) % 24)
                await conn.execute(
                    text(
                        "INSERT INTO respuestas_pretest_autoeficacia "
                        "(tenant_id, comision_id, student_pseudonym, instrument_version, "
                        " responses, total_score, subscale_scores, submitted_at, created_at) "
                        "VALUES (:t, :c, :s, :v, CAST(:r AS JSONB), :tot, CAST(:sub_s AS JSONB), :sub, :cr)"
                    ),
                    {
                        "t": str(TENANT_UTN),
                        "c": str(COMISION_1),
                        "s": str(pseudo),
                        "v": PRETEST_VERSION,
                        "r": json.dumps(responses),
                        "tot": total,
                        "sub_s": json.dumps(subs),
                        "sub": submitted,
                        "cr": submitted,
                    },
                )

            # Test Transferencia: 15 alumnos x 3 tests
            for idx, pseudo in enumerate(RESPONDIENTES_TRANSFER):
                for test_id in TRANSFER_TEST_IDS:
                    correct, time_taken, detail = transfer_for(idx, test_id)
                    submitted = now - timedelta(days=10 - idx % 5, hours=(idx + 3) % 24)
                    # group_assignment alterna experimental/comparison
                    group = "experimental" if idx % 2 == 0 else "comparison"
                    await conn.execute(
                        text(
                            "INSERT INTO respuestas_test_transferencia "
                            "(tenant_id, comision_id, student_pseudonym, instrument_version, "
                            " group_assignment, test_id, correct_answer, time_taken_seconds, "
                            " response_detail, submitted_at, created_at) "
                            "VALUES (:t, :c, :s, :v, :g, :tid, :ok, :tt, "
                            "        CAST(:d AS JSONB), :sub, :cr)"
                        ),
                        {
                            "t": str(TENANT_UTN),
                            "c": str(COMISION_1),
                            "s": str(pseudo),
                            "v": TRANSFER_VERSION,
                            "g": group,
                            "tid": test_id,
                            "ok": correct,
                            "tt": time_taken,
                            "d": json.dumps(detail),
                            "sub": submitted,
                            "cr": submitted,
                        },
                    )

        print(f"[OK] {len(RESPONDIENTES_CUESTIONARIO)} respuestas Cuestionario IA")
        print(f"[OK] {len(RESPONDIENTES_PRETEST)} respuestas Pretest Autoeficacia")
        print(f"[OK] {len(RESPONDIENTES_TRANSFER) * 3} respuestas Test Transferencia (15 alumnos x 3)")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
