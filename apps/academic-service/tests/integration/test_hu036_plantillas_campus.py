"""Aceptacion HU-036 (orquestador, antes de construir; el constructor no la
modifica). Autorizada por Jarvis en nombre de Juani (24/11). Decision de
Juani: plantilla de campus completo por materia; el docente la aplica a su
comision en un clic (unidades, introducciones, bienvenida y TPs sugeridos) y
despues retoca fechas y textos. Mientras el admin no las carga, se guarda como
plantilla un campus ya armado.

Contrato que fija esta prueba:
  - Modelo `PlantillaCampus` (tabla `plantillas_campus`, con `tenant_id`,
    `materia_id`, `nombre`, `contenido` JSONB, `created_by`) + migracion con
    ENABLE y FORCE ROW LEVEL SECURITY y policy de tenant.
  - `services/plantilla_campus_service.py`:
      * `armar_contenido(bienvenida_html, unidades, tps_por_unidad)` (pura):
        `unidades` son objetos con nombre, descripcion, orden,
        introduccion_html y fecha_apertura; `tps_por_unidad` es
        {unidad_id: [ficha]} donde cada ficha es un dict con al menos
        codigo, titulo, enunciado y `ejercicio_ids` (en orden). Devuelve
        {"version": "campus_v1", "bienvenida_html": ..., "unidades": [...]}
        con las unidades en orden y cada una con sus "tps". NO copia
        `fecha_apertura` ni ids de la comision de origen.
      * `planificar_aplicacion(contenido, nombres_existentes, bienvenida_actual)`
        (pura) -> objeto con `unidades_a_crear` (lista de dicts del
        contenido), `unidades_omitidas` (nombres que ya existian, que NO se
        pisan) y `bienvenida` (el HTML a escribir, o None si la comision ya
        tenia una).
      * `validar_misma_materia(materia_plantilla, materia_comision)` lanza
        HTTPException 422 si no coinciden.
      * `PlantillaCampusService(session).guardar(comision_id, nombre, user)` y
        `.aplicar(plantilla_id, comision_id, user)`: membresia de la
        comision (`assert_comision_member`) ANTES de leer o escribir nada.
  - Los TPs se crean en la comision destino como `draft`, sin fechas, con su
    `unidad_id` y la misma composicion de ejercicios.
  - Rutas: `POST /api/v1/plantillas-campus` (body {comision_id, nombre}),
    `GET /api/v1/plantillas-campus` (query `comision_id`: lista las plantillas
    de la materia de esa comision, con membresia) y `POST /api/v1/plantillas-campus/{plantilla_id}/aplicar`.
    Respuesta de aplicar: {unidades_creadas, unidades_omitidas, tps_creados,
    bienvenida_aplicada}.
  - Casbin: recurso `plantilla_campus` CRUD para docente, docente_admin y
    superadmin. Gateway: prefijo `/api/v1/plantillas-campus` en ROUTE_MAP.

C01  Guardar el campus de una comision como plantilla de su materia.
C02  Aplicar una plantilla crea unidades, introducciones, bienvenida y TPs.
C03  El listado trae las plantillas de la materia de la comision.
N01  Las fechas no viajan en la plantilla (el docente las pone despues).
N02  Aplicar no pisa unidades que ya existen ni una bienvenida ya escrita.
N03  No se aplica una plantilla de otra materia (422).
N04  Un docente ajeno a la comision no guarda ni aplica (403, sin escribir).
N05  Los TPs aplicados nacen en borrador: ningun alumno los ve sin que el
     docente los publique.
K02  Migracion con RLS; Casbin y gateway registrados.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from academic_service.auth.dependencies import User
from fastapi import HTTPException

RAIZ_SERVICIO = Path(__file__).resolve().parents[2]
RAIZ_REPO = RAIZ_SERVICIO.parents[1]


def _user(roles: set[str], tenant_id: UUID) -> User:
    return User(
        id=uuid4(),
        tenant_id=tenant_id,
        email="u@example.com",
        roles=frozenset(roles),
        realm=str(tenant_id),
    )


def _unidad(
    nombre: str, orden: int, fecha: date | None = None, intro: str | None = None
) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        comision_id=uuid4(),
        nombre=nombre,
        descripcion=f"Resumen {nombre}",
        orden=orden,
        introduccion_html=intro,
        fecha_apertura=fecha,
    )


def _ficha(codigo: str, ejercicios: list[UUID]) -> dict:
    return {
        "codigo": codigo,
        "titulo": f"TP {codigo}",
        "enunciado": "Resolve los ejercicios",
        "ejercicio_ids": [str(e) for e in ejercicios],
    }


def _contenido_ejemplo() -> tuple[dict, list[UUID]]:
    from academic_service.services.plantilla_campus_service import armar_contenido

    u2 = _unidad("Unidad 2 · Secuenciales", 1, date(2027, 3, 9), "<h2>Intro 2</h2>")
    u1 = _unidad("Unidad 1 · Bienvenida", 0, None, "<h2>Intro 1</h2>")
    ejs = [uuid4(), uuid4(), uuid4()]
    contenido = armar_contenido(
        "<h1>Bienvenidos</h1>",
        [u2, u1],
        {u2.id: [_ficha("SEC01", ejs)], u1.id: []},
    )
    return contenido, ejs


# ── C01 / N01: armar el contenido ──────────────────────────────────────


def test_c01_contenido_con_unidades_en_orden_y_sus_tps() -> None:
    contenido, ejs = _contenido_ejemplo()
    assert contenido["version"] == "campus_v1"
    assert contenido["bienvenida_html"] == "<h1>Bienvenidos</h1>"
    nombres = [u["nombre"] for u in contenido["unidades"]]
    assert nombres == ["Unidad 1 · Bienvenida", "Unidad 2 · Secuenciales"]
    u2 = contenido["unidades"][1]
    assert u2["introduccion_html"] == "<h2>Intro 2</h2>"
    assert u2["descripcion"] == "Resumen Unidad 2 · Secuenciales"
    assert [t["codigo"] for t in u2["tps"]] == ["SEC01"]
    assert u2["tps"][0]["ejercicio_ids"] == [str(e) for e in ejs]
    assert contenido["unidades"][0]["tps"] == []


def test_n01_las_fechas_y_los_ids_de_origen_no_viajan() -> None:
    contenido, _ = _contenido_ejemplo()
    texto = repr(contenido)
    for u in contenido["unidades"]:
        assert "fecha_apertura" not in u
        assert "id" not in u
        assert "comision_id" not in u
    assert "2027-03-09" not in texto
    assert "datetime.date(2027, 3, 9)" not in texto


def test_c01_el_contenido_es_json() -> None:
    import json

    contenido, _ = _contenido_ejemplo()
    assert json.loads(json.dumps(contenido)) == contenido


# ── C02 / N02: planificar la aplicacion ────────────────────────────────


def test_c02_comision_vacia_recibe_todo() -> None:
    from academic_service.services.plantilla_campus_service import planificar_aplicacion

    contenido, _ = _contenido_ejemplo()
    plan = planificar_aplicacion(contenido, nombres_existentes=set(), bienvenida_actual=None)
    assert [u["nombre"] for u in plan.unidades_a_crear] == [
        "Unidad 1 · Bienvenida",
        "Unidad 2 · Secuenciales",
    ]
    assert plan.unidades_omitidas == []
    assert plan.bienvenida == "<h1>Bienvenidos</h1>"


def test_n02_no_pisa_unidades_ni_bienvenida_existentes() -> None:
    from academic_service.services.plantilla_campus_service import planificar_aplicacion

    contenido, _ = _contenido_ejemplo()
    plan = planificar_aplicacion(
        contenido,
        nombres_existentes={"Unidad 2 · Secuenciales"},
        bienvenida_actual="<p>La mia</p>",
    )
    assert [u["nombre"] for u in plan.unidades_a_crear] == ["Unidad 1 · Bienvenida"]
    assert plan.unidades_omitidas == ["Unidad 2 · Secuenciales"]
    assert plan.bienvenida is None


def test_n02_bienvenida_vacia_cuenta_como_sin_bienvenida() -> None:
    from academic_service.services.plantilla_campus_service import planificar_aplicacion

    contenido, _ = _contenido_ejemplo()
    plan = planificar_aplicacion(contenido, nombres_existentes=set(), bienvenida_actual="   ")
    assert plan.bienvenida == "<h1>Bienvenidos</h1>"


# ── N03: misma materia ─────────────────────────────────────────────────


def test_n03_no_se_aplica_una_plantilla_de_otra_materia() -> None:
    from academic_service.services.plantilla_campus_service import validar_misma_materia

    m = uuid4()
    validar_misma_materia(m, m)
    with pytest.raises(HTTPException) as exc:
        validar_misma_materia(m, uuid4())
    assert exc.value.status_code == 422


# ── N04: permisos ──────────────────────────────────────────────────────


def _sesion_sin_membresia() -> MagicMock:
    r = MagicMock()
    r.all = MagicMock(return_value=[])
    r.scalar_one_or_none = MagicMock(return_value=None)
    r.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
    session = MagicMock()
    session.execute = AsyncMock(return_value=r)
    session.get = AsyncMock(return_value=None)
    session.add = MagicMock()
    session.add_all = MagicMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    return session


async def test_n04_docente_ajeno_no_guarda_plantilla(tenant_a_id: UUID) -> None:
    from academic_service.services.plantilla_campus_service import PlantillaCampusService

    session = _sesion_sin_membresia()
    with pytest.raises(HTTPException) as exc:
        await PlantillaCampusService(session).guardar(
            uuid4(), "Prog 1 base", _user({"docente"}, tenant_a_id)
        )
    assert exc.value.status_code == 403
    session.add.assert_not_called()
    session.add_all.assert_not_called()
    session.flush.assert_not_called()


async def test_n04_docente_ajeno_no_aplica_plantilla(tenant_a_id: UUID) -> None:
    from academic_service.services.plantilla_campus_service import PlantillaCampusService

    session = _sesion_sin_membresia()
    with pytest.raises(HTTPException) as exc:
        await PlantillaCampusService(session).aplicar(
            uuid4(), uuid4(), _user({"docente"}, tenant_a_id)
        )
    assert exc.value.status_code == 403
    session.add.assert_not_called()
    session.add_all.assert_not_called()
    session.flush.assert_not_called()


# ── N05: los TPs aplicados nacen en borrador ───────────────────────────


def test_n05_los_tps_aplicados_nacen_en_borrador_y_sin_fechas() -> None:
    from academic_service.services.plantilla_campus_service import datos_tp_aplicado

    comision, unidad, user_id = uuid4(), uuid4(), uuid4()
    ficha = {
        **_ficha("SEC01", [uuid4()]),
        "fecha_inicio": "2026-03-01",
        "fecha_fin": "2026-03-20",
        "estado": "published",
    }
    datos = datos_tp_aplicado(ficha, comision_id=comision, unidad_id=unidad, created_by=user_id)
    assert datos["estado"] == "draft"
    assert datos["fecha_inicio"] is None
    assert datos["fecha_fin"] is None
    assert datos["comision_id"] == comision
    assert datos["unidad_id"] == unidad
    assert datos["codigo"] == "SEC01"
    assert datos["version"] == 1
    assert datos["parent_tarea_id"] is None


# ── Cableado: rutas, modelo, migracion, Casbin, gateway ────────────────


def test_c03_rutas() -> None:
    from academic_service.main import app

    paths = app.openapi()["paths"]
    assert {"get", "post"} <= set(paths.get("/api/v1/plantillas-campus", {}))
    assert "post" in paths.get("/api/v1/plantillas-campus/{plantilla_id}/aplicar", {})
    params = {p["name"] for p in paths["/api/v1/plantillas-campus"]["get"].get("parameters", [])}
    assert "comision_id" in params


def test_k02_modelo_y_migracion_con_rls() -> None:
    from academic_service.models import PlantillaCampus

    cols = PlantillaCampus.__table__.columns
    for c in ("tenant_id", "materia_id", "nombre", "contenido", "created_by"):
        assert c in cols, c
    assert PlantillaCampus.__tablename__ == "plantillas_campus"
    versiones = RAIZ_SERVICIO / "alembic" / "versions"
    textos = [p.read_text(encoding="utf-8") for p in versiones.glob("*.py")]
    migra = [t for t in textos if "plantillas_campus" in t]
    assert migra, "falta la migracion de plantillas_campus"
    t = migra[0]
    assert "ALTER TABLE plantillas_campus ENABLE ROW LEVEL SECURITY" in t
    assert "ALTER TABLE plantillas_campus FORCE ROW LEVEL SECURITY" in t
    assert "CREATE POLICY" in t
    assert "def downgrade" in t


def test_k02_casbin_y_gateway() -> None:
    from academic_service.seeds.casbin_policies import POLICIES

    for rol in ("role:docente", "role:docente_admin", "role:superadmin"):
        for accion in ("create", "read"):
            assert (rol, "*", "plantilla_campus:*", accion) in POLICIES, (rol, accion)
    proxy = (RAIZ_REPO / "apps/api-gateway/src/api_gateway/routes/proxy.py").read_text(
        encoding="utf-8"
    )
    assert '"/api/v1/plantillas-campus"' in proxy
