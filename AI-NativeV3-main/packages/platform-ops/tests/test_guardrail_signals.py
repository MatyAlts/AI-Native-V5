"""Tests golden del modulo guardrail_signals (R8 informeSoc.md).

Tests deterministicos sobre eventos sinteticos. Validan extraccion de
senales y aplicacion del modificador con sus 4 reglas. Usa un fake
dataclass `FakeClassification` para no acoplar con el ClassificationResult
real del classifier-service.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from platform_ops.guardrail_signals import (
    GUARDRAIL_MODIFIER_VERSION,
    SEVERITY_3_PLUS_COUNT_THRESHOLD,
    apply_guardrail_modifier,
    extract_guardrail_signals,
)


@dataclass
class FakeClassification:
    """Stand-in para ClassificationResult — mismo shape minimo."""

    appropriation: str
    reason: str = "razon original"
    ct_summary: float = 0.5
    ccd_mean: float = 0.5
    ccd_orphan_ratio: float = 0.2
    cii_stability: float = 0.5
    cii_evolution: float = 0.5
    features: dict[str, Any] = field(default_factory=dict)


def _adv_event(category: str, severity: int) -> dict[str, Any]:
    """Helper para construir un evento intento_adverso_detectado fake."""
    return {
        "event_type": "intento_adverso_detectado",
        "payload": {"category": category, "severity": severity},
    }


# ---------------------------------------------------------------------------
# extract_guardrail_signals
# ---------------------------------------------------------------------------


def test_sin_eventos_de_intento_adverso_devuelve_signals_vacios() -> None:
    events = [
        {"event_type": "prompt_enviado", "payload": {}},
        {"event_type": "tutor_respondio", "payload": {}},
    ]
    signals = extract_guardrail_signals(events)
    assert signals.total_attempts == 0
    assert signals.severity_3_plus_count == 0
    assert signals.categories_detected == frozenset()
    assert signals.overuse_confirmed is False


def test_un_evento_severo_se_cuenta_correctamente() -> None:
    events = [_adv_event("jailbreak_substitution", 4)]
    signals = extract_guardrail_signals(events)
    assert signals.total_attempts == 1
    assert signals.severity_3_plus_count == 1
    assert "jailbreak_substitution" in signals.categories_detected
    assert signals.overuse_confirmed is False


def test_overuse_se_marca_como_confirmed() -> None:
    events = [_adv_event("overuse", 1)]
    signals = extract_guardrail_signals(events)
    assert signals.total_attempts == 1
    assert signals.severity_3_plus_count == 0  # overuse es severidad 1
    assert signals.overuse_confirmed is True


def test_severidad_2_no_cuenta_para_3_plus() -> None:
    events = [
        _adv_event("jailbreak_fiction", 2),
        _adv_event("persuasion_urgency", 2),
    ]
    signals = extract_guardrail_signals(events)
    assert signals.total_attempts == 2
    assert signals.severity_3_plus_count == 0


def test_categorias_se_deduplica() -> None:
    events = [
        _adv_event("direct_answer", 3),
        _adv_event("direct_answer", 3),
        _adv_event("direct_answer", 3),
    ]
    signals = extract_guardrail_signals(events)
    assert signals.total_attempts == 3
    assert signals.severity_3_plus_count == 3
    assert signals.categories_detected == frozenset({"direct_answer"})


# ---------------------------------------------------------------------------
# apply_guardrail_modifier — Regla 1: combinacion severa
# ---------------------------------------------------------------------------


def test_regla_1_severidad_alta_mas_overuse_sobre_reflexiva_baja_a_delegacion() -> None:
    events = [
        _adv_event("direct_answer", 3),
        _adv_event("jailbreak_indirect", 3),
        _adv_event("direct_answer", 3),
        _adv_event("overuse", 1),
    ]
    signals = extract_guardrail_signals(events)
    classification = FakeClassification(appropriation="apropiacion_reflexiva")

    result = apply_guardrail_modifier(classification, signals)

    assert result.appropriation == "delegacion_pasiva"
    assert result.features["sub_branch"] == "guardrail_triggered_combined"
    assert result.features["modifier_applied"] == "rule_1_combined_severe"
    assert result.features["appropriation_before_modifier"] == "apropiacion_reflexiva"
    assert result.features["guardrail_modifier_version"] == GUARDRAIL_MODIFIER_VERSION
    # La classification original no se muto
    assert classification.appropriation == "apropiacion_reflexiva"


# ---------------------------------------------------------------------------
# apply_guardrail_modifier — Regla 2: 3+ severidad sin overuse
# ---------------------------------------------------------------------------


def test_regla_2_baja_reflexiva_a_superficial() -> None:
    events = [
        _adv_event("direct_answer", 3),
        _adv_event("jailbreak_indirect", 3),
        _adv_event("direct_answer", 3),
    ]
    signals = extract_guardrail_signals(events)
    classification = FakeClassification(appropriation="apropiacion_reflexiva")

    result = apply_guardrail_modifier(classification, signals)

    assert result.appropriation == "apropiacion_superficial"
    assert result.features["modifier_applied"] == "rule_2_three_plus_severity_3"
    assert result.features["appropriation_before_modifier"] == "apropiacion_reflexiva"


def test_regla_2_baja_superficial_a_delegacion_con_sub_branch() -> None:
    events = [
        _adv_event("direct_answer", 3),
        _adv_event("jailbreak_substitution", 4),
        _adv_event("direct_answer", 3),
    ]
    signals = extract_guardrail_signals(events)
    classification = FakeClassification(appropriation="apropiacion_superficial")

    result = apply_guardrail_modifier(classification, signals)

    assert result.appropriation == "delegacion_pasiva"
    assert result.features["sub_branch"] == "guardrail_triggered"
    assert result.features["modifier_applied"] == "rule_2_three_plus_severity_3"


def test_regla_2_sobre_delegacion_no_baja_mas() -> None:
    """delegacion_pasiva ya es piso — la regla no la modifica."""
    events = [
        _adv_event("direct_answer", 3),
        _adv_event("jailbreak_indirect", 3),
        _adv_event("direct_answer", 3),
    ]
    signals = extract_guardrail_signals(events)
    classification = FakeClassification(appropriation="delegacion_pasiva")

    result = apply_guardrail_modifier(classification, signals)

    assert result.appropriation == "delegacion_pasiva"
    # No se aplica modificador con resultado distinto pero igual queda metadata
    # NO — Regla 2 solo aplica si _LOWER_LEVEL.get devuelve algo. Para
    # delegacion_pasiva no hay nivel inferior, asi que la regla no se aplica.
    # Pero podria aplicar regla 4 si tambien hay overuse. En este test no hay
    # overuse, asi que ninguna regla aplica.
    assert "modifier_applied" not in result.features


# ---------------------------------------------------------------------------
# apply_guardrail_modifier — Regla 3: severidad baja
# ---------------------------------------------------------------------------


def test_regla_3_un_evento_severo_marca_warning_pero_no_modifica_appropriation() -> None:
    events = [_adv_event("direct_answer", 3)]
    signals = extract_guardrail_signals(events)
    classification = FakeClassification(appropriation="apropiacion_reflexiva")

    result = apply_guardrail_modifier(classification, signals)

    assert result.appropriation == "apropiacion_reflexiva"
    assert result.features["guardrail_warning_low_count"] is True
    assert result.features["modifier_applied"] == "rule_3_low_count_warning"
    # No hay appropriation_before_modifier porque no cambio
    assert "appropriation_before_modifier" not in result.features


def test_regla_3_dos_eventos_severos_marcan_warning() -> None:
    events = [_adv_event("direct_answer", 3), _adv_event("jailbreak_indirect", 3)]
    signals = extract_guardrail_signals(events)
    classification = FakeClassification(appropriation="apropiacion_superficial")

    result = apply_guardrail_modifier(classification, signals)

    assert result.appropriation == "apropiacion_superficial"
    assert result.features["guardrail_warning_low_count"] is True


# ---------------------------------------------------------------------------
# apply_guardrail_modifier — Regla 4: solo overuse
# ---------------------------------------------------------------------------


def test_regla_4_solo_overuse_marca_flag_sin_modificar_appropriation() -> None:
    events = [_adv_event("overuse", 1)]
    signals = extract_guardrail_signals(events)
    classification = FakeClassification(appropriation="apropiacion_reflexiva")

    result = apply_guardrail_modifier(classification, signals)

    assert result.appropriation == "apropiacion_reflexiva"
    assert result.features["overuse_detected"] is True
    assert result.features["modifier_applied"] == "rule_4_overuse_only"


# ---------------------------------------------------------------------------
# Sin senales: classification queda intacta
# ---------------------------------------------------------------------------


def test_sin_eventos_no_modifica_classification() -> None:
    events: list[dict[str, Any]] = []
    signals = extract_guardrail_signals(events)
    classification = FakeClassification(appropriation="apropiacion_superficial")

    result = apply_guardrail_modifier(classification, signals)

    assert result.appropriation == "apropiacion_superficial"
    assert result.features == {}
    # Ni siquiera metadata — la regla 4 no aplica porque no hay overuse.


# ---------------------------------------------------------------------------
# Determinismo
# ---------------------------------------------------------------------------


def test_dos_llamadas_idempotentes() -> None:
    events = [_adv_event("direct_answer", 3), _adv_event("direct_answer", 3), _adv_event("direct_answer", 3)]
    signals = extract_guardrail_signals(events)
    classification = FakeClassification(appropriation="apropiacion_reflexiva")

    r1 = apply_guardrail_modifier(classification, signals)
    r2 = apply_guardrail_modifier(classification, signals)
    assert r1 == r2


# ---------------------------------------------------------------------------
# Constantes (anti-regresion)
# ---------------------------------------------------------------------------


def test_umbral_severidad_3_plus_se_mantiene_en_3() -> None:
    assert SEVERITY_3_PLUS_COUNT_THRESHOLD == 3
    assert GUARDRAIL_MODIFIER_VERSION == "1.0.0"
