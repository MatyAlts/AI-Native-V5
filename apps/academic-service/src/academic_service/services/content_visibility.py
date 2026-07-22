"""Filtrado por rol del contenido sensible de ejercicios / TPs (A0.3).

Los ejercicios y las TPs monolíticas guardan, además del enunciado que ve
el alumno, material de SOLUCIÓN y de conducción del tutor: test cases
ocultos (`is_public=false`, con la respuesta esperada `expected`), pistas /
anti-soluciones (`respuesta_pista`), banco socrático, misconceptions con su
pregunta diagnóstica, heurística de cierre, anti-patrones y `tutor_rules`.

Ese material NO debe viajar al ALUMNO (rompe la evaluación honesta y el
"probar código"): un estudiante podía leer la solución vía
`GET /tareas-practicas/{id}/ejercicios`, `GET /ejercicios/{id}` o el detalle
de la TP monolítica. Los roles de autoría/corrección/tutoría siguen viendo
todo (el docente para corregir, el tutor-service para inyectar contexto
socrático al LLM — ADR-048/049).

Este módulo centraliza el criterio de rol y el saneo para que ambos routers
(`tareas_practicas.py`, `ejercicios.py`) apliquen exactamente la misma
política.
"""

from __future__ import annotations

from platform_contracts.academic.ejercicio import EjercicioRead

from academic_service.auth.dependencies import User
from academic_service.schemas.tarea_practica import TareaPracticaOut

# Roles que ven el contenido pedagógico COMPLETO (con datos de solución).
# `tutor_service` va incluido: el tutor-service inyecta pistas / misconceptions /
# tests ocultos al system message del LLM (ADR-048/049), por eso necesita el
# objeto entero aunque no sea docente ni alumno de la comisión. El resto de los
# roles (estudiante) recibe la vista saneada.
FULL_CONTENT_ROLES: frozenset[str] = frozenset(
    {"docente", "docente_admin", "superadmin", "jtp", "auxiliar", "tutor_service"}
)


def is_full_content_role(user: User) -> bool:
    """True si el caller puede ver el contenido con datos de solución."""
    return bool(user.roles & FULL_CONTENT_ROLES)


def sanitize_ejercicio_for_student(ej: EjercicioRead) -> EjercicioRead:
    """Vista del Ejercicio para el ALUMNO — sin datos de solución (A0.3).

    Quita:
      - test cases ocultos (`is_public=false`): traen `expected` (respuesta
        esperada) y el `code` del test. El alumno solo conserva los públicos,
        que necesita para "probar código" honesto (F1).
      - `respuesta_pista`: anti-soluciones / pistas de resolución.
      - `misconceptions`: confusiones anticipadas + pregunta diagnóstica.
      - `banco_preguntas`: banco socrático estratificado (guion del tutor).
      - `heuristica_cierre`, `anti_patrones`, `tutor_rules`: reglas internas
        de cómo el tutor conduce el episodio.

    Conserva enunciado, código inicial, prerequisitos, dificultad, unidad
    temática, rúbrica y SOLO los test cases públicos.
    """
    return ej.model_copy(
        update={
            "test_cases": [tc for tc in ej.test_cases if tc.is_public],
            "respuesta_pista": [],
            "misconceptions": [],
            "banco_preguntas": None,
            "heuristica_cierre": None,
            "anti_patrones": [],
            "tutor_rules": None,
        }
    )


def sanitize_tarea_practica_for_student(tp: TareaPracticaOut) -> TareaPracticaOut:
    """Vista de la TP monolítica para el ALUMNO — sin test cases ocultos (A0.3).

    `TareaPractica.test_cases` es JSONB no tipado (`list[dict]`); se filtran los
    que no son `is_public=True` (traen `expected` y el `code` del test oculto).
    Fail-closed: un test sin la clave `is_public` se trata como oculto. Los
    públicos quedan intactos para "probar código".
    """
    return tp.model_copy(
        update={
            "test_cases": [tc for tc in tp.test_cases if tc.get("is_public") is True],
        }
    )
