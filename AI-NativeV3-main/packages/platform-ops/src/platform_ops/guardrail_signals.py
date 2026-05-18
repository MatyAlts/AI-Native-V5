"""Senales de guardrail para modificar clasificacion (R8 informeSoc.md).

Funciones puras sobre eventos del CTR:
  - `extract_guardrail_signals(events)` — agrega los eventos `intento_adverso_detectado`
    en un resumen estructurado (total, severidad >= 3, categorias, overuse).
  - `apply_guardrail_modifier(classification, signals)` — modifica una
    ClassificationResult segun las 4 reglas iniciales del design doc.

BLOQUEO CRITICO (design doc seccion 1):
  Este modulo NO debe conectarse al `pipeline.py` real hasta que:
    1. A1 (re-clasificacion de las 106 historicas) este ejecutado.
    2. Intercoder Protocolo B (ADR-046) tenga kappa >= 0.70 sobre el arbol
       de 3 categorias actual.
    3. Validacion empirica sobre las 106 historicas mida si el modificador
       cambia clasificaciones de manera consistente con criterio docente.

Por lo tanto: este modulo existe como utilidad. El flag
`settings.guardrail_modifier_enabled` en classifier-service esta OFF por
default. Cuando se prenda, el comportamiento del pipeline cambia — eso
requiere ADR-052 + bump de `classifier_config_hash` coordinado.

Funciones puras, deterministicas, sin side-effects. Tests golden en
`tests/test_guardrail_signals.py`.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

GUARDRAIL_MODIFIER_VERSION = "1.0.0"

# Umbrales de las reglas iniciales (operacionalizacion inicial — calibrar
# empiricamente sobre las 106 historicas post-A1 con criterio docente).
SEVERITY_3_PLUS_COUNT_THRESHOLD = 3  # disparador de Regla 1


@dataclass(frozen=True)
class GuardrailSignals:
    """Resumen de senales de guardrail por episodio."""

    total_attempts: int  # cantidad total de intento_adverso_detectado
    severity_3_plus_count: int  # cantidad con severity >= 3
    categories_detected: frozenset[str]  # ej. {"jailbreak_substitution"}
    overuse_confirmed: bool  # cualquier intento con category="overuse"
    extraction_version: str = "guardrail_signals/v1.0.0"


def extract_guardrail_signals(events: list[dict[str, Any]]) -> GuardrailSignals:
    """Resume las senales de guardrail de la cadena de eventos.

    Args:
        events: lista de dicts de eventos del episodio. Solo los de tipo
            `intento_adverso_detectado` se consideran. El payload esperado
            tiene al menos:
                - `category`: str (ej. "jailbreak_substitution", "overuse")
                - `severity`: int (1-5)

    Returns:
        GuardrailSignals con totales agregados. Si no hay eventos de
        intento adverso, devuelve totales 0 y categorias vacias.
    """
    total = 0
    severity_3_plus = 0
    categories: set[str] = set()
    overuse_seen = False

    for e in events:
        if e.get("event_type") != "intento_adverso_detectado":
            continue
        payload = e.get("payload") or {}
        category = payload.get("category")
        severity = payload.get("severity")

        total += 1
        if isinstance(category, str):
            categories.add(category)
            if category == "overuse":
                overuse_seen = True
        if isinstance(severity, int) and severity >= 3:
            severity_3_plus += 1

    return GuardrailSignals(
        total_attempts=total,
        severity_3_plus_count=severity_3_plus,
        categories_detected=frozenset(categories),
        overuse_confirmed=overuse_seen,
    )


# Mapa de "bajar un nivel" para la Regla 1.
_LOWER_LEVEL: dict[str, str] = {
    "apropiacion_reflexiva": "apropiacion_superficial",
    "apropiacion_superficial": "delegacion_pasiva",
    # delegacion_pasiva ya es el piso — no se baja mas.
}


def apply_guardrail_modifier(
    classification: Any,  # tipado loose para no acoplar al import del classifier
    signals: GuardrailSignals,
) -> Any:
    """Aplica las reglas del modificador y devuelve una classification MODIFICADA.

    Args:
        classification: objeto con atributos `appropriation: str`,
            `reason: str`, `features: dict`. Tipicamente `ClassificationResult`
            del classifier-service. El tipado loose permite testear sin
            importar el classifier (que tiene dependencias de SQLAlchemy).
        signals: resultado de `extract_guardrail_signals`.

    Returns:
        Si las reglas no aplican, devuelve la classification original sin
        modificar. Si las reglas aplican, devuelve una copia modificada via
        `dataclasses.replace` con campos `appropriation`, `reason`,
        `features` actualizados.

        Campos agregados a `features` cuando hay modificacion:
            - `guardrail_signals`: dict serializado
            - `guardrail_modifier_version`: version
            - `modifier_applied`: codigo de la regla aplicada
            - `appropriation_before_modifier`: el valor original

    Reglas (en orden, primera que aplique gana):
      1. severity_3_plus_count >= 3 Y overuse_confirmed Y appropriation =
         "apropiacion_reflexiva" => bajar a "delegacion_pasiva"
         (sub_branch="guardrail_triggered_combined")
      2. severity_3_plus_count >= 3 => bajar un nivel (reflexiva -> superficial
         o superficial -> delegacion_pasiva)
      3. 1 <= severity_3_plus_count <= 2 => no modifica appropriation,
         marca `features.guardrail_warning_low_count = True`
      4. overuse_confirmed sin otras condiciones => marca
         `features.overuse_detected = True`

    Funcion pura — no muta la classification de entrada, devuelve nueva.
    """
    original_appropriation = classification.appropriation
    new_features = dict(classification.features) if classification.features else {}
    new_appropriation = original_appropriation
    new_reason = classification.reason
    modifier_applied: str | None = None

    # Regla 1: combinacion severa
    if (
        signals.severity_3_plus_count >= SEVERITY_3_PLUS_COUNT_THRESHOLD
        and signals.overuse_confirmed
        and original_appropriation == "apropiacion_reflexiva"
    ):
        new_appropriation = "delegacion_pasiva"
        new_features["sub_branch"] = "guardrail_triggered_combined"
        new_reason = (
            f"{classification.reason} Modificador (regla 1): "
            f"{signals.severity_3_plus_count} intentos severos + overuse "
            f"sobre apropiacion_reflexiva."
        )
        modifier_applied = "rule_1_combined_severe"

    # Regla 2: severidad alta sin overuse
    elif signals.severity_3_plus_count >= SEVERITY_3_PLUS_COUNT_THRESHOLD:
        lowered = _LOWER_LEVEL.get(original_appropriation)
        if lowered:
            new_appropriation = lowered
            new_reason = (
                f"{classification.reason} Modificador (regla 2): "
                f"{signals.severity_3_plus_count} intentos adversos severos."
            )
            if lowered == "delegacion_pasiva":
                new_features["sub_branch"] = "guardrail_triggered"
            modifier_applied = "rule_2_three_plus_severity_3"

    # Regla 3: severidad baja-media (1-2 incidentes severos)
    elif 1 <= signals.severity_3_plus_count <= 2:
        new_features["guardrail_warning_low_count"] = True
        modifier_applied = "rule_3_low_count_warning"

    # Regla 4: solo overuse
    elif signals.overuse_confirmed:
        new_features["overuse_detected"] = True
        modifier_applied = "rule_4_overuse_only"

    # Si alguna regla aplico, persistir metadata
    if modifier_applied is not None:
        new_features["guardrail_signals"] = {
            "total_attempts": signals.total_attempts,
            "severity_3_plus_count": signals.severity_3_plus_count,
            "categories_detected": sorted(signals.categories_detected),
            "overuse_confirmed": signals.overuse_confirmed,
            "extraction_version": signals.extraction_version,
        }
        new_features["guardrail_modifier_version"] = GUARDRAIL_MODIFIER_VERSION
        new_features["modifier_applied"] = modifier_applied
        if new_appropriation != original_appropriation:
            new_features["appropriation_before_modifier"] = original_appropriation

    # Devolver copia modificada via dataclasses.replace (compat con cualquier
    # @dataclass). El caller asume que classification es @dataclass.
    return replace(
        classification,
        appropriation=new_appropriation,
        reason=new_reason,
        features=new_features,
    )
