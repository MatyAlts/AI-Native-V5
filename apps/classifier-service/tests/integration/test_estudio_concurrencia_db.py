"""Operaciones concurrentes serializadas (tarea 8.2, design D10b, spec estudio-codificacion).

Dos pedidos HTTP reales contra la app, cada uno con su sesión de Postgres.
Para que la carrera ocurra siempre, el test toma antes `FOR UPDATE` sobre la
fila del estudio desde otra conexión, lanza los dos pedidos, espera en
`pg_stat_activity` a que AMBOS estén bloqueados esperando un lock y recién ahí
suelta. Cada escenario se repite varias veces; todas las repeticiones tienen
que terminar en uno de los dos resultados válidos de la spec.
"""

from __future__ import annotations

import asyncio
import copy

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

REPETICIONES = 4


async def _con_barrera(estudio, *pedidos):
    """Ejecuta los pedidos con la fila del estudio bloqueada hasta que todos esperan."""
    engine = create_async_engine(estudio.url)
    try:
        async with engine.connect() as conn:
            await conn.execute(
                text("SELECT set_config('app.current_tenant', :t, true)"),
                {"t": str(estudio.tenant_id)},
            )
            await conn.execute(
                text("SELECT id FROM estudio_codificacion WHERE clave = :c FOR UPDATE"),
                {"c": estudio.clave},
            )
            tareas = [asyncio.create_task(p) for p in pedidos]
            for _ in range(200):
                # Las estadísticas se congelan por transacción: hay que limpiar
                # el snapshot en cada sondeo o se ve siempre la primera lectura.
                await conn.execute(text("SELECT pg_stat_clear_snapshot()"))
                esperando = (
                    await conn.execute(
                        text(
                            "SELECT count(*) FROM pg_stat_activity WHERE datname = current_database() "
                            "AND wait_event_type = 'Lock' AND pid <> pg_backend_pid()"
                        )
                    )
                ).scalar_one()
                if esperando >= len(pedidos):
                    break
                await asyncio.sleep(0.025)
            else:
                raise AssertionError(
                    "los pedidos no llegaron a bloquearse: la barrera no probó nada"
                )
            await conn.rollback()
            return await asyncio.gather(*tareas)
    finally:
        await engine.dispose()


async def _guardar(estudio, item_id, cuerpo):
    return await estudio.pedir("PUT", f"/items/{item_id}/mi-etiqueta", estudio.c1, json=cuerpo)


async def test_guardado_contra_cierre(estudio_http, etiqueta_reflexiva) -> None:
    resultados = set()
    for vuelta in range(REPETICIONES):
        estudio_http.clave = f"concurrencia-cierre-{vuelta}"
        estudio_http.tenant_id = estudio_http.tenant_id  # mismo tenant, estudio nuevo
        await estudio_http.crear()
        await estudio_http.preparar(n=1)
        (item,) = await estudio_http.items()
        assert (
            await _guardar(estudio_http, item["item_id"], etiqueta_reflexiva)
        ).status_code == 200
        parcial = {"respuestas": {"d1": {"valor": "presente", "cita": "turno 1"}}}
        guardado, cierre = await _con_barrera(
            estudio_http,
            _guardar(estudio_http, item["item_id"], parcial),
            estudio_http.pedir("POST", "/mi-codificacion/cerrar", estudio_http.c1),
        )
        par = (guardado.status_code, cierre.status_code)
        assert par in {(200, 422), (409, 200)}, (par, guardado.text, cierre.text)
        if cierre.status_code == 200:
            regimen = await estudio_http.sql(
                "SELECT e.regimen FROM estudio_etiqueta e JOIN estudio_membresia m ON m.id = e.membresia_id "
                "JOIN estudio_codificacion c ON c.id = m.estudio_id WHERE c.clave = :c",
                {"c": estudio_http.clave},
            )
            assert regimen == [{"regimen": "reflexiva"}]
        resultados.add(par)
    print("resultados guardado/cierre:", sorted(resultados))


async def test_guardado_contra_cambio_de_vigente(estudio_http, etiqueta_reflexiva) -> None:
    for vuelta in range(REPETICIONES):
        estudio_http.clave = f"concurrencia-vigente-{vuelta}"
        await estudio_http.crear()
        await estudio_http.preparar(n=1)
        await estudio_http.codebook("v1", vigente=False, congelar=True)
        (item,) = await estudio_http.items()
        guardado, cambio = await _con_barrera(
            estudio_http,
            _guardar(estudio_http, item["item_id"], copy.deepcopy(etiqueta_reflexiva)),
            estudio_http.pedir(
                "PUT", "/codebook-vigente", estudio_http.investigador, json={"etiqueta": "v1"}
            ),
        )
        version = await estudio_http.sql(
            "SELECT v.etiqueta FROM estudio_etiqueta e JOIN codebook_version v ON v.id = e.codebook_version_id "
            "JOIN estudio_codificacion c ON c.id = v.estudio_id WHERE c.clave = :c",
            {"c": estudio_http.clave},
        )
        par = (guardado.status_code, cambio.status_code)
        assert par in {(200, 200), (200, 409)}, (par, guardado.text, cambio.text)
        esperado = "v1" if cambio.status_code == 200 else "v0"
        assert version == [{"etiqueta": esperado}], (par, version)


async def test_guardado_contra_reemplazo_de_muestra(estudio_http, etiqueta_reflexiva) -> None:
    for vuelta in range(REPETICIONES):
        estudio_http.clave = f"concurrencia-muestra-{vuelta}"
        await estudio_http.crear()
        await estudio_http.preparar(n=1)
        (item,) = await estudio_http.items()
        nuevo = estudio_http.ctr.agregar()
        guardado, carga = await _con_barrera(
            estudio_http,
            _guardar(estudio_http, item["item_id"], copy.deepcopy(etiqueta_reflexiva)),
            estudio_http.cargar_muestra([nuevo]),
        )
        par = (guardado.status_code, carga.status_code)
        assert par in {(200, 409), (404, 200)}, (par, guardado.text, carga.text)


# ── Primer uso de una membresía contra su revocación (verify-2, N1) ─────────
# El primer uso ata el `user_id` (UPDATE de la membresía). Si lo hace ANTES de
# tomar la fila del estudio y la revocación ya tiene el estudio y va por la
# membresía, cada una espera a la otra: deadlock -> 500. La barrera fuerza esa
# intercalación: la revocación entra primero a la cola del lock del estudio y
# recién después el primer uso. Con el orden de D10b (estudio, luego
# membresía), el primer uso espera sin haber tocado la membresía.


async def _esperando(conn) -> int:
    await conn.execute(text("SELECT pg_stat_clear_snapshot()"))
    return (
        await conn.execute(
            text(
                "SELECT count(*) FROM pg_stat_activity WHERE datname = current_database() "
                "AND wait_event_type = 'Lock' AND pid <> pg_backend_pid()"
            )
        )
    ).scalar_one()


async def _barrera_en_orden(estudio, *pedidos):
    """Como `_con_barrera`, pero lanza cada pedido recién cuando el anterior ya
    espera un lock: fija el orden de llegada a la cola del estudio."""
    engine = create_async_engine(estudio.url)
    try:
        async with engine.connect() as conn:
            await conn.execute(
                text("SELECT set_config('app.current_tenant', :t, true)"),
                {"t": str(estudio.tenant_id)},
            )
            await conn.execute(
                text("SELECT id FROM estudio_codificacion WHERE clave = :c FOR UPDATE"),
                {"c": estudio.clave},
            )
            tareas = []
            for n, pedido in enumerate(pedidos, start=1):
                tareas.append(asyncio.create_task(pedido))
                for _ in range(200):
                    if await _esperando(conn) >= n:
                        break
                    await asyncio.sleep(0.025)
                else:
                    raise AssertionError(
                        "el pedido no llegó a bloquearse: la barrera no probó nada"
                    )
            await conn.rollback()
            return await asyncio.gather(*tareas)
    finally:
        await engine.dispose()


async def _nueva_membresia(estudio, rol: str, persona_de, vuelta: int):
    persona = type(estudio.c1)(estudio.tenant_id, f"n1-{rol}-{vuelta}@ejemplo.org")
    alta = persona_de
    r = await estudio.pedir("POST", "/membresias", alta, json={"email": persona.email, "rol": rol})
    assert r.status_code == 201, r.text
    return persona, r.json()["membresia_id"]


async def test_primer_uso_del_codificador_contra_su_revocacion(
    estudio_http, etiqueta_reflexiva
) -> None:
    await estudio_http.preparar(1)
    item = (await estudio_http.items())[0]["item_id"]
    resultados = []
    for vuelta in range(REPETICIONES):
        persona, mid = await _nueva_membresia(
            estudio_http, "codificador", estudio_http.investigador, vuelta
        )
        revocar, guardar = await _barrera_en_orden(
            estudio_http,
            estudio_http.pedir("DELETE", f"/membresias/{mid}", estudio_http.investigador),
            estudio_http.pedir(
                "PUT", f"/items/{item}/mi-etiqueta", persona, json=etiqueta_reflexiva
            ),
        )
        resultados.append((revocar.status_code, guardar.status_code))
    # La revocación entra primero: el guardado posterior ve la membresía revocada.
    assert resultados == [(200, 403)] * REPETICIONES


@pytest.mark.parametrize("accion", ["crear_version", "alta_membresia"])
async def test_primer_uso_del_investigador_contra_su_revocacion(estudio_http, accion) -> None:
    """`crear_version` pasa por `investigador_con_estudio_bloqueado`;
    `alta_membresia`, por `_estudio_para_gestionar`."""
    resultados = []
    for vuelta in range(REPETICIONES):
        persona, mid = await _nueva_membresia(
            estudio_http, "investigador", estudio_http.admin, vuelta
        )
        if accion == "crear_version":
            pedido = estudio_http.pedir(
                "POST", "/codebook", persona, json={"etiqueta": f"n1-{vuelta}"}
            )
        else:
            pedido = estudio_http.pedir(
                "POST",
                "/membresias",
                persona,
                json={"email": f"n1-alta-{vuelta}@ejemplo.org", "rol": "codificador"},
            )
        revocar, crear = await _barrera_en_orden(
            estudio_http,
            estudio_http.pedir("DELETE", f"/membresias/{mid}", estudio_http.admin),
            pedido,
        )
        resultados.append((revocar.status_code, crear.status_code))
    assert resultados == [(200, 403)] * REPETICIONES
