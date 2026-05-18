"""Etiquetador de eventos por nivel analitico N1-N4 (componente C3.2 de la tesis).

ADR-020 - derivacion en lectura, funcion pura. NO almacena `n_level` en el
payload del evento (rompe self_hash y choca con append-only). Las reglas son
versionables via LABELER_VERSION: bumpear re-etiqueta historicos sin tocar el CTR.

Niveles (Tesis Seccion 4.3):
- N1: Comprension y planificacion (lectura del enunciado, anotaciones).
- N2: Elaboracion estrategica (escritura/edicion de codigo).
- N3: Validacion (ejecucion de codigo).
- N4: Interaccion con IA (prompts al tutor, respuestas recibidas, codigo
       copiado del tutor o pegado desde fuente externa).
- meta: apertura/cierre/abandono del episodio.

Override condicional para `edicion_codigo`: el payload trae `origin` con valores
"student_typed" | "copied_from_tutor" | "pasted_external" | None (legacy). Una
edicion copiada del tutor o pegada desde afuera se etiqueta N4 (la accion
proviene de una interaccion IA/externa, no es elaboracion propia del estudiante).

Override temporal para `anotacion_creada` (ADR-023, G8a, v1.1.0):
La Tabla 4.1 de la tesis asigna las anotaciones a N1 ("notas tomadas;
reformulacion verbal en el asistente") cuando ocurren durante la lectura del
enunciado, y a N4 ("apropiacion de argumento: reproduccion razonada de una
explicacion del asistente en produccion posterior propia") cuando ocurren tras
una respuesta del tutor. v1.0.0 las etiquetaba N2 fijo por no requerir
clasificacion semantica del contenido — sesgo sistematico documentado en
Seccion 17.3.

v1.1.0 introduce un override por POSICION TEMPORAL EN EL EPISODIO (heuristico
liviano, sin embeddings):
  - Anotacion dentro de los primeros ANOTACION_N1_WINDOW_SECONDS (120s) desde
    `episodio_abierto` => N1 (lectura del enunciado).
  - Anotacion dentro de ANOTACION_N4_WINDOW_SECONDS (60s) post `tutor_respondio`
    => N4 (apropiacion tras respuesta del tutor).
  - En cualquier otro caso => N2 (fallback v1.0.0, elaboracion estrategica).

Si las dos ventanas se solapan (anotacion N1 que ademas esta dentro de la
ventana post-tutor), gana N4 — la senal "apropiacion tras respuesta" es mas
informativa pedagogicamente que "lectura inicial".

API:
  - `label_event(event_type, payload, context=None)`: sin contexto, comportamiento
    v1.0.0 puro (compat con callers que no tienen episodio entero a mano).
    Con contexto, aplica override temporal.
  - `time_in_level(events)` y `n_level_distribution(events)` construyen contexto
    automaticamente — los caminos del piloto SI usan el override.

La heuristica es operacionalizacion conservadora declarable. La migracion
semantica (clasificacion del contenido de la anotacion) queda como agenda
del Eje B post-defensa, lo cual no invalida v1.1.0 — la tesis 19.5 declara
que el override temporal ES la version del piloto.

Cualquier cambio de las constantes de override o de la asignacion fija obliga
a bumpear LABELER_VERSION (ADR-020) y a actualizar la Seccion 19.5 de la tesis
sobre que sesgo se cierra.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from itertools import pairwise
from typing import Any, Literal

NLevel = Literal["N1", "N2", "N3", "N4", "meta"]

# v1.2.0 (Sec 9 epic ai-native-completion / ADR-033/034): introduce regla de
# etiquetado para `tests_ejecutados`. Bumpear MINOR aca obliga a re-etiquetar
# reportes empiricos pero NO toca el CTR (ADR-020 — labeler es derivado en lectura).
# v1.1.0 sigue accesible recomputando con la version anterior.
#
# Historico:
#   1.0.0 — base (Tabla 4.1 de la tesis).
#   1.1.0 — override temporal de `anotacion_creada` (ADR-023, G8a).
#   1.2.0 — regla N3/N4 para `tests_ejecutados` (ADR-033/034).
LABELER_VERSION = "1.2.0"

# Ventanas temporales del override (ADR-023). Decisiones arbitrarias del piloto
# documentadas en el ADR. Bumpear estas constantes obliga a bumpear LABELER_VERSION.
ANOTACION_N1_WINDOW_SECONDS = 120.0
ANOTACION_N4_WINDOW_SECONDS = 60.0

# v1.2.0: ventana post-`tutor_respondio` para que `tests_ejecutados` con
# todos los tests pass se etiquete N4 (apropiacion reflexiva — el alumno
# valida sin la influencia inmediata del tutor). >= 60s. < 60s o tests
# fallidos => N3 (validacion funcional). Spec 9 / scenario "Tests todos
# pass, sin tutor reciente" / "Tests con fallos".
TESTS_EJECUTADOS_N4_MIN_DELTA_SECONDS = 60.0

_MIN_EVENTS_FOR_DELTA = 2

EVENT_N_LEVEL_BASE: dict[str, NLevel] = {
    "episodio_abierto": "meta",
    "episodio_cerrado": "meta",
    "episodio_abandonado": "meta",
    "lectura_enunciado": "N1",
    "anotacion_creada": "N2",
    "edicion_codigo": "N2",
    "codigo_ejecutado": "N3",
    "prompt_enviado": "N4",
    "tutor_respondio": "N4",
    # ADR-019 (G3 Fase A): intento adverso del estudiante en su prompt al tutor.
    # Se mapea a N4 porque ocurre en la dimension de interaccion con la IA.
    "intento_adverso_detectado": "N4",
    # v1.2.0 (Sec 9 / ADR-033-034): tests Pyodide ejecutados por el alumno.
    # Base = N3 (validacion funcional). Override a N4 si todos pass + tutor
    # reciente >= 60s (apropiacion reflexiva). Ver `label_event`.
    "tests_ejecutados": "N3",
}

_EDICION_CODIGO_N4_ORIGINS = {"copied_from_tutor", "pasted_external"}


@dataclass(frozen=True)
class EpisodeContext:
    """Contexto temporal de un evento dentro de su episodio (ADR-023, v1.1.0).

    Lo construye `time_in_level` / `n_level_distribution` para cada evento.
    Callers fuera del clasificador (ej. tests directos) pueden pasar
    `context=None` y mantener comportamiento v1.0.0.

    Attributes:
        event_ts: timestamp del evento que se esta etiquetando.
        episode_started_at: timestamp del primer `episodio_abierto` visto. None si
            el episodio no abrio (eventos huerfanos — comportamiento v1.0.0).
        last_tutor_respondio_at: timestamp del `tutor_respondio` mas reciente
            ANTES o IGUAL al `event_ts`. None si todavia no hubo respuesta del tutor.
    """

    event_ts: datetime
    episode_started_at: datetime | None
    last_tutor_respondio_at: datetime | None


def label_event(
    event_type: str,
    payload: dict[str, Any] | None = None,
    context: EpisodeContext | None = None,
) -> NLevel:
    """Devuelve el nivel analitico de un evento.

    Sin `context` el comportamiento es v1.0.0 puro (no override temporal). Con
    contexto, `anotacion_creada` aplica override por posicion temporal segun
    ADR-023 / v1.1.0.

    `event_type` desconocido devuelve "meta" como fallback conservador.
    """
    base = EVENT_N_LEVEL_BASE.get(event_type)
    if base is None:
        return "meta"
    if event_type == "edicion_codigo":
        origin = (payload or {}).get("origin")
        if origin in _EDICION_CODIGO_N4_ORIGINS:
            return "N4"
    if event_type == "anotacion_creada":
        # ADR-045 (Mejora 3 plan post-piloto-1, G8b lexico): si el flag esta
        # ON, el override lexico sobre contenido textual tiene precedencia
        # sobre el temporal v1.1.0. OFF por default — preserva exactamente el
        # comportamiento v1.1.0 del piloto-1. Patron fail-soft: cualquier
        # error en el lexical NO rompe el labeler (cae al fallback temporal).
        try:
            from classifier_service.config import settings as _settings

            if _settings.lexical_anotacion_override_enabled:
                from classifier_service.services.event_labeler_lexical import (
                    lexical_label,
                )

                content = (payload or {}).get("content", "") or ""
                lex = lexical_label(content)
                if lex is not None:
                    return lex
        except Exception:  # noqa: BLE001 — fail-soft per ADR-045
            pass
        # Override temporal v1.1.0 (ADR-023) — N4 gana sobre N1 si ambas matchean.
        if context is not None:
            if context.last_tutor_respondio_at is not None:
                delta_tutor = (context.event_ts - context.last_tutor_respondio_at).total_seconds()
                if 0.0 <= delta_tutor < ANOTACION_N4_WINDOW_SECONDS:
                    return "N4"
            if context.episode_started_at is not None:
                delta_open = (context.event_ts - context.episode_started_at).total_seconds()
                if 0.0 <= delta_open < ANOTACION_N1_WINDOW_SECONDS:
                    return "N1"
    if event_type == "tests_ejecutados":
        # v1.2.0: regla N3/N4 (Spec 9, ADR-033-034).
        # - Tests con fallos => N3 siempre (validacion funcional, sin reflexion).
        # - Todos pass + tutor_respondio reciente (>= 60s ago) => N4
        #   (apropiacion reflexiva — el alumno valida solo, sin la influencia
        #   inmediata del tutor).
        # - Todos pass + tutor reciente (< 60s) o sin tutor todavia => N3.
        p = payload or {}
        failed = p.get("test_count_failed")
        if isinstance(failed, int) and failed > 0:
            return "N3"
        if isinstance(failed, int) and failed == 0 and context is not None:
            if context.last_tutor_respondio_at is not None:
                delta = (context.event_ts - context.last_tutor_respondio_at).total_seconds()
                if delta >= TESTS_EJECUTADOS_N4_MIN_DELTA_SECONDS:
                    return "N4"
        # Sin contexto o sin failed conocido o tutor demasiado reciente => base N3.
    return base


def _build_event_contexts(
    sorted_events: list[dict[str, Any]],
) -> list[EpisodeContext]:
    """Pre-computa EpisodeContext para cada evento (en el mismo orden recibido).

    Asume `sorted_events` ya ordenado por `seq`. Recorre una vez el episodio
    propagando `episode_started_at` (primer `episodio_abierto`) y
    `last_tutor_respondio_at` (ultimo `tutor_respondio` visto al momento).
    """
    episode_started_at: datetime | None = None
    last_tutor_respondio_at: datetime | None = None
    contexts: list[EpisodeContext] = []
    for ev in sorted_events:
        ts = _parse_ts(ev["ts"])
        # Snapshot del contexto ANTES de procesar este evento (los flags
        # se actualizan despues, asi `tutor_respondio` mismo no se considera
        # como su propio "ultimo tutor_respondio" para el override).
        contexts.append(
            EpisodeContext(
                event_ts=ts,
                episode_started_at=episode_started_at,
                last_tutor_respondio_at=last_tutor_respondio_at,
            )
        )
        if ev["event_type"] == "episodio_abierto" and episode_started_at is None:
            episode_started_at = ts
        elif ev["event_type"] == "tutor_respondio":
            last_tutor_respondio_at = ts
    return contexts


def time_in_level(events: list[dict[str, Any]]) -> dict[NLevel, float]:
    """Suma duracion (segundos) acumulada por nivel a lo largo del episodio.

    La duracion de un evento es el delta hasta el evento siguiente. El ultimo
    evento aporta 0 (no hay siguiente). Asume `seq` ordenable; si los timestamps
    estan invertidos por reloj de cliente, el delta se clamp a 0.

    Episodios con < 2 eventos devuelven todos los niveles en 0.0.

    v1.1.0 (ADR-023): `anotacion_creada` se etiqueta con override temporal segun
    su posicion en el episodio (ver docstring del modulo).
    """
    durations: dict[NLevel, float] = {
        "N1": 0.0,
        "N2": 0.0,
        "N3": 0.0,
        "N4": 0.0,
        "meta": 0.0,
    }
    if len(events) < _MIN_EVENTS_FOR_DELTA:
        return durations

    sorted_events = sorted(events, key=lambda e: e["seq"])
    contexts = _build_event_contexts(sorted_events)
    for (current, nxt), ctx in zip(pairwise(sorted_events), contexts, strict=False):
        level = label_event(current["event_type"], current.get("payload"), context=ctx)
        delta = (_parse_ts(nxt["ts"]) - _parse_ts(current["ts"])).total_seconds()
        if delta < 0:
            delta = 0.0
        durations[level] += delta
    return durations


def n_level_distribution(events: list[dict[str, Any]]) -> dict[str, Any]:
    """Distribucion completa para el endpoint /n-level-distribution.

    Devuelve `labeler_version`, `distribution_seconds` (segundos por nivel),
    `distribution_ratio` (fraccion del tiempo total), y `total_events_per_level`
    (cantidad de eventos por nivel). El ratio es 0.0 si el episodio tiene 0
    duracion (un solo evento, o todos al mismo timestamp).

    v1.1.0: tanto los conteos como los segundos consideran el override temporal
    de `anotacion_creada`. La consistencia entre ambos (mismo evento → mismo
    nivel para conteo y duracion) se preserva usando el mismo contexto.
    """
    durations = time_in_level(events)
    counts: dict[NLevel, int] = {"N1": 0, "N2": 0, "N3": 0, "N4": 0, "meta": 0}
    if events:
        sorted_events = sorted(events, key=lambda e: e["seq"])
        contexts = _build_event_contexts(sorted_events)
        for ev, ctx in zip(sorted_events, contexts, strict=False):
            counts[label_event(ev["event_type"], ev.get("payload"), context=ctx)] += 1

    total_seconds = sum(durations.values())
    if total_seconds > 0:
        ratios: dict[NLevel, float] = {
            level: secs / total_seconds for level, secs in durations.items()
        }
    else:
        ratios = dict.fromkeys(durations, 0.0)

    return {
        "labeler_version": LABELER_VERSION,
        "distribution_seconds": durations,
        "distribution_ratio": ratios,
        "total_events_per_level": counts,
    }


def _parse_ts(ts: str | datetime) -> datetime:
    if isinstance(ts, datetime):
        return ts
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))
