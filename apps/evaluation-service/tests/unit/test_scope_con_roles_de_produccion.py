"""El guard de comision, con la identidad que el gateway emite DE VERDAD.

Fija en la suite el hallazgo que costo mas caro de los dos dias de auditoria.

El api-gateway le asigna `clerk_base_roles = "estudiante,docente"` a TODO
usuario logueado con Clerk (`api_gateway/config.py`) y despues PISA
autoritativamente el header entrante con `",".join(sorted(principal.roles))`
(`jwt_auth.py`). El comentario del propio config lo dice: "la distincion real
docente/alumno la da usuarios_comision/inscripciones por identidad, NO el token".

Consecuencia: **un guard que discrimina por rol le da 403 a los alumnos**, que
en `usuarios_comision` no existen porque viven en `inscripciones`. Una version
anterior de estos guards preguntaba `if user.roles & DOCENTE_ROLES` y habria
matado el flujo de entrega del piloto entero.

Y no lo agarraba ningun test porque los ~40 que existian arman al alumno con
`X-User-Roles: "estudiante"` a secas — una identidad que produccion NUNCA emite.
Los seis que decian "regresion critica: el alumno sigue pudiendo..." validaban
una forma que no existe.

`_assert_comision_visible` pregunta por PROPIEDAD antes que por rol, y eso es lo
inmune: `student_pseudonym == user.id` compara contra el `X-User-Id`, que el
gateway inyecta desde el JWT ya validado. El token puede mentir sobre los roles;
sobre eso no.

**La regla que sale de aca, y vale para todo el repo: un test de autorizacion
con un usuario de un solo rol no prueba nada en este deploy.**

Son unitarios a proposito (la db es un doble): la propiedad es del guard, no de
la base.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from evaluation_service.auth.dependencies import User
from evaluation_service.routes.entregas import _assert_comision_visible
from fastapi import HTTPException

TENANT = uuid.uuid4()
COMISION = uuid.uuid4()

# Lo que el gateway inyecta HOY para CUALQUIER usuario logueado con Clerk.
ROLES_DE_PRODUCCION = frozenset({"estudiante", "docente"})


def _user(user_id: uuid.UUID, roles: frozenset[str] = ROLES_DE_PRODUCCION) -> User:
    return User(
        id=user_id,
        tenant_id=TENANT,
        email="alguien@utn.edu.ar",
        roles=roles,
        realm=str(TENANT),
    )


def _entrega(dueno: uuid.UUID):
    e = MagicMock()
    e.student_pseudonym = dueno
    e.comision_id = COMISION
    e.tenant_id = TENANT
    return e


def _db(hay_membresia: bool):
    """Doble de la sesion: `first()` decide si el user esta en la comision."""
    db = MagicMock()
    db.execute = AsyncMock(
        return_value=MagicMock(first=MagicMock(return_value=(1,) if hay_membresia else None))
    )
    return db


class TestElAlumnoNoQuedaAfuera:
    async def test_el_alumno_pasa_sobre_su_propia_entrega(self) -> None:
        """El caso que un guard por rol rompia para TODO el piloto."""
        alumno = uuid.uuid4()
        # Sin membresia en `usuarios_comision`: los alumnos viven en
        # `inscripciones`, asi que el doble devuelve None a proposito.
        db = _db(hay_membresia=False)

        await _assert_comision_visible(db, _entrega(alumno), _user(alumno))

        db.execute.assert_not_awaited()

    async def test_el_alumno_NO_pasa_sobre_la_de_otro(self) -> None:
        """La propiedad no puede aflojar el aislamiento entre alumnos."""
        alumno, ajena = uuid.uuid4(), uuid.uuid4()
        db = _db(hay_membresia=False)

        with pytest.raises(HTTPException) as exc:
            await _assert_comision_visible(db, _entrega(ajena), _user(alumno))
        assert exc.value.status_code == 404


class TestElDocenteAjenoSigueFrenado:
    async def test_docente_de_otra_comision_no_pasa(self) -> None:
        docente, alumno = uuid.uuid4(), uuid.uuid4()
        db = _db(hay_membresia=False)

        with pytest.raises(HTTPException) as exc:
            await _assert_comision_visible(db, _entrega(alumno), _user(docente))
        # 404 y no 403: un 403 confirmaria que la entrega existe, y ahi el id de
        # una comision ajena se vuelve un oraculo de existencia.
        assert exc.value.status_code == 404

    async def test_el_docente_de_LA_comision_pasa(self) -> None:
        docente, alumno = uuid.uuid4(), uuid.uuid4()
        db = _db(hay_membresia=True)

        await _assert_comision_visible(db, _entrega(alumno), _user(docente))
        db.execute.assert_awaited()

    async def test_oversight_pasa_sin_membresia(self) -> None:
        """Coordinacion corrige cross-comision a proposito."""
        admin, alumno = uuid.uuid4(), uuid.uuid4()
        db = _db(hay_membresia=False)

        await _assert_comision_visible(
            db, _entrega(alumno), _user(admin, frozenset({"superadmin", "estudiante", "docente"}))
        )
