"""Exportación del investigador (tarea 10.2, design D12, spec estudio-codificacion-exportacion).
App real + Postgres real + CTR falso."""

from __future__ import annotations

import csv
import io
import logging

import pytest

CAMPOS_ETIQUETA = {
    "episode_id",
    "item_id",
    "alias",
    "membresia_id",
    "semilla",
    "posicion",
    "codebook_etiqueta",
    "codebook_sha256",
    "traza_version",
    "dim_d1_valor",
    "dim_d1_cita",
    "dim_d2_valor",
    "dim_d2_cita",
    "dim_d4_valor",
    "dim_d4_cita",
    "regimen",
    "regimen_regla",
    "regimen_propuesto",
    "disiente_de_regla",
    "es_frontera",
    "confianza",
    "notas",
    "enunciado_tp_sha256_original",
    "enunciado_tp_sha256_mostrado",
    "enunciado_tp_archivo_sha256",
    "enunciado_ejercicio_sha256_original",
    "enunciado_ejercicio_sha256_mostrado",
    "enunciado_ejercicio_archivo_sha256",
    "created_at",
    "updated_at",
    "cerrada_at",
    "revocada_at",
}


async def _exportar(e, contenido="etiquetas", formato="json", persona=None):
    return await e.pedir(
        "GET",
        "/exportacion",
        persona or e.investigador,
        params={"contenido": contenido, "formato": formato},
    )


@pytest.fixture
async def codificado(estudio_http, etiqueta_reflexiva):
    e = estudio_http
    await e.preparar(n=2)
    items = [i["item_id"] for i in await e.items(e.c1)]
    exento = {**etiqueta_reflexiva, "regimen": "evidencia_insuficiente", "notas": '=HYPERLINK("x")'}
    for item, cuerpo in ((items[0], etiqueta_reflexiva), (items[1], exento)):
        r = await e.pedir("PUT", f"/items/{item}/mi-etiqueta", e.c1, json=cuerpo)
        assert r.status_code == 200, r.text
    r = await e.pedir(
        "PUT",
        f"/items/{items[0]}/mi-etiqueta",
        e.c2,
        json={"respuestas": {"d1": {"valor": "ausente", "cita": None}}},
    )
    assert r.status_code == 200, r.text
    assert (await e.pedir("POST", "/mi-codificacion/cerrar", e.c1)).status_code == 200
    return e, items


@pytest.mark.parametrize("quien", ["c1", "ajeno", "admin"])
async def test_solo_el_investigador_exporta(codificado, quien) -> None:
    e, _ = codificado
    assert (await _exportar(e, persona=getattr(e, quien))).status_code == 403


async def test_json_de_etiquetas_con_trazabilidad_y_sin_emails(codificado) -> None:
    e, items = codificado
    r = await _exportar(e)
    assert r.status_code == 200, r.text
    filas = r.json()
    assert len(filas) == 3
    assert all(set(f) == CAMPOS_ETIQUETA for f in filas)
    assert "@ejemplo.org" not in r.text
    assert "hola tutor" not in r.text and "que probaste?" not in r.text

    c1 = sorted((f for f in filas if f["alias"] == "C1"), key=lambda f: f["posicion"])
    assert [f["item_id"] for f in c1] == items
    exenta = c1[1]
    assert (
        exenta["regimen"],
        exenta["regimen_regla"],
        exenta["disiente_de_regla"],
        exenta["notas"],
    ) == (
        "evidencia_insuficiente",
        "reflexiva",
        False,
        '=HYPERLINK("x")',
    )
    assert c1[0]["cerrada_at"] is not None
    c2 = [f for f in filas if f["alias"] == "C2"]
    assert (c2[0]["regimen"], c2[0]["regimen_regla"], c2[0]["cerrada_at"]) == (None, None, None)

    db = await e.sql(
        "SELECT m.alias, m.semilla, v.etiqueta, v.contenido_sha256 FROM estudio_membresia m, estudio_codificacion c "
        "JOIN codebook_version v ON v.id = c.codebook_vigente_id WHERE m.rol = 'codificador'"
    )
    por_alias = {d["alias"]: d for d in db}
    for f in filas:
        assert f["semilla"] == por_alias[f["alias"]]["semilla"]
        assert (f["codebook_etiqueta"], f["codebook_sha256"], f["traza_version"]) == (
            "v0",
            por_alias[f["alias"]]["contenido_sha256"],
            "traza_v1",
        )
    enunciados = await e.sql(
        "SELECT m.item_id, n.sha256_original, n.sha256_mostrado, n.archivo_sha256 FROM estudio_muestra m "
        "JOIN estudio_enunciado n ON n.fuente = 'tp' AND n.fuente_id = m.problema_id"
    )
    por_item = {str(x["item_id"]): x for x in enunciados}
    for f in filas:
        esperado = por_item[f["item_id"]]
        assert (
            f["enunciado_tp_sha256_original"],
            f["enunciado_tp_sha256_mostrado"],
            f["enunciado_tp_archivo_sha256"],
        ) == (
            esperado["sha256_original"],
            esperado["sha256_mostrado"],
            esperado["archivo_sha256"],
        )
        assert f["enunciado_ejercicio_sha256_original"] is None


async def test_csv_y_json_con_las_mismas_filas_y_valores(codificado) -> None:
    e, _ = codificado
    json_filas = (await _exportar(e)).json()
    r = await _exportar(e, formato="csv")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    csv_filas = list(csv.DictReader(io.StringIO(r.text, newline="")))
    assert len(csv_filas) == len(json_filas)

    def celda(v):
        if v is None:
            return ""
        if isinstance(v, bool):
            return "true" if v else "false"
        t = str(v)
        return "'" + t if isinstance(v, str) and t[:1] in ("=", "+", "-", "@", "\t", "\r") else t

    clave = lambda f: (f["alias"], f["item_id"])  # noqa: E731
    for j, c in zip(sorted(json_filas, key=clave), sorted(csv_filas, key=clave), strict=True):
        assert {k: celda(v) for k, v in j.items()} == c
    assert any(c["notas"] == '\'=HYPERLINK("x")' for c in csv_filas)


async def test_estudio_sin_etiquetas(estudio_http) -> None:
    assert (await _exportar(estudio_http)).json() == []
    r = await _exportar(estudio_http, formato="csv")
    assert len(r.text.strip().splitlines()) == 1
    assert r.text.startswith("episode_id,")


async def test_historial_y_entrenamiento(codificado) -> None:
    e, _ = codificado
    historial = (await _exportar(e, "historial")).json()
    assert len(historial) == 3
    assert {
        "historial_id",
        "etiqueta_id",
        "alias",
        "item_id",
        "episode_id",
        "guardado_at",
        "snapshot",
    } <= set(historial[0])
    entrenamiento = await _exportar(e, "entrenamiento")
    assert (entrenamiento.status_code, entrenamiento.json()) == (200, [])


@pytest.mark.parametrize(
    "params",
    [{"contenido": "emails", "formato": "json"}, {"contenido": "etiquetas", "formato": "xlsx"}],
)
async def test_parametros_invalidos_dan_422(codificado, params) -> None:
    e, _ = codificado
    assert (await e.pedir("GET", "/exportacion", e.investigador, params=params)).status_code == 422


async def test_exportacion_queda_registrada_sin_valores_ni_emails(codificado, caplog) -> None:
    e, _ = codificado
    with caplog.at_level(logging.INFO, logger="classifier_service.routes.estudio"):
        assert (await _exportar(e, "historial", "csv")).status_code == 200
    eventos = [rec for rec in caplog.records if rec.getMessage() == "estudio_exportacion"]
    assert len(eventos) == 1
    ev = eventos[0]
    assert (ev.estudio, ev.contenido, ev.formato, ev.filas, ev.autor_user_id) == (
        e.clave,
        "historial",
        "csv",
        3,
        str(e.investigador.user_id),
    )
    assert ev.momento
    texto = repr(vars(ev))
    for prohibido in ("@ejemplo.org", "reflexiva", "HYPERLINK"):
        assert prohibido not in texto


async def test_posicion_exportada_se_recomputa_con_la_semilla(
    estudio_http, etiqueta_reflexiva
) -> None:
    """Spec "Orden recomputable": semilla + item_id exportados dan la posición."""
    import hashlib

    e = estudio_http
    await e.preparar(n=5)
    for item in await e.items(e.c1):
        assert (
            await e.pedir(
                "PUT", f"/items/{item['item_id']}/mi-etiqueta", e.c1, json=etiqueta_reflexiva
            )
        ).status_code == 200
    filas = (await _exportar(e)).json()
    assert len(filas) == 5
    semilla = filas[0]["semilla"]
    ordenados = sorted(
        (f["item_id"] for f in filas),
        key=lambda i: hashlib.sha256(f"{semilla}:{i}".encode()).hexdigest(),
    )
    assert {f["item_id"]: f["posicion"] for f in filas} == {
        i: n for n, i in enumerate(ordenados, start=1)
    }
