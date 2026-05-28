"""Coherencia Temporal (CT).

Definición operacional:
  - Divide el episodio en ventanas de trabajo separadas por pausas >5min.
  - Para cada ventana, calcula una "actividad temporal" (densidad de eventos,
    ratio prompt/ejecución, pausas reflexivas).
  - ct_summary = promedio ponderado normalizado en [0, 1], donde:
      * 0 = actividad extremadamente fragmentada / no productiva
      * 1 = patrones de trabajo sostenido y progresivo

La métrica NO colapsa los valores por ventana: se preservan en `features`
para explainability. El score global es solo una síntesis.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

PAUSE_THRESHOLD = timedelta(minutes=5)
# Pausas mayores dividen el episodio en ventanas distintas

MIN_EVENTS_FOR_SCORE = 3
# Con menos de 3 eventos, no podemos evaluar CT significativamente


@dataclass
class WorkWindow:
    start: datetime
    end: datetime
    event_count: int
    prompt_count: int
    execution_count: int
    reflection_count: int

    @property
    def duration_seconds(self) -> float:
        return (self.end - self.start).total_seconds()

    @property
    def density(self) -> float:
        """Eventos por minuto."""
        mins = max(self.duration_seconds / 60, 1.0)
        return self.event_count / mins

    @property
    def prompt_exec_ratio(self) -> float:
        """Ratio prompts enviados / ejecuciones de código.

        Valor >1: más consulta que acción (posible pasividad).
        Valor <0.5: más acción con poca reflexión.
        ~1 es el rango saludable.

        NOTA (CS08 informeSocra1.md / plan1Socra.md, 2026-05-16):
        el rango saludable en torno a 1:1 (que `compute_ct_summary` aplica
        como `balance = 1.0 - abs(ratio - 0.5) * 2`) es OPERACIONALIZACION
        DEL IMPLEMENTADOR, no derivacion de literatura cognitiva establecida.
        La eleccion de "balance perfecto" a ratio = 0.5 (50% prompts) es
        decision de diseno arbitraria. Calibrar empiricamente sobre las 106
        classifications historicas post-A1 antes de presentar como umbral
        universal. Bumpear `LABELER_VERSION` si la calibracion modifica
        el ratio objetivo. Plan documentado en plan1Socra.md CS20.
        """
        total = self.prompt_count + self.execution_count
        if total == 0:
            return 0.5
        return self.prompt_count / total


def compute_windows(events: list[dict]) -> list[WorkWindow]:
    """Divide eventos en ventanas por pausas > PAUSE_THRESHOLD."""
    if not events:
        return []

    # Asumimos eventos en orden de seq
    sorted_events = sorted(events, key=lambda e: e["seq"])
    windows: list[WorkWindow] = []
    current_events: list[dict] = [sorted_events[0]]

    for prev, curr in itertools.pairwise(sorted_events):
        prev_ts = _parse_ts(prev["ts"])
        curr_ts = _parse_ts(curr["ts"])
        if curr_ts - prev_ts > PAUSE_THRESHOLD:
            windows.append(_build_window(current_events))
            current_events = [curr]
        else:
            current_events.append(curr)

    if current_events:
        windows.append(_build_window(current_events))

    return windows


def compute_ct_summary(windows: list[WorkWindow]) -> float:
    """Coherencia temporal agregada en [0, 1].

    Heurística:
    - Cada ventana aporta con peso proporcional a su duración.
    - Score de ventana combina densidad y balance prompt/exec.

    Bug fix 2026-05-28: si una ventana NO tiene prompts NI ejecuciones,
    el balance heredado del fallback `prompt_exec_ratio = 0.5` daba
    falso positivo (balance "perfecto" sin actividad real). En ese
    caso usamos solo density_score para el score de la ventana.
    """
    if not windows:
        return 0.5  # neutral si no hay datos

    total_weight = 0.0
    weighted_sum = 0.0

    for w in windows:
        weight = w.duration_seconds / 60  # minutos de la ventana
        if weight <= 0:
            continue

        # Score de la ventana:
        # - densidad normalizada (clamp entre 0.5 y 5 eventos/min → 0-1)
        density_score = min(1.0, max(0.0, (w.density - 0.5) / 4.5))

        if w.prompt_count + w.execution_count == 0:
            # Sin prompts ni ejecuciones, el balance no es interpretable.
            # Solo aportamos density_score (sin coeficiente artificial).
            window_score = density_score
        else:
            # balance: cercanía a ratio 0.5 (mitad prompts, mitad exec)
            balance = 1.0 - abs(w.prompt_exec_ratio - 0.5) * 2
            window_score = 0.5 * density_score + 0.5 * balance

        weighted_sum += weight * window_score
        total_weight += weight

    if total_weight == 0:
        return 0.5
    return weighted_sum / total_weight


def ct_features(events: list[dict]) -> dict[str, Any]:
    """Features explicativos de CT para auditoría."""
    windows = compute_windows(events)
    if not windows:
        return {"windows": 0, "ct_summary": 0.5, "insufficient_data": True}

    # Bug fix 2026-05-28: marcar insufficient_data cuando el episodio no
    # tiene NI ejecuciones de código NI anotaciones reflexivas. El valor
    # de ct_summary puede caer cerca de 0.5 en ese caso pero NO refleja
    # señal pedagógica real — solo densidad de prompts/eventos auxiliares.
    total_execs = sum(w.execution_count for w in windows)
    total_reflections = sum(w.reflection_count for w in windows)
    insufficient = total_execs == 0 and total_reflections == 0

    return {
        "windows": len(windows),
        "total_duration_min": sum(w.duration_seconds for w in windows) / 60,
        "ct_summary": compute_ct_summary(windows),
        "avg_density_evt_per_min": sum(w.density for w in windows) / len(windows),
        "avg_prompt_exec_ratio": sum(w.prompt_exec_ratio for w in windows) / len(windows),
        "insufficient_data": insufficient,
    }


# ── Internos ──────────────────────────────────────────────────────────


def _parse_ts(ts: str | datetime) -> datetime:
    if isinstance(ts, datetime):
        return ts
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def _build_window(events: list[dict]) -> WorkWindow:
    first_ts = _parse_ts(events[0]["ts"])
    last_ts = _parse_ts(events[-1]["ts"])
    prompts = sum(1 for e in events if e["event_type"] == "prompt_enviado")
    # `execution_count` cuenta ejecuciones que el alumno hace contra el código:
    # tanto el run libre (`codigo_ejecutado`) como la corrida de tests
    # (`tests_ejecutados`) son actos de ejecución sobre su solución, y ambos
    # cuentan para el `prompt_exec_ratio` (balance prompts ↔ acción). Antes
    # solo se contaba `codigo_ejecutado` y los alumnos que usaban tests pero
    # no run libre caían en `prompt_exec_ratio = 1.0` (balance = 0), forzando
    # `ct_summary = 0.5` constante.
    execs = sum(
        1 for e in events if e["event_type"] in ("codigo_ejecutado", "tests_ejecutados")
    )
    reflections = sum(1 for e in events if e["event_type"] == "anotacion_creada")
    return WorkWindow(
        start=first_ts,
        end=last_ts,
        event_count=len(events),
        prompt_count=prompts,
        execution_count=execs,
        reflection_count=reflections,
    )
