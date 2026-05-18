"""Devolucion metacognitiva narrativa al cierre del episodio (R5 informeSoc.md).

Funcion pura determinista que toma la cadena de eventos de un episodio cerrado
y devuelve un parrafo narrativo en lenguaje no tecnico, sin score, sin nombrar
categoria de apropiacion, sin nombrar niveles N1-N4. Cinco plantillas
seleccionadas por reglas deterministicas en orden fijo.

Disenado para activarse via flag opt-in `metacognitive_feedback_enabled` (Nivel 1
de `politica-visibilidad-estudiante.md`). Default OFF en piloto-1 — el modulo
existe pero no se llama desde el pipeline hasta revision coautoral.

Invariantes (R5 design doc seccion 1):
  - El CTR sigue siendo append-only (este modulo NO emite eventos).
  - `classifier_config_hash` no cambia (este modulo es lectura).
  - LABELER_VERSION no se bumpea (la devolucion es UI, no clasificacion).
  - Nunca score numerico al estudiante.
  - Nunca nombre de categoria de apropiacion.
  - Nunca nombres N1-N4.

ATENCION (2026-05-16): las 5 plantillas estan marcadas como DRAFT —
PENDIENTE REVISION COAUTORAL con dir + co-dir + Ana Garis. El codigo
funciona pero las plantillas son provisionales. No usar en piloto real
sin revisar los textos.

Funcion pura: input lista de eventos, output dict con feedback_text +
metadata. Bit-exact reproducible para misma cadena de eventos. Tests
golden en `tests/test_metacognitive_feedback.py`.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

METACOG_FEEDBACK_VERSION = "1.0.0-draft"

# Selectores de plantilla (orden importa — primera regla matching gana).
FeedbackTemplate = Literal[
    "episodio_corto",
    "abandonado_o_comprometido",
    "sin_tutor",
    "solo_conversacion",
    "integrando_feedback",
    "consulta_temprana",
    "mixto",
]

# Umbrales de seleccion. Operacionalizacion conservadora — calibrar con docentes.
MIN_EVENTS_FOR_FEEDBACK = 5
CONSULTA_TEMPRANA_WINDOW_SECONDS = 180.0  # primeros 3 minutos
INTEGRANDO_FEEDBACK_MIN_RATIO_POST_TESTS = 0.5  # 50%+ de prompts post-tests
CONSULTA_TEMPRANA_MIN_RATIO = 0.5  # 50%+ de prompts en ventana temprana

_MIN_EVENTS_FOR_TIME_DELTA = 2


# =============================================================================
# PLANTILLAS — DRAFT PENDIENTE REVISION COAUTORAL
# =============================================================================
#
# Cada plantilla acepta kwargs y devuelve string. Reglas de redaccion:
#   - 60-120 palabras.
#   - Espanol rioplatense neutro sin modismos fuertes.
#   - Sin emojis.
#   - Sin juicios valorativos ("hiciste bien", "te conviene").
#   - Sin comparar con cohorte.
#   - Sin sugerir lo que el estudiante "deberia" haber hecho.
#   - Final invitacional, no cerrado.
#
# La operacionalizacion inicial fue redactada por el implementador de R5
# como punto de partida. NO usar en piloto real sin la revision coautoral
# de dir + co-dir + Ana Garis.

_TEMPLATES: dict[FeedbackTemplate, str] = {
    # DRAFT — PENDIENTE REVISION COAUTORAL
    "episodio_corto": (
        "Este episodio fue muy corto para que podamos mostrarte un patron "
        "claro de tu trabajo. Esta bien — a veces uno abre, mira un poco y "
        "se va. Cuando vuelvas y sientas que es el momento de quedarte un "
        "rato con el ejercicio, te vamos a poder devolver algo mas concreto."
    ),
    # DRAFT — PENDIENTE REVISION COAUTORAL
    "abandonado_o_comprometido": (
        "Este episodio no se cerro de la manera habitual. No vamos a "
        "devolverte un patron sobre el — preferimos no mostrarte algo que "
        "no esta basado en una cadena de actividad completa."
    ),
    # DRAFT — PENDIENTE REVISION COAUTORAL
    "sin_tutor": (
        "Durante este episodio trabajaste sin consultar al tutor. Escribiste "
        "codigo, lo ejecutaste y avanzaste por tu cuenta. Eso es informacion "
        "sobre como estas trabajando: a veces hace falta espacio sin "
        "preguntas externas para que las ideas se ordenen. Si en algun "
        "momento sentis que te quedaste pegado, el tutor esta para "
        "preguntas — no para respuestas."
    ),
    # DRAFT — PENDIENTE REVISION COAUTORAL
    "solo_conversacion": (
        "Durante este episodio hablaste con el tutor pero no ejecutaste "
        "codigo. Conversaste sin pasar a probar. Eso puede tener sentido "
        "cuando estas todavia entendiendo el problema, o puede indicar que "
        "te conviene probar antes — el codigo te va a decir cosas que la "
        "conversacion no. La proxima vez que entres, fijate si te sirve "
        "ejecutar algo aunque sea incompleto."
    ),
    # DRAFT — PENDIENTE REVISION COAUTORAL
    "integrando_feedback": (
        "Durante este episodio le hiciste {n_prompts} preguntas al tutor. "
        "{n_post_tests} de esas conversaciones ocurrieron despues de "
        "ejecutar tests, antes de modificar el codigo. Eso suele indicar "
        "que estas integrando lo que el tutor te dice con lo que el codigo "
        "te muestra. Es informacion sobre como estas trabajando. Si te "
        "resulta util pensarla, podes anotarte que parte de ese ida y vuelta "
        "te sirvio."
    ),
    # DRAFT — PENDIENTE REVISION COAUTORAL
    "consulta_temprana": (
        "Durante este episodio le hiciste {n_prompts} preguntas al tutor. "
        "{n_temprana} de esas conversaciones ocurrieron en los primeros "
        "minutos del episodio, antes de que pasara mucho tiempo con el "
        "enunciado. Eso es informacion sobre como estas trabajando: a veces "
        "consultar temprano agiliza, a veces convendria leer un poco mas "
        "antes. Vos sabes mejor que nadie si esta vez funciono o no."
    ),
    # DRAFT — PENDIENTE REVISION COAUTORAL
    "mixto": (
        "Durante este episodio trabajaste de varias maneras: escribiste "
        "codigo, ejecutaste tests, conversaste con el tutor. No hay un "
        "patron unico que nos llame la atencion — eso es normal cuando el "
        "trabajo es exploratorio. Si te quedas pensando un momento, fijate "
        "en cual de esas modalidades te resulto mas util y por que. Esa "
        "respuesta tuya vale mas que cualquier devolucion nuestra."
    ),
}


def _coerce_ts(ts: Any) -> datetime:
    """Convierte timestamp a datetime. Acepta str ISO-8601 o datetime."""
    if isinstance(ts, datetime):
        return ts
    return datetime.fromisoformat(str(ts).replace("Z", "+00:00"))


def _episode_started_at(events: list[dict[str, Any]]) -> datetime | None:
    """Encuentra el primer `episodio_abierto`. Devuelve None si no hay."""
    for e in events:
        if e.get("event_type") == "episodio_abierto":
            return _coerce_ts(e["ts"])
    return None


def _was_abandoned_or_compromised(events: list[dict[str, Any]]) -> bool:
    """True si el episodio fue abandonado o la cadena esta comprometida.

    Detecta: presencia de `episodio_abandonado`, ausencia de `episodio_cerrado`,
    o flag `integrity_compromised=true` en `episodio_cerrado`.
    """
    has_abandonado = any(e.get("event_type") == "episodio_abandonado" for e in events)
    if has_abandonado:
        return True
    cerrado = next((e for e in events if e.get("event_type") == "episodio_cerrado"), None)
    if cerrado is None:
        return True
    payload = cerrado.get("payload") or {}
    if payload.get("integrity_compromised") is True:
        return True
    return False


def _prompts_post_tests_count(events: list[dict[str, Any]]) -> int:
    """Cuenta prompts del estudiante emitidos tras un `tests_ejecutados`.

    Definicion operacional: un `prompt_enviado` cuenta si el ultimo
    `tests_ejecutados` o `codigo_ejecutado` previo en el episodio ocurrio
    antes del prompt (sin importar el delta — la senal es "ya probaste y
    despues preguntas", no "que tan rapido preguntas").
    """
    count = 0
    last_test_or_exec = False
    for e in events:
        et = e.get("event_type")
        if et in ("tests_ejecutados", "codigo_ejecutado"):
            last_test_or_exec = True
        elif et == "prompt_enviado" and last_test_or_exec:
            count += 1
            last_test_or_exec = False  # reset hasta el proximo test/exec
    return count


def _prompts_en_ventana_temprana(
    events: list[dict[str, Any]],
    window_seconds: float,
) -> int:
    """Cuenta prompts del estudiante dentro de los primeros `window_seconds`."""
    started_at = _episode_started_at(events)
    if started_at is None:
        return 0
    count = 0
    for e in events:
        if e.get("event_type") != "prompt_enviado":
            continue
        delta = (_coerce_ts(e["ts"]) - started_at).total_seconds()
        if 0.0 <= delta < window_seconds:
            count += 1
    return count


def _select_template(events: list[dict[str, Any]]) -> tuple[FeedbackTemplate, dict[str, Any]]:
    """Aplica las reglas en orden fijo y devuelve (plantilla, kwargs).

    Reglas (primera matching gana):
      1. episodio < 5 eventos => episodio_corto
      2. abandonado o integrity_compromised => abandonado_o_comprometido
      3. 0 prompts => sin_tutor
      4. >= 1 prompt y 0 ejecuciones/tests => solo_conversacion
      5. >= 50% prompts post-tests => integrando_feedback
      6. >= 50% prompts en primeros 180s => consulta_temprana
      7. default => mixto
    """
    if len(events) < MIN_EVENTS_FOR_FEEDBACK:
        return "episodio_corto", {}

    if _was_abandoned_or_compromised(events):
        return "abandonado_o_comprometido", {}

    n_prompts = sum(1 for e in events if e.get("event_type") == "prompt_enviado")
    n_exec = sum(1 for e in events if e.get("event_type") == "codigo_ejecutado")
    n_tests = sum(1 for e in events if e.get("event_type") == "tests_ejecutados")

    if n_prompts == 0:
        return "sin_tutor", {}

    if n_exec == 0 and n_tests == 0:
        return "solo_conversacion", {"n_prompts": n_prompts}

    n_post_tests = _prompts_post_tests_count(events)
    if n_prompts > 0 and n_post_tests / n_prompts >= INTEGRANDO_FEEDBACK_MIN_RATIO_POST_TESTS:
        return "integrando_feedback", {
            "n_prompts": n_prompts,
            "n_post_tests": n_post_tests,
        }

    n_temprana = _prompts_en_ventana_temprana(events, CONSULTA_TEMPRANA_WINDOW_SECONDS)
    if n_prompts > 0 and n_temprana / n_prompts >= CONSULTA_TEMPRANA_MIN_RATIO:
        return "consulta_temprana", {
            "n_prompts": n_prompts,
            "n_temprana": n_temprana,
        }

    return "mixto", {}


def generate_metacognitive_feedback(events: list[dict[str, Any]]) -> dict[str, Any]:
    """Genera devolucion metacognitiva narrativa para el estudiante.

    Args:
        events: lista de dicts de eventos del episodio cerrado. Cada uno
            con al menos:
                - `event_type`: str
                - `ts`: datetime o str ISO-8601
                - `payload`: dict | None (relevante para integrity_compromised)

    Returns:
        Dict con:
            - `feedback_template`: cual de las 7 plantillas se selecciono
            - `feedback_text`: string narrativo (60-120 palabras)
            - `metacog_feedback_version`: version del modulo
            - `is_draft`: True mientras las plantillas no esten revisadas

    Funcion pura, deterministica, sin side-effects.
    """
    template, kwargs = _select_template(events)
    raw_text = _TEMPLATES[template]
    if kwargs:
        feedback_text = raw_text.format(**kwargs)
    else:
        feedback_text = raw_text

    return {
        "feedback_template": template,
        "feedback_text": feedback_text,
        "metacog_feedback_version": METACOG_FEEDBACK_VERSION,
        "is_draft": True,  # bajar a False cuando las plantillas esten revisadas
    }
