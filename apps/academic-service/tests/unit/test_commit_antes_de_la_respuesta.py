"""El commit tiene que pasar ANTES de que la respuesta salga.

El bug
------
`get_db` (`auth/dependencies.py`) abre `tenant_session`, que tiene el
`await session.commit()` en el **teardown del generador**. FastAPI corre ese
teardown en el `AsyncExitStack` de la request, y ese stack se cierra DESPUES de
`await response(scope, receive, send)` — o sea, despues de que la respuesta ya
salio para el cliente. Se ve en el fuente de la version instalada
(`fastapi/routing.py::request_response`)::

    async with AsyncExitStack() as request_stack:      # <- teardown de `scope="request"`
        async with AsyncExitStack() as function_stack: # <- teardown de `scope="function"`
            response = await f(request)
        # aca cierra function_stack
        await response(scope, receive, send)           # <- LA RESPUESTA SALE
    # aca cierra request_stack

Y ningun handler de ejercicios/TPs commitea por su cuenta: los unicos `commit()`
explicitos del academic-service estan en `routes/instrumentos.py` y
`routes/student_profiles.py`. O sea que el 100% de las escrituras dependia de
ese commit tardio.

Que rompe en la practica
------------------------
El smoke E2E, sobre el mismo commit y relanzando la misma corrida:

    POST ejercicio                 -> 201
    POST TP                        -> 201
    POST /{tp}/ejercicios          -> 201
    POST /{tp}/publish             -> 422 "Una TP no se puede publicar vacia"

El `add` contesto 201 y el `publish`, milisegundos despues, no vio la
asociacion. Se agrupa en los ~400 ms posteriores al bloque de Java (27 s de
Docker + JVM) que satura el runner de 4 vCPU. NO es flaky: es una carrera que
el orden de operaciones garantiza.

Y le pega a un docente real:
`web-teacher/.../TareasPracticasView.tsx:1352-1362` hace exactamente esa
secuencia — `tpEjerciciosApi.add` en loop y `fetchPairs()` inmediato.

La variante grave del mismo bug: si el teardown explota, el cliente ya recibio
`200 OK` con el id de una fila que despues no existe.

Que verifican estos tests
-------------------------
El ORDEN, no un `sleep`. Un middleware ASGI anota el momento exacto en que sale
`http.response.start`; la sesion falsa anota su `commit`. Si el commit queda
despues de ese marcador, el test cae. Un test con `sleep` mediria la ventana,
no la propiedad — y pasaria en verde el dia que la maquina este rapida.

Se ejercita el `get_db` DE PRODUCCION (solo se reemplaza `tenant_session` por
una sesion falsa, para no necesitar Postgres): si alguien le saca el
`scope="function"`, estos tests caen.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from uuid import UUID, uuid4

import pytest
from academic_service.auth import dependencies as deps
from academic_service.auth.dependencies import User, get_current_user, get_db
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient

TENANT = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")


class _SesionFalsa:
    """Lo minimo que `tenant_session` le da al handler, mas el registro."""

    def __init__(self, orden: list[str]) -> None:
        self._orden = orden

    async def commit(self) -> None:
        self._orden.append("commit")

    async def rollback(self) -> None:
        self._orden.append("rollback")


def _tenant_session_falsa(orden: list[str], *, commit_explota: bool = False) -> Any:
    """Copia fiel de la forma de `db/session.py::tenant_session`.

    Misma estructura —`yield` y despues `commit()`, `rollback()` en el except—
    para que lo que se mide sea CUANDO corre ese teardown, no otra cosa.
    """

    @asynccontextmanager
    async def _fake(tenant_id: UUID) -> AsyncIterator[_SesionFalsa]:
        session = _SesionFalsa(orden)
        try:
            yield session
            if commit_explota:
                orden.append("commit-explota")
                raise RuntimeError("la base rechazo el commit")
            await session.commit()
        except Exception:
            await session.rollback()
            raise

    return _fake


def _app(orden: list[str]) -> FastAPI:
    app = FastAPI()

    @app.post("/escribir", status_code=201)
    async def escribir(db: Any = Depends(get_db)) -> dict[str, str]:
        orden.append("handler")
        return {"id": str(uuid4())}

    async def _usuario_de_prueba() -> User:
        return User(
            id=uuid4(),
            tenant_id=TENANT,
            email="docente@test.local",
            roles={"docente"},
            realm=str(TENANT),
        )

    app.dependency_overrides[get_current_user] = _usuario_de_prueba
    return app


def _transporte_que_anota(app: FastAPI, orden: list[str]) -> ASGITransport:
    """ASGITransport que anota `http.response.start` en la linea de tiempo.

    Es el momento REAL en que la respuesta sale hacia el cliente. Comparar el
    commit contra esto —y no contra el retorno del handler— es lo que hace que
    el test hable del bug y no de otra cosa.

    Se anota tambien el status: la pregunta de los casos de error no es "salio
    una respuesta" (siempre sale, `ServerErrorMiddleware` manda un 500 antes de
    re-levantar) sino **cual**. Un 500 despues de un rollback es correcto; un
    201 despues de un commit que exploto es el bug.
    """
    interna = app

    async def _app(scope: Any, receive: Any, send: Any) -> None:
        async def _send(mensaje: dict[str, Any]) -> None:
            if mensaje["type"] == "http.response.start":
                orden.append(f"respuesta:{mensaje['status']}")
            await send(mensaje)

        await interna(scope, receive, _send)

    return ASGITransport(app=_app)


@pytest.fixture
def orden() -> list[str]:
    return []


async def test_el_commit_sale_antes_que_la_respuesta(
    orden: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """La propiedad entera del fix, en una linea de tiempo.

    Verificado por reversion: sacandole el `scope="function"` a `get_db`, el
    orden pasa a `handler -> respuesta -> commit` y este test cae.
    """
    monkeypatch.setattr(deps, "tenant_session", _tenant_session_falsa(orden))
    app = _app(orden)

    async with AsyncClient(
        transport=_transporte_que_anota(app, orden), base_url="http://test"
    ) as c:
        resp = await c.post("/escribir")

    assert resp.status_code == 201, resp.text
    assert orden == ["handler", "commit", "respuesta:201"], orden


async def test_si_el_commit_explota_el_cliente_NO_recibe_un_201(
    orden: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """La variante grave, que es el motivo por el que el fix vale la pena.

    Con el commit despues de la respuesta, un teardown que explota dejaba al
    cliente con `201 {"id": ...}` de una fila que NO existe — el peor resultado
    posible, porque el cliente guarda ese id y lo usa. Ahora la escritura
    fallida se ve como lo que es: un 500.

    **Este es el cambio de manejo de errores que el fix introduce, a
    proposito.** Una escritura que no pudo commitear deja de contestar 2xx.
    """
    monkeypatch.setattr(deps, "tenant_session", _tenant_session_falsa(orden, commit_explota=True))
    app = _app(orden)

    with pytest.raises(RuntimeError, match="la base rechazo el commit"):
        async with AsyncClient(
            transport=_transporte_que_anota(app, orden), base_url="http://test"
        ) as c:
            await c.post("/escribir")

    # Lo que importa: el 201 NUNCA salio. Sale un 500, que es la verdad.
    assert orden == ["handler", "commit-explota", "rollback", "respuesta:500"], orden


async def test_un_handler_que_revienta_sigue_haciendo_rollback(
    orden: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """El fix no puede romper el camino de error que ya andaba.

    `tenant_session` hace `rollback()` cuando el bloque levanta. Mover el
    teardown de stack no cambia que la excepcion del handler llegue al
    generador; este test lo deja escrito.
    """
    monkeypatch.setattr(deps, "tenant_session", _tenant_session_falsa(orden))
    app = _app(orden)

    @app.post("/explotar", status_code=201)
    async def explotar(db: Any = Depends(get_db)) -> dict[str, str]:
        orden.append("handler")
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        async with AsyncClient(
            transport=_transporte_que_anota(app, orden), base_url="http://test"
        ) as c:
            await c.post("/explotar")

    assert orden == ["handler", "rollback", "respuesta:500"], orden
    assert "commit" not in orden
