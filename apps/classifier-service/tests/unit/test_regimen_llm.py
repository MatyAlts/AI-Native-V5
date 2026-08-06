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
        {
            "seq": 3,
            "event_type": "tutor_respondio",
            "payload": {"content": "qué esperás que pase?"},
        },
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
def _mock_complete(salida: dict | str, output_tokens: int = 50):
    """Devuelve un callable async que ignora los args y responde `salida`.

    `output_tokens` viaja en el doble porque el codigo lo usa para distinguir
    una respuesta TRUNCADA de un JSON mal formado. Un doble sin ese campo hace
    que el test recorra un camino que en produccion no existe: `CompleteResult`
    siempre lo trae.
    """
    content = salida if isinstance(salida, str) else json.dumps(salida, ensure_ascii=False)

    async def _fn(**_kwargs):
        return SimpleNamespace(content=content, output_tokens=output_tokens)

    return _fn


_EVENTS = [{"seq": 1, "event_type": "prompt_enviado", "payload": {"content": "test"}}]


@pytest.mark.asyncio
async def test_clasifica_ok_cuando_es_consistente_y_confiado() -> None:
    salida = _raw(True, True, True, False, "REFLEXIVA", conf=0.95).model_dump()
    r = await clasificar_regimen_llm(
        events=_EVENTS,
        enunciado="x",
        episode_id="e1",
        complete=_mock_complete(salida),
        model="gpt-4o",
        tenant_id=TENANT,
    )
    assert r.estado == "ok"
    assert r.regimen == "REFLEXIVA"
    assert r.prompt_version  # pinneado para auditoría


@pytest.mark.asyncio
async def test_descarta_si_el_modelo_contradice_la_regla() -> None:
    # El modelo dice REFLEXIVA pero las dimensiones (oráculo) dan SUPERFICIAL.
    salida = _raw(True, True, True, True, "REFLEXIVA").model_dump()
    r = await clasificar_regimen_llm(
        events=_EVENTS,
        enunciado="x",
        episode_id="e2",
        complete=_mock_complete(salida),
        model="gpt-4o",
        tenant_id=TENANT,
    )
    assert r.estado == "inconsistente"
    assert r.regimen is None  # no se infiere etiqueta de salida inconsistente


@pytest.mark.asyncio
async def test_rutea_a_revision_si_baja_confianza() -> None:
    salida = _raw(True, True, True, False, "REFLEXIVA", conf=0.4).model_dump()
    r = await clasificar_regimen_llm(
        events=_EVENTS,
        enunciado="x",
        episode_id="e3",
        complete=_mock_complete(salida),
        model="gpt-4o",
        tenant_id=TENANT,
    )
    assert r.estado == "baja_confianza"
    assert r.regimen is None


@pytest.mark.asyncio
async def test_error_parseo_si_json_invalido() -> None:
    r = await clasificar_regimen_llm(
        events=_EVENTS,
        enunciado="x",
        episode_id="e4",
        complete=_mock_complete("esto no es json"),
        model="gpt-4o",
        tenant_id=TENANT,
        max_reintentos=1,
    )
    assert r.estado == "error_parseo"
    assert r.regimen is None


@pytest.mark.asyncio
async def test_truncado_no_reintenta_y_queda_registrado() -> None:
    """Una respuesta cortada por el techo de tokens NO se reintenta.

    El juez corre con `temperature=0.0`: el reintento es determinista y devuelve
    el MISMO corte. Reintentar quema tres llamadas al LLM para el mismo fallo —
    es el error que costo el incidente del wizard de ejercicios (27/07).

    Y el motivo tiene que quedar en `razon`, que se persiste en
    `features['regimen_llm']`. Sin eso, separar truncado de JSON roto obliga a
    ir a los logs del contenedor, que rotan.
    """
    llamadas = []

    async def _fn(**kwargs):
        llamadas.append(1)
        # JSON bien formado pero cortado a la mitad, con la salida en el techo.
        return SimpleNamespace(content='{"regimen": "REFLE', output_tokens=kwargs["max_tokens"])

    r = await clasificar_regimen_llm(
        events=_EVENTS,
        enunciado="x",
        episode_id="e-trunc",
        complete=_fn,
        model="gpt-4o",
        tenant_id=TENANT,
        max_reintentos=2,
        max_tokens=100,
    )
    assert r.estado == "error_parseo"
    assert r.regimen is None
    assert len(llamadas) == 1, "un truncado no se reintenta"
    assert "truncada" in r.razon
    assert "100" in r.razon, "el techo tiene que estar en el motivo, para poder subirlo"


@pytest.mark.asyncio
async def test_json_roto_no_truncado_si_reintenta() -> None:
    """El contrapunto: si NO llego al techo, el fallo puede ser transitorio y se reintenta."""
    llamadas = []

    async def _fn(**_kwargs):
        llamadas.append(1)
        return SimpleNamespace(content="esto no es json", output_tokens=12)

    r = await clasificar_regimen_llm(
        events=_EVENTS,
        enunciado="x",
        episode_id="e-roto",
        complete=_fn,
        model="gpt-4o",
        tenant_id=TENANT,
        max_reintentos=2,
        max_tokens=100,
    )
    assert r.estado == "error_parseo"
    assert len(llamadas) == 3, "sin truncamiento se agotan los reintentos"
    assert "truncada" not in r.razon


def _raw_sin_evidencia(regimen: str, *, verb: bool = False, verif: bool = False) -> dict:
    """Payload con las CUATRO `evidencia` vacias.

    `_raw` pone siempre `autonomia.evidencia = "x"`, asi que con ese helper
    `_hay_evidencia_citable` devuelve True SIEMPRE y la rama queda inalcanzable
    desde los tests. Por eso el bug de los 7 episodios del piloto no lo agarro
    ninguno: el doble hacia imposible el caso que se daba en produccion.
    """
    return {
        "verbalizacion": {"presente": verb, "evidencia": ""},
        "verificacion": {"presente": verif, "evidencia": ""},
        "justificacion": {"presente": False, "evidencia": ""},
        "autonomia": {"oraculo": False, "evidencia": ""},
        "regimen": regimen,
        "confianza": 0.9,
        "justificacion_global": "test",
    }


@pytest.mark.asyncio
async def test_superficial_sin_evidencia_es_ok() -> None:
    """Un episodio vacio no tiene nada que citar, y eso NO invalida el veredicto.

    Si el alumno no razono, no verifico y no justifico, las cuatro dimensiones
    vuelven vacias: no hay frase que citar porque no ocurrio. Exigir la cita ahi
    es pedir evidencia de una ausencia — y descartaba el SUPERFICIAL correcto,
    dejando que la etiqueta cayera al proxy conductual (que puede decir
    "apropiacion reflexiva"). 7 de 12 `inconsistente` del piloto eran este caso.
    """
    r = await clasificar_regimen_llm(
        events=_EVENTS,
        enunciado="x",
        episode_id="e-sup-vacio",
        complete=_mock_complete(_raw_sin_evidencia("SUPERFICIAL")),
        model="gpt-4o",
        tenant_id=TENANT,
    )
    assert r.estado == "ok"
    assert r.regimen == "SUPERFICIAL"


@pytest.mark.asyncio
async def test_reflexiva_sin_evidencia_sigue_inconsistente() -> None:
    """El contrapunto: afirmar REFLEXIVA sin citar una sola frase NO es verificable.

    Aca el juez esta afirmando que hubo marcadores. Una afirmacion sin cita se
    sigue mandando a revision humana — esa exigencia no se relaja.
    """
    r = await clasificar_regimen_llm(
        events=_EVENTS,
        enunciado="x",
        episode_id="e-ref-vacio",
        complete=_mock_complete(_raw_sin_evidencia("REFLEXIVA", verb=True, verif=True)),
        model="gpt-4o",
        tenant_id=TENANT,
    )
    assert r.estado == "inconsistente"
    assert r.regimen is None
    assert "no cita evidencia" in r.razon


# ── El juez GOBIERNA la etiqueta en el pipeline (helper de classify_ep, v4.0.0) ──
from classifier_service.config import settings as _settings
from classifier_service.routes.classify_ep import (
    _aplicar_juez_eje_fino,
)


class _FakeResult:
    """Mimetiza ClassificationResult: el juez puede gobernar appropriation/reason."""

    def __init__(self, features: dict, appropriation: str = "apropiacion_superficial") -> None:
        self.features = features
        self.appropriation = appropriation
        self.reason = "proxy conductual (subgrupo)"


@pytest.mark.asyncio
async def test_juez_noop_con_flag_off(monkeypatch) -> None:
    """Con el flag OFF, el juez no corre: ni veredicto ni cambio de etiqueta."""
    monkeypatch.setattr(_settings, "eje_fino_llm_enabled", False)
    result = _FakeResult({"subgrupo": {"key": "colaborador_reflexivo"}})
    await _aplicar_juez_eje_fino(result, [], uuid4(), {}, uuid4())
    assert "regimen_llm" not in result.features
    assert result.appropriation == "apropiacion_superficial"


@pytest.mark.asyncio
async def test_juez_noop_para_delegacion_pasiva(monkeypatch) -> None:
    """La delegación pasiva (overuse) la resuelve la etapa dura, NO el juez."""
    monkeypatch.setattr(_settings, "eje_fino_llm_enabled", True)
    result = _FakeResult(
        {"subgrupo": {"key": "dependiente_sobreuso"}}, appropriation="delegacion_pasiva"
    )
    await _aplicar_juez_eje_fino(result, [], uuid4(), {}, uuid4())
    assert "regimen_llm" not in result.features
    assert result.appropriation == "delegacion_pasiva"  # intacto


@pytest.mark.asyncio
async def test_juez_gobierna_appropriation_cuando_ok(monkeypatch) -> None:
    """Flag ON + con-tutor no-delegación + veredicto OK → el juez GOBIERNA la etiqueta."""
    from classifier_service.services.clients import AIGatewayClient

    monkeypatch.setattr(_settings, "eje_fino_llm_enabled", True)
    salida = _raw(True, True, True, False, "REFLEXIVA", conf=0.95).model_dump()

    async def _fake_complete(self, **_kwargs):  # bound method: recibe self
        return SimpleNamespace(content=json.dumps(salida, ensure_ascii=False), output_tokens=50)

    monkeypatch.setattr(AIGatewayClient, "complete", _fake_complete)
    # Arranca como superficial (proxy) y el juez lo sube a reflexiva.
    result = _FakeResult({"subgrupo": {"key": "colaborador_funcional"}})
    await _aplicar_juez_eje_fino(result, _EVENTS, uuid4(), {}, uuid4())

    rl = result.features.get("regimen_llm")
    assert rl is not None and rl["estado"] == "ok" and rl["regimen"] == "REFLEXIVA"
    assert result.appropriation == "apropiacion_reflexiva"  # gobernada por el juez
    assert "needs_review" not in result.features


@pytest.mark.asyncio
async def test_juez_desenganchado_con_tutor_pasa_por_el_juez(monkeypatch) -> None:
    """v4.0.0: el `desenganchado` (con-tutor) ahora también lo gobierna el juez."""
    from classifier_service.services.clients import AIGatewayClient

    monkeypatch.setattr(_settings, "eje_fino_llm_enabled", True)
    salida = _raw(False, False, False, True, "SUPERFICIAL", conf=0.9).model_dump()

    async def _fake_complete(self, **_kwargs):
        return SimpleNamespace(content=json.dumps(salida, ensure_ascii=False), output_tokens=50)

    monkeypatch.setattr(AIGatewayClient, "complete", _fake_complete)
    result = _FakeResult({"subgrupo": {"key": "desenganchado"}})
    await _aplicar_juez_eje_fino(result, _EVENTS, uuid4(), {}, uuid4())
    assert result.features["regimen_llm"]["estado"] == "ok"
    assert result.appropriation == "apropiacion_superficial"


@pytest.mark.asyncio
async def test_fallback_proxy_y_needs_review_si_veredicto_no_ok(monkeypatch) -> None:
    """Veredicto no-ok (baja confianza) → se conserva el proxy + needs_review."""
    from classifier_service.services.clients import AIGatewayClient

    monkeypatch.setattr(_settings, "eje_fino_llm_enabled", True)
    salida = _raw(True, True, True, False, "REFLEXIVA", conf=0.3).model_dump()  # conf < 0.70

    async def _fake_complete(self, **_kwargs):
        return SimpleNamespace(content=json.dumps(salida, ensure_ascii=False), output_tokens=50)

    monkeypatch.setattr(AIGatewayClient, "complete", _fake_complete)
    result = _FakeResult({"subgrupo": {"key": "colaborador_reflexivo"}})
    await _aplicar_juez_eje_fino(result, _EVENTS, uuid4(), {}, uuid4())

    # El veredicto crudo se guarda, pero NO gobierna: etiqueta del proxy intacta.
    assert result.features["regimen_llm"]["estado"] == "baja_confianza"
    assert result.appropriation == "apropiacion_superficial"  # proxy conservado
    assert result.features["needs_review"] is True
    assert "baja_confianza" in result.features["needs_review_reason"]


@pytest.mark.asyncio
async def test_fallback_proxy_y_needs_review_si_veredicto_inconsistente(monkeypatch) -> None:
    """Veredicto inconsistente (modelo contradice la regla) → proxy + needs_review."""
    from classifier_service.services.clients import AIGatewayClient

    monkeypatch.setattr(_settings, "eje_fino_llm_enabled", True)
    # Modelo dice REFLEXIVA pero autonomía=oráculo → la regla da SUPERFICIAL.
    salida = _raw(True, True, True, True, "REFLEXIVA", conf=0.9).model_dump()

    async def _fake_complete(self, **_kwargs):
        return SimpleNamespace(content=json.dumps(salida, ensure_ascii=False), output_tokens=50)

    monkeypatch.setattr(AIGatewayClient, "complete", _fake_complete)
    result = _FakeResult({"subgrupo": {"key": "colaborador_reflexivo"}})
    await _aplicar_juez_eje_fino(result, _EVENTS, uuid4(), {}, uuid4())

    assert result.features["regimen_llm"]["estado"] == "inconsistente"
    assert result.appropriation == "apropiacion_superficial"  # proxy conservado
    assert result.features["needs_review"] is True
    assert "inconsistente" in result.features["needs_review_reason"]


@pytest.mark.asyncio
async def test_fallback_proxy_y_needs_review_si_error_parseo(monkeypatch) -> None:
    """Veredicto error_parseo (JSON inválido) → proxy + needs_review."""
    from classifier_service.services.clients import AIGatewayClient

    monkeypatch.setattr(_settings, "eje_fino_llm_enabled", True)

    async def _fake_complete(self, **_kwargs):
        return SimpleNamespace(content="esto no es json", output_tokens=12)

    monkeypatch.setattr(AIGatewayClient, "complete", _fake_complete)
    result = _FakeResult({"subgrupo": {"key": "desenganchado"}})
    await _aplicar_juez_eje_fino(result, _EVENTS, uuid4(), {}, uuid4())

    assert result.features["regimen_llm"]["estado"] == "error_parseo"
    assert result.appropriation == "apropiacion_superficial"  # proxy conservado
    assert result.features["needs_review"] is True
    assert "error_parseo" in result.features["needs_review_reason"]


@pytest.mark.asyncio
async def test_fallback_no_rompe_el_cierre_si_el_gateway_falla(monkeypatch) -> None:
    """Crítico: si el ai-gateway falla, NO se propaga; se conserva el proxy + needs_review."""
    from classifier_service.services.clients import AIGatewayClient

    monkeypatch.setattr(_settings, "eje_fino_llm_enabled", True)

    async def _boom(self, **_kwargs):
        raise RuntimeError("ai-gateway caído")

    monkeypatch.setattr(AIGatewayClient, "complete", _boom)
    result = _FakeResult({"subgrupo": {"key": "colaborador_reflexivo"}})
    # No debe levantar excepción (cerrar el episodio nunca falla por el LLM).
    await _aplicar_juez_eje_fino(result, _EVENTS, uuid4(), {}, uuid4())
    assert "regimen_llm" not in result.features  # nunca llegó a tener veredicto
    assert result.appropriation == "apropiacion_superficial"  # proxy conservado
    assert result.features["needs_review"] is True
    assert "error_gateway" in result.features["needs_review_reason"]
