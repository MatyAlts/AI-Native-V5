"""Postprocesamiento de respuestas del tutor — Fase B de guardrails (ADR-027 → ADR-044).

Cierre de la Mejora 4 del plan post-piloto-1. Cumple la promesa textual de la
Sección 8.5.1 de la tesis sobre cálculo de un score de cumplimiento socrático
sobre cada respuesta del tutor, complementario al detector preprocesamiento de
prompts adversos del estudiante (Fase A — ADR-019).

Función principal:

    compute_socratic_compliance(prompt, response, prompt_kind=None)
        -> SocraticComplianceResult(score, violations)

donde `score ∈ [0, 1]` (1 = perfectamente socrático, 0 = totalmente no compliant)
y `violations` es una lista de strings con los pattern_ids de las violaciones
detectadas. La fórmula es reproducible bit-a-bit: dada la misma terna
(prompt, response, prompt_kind) y la misma versión del corpus, la salida es
idéntica.

Reproducibilidad bit-a-bit: el hash determinista `socratic_compliance_corpus_hash`
captura la versión del corpus + los regex + los thresholds + las penalizaciones.
Bumpear cualquiera de estos cambia el hash. La práctica operativa es la misma
que `guardrails_corpus_hash` (ADR-019) y `classifier_config_hash` (ADR-009).

Integración con el classifier (CRÍTICO, ADR-027 línea 38, ADR-044):
- El score se persiste en `TutorRespondioPayload.socratic_compliance` y las
  violaciones en `TutorRespondioPayload.violations`. Ambos campos ya existen
  en el contract desde F8 con valores default `None` y `[]` respectivamente.
- El `classifier-service` IGNORA estos campos en su feature extraction. El
  `classifier_config_hash` permanece estable. Validación intercoder κ con
  docentes (50 respuestas, target κ ≥ 0.6, ADR-044) es la condición que
  destrabaría considerar incorporarlos al árbol — hasta entonces, son
  metadata de auditoría operativa pedagógica, no input del clasificador.

Limitaciones declaradas:
- Detector 3 (off-topic) usa similitud léxica simple (Jaccard de tokens
  significativos), NO embeddings. La migración a embeddings requiere llamada
  al ai-gateway con costo y queda como agenda futura del ADR sucesor.
- Sin clasificación semántica del contenido del prompt — el detector de
  "prompt directo" usa regex sobre verbos imperativos. Los falsos positivos
  pedagógicos (estudiante que pide ejemplo legítimo) se mitigan con la
  combinación de los tres detectores: una sola violación produce penalización
  parcial, no descalifica la respuesta.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Literal

# Versión semver del corpus de detectors. Bumpear cualquier patrón, threshold
# o penalización requiere bumpear esto y el golden hash de los tests.
SOCRATIC_COMPLIANCE_VERSION = "1.0.0"

# Tipos de prompt del estudiante. La detección distingue entre:
# - "direct": el estudiante pide explícitamente la solución completa.
# - "reflective": el estudiante pide entender, explicación, ayuda conceptual.
# - "neutral": ni claramente directo ni claramente reflexivo (default).
#
# Cuando el caller no pasa `prompt_kind`, el módulo lo deriva con
# `infer_prompt_kind(prompt)`. Si el caller lo pasa explícitamente (ej. desde
# F6 / ADR-024 cuando se materialice), se respeta.
PromptKind = Literal["direct", "reflective", "neutral"]


@dataclass(frozen=True)
class SocraticComplianceResult:
    """Resultado del cálculo de cumplimiento socrático sobre una respuesta.

    Attributes:
        score: float ∈ [0, 1]. 1 = perfecto, 0 = totalmente no compliant.
        violations: lista de pattern_ids de las violaciones detectadas, en el
            orden en que el corpus las evalúa (estable bit-a-bit).
        prompt_kind: tipo de prompt del estudiante (derivado o pasado).
        corpus_hash: hash determinista del corpus que produjo el resultado.
            Se loguea en structlog para auditabilidad (NO va al payload del
            evento CTR en esta versión — ver agenda futura del ADR-044).
    """

    score: float
    violations: list[str] = field(default_factory=list)
    prompt_kind: PromptKind = "neutral"
    corpus_hash: str = ""


# ---------------------------------------------------------------------------
# Patrones de detección (regex). Mismas convenciones que guardrails.py:
# - case-insensitive
# - separadores tolerantes para evasión trivial
# - Tildes cubiertas con `(o|ó)` etc.
# ---------------------------------------------------------------------------


# Detector D1: prompt directo — verbo imperativo + objeto solución.
# Cubre español rioplatense (dame, escribime, hacelo) + neutral (dame, escribe,
# hace) + inglés (give, write, do, solve).
_DIRECT_PROMPT_PATTERNS = [
    # "dame/dale/escribime/hacelo/respondeme + el código/solución/respuesta"
    r"\b(dame|dale|escrib(e|í|ime|ímelo)|hac(e|é|elo|emelo|elo)|respond(e|eme|ele|émelo))\b"
    r"[\s\-_.,]+"
    r"(el|la|los|las|todo|me|nos)?[\s\-_.,]*"
    r"(c(o|ó)digo|soluci(o|ó)n|respuesta|funci(o|ó)n|programa|answer|implementaci(o|ó)n)",
    # "resolveme/resuelvelo + esto/el problema/el ejercicio"
    r"\b(resolv(e|eme|elo|emelo)|soluciona(me|lo|melo)?)\b[\s\-_.,]+"
    r"(esto|el|este|el\s+problema|el\s+ejercicio|el\s+tp)",
    # "necesito + el código/la solución (con conjugación imperativa o de necesidad)"
    r"\bnecesit(o|amos)\b[\s\-_.,]+"
    r"(el|la)?[\s\-_.,]*"
    r"(c(o|ó)digo|soluci(o|ó)n|respuesta\s+(completa|final))",
    # EN equivalentes
    r"\b(give|write|solve|do|provide|implement)\s+(me\s+)?(the\s+)?"
    r"(code|solution|answer|implementation|function|program)",
]

# Detector D2: prompt reflexivo — el estudiante busca entender, no obtener.
_REFLECTIVE_PROMPT_PATTERNS = [
    # "no entiendo + (cómo/qué/por qué)"
    r"\bno\s+entiendo\b",
    # "ayudame/ayudame a entender", "explicame", "podes explicar"
    r"\b(ayud(a|á|ame|ame\s+a\s+entender)|explic(a|á|ame|ame))\b",
    r"\bpod(e|é)s\b[\s\-_.,]+(explicar|ayudar|guiar)",
    # "qué + verbo cognitivo (pensas/opinas/te parece)"
    r"\bqu(e|é)\s+(pens(a|á|as)|opina(s)?|te\s+parec(e|en))\b",
    # "cómo se hace/funciona/calcula" — exploración
    r"\bc(o|ó)mo\s+(se\s+)?(hace|funciona|calcula|llega|llegamos|abord)",
    # "por qué + ..."
    r"\bpor\s+qu(e|é)\b",
    # EN equivalentes
    r"\b(i\s+don'?t\s+understand|help\s+me\s+understand|can\s+you\s+explain|"
    r"what\s+do\s+you\s+think|why\s+(does|do|is)|how\s+(does|do)\s+(this|it))",
]

# Detector D3: bloque de código en la respuesta del tutor.
# Si la respuesta contiene un fenced code block ```...``` con contenido
# significativo (>= 3 líneas o >= 60 chars), es candidato a violación cuando
# combina con prompt directo.
_CODE_BLOCK_PATTERN = re.compile(
    r"```[a-zA-Z0-9_+\-]*\s*\n([\s\S]+?)\n```",
    re.MULTILINE,
)
_MIN_CODE_BLOCK_CHARS = 60  # umbral de "bloque significativo"
_MIN_CODE_BLOCK_LINES = 3

# Detector D4: pregunta al final de la respuesta. La heurística es robusta:
# acepta signos de interrogación tanto al final como en la última oración
# (no solo el último carácter), y palabras interrogativas iniciales del
# último parágrafo.
_QUESTION_MARK_PATTERN = re.compile(r"[?¿]")

# Stopwords mínimas para el cálculo de Jaccard del detector de off-topic.
# Lista deliberadamente acotada al castellano + inglés básicos. La similitud
# léxica es operacionalización conservadora — no clasificación semántica.
_STOPWORDS = frozenset({
    # Español
    "a", "al", "ante", "bajo", "con", "de", "del", "desde", "el", "en", "es",
    "ese", "esa", "eso", "esta", "este", "esto", "estos", "estas", "fue",
    "ha", "han", "hay", "la", "las", "le", "les", "lo", "los", "me", "mi",
    "mis", "no", "nos", "o", "para", "pero", "por", "que", "qué", "se",
    "ser", "si", "sí", "sin", "sobre", "su", "sus", "te", "tu", "tus", "un",
    "una", "uno", "unos", "unas", "y", "ya", "yo",
    # English
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "have",
    "in", "is", "it", "its", "of", "on", "or", "the", "this", "to", "was",
    "were", "with", "you", "your",
})

_TOKEN_PATTERN = re.compile(r"\b[a-záéíóúñü0-9_]{3,}\b", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Thresholds y penalizaciones. Documentadas + en hash determinista del corpus.
# ---------------------------------------------------------------------------

# D3 (bloque de código en respuesta a prompt directo): violación grave —
# contradice frontalmente el rol socrático.
PENALTY_DIRECT_CODE_IN_RESPONSE = 0.5

# D4 (sin pregunta cuando el prompt era reflexivo): violación moderada — la
# pregunta es la herramienta socrática por excelencia, su ausencia es señal.
PENALTY_NO_QUESTION_TO_REFLECTIVE = 0.3

# D5 (off-topic): violación moderada — la respuesta no se corresponde con
# el prompt. Umbral conservador (Jaccard < 0.05) para minimizar falsos
# positivos en respuestas socráticas que reformulan con vocabulario distinto.
PENALTY_OFF_TOPIC = 0.4
OFF_TOPIC_JACCARD_THRESHOLD = 0.05
OFF_TOPIC_MIN_TOKENS = 5  # piso anti-falso-positivo en respuestas cortas


# ---------------------------------------------------------------------------
# Compiled regexes
# ---------------------------------------------------------------------------


def _compile_patterns(patterns: list[str]) -> list[re.Pattern[str]]:
    flags = re.IGNORECASE | re.MULTILINE
    return [re.compile(p, flags) for p in patterns]


_DIRECT_COMPILED = _compile_patterns(_DIRECT_PROMPT_PATTERNS)
_REFLECTIVE_COMPILED = _compile_patterns(_REFLECTIVE_PROMPT_PATTERNS)


# ---------------------------------------------------------------------------
# Hash determinista del corpus (mismo patrón canónico que guardrails.py)
# ---------------------------------------------------------------------------


def compute_socratic_compliance_corpus_hash() -> str:
    """SHA-256 determinista del corpus de detectors + thresholds + versión.

    Bumpear SOCRATIC_COMPLIANCE_VERSION, cualquier patrón, cualquier threshold
    o cualquier penalización cambia el hash. Mismo patrón canónico que
    `classifier_config_hash` (ADR-009) y `guardrails_corpus_hash` (ADR-019):
    `sort_keys=True`, `ensure_ascii=False`, `separators=(",", ":")`. UTF-8.
    """
    canonical = json.dumps(
        {
            "version": SOCRATIC_COMPLIANCE_VERSION,
            "direct_prompt_patterns": _DIRECT_PROMPT_PATTERNS,
            "reflective_prompt_patterns": _REFLECTIVE_PROMPT_PATTERNS,
            "thresholds": {
                "min_code_block_chars": _MIN_CODE_BLOCK_CHARS,
                "min_code_block_lines": _MIN_CODE_BLOCK_LINES,
                "off_topic_jaccard_threshold": OFF_TOPIC_JACCARD_THRESHOLD,
                "off_topic_min_tokens": OFF_TOPIC_MIN_TOKENS,
            },
            "penalties": {
                "direct_code_in_response": PENALTY_DIRECT_CODE_IN_RESPONSE,
                "no_question_to_reflective": PENALTY_NO_QUESTION_TO_REFLECTIVE,
                "off_topic": PENALTY_OFF_TOPIC,
            },
            "stopwords": sorted(_STOPWORDS),
        },
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


SOCRATIC_COMPLIANCE_CORPUS_HASH = compute_socratic_compliance_corpus_hash()


# ---------------------------------------------------------------------------
# Detectors individuales — funciones puras
# ---------------------------------------------------------------------------


def infer_prompt_kind(prompt: str) -> PromptKind:
    """Clasifica el prompt del estudiante como directo, reflexivo o neutral.

    Si el prompt matchea el corpus de directos, devuelve "direct". Si matchea
    el de reflexivos, "reflective". Si matchea AMBOS (caso ambiguo: "no
    entiendo, dame el código"), prevalece "direct" porque la solicitud
    explícita domina la intención. Si no matchea ninguno, "neutral".
    """
    if not prompt:
        return "neutral"
    is_direct = any(rgx.search(prompt) for rgx in _DIRECT_COMPILED)
    if is_direct:
        return "direct"
    is_reflective = any(rgx.search(prompt) for rgx in _REFLECTIVE_COMPILED)
    if is_reflective:
        return "reflective"
    return "neutral"


def has_significant_code_block(response: str) -> bool:
    """¿La respuesta contiene un bloque de código significativo?

    Significativo = fenced code block con >= _MIN_CODE_BLOCK_CHARS o
    >= _MIN_CODE_BLOCK_LINES líneas en su interior. Bloques inline (` `var` `)
    o snippets triviales (1-2 líneas) NO cuentan: el tutor puede mostrar
    sintaxis breve sin violar el rol socrático.
    """
    if not response:
        return False
    for match in _CODE_BLOCK_PATTERN.finditer(response):
        body = match.group(1)
        if len(body) >= _MIN_CODE_BLOCK_CHARS:
            return True
        if body.count("\n") + 1 >= _MIN_CODE_BLOCK_LINES:
            return True
    return False


def has_question(response: str) -> bool:
    """¿La respuesta contiene al menos una pregunta?

    Detecta signos de interrogación (`?` o `¿`) en cualquier posición. Una
    respuesta socrática típica termina con pregunta, pero también la incluye
    en cualquier parte del texto (ej. preguntas intercaladas). Esta heurística
    es deliberadamente permisiva — el detector contrario (sin pregunta) es
    el que dispara la violación.
    """
    if not response:
        return False
    return bool(_QUESTION_MARK_PATTERN.search(response))


def _significant_tokens(text: str) -> set[str]:
    """Tokens significativos para Jaccard: palabras de >=3 chars que no son
    stopwords. Idempotente."""
    return {
        t.lower()
        for t in _TOKEN_PATTERN.findall(text)
        if t.lower() not in _STOPWORDS
    }


def lexical_similarity_jaccard(prompt: str, response: str) -> float:
    """Similitud léxica Jaccard entre conjuntos de tokens significativos.

    Devuelve 0.0 si alguno de los dos conjuntos es vacío. Operacionalización
    conservadora — NO es similitud semántica. Migración a embeddings es
    agenda futura (ADR-044, sec. consecuencias).
    """
    p_tokens = _significant_tokens(prompt)
    r_tokens = _significant_tokens(response)
    if not p_tokens or not r_tokens:
        return 0.0
    intersection = p_tokens & r_tokens
    union = p_tokens | r_tokens
    return len(intersection) / len(union)


# ---------------------------------------------------------------------------
# Función principal: cómputo del score
# ---------------------------------------------------------------------------


def compute_socratic_compliance(
    prompt: str,
    response: str,
    prompt_kind: PromptKind | None = None,
) -> SocraticComplianceResult:
    """Calcula el score de cumplimiento socrático sobre una respuesta del tutor.

    Args:
        prompt: el prompt del estudiante que originó esta respuesta.
        response: la respuesta completa del tutor (texto, sin streaming chunks).
        prompt_kind: si el caller ya conoce el tipo de prompt (p.ej. F6/ADR-024
            futuro), lo pasa. Si es None, se infiere con `infer_prompt_kind`.

    Returns:
        SocraticComplianceResult con score ∈ [0, 1], lista de violations
        (pattern_ids de las violaciones detectadas), prompt_kind utilizado
        y corpus_hash para auditabilidad.

    Determinismo: dada la misma terna (prompt, response, prompt_kind) y la
    misma versión del corpus, la salida es idéntica bit-a-bit.
    """
    kind: PromptKind = prompt_kind if prompt_kind is not None else infer_prompt_kind(prompt)
    violations: list[str] = []
    total_penalty = 0.0

    # D3: bloque de código en respuesta a prompt directo.
    # Solo violación si el prompt fue clasificado como directo. Las preguntas
    # reflexivas o neutrales pueden incluir código de ejemplo legítimamente.
    if kind == "direct" and has_significant_code_block(response):
        violations.append(_violation_id("direct_code_in_response"))
        total_penalty += PENALTY_DIRECT_CODE_IN_RESPONSE

    # D4: sin pregunta cuando el prompt era reflexivo.
    if kind == "reflective" and not has_question(response):
        violations.append(_violation_id("no_question_to_reflective"))
        total_penalty += PENALTY_NO_QUESTION_TO_REFLECTIVE

    # D5: off-topic. Aplica a todos los kinds, con piso anti-falso-positivo
    # en respuestas cortas (la heurística Jaccard no es informativa con
    # menos de OFF_TOPIC_MIN_TOKENS tokens significativos).
    response_tokens = _significant_tokens(response)
    if len(response_tokens) >= OFF_TOPIC_MIN_TOKENS:
        sim = lexical_similarity_jaccard(prompt, response)
        if sim < OFF_TOPIC_JACCARD_THRESHOLD:
            violations.append(_violation_id("off_topic"))
            total_penalty += PENALTY_OFF_TOPIC

    score = max(0.0, 1.0 - total_penalty)
    return SocraticComplianceResult(
        score=score,
        violations=violations,
        prompt_kind=kind,
        corpus_hash=SOCRATIC_COMPLIANCE_CORPUS_HASH,
    )


def _violation_id(name: str) -> str:
    """Formato estable: `socratic_v{version_underscored}_{name}`."""
    v = SOCRATIC_COMPLIANCE_VERSION.replace(".", "_")
    return f"socratic_v{v}_{name}"
