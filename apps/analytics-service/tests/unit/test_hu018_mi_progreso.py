"""Aceptacion HU-018, Mi progreso del alumno. REVISADA en la ronda de arreglos
(orquestador, 22/11) por la verificacion independiente del PR #148.

Hallazgo F15 de HU-014: "Mi progreso" pide las alertas y da 403 al alumno,
porque con Clerk toda cuenta trae `estudiante,docente` y cae en la rama de
staff de `require_student_progress_access`.

La primera version de esta aceptacion (C01, `3c8b130`/`9cd4031`) pedia que esa
dependencia dejara pasar el propio pseudonimo sin mirar roles. La verificacion
mostro que eso abria `/student/{yo}/alerts?comision_id=<ajena>` a TODA cuenta:
devuelve `cohort_stats` de cualquier comision. Y el docstring de
`/student/me/cii-evolution-longitudinal` ya descartaba ese camino ("POR QUE UN
/me Y NO ABRIR EL GUARD"). Se reemplaza por el patron que ya usa el repo.

R02a  `require_student_progress_access` queda como estaba: con roles de
      produccion y sin membresia, ni siquiera el propio pseudonimo pasa.
R02b  Existe `GET /api/v1/analytics/student/me/alerts`, registrado ANTES de
      `/student/{student_pseudonym}/alerts`, y toma el pseudonimo del token.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from analytics_service import config
from analytics_service.routes import analytics as routes
from fastapi import HTTPException, status

ROLES_PROD = "estudiante,docente"


async def test_r02a_la_dependencia_no_abre_el_propio_pseudonimo_a_staff(monkeypatch) -> None:
    monkeypatch.setattr(config.settings, "enforce_comision_access", True)

    async def _no_es_miembro(*a, **k):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="no miembro")

    monkeypatch.setattr(routes, "assert_comision_member", _no_es_miembro)
    yo = uuid4()
    with pytest.raises(HTTPException) as exc:
        await routes.require_student_progress_access(
            student_pseudonym=yo,
            comision_id=uuid4(),
            x_user_id=str(yo),
            x_user_roles=ROLES_PROD,
            tenant_id=uuid4(),
        )
    assert exc.value.status_code == 403


def test_r02b_existe_alerts_me_antes_que_el_path_param() -> None:
    rutas = [getattr(r, "path", "") for r in routes.router.routes]
    me = "/api/v1/analytics/student/me/alerts"
    param = "/api/v1/analytics/student/{student_pseudonym}/alerts"
    assert me in rutas, "falta /student/me/alerts"
    assert rutas.index(me) < rutas.index(param), "/me tiene que ir antes del path param"


async def test_r02b_alerts_me_usa_el_pseudonimo_del_token(monkeypatch) -> None:
    visto: dict = {}

    async def _alerts(**kwargs):
        visto.update(kwargs)
        return "ok"

    monkeypatch.setattr(routes, "get_student_alerts", _alerts)
    handler = next(
        (
            r.endpoint
            for r in routes.router.routes
            if getattr(r, "path", "") == "/api/v1/analytics/student/me/alerts"
        ),
        None,
    )
    assert handler is not None, "falta /student/me/alerts"
    yo, comision = uuid4(), uuid4()
    await handler(comision_id=comision, language=None, tenant_id=uuid4(), user_id=yo)
    assert visto["student_pseudonym"] == yo
    assert visto["comision_id"] == comision
