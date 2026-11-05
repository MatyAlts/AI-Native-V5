"""Traza ciega por la API (tarea 6.3, design D4, D4b, D14, spec traza-ciega-episodio).

App real + Postgres real + CTR falso inyectado (`ctr_falso`). Los ítems y
enunciados se insertan por SQL: sus endpoints de carga son de 7.1, 7.2b y 7.3.
"""

from __future__ import annotations

import json
import logging
from uuid import UUID, uuid4

import pytest

CLAVES_PROHIBIDAS = {
    "episode_id",
    "student_pseudonym",
    "comision_id",
    "problema_id",
    "seq",
    "ts",
    "self_hash",
    "chain_hash",
    "prev_chain_hash",
    "user_id",
    "curso_config_hash",
    "classifier_config_hash",
}


def _sd(r) -> tuple[int, object]:
    """Status y `detail` sin romper si la respuesta no es JSON o no trae detail:
    así un 200 o un 500 inesperado falla por aserción y no por KeyError."""
    try:
        cuerpo = r.json()
    except ValueError:
        cuerpo = None
    return r.status_code, cuerpo.get("detail") if isinstance(cuerpo, dict) else cuerpo


def _claves(obj, acc: set[str]) -> set[str]:
    if isinstance(obj, dict):
        for k, v in obj.items():
            acc.add(k)
            _claves(v, acc)
    elif isinstance(obj, list):
        for v in obj:
            _claves(v, acc)
    return acc


async def _item_con_enunciados(estudio, *, ejercicio: bool = False, revisado: bool = True):
    ejercicio_id = uuid4() if ejercicio else None
    episodio = estudio.ctr.agregar(ejercicio_id=ejercicio_id)
    item_id = await estudio.insertar_item_sql(episodio)
    problema = UUID(estudio.ctr.episodios[episodio]["problema_id"])
    await estudio.insertar_enunciado_sql("tp", problema, "Consigna de la TP", revisado=True)
    if ejercicio_id:
        await estudio.insertar_enunciado_sql(
            "ejercicio", ejercicio_id, "Consigna del ejercicio", revisado=revisado
        )
    return episodio, item_id


async def _traza(estudio, item_id, persona=None):
    return await estudio.pedir("GET", f"/items/{item_id}/traza", persona or estudio.c1)


async def test_codificador_recibe_la_traza_ciega_de_un_item(estudio_http) -> None:
    episodio, item_id = await _item_con_enunciados(estudio_http, ejercicio=True)
    r = await _traza(estudio_http, item_id)
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert cuerpo["traza_version"] == "traza_v1"
    assert cuerpo["enunciado"] == {
        "tp_md": "Consigna de la TP",
        "ejercicio_md": "Consigna del ejercicio",
    }
    assert [e["tipo"] for e in cuerpo["elementos"]] == [
        "inicio",
        "mensaje_alumno",
        "respuesta_tutor",
        "fin_cerrado",
    ]
    texto = json.dumps(cuerpo)
    assert str(episodio) not in texto
    assert "overuse" not in texto
    assert "prompt_kind" not in texto
    assert not _claves(cuerpo, set()) & CLAVES_PROHIBIDAS
    assert estudio_http.ctr.llamadas == [(estudio_http.tenant_id, episodio)]


async def test_tp_monolitica_trae_solo_la_consigna_de_la_tp(estudio_http) -> None:
    _, item_id = await _item_con_enunciados(estudio_http, ejercicio=False)
    r = await _traza(estudio_http, item_id)
    assert r.status_code == 200, r.text
    assert r.json()["enunciado"] == {"tp_md": "Consigna de la TP", "ejercicio_md": None}


async def test_muestra_la_version_editada_del_enunciado(estudio_http) -> None:
    episodio = estudio_http.ctr.agregar()
    item_id = await estudio_http.insertar_item_sql(episodio)
    problema = UUID(estudio_http.ctr.episodios[episodio]["problema_id"])
    await estudio_http.insertar_enunciado_sql(
        "tp", problema, "Original con Prof. Perez", mostrado="Editada"
    )
    r = await _traza(estudio_http, item_id)
    assert r.status_code == 200, r.text
    assert r.json()["enunciado"]["tp_md"] == "Editada"


async def test_el_investigador_tambien_la_ve(estudio_http) -> None:
    _, item_id = await _item_con_enunciados(estudio_http)
    assert (await _traza(estudio_http, item_id, estudio_http.investigador)).status_code == 200


async def test_ancla_del_estudio_tambien_se_sirve(estudio_http) -> None:
    await estudio_http.pedir(
        "POST", "/codebook", estudio_http.investigador, json={"etiqueta": "v0"}
    )
    episodio = estudio_http.ctr.agregar()
    ancla = await estudio_http.insertar_item_sql(episodio, ancla_de="v0")
    problema = UUID(estudio_http.ctr.episodios[episodio]["problema_id"])
    await estudio_http.insertar_enunciado_sql("tp", problema, "Consigna")
    r = await _traza(estudio_http, ancla)
    assert r.status_code == 200, r.text


async def test_evento_agregado_despues_de_la_carga_no_aparece(estudio_http) -> None:
    episodio, item_id = await _item_con_enunciados(estudio_http)
    antes = (await _traza(estudio_http, item_id)).json()
    estudio_http.ctr.evento(episodio, "prompt_enviado", {"content": "volvi despues"}, estado="open")
    despues = await _traza(estudio_http, item_id)
    assert despues.status_code == 200
    assert despues.json() == antes
    assert "volvi despues" not in despues.text


@pytest.mark.parametrize("caso", ["episode_id_real", "inexistente", "de_otro_estudio"])
async def test_identificador_ajeno_da_404(estudio_http, caso) -> None:
    episodio, _ = await _item_con_enunciados(estudio_http)
    if caso == "episode_id_real":
        objetivo = episodio
    elif caso == "inexistente":
        objetivo = uuid4()
    else:
        otro = estudio_http.clave
        estudio_http.clave = "otro-estudio"
        r = await estudio_http.client.post(
            estudio_http.BASE,
            json={"clave": "otro-estudio", "titulo": "x"},
            headers=estudio_http.admin.headers(),
        )
        assert r.status_code == 201
        episodio_otro = estudio_http.ctr.agregar()
        objetivo = await estudio_http.insertar_item_sql(episodio_otro)
        estudio_http.clave = otro
    r = await _traza(estudio_http, objetivo)
    assert r.status_code == 404
    llamados = {ep for _, ep in estudio_http.ctr.llamadas}
    assert UUID(str(objetivo)) not in llamados


async def test_sin_membresia_da_403(estudio_http) -> None:
    _, item_id = await _item_con_enunciados(estudio_http)
    assert (await _traza(estudio_http, item_id, estudio_http.ajeno)).status_code == 403
    assert estudio_http.ctr.llamadas == []


@pytest.mark.parametrize("modo", ["caido", "timeout"])
async def test_ctr_caido_da_502_generico(estudio_http, modo) -> None:
    _, item_id = await _item_con_enunciados(estudio_http)
    estudio_http.ctr.modo = modo
    r = await _traza(estudio_http, item_id)
    assert r.status_code == 502
    assert modo not in r.text


@pytest.mark.parametrize("cuerpo", ["<html>proxy secreto</html>", '{"events": "secreto"}'])
async def test_ctr_200_no_json_o_con_otra_forma_da_502_generico(estudio_http, cuerpo) -> None:
    """verify-1, F6: con el lector REAL (no el falso) sobre un CTR que responde
    200 con un cuerpo que no es el episodio."""
    import httpx
    from classifier_service.main import app
    from classifier_service.services.ctr_lectura import CTRLector, get_ctr_lector

    _, item_id = await _item_con_enunciados(estudio_http)
    transporte = httpx.MockTransport(
        lambda r: httpx.Response(200, text=cuerpo, headers={"content-type": "text/html"})
    )
    app.dependency_overrides[get_ctr_lector] = lambda: CTRLector("http://ctr", transport=transporte)
    r = await _traza(estudio_http, item_id)
    assert r.status_code == 502
    assert "secreto" not in r.text


async def test_ctr_con_ts_que_no_se_parsea_da_502_generico(estudio_http) -> None:
    """verify-2, N2: el episodio coincide con la evidencia fija (pasa el tope)
    pero un `ts` no es ISO 8601: antes, `filtrar_traza` lanzaba y daba 500."""
    import copy as _c

    import httpx
    from classifier_service.main import app
    from classifier_service.services.ctr_lectura import CTRLector, get_ctr_lector

    episodio, item_id = await _item_con_enunciados(estudio_http)
    datos = _c.deepcopy(estudio_http.ctr.episodios[episodio])
    datos["events"][-1]["ts"] = "ayer secreto"
    transporte = httpx.MockTransport(lambda r: httpx.Response(200, json=datos))
    app.dependency_overrides[get_ctr_lector] = lambda: CTRLector("http://ctr", transport=transporte)
    r = await _traza(estudio_http, item_id)
    assert r.status_code == 502
    assert "secreto" not in r.text


async def test_tope_alterado_da_409_y_log(estudio_http, caplog) -> None:
    episodio, item_id = await _item_con_enunciados(estudio_http)
    estudio_http.ctr.episodios[episodio]["events"][-1]["chain_hash"] = "f" * 64
    with caplog.at_level(logging.WARNING, logger="classifier_service.routes.estudio"):
        r = await _traza(estudio_http, item_id)
    assert _sd(r) == (409, "evidencia_alterada")
    assert "elementos" not in r.text
    eventos = [rec for rec in caplog.records if rec.getMessage() == "estudio_evidencia_alterada"]
    assert [rec.item_id for rec in eventos] == [str(item_id)]


async def test_tope_inexistente_da_409(estudio_http) -> None:
    episodio, item_id = await _item_con_enunciados(estudio_http)
    estudio_http.ctr.episodios[episodio]["events"].pop()
    r = await _traza(estudio_http, item_id)
    assert _sd(r) == (409, "evidencia_alterada")


async def test_traza_version_distinta_da_409(estudio_http) -> None:
    _, item_id = await _item_con_enunciados(estudio_http)
    await estudio_http.sql(
        "UPDATE estudio_codificacion SET traza_version = 'traza_v0' WHERE clave = :c",
        {"c": estudio_http.clave},
        commit=True,
    )
    r = await _traza(estudio_http, item_id)
    assert _sd(r) == (409, "traza_version_distinta")


@pytest.mark.parametrize("revisado", [False, None])
async def test_enunciado_pendiente_da_409(estudio_http, revisado) -> None:
    if revisado is None:
        episodio = estudio_http.ctr.agregar(ejercicio_id=uuid4())
        item_id = await estudio_http.insertar_item_sql(episodio)
        problema = UUID(estudio_http.ctr.episodios[episodio]["problema_id"])
        await estudio_http.insertar_enunciado_sql("tp", problema, "Consigna de la TP")
    else:
        _, item_id = await _item_con_enunciados(estudio_http, ejercicio=True, revisado=False)
    r = await _traza(estudio_http, item_id)
    assert _sd(r) == (409, "enunciado_pendiente")
    assert estudio_http.ctr.llamadas == []
