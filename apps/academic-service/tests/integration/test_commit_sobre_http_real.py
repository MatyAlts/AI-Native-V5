"""El orden del commit, sobre HTTP de verdad y con Postgres de verdad.

Por que este archivo existe aparte de `tests/unit/test_commit_antes_de_la_respuesta.py`
-------------------------------------------------------------------------------------
Ese test mide el orden con un `ASGITransport` que anota `http.response.start`, y
esta bien: mata la mutacion de sacarle el `scope="function"` a `get_db`
(verificado). Pero hay una mitad que un transporte in-process **no puede**
mostrar, y es la que un cliente real ve:

Con `ASGITransport`, httpx corre la app como una corrutina y **re-levanta** la
excepcion del teardown al llamador. Por eso ese test tiene que envolverse en
`pytest.raises(RuntimeError)` y mirar un `send` instrumentado. Un cliente HTTP
real no recibe una excepcion: recibe **un numero**. Y con el bug puesto el numero
que recibe es `201`, porque los bytes de la respuesta ya salieron por el socket
antes de que el commit explotara — el servidor loguea el error y el cliente se
queda con el id de una fila que no existe. Esa es la variante grave del bug, y
la unica forma de verla como la ve el cliente es con un servidor ASGI real.

Ademas, la sesion no es un doble: es `tenant_session` contra Postgres. Lo que se
prueba es el cableado de produccion entero —`get_db` -> `_tenant_db`
(`scope="function"`) -> `tenant_session` -> `commit`— y no una copia de su forma.

Como se hace explotar el commit sin trucar nada
-----------------------------------------------
Con un `UNIQUE ... DEFERRABLE INITIALLY DEFERRED` sobre una tabla de usar y
tirar. Postgres valida ese constraint recien en el `COMMIT`, asi que el `INSERT`
del handler pasa limpio y la falla ocurre exactamente en el teardown, que es
donde el bug vive. Sin `sleep`, sin monkeypatch de la sesion, sin ventana que se
cierre el dia que la maquina este rapida.

Correr:
    ACADEMIC_DB_URL=postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/academic_main \
        uv run pytest apps/academic-service/tests/integration/test_commit_sobre_http_real.py -v
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import socket
import uuid
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
import pytest_asyncio
import uvicorn
from academic_service.auth.dependencies import User, get_current_user, get_db
from academic_service.config import settings as _settings
from fastapi import Depends, FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

_DSN = os.environ.get("ACADEMIC_DB_URL") or os.environ.get("EVAL_TEST_DB_URL")

pytestmark = pytest.mark.skipif(
    not _DSN,
    reason="Sin ACADEMIC_DB_URL: este test necesita Postgres real y un uvicorn real",
)

TENANT = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")

# El DSN con el que arranca el servicio, para devolverlo al terminar.
_DSN_ORIGINAL = _settings.academic_db_url

# Tabla de usar y tirar. Nombre fijo para poder limpiarla si una corrida muere a
# la mitad; se recrea desde cero en cada sesion de tests.
TABLA = "_probe_commit_orden"

_DDL = f"""
DROP TABLE IF EXISTS {TABLA};
CREATE TABLE {TABLA} (
    id    uuid PRIMARY KEY,
    marca text NOT NULL,
    CONSTRAINT uq_{TABLA}_marca UNIQUE (marca) DEFERRABLE INITIALLY DEFERRED
);
"""


async def _resetear_engine_del_servicio(dsn: str | None) -> None:
    """Tira el engine cacheado en `db/session.py` para que lo cree este loop.

    Y apunta `settings.academic_db_url` al DSN que se le pase. Sin eso el
    servicio entra con su DSN por default (`academic_user`) mientras la tabla la
    creo `postgres`, y el handler muere con `permission denied for table`. Se
    pasa `None` en el teardown para devolver el valor original y no contaminar
    al resto de la suite.
    """
    from academic_service.config import settings
    from academic_service.db import session as sess

    settings.academic_db_url = dsn if dsn is not None else _DSN_ORIGINAL
    if sess._engine is not None:
        await sess._engine.dispose()
    sess._engine = None
    sess._session_factory = None


def _puerto_libre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _app() -> FastAPI:
    """App minima cableada al `get_db` DE PRODUCCION.

    Lo unico que se reemplaza es `get_current_user` (no hay gateway ni JWT en el
    test). `get_db`, `_tenant_db` y `tenant_session` son los de verdad: si
    alguien le saca el `scope="function"` a `get_db`, este cableado cambia de
    comportamiento y los tests de abajo lo ven.
    """
    app = FastAPI()

    @app.post("/escribir", status_code=201)
    async def escribir(marca: str, db: AsyncSession = Depends(get_db)) -> dict[str, str]:
        fila = uuid.uuid4()
        await db.execute(
            text(f"INSERT INTO {TABLA} (id, marca) VALUES (:i, :m)"),
            {"i": str(fila), "m": marca},
        )
        return {"id": str(fila), "marca": marca}

    @app.get("/contar")
    async def contar(marca: str, db: AsyncSession = Depends(get_db)) -> dict[str, int]:
        n = (
            await db.execute(text(f"SELECT count(*) FROM {TABLA} WHERE marca = :m"), {"m": marca})
        ).scalar_one()
        return {"n": int(n)}

    async def _usuario() -> User:
        return User(
            id=uuid.uuid4(),
            tenant_id=TENANT,
            email="docente@test.local",
            roles={"docente"},
            realm=str(TENANT),
        )

    app.dependency_overrides[get_current_user] = _usuario
    return app


@pytest_asyncio.fixture
async def servidor() -> AsyncIterator[str]:
    """uvicorn real en un puerto real. Devuelve la base_url."""
    engine = create_async_engine(_DSN or "")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        for sentencia in _DDL.strip().split(";"):
            if sentencia.strip():
                await s.execute(text(sentencia))
        await s.commit()

    # `db/session.py` cachea el engine y el sessionmaker en globals. Con un event
    # loop por test (pytest-asyncio), el engine del test anterior queda atado al
    # loop viejo y el segundo test muere con "attached to a different loop". Se
    # resetean acá y se disponen al final.
    await _resetear_engine_del_servicio(_DSN)

    puerto = _puerto_libre()
    config = uvicorn.Config(
        _app(), host="127.0.0.1", port=puerto, log_level="error", lifespan="off"
    )
    server = uvicorn.Server(config)
    tarea = asyncio.create_task(server.serve())
    try:
        for _ in range(200):
            if server.started:
                break
            await asyncio.sleep(0.02)
        assert server.started, "uvicorn no arranco"
        yield f"http://127.0.0.1:{puerto}"
    finally:
        server.should_exit = True
        with contextlib.suppress(asyncio.TimeoutError):
            await asyncio.wait_for(tarea, timeout=10)
        async with factory() as s:
            await s.execute(text(f"DROP TABLE IF EXISTS {TABLA}"))
            await s.commit()
        await engine.dispose()
        await _resetear_engine_del_servicio(None)


async def _get_json(url: str, **params: Any) -> Any:
    async with httpx.AsyncClient(timeout=10) as c:
        return (await c.get(url, params=params)).json()


class TestLoQueVeUnClienteDeVerdad:
    async def test_lo_que_escribio_un_201_se_lee_en_el_request_siguiente(
        self, servidor: str
    ) -> None:
        """El read-after-write, extremo a extremo.

        Dos requests HTTP separados, conexiones separadas, contra Postgres real.
        Es la secuencia que hace el web-teacher (`add` en loop y `fetchPairs()`
        inmediato) y la que en el smoke E2E terminaba en
        `422 "Una TP no se puede publicar vacia"`.
        """
        marca = f"ok-{uuid.uuid4()}"
        async with httpx.AsyncClient(timeout=10) as c:
            resp = await c.post(f"{servidor}/escribir", params={"marca": marca})
        assert resp.status_code == 201, resp.text

        # Cliente nuevo = conexion nueva, como la hace un frontend.
        assert await _get_json(f"{servidor}/contar", marca=marca) == {"n": 1}

    async def test_un_commit_que_explota_NO_le_deja_al_cliente_un_201(self, servidor: str) -> None:
        """La variante grave, y la que el transporte in-process no puede mostrar.

        El `UNIQUE` es `DEFERRABLE INITIALLY DEFERRED`: el `INSERT` del handler
        pasa y la violacion salta recien en el `COMMIT`, o sea en el teardown de
        la dependencia. Con `scope="function"` ese teardown corre ANTES de
        emitir la respuesta, la excepcion sube y el cliente recibe **5xx**. Sin
        el scope, los bytes del `201` ya salieron por el socket: el cliente se
        queda con el id de una fila que no existe y el error solo aparece en el
        log del servidor.

        Con `ASGITransport` esta distincion no se ve: httpx re-levanta la
        excepcion al llamador en los dos casos.
        """
        marca = f"dup-{uuid.uuid4()}"
        async with httpx.AsyncClient(timeout=10) as c:
            primero = await c.post(f"{servidor}/escribir", params={"marca": marca})
            assert primero.status_code == 201, primero.text

            segundo = await c.post(f"{servidor}/escribir", params={"marca": marca})

        assert segundo.status_code >= 500, (
            f"el cliente recibio {segundo.status_code} sobre una escritura que no "
            "commiteo: se queda con el id de una fila que no existe"
        )

        # Y la mitad que le da sentido al status: la fila NO quedo.
        assert await _get_json(f"{servidor}/contar", marca=marca) == {"n": 1}
