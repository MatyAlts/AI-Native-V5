"""Override lexico de `anotacion_creada` (Mejora 3 / ADR-045, esqueleto OFF).

Detecta patrones lexicos en el contenido textual de la anotacion para asignar
N1 (lectura inicial / comprension) o N4 (apropiacion post-tutor) sobre el
mismo evento `anotacion_creada` que actualmente se etiqueta por posicion
temporal en `event_labeler.py` v1.1.0.

ESTADO: la activacion en runtime esta bloqueada por la feature flag
`lexical_anotacion_override_enabled = False` en `classifier_service/config.py`.
Mientras este OFF, este modulo NO se invoca desde `label_event()` y el
labeler sigue produciendo exactamente las mismas etiquetas que la heuristica
temporal v1.1.0 (ADR-023). Esto preserva la garantia de reproducibilidad
bit-a-bit del classifier_config_hash sobre todas las classifications historicas
del piloto-1.

ADR-045 (2026-05-09) formaliza el cierre parcial de la sub-mejora G8b del
plan post-piloto-1: el esqueleto tecnico (corpus lexico, hash determinista,
funcion pura, tests) queda implementado y listo. La activacion real depende
de validacion intercoder kappa >= 0.70 (alineacion con paper Cortez & Garis,
ppcona.docx Sec 7; ADR-046 supersede parcial sobre ADRs 027/044) sobre el
protocolo dual: 200 eventos estratificados 50 por nivel N1-N4 (Protocolo A,
validacion del etiquetador) + 50 episodios para categorias de apropiacion
(Protocolo B, validacion del arbol de decision). Etiquetadores: 2 docentes
independientes. Mismo gate humano cross-ADR.

G8c (clasificacion semantica via embeddings, ADR-023 Eje B post-defensa) NO
es atacable con el patron esqueleto-OFF — requiere endpoint nuevo en el
ai-gateway y decisiones arquitectonicas. Queda fuera de scope de ADR-045.

Reproducibilidad bit-a-bit: el modulo expone `LEXICAL_CORPUS_HASH` con la
misma formula canonica que `guardrails_corpus_hash` (ADR-043),
`socratic_corpus_hash` (ADR-044) y `classifier_config_hash` (ADR-009).
Bumpear `LEXICAL_CORPUS_VERSION` o cualquier patron regex cambia el hash.

Cuando el flag se prenda eventualmente, el `LABELER_VERSION` global del
labeler debe bumpearse a "2.0.0" (cambio semantico mayor: contenido textual
con precedencia sobre posicion temporal). Esto re-etiqueta classifications
historicas via recompute pero NO toca el CTR (ADR-020 — labeler es derivado
en lectura).

Limitaciones del corpus provisorio (a validar con docentes pre-activacion):
- Patrones N1: "estoy leyendo", "el enunciado pide", "no entiendo todavia",
  "me piden", "tengo que" + contexto de comprension inicial.
- Patrones N4: "ahora entiendo", "ahora veo", "tras la respuesta", "siguiendo
  el consejo", "el tutor me dijo" + contexto de apropiacion reflexiva.
- Falsos positivos posibles: una anotacion con la frase "ahora entiendo"
  puede ocurrir intra-codigo sin haber recibido respuesta del tutor reciente.
  La validacion intercoder mediria precision/recall reales.
- NO se computa N2 explicito: es el fallback de `label_event` cuando ni este
  modulo ni el override temporal asignan N1/N4.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Literal

LEXICAL_CORPUS_VERSION = "1.0.0"

LexicalLabel = Literal["N1", "N4"]


# Patrones provisorios — sujetos a validacion intercoder kappa pre-activacion.
# La forma `(regex_string, pattern_id)` matchea el mismo registro que
# `guardrails.py::_PATTERNS` y `postprocess_socratic.py::_PATTERNS`.
#
# Precedencia: N4 gana sobre N1 si ambos matchean el mismo contenido.
# Justificacion: la senal "apropiacion tras respuesta" es mas informativa
# pedagogicamente que "lectura inicial" — mismo criterio que el override
# temporal v1.1.0 cuando ambas ventanas matcheaban.
_PATTERNS: dict[LexicalLabel, list[tuple[str, str]]] = {
    "N1": [
        # "estoy leyendo (el enunciado/la consigna/el problema)"
        (
            r"(?i)\bestoy\s+leyendo\b",
            "n1_estoy_leyendo_v1_0_0",
        ),
        # "el enunciado pide/dice/menciona" / "la consigna pide/dice"
        (
            r"(?i)\b(el\s+enunciado|la\s+consigna)\s+(pide|dice|menciona|exige|requiere)\b",
            "n1_enunciado_pide_v1_0_0",
        ),
        # "no entiendo todavia" / "todavia no entiendo" / "todavia no me queda claro"
        (
            r"(?i)\b(no\s+entiendo\s+todav(i|í)a|todav(i|í)a\s+no\s+(entiendo|me\s+queda\s+claro))\b",
            "n1_no_entiendo_todavia_v1_0_0",
        ),
        # "me piden (que)" / "tengo que (entender|leer)"
        (
            r"(?i)\b(me\s+piden(\s+que)?|tengo\s+que\s+(entender|leer|comprender|interpretar))\b",
            "n1_me_piden_v1_0_0",
        ),
    ],
    "N4": [
        # "ahora (entiendo|veo|me doy cuenta|comprendo)"
        (
            r"(?i)\bahora\s+(entiendo|veo|me\s+doy\s+cuenta|comprendo|capt(o|é))\b",
            "n4_ahora_entiendo_v1_0_0",
        ),
        # "tras la respuesta" / "despues de la respuesta" / "con la respuesta del tutor"
        (
            r"(?i)\b(tras|despu(e|é)s\s+de|con)\s+la\s+respuesta\b",
            "n4_tras_la_respuesta_v1_0_0",
        ),
        # "siguiendo (el consejo|la pista|la sugerencia) del tutor"
        (
            r"(?i)\bsiguiendo\s+(el\s+consejo|la\s+pista|la\s+sugerencia|lo\s+que)\b",
            "n4_siguiendo_consejo_v1_0_0",
        ),
        # "el tutor (me dijo|sugiri(o|ó)|propuso|explic(o|ó))"
        (
            r"(?i)\bel\s+tutor\s+(me\s+dijo|sugiri(o|ó)|propuso|explic(o|ó)|me\s+ayud(o|ó))\b",
            "n4_el_tutor_v1_0_0",
        ),
    ],
}


def _compile_patterns(
    patterns: dict[LexicalLabel, list[tuple[str, str]]],
) -> dict[LexicalLabel, list[tuple[str, re.Pattern[str]]]]:
    return {
        label: [(pid, re.compile(pattern)) for pattern, pid in items]
        for label, items in patterns.items()
    }


_COMPILED = _compile_patterns(_PATTERNS)


def compute_lexical_corpus_hash() -> str:
    """SHA-256 determinista del corpus + version.

    Misma formula canonica que `guardrails_corpus_hash` y
    `socratic_corpus_hash`: sort_keys=True, ensure_ascii=False,
    separators=(",", ":"), encoding UTF-8.

    Bumpear LEXICAL_CORPUS_VERSION o cualquier patron regex cambia el hash.
    Cuando el flag se prenda eventualmente, las classifications computadas
    con este corpus llevaran este hash en su payload extendido (esquema a
    definir post-validacion intercoder).
    """
    canonical = json.dumps(
        {
            "corpus_version": LEXICAL_CORPUS_VERSION,
            "patterns": _PATTERNS,
        },
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


LEXICAL_CORPUS_HASH = compute_lexical_corpus_hash()


def lexical_label(content: str) -> LexicalLabel | None:
    """Devuelve N1 o N4 si el contenido matchea el corpus; None si no determina.

    Funcion pura, idempotente, sin side-effects, determinista bit-a-bit.

    Mientras `lexical_anotacion_override_enabled=False` en el config del
    classifier-service, esta funcion NO se invoca desde `label_event()`. La
    funcion esta disponible para tests deterministas, scripts de calibracion
    intercoder con docentes, y para el dia que el flag se prenda.

    Precedencia: si el contenido matchea ambos N4 y N1, gana N4 (mismo
    criterio que el override temporal v1.1.0 — apropiacion post-tutor es
    mas informativa que lectura inicial).
    """
    if not content:
        return None

    # N4 primero por precedencia
    for _pid, regex in _COMPILED["N4"]:
        if regex.search(content):
            return "N4"

    for _pid, regex in _COMPILED["N1"]:
        if regex.search(content):
            return "N1"

    return None
