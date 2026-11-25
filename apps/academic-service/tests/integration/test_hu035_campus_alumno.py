"""Aceptacion HU-035 (orquestador, antes de construir; el constructor no la
modifica). El alumno navega el campus de su comision: lee la bienvenida y las
unidades, y la introduccion de una unidad solo cuando ya abrio.

Contrato que fija esta prueba:
  - `ComisionService.obtener_bienvenida(comision_id, user)` deja leer al
    alumno INSCRIPTO (gate `assert_comision_access`), ademas del staff. Un
    alumno no inscripto recibe 403. Escribir sigue siendo solo del staff.
  - `unidad_para_lector(out: UnidadOut, es_staff: bool, hoy: date) ->
    UnidadOut` en `services/unidad_service.py`: si el lector NO es staff y la
    unidad tiene `fecha_apertura > hoy`, devuelve una copia con
    `introduccion_html=None` (nombre, descripcion y fecha se mantienen, para
    la tarjeta "Abre el ..."). En cualquier otro caso la devuelve igual.
  - `routes/unidades.py` la aplica en el listado y en el detalle.

C02  El alumno inscripto lee la bienvenida de su curso.
N01  Un alumno no inscripto no lee la bienvenida (403).
N02  El alumno no recibe la introduccion de una unidad que todavia no abrio.
N03  El docente si la recibe (para armarla antes de que abra).
N04  El alumno inscripto sigue sin poder escribir la bienvenida.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from academic_service.auth.dependencies import User
from academic_service.models import Comision
from academic_service.schemas.unidad import UnidadOut
from fastapi import HTTPException

RAIZ_SERVICIO = Path(__file__).resolve().parents[2]
HOY = date(2027, 3, 10)


def _user(roles: set[str], tenant_id: UUID) -> User:
    return User(
        id=uuid4(),
        tenant_id=tenant_id,
        email="u@example.com",
        roles=frozenset(roles),
        realm=str(tenant_id),
    )


def _fake_comision(tenant_id: UUID) -> MagicMock:
    c = MagicMock(spec=Comision)
    c.id = uuid4()
    c.tenant_id = tenant_id
    c.bienvenida_html = "<h1>Bienvenidos</h1>"
    c.deleted_at = None
    return c


def _sesion_por_tabla(
    comision: object, docente_de: list[UUID], inscripto_en: list[UUID]
) -> MagicMock:
    """Responde segun la tabla que consulta cada `execute`: `usuarios_comision`
    (staff) e `inscripciones` (alumnos) por separado, y la comision para el
    resto. Asi la prueba distingue "es docente" de "esta inscripto" sin
    depender del orden de las consultas."""

    def _resultado(stmt: object, *args: object, **kwargs: object) -> MagicMock:
        sql = str(stmt).lower()
        r = MagicMock()
        if "inscripciones" in sql:
            ids = inscripto_en
        elif "usuarios_comision" in sql:
            ids = docente_de
        else:
            ids = []
        r.all = MagicMock(return_value=[(i,) for i in ids])
        r.scalar_one_or_none = MagicMock(return_value=comision)
        r.scalar_one = MagicMock(return_value=comision)
        return r

    session = MagicMock()
    session.execute = AsyncMock(side_effect=_resultado)
    session.get = AsyncMock(return_value=comision)
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    return session


def _out(fecha: date | None, intro: str | None = "<h2>Intro</h2>") -> UnidadOut:
    return UnidadOut(
        id=uuid4(),
        tenant_id=uuid4(),
        comision_id=uuid4(),
        nombre="Unidad 3 · Condicionales",
        descripcion="Decisiones",
        orden=2,
        introduccion_html=intro,
        fecha_apertura=fecha,
        created_by=uuid4(),
        created_at="2026-11-01T00:00:00Z",
    )


# ── Bienvenida ─────────────────────────────────────────────────────────


async def test_c02_alumno_inscripto_lee_la_bienvenida(tenant_a_id: UUID) -> None:
    from academic_service.services.comision_service import ComisionService

    comision = _fake_comision(tenant_a_id)
    session = _sesion_por_tabla(comision, docente_de=[], inscripto_en=[comision.id])
    alumno = _user({"estudiante"}, tenant_a_id)

    assert (
        await ComisionService(session).obtener_bienvenida(comision.id, alumno)
        == "<h1>Bienvenidos</h1>"
    )


async def test_n01_alumno_no_inscripto_no_lee_la_bienvenida(tenant_a_id: UUID) -> None:
    from academic_service.services.comision_service import ComisionService

    comision = _fake_comision(tenant_a_id)
    session = _sesion_por_tabla(comision, docente_de=[], inscripto_en=[])
    alumno = _user({"estudiante"}, tenant_a_id)

    with pytest.raises(HTTPException) as exc:
        await ComisionService(session).obtener_bienvenida(comision.id, alumno)
    assert exc.value.status_code == 403


async def test_n04_alumno_inscripto_no_escribe_la_bienvenida(tenant_a_id: UUID) -> None:
    from academic_service.services.comision_service import ComisionService

    comision = _fake_comision(tenant_a_id)
    session = _sesion_por_tabla(comision, docente_de=[], inscripto_en=[comision.id])
    alumno = _user({"estudiante"}, tenant_a_id)

    with pytest.raises(HTTPException) as exc:
        await ComisionService(session).actualizar_bienvenida(comision.id, "<p>hackeado</p>", alumno)
    assert exc.value.status_code == 403
    assert comision.bienvenida_html == "<h1>Bienvenidos</h1>"
    session.flush.assert_not_called()


# ── Unidades que todavia no abrieron ───────────────────────────────────


def test_n02_alumno_no_recibe_la_introduccion_antes_de_la_apertura() -> None:
    from academic_service.services.unidad_service import unidad_para_lector

    out = _out(date(2027, 3, 16))
    vista = unidad_para_lector(out, es_staff=False, hoy=HOY)
    assert vista.introduccion_html is None
    assert vista.nombre == out.nombre
    assert vista.descripcion == out.descripcion
    assert vista.fecha_apertura == date(2027, 3, 16)
    # No muta el original: el ORM/cache no pierde la introduccion.
    assert out.introduccion_html == "<h2>Intro</h2>"


def test_c03_alumno_recibe_la_introduccion_desde_el_dia_de_apertura() -> None:
    from academic_service.services.unidad_service import unidad_para_lector

    assert (
        unidad_para_lector(_out(HOY), es_staff=False, hoy=HOY).introduccion_html == "<h2>Intro</h2>"
    )
    assert (
        unidad_para_lector(_out(date(2027, 3, 1)), es_staff=False, hoy=HOY).introduccion_html
        == "<h2>Intro</h2>"
    )
    assert (
        unidad_para_lector(_out(None), es_staff=False, hoy=HOY).introduccion_html
        == "<h2>Intro</h2>"
    )


def test_n03_el_docente_ve_la_introduccion_antes_de_que_abra() -> None:
    from academic_service.services.unidad_service import unidad_para_lector

    vista = unidad_para_lector(_out(date(2027, 3, 16)), es_staff=True, hoy=HOY)
    assert vista.introduccion_html == "<h2>Intro</h2>"


def test_n02_las_rutas_de_unidades_aplican_la_vista_del_lector() -> None:
    fuente = (RAIZ_SERVICIO / "src/academic_service/routes/unidades.py").read_text(encoding="utf-8")
    # Listado y detalle: las dos lecturas del alumno.
    assert fuente.count("unidad_para_lector(") >= 2
