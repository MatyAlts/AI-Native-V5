"""Aceptacion HU-033 (orquestador, antes de construir; el constructor no la
modifica). Juani (24/11): campus por comision, lo arma el docente desde su
panel; bienvenida e introduccion de cada unidad en HTML (con JS) que se
muestran en un recuadro aislado; las unidades se abren por fecha.

Contrato que fija esta prueba:
  - `Unidad.introduccion_html` (Text, nullable) y `Unidad.fecha_apertura`
    (date, nullable: sin fecha = abierta). `descripcion` (ya existe) es el
    resumen de la tarjeta.
  - `Comision.bienvenida_html` (Text, nullable).
  - `UnidadUpdate`/`UnidadOut` llevan `introduccion_html` y `fecha_apertura`.
  - `BienvenidaUpdate(html=...)` y `ComisionService.actualizar_bienvenida(
    comision_id, html, user)` / `obtener_bienvenida(comision_id, user)`.
  - Rutas `GET` y `PUT /api/v1/comisiones/{comision_id}/bienvenida`.
  - Tope de HTML: `HTML_CAMPUS_MAX_CHARS = 512_000` (bienvenida e
    introduccion); mas largo es 422.

C02  La bienvenida se guarda y se lee por comision.
C03  Cada unidad guarda su introduccion HTML y su fecha de apertura.
N01  Un docente que no es de la comision no puede escribir la bienvenida ni
     la introduccion (403, sin tocar nada). Un estudiante tampoco.
N03  HTML mas largo que el tope se rechaza.
N05  Las unidades existentes siguen igual: sin fecha y sin introduccion.
K02  Migracion alembic que agrega las tres columnas.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from academic_service.auth.dependencies import User
from academic_service.models import Comision, Unidad
from academic_service.schemas.unidad import UnidadOut, UnidadUpdate
from academic_service.services.unidad_service import UnidadService
from fastapi import HTTPException
from pydantic import ValidationError

RAIZ_SERVICIO = Path(__file__).resolve().parents[2]


def _user(roles: set[str], tenant_id: UUID) -> User:
    return User(
        id=uuid4(),
        tenant_id=tenant_id,
        email="u@example.com",
        roles=frozenset(roles),
        realm=str(tenant_id),
    )


def _result_scalar(obj: object | None) -> MagicMock:
    r = MagicMock()
    r.scalar_one_or_none = MagicMock(return_value=obj)
    return r


def _result_rows(comision_ids: list[UUID]) -> MagicMock:
    r = MagicMock()
    r.all = MagicMock(return_value=[(cid,) for cid in comision_ids])
    return r


def _session(*results: MagicMock) -> MagicMock:
    session = MagicMock()
    session.execute = AsyncMock(side_effect=list(results))
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    return session


def _sesion_flexible(comision: object, miembros: list[UUID]) -> MagicMock:
    """Cada `execute` devuelve un resultado que sirve tanto para la membresia
    (`.all()`) como para buscar la comision (`.scalar_one_or_none()`), asi la
    prueba no depende del orden de las consultas del servicio."""
    r = MagicMock()
    r.all = MagicMock(return_value=[(cid,) for cid in miembros])
    r.scalar_one_or_none = MagicMock(return_value=comision)
    r.scalar_one = MagicMock(return_value=comision)
    session = MagicMock()
    session.execute = AsyncMock(return_value=r)
    session.get = AsyncMock(return_value=comision)
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    return session


def _fake_unidad(comision_id: UUID, tenant_id: UUID) -> MagicMock:
    u = MagicMock(spec=Unidad)
    u.id = uuid4()
    u.tenant_id = tenant_id
    u.comision_id = comision_id
    u.nombre = "U2"
    u.orden = 1
    u.introduccion_html = None
    u.fecha_apertura = None
    return u


def _fake_comision(tenant_id: UUID) -> MagicMock:
    c = MagicMock(spec=Comision)
    c.id = uuid4()
    c.tenant_id = tenant_id
    c.bienvenida_html = None
    c.deleted_at = None
    return c


# ── Modelo y esquemas ──────────────────────────────────────────────────


def test_modelo_tiene_las_columnas_nuevas() -> None:
    assert "introduccion_html" in Unidad.__table__.columns
    assert "fecha_apertura" in Unidad.__table__.columns
    assert "bienvenida_html" in Comision.__table__.columns
    assert Unidad.__table__.columns["introduccion_html"].nullable
    assert Unidad.__table__.columns["fecha_apertura"].nullable
    assert Comision.__table__.columns["bienvenida_html"].nullable


def test_c03_esquemas_llevan_introduccion_y_fecha() -> None:
    upd = UnidadUpdate(introduccion_html="<h2>Hola</h2>", fecha_apertura=date(2027, 3, 9))
    assert upd.introduccion_html == "<h2>Hola</h2>"
    assert upd.fecha_apertura == date(2027, 3, 9)
    assert "introduccion_html" in UnidadOut.model_fields
    assert "fecha_apertura" in UnidadOut.model_fields


def test_n03_tope_de_html() -> None:
    from academic_service.schemas.unidad import HTML_CAMPUS_MAX_CHARS

    assert HTML_CAMPUS_MAX_CHARS == 512_000
    UnidadUpdate(introduccion_html="x" * HTML_CAMPUS_MAX_CHARS)
    with pytest.raises(ValidationError):
        UnidadUpdate(introduccion_html="x" * (HTML_CAMPUS_MAX_CHARS + 1))


def test_n03_tope_de_la_bienvenida() -> None:
    from academic_service.schemas.comision import BienvenidaUpdate
    from academic_service.schemas.unidad import HTML_CAMPUS_MAX_CHARS

    BienvenidaUpdate(html="<p>Hola</p>")
    with pytest.raises(ValidationError):
        BienvenidaUpdate(html="x" * (HTML_CAMPUS_MAX_CHARS + 1))


# ── C03 / N01: introduccion y fecha por unidad ─────────────────────────


async def test_c03_docente_miembro_guarda_introduccion_y_fecha(tenant_a_id: UUID) -> None:
    com = uuid4()
    unidad = _fake_unidad(com, tenant_a_id)
    session = _session(_result_scalar(unidad), _result_rows([com]))
    user = _user({"docente"}, tenant_a_id)

    await UnidadService(session).update(
        unidad.id,
        UnidadUpdate(
            introduccion_html="<script>1</script><h2>Intro</h2>", fecha_apertura=date(2027, 3, 9)
        ),
        user,
    )
    assert unidad.introduccion_html == "<script>1</script><h2>Intro</h2>"
    assert unidad.fecha_apertura == date(2027, 3, 9)
    session.flush.assert_awaited()


async def test_n01_docente_ajeno_no_toca_la_introduccion(tenant_a_id: UUID) -> None:
    com = uuid4()
    unidad = _fake_unidad(com, tenant_a_id)
    session = _session(_result_scalar(unidad), _result_rows([]))
    user = _user({"docente"}, tenant_a_id)

    with pytest.raises(HTTPException) as exc:
        await UnidadService(session).update(
            unidad.id, UnidadUpdate(introduccion_html="<p>x</p>"), user
        )
    assert exc.value.status_code == 403
    assert unidad.introduccion_html is None
    session.flush.assert_not_called()


# ── C02 / N01: bienvenida por comision ─────────────────────────────────


async def test_c02_docente_miembro_guarda_y_lee_la_bienvenida(tenant_a_id: UUID) -> None:
    from academic_service.services.comision_service import ComisionService

    comision = _fake_comision(tenant_a_id)
    session = _sesion_flexible(comision, [comision.id])
    user = _user({"docente"}, tenant_a_id)
    svc = ComisionService(session)

    await svc.actualizar_bienvenida(comision.id, "<h1>Bienvenidos</h1>", user)
    assert comision.bienvenida_html == "<h1>Bienvenidos</h1>"
    session.flush.assert_awaited()
    assert await svc.obtener_bienvenida(comision.id, user) == "<h1>Bienvenidos</h1>"


async def test_n01_docente_ajeno_no_escribe_la_bienvenida(tenant_a_id: UUID) -> None:
    from academic_service.services.comision_service import ComisionService

    comision = _fake_comision(tenant_a_id)
    session = _sesion_flexible(comision, [])
    user = _user({"docente"}, tenant_a_id)

    with pytest.raises(HTTPException) as exc:
        await ComisionService(session).actualizar_bienvenida(comision.id, "<p>x</p>", user)
    assert exc.value.status_code == 403
    assert comision.bienvenida_html is None
    session.flush.assert_not_called()


async def test_n01_estudiante_no_escribe_la_bienvenida(tenant_a_id: UUID) -> None:
    from academic_service.services.comision_service import ComisionService

    comision = _fake_comision(tenant_a_id)
    session = _sesion_flexible(comision, [])
    user = _user({"estudiante"}, tenant_a_id)

    with pytest.raises(HTTPException) as exc:
        await ComisionService(session).actualizar_bienvenida(comision.id, "<p>x</p>", user)
    assert exc.value.status_code == 403
    assert comision.bienvenida_html is None


def test_c02_rutas_de_la_bienvenida() -> None:
    from academic_service.main import app

    metodos: set[str] = set()
    for r in app.routes:
        if getattr(r, "path", "") == "/api/v1/comisiones/{comision_id}/bienvenida":
            metodos |= set(getattr(r, "methods", set()))
    assert {"GET", "PUT"} <= metodos, metodos


# ── N05 / K02 ──────────────────────────────────────────────────────────


def test_n05_unidad_nueva_sin_fecha_ni_introduccion() -> None:
    from academic_service.schemas.unidad import UnidadCreate

    nueva = UnidadCreate(comision_id=uuid4(), nombre="U1")
    datos = nueva.model_dump()
    assert datos.get("introduccion_html") is None
    assert datos.get("fecha_apertura") is None


def test_k02_migracion_agrega_las_columnas() -> None:
    versiones = RAIZ_SERVICIO / "alembic" / "versions"
    textos = [p.read_text(encoding="utf-8") for p in versiones.glob("*.py")]
    candidatas = [t for t in textos if "bienvenida_html" in t]
    assert candidatas, "falta la migracion de la HU-033"
    t = candidatas[0]
    for columna in ("introduccion_html", "fecha_apertura", "bienvenida_html"):
        assert columna in t, columna
    assert "def downgrade" in t
