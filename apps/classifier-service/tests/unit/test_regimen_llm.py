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


def _raw_tri(v, e, j, a, regimen="SUPERFICIAL", conf=0.9) -> RegimenLLMRaw:
    """Construye un `RegimenLLMRaw` con las CUATRO dimensiones en formato
    trivaluado nativo (`"presente" | "ausente" | "no_evaluable"`), sin pasar
    por la coacción de booleanos legados. Es lo que emite el juez a partir de
    ahora (Tabla 3.11 + Tabla B.2)."""
    return RegimenLLMRaw.model_validate(
        {
            "verbalizacion": {"presente": v, "evidencia": "x" if v == "presente" else ""},
            "verificacion": {"presente": e, "evidencia": "x" if e == "presente" else ""},
            "justificacion": {"presente": j, "evidencia": "x" if j == "presente" else ""},
            "autonomia": {"presente": a, "evidencia": "x" if a == "presente" else ""},
            "regimen": regimen,
            "confianza": conf,
            "justificacion_global": "test",
        }
    )


# ── Dimensiones trivaluadas (B2a) y retrocompatibilidad de lectura ────────
def test_dim_acepta_no_evaluable_nativo() -> None:
    """Tabla B.2: las cuatro dimensiones admiten `no_evaluable`, no solo bool."""
    raw = _raw_tri("no_evaluable", "presente", "ausente", "presente")
    assert raw.verbalizacion.presente == "no_evaluable"


def test_dim_coacciona_booleano_legado_true_a_presente() -> None:
    """Retrocompatibilidad D2: `presente: true` persistido antes de esta change
    se sigue parseando, y pasa a valer el string `"presente"`."""
    raw = _raw(True, False, False, False, "SUPERFICIAL")
    assert raw.verbalizacion.presente == "presente"


def test_dim_coacciona_booleano_legado_false_a_ausente() -> None:
    raw = _raw(False, False, False, False, "SUPERFICIAL")
    assert raw.verbalizacion.presente == "ausente"


def test_autonomia_acepta_presente_nativo_trivaluado() -> None:
    """Corrección de D4: autonomía también es trivaluada (Tabla B.2 admite
    `no evaluable` para A cuando no hay propuestas del asistente que juzgar)."""
    raw = _raw_tri("presente", "presente", "ausente", "no_evaluable")
    assert raw.autonomia.presente == "no_evaluable"


def test_autonomia_coacciona_oraculo_legado_true_a_ausente() -> None:
    """`oraculo: true` (comportamiento oráculo) persistido antes de esta change
    equivale a autonomía AUSENTE en la escala trivaluada nueva."""
    raw = _raw(True, True, True, True, "SUPERFICIAL")
    assert raw.autonomia.presente == "ausente"


def test_autonomia_coacciona_oraculo_legado_false_a_presente() -> None:
    """`oraculo: false` (interlocutor) equivale a autonomía PRESENTE."""
    raw = _raw(True, True, True, False, "REFLEXIVA")
    assert raw.autonomia.presente == "presente"


def test_retrocompatibilidad_payload_real_del_piloto_produce_mismo_veredicto() -> None:
    """Requisito duro: un `features['regimen_llm']['raw']` real del piloto, con
    las CUATRO dimensiones en formato booleano legado, se re-parsea sin error y
    la regla determinista produce el MISMO veredicto que antes de esta change."""
    payload_legado = {
        "verbalizacion": {
            "presente": True,
            "evidencia": "la linea 13 agrega el producto al final",
        },
        "verificacion": {"presente": True, "evidencia": "'r' es solo lectura"},
        "justificacion": {"presente": True, "evidencia": "el formato 'a' es el correcto"},
        "autonomia": {"oraculo": False, "evidencia": "razona sin que se lo pidan"},
        "regimen": "REFLEXIVA",
        "confianza": 0.95,
        "justificacion_global": "test",
    }
    raw = RegimenLLMRaw.model_validate(payload_legado)
    assert regimen_segun_regla(raw) == "REFLEXIVA"


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


# ── Kleene fuerte (Tabla 3.11, D1) — los 4 casos en alcance de este commit ──
def test_kleene_caso1_v_a_y_al_menos_una_de_e_o_j_presentes_es_reflexiva() -> None:
    """Caso 1 de la Tabla 3.11: V, A y (E o J) presentes → apropiación
    reflexiva automática, sin que intervenga ningún `no_evaluable`."""
    assert (
        regimen_segun_regla(_raw_tri("presente", "presente", "ausente", "presente"))
        == "REFLEXIVA"
    )


def test_kleene_caso3_ausente_gana_sobre_no_evaluable_en_las_demas() -> None:
    """Caso 3 y propiedad definitoria de Kleene FUERTE (vs. débil): una
    dimensión que por sí sola hace falsa la fórmula (V ausente) decide
    SUPERFICIAL sin importar que las otras sean `no_evaluable`. Con Kleene
    débil este caso derivaría a revisión; con Kleene fuerte, no."""
    assert (
        regimen_segun_regla(
            _raw_tri("ausente", "no_evaluable", "no_evaluable", "no_evaluable")
        )
        == "SUPERFICIAL"
    )


def test_kleene_caso3_e_y_j_ambas_ausentes_es_superficial() -> None:
    """Caso 3, otra rama: E y J ambas ausentes hace falso el término (b),
    aunque V y A estén presentes."""
    assert (
        regimen_segun_regla(_raw_tri("presente", "ausente", "ausente", "presente"))
        == "SUPERFICIAL"
    )


def test_kleene_verificacion_no_evaluable_pero_justificacion_presente_determina() -> None:
    """D1, segunda fila de la tabla: si J ya es presente, el término (b) es
    verdadero aunque E sea `no_evaluable` — el veredicto queda determinado."""
    assert (
        regimen_segun_regla(_raw_tri("presente", "no_evaluable", "presente", "presente"))
        == "REFLEXIVA"
    )


def test_kleene_caso4_verbalizacion_no_evaluable_es_indeterminado() -> None:
    """Caso 4: ninguna dimensión hace falsa la fórmula y V es `no_evaluable`
    → indeterminado, deriva (no colapsa a ausente ni a presente)."""
    assert (
        regimen_segun_regla(_raw_tri("no_evaluable", "presente", "presente", "presente"))
        == "INDETERMINADO"
    )


def test_kleene_caso4_ejemplo_literal_de_la_tabla() -> None:
    """Caso 4, ejemplo textual de la tabla: V y A presentes, E no evaluable,
    J ausente → indeterminado (ninguna dimensión hace falsa la fórmula por sí
    sola, pero (b) queda indeciso)."""
    assert (
        regimen_segun_regla(_raw_tri("presente", "no_evaluable", "ausente", "presente"))
        == "INDETERMINADO"
    )


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


# ── Valores fuera de dominio de punta a punta (hueco de cobertura, QA) ─────
# El caso 5 de la Tabla 3.11 ("salida inválida") queda fuera de alcance de
# este commit (depende de B4). Lo que SÍ es alcance es que "no revienta" sea
# una propiedad VERIFICADA y no una afirmación de pasillo: `RegimenLLMRaw`
# rechaza estos payloads con `ValidationError`, que `clasificar_regimen_llm`
# ya atrapa junto al `JSONDecodeError` — pero hasta ahora nada lo probaba con
# un valor real fuera de dominio, solo con JSON mal formado.
@pytest.mark.asyncio
async def test_valor_fuera_de_dominio_en_enum_degrada_a_error_parseo() -> None:
    """`"quizas"` no es `presente|ausente|no_evaluable`: `Literal` lo rechaza,
    `ValidationError` sube, y el flujo entero degrada a `error_parseo` sin
    excepción no capturada."""
    salida = _raw_dict_tri("quizas", "presente", "presente", "presente", "REFLEXIVA")
    r = await clasificar_regimen_llm(
        events=_EVENTS,
        enunciado="x",
        episode_id="e-fuera-de-dominio",
        complete=_mock_complete(salida),
        model="gpt-4o",
        tenant_id=TENANT,
    )
    assert r.estado == "error_parseo"
    assert r.regimen is None


@pytest.mark.asyncio
async def test_valor_null_en_dimension_degrada_a_error_parseo() -> None:
    """Segundo caso: `null` en vez de un valor. Distinto camino de rechazo
    de Pydantic que un string fuera de enum (aquí ni siquiera hay coacción de
    booleano posible), mismo resultado: `error_parseo`."""
    salida = _raw_dict_tri("presente", "presente", "presente", "presente", "REFLEXIVA")
    salida["verbalizacion"]["presente"] = None
    r = await clasificar_regimen_llm(
        events=_EVENTS,
        enunciado="x",
        episode_id="e-null",
        complete=_mock_complete(salida),
        model="gpt-4o",
        tenant_id=TENANT,
    )
    assert r.estado == "error_parseo"
    assert r.regimen is None


@pytest.mark.asyncio
async def test_campo_faltante_en_el_payload_degrada_a_error_parseo() -> None:
    """Tercer caso: falta un campo requerido a nivel raíz (`confianza`)."""
    salida = _raw_dict_tri("presente", "presente", "presente", "presente", "REFLEXIVA")
    del salida["confianza"]
    r = await clasificar_regimen_llm(
        events=_EVENTS,
        enunciado="x",
        episode_id="e-sin-confianza",
        complete=_mock_complete(salida),
        model="gpt-4o",
        tenant_id=TENANT,
    )
    assert r.estado == "error_parseo"
    assert r.regimen is None


@pytest.mark.asyncio
async def test_dimension_faltante_en_el_payload_degrada_a_error_parseo() -> None:
    """Cuarto caso: falta una dimensión entera (`autonomia`), no solo un campo
    dentro de ella. `model_config = {"extra": "forbid"}` en `RegimenLLMRaw`
    hace que ni siquiera un payload con las otras tres dimensiones perfectas
    se salve — sigue siendo `ValidationError` → `error_parseo`."""
    salida = _raw_dict_tri("presente", "presente", "presente", "presente", "REFLEXIVA")
    del salida["autonomia"]
    r = await clasificar_regimen_llm(
        events=_EVENTS,
        enunciado="x",
        episode_id="e-sin-autonomia",
        complete=_mock_complete(salida),
        model="gpt-4o",
        tenant_id=TENANT,
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


def _raw_dict_tri(v, e, j, a, regimen: str, conf: float = 0.9) -> dict:
    """Como `_raw_tri` pero devuelve el dict crudo (payload del LLM), para
    inyectar en `_mock_complete` de los tests de `clasificar_regimen_llm`."""
    return {
        "verbalizacion": {"presente": v, "evidencia": "x" if v == "presente" else ""},
        "verificacion": {"presente": e, "evidencia": "x" if e == "presente" else ""},
        "justificacion": {"presente": j, "evidencia": "x" if j == "presente" else ""},
        "autonomia": {"presente": a, "evidencia": "x" if a == "presente" else ""},
        "regimen": regimen,
        "confianza": conf,
        "justificacion_global": "test",
    }


@pytest.mark.asyncio
async def test_abstencion_traza_insuficiente_cuando_regla_es_indeterminada() -> None:
    """Caso 4 de la Tabla 3.11 de punta a punta: la regla no puede decidir
    (V no evaluable, nada la hace falsa) → estado nuevo `abstencion_traza_
    insuficiente`, sin inferir ningún régimen."""
    salida = _raw_dict_tri("no_evaluable", "presente", "presente", "presente", "REFLEXIVA")
    r = await clasificar_regimen_llm(
        events=_EVENTS,
        enunciado="x",
        episode_id="e-abstencion",
        complete=_mock_complete(salida),
        model="gpt-4o",
        tenant_id=TENANT,
    )
    assert r.estado == "abstencion_traza_insuficiente"
    assert r.regimen is None


@pytest.mark.asyncio
async def test_kleene_caso3_sigue_ok_y_no_deriva_pese_a_los_no_evaluable() -> None:
    """Contrapunto del anterior: caso 3 (V ausente decide SUPERFICIAL) tiene
    que seguir resolviendo como `ok`, no como abstención, aunque el resto de
    las dimensiones venga `no_evaluable`."""
    salida = _raw_dict_tri(
        "ausente", "no_evaluable", "no_evaluable", "no_evaluable", "SUPERFICIAL"
    )
    r = await clasificar_regimen_llm(
        events=_EVENTS,
        enunciado="x",
        episode_id="e-caso3-ok",
        complete=_mock_complete(salida),
        model="gpt-4o",
        tenant_id=TENANT,
    )
    assert r.estado == "ok"
    assert r.regimen == "SUPERFICIAL"


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
async def test_fallback_proxy_y_needs_review_si_abstencion_traza_insuficiente(monkeypatch) -> None:
    """Caso 4 de punta a punta en el pipeline: la abstención NO toca
    `appropriation` (se conserva la etiqueta del proxy conductual) y SÍ marca
    `needs_review` con un motivo legible. Reusa el fallback existente
    (`_marcar_para_revision`) — no abre un camino nuevo (D1)."""
    from classifier_service.services.clients import AIGatewayClient

    monkeypatch.setattr(_settings, "eje_fino_llm_enabled", True)
    salida = _raw_dict_tri("no_evaluable", "presente", "presente", "presente", "REFLEXIVA")

    async def _fake_complete(self, **_kwargs):
        return SimpleNamespace(content=json.dumps(salida, ensure_ascii=False), output_tokens=50)

    monkeypatch.setattr(AIGatewayClient, "complete", _fake_complete)
    result = _FakeResult({"subgrupo": {"key": "colaborador_reflexivo"}})
    await _aplicar_juez_eje_fino(result, _EVENTS, uuid4(), {}, uuid4())

    assert result.features["regimen_llm"]["estado"] == "abstencion_traza_insuficiente"
    assert result.appropriation == "apropiacion_superficial"  # proxy conservado, no tocado
    assert result.features["needs_review"] is True
    assert "abstencion_traza_insuficiente" in result.features["needs_review_reason"]


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


# ── Contrato de salida del juez: RESPONSE_JSON_SCHEMA (B2a, D4 corregida) ──
from classifier_service.services.regimen_llm import RESPONSE_JSON_SCHEMA  # noqa: E402

_TRIVALUADO = {"presente", "ausente", "no_evaluable"}


def test_prompt_version_bumpeada_por_el_cambio_de_semantica_de_la_regla() -> None:
    """Task 3.7: la regla cambió de semántica (binaria → trivaluada con Kleene
    fuerte), y eso tiene que quedar versionado — es lo que hace recomputable
    el veredicto histórico (D1 del design.md, costo de revertir)."""
    from classifier_service.services.regimen_llm import PROMPT_VERSION

    assert PROMPT_VERSION != "eje_fino_v1.1.0"
    assert PROMPT_VERSION == "eje_fino_v1.2.0"


def test_system_prompt_define_no_evaluable_por_lo_que_falta_no_por_confianza() -> None:
    """Task 3.5: el prompt tiene que definir `no_evaluable` por AUSENCIA de
    traza citable, no por la confianza del modelo (para confianza ya está
    `confianza_min` — mezclar los dos criterios es el riesgo que el design.md
    señala en Risks/Trade-offs). Y ya no puede decir que `presente`/`oraculo`
    es "un booleano real": es falso desde que el contrato es trivaluado."""
    from classifier_service.services.regimen_llm import SYSTEM_PROMPT

    assert "no_evaluable" in SYSTEM_PROMPT
    assert "booleano real" not in SYSTEM_PROMPT
    assert "autonomia" in SYSTEM_PROMPT.lower() or "autonomía" in SYSTEM_PROMPT.lower()


def test_fewshot_emite_formato_trivaluado_no_booleano() -> None:
    """Task 3.6: si los few-shot siguen emitiendo booleanos, el modelo los
    imita y el tercer valor no aparece nunca en producción. Cada salida de
    ejemplo tiene que declarar `autonomia.presente` (no `autonomia.oraculo`)
    y parsear contra `RegimenLLMRaw` con los valores trivaluados nativos."""
    from classifier_service.services.regimen_llm import _FEWSHOT

    assert len(_FEWSHOT) > 0
    for _entrada, salida in _FEWSHOT:
        assert "presente" in salida["autonomia"], "el fewshot sigue en formato legado (oraculo)"
        assert "oraculo" not in salida["autonomia"]
        raw = RegimenLLMRaw.model_validate(salida)
        for dim in (raw.verbalizacion, raw.verificacion, raw.justificacion, raw.autonomia):
            assert dim.presente in ("presente", "ausente", "no_evaluable")


def test_schema_las_cuatro_dimensiones_son_enum_trivaluado() -> None:
    """D4 corregida: las CUATRO dimensiones (V, E, J, A) son trivaluadas en el
    contrato — no solo las tres que la versión anterior de D4 suponía.
    `autonomia` deja de tener la forma `{"oraculo": boolean}` y pasa a tener
    la MISMA forma que las otras tres: `{"presente": enum, "evidencia": str}`.
    """
    props = RESPONSE_JSON_SCHEMA["json_schema"]["schema"]["properties"]
    for dim in ("verbalizacion", "verificacion", "justificacion", "autonomia"):
        presente_schema = props[dim]["properties"]["presente"]
        assert presente_schema["type"] == "string"
        assert set(presente_schema["enum"]) == _TRIVALUADO
    assert "oraculo" not in props["autonomia"]["properties"]
