"""Tests del juez LLM del eje superficial↔reflexiva (regimen_llm.py).

Cubren lo crítico del diseño v4: la regla de decisión en código (la garantía,
no el LLM), el descarte de salidas inconsistentes, el ruteo por baja confianza,
el manejo de salidas inválidas, y el armado del contexto. Ningún test pega al
ai-gateway: el `complete` se inyecta como mock.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from uuid import uuid4

import pytest
from classifier_service.services.regimen_llm import (
    RegimenLLMRaw,
    armar_contexto,
    clasificar_regimen_llm,
    regimen_segun_regla,
)

TENANT = uuid4()


def _raw(verb, verif, just, oraculo, regimen, conf=0.9) -> RegimenLLMRaw:
    return RegimenLLMRaw.model_validate(
        {
            "verbalizacion": {"presente": verb, "evidencia": "x" if verb else ""},
            "verificacion": {"presente": verif, "evidencia": "x" if verif else ""},
            "justificacion": {"presente": just, "evidencia": "x" if just else ""},
            "autonomia": {"oraculo": oraculo, "evidencia": "x"},
            "regimen": regimen,
            "confianza": conf,
            "justificacion_global": "test",
        }
    )


# ── La regla de decisión (espejo del criterio docente) ────────────────────
def test_regla_reflexiva_cumple_las_tres_condiciones() -> None:
    # (a) verbaliza, (b) verifica O justifica, (c) no oráculo
    assert regimen_segun_regla(_raw(True, True, False, False, "REFLEXIVA")) == "REFLEXIVA"
    assert regimen_segun_regla(_raw(True, False, True, False, "REFLEXIVA")) == "REFLEXIVA"


def test_regla_sin_verbalizacion_es_superficial() -> None:
    # falta (a) — aunque verifique y justifique
    assert regimen_segun_regla(_raw(False, True, True, False, "REFLEXIVA")) == "SUPERFICIAL"


def test_regla_oraculo_bloquea_reflexiva() -> None:
    # condición (c): autonomía=oráculo fuerza SUPERFICIAL aunque verbalice y justifique
    assert regimen_segun_regla(_raw(True, True, True, True, "REFLEXIVA")) == "SUPERFICIAL"


def test_regla_sin_verificacion_ni_justificacion_es_superficial() -> None:
    # falta (b)
    assert regimen_segun_regla(_raw(True, False, False, False, "REFLEXIVA")) == "SUPERFICIAL"


# ── Armado del contexto ───────────────────────────────────────────────────
def test_armar_contexto_extrae_dialogo_y_conteos() -> None:
    events = [
        {"seq": 2, "event_type": "prompt_enviado", "payload": {"content": "por qué da error?"}},
        {"seq": 3, "event_type": "tutor_respondio", "payload": {"content": "qué esperás que pase?"}},
        {"seq": 4, "event_type": "codigo_ejecutado", "payload": {"stderr": "NameError"}},
        {"seq": 5, "event_type": "codigo_ejecutado", "payload": {"stderr": ""}},
        {"seq": 6, "event_type": "edicion_codigo", "payload": {"snapshot": "print('hola')"}},
    ]
    ctx = armar_contexto(events)
    assert "ALUMNO: por qué da error?" in ctx["transcript"]
    assert "TUTOR: qué esperás que pase?" in ctx["transcript"]
    assert ctx["n_exec"] == 2
    assert ctx["n_prompts"] == 1
    assert "print('hola')" in ctx["codigo_y_notas"]


def test_armar_contexto_episodio_mudo() -> None:
    ctx = armar_contexto([{"seq": 1, "event_type": "codigo_ejecutado", "payload": {}}])
    assert "sin diálogo" in ctx["transcript"]
    assert ctx["n_prompts"] == 0


# ── Flujo completo con `complete` mockeado ────────────────────────────────
def _mock_complete(salida: dict | str):
    """Devuelve un callable async que ignora los args y responde `salida`."""
    content = salida if isinstance(salida, str) else json.dumps(salida, ensure_ascii=False)

    async def _fn(**_kwargs):
        return SimpleNamespace(content=content)

    return _fn


_EVENTS = [{"seq": 1, "event_type": "prompt_enviado", "payload": {"content": "test"}}]


@pytest.mark.asyncio
async def test_clasifica_ok_cuando_es_consistente_y_confiado() -> None:
    salida = _raw(True, True, True, False, "REFLEXIVA", conf=0.95).model_dump()
    r = await clasificar_regimen_llm(
        events=_EVENTS, enunciado="x", episode_id="e1",
        complete=_mock_complete(salida), model="gpt-4o", tenant_id=TENANT,
    )
    assert r.estado == "ok"
    assert r.regimen == "REFLEXIVA"
    assert r.prompt_version  # pinneado para auditoría


@pytest.mark.asyncio
async def test_descarta_si_el_modelo_contradice_la_regla() -> None:
    # El modelo dice REFLEXIVA pero las dimensiones (oráculo) dan SUPERFICIAL.
    salida = _raw(True, True, True, True, "REFLEXIVA").model_dump()
    r = await clasificar_regimen_llm(
        events=_EVENTS, enunciado="x", episode_id="e2",
        complete=_mock_complete(salida), model="gpt-4o", tenant_id=TENANT,
    )
    assert r.estado == "inconsistente"
    assert r.regimen is None  # no se infiere etiqueta de salida inconsistente


@pytest.mark.asyncio
async def test_rutea_a_revision_si_baja_confianza() -> None:
    salida = _raw(True, True, True, False, "REFLEXIVA", conf=0.4).model_dump()
    r = await clasificar_regimen_llm(
        events=_EVENTS, enunciado="x", episode_id="e3",
        complete=_mock_complete(salida), model="gpt-4o", tenant_id=TENANT,
    )
    assert r.estado == "baja_confianza"
    assert r.regimen is None


@pytest.mark.asyncio
async def test_error_parseo_si_json_invalido() -> None:
    r = await clasificar_regimen_llm(
        events=_EVENTS, enunciado="x", episode_id="e4",
        complete=_mock_complete("esto no es json"), model="gpt-4o", tenant_id=TENANT,
        max_reintentos=1,
    )
    assert r.estado == "error_parseo"
    assert r.regimen is None


# ── Modo sombra en el pipeline (helper de classify_ep) ────────────────────
from classifier_service.config import settings as _settings
from classifier_service.routes.classify_ep import (
    _aplicar_juez_eje_fino_sombra,
)


class _FakeResult:
    def __init__(self, features: dict) -> None:
        self.features = features


@pytest.mark.asyncio
async def test_sombra_noop_con_flag_off(monkeypatch) -> None:
    """Con el flag OFF (default), el modo sombra no toca nada ni llama al LLM."""
    monkeypatch.setattr(_settings, "eje_fino_llm_enabled", False)
    result = _FakeResult({"subgrupo": {"key": "colaborador_reflexivo"}})
    await _aplicar_juez_eje_fino_sombra(result, [], uuid4(), {}, uuid4())
    assert "regimen_llm" not in result.features


@pytest.mark.asyncio
async def test_sombra_noop_fuera_de_zona_gris(monkeypatch) -> None:
    """Aunque el flag esté ON, la pasiva (no zona gris) no pasa por el juez."""
    monkeypatch.setattr(_settings, "eje_fino_llm_enabled", True)
    result = _FakeResult({"subgrupo": {"key": "dependiente_sobreuso"}})
    await _aplicar_juez_eje_fino_sombra(result, [], uuid4(), {}, uuid4())
    assert "regimen_llm" not in result.features


@pytest.mark.asyncio
async def test_sombra_mete_veredicto_en_features_cuando_on(monkeypatch) -> None:
    """Flag ON + zona gris + LLM consistente → el veredicto va a features['regimen_llm']."""
    from classifier_service.services.clients import AIGatewayClient

    monkeypatch.setattr(_settings, "eje_fino_llm_enabled", True)
    salida = _raw(True, True, True, False, "REFLEXIVA", conf=0.95).model_dump()

    async def _fake_complete(self, **_kwargs):  # bound method: recibe self
        return SimpleNamespace(content=json.dumps(salida, ensure_ascii=False))

    monkeypatch.setattr(AIGatewayClient, "complete", _fake_complete)
    result = _FakeResult({"subgrupo": {"key": "colaborador_funcional"}})
    await _aplicar_juez_eje_fino_sombra(result, _EVENTS, uuid4(), {}, uuid4())

    rl = result.features.get("regimen_llm")
    assert rl is not None and rl["estado"] == "ok"
    assert rl["regimen"] == "REFLEXIVA"
    assert rl["prompt_version"]  # pinneado


@pytest.mark.asyncio
async def test_sombra_no_rompe_si_el_llm_falla(monkeypatch) -> None:
    """Best-effort: si el ai-gateway falla, el modo sombra loguea y NO propaga."""
    from classifier_service.services.clients import AIGatewayClient

    monkeypatch.setattr(_settings, "eje_fino_llm_enabled", True)

    async def _boom(self, **_kwargs):
        raise RuntimeError("ai-gateway caído")

    monkeypatch.setattr(AIGatewayClient, "complete", _boom)
    result = _FakeResult({"subgrupo": {"key": "colaborador_reflexivo"}})
    # No debe levantar excepción (best-effort) ni escribir un veredicto.
    await _aplicar_juez_eje_fino_sombra(result, _EVENTS, uuid4(), {}, uuid4())
    assert "regimen_llm" not in result.features
