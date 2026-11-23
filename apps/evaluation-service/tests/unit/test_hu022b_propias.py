"""HU-022 (vuelta 2), C01/N01/N02: `GET /entregas?propias=true`.

EL BUG (F24, prueba en produccion del 23/11)
---------------------------------------------
El docente pasa a "Ver como alumno" y la vista del alumno le muestra como
PROPIAS las entregas de los alumnos de su comision: ve un TP "Entregado ·
Esperando correccion" que nunca hizo y no puede empezarlo. La vista del alumno
pide `GET /entregas?comision_id=...` y, como quien pide tiene comisiones
asignadas, entra por la rama de staff, que devuelve la comision entera.

El contrato nuevo: `propias=true` fuerza la rama del alumno COMPLETA, aunque
quien pida sea docente asignado. "Completa" importa: esa rama filtra por
`student_pseudonym == user.id` y ademas deja ver el propio `draft`, que la
rama de staff oculta.

Sesion mockeada, sin DB: se captura el `select(Entrega)` que arma el endpoint
y se mira su WHERE compilado con los valores.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

from evaluation_service.auth.dependencies import User
from evaluation_service.routes.entregas import list_entregas
from sqlalchemy.sql.selectable import Select

TENANT = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
COMISION = UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")


def _user(uid: UUID, roles: set[str]) -> User:
    return User(id=uid, tenant_id=TENANT, email="x@utn.edu.ar", roles=frozenset(roles), realm="utn")


def _db_que_captura(comisiones_del_caller: list[UUID]) -> tuple[MagicMock, list[Select]]:
    """Responde la consulta cruda de `usuarios_comision` con las comisiones
    dadas, y captura cada `select` que el endpoint arme."""
    capturados: list[Select] = []

    async def _execute(stmt, *args, **kwargs):
        if isinstance(stmt, Select):
            capturados.append(stmt)
            return MagicMock(
                scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[]))),
                all=MagicMock(return_value=[]),
            )
        # text(...) de usuarios_comision y cualquier otra consulta cruda.
        return MagicMock(all=MagicMock(return_value=[(c,) for c in comisiones_del_caller]))

    db = MagicMock()
    db.execute = AsyncMock(side_effect=_execute)
    return db, capturados


def _where(stmts: list[Select]) -> str:
    """El WHERE del `select(Entrega)` principal, con los valores literales."""
    principal = [s for s in stmts if "FROM entregas" in str(s)]
    assert principal, "el endpoint no armo ningun select sobre entregas"
    sql = str(principal[0].compile(compile_kwargs={"literal_binds": True}))
    return sql.split("WHERE", 1)[1] if "WHERE" in sql else ""


def _sin_guiones(u: UUID) -> str:
    return u.hex


async def _listar(user: User, comisiones: list[UUID], **kw) -> str:
    db, capturados = _db_que_captura(comisiones)
    params = {
        "tarea_practica_id": None,
        "comision_id": COMISION,
        "estado": None,
        "student_pseudonym": None,
        "cursor": None,
        "limit": 50,
        "user": user,
        "db": db,
    }
    params.update(kw)
    await list_entregas(**params)
    return _where(capturados)


def _filtra_por(where: str, uid: UUID) -> bool:
    # Postgres UUID compilado: aparece con o sin guiones segun el dialecto.
    return str(uid) in where or _sin_guiones(uid) in where


class TestC01DocenteEnVistaAlumno:
    async def test_propias_filtra_por_el_propio_usuario(self) -> None:
        docente = uuid4()
        where = await _listar(_user(docente, {"estudiante", "docente"}), [COMISION], propias=True)
        assert "student_pseudonym" in where and _filtra_por(where, docente), (
            "con propias=true el docente asignado sigue recibiendo la comision "
            f"entera: el WHERE no filtra por su propio id. WHERE: {where}"
        )

    async def test_propias_deja_ver_el_propio_borrador(self) -> None:
        """La rama de staff oculta `draft`; la del alumno no. Sin su borrador,
        el docente que empezo un TP como alumno no puede retomarlo."""
        docente = uuid4()
        where = await _listar(_user(docente, {"estudiante", "docente"}), [COMISION], propias=True)
        assert "draft" not in where, (
            f"con propias=true se siguen ocultando los borradores: WHERE {where}"
        )

    async def test_propias_ignora_student_pseudonym_ajeno(self) -> None:
        """`propias` no se combina con otro pseudonimo: manda el propio."""
        docente, otro = uuid4(), uuid4()
        where = await _listar(
            _user(docente, {"estudiante", "docente"}),
            [COMISION],
            propias=True,
            student_pseudonym=otro,
        )
        assert _filtra_por(where, docente)
        assert not _filtra_por(where, otro), (
            f"con propias=true se filtro por el pseudonimo de otro: WHERE {where}"
        )


class TestN01AlumnoComun:
    async def test_alumno_con_propias_sigue_viendo_solo_lo_suyo(self) -> None:
        alumno = uuid4()
        where = await _listar(_user(alumno, {"estudiante", "docente"}), [], propias=True)
        assert _filtra_por(where, alumno)

    async def test_alumno_sin_propias_sigue_viendo_solo_lo_suyo(self) -> None:
        alumno = uuid4()
        where = await _listar(_user(alumno, {"estudiante", "docente"}), [])
        assert _filtra_por(where, alumno)


class TestN02PanelDocente:
    async def test_sin_propias_el_docente_sigue_viendo_su_comision(self) -> None:
        """El panel de correcciones no manda `propias`: tiene que seguir
        trayendo la comision entera, sin filtrar por el id del docente."""
        docente = uuid4()
        where = await _listar(_user(docente, {"estudiante", "docente"}), [COMISION])
        assert not _filtra_por(where, docente), (
            f"sin propias el docente quedo filtrado a si mismo: WHERE {where}"
        )
        assert "comision_id IN" in where.replace("\n", " ") or "comision_id IN" in where, (
            f"sin propias se perdio el aislamiento por comision: WHERE {where}"
        )
