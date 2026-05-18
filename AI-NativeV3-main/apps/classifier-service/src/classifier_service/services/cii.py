"""Coherencia Inter-Iteración (CII).

Definición operacional:
  Cada "iteración" es una secuencia (prompt → ejecución → reflexión).

  - cii_stability: estabilidad de enfoque entre iteraciones.
    Alta si el estudiante profundiza en el mismo tema;
    baja si salta de tema.
    Proxy simple: similitud textual (overlap de tokens) entre prompts
    consecutivos.

  - cii_evolution: evolución de calidad.
    Proxy simple: longitud media de los prompts a lo largo del episodio.
    Aumenta → el estudiante desarrolla pensamiento más elaborado.
    Decrece → puede indicar frustración o delegación creciente.

Ambas se reportan en [0, 1].
"""

from __future__ import annotations

import itertools
from typing import Any


def compute_cii(events: list[dict]) -> dict[str, Any]:
    """Calcula cii_stability y cii_evolution."""
    prompts = [
        e for e in sorted(events, key=lambda x: x["seq"]) if e["event_type"] == "prompt_enviado"
    ]

    if len(prompts) < 2:
        return {
            "cii_stability": 0.5,
            "cii_evolution": 0.5,
            "iterations": len(prompts),
            "insufficient_data": True,
        }

    contents = [(p.get("payload") or {}).get("content", "") for p in prompts]

    # Stability: similitud media entre prompts consecutivos
    similarities = []
    for a, b in itertools.pairwise(contents):
        sim = _jaccard_tokens(a, b)
        similarities.append(sim)
    stability = sum(similarities) / len(similarities) if similarities else 0.0

    # Evolution: ¿crece la longitud/complejidad?
    lengths = [len(c.split()) for c in contents if c]
    if len(lengths) < 2:
        evolution = 0.5
    else:
        # Regresión simple: slope normalizada
        n = len(lengths)
        xs = list(range(n))
        mean_x = sum(xs) / n
        mean_y = sum(lengths) / n
        num = sum((xs[i] - mean_x) * (lengths[i] - mean_y) for i in range(n))
        den = sum((xs[i] - mean_x) ** 2 for i in range(n))
        slope = num / den if den > 0 else 0
        # Normalizar: slope 0 → 0.5 (neutral), slope +2 palabras/iter → 1.0
        evolution = max(0.0, min(1.0, 0.5 + slope / 4.0))

    return {
        "cii_stability": stability,
        "cii_evolution": evolution,
        "iterations": len(prompts),
        "similarities": similarities,
        "prompt_lengths": lengths,
    }


def _jaccard_tokens(a: str, b: str) -> float:
    """Similitud Jaccard simple por overlap de palabras (lowercased)."""
    tokens_a = set(a.lower().split())
    tokens_b = set(b.lower().split())
    if not tokens_a and not tokens_b:
        return 1.0
    if not tokens_a or not tokens_b:
        return 0.0
    inter = tokens_a & tokens_b
    union = tokens_a | tokens_b
    return len(inter) / len(union)
