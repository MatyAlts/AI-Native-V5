"""Anclas de entrenamiento por la API (tarea 7.3, design D11, D4b, D14,
spec entrenamiento-calibracion). App real + Postgres real + CTR falso."""

from __future__ import annotations

import copy
from uuid import UUID, uuid4

import pytest


def _sd(r) -> tuple[int, object]:
    try:
        cuerpo = r.json()
    except ValueError:
        cuerpo = None
    return r.status_code, cuerpo.get("detail") if isinstance(cuerpo, dict) else cuerpo


def _ancla(episode_id, etiqueta_reflexiva, **extra) -> dict:
    return {
        "episode_id": str(episode_id),
        "uso": "practica",
        "orden": 1,
        "respuesta_esperada": etiqueta_reflexiva,
        "explicacion_md": "Las tres dimensiones estan",
        "consensuado_por": "C1 y C2",
        **extra,
    }


@pytest.fixture
async def borrador(estudio_http):
    await estudio_http.codebook("v0", congelar=False, vigente=False)
    return estudio_http


async def _crear(estudio, cuerpo, etiqueta="v0", persona=None):
    return await estudio.pedir(
        "POST", f"/codebook/{etiqueta}/anclas", persona or estudio.investigador, json=cuerpo
    )


async def _crear_ok(estudio, cuerpo) -> dict:
    r = await _crear(estudio, cuerpo)
    assert r.status_code == 201, r.text
    return r.json()


async def test_alta_valida_con_evidencia_fija_y_enunciados(borrador, etiqueta_reflexiva) -> None:
    ejercicio = uuid4()
    ep = borrador.ctr.agregar(estado="paused", cierre="episodio_abandonado", ejercicio_id=ejercicio)
    r = await _crear(borrador, _ancla(ep, etiqueta_reflexiva))
    assert r.status_code == 201, r.text
    cuerpo = r.json()
    assert cuerpo["item_id"] != str(ep)
    assert cuerpo["enunciados_listos"] is False
    assert cuerpo["respuesta_esperada"]["regimen"] == "reflexiva"
    datos = borrador.ctr.episodios[ep]
    filas = await borrador.sql(
        "SELECT episode_id, seq_tope, chain_hash_tope, estado_carga, problema_id, ejercicio_id, uso, orden "
        "FROM estudio_ancla"
    )
    assert [dict(f) for f in filas] == [
        {
            "episode_id": ep,
            "seq_tope": datos["events"][-1]["seq"],
            "chain_hash_tope": datos["events"][-1]["chain_hash"],
            "estado_carga": "paused",
            "problema_id": UUID(datos["problema_id"]),
            "ejercicio_id": ejercicio,
            "uso": "practica",
            "orden": 1,
        }
    ]


@pytest.mark.parametrize(
    "respuesta",
    [
        {"respuestas": {"d1": {"valor": "quizas", "cita": None}}},
        {"respuestas": {}, "regimen": "inexistente"},
    ],
)
async def test_respuesta_esperada_fuera_del_esquema_da_400(
    borrador, etiqueta_reflexiva, respuesta
) -> None:
    r = await _crear(borrador, _ancla(borrador.ctr.agregar(), respuesta))
    assert r.status_code == 400
    assert await borrador.sql("SELECT item_id FROM estudio_ancla") == []


@pytest.mark.parametrize("caso", ["inexistente", "open", "paused_sin_abandono", "integridad"])
async def test_episodio_invalido_da_422(borrador, etiqueta_reflexiva, caso) -> None:
    ctr = borrador.ctr
    ep = {
        "inexistente": uuid4,
        "open": lambda: ctr.agregar(estado="open", cierre=None),
        "paused_sin_abandono": lambda: ctr.agregar(estado="paused", cierre=None),
        "integridad": lambda: ctr.agregar(integrity_compromised=True),
    }[caso]()
    r = await _crear(borrador, _ancla(ep, etiqueta_reflexiva))
    assert r.status_code == 422
    assert await borrador.sql("SELECT item_id FROM estudio_ancla") == []


async def test_episodio_de_la_muestra_no_puede_ser_ancla(borrador, etiqueta_reflexiva) -> None:
    ep = borrador.ctr.agregar()
    assert (await borrador.cargar_muestra([ep])).status_code == 200
    r = await _crear(borrador, _ancla(ep, etiqueta_reflexiva))
    assert _sd(r) == (409, "episodio_en_muestra")
    assert await borrador.sql("SELECT item_id FROM estudio_ancla") == []


async def test_muestra_despues_del_ancla_da_409(borrador, etiqueta_reflexiva) -> None:
    ep = borrador.ctr.agregar()
    assert (await _crear(borrador, _ancla(ep, etiqueta_reflexiva))).status_code == 201
    r = await borrador.cargar_muestra([borrador.ctr.agregar(), ep])
    assert _sd(r) == (409, "episodio_es_ancla")


async def test_edicion_y_baja_en_borrador(borrador, etiqueta_reflexiva) -> None:
    creada = await _crear_ok(borrador, _ancla(borrador.ctr.agregar(), etiqueta_reflexiva))
    r = await borrador.pedir(
        "PUT",
        f"/codebook/v0/anclas/{creada['item_id']}",
        borrador.investigador,
        json={
            "uso": "ejemplo",
            "orden": 3,
            "explicacion_md": "Otra explicacion",
            "consensuado_por": "C1",
            "respuesta_esperada": {"regimen": "evidencia_insuficiente", "notas": "traza corta"},
        },
    )
    assert r.status_code == 200, r.text
    filas = await borrador.sql(
        "SELECT uso, orden, explicacion_md, respuesta_esperada->>'regimen' AS regimen FROM estudio_ancla"
    )
    assert [dict(f) for f in filas] == [
        {
            "uso": "ejemplo",
            "orden": 3,
            "explicacion_md": "Otra explicacion",
            "regimen": "evidencia_insuficiente",
        }
    ]
    assert (
        await borrador.pedir(
            "DELETE", f"/codebook/v0/anclas/{creada['item_id']}", borrador.investigador
        )
    ).status_code == 200
    assert await borrador.sql("SELECT item_id FROM estudio_ancla") == []


async def test_ancla_de_version_congelada_da_409(borrador, etiqueta_reflexiva) -> None:
    creada = await _crear_ok(borrador, _ancla(borrador.ctr.agregar(), etiqueta_reflexiva))
    assert (
        await borrador.pedir("POST", "/codebook/v0/congelar", borrador.investigador)
    ).status_code == 200
    assert _sd(await _crear(borrador, _ancla(borrador.ctr.agregar(), etiqueta_reflexiva))) == (
        409,
        "version_congelada",
    )
    editar = await borrador.pedir(
        "PUT",
        f"/codebook/v0/anclas/{creada['item_id']}",
        borrador.investigador,
        json={"explicacion_md": "x"},
    )
    assert _sd(editar) == (409, "version_congelada")
    borrar = await borrador.pedir(
        "DELETE", f"/codebook/v0/anclas/{creada['item_id']}", borrador.investigador
    )
    assert _sd(borrar) == (409, "version_congelada")
    assert len(await borrador.sql("SELECT item_id FROM estudio_ancla")) == 1


async def test_listado_marca_enunciados_listos(borrador, etiqueta_reflexiva) -> None:
    ep_listo, ep_pendiente = borrador.ctr.agregar(), borrador.ctr.agregar()
    listo = await _crear_ok(borrador, _ancla(ep_listo, etiqueta_reflexiva))
    pendiente = await _crear_ok(borrador, _ancla(ep_pendiente, etiqueta_reflexiva, orden=2))
    assert (await borrador.cargar_enunciados(borrador.requeridos([ep_listo]))).status_code == 200
    await borrador.revisar_todos()
    r = await borrador.pedir("GET", "/codebook/v0/anclas", borrador.investigador)
    assert r.status_code == 200
    estado = {a["item_id"]: a["enunciados_listos"] for a in r.json()}
    assert estado == {listo["item_id"]: True, pendiente["item_id"]: False}


async def test_evidencia_del_ancla_fija(borrador, etiqueta_reflexiva) -> None:
    ep = borrador.ctr.agregar()
    creada = await _crear_ok(borrador, _ancla(ep, etiqueta_reflexiva))
    assert (await borrador.cargar_enunciados(borrador.requeridos([ep]))).status_code == 200
    await borrador.revisar_todos()
    antes = await borrador.pedir("GET", f"/items/{creada['item_id']}/traza", borrador.c1)
    assert antes.status_code == 200, antes.text
    borrador.ctr.evento(ep, "prompt_enviado", {"content": "evento nuevo"})
    despues = await borrador.pedir("GET", f"/items/{creada['item_id']}/traza", borrador.c1)
    assert despues.json() == antes.json()


@pytest.mark.parametrize("quien", ["c1", "admin", "ajeno"])
async def test_solo_el_investigador_gestiona_anclas(borrador, etiqueta_reflexiva, quien) -> None:
    persona = getattr(borrador, quien)
    assert (
        await _crear(borrador, _ancla(borrador.ctr.agregar(), etiqueta_reflexiva), persona=persona)
    ).status_code == 403
    assert (await borrador.pedir("GET", "/codebook/v0/anclas", persona)).status_code == 403


# ── Revalidación de anclas al cambiar el esquema y al congelar (verify-1, F1) ──
# El esquema del borrador se puede editar con anclas cargadas. El PUT AVISA
# (`anclas_invalidas`) y no rechaza: rechazar dejaría al investigador sin salida
# cuando renombra una dimensión (el ancla tampoco valida contra el esquema
# viejo). El gate duro es congelar: 422 con cada ancla y sus motivos.


def _esquema_cambiado(esquema: dict, caso: str) -> dict:
    b = copy.deepcopy(esquema)
    if caso == "regla":
        # reflexiva ahora exige d4 oraculo: el ancla (d4 interlocutor) da superficial.
        b["reglas_regimen"][0]["condicion"][2] = [{"dimension": "d4", "en": ["oraculo"]}]
    elif caso == "dimension":
        b["dimensiones"][0]["clave"] = "d1_nueva"
        b["reglas_regimen"][0]["condicion"][0] = [{"dimension": "d1_nueva", "en": ["presente"]}]
    elif caso == "valor":
        b["dimensiones"][2]["valores"] = ["tutor", "oraculo"]
        b["reglas_regimen"][0]["condicion"][2] = [{"dimension": "d4", "en": ["tutor"]}]
    elif caso == "regla_sin_d4":
        # La regla deja de mirar d4: un ancla sin d4 ya no queda con régimen nulo.
        del b["reglas_regimen"][0]["condicion"][2]
    return b


_MOTIVO = {"regla": "superficial", "dimension": "d1", "valor": "d4", "regla_sin_d4": "reflexiva"}


async def _cambiar_esquema(estudio, esquema: dict):
    return await estudio.pedir(
        "PUT", "/codebook/v0", estudio.investigador, json={"esquema": esquema}
    )


async def _congelar(estudio):
    return await estudio.pedir("POST", "/codebook/v0/congelar", estudio.investigador)


@pytest.mark.parametrize("caso", ["regla", "dimension", "valor", "regla_sin_d4"])
async def test_ancla_que_no_valida_contra_el_esquema_vigente_impide_congelar(
    borrador, esquema_prueba, etiqueta_reflexiva, caso
) -> None:
    esperada = copy.deepcopy(etiqueta_reflexiva)
    if caso == "regla_sin_d4":
        del esperada["respuestas"]["d4"]
    creada = await _crear_ok(borrador, _ancla(borrador.ctr.agregar(), esperada))

    r = await _cambiar_esquema(borrador, _esquema_cambiado(esquema_prueba, caso))
    assert r.status_code == 200, r.text
    aviso = r.json().get("anclas_invalidas", [])
    assert [(a["item_id"], a["uso"], a["orden"]) for a in aviso] == [
        (creada["item_id"], "practica", 1)
    ]
    assert any(_MOTIVO[caso] in m for m in aviso[0]["motivos"]), aviso

    r = await _congelar(borrador)
    assert r.status_code == 422, r.text
    detalle = r.json()["detail"]
    assert detalle["codigo"] == "anclas_invalidas"
    assert [a["item_id"] for a in detalle["anclas"]] == [creada["item_id"]]
    assert any(_MOTIVO[caso] in m for m in detalle["anclas"][0]["motivos"]), detalle
    assert detalle["errores"], "el panel muestra `errores` como texto"
    assert await borrador.sql("SELECT estado, contenido_sha256 FROM codebook_version") == [
        {"estado": "borrador", "contenido_sha256": None}
    ]


async def test_ancla_exenta_sigue_valida_con_otra_regla(borrador, esquema_prueba) -> None:
    exenta = {"regimen": "evidencia_insuficiente", "notas": "traza corta"}
    await _crear_ok(borrador, _ancla(borrador.ctr.agregar(), exenta))
    r = await _cambiar_esquema(borrador, _esquema_cambiado(esquema_prueba, "regla"))
    assert (r.status_code, r.json().get("anclas_invalidas")) == (200, [])
    assert (await _congelar(borrador)).status_code == 200


async def test_ancla_corregida_contra_el_esquema_nuevo_permite_congelar(
    borrador, esquema_prueba, etiqueta_reflexiva
) -> None:
    creada = await _crear_ok(borrador, _ancla(borrador.ctr.agregar(), etiqueta_reflexiva))
    assert (
        await _cambiar_esquema(borrador, _esquema_cambiado(esquema_prueba, "regla"))
    ).status_code == 200
    assert (await _congelar(borrador)).status_code == 422
    corregida = copy.deepcopy(etiqueta_reflexiva)
    corregida["respuestas"]["d4"]["valor"] = "oraculo"
    r = await borrador.pedir(
        "PUT",
        f"/codebook/v0/anclas/{creada['item_id']}",
        borrador.investigador,
        json={"respuesta_esperada": corregida},
    )
    assert r.status_code == 200, r.text
    assert r.json()["respuesta_esperada"]["regimen"] == "reflexiva"
    assert (await _congelar(borrador)).status_code == 200


# ── Completitud de la respuesta esperada al congelar (verify-2, O1) ─────────
# Decisión del orquestador: al congelar, cada ancla tiene que estar completa con
# la misma completitud que el cierre de una codificación (`faltantes_cierre`:
# régimen, dimensiones, citas, notas, confianza). En borrador se permite
# incompleta, pero el alta y la edición avisan con `faltantes`.


def _incompleta(caso: str, etiqueta_reflexiva: dict) -> tuple[dict, str]:
    esperada = copy.deepcopy(etiqueta_reflexiva)
    if caso == "vacia":
        return {"respuestas": {}}, "regimen"
    if caso == "sin_dimension":
        del esperada["respuestas"]["d2"]
        return esperada, "dimension:d2"
    if caso == "sin_cita":
        esperada["respuestas"]["d1"]["cita"] = "   "
        return esperada, "cita:d1"
    return {"regimen": "evidencia_insuficiente"}, "notas"  # exenta sin notas


@pytest.mark.parametrize("caso", ["vacia", "sin_dimension", "sin_cita", "exenta_sin_notas"])
async def test_ancla_incompleta_se_guarda_con_aviso_y_no_deja_congelar(
    borrador, etiqueta_reflexiva, caso
) -> None:
    esperada, falta = _incompleta(caso, etiqueta_reflexiva)
    r = await _crear(borrador, _ancla(borrador.ctr.agregar(), esperada))
    assert r.status_code == 201, r.text
    assert falta in r.json().get("faltantes", [])

    r = await _congelar(borrador)
    assert r.status_code == 422, r.text
    detalle = r.json()["detail"]
    assert detalle["codigo"] == "anclas_invalidas"
    assert any(falta in m for m in detalle["anclas"][0]["motivos"]), detalle
    assert await borrador.sql("SELECT estado, contenido_sha256 FROM codebook_version") == [
        {"estado": "borrador", "contenido_sha256": None}
    ]


async def test_ancla_completa_no_avisa_y_completarla_por_edicion_permite_congelar(
    borrador, etiqueta_reflexiva
) -> None:
    completa = await _crear_ok(borrador, _ancla(borrador.ctr.agregar(), etiqueta_reflexiva))
    assert completa.get("faltantes") == []
    esperada, _ = _incompleta("sin_cita", etiqueta_reflexiva)
    incompleta = await _crear_ok(borrador, _ancla(borrador.ctr.agregar(), esperada, orden=2))
    assert incompleta.get("faltantes") == ["cita:d1"]
    sin_completar = await borrador.pedir(
        "PUT",
        f"/codebook/v0/anclas/{incompleta['item_id']}",
        borrador.investigador,
        json={"explicacion_md": "todavia sin cita"},
    )
    assert (sin_completar.status_code, sin_completar.json().get("faltantes")) == (200, ["cita:d1"])
    r = await borrador.pedir(
        "PUT",
        f"/codebook/v0/anclas/{incompleta['item_id']}",
        borrador.investigador,
        json={"respuesta_esperada": etiqueta_reflexiva},
    )
    assert (r.status_code, r.json().get("faltantes")) == (200, [])
    assert (await _congelar(borrador)).status_code == 200


async def test_esquema_que_deja_incompleta_un_ancla_avisa_en_el_put(
    borrador, esquema_prueba, etiqueta_reflexiva
) -> None:
    creada = await _crear_ok(borrador, _ancla(borrador.ctr.agregar(), etiqueta_reflexiva))
    b = copy.deepcopy(esquema_prueba)
    b["dimensiones"][1]["cita_requerida_si"] = ["presente"]  # d2 presente sin cita
    r = await _cambiar_esquema(borrador, b)
    aviso = r.json().get("anclas_invalidas", [])
    assert [a["item_id"] for a in aviso] == [creada["item_id"]]
    assert any("cita:d2" in m for m in aviso[0]["motivos"]), aviso
