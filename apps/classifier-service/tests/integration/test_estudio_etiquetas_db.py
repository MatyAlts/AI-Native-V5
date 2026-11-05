"""Etiquetado, historial, cierre y aislamiento (tareas 8.1 y 8.3, design D9, D10).

App real + Postgres real + CTR falso. Esquema de prueba del conftest (regla:
reflexiva si d1 presente, d2 presente y d4 interlocutor; si no, superficial).
"""

from __future__ import annotations

import copy
from uuid import uuid4

import pytest


def _sd(r) -> tuple[int, object]:
    try:
        cuerpo = r.json()
    except ValueError:
        cuerpo = None
    return r.status_code, cuerpo.get("detail") if isinstance(cuerpo, dict) else cuerpo


async def _guardar(estudio, item_id, cuerpo, persona=None):
    return await estudio.pedir(
        "PUT", f"/items/{item_id}/mi-etiqueta", persona or estudio.c1, json=cuerpo
    )


async def _mia(estudio, item_id, persona=None):
    return await estudio.pedir("GET", f"/items/{item_id}/mi-etiqueta", persona or estudio.c1)


async def _cerrar(estudio, persona=None):
    return await estudio.pedir("POST", "/mi-codificacion/cerrar", persona or estudio.c1)


@pytest.fixture
async def listo(estudio_http):
    await estudio_http.preparar(n=2)
    items = await estudio_http.items()
    return estudio_http, [i["item_id"] for i in items]


async def test_con_codebook_borrador_no_se_guarda(estudio_http, etiqueta_reflexiva) -> None:
    await estudio_http.preparar(n=1, congelar=False)
    (item,) = await estudio_http.items()
    r = await _guardar(estudio_http, item["item_id"], etiqueta_reflexiva)
    assert _sd(r) == (409, "codebook_borrador")
    assert await estudio_http.sql("SELECT id FROM estudio_etiqueta") == []


async def test_guardado_parcial_registra_version_y_traza(listo) -> None:
    estudio, items = listo
    r = await _guardar(
        estudio, items[0], {"respuestas": {"d1": {"valor": "presente", "cita": "turno 1"}}}
    )
    assert r.status_code == 200, r.text
    assert (r.json()["regimen"], r.json()["regimen_regla"]) == (None, None)
    filas = await estudio.sql(
        "SELECT e.traza_version, e.codebook_version_id = c.codebook_vigente_id AS vigente, e.respuestas "
        "FROM estudio_etiqueta e, estudio_codificacion c"
    )
    assert filas == [
        {
            "traza_version": "traza_v1",
            "vigente": True,
            "respuestas": {"d1": {"valor": "presente", "cita": "turno 1"}},
        }
    ]
    assert [i["estado"] for i in await estudio.items() if i["item_id"] == items[0]] == ["parcial"]


async def test_regimen_derivado_se_devuelve_y_se_persiste(listo, etiqueta_reflexiva) -> None:
    estudio, items = listo
    r = await _guardar(estudio, items[0], etiqueta_reflexiva)
    assert r.status_code == 200, r.text
    assert (r.json()["regimen"], r.json()["regimen_regla"], r.json()["disiente_de_regla"]) == (
        "reflexiva",
        "reflexiva",
        False,
    )
    filas = await estudio.sql("SELECT regimen, regimen_regla FROM estudio_etiqueta")
    assert filas == [{"regimen": "reflexiva", "regimen_regla": "reflexiva"}]
    assert [i["estado"] for i in await estudio.items() if i["item_id"] == items[0]] == ["completa"]


async def test_regimen_distinto_del_derivado_da_422_y_no_guarda(listo, etiqueta_reflexiva) -> None:
    estudio, items = listo
    r = await _guardar(estudio, items[0], {**etiqueta_reflexiva, "regimen": "superficial"})
    assert r.status_code == 422
    assert await estudio.sql("SELECT id FROM estudio_etiqueta") == []


async def test_propuesto_exige_nota_y_no_reemplaza_al_derivado(listo, etiqueta_reflexiva) -> None:
    estudio, items = listo
    sin_nota = await _guardar(
        estudio, items[0], {**etiqueta_reflexiva, "regimen_propuesto": "superficial"}
    )
    assert sin_nota.status_code == 422
    con_nota = await _guardar(
        estudio,
        items[0],
        {**etiqueta_reflexiva, "regimen_propuesto": "superficial", "notas": "la regla falla aca"},
    )
    assert con_nota.status_code == 200, con_nota.text
    assert (
        con_nota.json()["regimen"],
        con_nota.json()["regimen_propuesto"],
        con_nota.json()["disiente_de_regla"],
    ) == (
        "reflexiva",
        "superficial",
        True,
    )


@pytest.mark.parametrize(
    "cuerpo",
    [
        {"respuestas": {"d9": {"valor": "presente", "cita": None}}},
        {"respuestas": {"d1": {"valor": "quizas", "cita": None}}},
        {"respuestas": {}, "campo_raro": 1},
        {"regimen": "inexistente"},
        # verify-1, F2: tipos no hashables daban 500 (`x in set`).
        {"regimen": ["reflexiva"]},
        {"regimen": {"clave": "reflexiva"}},
        {"regimen_propuesto": ["superficial"], "notas": "n"},
        {"respuestas": {"d1": {"valor": ["presente"], "cita": None}}},
        {"confianza": ["alta"]},
    ],
)
async def test_fuera_del_esquema_da_400(listo, cuerpo) -> None:
    estudio, items = listo
    assert (await _guardar(estudio, items[0], cuerpo)).status_code == 400
    assert await estudio.sql("SELECT id FROM estudio_etiqueta") == []


async def test_reedicion_una_sola_fila_con_regimen_actualizado_e_historial(
    listo, etiqueta_reflexiva
) -> None:
    estudio, items = listo
    assert (
        await _guardar(
            estudio, items[0], {"respuestas": {"d1": {"valor": "presente", "cita": "t1"}}}
        )
    ).status_code == 200
    assert (await _guardar(estudio, items[0], etiqueta_reflexiva)).status_code == 200
    otra = copy.deepcopy(etiqueta_reflexiva)
    otra["respuestas"]["d4"]["valor"] = "oraculo"
    r = await _guardar(estudio, items[0], otra)
    assert r.json()["regimen"] == "superficial"
    filas = await estudio.sql(
        "SELECT regimen, created_at < updated_at AS reeditada FROM estudio_etiqueta"
    )
    assert filas == [{"regimen": "superficial", "reeditada": True}]
    historial = await estudio.sql(
        "SELECT snapshot->>'regimen' AS regimen FROM estudio_etiqueta_historial ORDER BY id"
    )
    assert [h["regimen"] for h in historial] == [None, "reflexiva", "superficial"]


async def test_item_ajeno_da_404(listo, etiqueta_reflexiva) -> None:
    estudio, _ = listo
    assert (await _guardar(estudio, uuid4(), etiqueta_reflexiva)).status_code == 404
    assert (await _mia(estudio, uuid4())).status_code == 404


async def test_investigador_no_etiqueta(listo, etiqueta_reflexiva) -> None:
    estudio, items = listo
    assert (
        await _guardar(estudio, items[0], etiqueta_reflexiva, estudio.investigador)
    ).status_code == 403


# ── Cierre ────────────────────────────────────────────────────────────────


async def test_cierre_incompleto_da_422_detallado(listo, etiqueta_reflexiva) -> None:
    estudio, items = listo
    assert (await _guardar(estudio, items[0], etiqueta_reflexiva)).status_code == 200
    r = await _cerrar(estudio)
    assert r.status_code == 422
    detalle = r.json()["detail"]
    assert detalle["codigo"] == "incompleta"
    assert detalle["faltan"] == 1
    assert [(f["item_id"], f["motivos"]) for f in detalle["faltantes"]] == [
        (items[1], ["sin_etiqueta"])
    ]
    assert (
        await estudio.sql("SELECT cerrada_at FROM estudio_membresia WHERE email = 'c1@ejemplo.org'")
    ) == [{"cerrada_at": None}]


async def test_cerrar_sin_muestra_cargada_da_409_sin_muestra(estudio_http) -> None:
    """verify-1, F4: antes respondía 422 `incompleta` con `faltan: 0`."""
    await estudio_http.codebook()
    r = await _cerrar(estudio_http)
    assert _sd(r) == (409, "sin_muestra")
    assert (
        await estudio_http.sql(
            "SELECT cerrada_at FROM estudio_membresia WHERE email = 'c1@ejemplo.org'"
        )
    ) == [{"cerrada_at": None}]


async def test_cita_con_solo_espacios_impide_cerrar(listo, etiqueta_reflexiva) -> None:
    estudio, items = listo
    sin_cita = copy.deepcopy(etiqueta_reflexiva)
    sin_cita["respuestas"]["d1"]["cita"] = "   "
    for item in items:
        assert (await _guardar(estudio, item, sin_cita)).status_code == 200
    r = await _cerrar(estudio)
    assert r.status_code == 422
    assert {tuple(f["motivos"]) for f in r.json()["detail"]["faltantes"]} == {("cita:d1",)}


async def test_cierre_con_propuesto_y_bloqueo_posterior(listo, etiqueta_reflexiva) -> None:
    estudio, items = listo
    assert (await _guardar(estudio, items[0], etiqueta_reflexiva)).status_code == 200
    propuesta = {**etiqueta_reflexiva, "regimen_propuesto": "superficial", "notas": "porque si"}
    assert (await _guardar(estudio, items[1], propuesta)).status_code == 200
    r = await _cerrar(estudio)
    assert r.status_code == 200, r.text
    assert r.json()["cerrada_at"]
    filas = await estudio.sql(
        "SELECT regimen, regimen_propuesto FROM estudio_etiqueta ORDER BY regimen_propuesto"
    )
    assert [dict(f) for f in filas] == [
        {"regimen": "reflexiva", "regimen_propuesto": "superficial"},
        {"regimen": "reflexiva", "regimen_propuesto": None},
    ]
    assert _sd(await _guardar(estudio, items[0], etiqueta_reflexiva)) == (
        409,
        "codificacion_cerrada",
    )
    assert _sd(await _cerrar(estudio)) == (409, "codificacion_cerrada")
    r = await estudio.client.get(f"{estudio.BASE}/mis-membresias", headers=estudio.c1.headers())
    assert [m["cerrada"] for m in r.json()] == [True]


# ── 8.3 Aislamiento ───────────────────────────────────────────────────────


async def test_un_codificador_nunca_ve_la_etiqueta_del_otro(listo, etiqueta_reflexiva) -> None:
    estudio, items = listo
    propuesta = {
        **etiqueta_reflexiva,
        "regimen_propuesto": "superficial",
        "notas": "nota secreta de c1",
    }
    assert (await _guardar(estudio, items[0], propuesta)).status_code == 200
    r = await _mia(estudio, items[0], estudio.c2)
    assert r.status_code == 200
    assert r.json() == {
        "respuestas": {},
        "regimen": None,
        "regimen_regla": None,
        "regimen_propuesto": None,
        "disiente_de_regla": False,
        "es_frontera": False,
        "confianza": None,
        "notas": None,
        "updated_at": None,
    }
    propios_b = await estudio.items(estudio.c2)
    assert {i["estado"] for i in propios_b} == {"sin_empezar"}
    assert (await _mia(estudio, items[0])).json()["notas"] == "nota secreta de c1"


async def test_progreso_del_investigador_solo_con_cantidades(listo, etiqueta_reflexiva) -> None:
    estudio, items = listo
    assert (await _guardar(estudio, items[0], etiqueta_reflexiva)).status_code == 200
    propuesta = {**etiqueta_reflexiva, "regimen_propuesto": "superficial", "notas": "nota"}
    assert (await _guardar(estudio, items[1], propuesta)).status_code == 200
    assert (
        await _guardar(
            estudio,
            items[0],
            {"respuestas": {"d1": {"valor": "ausente", "cita": None}}},
            estudio.c2,
        )
    ).status_code == 200
    r = await estudio.pedir("GET", "/progreso", estudio.investigador)
    assert r.status_code == 200, r.text
    assert sorted(r.json(), key=lambda p: p["alias"]) == [
        {
            "alias": "C1",
            "completos": 2,
            "parciales": 0,
            "con_regimen_propuesto": 1,
            "cerrada": False,
            "revocada": False,
        },
        {
            "alias": "C2",
            "completos": 0,
            "parciales": 1,
            "con_regimen_propuesto": 0,
            "cerrada": False,
            "revocada": False,
        },
    ]
    assert "reflexiva" not in r.text
    assert "nota" not in r.text


async def test_progreso_es_solo_del_investigador(listo) -> None:
    estudio, _ = listo
    assert (await estudio.pedir("GET", "/progreso", estudio.c1)).status_code == 403
