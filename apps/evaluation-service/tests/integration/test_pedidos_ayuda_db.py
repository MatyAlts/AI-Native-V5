"""Pedidos de ayuda contra Postgres real: las consultas que los unit tests no ven.

Los tests de `tests/unit/test_pedidos_ayuda_rutas.py` neutralizan la base; aca
corren de verdad el SQL de inscripcion, el scope del docente, el anti-spam, el
`WHERE student_pseudonym` de `/mios` y el filtro por comision del listado.

Solo se neutralizan `_comision_de_la_tp` y `_ejercicios_esperados` (helpers ya
existentes de `entregas.py`, probados en sus propios tests): la TP y la
comision no se siembran porque arrastran una cadena de FKs academicos.
Las filas de `inscripciones` / `usuarios_comision` se siembran con
`session_replication_role = replica` (sin FKs) y con ids aleatorios, y se
limpian al final.

Correr (base MIGRADA, de preferencia descartable):
    EVAL_TEST_DB_URL=postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/<db> \
        uv run pytest apps/evaluation-service/tests/integration/test_pedidos_ayuda_db.py -v
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator
from typing import Any

import pytest
import pytest_asyncio
from evaluation_service.auth import get_db
from evaluation_service.main import app
from evaluation_service.routes import pedidos_ayuda as mod
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

_DSN = os.environ.get("EVAL_TEST_DB_URL")

pytestmark = pytest.mark.skipif(
    not _DSN, reason="Sin EVAL_TEST_DB_URL: este test necesita Postgres real"
)


class Mundo:
    def __init__(self) -> None:
        self.tenant = uuid.uuid4()
        self.comision = uuid.uuid4()
        self.otra_comision = uuid.uuid4()
        self.tp = uuid.uuid4()
        self.tp2 = uuid.uuid4()
        self.alumno = uuid.uuid4()
        self.otro_alumno = uuid.uuid4()
        self.docente = uuid.uuid4()
        self.docente_ajeno = uuid.uuid4()
        self.admin = uuid.uuid4()
        self.comision_de_tp: dict[uuid.UUID, uuid.UUID] = {}

    def headers(self, user: uuid.UUID, roles: str) -> dict[str, str]:
        return {
            "X-User-Id": str(user),
            "X-Tenant-Id": str(self.tenant),
            "X-User-Email": "x@example.com",
            "X-User-Roles": roles,
        }


@pytest_asyncio.fixture
async def mundo(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[Mundo]:
    m = Mundo()
    m.comision_de_tp = {m.tp: m.comision, m.tp2: m.comision}
    engine = create_async_engine(_DSN)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as c:
        await c.execute(text("SET LOCAL session_replication_role = replica"))
        for alumno in (m.alumno, m.otro_alumno):
            await c.execute(
                text(
                    "INSERT INTO inscripciones "
                    "(tenant_id, comision_id, student_pseudonym, fecha_inscripcion) "
                    "VALUES (:t, :c, :s, current_date)"
                ),
                {"t": str(m.tenant), "c": str(m.comision), "s": str(alumno)},
            )
        await c.execute(
            text(
                "INSERT INTO usuarios_comision "
                "(tenant_id, comision_id, user_id, rol, fecha_desde) "
                "VALUES (:t, :c, :u, 'titular', current_date)"
            ),
            {"t": str(m.tenant), "c": str(m.comision), "u": str(m.docente)},
        )

    async def _get_db() -> AsyncIterator[Any]:
        async with factory() as s:
            await s.execute(
                text("SELECT set_config('app.current_tenant', :t, true)"), {"t": str(m.tenant)}
            )
            yield s
            await s.commit()

    async def _comision(_db: Any, tp: uuid.UUID) -> uuid.UUID | None:
        return m.comision_de_tp.get(tp)

    async def _ejercicios(_db: Any, _tp: uuid.UUID) -> list[dict[str, Any]]:
        return []

    monkeypatch.setattr(mod, "_comision_de_la_tp", _comision)
    monkeypatch.setattr(mod, "_ejercicios_esperados", _ejercicios)
    app.dependency_overrides[get_db] = _get_db

    yield m

    app.dependency_overrides.clear()
    async with engine.begin() as c:
        await c.execute(
            text("DELETE FROM pedidos_ayuda WHERE tenant_id = :t"), {"t": str(m.tenant)}
        )
        await c.execute(
            text("DELETE FROM inscripciones WHERE tenant_id = :t"), {"t": str(m.tenant)}
        )
        await c.execute(
            text("DELETE FROM usuarios_comision WHERE tenant_id = :t"), {"t": str(m.tenant)}
        )
    await engine.dispose()


async def _req(
    metodo: str, url: str, headers: dict[str, str], body: dict[str, Any] | None = None
) -> Any:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        return await c.request(metodo, url, json=body, headers=headers)


async def _soltar_el_minuto(m: Mundo) -> None:
    """Envejece los pedidos 2 minutos para saltear el anti-spam de 60 s."""
    engine = create_async_engine(_DSN)
    async with engine.begin() as c:
        await c.execute(
            text(
                "UPDATE pedidos_ayuda SET created_at = created_at - interval '2 minutes' "
                "WHERE tenant_id = :t"
            ),
            {"t": str(m.tenant)},
        )
    await engine.dispose()


def _body(m: Mundo, **extra: Any) -> dict[str, Any]:
    return {"tarea_practica_id": str(m.tp), "categoria": "no_puedo_avanzar", **extra}


class TestCrearContraPostgres:
    async def test_crea_y_persiste(self, mundo: Mundo) -> None:
        r = await _req(
            "POST",
            "/api/v1/pedidos-ayuda",
            mundo.headers(mundo.alumno, "estudiante"),
            _body(mundo, mensaje="hola", contexto={"pantalla": "episodio"}),
        )
        assert r.status_code == 201, r.text
        j = r.json()
        assert j["estado"] == "pendiente"
        assert j["comision_id"] == str(mundo.comision)
        assert j["contexto"] == {"pantalla": "episodio"}
        assert j["created_at"]

    async def test_alumno_sin_inscripcion_403(self, mundo: Mundo) -> None:
        r = await _req(
            "POST",
            "/api/v1/pedidos-ayuda",
            mundo.headers(uuid.uuid4(), "estudiante"),
            _body(mundo),
        )
        assert r.status_code == 403

    async def test_inscripcion_borrada_403(self, mundo: Mundo) -> None:
        engine = create_async_engine(_DSN)
        async with engine.begin() as c:
            await c.execute(
                text(
                    "UPDATE inscripciones SET deleted_at = now() "
                    "WHERE tenant_id = :t AND student_pseudonym = :s"
                ),
                {"t": str(mundo.tenant), "s": str(mundo.otro_alumno)},
            )
        await engine.dispose()
        r = await _req(
            "POST",
            "/api/v1/pedidos-ayuda",
            mundo.headers(mundo.otro_alumno, "estudiante"),
            _body(mundo),
        )
        assert r.status_code == 403

    async def test_anti_spam_429_y_luego_pasa(self, mundo: Mundo) -> None:
        h = mundo.headers(mundo.alumno, "estudiante")
        assert (await _req("POST", "/api/v1/pedidos-ayuda", h, _body(mundo))).status_code == 201
        r2 = await _req("POST", "/api/v1/pedidos-ayuda", h, _body(mundo))
        assert r2.status_code == 429
        await _soltar_el_minuto(mundo)
        assert (await _req("POST", "/api/v1/pedidos-ayuda", h, _body(mundo))).status_code == 201

    async def test_tope_de_tres_pendientes_y_resolver_libera(self, mundo: Mundo) -> None:
        h = mundo.headers(mundo.alumno, "estudiante")
        ids = []
        for _ in range(3):
            r = await _req("POST", "/api/v1/pedidos-ayuda", h, _body(mundo))
            assert r.status_code == 201, r.text
            ids.append(r.json()["id"])
            await _soltar_el_minuto(mundo)

        cuarto = await _req("POST", "/api/v1/pedidos-ayuda", h, _body(mundo))
        assert cuarto.status_code == 409

        # Otra TP del mismo alumno no comparte el tope.
        otra = await _req(
            "POST",
            "/api/v1/pedidos-ayuda",
            h,
            {**_body(mundo), "tarea_practica_id": str(mundo.tp2)},
        )
        assert otra.status_code == 201
        await _soltar_el_minuto(mundo)

        res = await _req(
            "PATCH",
            f"/api/v1/pedidos-ayuda/{ids[0]}/resolver",
            mundo.headers(mundo.docente, "docente"),
        )
        assert res.status_code == 200
        de_nuevo = await _req("POST", "/api/v1/pedidos-ayuda", h, _body(mundo))
        assert de_nuevo.status_code == 201

    async def test_el_anti_spam_es_por_alumno(self, mundo: Mundo) -> None:
        a = mundo.headers(mundo.alumno, "estudiante")
        b = mundo.headers(mundo.otro_alumno, "estudiante")
        assert (await _req("POST", "/api/v1/pedidos-ayuda", a, _body(mundo))).status_code == 201
        assert (await _req("POST", "/api/v1/pedidos-ayuda", b, _body(mundo))).status_code == 201


class TestMios:
    async def test_solo_los_del_alumno_del_mas_nuevo_al_mas_viejo(self, mundo: Mundo) -> None:
        a = mundo.headers(mundo.alumno, "estudiante")
        b = mundo.headers(mundo.otro_alumno, "estudiante")
        primero = (
            await _req("POST", "/api/v1/pedidos-ayuda", a, _body(mundo, mensaje="primero"))
        ).json()
        await _req("POST", "/api/v1/pedidos-ayuda", b, _body(mundo, mensaje="del otro"))
        await _soltar_el_minuto(mundo)
        segundo = (
            await _req("POST", "/api/v1/pedidos-ayuda", a, _body(mundo, mensaje="segundo"))
        ).json()

        r = await _req("GET", f"/api/v1/pedidos-ayuda/mios?tarea_practica_id={mundo.tp}", a)

        assert r.status_code == 200
        assert [p["id"] for p in r.json()] == [segundo["id"], primero["id"]]
        assert all(p["student_pseudonym"] == str(mundo.alumno) for p in r.json())

    async def test_filtra_por_tp(self, mundo: Mundo) -> None:
        a = mundo.headers(mundo.alumno, "estudiante")
        await _req("POST", "/api/v1/pedidos-ayuda", a, _body(mundo))
        r = await _req("GET", f"/api/v1/pedidos-ayuda/mios?tarea_practica_id={mundo.tp2}", a)
        assert r.json() == []


class TestListaDelDocente:
    async def test_docente_de_la_comision_ve_pendientes_y_el_contador(self, mundo: Mundo) -> None:
        a = mundo.headers(mundo.alumno, "estudiante")
        b = mundo.headers(mundo.otro_alumno, "estudiante")
        p1 = (await _req("POST", "/api/v1/pedidos-ayuda", a, _body(mundo))).json()
        p2 = (await _req("POST", "/api/v1/pedidos-ayuda", b, _body(mundo))).json()
        doc = mundo.headers(mundo.docente, "docente")
        await _req("PATCH", f"/api/v1/pedidos-ayuda/{p1['id']}/resolver", doc)

        pend = await _req(
            "GET", f"/api/v1/pedidos-ayuda?comision_id={mundo.comision}&estado=pendiente", doc
        )
        res = await _req(
            "GET", f"/api/v1/pedidos-ayuda?comision_id={mundo.comision}&estado=resuelto", doc
        )

        assert pend.status_code == 200
        assert [p["id"] for p in pend.json()["data"]] == [p2["id"]]
        assert pend.json()["meta"]["pendientes"] == 1
        assert [p["id"] for p in res.json()["data"]] == [p1["id"]]
        # El contador de pendientes no depende del filtro de estado.
        assert res.json()["meta"]["pendientes"] == 1

    async def test_otra_comision_no_aparece(self, mundo: Mundo) -> None:
        a = mundo.headers(mundo.alumno, "estudiante")
        await _req("POST", "/api/v1/pedidos-ayuda", a, _body(mundo))
        admin = mundo.headers(mundo.admin, "docente_admin")
        r = await _req("GET", f"/api/v1/pedidos-ayuda?comision_id={mundo.otra_comision}", admin)
        assert r.status_code == 200
        assert r.json()["data"] == []
        assert r.json()["meta"]["pendientes"] == 0

    async def test_docente_de_otra_comision_404(self, mundo: Mundo) -> None:
        r = await _req(
            "GET",
            f"/api/v1/pedidos-ayuda?comision_id={mundo.comision}",
            mundo.headers(mundo.docente_ajeno, "docente"),
        )
        assert r.status_code == 404

    async def test_docente_con_membresia_borrada_404(self, mundo: Mundo) -> None:
        engine = create_async_engine(_DSN)
        async with engine.begin() as c:
            await c.execute(
                text("UPDATE usuarios_comision SET deleted_at = now() WHERE tenant_id = :t"),
                {"t": str(mundo.tenant)},
            )
        await engine.dispose()
        r = await _req(
            "GET",
            f"/api/v1/pedidos-ayuda?comision_id={mundo.comision}",
            mundo.headers(mundo.docente, "docente"),
        )
        assert r.status_code == 404

    async def test_admin_ve_la_comision_sin_estar_asignado(self, mundo: Mundo) -> None:
        r = await _req(
            "GET",
            f"/api/v1/pedidos-ayuda?comision_id={mundo.comision}",
            mundo.headers(mundo.admin, "docente_admin"),
        )
        assert r.status_code == 200


class TestResolverContraPostgres:
    async def test_resolver_persiste_y_es_idempotente(self, mundo: Mundo) -> None:
        a = mundo.headers(mundo.alumno, "estudiante")
        doc = mundo.headers(mundo.docente, "docente")
        p = (await _req("POST", "/api/v1/pedidos-ayuda", a, _body(mundo))).json()

        r1 = await _req("PATCH", f"/api/v1/pedidos-ayuda/{p['id']}/resolver", doc)
        r2 = await _req(
            "PATCH",
            f"/api/v1/pedidos-ayuda/{p['id']}/resolver",
            mundo.headers(mundo.admin, "docente_admin"),
        )

        assert r1.status_code == r2.status_code == 200
        assert r1.json()["resuelto_por"] == r2.json()["resuelto_por"] == str(mundo.docente)
        assert r1.json()["resuelto_at"] == r2.json()["resuelto_at"]

    async def test_docente_ajeno_404_y_sigue_pendiente(self, mundo: Mundo) -> None:
        a = mundo.headers(mundo.alumno, "estudiante")
        p = (await _req("POST", "/api/v1/pedidos-ayuda", a, _body(mundo))).json()

        r = await _req(
            "PATCH",
            f"/api/v1/pedidos-ayuda/{p['id']}/resolver",
            mundo.headers(mundo.docente_ajeno, "docente"),
        )
        assert r.status_code == 404

        mios = await _req("GET", f"/api/v1/pedidos-ayuda/mios?tarea_practica_id={mundo.tp}", a)
        assert mios.json()[0]["estado"] == "pendiente"
