"""Tests de la rama de autorización "Mi progreso" del alumno (F9).

Los endpoints `/student/{id}/{cii-evolution-longitudinal,episodes,alerts}`
ganan una rama de auth: un ESTUDIANTE (sin rol de staff) solo puede pedir SU
propio `student_pseudonym` (el path debe coincidir con `X-User-Id`), mientras
que docente/oversight sigue viendo cualquiera (aislamiento por comisión de hoy).

El conftest pone `enforce_comision_access=False` para el resto de la suite; acá
lo prendemos explícitamente (como `test_comision_access_guard.py`) y mockeamos
`assert_comision_member` para no tocar la DB al probar la rama docente.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from analytics_service import config
from analytics_service.routes import analytics as routes
from fastapi import HTTPException

# ── Rama estudiante (require_student_progress_access) ──────────────────


async def test_estudiante_pide_su_propio_progreso_ok(monkeypatch) -> None:
    """Estudiante con path == su X-User-Id → pasa (no 403, no toca comisión)."""
    monkeypatch.setattr(config.settings, "enforce_comision_access", True)

    async def _boom(*a, **k):  # no debe llamarse para un estudiante
        raise AssertionError("assert_comision_member no debe correr para estudiante")

    monkeypatch.setattr(routes, "assert_comision_member", _boom)

    me = uuid4()
    await routes.require_student_progress_access(
        student_pseudonym=me,
        comision_id=uuid4(),
        x_user_id=str(me),
        x_user_roles="estudiante",
        tenant_id=uuid4(),
    )


async def test_estudiante_pide_el_de_otro_403(monkeypatch) -> None:
    """Estudiante con path != su X-User-Id → 403."""
    monkeypatch.setattr(config.settings, "enforce_comision_access", True)
    with pytest.raises(HTTPException) as exc:
        await routes.require_student_progress_access(
            student_pseudonym=uuid4(),  # otro alumno
            comision_id=uuid4(),
            x_user_id=str(uuid4()),  # el caller
            x_user_roles="estudiante",
            tenant_id=uuid4(),
        )
    assert exc.value.status_code == 403


async def test_caller_sin_roles_tratado_como_estudiante(monkeypatch) -> None:
    """Sin X-User-Roles → no es staff → restringido a su propio pseudónimo."""
    monkeypatch.setattr(config.settings, "enforce_comision_access", True)
    with pytest.raises(HTTPException) as exc:
        await routes.require_student_progress_access(
            student_pseudonym=uuid4(),
            comision_id=uuid4(),
            x_user_id=str(uuid4()),
            x_user_roles=None,
            tenant_id=uuid4(),
        )
    assert exc.value.status_code == 403


# ── Rama docente/oversight (comportamiento de hoy) ─────────────────────


@pytest.mark.parametrize("role", ["docente", "docente_admin", "superadmin", "jtp", "auxiliar"])
async def test_docente_ve_cualquier_alumno_via_comision(monkeypatch, role: str) -> None:
    """Staff → delega en assert_comision_member (aislamiento por comisión),
    sin exigir que el path coincida con su user_id."""
    monkeypatch.setattr(config.settings, "enforce_comision_access", True)
    seen: dict[str, object] = {}

    async def fake_assert(user_id, comision_id, tenant_id):
        seen["args"] = (user_id, comision_id, tenant_id)

    monkeypatch.setattr(routes, "assert_comision_member", fake_assert)

    uid, cid, tid, otro_alumno = uuid4(), uuid4(), uuid4(), uuid4()
    await routes.require_student_progress_access(
        student_pseudonym=otro_alumno,  # docente pide el progreso de otro
        comision_id=cid,
        x_user_id=str(uid),
        x_user_roles=role,
        tenant_id=tid,
    )
    assert seen["args"] == (uid, cid, tid)


async def test_docente_no_asignado_recibe_403_de_comision(monkeypatch) -> None:
    """Si assert_comision_member rechaza (no es de esa comisión), propaga 403."""
    monkeypatch.setattr(config.settings, "enforce_comision_access", True)

    async def fake_assert(user_id, comision_id, tenant_id):
        raise HTTPException(status_code=403, detail="no sos docente asignado")

    monkeypatch.setattr(routes, "assert_comision_member", fake_assert)

    with pytest.raises(HTTPException) as exc:
        await routes.require_student_progress_access(
            student_pseudonym=uuid4(),
            comision_id=uuid4(),
            x_user_id=str(uuid4()),
            x_user_roles="docente",
            tenant_id=uuid4(),
        )
    assert exc.value.status_code == 403


async def test_rol_mixto_docente_estudiante_tratado_como_staff(monkeypatch) -> None:
    """Un caller con 'docente,estudiante' es staff → ve cualquiera (rama comisión)."""
    monkeypatch.setattr(config.settings, "enforce_comision_access", True)
    called = {"n": 0}

    async def fake_assert(user_id, comision_id, tenant_id):
        called["n"] += 1

    monkeypatch.setattr(routes, "assert_comision_member", fake_assert)
    await routes.require_student_progress_access(
        student_pseudonym=uuid4(),  # otro alumno, distinto al user_id
        comision_id=uuid4(),
        x_user_id=str(uuid4()),
        x_user_roles="docente,estudiante",
        tenant_id=uuid4(),
    )
    assert called["n"] == 1


# ── Gate por flag + validación de headers ──────────────────────────────


async def test_enforce_off_es_noop(monkeypatch) -> None:
    """Con el flag en False no exige nada (modo dev/test) — ni user ni self-check."""
    monkeypatch.setattr(config.settings, "enforce_comision_access", False)
    await routes.require_student_progress_access(
        student_pseudonym=uuid4(),
        comision_id=uuid4(),
        x_user_id=None,
        x_user_roles=None,
        tenant_id=uuid4(),
    )


async def test_enforce_on_sin_user_id_401(monkeypatch) -> None:
    monkeypatch.setattr(config.settings, "enforce_comision_access", True)
    with pytest.raises(HTTPException) as exc:
        await routes.require_student_progress_access(
            student_pseudonym=uuid4(),
            comision_id=uuid4(),
            x_user_id=None,
            x_user_roles="estudiante",
            tenant_id=uuid4(),
        )
    assert exc.value.status_code == 401


async def test_enforce_on_user_id_invalido_400(monkeypatch) -> None:
    monkeypatch.setattr(config.settings, "enforce_comision_access", True)
    with pytest.raises(HTTPException) as exc:
        await routes.require_student_progress_access(
            student_pseudonym=uuid4(),
            comision_id=uuid4(),
            x_user_id="not-a-uuid",
            x_user_roles="estudiante",
            tenant_id=uuid4(),
        )
    assert exc.value.status_code == 400
