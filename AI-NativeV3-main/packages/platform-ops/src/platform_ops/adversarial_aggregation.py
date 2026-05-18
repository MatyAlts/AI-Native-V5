"""Agregación de eventos adversos por cohorte (ADR-019, RN-129).

Función pura sobre lista de eventos `intento_adverso_detectado` (cada uno
ya con `category, severity, student_pseudonym, matched_text, ts, pattern_id`)
que produce el output del endpoint `/cohort/{id}/adversarial-events`.

Diseño: separar la agregación pura del fetching cross-DB. La función vive
en platform-ops, testeable sin DB con mocks. El endpoint en
analytics-service llama `RealLongitudinalDataSource.list_adversarial_events_by_comision`
y le pasa el resultado a esta función.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

# Limite de matched_text en el output (defensa contra payloads gigantes)
_MAX_MATCHED_TEXT_OUTPUT = 200

# Cuantos top students mostrar
_TOP_STUDENTS_LIMIT = 10


def aggregate_adversarial_events(events: list[dict[str, Any]]) -> dict[str, Any]:
    """Construye el output del endpoint `/cohort/{id}/adversarial-events`.

    Args:
        events: lista de dicts con keys: `episode_id`, `student_pseudonym`, `ts`,
            `category`, `severity`, `pattern_id`, `matched_text`,
            `guardrails_corpus_hash`. Asume eventos ya filtrados por comisión
            y por `event_type='intento_adverso_detectado'`. El caller los
            obtiene de `RealLongitudinalDataSource.list_adversarial_events_by_comision`.

    Returns:
        Dict con:
            - `n_events_total`: int.
            - `counts_by_category`: {category: count}.
            - `counts_by_severity`: {"1": n, "2": n, ..., "5": n}.
            - `counts_by_student`: {student_pseudonym: count}.
            - `top_students_by_n_events`: [{student_pseudonym, n_events}], top 10.
            - `recent_events`: lista de los más recientes (asume input ya ordenado
              desc por ts; si no, se reordena defensivamente). matched_text
              truncado a 200 chars.

    Función pura, idempotente.
    """
    if not events:
        return {
            "n_events_total": 0,
            "counts_by_category": {},
            "counts_by_severity": {str(s): 0 for s in range(1, 6)},
            "counts_by_student": {},
            "top_students_by_n_events": [],
            "recent_events": [],
        }

    counts_by_category: Counter[str] = Counter()
    counts_by_severity: Counter[str] = Counter()
    counts_by_student: Counter[str] = Counter()

    for ev in events:
        counts_by_category[ev.get("category", "unknown")] += 1
        sev = ev.get("severity", 0)
        counts_by_severity[str(sev)] += 1
        counts_by_student[ev.get("student_pseudonym", "unknown")] += 1

    # Top students por count
    top_students = [
        {"student_pseudonym": alias, "n_events": count}
        for alias, count in counts_by_student.most_common(_TOP_STUDENTS_LIMIT)
    ]

    # Severity buckets fijos 1..5 (incluso si no hay eventos en algunos)
    severity_full = {str(s): counts_by_severity.get(str(s), 0) for s in range(1, 6)}

    # Recent events con matched_text truncado defensivamente
    sorted_events = sorted(
        events,
        key=lambda e: e.get("ts") or "",
        reverse=True,
    )
    recent = []
    for ev in sorted_events[:50]:
        matched = ev.get("matched_text", "")
        if len(matched) > _MAX_MATCHED_TEXT_OUTPUT:
            matched = matched[:_MAX_MATCHED_TEXT_OUTPUT] + "..."
        recent.append(
            {
                "episode_id": ev.get("episode_id", ""),
                "student_pseudonym": ev.get("student_pseudonym", ""),
                "ts": ev.get("ts", ""),
                "category": ev.get("category", "unknown"),
                "severity": int(ev.get("severity", 0)),
                "pattern_id": ev.get("pattern_id", ""),
                "matched_text": matched,
            }
        )

    return {
        "n_events_total": len(events),
        "counts_by_category": dict(counts_by_category),
        "counts_by_severity": severity_full,
        "counts_by_student": dict(counts_by_student),
        "top_students_by_n_events": top_students,
        "recent_events": recent,
    }
