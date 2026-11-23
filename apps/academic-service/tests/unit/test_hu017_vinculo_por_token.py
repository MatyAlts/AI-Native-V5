"""Aceptacion HU-017 C09, vinculo de docente por email (orquestador, antes de
construir; el constructor no la modifica). Juani (23/11): "si sumalo".

Hallazgo de la revision de seguridad del PR #150: `POST /api/v1/users/me/profile`
vincula `usuarios_comision.user_id` con el email que manda el CLIENTE en el body
(`data.email`), sin verificarlo. Un alumno que manda el email de un docente pasa
a ser "miembro" de todas sus comisiones (lee trazas, ve la cola, cambia
etiquetas) y le saca el vinculo al docente real. HU-017 apoya toda la
separacion en esa tabla.

El email confiable es el del token: el gateway lo valida en el JWT de Clerk
(claim `email`, obligatorio) y lo pisa en `X-User-Email`, que llega como
`user.email`.

C09  El vinculo con `usuarios_comision` usa el email del token, nunca el del body.
C10  El email que se guarda en el perfil es el del token (el docente lo ve en su
     listado de alumnos: no puede ser uno inventado).
N06  Si el token no trae email, no se vincula nada.
N07  Un docente legitimo (body y token con el mismo email, distinto en
     mayusculas) se sigue vinculando al loguearse.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

from academic_service.auth import User
from academic_service.routes import student_profiles as ruta
from academic_service.schemas.student_profile import StudentProfileUpsert
from sqlalchemy.dialects import postgresql
from sqlalchemy.sql.dml import Insert, Update

TENANT = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
DOCENTE = "docente.real@utn.edu.ar"
ALUMNO = "alumno@gmail.com"


def _user(email: str) -> User:
    return User(
        id=uuid4(),
        tenant_id=TENANT,
        email=email,
        roles=frozenset({"estudiante", "docente"}),
        realm=str(TENANT),
    )


def _db() -> tuple[MagicMock, list[Any]]:
    sentencias: list[Any] = []

    async def _execute(stmt: Any, *_a: Any, **_k: Any) -> MagicMock:
        sentencias.append(stmt)
        return MagicMock(scalar_one=MagicMock(return_value=MagicMock()))

    db = MagicMock()
    db.execute = AsyncMock(side_effect=_execute)
    db.commit = AsyncMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    return db, sentencias


def _sql(stmt: Any) -> str:
    return str(
        stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
    ).lower()


def _vinculos(sentencias: list[Any]) -> list[str]:
    return [_sql(s) for s in sentencias if isinstance(s, Update) and "usuarios_comision" in _sql(s)]


def _inserts_perfil(sentencias: list[Any]) -> list[str]:
    return [_sql(s) for s in sentencias if isinstance(s, Insert) and "student_profiles" in _sql(s)]


async def _llamar(user: User, email_body: str | None) -> list[Any]:
    db, sentencias = _db()
    data = StudentProfileUpsert(full_name="X", email=email_body)
    await ruta.upsert_my_profile(data, user, db)
    return sentencias


# ── C09 ────────────────────────────────────────────────────────────────


async def test_c09_el_email_del_body_no_vincula_comisiones_ajenas() -> None:
    sentencias = await _llamar(_user(ALUMNO), DOCENTE)
    for sql in _vinculos(sentencias):
        assert DOCENTE not in sql, "vinculo con el email del body"
    assert any(ALUMNO in sql for sql in _vinculos(sentencias)), "no vinculo con el del token"


# ── C10 ────────────────────────────────────────────────────────────────


async def test_c10_el_perfil_guarda_el_email_del_token() -> None:
    sentencias = await _llamar(_user(ALUMNO), DOCENTE)
    perfiles = _inserts_perfil(sentencias)
    assert perfiles, "no se guardo el perfil"
    assert all(DOCENTE not in sql for sql in perfiles)
    assert any(ALUMNO in sql for sql in perfiles)


# ── N06 ────────────────────────────────────────────────────────────────


async def test_n06_sin_email_en_el_token_no_se_vincula() -> None:
    sentencias = await _llamar(_user(""), DOCENTE)
    assert _vinculos(sentencias) == []


# ── N07 ────────────────────────────────────────────────────────────────


async def test_n07_el_docente_legitimo_se_sigue_vinculando() -> None:
    sentencias = await _llamar(_user("Docente.Real@UTN.edu.ar"), DOCENTE)
    vinculos = _vinculos(sentencias)
    assert len(vinculos) == 1
    assert DOCENTE in vinculos[0]
