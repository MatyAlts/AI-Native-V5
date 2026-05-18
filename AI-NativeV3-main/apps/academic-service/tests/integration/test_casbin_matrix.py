"""Test de la matriz de permisos Casbin.

Verifica que cada combinación rol × recurso × acción devuelva el
resultado correcto según las policies del seed.

Usa un enforcer en memoria (sin adapter DB) para velocidad.
"""

from __future__ import annotations

from tempfile import NamedTemporaryFile

import casbin
import pytest
from academic_service.auth.casbin_setup import CASBIN_MODEL
from academic_service.seeds.casbin_policies import POLICIES


@pytest.fixture(scope="module")
def enforcer() -> casbin.Enforcer:
    """Enforcer en memoria con policies del seed."""
    with NamedTemporaryFile(mode="w", suffix=".conf", delete=False) as f:
        f.write(CASBIN_MODEL)
        model_path = f.name

    with NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        # Casbin file adapter: p, sub, dom, obj, act
        for sub, dom, obj, act in POLICIES:
            f.write(f"p, {sub}, {dom}, {obj}, {act}\n")
        policy_path = f.name

    return casbin.Enforcer(model_path, policy_path)


# ── Matriz esperada: (rol, recurso, acción, esperado) ──────────────────
# True = debe permitirse, False = debe denegarse.
MATRIX = [
    # Superadmin: todo
    ("role:superadmin", "universidad:123", "create", True),
    ("role:superadmin", "universidad:123", "delete", True),
    ("role:superadmin", "comision:abc", "update", True),
    ("role:superadmin", "tarea_practica_template:tpl1", "create", True),
    ("role:superadmin", "tarea_practica_template:tpl1", "delete", True),
    # ADR-039 (epic ai-native-completion-and-byok): BYOK keys son admin-only.
    ("role:superadmin", "byok_key:abc", "create", True),
    ("role:superadmin", "byok_key:abc", "read", True),
    ("role:superadmin", "byok_key:abc", "update", True),
    ("role:superadmin", "byok_key:abc", "delete", True),
    # Docente admin: gestiona su tenant
    ("role:docente_admin", "carrera:x", "create", True),
    ("role:docente_admin", "carrera:x", "read", True),
    ("role:docente_admin", "carrera:x", "delete", True),
    ("role:docente_admin", "comision:abc", "create", True),
    ("role:docente_admin", "materia:m1", "update", True),
    ("role:docente_admin", "audit:log", "read", True),
    ("role:docente_admin", "tarea_practica_template:tpl1", "create", True),
    ("role:docente_admin", "tarea_practica_template:tpl1", "update", True),
    ("role:docente_admin", "tarea_practica_template:tpl1", "delete", True),
    ("role:docente_admin", "byok_key:abc", "create", True),
    ("role:docente_admin", "byok_key:abc", "read", True),
    ("role:docente_admin", "byok_key:abc", "update", True),
    ("role:docente_admin", "byok_key:abc", "delete", True),
    # Docente: lectura del árbol académico, sin modificar
    ("role:docente", "comision:abc", "read", True),
    ("role:docente", "comision:abc", "create", False),
    ("role:docente", "carrera:x", "delete", False),
    ("role:docente", "materia:m1", "read", True),
    ("role:docente", "materia:m1", "update", False),
    ("role:docente", "universidad:123", "update", False),
    ("role:docente", "tarea_practica_template:tpl1", "create", True),
    ("role:docente", "tarea_practica_template:tpl1", "read", True),
    ("role:docente", "tarea_practica_template:tpl1", "update", True),
    ("role:docente", "tarea_practica_template:tpl1", "delete", True),
    # Docente NO gestiona BYOK keys — admin-only.
    ("role:docente", "byok_key:abc", "create", False),
    ("role:docente", "byok_key:abc", "read", False),
    # Estudiante: muy limitado
    ("role:estudiante", "comision:abc", "read", True),
    ("role:estudiante", "comision:abc", "create", False),
    ("role:estudiante", "universidad:123", "read", True),
    ("role:estudiante", "universidad:123", "update", False),
    ("role:estudiante", "carrera:x", "delete", False),
    # `materia:* read` agregado para que el alumno pueda llamar
    # GET /api/v1/materias/mias (filtrado por su student_pseudonym desde
    # headers — el endpoint NO expone materias de otros).
    ("role:estudiante", "materia:m1", "read", True),
    ("role:estudiante", "materia:m1", "update", False),
    ("role:estudiante", "tarea_practica_template:tpl1", "read", True),
    ("role:estudiante", "tarea_practica_template:tpl1", "create", False),
    ("role:estudiante", "tarea_practica_template:tpl1", "update", False),
    ("role:estudiante", "tarea_practica_template:tpl1", "delete", False),
    # Estudiante NO ve ni gestiona BYOK keys — datos sensibles del tenant.
    ("role:estudiante", "byok_key:abc", "read", False),
    ("role:estudiante", "byok_key:abc", "create", False),
]


@pytest.mark.parametrize("sub,obj,act,expected", MATRIX)
def test_casbin_matrix(
    enforcer: casbin.Enforcer,
    sub: str,
    obj: str,
    act: str,
    expected: bool,
) -> None:
    """Cada celda de la matriz de permisos se evalúa correctamente."""
    actual = enforcer.enforce(sub, "*", obj, act)
    assert actual == expected, f"({sub}, {obj}, {act}) = {actual}, esperado {expected}"


def test_matriz_es_exhaustiva(enforcer: casbin.Enforcer) -> None:
    """Validación metamétrica: la matriz cubre los 4 roles."""
    roles_en_matriz = {row[0] for row in MATRIX}
    assert roles_en_matriz == {
        "role:superadmin",
        "role:docente_admin",
        "role:docente",
        "role:estudiante",
    }


def test_deny_por_default(enforcer: casbin.Enforcer) -> None:
    """Sin policy, la respuesta debe ser deny."""
    assert not enforcer.enforce("role:invitado", "*", "comision:abc", "read")
    assert not enforcer.enforce("role:estudiante", "*", "recurso-no-existe:x", "create")
