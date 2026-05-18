"""Análisis de sensibilidad de las cinco coherencias y el árbol de decisión (CS04).

Origen: plan1Socra.md CS04 (P0, antes de defensa). Recorre las 106 classifications
históricas re-clasificadas (post-A1) variando las constantes operacionales
del clasificador y reporta qué fracción de las clasificaciones cambia de
categoría con cada variación.

BLOQUEO CRÍTICO — NO EJECUTAR ANTES DE A1
=========================================
Este script depende de:
  1. **A1 cerrado**: las 106 classifications históricas re-clasificadas con
     `classifier_config_hash` actual (post-LABELER_VERSION 1.2.0). Sin A1,
     el script opera sobre corpus con hash legacy y los resultados no son
     comparables con el sistema vigente.
  2. **Acceso a la DB real del piloto**: las classifications viven en
     `classifier_db.classifications`. El script asume conexión configurada
     via `CLASSIFIER_DB_URL`.

Ejecutar SOLO cuando A1 esté cerrado y verificado. Documentación en
`docs/research/manual-etiquetador-N4.md` §3 y plan1Socra.md §6 DAG.

Salida esperada
---------------
1. `sensitivity-ct-pause-threshold.csv` — variaciones de PAUSE_THRESHOLD
   (CT) en {3, 4, 5, 6, 8, 10} minutos. Columnas: threshold_min,
   n_classifications_changed, fraction_changed, transitions_summary.
2. `sensitivity-ccd-correlation-window.csv` — variaciones de
   CORRELATION_WINDOW (CCD) en {1, 2, 3, 5} minutos. Mismo formato.
3. `sensitivity-tree-thresholds.csv` — variaciones de los umbrales del
   árbol (`ct_high`, `ccd_orphan_high`, `ccd_mean_low`, `cii_stability_low`,
   `cii_evolution_low`) en ±20%. Mismo formato.
4. `sensitivity-report.md` — reporte agregado con conclusiones.

El reporte final va al Anexo C del paper (`paper-draft.md` Anexo C — pendiente).

Uso
---
```bash
export CLASSIFIER_DB_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/classifier_db
uv run python scripts/sensitivity-analysis-cognitive-coherences.py \\
    --output-dir docs/research/sensitivity-2026-05-XX/
```

Funciones puras del análisis
============================
La lógica de variación de constantes se importa del classifier sin modificarlo:
  - `classifier_service.services.ct.compute_ct_summary` (PAUSE_THRESHOLD)
  - `classifier_service.services.ccd.compute_ccd` (CORRELATION_WINDOW)
  - `classifier_service.services.tree.classify` (DEFAULT_REFERENCE_PROFILE.thresholds)

El script monkey-patcha las constantes para cada corrida sin alterar el código
del classifier-service. Esto preserva la reproducibilidad del clasificador
en runtime.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

# Estructura de cada corrida de sensibilidad. Pura, sin DB.


@dataclass(frozen=True)
class SensitivityRunInput:
    """Configuración de una corrida de sensibilidad."""

    name: str  # ej. "pause_threshold_5min"
    parameter_path: str  # ej. "ct.PAUSE_THRESHOLD"
    parameter_value: Any  # valor numérico o timedelta
    baseline_value: Any  # valor original


@dataclass(frozen=True)
class SensitivityRunOutput:
    """Resultado de una corrida sobre las 106 históricas."""

    run_input: SensitivityRunInput
    n_classifications_total: int
    n_classifications_changed: int
    fraction_changed: float
    transitions: dict[str, int]  # ej. {"reflexiva->superficial": 7, ...}


def _variar_ct_pause_threshold() -> list[SensitivityRunInput]:
    """Genera las corridas para PAUSE_THRESHOLD de CT."""
    from datetime import timedelta

    baseline = timedelta(minutes=5)
    return [
        SensitivityRunInput(
            name=f"pause_threshold_{m}min",
            parameter_path="ct.PAUSE_THRESHOLD",
            parameter_value=timedelta(minutes=m),
            baseline_value=baseline,
        )
        for m in [3, 4, 5, 6, 8, 10]
    ]


def _variar_ccd_correlation_window() -> list[SensitivityRunInput]:
    """Genera las corridas para CORRELATION_WINDOW de CCD."""
    from datetime import timedelta

    baseline = timedelta(minutes=2)
    return [
        SensitivityRunInput(
            name=f"correlation_window_{m}min",
            parameter_path="ccd.CORRELATION_WINDOW",
            parameter_value=timedelta(minutes=m),
            baseline_value=baseline,
        )
        for m in [1, 2, 3, 5]
    ]


def _variar_tree_thresholds() -> list[SensitivityRunInput]:
    """Genera las corridas para los umbrales del árbol (±20%)."""
    baseline_profile = {
        "ct_low": 0.35,
        "ct_high": 0.65,
        "ccd_orphan_high": 0.5,
        "ccd_mean_low": 0.35,
        "cii_stability_low": 0.2,
        "cii_evolution_low": 0.3,
    }
    runs = []
    for key, baseline_value in baseline_profile.items():
        for variation in [-0.2, -0.1, +0.1, +0.2]:
            new_value = baseline_value * (1 + variation)
            new_value = max(0.0, min(1.0, new_value))
            runs.append(
                SensitivityRunInput(
                    name=f"tree_{key}_{int(variation*100):+d}pct",
                    parameter_path=f"tree.DEFAULT_REFERENCE_PROFILE.thresholds.{key}",
                    parameter_value=new_value,
                    baseline_value=baseline_value,
                )
            )
    return runs


def all_sensitivity_runs() -> list[SensitivityRunInput]:
    """Devuelve todas las corridas planificadas (16 + 4 + 24 = 44)."""
    return (
        _variar_ct_pause_threshold()
        + _variar_ccd_correlation_window()
        + _variar_tree_thresholds()
    )


def _format_transition_key(before: str, after: str) -> str:
    return f"{before}->{after}"


def summarize_transitions(
    baseline_classifications: list[dict[str, Any]],
    varied_classifications: list[dict[str, Any]],
) -> tuple[int, dict[str, int]]:
    """Compara baseline vs varied y devuelve (n_changed, transitions_dict).

    Asume mismos episodios en mismo orden. Cada classification es dict
    con al menos `episode_id` y `appropriation`.
    """
    if len(baseline_classifications) != len(varied_classifications):
        raise ValueError(
            f"Mismatch: {len(baseline_classifications)} vs {len(varied_classifications)}"
        )

    n_changed = 0
    transitions: dict[str, int] = {}
    for base, varied in zip(baseline_classifications, varied_classifications):
        if base["episode_id"] != varied["episode_id"]:
            raise ValueError(
                f"Episode order mismatch: {base['episode_id']} vs {varied['episode_id']}"
            )
        if base["appropriation"] != varied["appropriation"]:
            n_changed += 1
            key = _format_transition_key(base["appropriation"], varied["appropriation"])
            transitions[key] = transitions.get(key, 0) + 1
    return n_changed, transitions


def write_csv_report(runs: list[SensitivityRunOutput], output_path: Path) -> None:
    """Escribe CSV con resumen por corrida."""
    with open(output_path, "w", newline="", encoding="utf-8") as fp:
        writer = csv.writer(fp)
        writer.writerow(
            [
                "run_name",
                "parameter_path",
                "parameter_value",
                "baseline_value",
                "n_total",
                "n_changed",
                "fraction_changed",
                "transitions_json",
            ]
        )
        for run in runs:
            writer.writerow(
                [
                    run.run_input.name,
                    run.run_input.parameter_path,
                    str(run.run_input.parameter_value),
                    str(run.run_input.baseline_value),
                    run.n_classifications_total,
                    run.n_classifications_changed,
                    f"{run.fraction_changed:.4f}",
                    json.dumps(run.transitions, sort_keys=True),
                ]
            )


def main() -> int:
    """Punto de entrada del script.

    BLOQUEADO POR A1 — este `main` levanta NotImplementedError hasta que se
    apruebe la ejecución y se implemente la lectura de las 106 históricas
    desde `classifier_db`. La estructura de funciones puras arriba está
    lista para integrarse cuando A1 cierre.
    """
    parser = argparse.ArgumentParser(description="Análisis de sensibilidad CS04.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="Directorio donde escribir los CSVs y el reporte markdown.",
    )
    parser.add_argument(
        "--db-url",
        type=str,
        default=None,
        help="URL de classifier_db. Por default lee env var CLASSIFIER_DB_URL.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="No conecta a DB ni ejecuta corridas; solo lista las 44 corridas planificadas.",
    )
    args = parser.parse_args()

    if args.dry_run:
        runs = all_sensitivity_runs()
        print(f"Total corridas planificadas: {len(runs)}")
        for run in runs:
            print(f"  - {run.name}: {run.parameter_path} = {run.parameter_value}")
        return 0

    raise NotImplementedError(
        "BLOQUEADO POR A1 (plan1Socra.md CS04). Para ejecutar este script "
        "es necesario que A1 (re-clasificación de las 106 históricas con "
        "classifier_config_hash actual post-LABELER 1.2.0) esté cerrado y "
        "verificado. La lectura desde `classifier_db.classifications` debe "
        "implementarse coordinada con dirección + co-dirección. Estructura "
        "de funciones puras lista en este script (all_sensitivity_runs, "
        "summarize_transitions, write_csv_report). Modo --dry-run lista "
        "las corridas planificadas sin tocar DB."
    )


if __name__ == "__main__":
    sys.exit(main())
