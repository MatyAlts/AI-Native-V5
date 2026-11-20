"""Unitarios de apoyo del juez v3 (HU-005): salida, prompt, few-shot y enrutamiento.

La aceptación vive en `tests/aceptacion_hu005/`; estos cubren detalles de
construcción que la aceptación no fija.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from uuid import UUID

import pytest
from classifier_service.config import settings
from classifier_service.routes import classify_ep
from classifier_service.services import juez_v2, juez_v3
from classifier_service.services.juez_v2 import _verificar_evidencia
from classifier_service.services.juez_v2_sinteticos import SINTETICOS_ALBERTO
from classifier_service.services.juez_v3 import RegimenV3Raw
from classifier_service.services.regimen_llm import normalizar_regimen_llm_persistido
from classifier_service.services.regla_mtac import regimen_segun_regla_mtac
from pydantic import ValidationError

TENANT = UUID("00000000-0000-0000-0000-0000000000aa")
CLAVE = {"s-7f3a": "PASIVA", "s-2c9e": "SUPERFICIAL", "s-b41d": "REFLEXIVA"}


def _salida(**cambios) -> dict:
    base = dict(juez_v3._SALIDAS_FEWSHOT_V3["s-b41d"])
    base.update(cambios)
    return base


# ── Salida ──────────────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "frontera",
    [["REFLEXIVA"], ["REFLEXIVA", "REFLEXIVA"], ["REFLEXIVA", "SUPERFICIAL", "PASIVA"]],
)
def test_frontera_entre_tiene_que_ser_vacia_o_dos_distintos(frontera):
    with pytest.raises(ValidationError):
        RegimenV3Raw.model_validate(_salida(es_frontera=True, frontera_entre=frontera))


def test_frontera_entre_acepta_evidencia_insuficiente():
    raw = RegimenV3Raw.model_validate(
        _salida(es_frontera=True, frontera_entre=["SUPERFICIAL", "EVIDENCIA_INSUFICIENTE"])
    )
    assert raw.frontera_entre == ["SUPERFICIAL", "EVIDENCIA_INSUFICIENTE"]


def test_schema_v3_suma_la_frontera_sin_tocar_el_del_v2():
    v3 = juez_v3.RESPONSE_JSON_SCHEMA_V3["json_schema"]["schema"]
    v2 = juez_v2.RESPONSE_JSON_SCHEMA_V2["json_schema"]["schema"]
    assert set(v3["properties"]["frontera_entre"]["items"]["enum"]) == {
        "REFLEXIVA",
        "SUPERFICIAL",
        "PASIVA",
        "EVIDENCIA_INSUFICIENTE",
    }
    assert "es_frontera" not in v2["properties"]
    assert "es_frontera" not in v2["required"]


# ── Prompt ──────────────────────────────────────────────────────────────────
def test_prompt_v3_reusa_d1_a_d3_y_la_regla_del_v2_y_cambia_la_d4():
    for seccion in (juez_v2._SECCION_D1_D3, juez_v2._SECCION_REGIMENES_Y_REGLA):
        assert seccion in juez_v3.SYSTEM_PROMPT_V3
        assert seccion in juez_v2.SYSTEM_PROMPT_V2
    assert juez_v2._SECCION_D4_V2 not in juez_v3.SYSTEM_PROMPT_V3
    assert "¿usa la IA para pensar o para que piense por él?" not in juez_v3.SYSTEM_PROMPT_V3
    assert "codebook MTAC v2" in juez_v3.SYSTEM_PROMPT_V3


def test_ejemplos_v3_solo_de_fuentes_permitidas():
    anclas = {"9a54cd3b", "c06498f3", "11007e5f", "2c3a952b", "622a9ba0"}
    sinteticos = {f"sintetico_alberto {sid}" for sid in SINTETICOS_ALBERTO}
    permitidas = anclas | sinteticos | {"codebook_v1 §8"}
    assert {e["fuente"] for e in juez_v3.EJEMPLOS_FRONTERA_V3} <= permitidas


# ── Few-shot ────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("sid", list(juez_v3._SALIDAS_FEWSHOT_V3))
def test_fewshot_v3_pasa_la_verificacion_y_da_el_regimen_de_la_clave(sid):
    raw = RegimenV3Raw.model_validate(juez_v3._SALIDAS_FEWSHOT_V3[sid])
    assert _verificar_evidencia(raw, SINTETICOS_ALBERTO[sid]["elementos"]) is None
    d = (raw.d1_verbalizacion, raw.d2_verificacion, raw.d3_justificacion, raw.d4_autonomia)
    assert regimen_segun_regla_mtac(*(x.valor for x in d)) == raw.regimen == CLAVE[sid]


def test_mensajes_v3_tienen_los_tres_fewshot_con_salida_v3():
    msgs = juez_v3.construir_mensajes_v3("TRAZA", "E", "id")
    asistentes = [json.loads(m["content"]) for m in msgs if m["role"] == "assistant"]
    assert len(asistentes) == 3
    assert all("es_frontera" in a and "frontera_entre" in a for a in asistentes)


# ── Enrutamiento ────────────────────────────────────────────────────────────
async def test_v3_con_gateway_caido_deja_la_ex_pasiva_sin_clasificar(monkeypatch):
    async def _explota(**kw):
        raise RuntimeError("gateway caído")

    async def _no_llamar(**kw):
        raise AssertionError("con v3 no corre el v2")

    monkeypatch.setattr(settings, "eje_fino_llm_enabled", True)
    monkeypatch.setattr(settings, "eje_fino_juez_version", "v3")
    monkeypatch.setattr(classify_ep, "clasificar_regimen_v3", _explota)
    monkeypatch.setattr(classify_ep, "clasificar_regimen_v2", _no_llamar)
    monkeypatch.setattr(classify_ep, "AIGatewayClient", lambda **kw: SimpleNamespace(complete=None))
    res = SimpleNamespace(
        appropriation="delegacion_pasiva",
        reason="p",
        features={"subgrupo": {"key": "dependiente_delegador"}},
    )
    await classify_ep._aplicar_juez_eje_fino(res, [], UUID(int=1), {}, TENANT)
    assert res.appropriation == "sin_clasificar"
    assert res.features["needs_review_reason"] == "juez_v3_error_gateway: gateway caído"


def test_normalizar_v3_corrupto_devuelve_el_dato_tal_cual():
    corrupto = {"juez_version": "v3", "estado": "ok", "raw": {"es_frontera": "quizás"}}
    assert normalizar_regimen_llm_persistido(corrupto) == corrupto


def test_normalizar_no_confunde_un_registro_v3_con_uno_v2():
    raw = _salida(es_frontera=True, frontera_entre=["REFLEXIVA", "SUPERFICIAL"])
    registro = {
        "estado": "ok",
        "regimen": "REFLEXIVA",
        "confianza": "0.9",  # solo la validación v3 lo vuelve número
        "raw": raw,
        "razon": "r",
        "model_used": "m",
        "prompt_version": juez_v3.PROMPT_VERSION_V3,
        "juez_version": "v3",
    }
    leido = normalizar_regimen_llm_persistido(registro)
    assert leido["raw"]["frontera_entre"] == ["REFLEXIVA", "SUPERFICIAL"]
    assert leido["juez_version"] == "v3"
    assert leido["confianza"] == 0.9
