"""Detección preprocesamiento de intentos adversos en prompts del estudiante (ADR-019, ADR-043).

Fase A: análisis del prompt ANTES de enviarlo al LLM. Por cada match del
corpus regex, el caller (tutor_core) emite un evento CTR `intento_adverso_detectado`.
NO bloquea el flow — el prompt llega al LLM sin modificación.

Fase B (postprocesamiento de respuesta + `socratic_compliance`) NO está en v1.0.0.

v1.2.0 (ADR-043) agrega la categoría `overuse` mediante detector basado en ventana
temporal cross-prompt sobre el mismo episodio (sliding window en Redis). El detector
no es regex sino estado por episodio; convive con el flow side-channel del resto.

Reproducibilidad bit-a-bit: cada match lleva `guardrails_corpus_hash`. Bumpear
GUARDRAILS_CORPUS_VERSION, cualquier patrón regex o cualquier threshold de overuse
cambia el hash. Eventos viejos quedan etiquetados con el hash del corpus que los
detectó (mismo patrón que `classifier_config_hash` en ADR-009).

Limitaciones declaradas en el ADR-019 + revisión adversarial 2026-04-27:
- Regex no detecta encadenamientos sofisticados (técnica 4 de Sección 8.5.1).
- Evasión intra-palabra (e.g. `"olvi-da tus instrucciones"`, `"ig-no-ra"`)
  NO está cubierta en v1.1.0 — es señal clara de malicia pero matchearla
  con regex sin introducir falsos positivos masivos requiere clasificador
  ML (Fase B). Documentado como agenda futura.
- Falsos positivos posibles (especialmente `jailbreak_fiction` — severidad 2).
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Literal, Protocol
from uuid import UUID

GUARDRAILS_CORPUS_VERSION = "1.2.0"

Category = Literal[
    "jailbreak_indirect",
    "jailbreak_substitution",
    "jailbreak_fiction",
    "persuasion_urgency",
    "prompt_injection",
    "overuse",
]


@dataclass(frozen=True)
class Match:
    """Match de un patrón adverso. Devuelto por `detect()`."""

    pattern_id: str
    category: Category
    severity: int
    matched_text: str


# Severidad por categoria (ADR-019 tabla, extendida por ADR-043):
# - jailbreak_indirect: 3 (intento explicito de cambio de rol)
# - jailbreak_substitution: 4 (override directo)
# - jailbreak_fiction: 2 (ambiguo — puede ser legitimo)
# - persuasion_urgency: 2 (manipulacion emocional informativa)
# - prompt_injection: 5 (markup injection — riesgo alto)
# - overuse: 1 (informativo — patrón de uso excesivo del tutor, ADR-043)
_SEVERITY: dict[Category, int] = {
    "jailbreak_indirect": 3,
    "jailbreak_substitution": 4,
    "jailbreak_fiction": 2,
    "persuasion_urgency": 2,
    "prompt_injection": 5,
    "overuse": 1,
}


# ADR-043: Thresholds del detector de sobreuso. Se incluyen en el hash canónico
# del corpus para preservar reproducibilidad bit-a-bit: cualquier cambio en
# estos valores cambia `guardrails_corpus_hash` y los eventos nuevos quedan
# etiquetados con el hash nuevo, mientras los históricos preservan el suyo.
#
# Heurística operativa:
# - BURST: >= OVERUSE_BURST_THRESHOLD prompts dentro de una ventana móvil de
#   OVERUSE_BURST_WINDOW_SECONDS sobre el mismo episodio. Captura ráfagas
#   compulsivas tipo "spam" del tutor.
# - PROPORTION: durante los primeros OVERUSE_PROPORTION_WINDOW_SECONDS del
#   episodio, fracción de prompts respecto del total de eventos cognitivos
#   supera OVERUSE_PROPORTION_THRESHOLD. Captura inicios donde el estudiante
#   arranca preguntando antes de leer/pensar.
#
# Análisis de sensibilidad: ver `docs/adr/043-sensitivity-analysis.md` (a
# generar con `scripts/g3-overuse-sensitivity-analysis.py`).
OVERUSE_BURST_WINDOW_SECONDS = 300.0
OVERUSE_BURST_THRESHOLD = 6
OVERUSE_PROPORTION_WINDOW_SECONDS = 600.0
OVERUSE_PROPORTION_THRESHOLD = 0.7
OVERUSE_MIN_EVENTS_FOR_PROPORTION = 5  # piso anti-falso-positivo en episodios cortos


# Patrones por categoria. Cada string es una regex case-insensitive.
# Convenciones:
# - Separar palabras con `[\s\-_.]+` (no solo `\s+`) para tolerar guiones/puntos/
#   underscores como evasion ("olvi-da tus instrucciones" debe matchear).
# - Tildes en mayusculas: `re.IGNORECASE` solo cubre ASCII; las variantes con
#   tildes se incluyen explicitamente como `(o|ó)` o `(O|Ó)`.
# - Mezclar ES + EN: estudiantes pueden tipear en ambos idiomas.
# - v1.1.0: corpus ampliado tras revision adversarial — cobertura mejorada
#   contra variantes triviales evitables (verbos `ignora`/`descarta`/`borra`,
#   palabras `prompt`/`reglas`/`directivas` ademas de `instrucciones`).
_PATTERNS: dict[Category, list[str]] = {
    "jailbreak_indirect": [
        # "imagina(te)? que (sos|eres|seas|fueras) un tutor sin restriccion(es)?"
        # Tolera separadores variados (guiones/puntos en evasion)
        r"imagin(a|ate|emos|á|ate)[\s\-_.]+que[\s\-_.]+(sos|eres|seas|fueras)[\s\-_.]+(un[\s\-_.]+)?(tutor|asistente|ai)[\s\-_.]+sin[\s\-_.]+restricci",
        # "pretend you (are|were|will be) a tutor without/with no restrictions"
        r"pretend\s+you\s+(are|were|will\s+be)\s+(an?\s+)?(tutor|assistant|ai)\s+(without|with\s+no)",
        # "act(u|ú)a como (si no )?(tuvieras|tuvieses|tendrias) restricciones"
        r"act(u|ú)a[\s\-_.]+como[\s\-_.]+(si[\s\-_.]+no[\s\-_.]+)?(tuvieras|tuvieses|tendrias|tendrías)[\s\-_.]+restricci",
        # "roleplay as ... without/with no filter/limit/restriction"
        r"role[\s\-_]?play\s+as\s+.{1,40}\s+(without|with\s+no)\s+(filter|limit|restrict)",
    ],
    "jailbreak_substitution": [
        # Verbos: olvida/ignora/descarta/borra (con tildes ESP) + tildes mayuscula:
        #   olvida/olvidá/olvidate, ignora, descarta, borra
        # Separadores tolerantes: guiones, puntos, underscores ("olvi-da")
        # Objetos: tus/las/todas mis/tus + instrucciones/reglas/directivas/prompt/orden
        r"(olvid|ignor|descart|borr|olv(i|í)d)[aá](te)?[\s\-_.]+(tus|las|tod[oa]s\s+(tus|las|mis|los))?[\s\-_.]*(instrucci|regl|prompt|directiv|orden|comando)",
        # Variante mas ancha en EN: "ignore" + opcional all/your/previous + objeto
        r"ignore[\s\-_]+(all\s+|your\s+|the\s+|previous\s+)*(instruction|prompt|message|rule|directive|command)",
        # "new/nuevo system prompt" / "nuevo prompt del sistema"
        r"new[\s\-_]+system[\s\-_]+(prompt|message|instruction|rule)",
        r"nuevo[\s\-_]+(system\s+)?prompt[\s\-_]+(del?\s+)?sistema",
        # "disregard (the|your)? (rules|guidelines|instructions|directives)"
        r"disregard\s+(the\s+|your\s+|all\s+)?(rule|guideline|instruction|directive|prompt)",
        # "olvida/borra/descarta lo (de) (antes|previo|anterior)" — variante elidida
        r"(olvid|borr|descart)[aá](te)?[\s\-_.]+(todo[\s\-_.]+)?lo[\s\-_.]+(de[\s\-_.]+)?(antes|previo|anterior)",
        # "override (your|the) (system|prompt|instructions)"
        r"override\s+(your\s+|the\s+)?(system|prompt|instruction|rule)",
    ],
    "jailbreak_fiction": [
        # "en una novela/historia/ficcion donde ..."
        r"en\s+una\s+(novela|historia|ficci(o|ó)n)\s+donde",
        # "in a fictional scenario/world/setting"
        r"in\s+an?\s+fictional\s+(scenario|world|setting)",
        # "escribi(endo)? un cuento/relato/historia donde"
        r"escrib(i|í|iendo)\s+(un\s+)?(cuento|relato|historia)\s+donde",
    ],
    "persuasion_urgency": [
        # Familia enfermo/muriendo (manipulacion emocional clara)
        r"mi\s+(abuel[ao]|madre|padre|herman[ao]|familiar|t(i|í)[ao])\s+(est[aá])\s+(muriendo|enferm|grave)",
        # "tengo examen (mañana|manana|hoy|esta noche/tarde|en N)"
        # Match solo cuando hay temporalidad inminente — NO matchea "estudie para el examen"
        r"tengo\s+(un\s+)?(examen|parcial|final)\s+(ma(ñ|n)ana|hoy|esta\s+(noche|tarde)|en\s+\d)",
        # "i have an exam (tomorrow|today|in N hours)"
        r"i\s+have\s+(an?\s+)?(exam|test|final)\s+(tomorrow|today|in\s+\d)",
        # "es (super)? urgente" SOLO si va con imperativo — restriccion v1.1.0:
        # el patron viejo `r"es\s+...urgente\s+(por favor)?"` matcheaba prompts
        # legitimos como "es urgente que entienda esto antes del examen".
        # Nuevo: requiere verbo imperativo cercano (dame/escribime/respondeme/etc.)
        r"(es|sea)\s+(super\s+|muy\s+)?urgente\s*[,!.;]?\s*(por\s+favor\s+)?(dame|dale|escrib(e|ime|ímelo|í)|respond(e|eme|émelo|é)|necesito\s+(la|el|que)|ayudame|hace(lo|melo))",
    ],
    "prompt_injection": [
        # Markup tags de sistema
        r"</?\s*system\s*>",
        # "system:" al inicio de linea o despues de newline
        r"(^|\n)\s*system\s*:",
        # "[INST]" / "[/INST]" — markup de instruct models
        r"\[\s*/?\s*INST\s*\]",
        # "<|im_start|>" / "<|im_end|>" — markup OpenAI/ChatML
        r"<\|im_(start|end)\|>",
        # "<|endoftext|>" / EOS markup (ChatGPT-style)
        r"<\|(endoftext|eos|bos)\|>",
    ],
}


def _compile_patterns(
    raw: dict[Category, list[str]],
) -> dict[Category, list[tuple[str, re.Pattern[str]]]]:
    """Compila cada regex con flags case-insensitive + multilinea (donde aplica).

    Devuelve `{category: [(pattern_id, compiled_regex), ...]}`. El `pattern_id`
    es estable (`{category}_v{version}_p{idx}`) y se incluye en el evento CTR
    para análisis empírico (qué patrón específico hizo match).
    """
    compiled: dict[Category, list[tuple[str, re.Pattern[str]]]] = {}
    flags = re.IGNORECASE | re.MULTILINE
    for category, patterns in raw.items():
        compiled[category] = [
            (
                f"{category}_v{GUARDRAILS_CORPUS_VERSION.replace('.', '_')}_p{idx}",
                re.compile(pat, flags),
            )
            for idx, pat in enumerate(patterns)
        ]
    return compiled


_COMPILED = _compile_patterns(_PATTERNS)


def compute_guardrails_corpus_hash() -> str:
    """SHA-256 determinista del corpus de patrones + thresholds de overuse + versión.

    Bumpear GUARDRAILS_CORPUS_VERSION, cualquier string en `_PATTERNS` o cualquier
    threshold de overuse (ADR-043) cambia el hash. Mismo patrón canónico que
    `classifier_config_hash` (ADR-009): `sort_keys=True`, `ensure_ascii=False`,
    `separators=(",", ":")`. Encoding UTF-8.
    """
    canonical = json.dumps(
        {
            "corpus_version": GUARDRAILS_CORPUS_VERSION,
            "patterns": _PATTERNS,
            "overuse_thresholds": {
                "burst_window_seconds": OVERUSE_BURST_WINDOW_SECONDS,
                "burst_threshold": OVERUSE_BURST_THRESHOLD,
                "proportion_window_seconds": OVERUSE_PROPORTION_WINDOW_SECONDS,
                "proportion_threshold": OVERUSE_PROPORTION_THRESHOLD,
                "min_events_for_proportion": OVERUSE_MIN_EVENTS_FOR_PROPORTION,
            },
        },
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


GUARDRAILS_CORPUS_HASH = compute_guardrails_corpus_hash()


# Length cap para `matched_text`. Si una regex matchea un fragmento gigante,
# truncamos para no inflar el evento CTR. Mantiene el inicio (donde suele
# estar la senal mas clara).
_MAX_MATCHED_TEXT = 200


def detect(content: str) -> list[Match]:
    """Devuelve TODOS los matches del corpus para el prompt dado.

    Lista vacia si nada matchea. Multiples matches del mismo patron en el
    mismo prompt cuentan UNA sola vez (re.search, no re.findall) — un evento
    CTR por (patron, prompt). Multiples patrones distintos que matcheen
    generan multiples eventos.

    Funcion pura, idempotente, sin side-effects. Latencia <1ms para prompts
    de hasta ~10k chars (validado en tests).
    """
    if not content:
        return []

    matches: list[Match] = []
    for category, items in _COMPILED.items():
        severity = _SEVERITY[category]
        for pattern_id, regex in items:
            m = regex.search(content)
            if m is None:
                continue
            matched = m.group(0)
            if len(matched) > _MAX_MATCHED_TEXT:
                matched = matched[:_MAX_MATCHED_TEXT] + "..."
            matches.append(
                Match(
                    pattern_id=pattern_id,
                    category=category,
                    severity=severity,
                    matched_text=matched,
                )
            )
    return matches


# ---------------------------------------------------------------------------
# Detector de sobreuso (ADR-043, v1.2.0)
#
# A diferencia del detector regex (función pura sobre un único prompt), el
# detector de sobreuso requiere ESTADO POR EPISODIO porque debe razonar sobre
# múltiples prompts en una ventana temporal. Se materializa con sliding windows
# en Redis: una sorted set por episodio con score=epoch_ts, member=event_id.
#
# Convivencia con el flow side-channel: el detector NO bloquea. Si Redis cae,
# el caller (`tutor_core.interact()`) atrapa la excepción y continúa sin
# emitir el evento — mismo patrón fail-soft que el detector regex.
#
# Aislamiento multi-tenant: la key incluye `episode_id` que es UUID único por
# tenant (no hay riesgo de colisión cross-tenant). La RLS de Postgres no aplica
# a Redis pero el aislamiento queda dado por la unicidad del UUID.
# ---------------------------------------------------------------------------


class _RedisLike(Protocol):
    """Protocolo mínimo de Redis async que el detector necesita.

    Definido como Protocol para evitar dependencia hard de `redis.asyncio`
    en este módulo (que sigue siendo importable sin Redis para tests directos
    del detector regex).
    """

    async def zadd(self, key: str, mapping: dict[str, float]) -> int: ...
    async def zremrangebyscore(self, key: str, min_score: float, max_score: float) -> int: ...
    async def zcard(self, key: str) -> int: ...
    async def zrangebyscore(
        self, key: str, min_score: float, max_score: float
    ) -> list[bytes]: ...
    async def expire(self, key: str, seconds: int) -> bool: ...


# Prefijo de la key Redis del ledger de overuse. Disjunto del prefijo de
# sesiones (`tutor:session:` en `session.py`) para evitar colisiones.
OVERUSE_KEY_PREFIX = "tutor:overuse:"

# TTL del ledger por episodio. Mayor que la sesión (6h) para tolerar desfases
# entre cierre de episodio y limpieza de Redis. Fail-safe: la sorted set se
# limpia naturalmente cuando vence el TTL.
_OVERUSE_KEY_TTL_SECONDS = 8 * 3600


class OveruseDetector:
    """Detector de sobreuso del tutor con sliding window por episodio (ADR-043).

    Mantiene en Redis una sorted set por episodio con los timestamps de los
    eventos relevantes para detectar dos patrones de sobreuso:

    - **Burst**: cantidad de prompts dentro de los últimos
      `OVERUSE_BURST_WINDOW_SECONDS` supera `OVERUSE_BURST_THRESHOLD`. Captura
      ráfagas compulsivas (típicamente "dame esto, dame el otro, dame...").
    - **Proportion**: durante los primeros
      `OVERUSE_PROPORTION_WINDOW_SECONDS` desde el primer evento del episodio,
      la fracción `prompts / total_eventos` supera
      `OVERUSE_PROPORTION_THRESHOLD`. Captura inicios de episodio donde el
      estudiante prompea sin leer ni pensar.

    Diseño:

    - El detector mantiene DOS sorted sets por episodio: una para `prompt_enviado`
      (key `{prefix}{episode_id}:prompts`) y otra para todos los eventos
      cognitivos no-prompt (`{prefix}{episode_id}:events`). Score = epoch_ts.
    - El caller invoca `record_event()` para registrar y `check()` para evaluar.
    - Cada `check()` que devuelve un Match es independiente del próximo: no se
      "deduplica" — si el patrón de sobreuso persiste, se emiten múltiples
      eventos. La análisis empírico agrupa por episodio en analytics.

    Race conditions: en condiciones de alta concurrencia sobre el mismo
    episodio (improbable: el estudiante es un solo cliente HTTP), dos prompts
    casi simultáneos pueden ambos disparar una detección de burst. Comportamiento
    aceptable: dos eventos de overuse con misma severidad se appendean al CTR.
    """

    def __init__(self, redis_client: _RedisLike) -> None:
        self.redis = redis_client

    @staticmethod
    def _prompts_key(episode_id: UUID) -> str:
        return f"{OVERUSE_KEY_PREFIX}{episode_id}:prompts"

    @staticmethod
    def _events_key(episode_id: UUID) -> str:
        return f"{OVERUSE_KEY_PREFIX}{episode_id}:events"

    async def record_prompt(self, episode_id: UUID, prompt_event_id: UUID, ts: float) -> None:
        """Registra un `prompt_enviado` en el ledger del episodio."""
        key = self._prompts_key(episode_id)
        await self.redis.zadd(key, {str(prompt_event_id): ts})
        await self.redis.expire(key, _OVERUSE_KEY_TTL_SECONDS)

    async def record_non_prompt_event(
        self, episode_id: UUID, event_id: UUID, ts: float
    ) -> None:
        """Registra un evento cognitivo no-prompt (lectura, edicion, ejecucion).

        Se usa para calcular la PROPORCIÓN de prompts en el patrón de inicio.
        Eventos `meta` (apertura/cierre/abandono) NO entran al ledger.
        """
        key = self._events_key(episode_id)
        await self.redis.zadd(key, {str(event_id): ts})
        await self.redis.expire(key, _OVERUSE_KEY_TTL_SECONDS)

    async def check(self, episode_id: UUID, now: float) -> Match | None:
        """Evalúa los dos patrones de sobreuso para el episodio. Devuelve el
        primer match encontrado, o None si ninguno aplica.

        Orden de evaluación: primero burst (más sensible al estado actual),
        después proportion (sensible a la trayectoria desde el inicio).

        No realiza trim destructivo del ledger: el TTL de Redis se encarga
        de la limpieza natural. Trimear acá rompería el cálculo de proportion
        que necesita una ventana más amplia que burst.
        """
        prompts_key = self._prompts_key(episode_id)
        events_key = self._events_key(episode_id)

        # Patrón BURST: prompts en la ventana móvil de N segundos. Conteo
        # mediante `zrangebyscore` (inclusivo en ambos extremos), sin trim.
        burst_min = now - OVERUSE_BURST_WINDOW_SECONDS
        prompts_in_burst_window = await self.redis.zrangebyscore(
            prompts_key, burst_min, now
        )
        burst_count = len(prompts_in_burst_window)
        if burst_count >= OVERUSE_BURST_THRESHOLD:
            return Match(
                pattern_id=f"overuse_v{GUARDRAILS_CORPUS_VERSION.replace('.', '_')}_burst",
                category="overuse",
                severity=_SEVERITY["overuse"],
                matched_text=(
                    f"burst: {burst_count} prompts en ventana de "
                    f"{int(OVERUSE_BURST_WINDOW_SECONDS)}s"
                ),
            )

        # Patrón PROPORTION: durante los últimos OVERUSE_PROPORTION_WINDOW_SECONDS
        # del episodio, ¿la fracción de prompts sobre el total de eventos
        # cognitivos supera el umbral?
        proportion_min = now - OVERUSE_PROPORTION_WINDOW_SECONDS
        prompts_in_window = await self.redis.zrangebyscore(
            prompts_key, proportion_min, now
        )
        events_in_window = await self.redis.zrangebyscore(
            events_key, proportion_min, now
        )
        total_in_window = len(prompts_in_window) + len(events_in_window)
        if total_in_window < OVERUSE_MIN_EVENTS_FOR_PROPORTION:
            return None  # piso anti-falso-positivo en episodios cortos
        proportion = len(prompts_in_window) / total_in_window
        if proportion >= OVERUSE_PROPORTION_THRESHOLD:
            return Match(
                pattern_id=f"overuse_v{GUARDRAILS_CORPUS_VERSION.replace('.', '_')}_proportion",
                category="overuse",
                severity=_SEVERITY["overuse"],
                matched_text=(
                    f"proportion: {len(prompts_in_window)}/{total_in_window}"
                    f" prompts en ventana de {int(OVERUSE_PROPORTION_WINDOW_SECONDS)}s"
                    f" = {proportion:.2f}"
                ),
            )

        return None
