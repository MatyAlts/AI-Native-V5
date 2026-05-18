"""Seeds de la matriz de permisos Casbin.

Se ejecuta una vez después de las migraciones iniciales. Idempotente.
La matriz replica la tabla del documento de arquitectura sección 6.2.

Uso:
    python -m academic_service.seeds.casbin_policies
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

# Permitir ejecutar como script desde la raíz del servicio
SRC = Path(__file__).parent.parent.parent
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

# Matriz de permisos (sujeto, recurso, acción)
# "sub" es role:<rol>. Casbin resuelve la pertenencia via g (role inheritance),
# pero para simplicidad F1 definimos las policies directamente sobre role:<nombre>.
# En F5 el matcher se extiende para verificar comisiones específicas.
POLICIES: list[tuple[str, str, str, str]] = [
    # ── Superadmin: todo ──────────────────────────────────────────────
    # (superadmin bypasa en check_permission, pero mantenemos policies
    # explícitas para documentación y para que el test de matriz pase)
    ("role:superadmin", "*", "universidad:*", "create"),
    ("role:superadmin", "*", "universidad:*", "read"),
    ("role:superadmin", "*", "universidad:*", "update"),
    ("role:superadmin", "*", "universidad:*", "delete"),
    ("role:superadmin", "*", "facultad:*", "create"),
    ("role:superadmin", "*", "facultad:*", "read"),
    ("role:superadmin", "*", "facultad:*", "update"),
    ("role:superadmin", "*", "facultad:*", "delete"),
    ("role:superadmin", "*", "carrera:*", "create"),
    ("role:superadmin", "*", "carrera:*", "read"),
    ("role:superadmin", "*", "carrera:*", "update"),
    ("role:superadmin", "*", "carrera:*", "delete"),
    ("role:superadmin", "*", "plan:*", "create"),
    ("role:superadmin", "*", "plan:*", "read"),
    ("role:superadmin", "*", "plan:*", "update"),
    ("role:superadmin", "*", "plan:*", "delete"),
    ("role:superadmin", "*", "materia:*", "create"),
    ("role:superadmin", "*", "materia:*", "read"),
    ("role:superadmin", "*", "materia:*", "update"),
    ("role:superadmin", "*", "materia:*", "delete"),
    ("role:superadmin", "*", "periodo:*", "create"),
    ("role:superadmin", "*", "periodo:*", "read"),
    ("role:superadmin", "*", "periodo:*", "update"),
    ("role:superadmin", "*", "periodo:*", "delete"),
    ("role:superadmin", "*", "comision:*", "create"),
    ("role:superadmin", "*", "comision:*", "read"),
    ("role:superadmin", "*", "comision:*", "update"),
    ("role:superadmin", "*", "comision:*", "delete"),
    ("role:superadmin", "*", "inscripcion:*", "create"),
    ("role:superadmin", "*", "inscripcion:*", "read"),
    ("role:superadmin", "*", "inscripcion:*", "update"),
    ("role:superadmin", "*", "inscripcion:*", "delete"),
    ("role:superadmin", "*", "usuario_comision:*", "create"),
    ("role:superadmin", "*", "usuario_comision:*", "read"),
    ("role:superadmin", "*", "usuario_comision:*", "update"),
    ("role:superadmin", "*", "usuario_comision:*", "delete"),
    ("role:superadmin", "*", "tarea_practica:*", "create"),
    ("role:superadmin", "*", "tarea_practica:*", "read"),
    ("role:superadmin", "*", "tarea_practica:*", "update"),
    ("role:superadmin", "*", "tarea_practica:*", "delete"),
    ("role:superadmin", "*", "tarea_practica_template:*", "create"),
    ("role:superadmin", "*", "tarea_practica_template:*", "read"),
    ("role:superadmin", "*", "tarea_practica_template:*", "update"),
    ("role:superadmin", "*", "tarea_practica_template:*", "delete"),
    # ADR-039 (Sec 7.7 epic ai-native-completion-and-byok): BYOK keys son
    # admin-only. La verificacion runtime vive en `apps/ai-gateway/.../routes/byok.py`
    # (header X-User-Roles) por simplicidad — agregamos las policies aca para que
    # la matriz documente quien deberia poder gestionarlas y prep para enforcement
    # via Casbin desde el api-gateway en una iteracion futura.
    ("role:superadmin", "*", "unidad:*", "create"),
    ("role:superadmin", "*", "unidad:*", "read"),
    ("role:superadmin", "*", "unidad:*", "update"),
    ("role:superadmin", "*", "unidad:*", "delete"),
    ("role:superadmin", "*", "byok_key:*", "create"),
    ("role:superadmin", "*", "byok_key:*", "read"),
    ("role:superadmin", "*", "byok_key:*", "update"),
    ("role:superadmin", "*", "byok_key:*", "delete"),
    ("role:superadmin", "*", "audit:*", "read"),
    # ── Docente admin: gestión institucional completa de su tenant ────
    # (dom "*" acá es metafórico — en F5 se filtra por tenant)
    ("role:docente_admin", "*", "universidad:*", "read"),
    ("role:docente_admin", "*", "universidad:*", "update"),  # solo la propia
    ("role:docente_admin", "*", "facultad:*", "create"),
    ("role:docente_admin", "*", "facultad:*", "read"),
    ("role:docente_admin", "*", "facultad:*", "update"),
    ("role:docente_admin", "*", "facultad:*", "delete"),
    ("role:docente_admin", "*", "carrera:*", "create"),
    ("role:docente_admin", "*", "carrera:*", "read"),
    ("role:docente_admin", "*", "carrera:*", "update"),
    ("role:docente_admin", "*", "carrera:*", "delete"),
    ("role:docente_admin", "*", "plan:*", "create"),
    ("role:docente_admin", "*", "plan:*", "read"),
    ("role:docente_admin", "*", "plan:*", "update"),
    ("role:docente_admin", "*", "plan:*", "delete"),
    ("role:docente_admin", "*", "materia:*", "create"),
    ("role:docente_admin", "*", "materia:*", "read"),
    ("role:docente_admin", "*", "materia:*", "update"),
    ("role:docente_admin", "*", "materia:*", "delete"),
    ("role:docente_admin", "*", "periodo:*", "create"),
    ("role:docente_admin", "*", "periodo:*", "read"),
    ("role:docente_admin", "*", "periodo:*", "update"),
    ("role:docente_admin", "*", "periodo:*", "delete"),
    ("role:docente_admin", "*", "comision:*", "create"),
    ("role:docente_admin", "*", "comision:*", "read"),
    ("role:docente_admin", "*", "comision:*", "update"),
    ("role:docente_admin", "*", "comision:*", "delete"),
    ("role:docente_admin", "*", "inscripcion:*", "create"),
    ("role:docente_admin", "*", "inscripcion:*", "read"),
    ("role:docente_admin", "*", "inscripcion:*", "update"),
    ("role:docente_admin", "*", "inscripcion:*", "delete"),
    ("role:docente_admin", "*", "usuario_comision:*", "create"),
    ("role:docente_admin", "*", "usuario_comision:*", "read"),
    ("role:docente_admin", "*", "usuario_comision:*", "update"),
    ("role:docente_admin", "*", "usuario_comision:*", "delete"),
    ("role:docente_admin", "*", "tarea_practica:*", "create"),
    ("role:docente_admin", "*", "tarea_practica:*", "read"),
    ("role:docente_admin", "*", "tarea_practica:*", "update"),
    ("role:docente_admin", "*", "tarea_practica:*", "delete"),
    ("role:docente_admin", "*", "tarea_practica_template:*", "create"),
    ("role:docente_admin", "*", "tarea_practica_template:*", "read"),
    ("role:docente_admin", "*", "tarea_practica_template:*", "update"),
    ("role:docente_admin", "*", "tarea_practica_template:*", "delete"),
    # BYOK keys — admin del tenant gestiona keys del scope tenant/materia/facultad.
    ("role:docente_admin", "*", "unidad:*", "create"),
    ("role:docente_admin", "*", "unidad:*", "read"),
    ("role:docente_admin", "*", "unidad:*", "update"),
    ("role:docente_admin", "*", "unidad:*", "delete"),
    ("role:docente_admin", "*", "byok_key:*", "create"),
    ("role:docente_admin", "*", "byok_key:*", "read"),
    ("role:docente_admin", "*", "byok_key:*", "update"),
    ("role:docente_admin", "*", "byok_key:*", "delete"),
    ("role:docente_admin", "*", "audit:*", "read"),
    # ── Docente: solo comisiones asignadas + lectura del árbol ─────────
    ("role:docente", "*", "universidad:*", "read"),
    ("role:docente", "*", "facultad:*", "read"),
    ("role:docente", "*", "carrera:*", "read"),
    ("role:docente", "*", "plan:*", "read"),
    ("role:docente", "*", "materia:*", "read"),
    ("role:docente", "*", "periodo:*", "read"),
    ("role:docente", "*", "comision:*", "read"),
    ("role:docente", "*", "inscripcion:*", "read"),
    ("role:docente", "*", "tarea_practica:*", "create"),
    ("role:docente", "*", "tarea_practica:*", "read"),
    ("role:docente", "*", "tarea_practica:*", "update"),
    ("role:docente", "*", "tarea_practica:*", "delete"),
    ("role:docente", "*", "unidad:*", "create"),
    ("role:docente", "*", "unidad:*", "read"),
    ("role:docente", "*", "unidad:*", "update"),
    ("role:docente", "*", "unidad:*", "delete"),
    ("role:docente", "*", "tarea_practica_template:*", "create"),
    ("role:docente", "*", "tarea_practica_template:*", "read"),
    ("role:docente", "*", "tarea_practica_template:*", "update"),
    ("role:docente", "*", "tarea_practica_template:*", "delete"),
    # tp-entregas-correccion: entrega + calificacion CRUD para docentes
    ("role:docente", "*", "entrega:*", "read"),
    ("role:docente", "*", "calificacion:*", "create"),
    ("role:docente", "*", "calificacion:*", "read"),
    ("role:docente", "*", "calificacion:*", "update"),
    ("role:docente_admin", "*", "entrega:*", "read"),
    ("role:docente_admin", "*", "calificacion:*", "create"),
    ("role:docente_admin", "*", "calificacion:*", "read"),
    ("role:docente_admin", "*", "calificacion:*", "update"),
    ("role:superadmin", "*", "entrega:*", "create"),
    ("role:superadmin", "*", "entrega:*", "read"),
    ("role:superadmin", "*", "entrega:*", "update"),
    ("role:superadmin", "*", "entrega:*", "delete"),
    ("role:superadmin", "*", "calificacion:*", "create"),
    ("role:superadmin", "*", "calificacion:*", "read"),
    ("role:superadmin", "*", "calificacion:*", "update"),
    ("role:superadmin", "*", "calificacion:*", "delete"),
    # En F2+, docente tendrá create/update sobre material, ejercicios, rúbricas
    # y correcciones de SUS comisiones (se enforza con ABAC adicional).
    # ── Estudiante: lectura muy limitada ──────────────────────────────
    ("role:estudiante", "*", "universidad:*", "read"),
    ("role:estudiante", "*", "carrera:*", "read"),
    # `materia:* read` requerido por GET /api/v1/materias/mias (filtra por
    # student_pseudonym desde headers — el endpoint NO expone materias de
    # otros alumnos). Diseño shape: el alumno elige materia, no comisión.
    ("role:estudiante", "*", "materia:*", "read"),
    ("role:estudiante", "*", "comision:*", "read"),
    ("role:estudiante", "*", "inscripcion:*", "read"),
    ("role:estudiante", "*", "unidad:*", "read"),
    ("role:estudiante", "*", "tarea_practica:*", "read"),
    ("role:estudiante", "*", "tarea_practica_template:*", "read"),
    # tp-entregas-correccion: estudiante puede crear y leer SUS entregas/calificaciones
    ("role:estudiante", "*", "entrega:*", "create"),
    ("role:estudiante", "*", "entrega:*", "read"),
    ("role:estudiante", "*", "calificacion:*", "read"),
    # En F2+: propio material, problemas de sus comisiones, tutor socrático
    # ── Unidad (ADR-041): agrupacion tematica de TPs por comision ────────
    # superadmin CRUD
    ("role:superadmin", "*", "unidad:*", "create"),
    ("role:superadmin", "*", "unidad:*", "read"),
    ("role:superadmin", "*", "unidad:*", "update"),
    ("role:superadmin", "*", "unidad:*", "delete"),
    # docente_admin CRUD
    ("role:docente_admin", "*", "unidad:*", "create"),
    ("role:docente_admin", "*", "unidad:*", "read"),
    ("role:docente_admin", "*", "unidad:*", "update"),
    ("role:docente_admin", "*", "unidad:*", "delete"),
    # docente CRUD (gestiona sus propias comisiones)
    ("role:docente", "*", "unidad:*", "create"),
    ("role:docente", "*", "unidad:*", "read"),
    ("role:docente", "*", "unidad:*", "update"),
    ("role:docente", "*", "unidad:*", "delete"),
    # estudiante: solo lectura
    ("role:estudiante", "*", "unidad:*", "read"),
    # tutor_service: lectura para resoluciones de contexto
    ("role:tutor_service", "*", "unidad:*", "read"),
    # ── Service accounts (cross-service) ─────────────────────────────
    ("role:tutor_service", "*", "unidad:*", "read"),
    ("role:tutor_service", "*", "tarea_practica:*", "read"),
    ("role:tutor_service", "*", "tarea_practica_template:*", "read"),
    ("role:tutor_service", "*", "comision:*", "read"),
    ("role:evaluation_service", "*", "entrega:*", "read"),
    # ── Ejercicios reusables (ADR-047 + ADR-048) ─────────────────────
    # Banco de ejercicios standalone por tenant. CRUD para superadmin,
    # docente_admin y docente (cualquier docente puede crear ejercicios
    # en el banco compartido del tenant). Estudiantes solo lectura.
    # tutor_service necesita lectura para resolver el ejercicio del
    # episodio (ver ADR-049: propagación de ejercicio_id al CTR).
    ("role:superadmin", "*", "ejercicio:*", "create"),
    ("role:superadmin", "*", "ejercicio:*", "read"),
    ("role:superadmin", "*", "ejercicio:*", "update"),
    ("role:superadmin", "*", "ejercicio:*", "delete"),
    ("role:docente_admin", "*", "ejercicio:*", "create"),
    ("role:docente_admin", "*", "ejercicio:*", "read"),
    ("role:docente_admin", "*", "ejercicio:*", "update"),
    ("role:docente_admin", "*", "ejercicio:*", "delete"),
    ("role:docente", "*", "ejercicio:*", "create"),
    ("role:docente", "*", "ejercicio:*", "read"),
    ("role:docente", "*", "ejercicio:*", "update"),
    ("role:docente", "*", "ejercicio:*", "delete"),
    ("role:estudiante", "*", "ejercicio:*", "read"),
    ("role:tutor_service", "*", "ejercicio:*", "read"),
    # ── Instrumentos del diseño cuasi-experimental (ADR-053) ─────────
    # P2-1 (pretest autoeficacia), P2-2 (cuestionario IA previa), P2-3
    # (test de transferencia) del PlanMejora.md. Estudiante crea/lee su
    # propia respuesta (RLS adicional impone que sólo vea la suya); docente
    # y docente_admin leen agregados anonimizados via analytics-service con
    # k-anonymity gate (MIN_STUDENTS_FOR_QUARTILES=5).
    ("role:superadmin", "*", "instrumento_cuestionario_ia:*", "create"),
    ("role:superadmin", "*", "instrumento_cuestionario_ia:*", "read"),
    ("role:superadmin", "*", "instrumento_cuestionario_ia:*", "delete"),
    ("role:docente_admin", "*", "instrumento_cuestionario_ia:*", "read"),
    ("role:docente", "*", "instrumento_cuestionario_ia:*", "read"),
    ("role:estudiante", "*", "instrumento_cuestionario_ia:*", "create"),
    ("role:estudiante", "*", "instrumento_cuestionario_ia:*", "read"),
    ("role:superadmin", "*", "instrumento_pretest_autoeficacia:*", "create"),
    ("role:superadmin", "*", "instrumento_pretest_autoeficacia:*", "read"),
    ("role:superadmin", "*", "instrumento_pretest_autoeficacia:*", "delete"),
    ("role:docente_admin", "*", "instrumento_pretest_autoeficacia:*", "read"),
    ("role:docente", "*", "instrumento_pretest_autoeficacia:*", "read"),
    ("role:estudiante", "*", "instrumento_pretest_autoeficacia:*", "create"),
    ("role:estudiante", "*", "instrumento_pretest_autoeficacia:*", "read"),
    ("role:superadmin", "*", "instrumento_test_transferencia:*", "create"),
    ("role:superadmin", "*", "instrumento_test_transferencia:*", "read"),
    ("role:superadmin", "*", "instrumento_test_transferencia:*", "delete"),
    ("role:docente_admin", "*", "instrumento_test_transferencia:*", "read"),
    ("role:docente", "*", "instrumento_test_transferencia:*", "read"),
    ("role:estudiante", "*", "instrumento_test_transferencia:*", "create"),
    ("role:estudiante", "*", "instrumento_test_transferencia:*", "read"),
]


async def seed() -> None:
    db_url = os.environ.get(
        "ACADEMIC_DB_URL",
        "postgresql+asyncpg://academic_user:academic_pass@127.0.0.1:5432/academic_main",
    )
    engine = create_async_engine(db_url)

    async with engine.begin() as conn:
        # Borrar policies previas (seed idempotente)
        await conn.execute(text("DELETE FROM casbin_rules WHERE ptype = 'p'"))

        # Insertar matriz
        for sub, dom, obj, act in POLICIES:
            await conn.execute(
                text("""
                    INSERT INTO casbin_rules (ptype, v0, v1, v2, v3)
                    VALUES ('p', :sub, :dom, :obj, :act)
                """),
                {"sub": sub, "dom": dom, "obj": obj, "act": act},
            )

        count = await conn.scalar(text("SELECT COUNT(*) FROM casbin_rules WHERE ptype = 'p'"))
        print(f"[OK] {count} policies Casbin cargadas")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed())
