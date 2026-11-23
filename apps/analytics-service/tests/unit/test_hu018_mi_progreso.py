"""Aceptacion HU-018, Mi progreso del alumno (orquestador, antes de construir;
el constructor no la modifica). Juani (22/11): "vos terminas todo entonces".

Hallazgo F15 de HU-014: en produccion "Mi progreso" pide las alertas y da 403
al alumno. Causa: con Clerk toda cuenta trae `estudiante,docente`, asi que el
alumno cae en la rama de staff de `require_student_progress_access` y
`assert_comision_member` lo rechaza (no esta en `usuarios_comision`).

C01  Un alumno con roles de produccion (`estudiante,docente`) pide su PROPIO
     progreso: pasa, sin consultar la membresia de comision.
N01  Con esos mismos roles, pedir el progreso de OTRO sigue pasando por la
     membresia de comision (y si no es miembro, 403).
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from analytics_service import config
from analytics_service.routes import analytics as routes
from fastapi import HTTPException, status

ROLES_PROD = "estudiante,docente"


async def test_c01_el_alumno_ve_su_propio_progreso_con_roles_de_produccion(monkeypatch) -> None:
    monkeypatch.setattr(config.settings, "enforce_comision_access", True)
    llamadas: list[object] = []

    async def _no_es_miembro(*a, **k):
        llamadas.append(a)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="no miembro")

    monkeypatch.setattr(routes, "assert_comision_member", _no_es_miembro)
    yo = uuid4()
    try:
        await routes.require_student_progress_access(
            student_pseudonym=yo,
            comision_id=uuid4(),
            x_user_id=str(yo),
            x_user_roles=ROLES_PROD,
            tenant_id=uuid4(),
        )
    except HTTPException as e:
        pytest.fail(f"el alumno recibio {e.status_code} sobre su propio progreso")
    assert llamadas == [], "no hace falta consultar la comision para el propio progreso"


async def test_n01_el_progreso_de_otro_sigue_pidiendo_membresia(monkeypatch) -> None:
    monkeypatch.setattr(config.settings, "enforce_comision_access", True)

    async def _no_es_miembro(*a, **k):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="no miembro")

    monkeypatch.setattr(routes, "assert_comision_member", _no_es_miembro)
    with pytest.raises(HTTPException) as exc:
        await routes.require_student_progress_access(
            student_pseudonym=uuid4(),
            comision_id=uuid4(),
            x_user_id=str(uuid4()),
            x_user_roles=ROLES_PROD,
            tenant_id=uuid4(),
        )
    assert exc.value.status_code == 403
