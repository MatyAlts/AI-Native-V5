"""Postprocesamiento de respuestas del tutor (Mejora 4 / ADR-044, esqueleto OFF).

Detecta patrones de incumplimiento del modo socrático sobre la respuesta del
LLM (NO sobre el prompt — ese trabajo lo hace `guardrails.py` / Fase A).
Devuelve un score `socratic_compliance` en [0, 1] y una lista de violations.

ESTADO: la activación en runtime está bloqueada por la feature flag
`socratic_compliance_enabled = False` en `config.py`. Mientras esté OFF,
el campo `TutorRespondioPayload.socratic_compliance` sigue persistiendo
`None` y `violations` queda como lista vacía, preservando la garantía del
ADR-027: el campo queda `None` hasta que la calibración con docentes valide
el cálculo (κ ≥ 0.6 sobre 50+ respuestas etiquetadas por 2 docentes).

ADR-044 (2026-05-09) formaliza el cierre parcial de la Mejora 4 del plan
post-piloto-1: el esqueleto técnico (detector, score, hooks, persistencia,
tests, hash determinista) queda implementado y listo. La activación real
depende de la validación intercoder.

Reproducibilidad bit-a-bit: el módulo expone `SOCRATIC_CORPUS_HASH` con la
misma fórmula canónica que `guardrails_corpus_hash` (ADR-043) y
`classifier_config_hash` (ADR-009): `sort_keys=True`, `ensure_ascii=False`,
`separators=(",", ":")`, encoding UTF-8. Bumpear `SOCRATIC_CORPUS_VERSION`,
cualquier patrón regex, peso del score o severidad cambia el hash.

Limitaciones del cálculo provisorio (a validar con docentes pre-activación):

- Penalización por bloque de código completo: heurística, no semántica. Una
  respuesta legítima del tutor podría incluir un snippet ilustrativo corto.
  Por eso el threshold es bloque grande (>200 chars), no cualquier ```.
- Penalización por ausencia de pregunta: detecta ausencia literal de "?" o
  "¿". No distingue preguntas implícitas ni preguntas embebidas.
- Penalización por respuesta directa: matchea imperativos típicos
  ("la solución es", "tenés que", "el código es"). False positives posibles
  cuando el tutor explica un concepto general.
- NO se computa "off-topic": requiere semantic similarity contra el prompt y
  los chunks RAG. Agenda Eje C post-defensa.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Literal

SOCRATIC_CORPUS_VERSION = "1.0.0"

ViolationCategory = Literal[
    "code_block_complete",
    "no_question_in_response",
    "direct_answer",
]


@dataclass(frozen=True)
class Violation:
    """Una violación al modo socrático detectada en la respuesta del tutor."""

    pattern_id: str
    category: ViolationCategory
    severity: int
    excerpt: str


# Patrones provisorios — sujetos a validación intercoder κ pre-activación.
# La forma `(regex_string, pattern_id)` matchea el mismo registro que
# `guardrails.py::_PATTERNS`.
_PATTERNS: dict[ViolationCategory, list[tuple[str, str]]] = {
    "code_block_complete": [
        # Fenced code block (``` ... ```) con cuerpo grande (>200 chars).
        # Una ilustración corta del tutor (1-3 líneas) NO matchea; un bloque
        # de resolución completa sí. Threshold provisorio.
        (r"```[\s\S]{200,}?```", "fenced_block_large_v1_0_0"),
    ],
    "direct_answer": [
        # Imperativos típicos de respuesta directa, no socrática.
        (
            r"(?i)\b(la\s+soluci(o|ó)n\s+es|el\s+c(o|ó)digo\s+es|"
            r"ten(e|é)s\s+que|deb(e|é)s\s+(hacer|escribir|usar)|"
            r"simplemente\s+(hac(e|é)|escrib(i|í)|us(a|á)))\b",
            "direct_answer_imperative_v1_0_0",
        ),
    ],
    # `no_question_in_response` se detecta como ausencia de "?" o "¿" — no
    # es una regex sino una condición negativa. Se computa aparte en
    # `postprocess()` para mantener la simetría del corpus en el hash.
    "no_question_in_response": [],
}


# Pesos por categoría. La penalización es:
#   penalty = sum(weight_i) sobre categorías presentes (sin contar duplicados
#   intra-categoría). Score:
#   socratic_compliance = max(0.0, min(1.0, 1.0 - penalty))
# Los tres pesos suman 1.0 para que las tres violaciones simultáneas saturen
# el score a 0. La severity se reporta como metadata en cada Violation (cuán
# seria es la violación per se) pero NO escalea el cálculo del score —
# desacoplado por simplicidad y para que el corpus_hash sea robusto a cambios
# de severity sin rebalancear pesos.
_WEIGHTS: dict[ViolationCategory, float] = {
    "code_block_complete": 0.4,
    "no_question_in_response": 0.3,
    "direct_answer": 0.3,
}

_SEVERITY: dict[ViolationCategory, int] = {
    "code_block_complete": 3,
    "no_question_in_response": 2,
    "direct_answer": 3,
}


def _compile_patterns(
    patterns: dict[ViolationCategory, list[tuple[str, str]]],
) -> dict[ViolationCategory, list[tuple[str, re.Pattern[str]]]]:
    compiled: dict[ViolationCategory, list[tuple[str, re.Pattern[str]]]] = {}
    for cat, items in patterns.items():
        compiled[cat] = [
            (pid, re.compile(pattern, re.IGNORECASE | re.MULTILINE))
            for pattern, pid in items
        ]
    return compiled


_COMPILED = _compile_patterns(_PATTERNS)


def compute_socratic_corpus_hash() -> str:
    """SHA-256 determinista del corpus + pesos + severidades + versión.

    Misma fórmula canónica que `guardrails_corpus_hash` y
    `classifier_config_hash`. Bumpear cualquier valor incluido en el JSON
    canónico cambia el hash, y eventos `tutor_respondio` futuros (cuando el
    flag se prenda) quedarán etiquetados con el hash nuevo. Eventos viejos
    preservan el hash con el que fueron computados.
    """
    canonical = json.dumps(
        {
            "corpus_version": SOCRATIC_CORPUS_VERSION,
            "patterns": _PATTERNS,
            "weights": _WEIGHTS,
            "severity": _SEVERITY,
        },
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


SOCRATIC_CORPUS_HASH = compute_socratic_corpus_hash()


_MAX_EXCERPT = 150


@dataclass(frozen=True)
class PostprocessResult:
    """Resultado de aplicar el postprocesador a una respuesta del tutor."""

    socratic_compliance: float
    violations: list[Violation]
    corpus_hash: str


def postprocess(response_content: str) -> PostprocessResult:
    """Analiza la respuesta del tutor y devuelve compliance + violations.

    Función pura, idempotente, sin side-effects, determinista bit-a-bit.

    Mientras `socratic_compliance_enabled=False` en el config, esta función
    NO se invoca desde runtime — el campo `socratic_compliance` del payload
    queda `None` y `violations` lista vacía. La función está disponible para
    tests deterministas, scripts de calibración intercoder con docentes, y
    para el día que el flag se prenda.
    """
    if not response_content:
        return PostprocessResult(
            socratic_compliance=0.5,
            violations=[],
            corpus_hash=SOCRATIC_CORPUS_HASH,
        )

    violations: list[Violation] = []

    for category, items in _COMPILED.items():
        severity = _SEVERITY[category]
        for pattern_id, regex in items:
            m = regex.search(response_content)
            if m is None:
                continue
            excerpt = m.group(0)
            if len(excerpt) > _MAX_EXCERPT:
                excerpt = excerpt[:_MAX_EXCERPT] + "..."
            violations.append(
                Violation(
                    pattern_id=pattern_id,
                    category=category,
                    severity=severity,
                    excerpt=excerpt,
                )
            )

    if "?" not in response_content and "¿" not in response_content:
        violations.append(
            Violation(
                pattern_id="no_question_marker_v1_0_0",
                category="no_question_in_response",
                severity=_SEVERITY["no_question_in_response"],
                excerpt="(respuesta sin signo de interrogación)",
            )
        )

    penalty = 0.0
    seen_categories: set[ViolationCategory] = set()
    for v in violations:
        if v.category in seen_categories:
            continue
        seen_categories.add(v.category)
        penalty += _WEIGHTS[v.category]

    score = max(0.0, min(1.0, 1.0 - penalty))

    return PostprocessResult(
        socratic_compliance=score,
        violations=violations,
        corpus_hash=SOCRATIC_CORPUS_HASH,
    )
