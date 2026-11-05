"""Lecturas para el panel del investigador (tareas 5.2 y 5.3, agregadas por el
orquestador en la tanda B para 11.8). App real + Postgres real + CTR falso."""

from __future__ import annotations

import pytest

CLAVES_MEMBRESIA = {
    "membresia_id",
    "email",
    "rol",
    "alias",
    "estado",
    "atada",
    "created_at",
    "cerrada_at",
    "revocada_at",
}


# ── 5.2 GET .../membresias ────────────────────────────────────────────────


async def test_investigador_lista_membresias_sin_etiquetas(
    estudio_http, etiqueta_reflexiva
) -> None:
    e = estudio_http
    await e.preparar(n=1)
    (item,) = await e.items(e.c1)
    assert (
        await e.pedir("PUT", f"/items/{item['item_id']}/mi-etiqueta", e.c1, json=etiqueta_reflexiva)
    ).status_code == 200
    assert (await e.pedir("POST", "/mi-codificacion/cerrar", e.c1)).status_code == 200
    listado = await e.pedir("GET", "/membresias", e.investigador)
    assert listado.status_code == 200, listado.text
    c2 = next(m for m in listado.json() if m["alias"] == "C2")
    assert (
        await e.pedir("DELETE", f"/membresias/{c2['membresia_id']}", e.investigador)
    ).status_code == 200

    r = await e.pedir("GET", "/membresias", e.investigador)
    assert r.status_code == 200, r.text
    filas = r.json()
    assert all(set(f) == CLAVES_MEMBRESIA for f in filas)
    resumen = sorted((f["alias"], f["email"], f["rol"], f["estado"], f["atada"]) for f in filas)
    assert resumen == [
        ("C1", "c1@ejemplo.org", "codificador", "cerrada", True),
        ("C2", "c2@ejemplo.org", "codificador", "revocada", False),
        ("I1", "inv@ejemplo.org", "investigador", "activa", True),
    ]
    assert "reflexiva" not in r.text and "turno 1" not in r.text


async def test_administrador_tambien_lista(estudio_http) -> None:
    r = await estudio_http.pedir("GET", "/membresias", estudio_http.admin)
    assert r.status_code == 200
    assert len(r.json()) == 3


@pytest.mark.parametrize("quien", ["c1", "ajeno"])
async def test_codificador_y_ajeno_no_listan(estudio_http, quien) -> None:
    assert (
        await estudio_http.pedir("GET", "/membresias", getattr(estudio_http, quien))
    ).status_code == 403


# ── 5.3 GET .../codebook/versiones y .../versiones/{etiqueta} ─────────────


@pytest.fixture
async def dos_versiones(estudio_http, etiqueta_reflexiva):
    e = estudio_http
    await e.codebook("v0", congelar=False, vigente=False)
    ep = e.ctr.agregar()
    r = await e.pedir(
        "POST",
        "/codebook/v0/anclas",
        e.investigador,
        json={
            "episode_id": str(ep),
            "uso": "practica",
            "orden": 1,
            "respuesta_esperada": etiqueta_reflexiva,
            "explicacion_md": "explicacion secreta",
            "consensuado_por": "C1 y C2",
        },
    )
    assert r.status_code == 201, r.text
    assert (await e.pedir("POST", "/codebook/v0/congelar", e.investigador)).status_code == 200
    assert (
        await e.pedir("PUT", "/codebook-vigente", e.investigador, json={"etiqueta": "v0"})
    ).status_code == 200
    assert (
        await e.pedir(
            "POST", "/codebook", e.investigador, json={"etiqueta": "v1", "clonar_de": "v0"}
        )
    ).status_code == 201
    return e, ep, r.json()["item_id"]


async def test_listado_de_versiones(dos_versiones) -> None:
    e, _, _ = dos_versiones
    for persona in (e.investigador, e.c1):
        r = await e.pedir("GET", "/codebook/versiones", persona)
        assert r.status_code == 200, r.text
        filas = sorted(r.json(), key=lambda v: v["etiqueta"])
        assert all(
            set(v) == {"etiqueta", "estado", "contenido_sha256", "congelada_at", "vigente"}
            for v in filas
        )
        assert [
            (v["etiqueta"], v["estado"], v["vigente"], v["contenido_sha256"] is not None)
            for v in filas
        ] == [
            ("v0", "congelada", True, True),
            ("v1", "borrador", False, False),
        ]


async def test_detalle_para_el_investigador_con_anclas_completas(dos_versiones) -> None:
    e, ep, item_id = dos_versiones
    r = await e.pedir("GET", "/codebook/versiones/v0", e.investigador)
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert (cuerpo["etiqueta"], cuerpo["estado"], cuerpo["vigente"], cuerpo["contenido_md"]) == (
        "v0",
        "congelada",
        True,
        "# Codebook",
    )
    assert cuerpo["esquema"]["regimen_evidencia_insuficiente"] == "evidencia_insuficiente"
    assert cuerpo["congelada_at"] and cuerpo["contenido_sha256"]
    (ancla,) = cuerpo["anclas"]
    assert (
        ancla["item_id"],
        ancla["episode_id"],
        ancla["explicacion_md"],
        ancla["respuesta_esperada"]["regimen"],
    ) == (
        item_id,
        str(ep),
        "explicacion secreta",
        "reflexiva",
    )


async def test_detalle_para_el_codificador_sin_respuesta_ni_episodio(dos_versiones) -> None:
    e, ep, item_id = dos_versiones
    r = await e.pedir("GET", "/codebook/versiones/v0", e.c1)
    assert r.status_code == 200, r.text
    assert r.json()["anclas"] == [{"item_id": item_id, "uso": "practica", "orden": 1}]
    assert str(ep) not in r.text
    assert "explicacion secreta" not in r.text
    assert "respuesta_esperada" not in r.text


async def test_version_inexistente_404_y_ajeno_403(dos_versiones) -> None:
    e, _, _ = dos_versiones
    assert (await e.pedir("GET", "/codebook/versiones/v9", e.investigador)).status_code == 404
    assert (await e.pedir("GET", "/codebook/versiones", e.ajeno)).status_code == 403
    assert (await e.pedir("GET", "/codebook/versiones/v0", e.ajeno)).status_code == 403


async def test_etiqueta_versiones_reservada(estudio_http) -> None:
    r = await estudio_http.pedir(
        "POST", "/codebook", estudio_http.investigador, json={"etiqueta": "versiones"}
    )
    assert r.status_code == 422


async def test_congelada_no_vigente_no_figura_como_vigente(dos_versiones) -> None:
    e, _, _ = dos_versiones
    assert (await e.pedir("POST", "/codebook/v1/congelar", e.investigador)).status_code == 200
    filas = (await e.pedir("GET", "/codebook/versiones", e.investigador)).json()
    assert sorted((v["etiqueta"], v["estado"], v["vigente"]) for v in filas) == [
        ("v0", "congelada", True),
        ("v1", "congelada", False),
    ]
    assert (await e.pedir("GET", "/codebook/versiones/v1", e.c1)).json()["vigente"] is False
