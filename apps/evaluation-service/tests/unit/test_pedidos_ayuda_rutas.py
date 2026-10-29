"""Rutas de `/api/v1/pedidos-ayuda` sin base de datos (sesion falsa).

Las consultas con SQL propio (inscripcion, anti-spam, listas, `/mios`) se prueban
contra Postgres real en `tests/integration/test_pedidos_ayuda_db.py`; aca se
prueba el FLUJO y cada rechazo, neutralizando solo lo que no es el guard bajo
prueba. Cada test negativo se verifico en rojo quitando su guard (ver
`STATUS.md` del change).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from evaluation_service.auth import get_db
from evaluation_service.main import app
from evaluation_service.routes import pedidos_ayuda as mod
from httpx import ASGITransport, AsyncClient
from structlog.testing import capture_logs

TENANT = uuid.uuid4()
COMISION = uuid.uuid4()
OTRA_COMISION = uuid.uuid4()
TP = uuid.uuid4()
ALUMNO = uuid.uuid4()
DOCENTE = uuid.uuid4()
DOCENTE_AJENO = uuid.uuid4()
ADMIN = uuid.uuid4()


class _Resultado:
    def __init__(self, filas: list[tuple[Any, ...]]) -> None:
        self._filas = filas

    def first(self) -> tuple[Any, ...] | None:
        return self._filas[0] if self._filas else None


class DbFalsa:
    """Guarda lo que se agrega y responde el SQL de membresia de docente."""

    def __init__(self) -> None:
        self.objs: dict[uuid.UUID, Any] = {}
        self.docentes: set[tuple[uuid.UUID, uuid.UUID]] = {(DOCENTE, COMISION)}
        self.flushes = 0

    def add(self, obj: Any) -> None:
        self.objs[obj.id] = obj

    async def flush(self) -> None:
        self.flushes += 1
        for o in self.objs.values():
            if o.created_at is None:
                o.created_at = datetime(2026, 10, 28, 15, 0, tzinfo=UTC)

    async def refresh(self, _obj: Any) -> None:
        return None

    async def get(self, _model: Any, pk: uuid.UUID) -> Any:
        return self.objs.get(pk)

    async def execute(self, stmt: Any, params: dict[str, Any] | None = None) -> _Resultado:
        sql = str(stmt)
        assert "usuarios_comision" in sql, f"consulta inesperada en un test unitario: {sql}"
        assert params is not None
        ok = (uuid.UUID(params["uid"]), uuid.UUID(params["cid"])) in self.docentes
        return _Resultado([(1,)] if ok else [])


class Escenario:
    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.db = DbFalsa()
        self.comision_de_tp: uuid.UUID | None = COMISION
        self.inscripto = True
        self.entrega_ok = True
        self.ejercicios: list[dict[str, Any]] = []
        self.segundos_desde_ultimo: float | None = None
        self.pendientes_en_tp = 0

        async def _comision(_db: Any, _tp: uuid.UUID) -> uuid.UUID | None:
            return self.comision_de_tp

        async def _inscripto(_db: Any, _c: uuid.UUID, _s: uuid.UUID) -> bool:
            return self.inscripto

        async def _entrega(_db: Any, _e: uuid.UUID, _s: uuid.UUID, _tp: uuid.UUID) -> bool:
            return self.entrega_ok

        async def _ejercicios(_db: Any, _tp: uuid.UUID) -> list[dict[str, Any]]:
            return self.ejercicios

        async def _desde(_db: Any, _s: uuid.UUID) -> float | None:
            return self.segundos_desde_ultimo

        async def _pend(_db: Any, _s: uuid.UUID, _tp: uuid.UUID) -> int:
            return self.pendientes_en_tp

        monkeypatch.setattr(mod, "_comision_de_la_tp", _comision)
        monkeypatch.setattr(mod, "_esta_inscripto", _inscripto)
        monkeypatch.setattr(mod, "_entrega_del_alumno_en_la_tp", _entrega)
        monkeypatch.setattr(mod, "_ejercicios_esperados", _ejercicios)
        monkeypatch.setattr(mod, "_segundos_desde_ultimo_pedido", _desde)
        monkeypatch.setattr(mod, "_pendientes_en_la_tp", _pend)


@pytest.fixture
def esc(monkeypatch: pytest.MonkeyPatch) -> Any:
    e = Escenario(monkeypatch)

    async def _db() -> Any:
        yield e.db

    app.dependency_overrides[get_db] = _db
    yield e
    app.dependency_overrides.clear()


def _headers(user: uuid.UUID, roles: str) -> dict[str, str]:
    return {
        "X-User-Id": str(user),
        "X-Tenant-Id": str(TENANT),
        "X-User-Email": "x@example.com",
        "X-User-Roles": roles,
    }


ALU = _headers(ALUMNO, "estudiante")
DOC = _headers(DOCENTE, "docente")
DOC_AJENO = _headers(DOCENTE_AJENO, "docente")
ADM = _headers(ADMIN, "docente_admin")


async def _req(
    metodo: str, url: str, headers: dict[str, str], body: dict[str, Any] | None = None
) -> Any:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        return await c.request(metodo, url, json=body, headers=headers)


async def _post(body: dict[str, Any], headers: dict[str, str] = ALU) -> Any:
    return await _req("POST", "/api/v1/pedidos-ayuda", headers, body)


def _body(**extra: Any) -> dict[str, Any]:
    return {"tarea_practica_id": str(TP), "categoria": "no_puedo_avanzar", **extra}


class TestCrear:
    async def test_alumno_inscripto_crea_y_la_comision_sale_de_la_tp(self, esc: Any) -> None:
        r = await _post(_body(mensaje="no entiendo el while", ejercicio_orden=2))

        assert r.status_code == 201, r.text
        j = r.json()
        assert j["estado"] == "pendiente"
        assert j["comision_id"] == str(COMISION)
        assert j["student_pseudonym"] == str(ALUMNO)
        assert j["ejercicio_orden"] == 2
        assert j["created_at"].startswith("2026-10-28")

    async def test_otra_tp_otra_comision(self, esc: Any) -> None:
        """Triangula: la comision acompana a la TP, no esta hardcodeada."""
        esc.comision_de_tp = OTRA_COMISION
        r = await _post(_body())
        assert r.status_code == 201
        assert r.json()["comision_id"] == str(OTRA_COMISION)

    async def test_sin_episode_id_crea(self, esc: Any) -> None:
        r = await _post(_body(categoria="error_plataforma"))
        assert r.status_code == 201
        assert r.json()["episode_id"] is None

    async def test_episode_id_inexistente_se_guarda_igual(self, esc: Any) -> None:
        ep = str(uuid.uuid4())
        r = await _post(_body(episode_id=ep))
        assert r.status_code == 201
        assert r.json()["episode_id"] == ep

    async def test_con_entrega_propia(self, esc: Any) -> None:
        entrega = str(uuid.uuid4())
        r = await _post(_body(entrega_id=entrega))
        assert r.status_code == 201
        assert r.json()["entrega_id"] == entrega

    async def test_el_body_no_puede_traer_la_comision(self, esc: Any) -> None:
        r = await _post(_body(comision_id=str(OTRA_COMISION)))
        assert r.status_code == 422
        assert not esc.db.objs


class TestRechazos:
    async def test_tp_inexistente_422(self, esc: Any) -> None:
        esc.comision_de_tp = None
        r = await _post(_body())
        assert r.status_code == 422
        assert not esc.db.objs

    async def test_alumno_no_inscripto_403(self, esc: Any) -> None:
        esc.inscripto = False
        r = await _post(_body())
        assert r.status_code == 403
        assert "inscripto" in r.json()["detail"]
        assert not esc.db.objs

    async def test_entrega_ajena_o_de_otra_tp_422(self, esc: Any) -> None:
        esc.entrega_ok = False
        r = await _post(_body(entrega_id=str(uuid.uuid4())))
        assert r.status_code == 422
        assert not esc.db.objs

    async def test_ejercicio_fuera_de_la_tp_422(self, esc: Any) -> None:
        esc.ejercicios = [{"orden": 1}, {"orden": 2}]
        r = await _post(_body(ejercicio_orden=7))
        assert r.status_code == 422
        assert not esc.db.objs

    async def test_ejercicio_dentro_de_la_tp_pasa(self, esc: Any) -> None:
        esc.ejercicios = [{"orden": 1}, {"orden": 2}]
        r = await _post(_body(ejercicio_orden=2))
        assert r.status_code == 201

    async def test_tp_monolitica_acepta_ejercicio_1(self, esc: Any) -> None:
        """Sin ejercicios declarados no hay contra que validar el orden."""
        esc.ejercicios = []
        r = await _post(_body(ejercicio_orden=1))
        assert r.status_code == 201

    async def test_docente_no_crea_403(self, esc: Any) -> None:
        r = await _post(_body(), DOC)
        assert r.status_code == 403
        assert not esc.db.objs

    async def test_sin_rol_alguno_403(self, esc: Any) -> None:
        r = await _post(_body(), _headers(ALUMNO, ""))
        assert r.status_code == 403

    async def test_quien_tiene_estudiante_y_otro_rol_pasa(self, esc: Any) -> None:
        r = await _post(_body(), _headers(ALUMNO, "estudiante,docente"))
        assert r.status_code == 201


class TestAntiSpam:
    async def test_segundo_pedido_a_los_10s_es_429_con_espera(self, esc: Any) -> None:
        esc.segundos_desde_ultimo = 10.0
        r = await _post(_body())
        assert r.status_code == 429
        assert "50" in r.json()["detail"]
        assert not esc.db.objs

    async def test_pasado_el_minuto_crea(self, esc: Any) -> None:
        esc.segundos_desde_ultimo = 61.0
        assert (await _post(_body())).status_code == 201

    async def test_justo_a_los_60s_ya_pasa(self, esc: Any) -> None:
        esc.segundos_desde_ultimo = 60.0
        assert (await _post(_body())).status_code == 201

    async def test_cuarto_pendiente_en_la_tp_409(self, esc: Any) -> None:
        esc.pendientes_en_tp = 3
        r = await _post(_body())
        assert r.status_code == 409
        assert "3 pedidos sin responder" in r.json()["detail"]
        assert not esc.db.objs

    async def test_con_dos_pendientes_todavia_crea(self, esc: Any) -> None:
        esc.pendientes_en_tp = 2
        assert (await _post(_body())).status_code == 201


class TestFueraDeLaTesis:
    def test_el_modulo_no_importa_ctr_ni_tutor(self) -> None:
        import inspect

        fuente = inspect.getsource(mod).lower()
        for prohibido in ("ctr", "tutor", "classifier", "services.clients", "httpx"):
            assert f"import {prohibido}" not in fuente
            assert f"from {prohibido}" not in fuente
            assert f"from evaluation_service.services.{prohibido}" not in fuente

    async def test_crear_no_hace_requests_http_salientes(
        self, esc: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Crear un pedido no sale a la red: ni CTR, ni tutor, ni nada."""
        import httpx

        salientes: list[str] = []
        original = httpx.AsyncClient.send

        async def _espia(self: Any, request: Any, *a: Any, **k: Any) -> Any:
            # El cliente del propio test habla con la app por ASGI (host "t").
            if request.url.host != "t":
                salientes.append(str(request.url))
                raise AssertionError("request saliente inesperado")
            return await original(self, request, *a, **k)

        monkeypatch.setattr(httpx.AsyncClient, "send", _espia)

        r = await _post(_body(episode_id=str(uuid.uuid4())))
        assert r.status_code == 201
        assert salientes == []

    async def test_el_log_lleva_ids_y_categoria_pero_no_el_mensaje(self, esc: Any) -> None:
        secreto = "mi DNI es 12345678 y no entiendo"
        with capture_logs() as logs:
            r = await _post(_body(mensaje=secreto, ejercicio_orden=1))
        assert r.status_code == 201
        creado = [x for x in logs if x["event"] == "pedido_ayuda_creado"]
        assert len(creado) == 1
        entrada = creado[0]
        assert entrada["categoria"] == "no_puedo_avanzar"
        assert entrada["comision_id"] == str(COMISION)
        assert entrada["pedido_id"] == r.json()["id"]
        assert secreto not in str(entrada)
        assert "mensaje" not in entrada

    async def test_los_rechazos_no_loguean_pedido_creado(self, esc: Any) -> None:
        esc.inscripto = False
        with capture_logs() as logs:
            await _post(_body())
        assert not [x for x in logs if x["event"] == "pedido_ayuda_creado"]


async def _crear_uno(esc: Any) -> dict[str, Any]:
    r = await _post(_body())
    assert r.status_code == 201
    return r.json()


class TestResolver:
    async def test_docente_de_la_comision_resuelve(self, esc: Any) -> None:
        p = await _crear_uno(esc)

        r = await _req("PATCH", f"/api/v1/pedidos-ayuda/{p['id']}/resolver", DOC)

        assert r.status_code == 200, r.text
        j = r.json()
        assert j["estado"] == "resuelto"
        assert j["resuelto_por"] == str(DOCENTE)
        assert j["resuelto_at"] is not None

    async def test_segunda_vez_es_200_y_no_cambia_quien_ni_cuando(self, esc: Any) -> None:
        esc.db.docentes.add((ADMIN, COMISION))
        p = await _crear_uno(esc)
        primera = (await _req("PATCH", f"/api/v1/pedidos-ayuda/{p['id']}/resolver", DOC)).json()

        r = await _req("PATCH", f"/api/v1/pedidos-ayuda/{p['id']}/resolver", ADM)

        assert r.status_code == 200
        assert r.json()["resuelto_por"] == primera["resuelto_por"] == str(DOCENTE)
        assert r.json()["resuelto_at"] == primera["resuelto_at"]

    async def test_docente_ajeno_404_y_no_cambia(self, esc: Any) -> None:
        p = await _crear_uno(esc)

        r = await _req("PATCH", f"/api/v1/pedidos-ayuda/{p['id']}/resolver", DOC_AJENO)

        assert r.status_code == 404
        assert esc.db.objs[uuid.UUID(p["id"])].estado == "pendiente"

    async def test_supervision_resuelve_sin_estar_asignada(self, esc: Any) -> None:
        p = await _crear_uno(esc)
        r = await _req("PATCH", f"/api/v1/pedidos-ayuda/{p['id']}/resolver", ADM)
        assert r.status_code == 200
        assert r.json()["resuelto_por"] == str(ADMIN)

    async def test_pedido_inexistente_404(self, esc: Any) -> None:
        r = await _req("PATCH", f"/api/v1/pedidos-ayuda/{uuid.uuid4()}/resolver", DOC)
        assert r.status_code == 404

    async def test_alumno_no_resuelve_403(self, esc: Any) -> None:
        p = await _crear_uno(esc)
        r = await _req("PATCH", f"/api/v1/pedidos-ayuda/{p['id']}/resolver", ALU)
        assert r.status_code == 403
        assert esc.db.objs[uuid.UUID(p["id"])].estado == "pendiente"

    async def test_loguea_resuelto_sin_el_mensaje(self, esc: Any) -> None:
        r0 = await _post(_body(mensaje="texto privado del alumno"))
        with capture_logs() as logs:
            await _req("PATCH", f"/api/v1/pedidos-ayuda/{r0.json()['id']}/resolver", DOC)
        resueltos = [x for x in logs if x["event"] == "pedido_ayuda_resuelto"]
        assert len(resueltos) == 1
        assert "texto privado" not in str(resueltos[0])


class TestListarDocente:
    async def test_alumno_no_lista_la_comision_403(self, esc: Any) -> None:
        r = await _req("GET", f"/api/v1/pedidos-ayuda?comision_id={COMISION}", ALU)
        assert r.status_code == 403

    async def test_docente_ajeno_404(self, esc: Any) -> None:
        r = await _req("GET", f"/api/v1/pedidos-ayuda?comision_id={COMISION}", DOC_AJENO)
        assert r.status_code == 404

    async def test_estado_invalido_422(self, esc: Any) -> None:
        r = await _req("GET", f"/api/v1/pedidos-ayuda?comision_id={COMISION}&estado=x", DOC)
        assert r.status_code == 422
