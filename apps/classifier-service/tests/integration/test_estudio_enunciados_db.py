"""Carga y revisión de enunciados, y bloqueo de la codificación por enunciados
(tarea 7.2b, design D14, spec estudio-codificacion).

App real + Postgres real + CTR falso. Los casos de bloqueo usan
`PUT .../mi-etiqueta` (tarea 8.1).
"""

from __future__ import annotations

import hashlib
import logging
from uuid import UUID, uuid4

import pytest


def _sd(r) -> tuple[int, object]:
    try:
        cuerpo = r.json()
    except ValueError:
        cuerpo = None
    return r.status_code, cuerpo.get("detail") if isinstance(cuerpo, dict) else cuerpo


def _sha(texto: str) -> str:
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


TP_A, TP_B, EJ_X, EJ_Y = (uuid4() for _ in range(4))


async def _muestra_dos_tps(estudio) -> list[UUID]:
    ctr = estudio.ctr
    episodios = [
        ctr.agregar(problema_id=TP_A, ejercicio_id=EJ_X),
        ctr.agregar(problema_id=TP_A, ejercicio_id=EJ_Y),
        ctr.agregar(problema_id=TP_B),
    ]
    assert (await estudio.cargar_muestra(episodios)).status_code == 200
    return episodios


TODOS = [
    ("tp", TP_A, "Consigna de la TP A"),
    ("tp", TP_B, "Consigna de la TP B, entregar antes del 12/05/2026"),
    ("ejercicio", EJ_X, "Ejercicio X: sumar pares"),
    ("ejercicio", EJ_Y, 'Ejercicio Y\nen dos lineas, con "comillas"'),
]


async def _estado(estudio) -> dict:
    r = await estudio.pedir("GET", "/enunciados", estudio.investigador)
    assert r.status_code == 200, r.text
    return r.json()


@pytest.mark.parametrize(
    "metodo,ruta",
    [("POST", "/enunciados"), ("GET", "/enunciados"), ("POST", f"/enunciados/{uuid4()}/revision")],
)
async def test_codificador_recibe_403(estudio_http, metodo, ruta) -> None:
    r = await estudio_http.pedir(
        metodo, ruta, estudio_http.c1, content=b"tipo,tp_id,ejercicio_id,enunciado\n"
    )
    assert r.status_code == 403


async def test_carga_completa_guarda_cuatro_con_hash_y_alertas(estudio_http) -> None:
    await _muestra_dos_tps(estudio_http)
    csv = estudio_http.csv_enunciados(TODOS)
    r = await estudio_http.cargar_enunciados(TODOS)
    assert r.status_code == 200, r.text
    assert r.json()["cobertura"]["faltantes"] == []
    assert r.json()["ignoradas"] == []
    filas = await estudio_http.sql(
        "SELECT fuente, fuente_id, contenido_original_md, sha256_original, archivo_sha256, alertas, "
        "revisado_at FROM estudio_enunciado ORDER BY fuente, contenido_original_md"
    )
    assert {(f["fuente"], f["fuente_id"]) for f in filas} == {(t, i) for t, i, _ in TODOS}
    for f in filas:
        assert f["sha256_original"] == _sha(f["contenido_original_md"])
        assert f["archivo_sha256"] == _sha(csv)
        assert f["revisado_at"] is None
    por_texto = {f["contenido_original_md"]: f["alertas"] for f in filas}
    assert por_texto["Consigna de la TP B, entregar antes del 12/05/2026"] == ["fecha"]
    assert por_texto['Ejercicio Y\nen dos lineas, con "comillas"'] == []


async def test_carga_parcial_informa_faltantes_e_ignora_filas_sin_uso(estudio_http) -> None:
    await _muestra_dos_tps(estudio_http)
    sin_uso = uuid4()
    r = await estudio_http.cargar_enunciados(
        [TODOS[0], TODOS[1], TODOS[2], ("tp", sin_uso, "TP de otra cosa")]
    )
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert cuerpo["cobertura"]["faltantes"] == [
        {"tipo": "ejercicio", "id": str(EJ_Y), "items_afectados": 1}
    ]
    assert cuerpo["ignoradas"] == [{"tipo": "tp", "id": str(sin_uso)}]
    guardados = await estudio_http.sql("SELECT fuente_id FROM estudio_enunciado")
    assert sin_uso not in {f["fuente_id"] for f in guardados}
    assert len(guardados) == 3


async def test_archivo_invalido_da_422_y_no_guarda_nada(estudio_http) -> None:
    await _muestra_dos_tps(estudio_http)
    r = await estudio_http.client.post(
        estudio_http.ruta("/enunciados"),
        content=f"tipo,tp_id,ejercicio_id,enunciado\ntp,{TP_A},,ok\ntp,{TP_A},,repetido\n".encode(),
        headers={**estudio_http.investigador.headers(), "Content-Type": "text/csv"},
    )
    assert r.status_code == 422
    assert "fila 3" in r.text
    assert await estudio_http.sql("SELECT id FROM estudio_enunciado") == []


async def test_mismo_texto_es_no_op_y_otro_texto_sin_revisar_reemplaza(
    estudio_http, caplog
) -> None:
    await _muestra_dos_tps(estudio_http)
    assert (await estudio_http.cargar_enunciados(TODOS)).status_code == 200
    antes = await estudio_http.sql(
        "SELECT fuente_id, sha256_original, archivo_sha256, cargado_at FROM estudio_enunciado"
    )
    assert (await estudio_http.cargar_enunciados(TODOS[:1])).status_code == 200
    igual = await estudio_http.sql(
        "SELECT fuente_id, sha256_original, archivo_sha256, cargado_at FROM estudio_enunciado"
    )
    assert sorted(igual, key=str) == sorted(antes, key=str)

    with caplog.at_level(logging.INFO, logger="classifier_service.routes.estudio"):
        r = await estudio_http.cargar_enunciados([("tp", TP_A, "Consigna corregida de la TP A")])
    assert r.status_code == 200, r.text
    fila = await estudio_http.sql(
        "SELECT contenido_original_md, sha256_original FROM estudio_enunciado WHERE fuente_id = :i",
        {"i": TP_A},
    )
    assert fila == [
        {
            "contenido_original_md": "Consigna corregida de la TP A",
            "sha256_original": _sha("Consigna corregida de la TP A"),
        }
    ]
    eventos = [rec for rec in caplog.records if rec.getMessage() == "estudio_enunciado_reemplazado"]
    assert len(eventos) == 1
    assert (eventos[0].sha256_anterior, eventos[0].sha256_nuevo) == (
        _sha("Consigna de la TP A"),
        _sha("Consigna corregida de la TP A"),
    )
    assert "Consigna" not in repr(vars(eventos[0]))


async def test_otro_texto_sobre_revisado_da_409_y_no_cambia(estudio_http) -> None:
    await _muestra_dos_tps(estudio_http)
    assert (await estudio_http.cargar_enunciados(TODOS)).status_code == 200
    await estudio_http.revisar_todos()
    r = await estudio_http.cargar_enunciados(
        [("tp", TP_A, "Texto distinto"), ("tp", TP_B, "Otro distinto")]
    )
    assert _sd(r) == (409, "enunciado_revisado")
    filas = await estudio_http.sql(
        "SELECT contenido_original_md FROM estudio_enunciado WHERE fuente = 'tp'"
    )
    assert sorted(f["contenido_original_md"] for f in filas) == sorted([TODOS[0][2], TODOS[1][2]])


async def test_revision_aprueba_o_edita_y_conserva_el_original(estudio_http) -> None:
    await _muestra_dos_tps(estudio_http)
    assert (await estudio_http.cargar_enunciados(TODOS)).status_code == 200
    enunciados = {e["fuente_id"]: e for e in (await _estado(estudio_http))["enunciados"]}
    tp_b = enunciados[str(TP_B)]
    assert tp_b["alertas"] == ["fecha"]
    assert tp_b["revisado"] is False

    editado = "Consigna de la TP B"
    r = await estudio_http.pedir(
        "POST",
        f"/enunciados/{tp_b['id']}/revision",
        estudio_http.investigador,
        json={"contenido_mostrado_md": editado},
    )
    assert r.status_code == 200, r.text
    r = await estudio_http.pedir(
        "POST",
        f"/enunciados/{enunciados[str(TP_A)]['id']}/revision",
        estudio_http.investigador,
        json={"contenido_mostrado_md": None},
    )
    assert r.status_code == 200, r.text
    filas = {
        f["fuente_id"]: f
        for f in await estudio_http.sql(
            "SELECT fuente_id, contenido_original_md, sha256_original, contenido_mostrado_md, sha256_mostrado, "
            "revisado_por FROM estudio_enunciado WHERE fuente = 'tp'"
        )
    }
    assert dict(filas[TP_B]) == {
        "fuente_id": TP_B,
        "contenido_original_md": TODOS[1][2],
        "sha256_original": _sha(TODOS[1][2]),
        "contenido_mostrado_md": editado,
        "sha256_mostrado": _sha(editado),
        "revisado_por": estudio_http.investigador.user_id,
    }
    assert filas[TP_A]["contenido_mostrado_md"] == TODOS[0][2]
    assert filas[TP_A]["sha256_mostrado"] == _sha(TODOS[0][2])

    otra = await estudio_http.pedir(
        "POST",
        f"/enunciados/{tp_b['id']}/revision",
        estudio_http.investigador,
        json={"contenido_mostrado_md": "x"},
    )
    assert _sd(otra) == (409, "enunciado_revisado")


async def test_revision_de_inexistente_da_404(estudio_http) -> None:
    r = await estudio_http.pedir(
        "POST",
        f"/enunciados/{uuid4()}/revision",
        estudio_http.investigador,
        json={"contenido_mostrado_md": None},
    )
    assert r.status_code == 404


async def test_traza_con_enunciado_faltante_da_409(estudio_http) -> None:
    await _muestra_dos_tps(estudio_http)
    assert (await estudio_http.cargar_enunciados(TODOS[:3])).status_code == 200
    await estudio_http.revisar_todos()
    items = await estudio_http.sql("SELECT item_id, ejercicio_id FROM estudio_muestra")
    afectado = next(i["item_id"] for i in items if i["ejercicio_id"] == EJ_Y)
    sano = next(i["item_id"] for i in items if i["ejercicio_id"] == EJ_X)
    assert _sd(await estudio_http.pedir("GET", f"/items/{afectado}/traza", estudio_http.c1)) == (
        409,
        "enunciado_pendiente",
    )
    assert (
        await estudio_http.pedir("GET", f"/items/{sano}/traza", estudio_http.c1)
    ).status_code == 200


# ── Bloqueo de la codificación de TODO el estudio (usa 8.1) ───────────────


async def _codificar(estudio, etiqueta, item_id):
    return await estudio.pedir("PUT", f"/items/{item_id}/mi-etiqueta", estudio.c1, json=etiqueta)


async def _sano(estudio) -> UUID:
    items = await estudio.sql("SELECT item_id, ejercicio_id FROM estudio_muestra")
    return next(i["item_id"] for i in items if i["ejercicio_id"] == EJ_X)


async def test_un_enunciado_faltante_bloquea_todos_los_items(
    estudio_http, etiqueta_reflexiva
) -> None:
    await _muestra_dos_tps(estudio_http)
    assert (await estudio_http.cargar_enunciados(TODOS[:3])).status_code == 200
    await estudio_http.revisar_todos()
    await estudio_http.codebook()
    r = await _codificar(estudio_http, etiqueta_reflexiva, await _sano(estudio_http))
    assert _sd(r) == (409, "enunciados_pendientes")
    assert await estudio_http.sql("SELECT id FROM estudio_etiqueta") == []


async def test_un_enunciado_sin_revisar_bloquea(estudio_http, etiqueta_reflexiva) -> None:
    await _muestra_dos_tps(estudio_http)
    assert (await estudio_http.cargar_enunciados(TODOS)).status_code == 200
    estado = await _estado(estudio_http)
    for e in estado["enunciados"][:-1]:
        r = await estudio_http.pedir(
            "POST",
            f"/enunciados/{e['id']}/revision",
            estudio_http.investigador,
            json={"contenido_mostrado_md": None},
        )
        assert r.status_code == 200
    await estudio_http.codebook()
    r = await _codificar(estudio_http, etiqueta_reflexiva, await _sano(estudio_http))
    assert _sd(r) == (409, "enunciados_pendientes")


async def test_todos_revisados_habilita_la_codificacion(estudio_http, etiqueta_reflexiva) -> None:
    await _muestra_dos_tps(estudio_http)
    assert (await estudio_http.cargar_enunciados(TODOS)).status_code == 200
    await estudio_http.revisar_todos()
    await estudio_http.codebook()
    r = await _codificar(estudio_http, etiqueta_reflexiva, await _sano(estudio_http))
    assert r.status_code == 200, r.text
