"""`_assert_tp_de_mi_comision`: el guard que entro con 47 lineas y CERO tests.

El commit `e3f68c5` agrego el guard a los dos endpoints de sincronizacion de
rubricas con Active-IA (`GET /activeia/tp/{id}/sincronizacion` y
`POST /activeia/tp/{id}/sincronizar`) y no dejo una sola linea de test. La
mutacion que sobrevivia intacta era romper el JOIN:

    uc.comision_id = tp.comision_id   ->   uc.tenant_id = tp.tenant_id

Con esa version el guard sigue devolviendo lo mismo que el original para todo
usuario que este en ALGUNA comision del tenant — que en produccion son todos los
docentes. O sea: el guard queda de adorno y nadie se entera.

Lo que queda abierto si no funciona no es solo lectura. `sincronizar` empuja el
TP con la cuenta de Active-IA **del docente que llama**, y pisa
`activeia_rubrica_ejercicio`, que es UNICA por `(tenant_id, ejercicio_id)` y no
lleva comision ni docente. Un docente ajeno le deja al docente legitimo un
vinculo apuntando a la rubrica de una cuenta que no es suya; y como `rubrica_id`
entra en la clave de idempotencia de `correcciones_ia`, la correccion previa deja
de encontrarse y se paga otra corrida sobre el mismo codigo.

## Por que estos tests van contra Postgres y no contra un doble

Porque la mutacion que importa vive DENTRO del SQL. Un test que mockea
`db.execute` y le devuelve una fila fija no puede distinguir
`uc.comision_id = tp.comision_id` de `uc.tenant_id = tp.tenant_id`: el doble
contesta lo mismo a las dos. El escenario que las separa —docente en la comision
A, TP de la comision B, MISMO tenant— solo existe si hay una base atras.

## La identidad con la que se prueba

Los tests corren con `docente_prod`, o sea `X-User-Roles: "estudiante,docente"`,
que es lo que el api-gateway emite HOY para todo usuario logueado con Clerk. Con
`"docente"` a secas estos tests seguirian pasando, pero estarian probando una
identidad que produccion nunca manda. Ver el docstring de
`tests/unit/test_scope_con_roles_de_produccion.py`.

Escenario y limpieza: fixture `scope_setup` en `conftest.py`.
"""

from __future__ import annotations

import os
import uuid
from datetime import date, timedelta

import pytest
from evaluation_service.config import settings
from evaluation_service.main import app
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

DB_URL = os.environ.get(
    "EVAL_TEST_DB_URL",
    "postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/academic_main",
)

SINC = "/api/v1/activeia/tp/{tp}/sincronizacion"
SINCRONIZAR = "/api/v1/activeia/tp/{tp}/sincronizar"

# El literal exacto que el guard devuelve. Se assertea junto con el status
# porque las dos mitades importan: el 404 para no confirmar que la TP existe, y
# el texto para que el body no reabra el oraculo que el status cerro.
NO_EXISTE = "Trabajo practico no existe"


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


# ── PoC del leak: el docente ajeno del MISMO tenant ────────────────────────


async def test_docente_ajeno_no_lee_la_sincronizacion_de_otra_comision(
    scope_setup: dict,
) -> None:
    """EL test del archivo. Es el unico que mata la mutacion del JOIN.

    El docente esta en `usuarios_comision` de la comision A. La TP es de la
    comision B. Mismo tenant, asi que la RLS no lo frena: lo unico que lo frena
    es que el JOIN sea por `comision_id`. Con el JOIN por `tenant_id` este
    request devuelve 200 con los titulos y los `rubrica_id` de la comision
    ajena.
    """
    async with _client() as client:
        resp = await client.get(
            SINC.format(tp=scope_setup["tp_ajena"]), headers=scope_setup["docente_prod"]
        )
    assert resp.status_code == 404, resp.text
    assert resp.json()["detail"] == NO_EXISTE, resp.text


async def test_docente_ajeno_no_empuja_rubricas_a_otra_comision(
    scope_setup: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    """El mismo leak en el endpoint que ESCRIBE, que es el que hace dano.

    El kill switch (`_assert_habilitado`) corre ANTES del guard, y esta apagado
    por default: sin prenderlo, este endpoint devuelve 503 para todo el mundo y
    un test que solo mirara "no es 200" pasaria sin que el guard exista. Por eso
    se prende el flag y se assertea **404 y no 503** — el status distingue "no
    sos de esta comision" de "la integracion esta apagada".
    """
    monkeypatch.setattr(settings, "activeia_enabled", True)
    async with _client() as client:
        resp = await client.post(
            SINCRONIZAR.format(tp=scope_setup["tp_ajena"]), headers=scope_setup["docente_prod"]
        )
    assert resp.status_code == 404, resp.text
    assert resp.json()["detail"] == NO_EXISTE, resp.text


async def test_la_tp_ajena_es_indistinguible_de_una_que_no_existe(
    scope_setup: dict,
) -> None:
    """Sin esto el 404 sigue siendo un oraculo de existencia.

    Un docente que prueba ids al azar tiene que ver EXACTAMENTE la misma
    respuesta para una TP que no existe y para una que existe en la comision de
    al lado. Si difieren en status o en `detail`, el id de una comision ajena
    vuelve a confirmar que hay algo ahi.
    """
    async with _client() as client:
        ajena = await client.get(
            SINC.format(tp=scope_setup["tp_ajena"]), headers=scope_setup["docente_prod"]
        )
        fantasma = await client.get(
            SINC.format(tp=uuid.uuid4()), headers=scope_setup["docente_prod"]
        )
    assert ajena.status_code == fantasma.status_code == 404
    assert ajena.json() == fantasma.json()


async def test_docente_sin_ninguna_comision_no_lee_nada(scope_setup: dict) -> None:
    """Un docente sin filas en `usuarios_comision` no llega a ninguna TP."""
    huerfano = scope_setup["headers"](uuid.uuid4(), "estudiante,docente")
    async with _client() as client:
        resp = await client.get(SINC.format(tp=scope_setup["tp_propia"]), headers=huerfano)
    assert resp.status_code == 404, resp.text
    assert resp.json()["detail"] == NO_EXISTE, resp.text


async def test_un_ALUMNO_logueado_tampoco_llega_a_la_TP(scope_setup: dict) -> None:
    """El guard de membresia es lo unico que frena al alumno. El de rol no.

    `require_correccion_ia` corre antes y NO lo frena: con
    `clerk_base_roles = "estudiante,docente"` todo usuario logueado trae
    `docente`, que esta en `CORRECCION_IA_ROLES`. (El caso negativo de
    `tests/unit/test_activeia_credenciales.py` usaba `{"estudiante"}` a secas y
    afirmaba una proteccion que en este deploy no existe.)

    Lo que si lo frena es esto: el alumno vive en `inscripciones`, no en
    `usuarios_comision`, asi que el JOIN no encuentra fila y sale 404. Se prueba
    contra la TP de su PROPIA comision a proposito — si estuviera inscripto y el
    guard mirara inscripciones, este test seria el que lo notara.
    """
    alumno = scope_setup["headers"](uuid.uuid4(), "estudiante,docente")
    async with _client() as client:
        resp = await client.get(SINC.format(tp=scope_setup["tp_propia"]), headers=alumno)
    assert resp.status_code == 404, resp.text
    assert resp.json()["detail"] == NO_EXISTE, resp.text


async def test_una_membresia_dada_de_baja_no_alcanza(scope_setup: dict) -> None:
    """`deleted_at IS NULL` no es decorativo.

    A un docente al que le sacaron la comision le queda la fila en
    `usuarios_comision` con `deleted_at`. Sin ese predicado sigue entrando a las
    TPs de una comision que ya no es suya.
    """
    ex_docente, membresia = uuid.uuid4(), uuid.uuid4()
    engine = create_async_engine(DB_URL)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        await s.execute(
            text("SELECT set_config('app.current_tenant', :t, true)"),
            {"t": str(scope_setup["tenant_id"])},
        )
        await s.execute(
            text(
                "INSERT INTO usuarios_comision "
                "(id, tenant_id, comision_id, user_id, rol, fecha_desde, deleted_at) "
                "VALUES (:id, :t, :c, :u, 'titular', :fd, now())"
            ),
            {
                "id": str(membresia),
                "t": str(scope_setup["tenant_id"]),
                "c": str(scope_setup["comision_propia"]),
                "u": str(ex_docente),
                "fd": date.today() - timedelta(days=90),
            },
        )
        await s.commit()
    try:
        headers = scope_setup["headers"](ex_docente, "estudiante,docente")
        async with _client() as client:
            resp = await client.get(SINC.format(tp=scope_setup["tp_propia"]), headers=headers)
        assert resp.status_code == 404, resp.text
        assert resp.json()["detail"] == NO_EXISTE, resp.text
    finally:
        async with factory() as s:
            await s.execute(
                text("SELECT set_config('app.current_tenant', :t, true)"),
                {"t": str(scope_setup["tenant_id"])},
            )
            await s.execute(
                text("DELETE FROM usuarios_comision WHERE id = :id"), {"id": str(membresia)}
            )
            await s.commit()
        await engine.dispose()


# ── El guard NO puede romper al docente legitimo ni a coordinacion ─────────


async def test_el_docente_de_LA_comision_sigue_leyendo_su_TP(scope_setup: dict) -> None:
    """Regresion critica: un guard que devuelve 404 a todo el mundo tambien
    "cierra" el agujero, y deja al docente sin ver su propia sincronizacion."""
    async with _client() as client:
        resp = await client.get(
            SINC.format(tp=scope_setup["tp_propia"]), headers=scope_setup["docente_prod"]
        )
    assert resp.status_code == 200, resp.text
    assert "ejercicios" in resp.json()


async def test_el_docente_de_LA_comision_pasa_el_guard_al_sincronizar(
    scope_setup: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    """En el POST, el docente propio tiene que PASAR el guard.

    Lo que lo frena despues es no tener cuenta de Active-IA conectada, que es un
    400 distinto — y esa distincion es justo lo que prueba que llego mas alla
    del guard. Assertear "no es 200" habria pasado igual con el guard rechazando
    a todos.
    """
    monkeypatch.setattr(settings, "activeia_enabled", True)
    async with _client() as client:
        resp = await client.post(
            SINCRONIZAR.format(tp=scope_setup["tp_propia"]), headers=scope_setup["docente_prod"]
        )
    assert resp.status_code != 404, resp.text
    assert resp.status_code == 400, resp.text


async def test_coordinacion_lee_cross_comision_a_proposito(scope_setup: dict) -> None:
    """`_OVERSIGHT` es un bypass deliberado: docente_admin corrige cross-comision."""
    async with _client() as client:
        resp = await client.get(
            SINC.format(tp=scope_setup["tp_ajena"]), headers=scope_setup["admin"]
        )
    assert resp.status_code == 200, resp.text


async def test_el_bypass_de_oversight_no_se_regala_al_docente_comun(
    scope_setup: dict,
) -> None:
    """Los roles de produccion NO incluyen ninguno de `_OVERSIGHT`.

    Si alguien agregara `"docente"` al frozenset `_OVERSIGHT`, el guard entero
    quedaria en no-op para todo el piloto y ningun otro test de este archivo lo
    notaria: todos los rechazos vendrian del bypass y no del JOIN.
    """
    from evaluation_service.routes.activeia import _OVERSIGHT

    assert not (_OVERSIGHT & {"docente", "estudiante", "jtp", "auxiliar"})
