"""Entrenamiento con anclas (tarea 9.1, design D11, spec entrenamiento-calibracion).
App real + Postgres real + CTR falso."""

from __future__ import annotations

from uuid import uuid4

import pytest


def _ancla(ep, respuesta, uso, orden, explicacion) -> dict:
    return {
        "episode_id": str(ep),
        "uso": uso,
        "orden": orden,
        "respuesta_esperada": respuesta,
        "explicacion_md": explicacion,
        "consensuado_por": "C1 y C2",
    }


@pytest.fixture
async def entrenamiento(estudio_http, etiqueta_reflexiva):
    """Vigente en BORRADOR con: un ejemplo listo, una práctica lista y una
    práctica con el enunciado sin cargar."""
    e = estudio_http
    await e.codebook("v0", congelar=False, vigente=True)
    eps = [e.ctr.agregar() for _ in range(3)]
    ids = {}
    for nombre, ep, uso, orden in (
        ("ejemplo", eps[0], "ejemplo", 1),
        ("practica", eps[1], "practica", 1),
        ("pendiente", eps[2], "practica", 2),
    ):
        r = await e.pedir(
            "POST",
            "/codebook/v0/anclas",
            e.investigador,
            json=_ancla(ep, etiqueta_reflexiva, uso, orden, f"explicacion de {nombre}"),
        )
        assert r.status_code == 201, r.text
        ids[nombre] = r.json()["item_id"]
    assert (await e.cargar_enunciados(e.requeridos(eps[:2]))).status_code == 200
    await e.revisar_todos()
    return e, ids


async def _responder(e, item_id, cuerpo, persona=None):
    return await e.pedir(
        "POST", f"/entrenamiento/{item_id}/respuesta", persona or e.c1, json=cuerpo
    )


async def test_sin_codebook_vigente_estado_vacio(estudio_http) -> None:
    r = await estudio_http.pedir("GET", "/entrenamiento", estudio_http.c1)
    assert r.status_code == 200, r.text
    assert r.json() == {"codebook": None, "ejemplos": [], "practicas": []}


async def test_vigente_sin_anclas(estudio_http) -> None:
    await estudio_http.codebook("v0", congelar=False)
    r = await estudio_http.pedir("GET", "/entrenamiento", estudio_http.c1)
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert (cuerpo["codebook"]["etiqueta"], cuerpo["codebook"]["estado"]) == ("v0", "borrador")
    assert (cuerpo["ejemplos"], cuerpo["practicas"]) == ([], [])


async def test_listado_con_ejemplos_y_practica_ciega(entrenamiento, etiqueta_reflexiva) -> None:
    e, ids = entrenamiento
    r = await e.pedir("GET", "/entrenamiento", e.c1)
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert [
        (x["item_id"], x["orden"], x["explicacion_md"], x["respuesta_esperada"]["regimen"])
        for x in cuerpo["ejemplos"]
    ] == [(ids["ejemplo"], 1, "explicacion de ejemplo", "reflexiva")]
    assert cuerpo["practicas"] == [{"item_id": ids["practica"], "orden": 1}]
    assert "explicacion de practica" not in r.text
    assert ids["pendiente"] not in r.text


async def test_responder_practica_guarda_y_devuelve_solo_esa_ancla(
    entrenamiento, etiqueta_reflexiva
) -> None:
    e, ids = entrenamiento
    cuerpo = {
        **etiqueta_reflexiva,
        "regimen_propuesto": "superficial",
        "notas": "me parece superficial",
    }
    r = await _responder(e, ids["practica"], cuerpo)
    assert r.status_code == 200, r.text
    devolucion = r.json()
    assert (
        devolucion["regimen"],
        devolucion["regimen_regla"],
        devolucion["regimen_propuesto"],
    ) == (
        "reflexiva",
        "reflexiva",
        "superficial",
    )
    assert devolucion["esperada"]["regimen"] == "reflexiva"
    assert devolucion["explicacion_md"] == "explicacion de practica"
    assert devolucion["coincide"] is True
    assert "explicacion de ejemplo" not in r.text
    filas = await e.sql(
        "SELECT r.regimen, r.regimen_propuesto, r.traza_version, v.etiqueta, v.estado "
        "FROM entrenamiento_respuesta r JOIN codebook_version v ON v.id = r.codebook_version_id"
    )
    assert [dict(f) for f in filas] == [
        {
            "regimen": "reflexiva",
            "regimen_propuesto": "superficial",
            "traza_version": "traza_v1",
            "etiqueta": "v0",
            "estado": "borrador",
        }
    ]


async def test_dos_intentos_dos_filas_y_ninguna_etiqueta(entrenamiento, etiqueta_reflexiva) -> None:
    e, ids = entrenamiento
    otra = {
        "respuestas": {
            "d1": {"valor": "ausente", "cita": None},
            "d2": {"valor": "ausente", "cita": None},
            "d4": {"valor": "oraculo", "cita": None},
        }
    }
    assert (await _responder(e, ids["practica"], etiqueta_reflexiva)).status_code == 200
    r = await _responder(e, ids["practica"], otra)
    assert (r.json()["regimen"], r.json()["coincide"]) == ("superficial", False)
    filas = await e.sql("SELECT regimen FROM entrenamiento_respuesta ORDER BY id")
    assert [f["regimen"] for f in filas] == ["reflexiva", "superficial"]
    assert await e.sql("SELECT id FROM estudio_etiqueta") == []


@pytest.mark.parametrize("cual", ["ejemplo", "pendiente", "inexistente"])
async def test_solo_practicas_listas_de_la_vigente(entrenamiento, etiqueta_reflexiva, cual) -> None:
    e, ids = entrenamiento
    objetivo = ids.get(cual) or str(uuid4())
    assert (await _responder(e, objetivo, etiqueta_reflexiva)).status_code == 404
    assert await e.sql("SELECT id FROM entrenamiento_respuesta") == []


async def test_respuesta_fuera_del_esquema_da_400(entrenamiento) -> None:
    e, ids = entrenamiento
    r = await _responder(e, ids["practica"], {"respuestas": {"d9": {"valor": "x", "cita": None}}})
    assert r.status_code == 400


async def test_sin_membresia_403(entrenamiento, etiqueta_reflexiva) -> None:
    e, ids = entrenamiento
    assert (await e.pedir("GET", "/entrenamiento", e.ajeno)).status_code == 403
    assert (await _responder(e, ids["practica"], etiqueta_reflexiva, e.ajeno)).status_code == 403


async def test_el_investigador_tambien_practica(entrenamiento, etiqueta_reflexiva) -> None:
    e, ids = entrenamiento
    assert (
        await _responder(e, ids["practica"], etiqueta_reflexiva, e.investigador)
    ).status_code == 200
