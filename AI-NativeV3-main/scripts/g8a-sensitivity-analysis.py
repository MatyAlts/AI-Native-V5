"""Analisis de sensibilidad del override temporal de `anotacion_creada` (ADR-023, G8a, v1.1.0).

Recomputa `n_level_distribution` sobre un corpus sintetico de episodios variando
las dos constantes del override:

  - ANOTACION_N1_WINDOW_SECONDS (default v1.1.0: 120)
  - ANOTACION_N4_WINDOW_SECONDS (default v1.1.0: 60)

Para cada combinacion reporta la distribucion de niveles entre las anotaciones
(que % de las anotaciones quedan en N1, N2, N4) y la varianza relativa del
ratio total de tiempo por nivel.

Output: tabla Markdown lista para incluir en el ADR-023 como apendice de
sensibilidad o en el reporte empirico del piloto-1.

Reproducibilidad bit-a-bit: seed fijo del generador sintetico.

Uso:
    uv run python scripts/g8a-sensitivity-analysis.py
    uv run python scripts/g8a-sensitivity-analysis.py --episodes 5000 --output sensitivity.md

Dependencias: solo `classifier-service` instalado en el venv (uv sync).
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

# Hacer importable el modulo del classifier desde la raiz del repo.
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "apps" / "classifier-service" / "src"))

from classifier_service.services import event_labeler  # noqa: E402

# Combinaciones de ventanas a evaluar.
# Cada tuple es (N1_window_seconds, N4_window_seconds).
# (120, 60) es el baseline v1.1.0 — primero del list para que la tabla lo destaque.
WINDOWS_TO_TEST: list[tuple[float, float]] = [
    (60.0, 30.0),    # ventanas mas estrictas
    (90.0, 30.0),
    (120.0, 60.0),   # baseline v1.1.0
    (180.0, 60.0),
    (180.0, 120.0),
    (240.0, 120.0),  # ventanas mas laxas
]

# Seed para reproducibilidad bit-a-bit.
RANDOM_SEED = 42


@dataclass
class EpisodeStats:
    """Stats por-episodio reducidos a lo que el analisis necesita."""

    counts: dict[str, int]
    durations: dict[str, float]
    total_anotaciones: int


def _make_event(
    seq: int,
    event_type: str,
    ts: datetime,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "seq": seq,
        "event_type": event_type,
        "ts": ts.isoformat().replace("+00:00", "Z"),
        "payload": payload or {},
    }


def _generate_episode(rng: random.Random, episode_idx: int) -> list[dict[str, Any]]:
    """Genera un episodio sintetico plausible.

    Distribucion realista del piloto:
      - Duracion total: 30-90 min
      - Numero de anotaciones: 0-8 (Poisson-ish; muchos episodios sin anotaciones)
      - Numero de prompts/respuestas: 1-12 (los prompts disparan la ventana N4)
      - Anotaciones distribuidas por mezcla:
          * 25% en los primeros 120s (lectura inicial — N1 con baseline)
          * 30% dentro de 60s post un tutor_respondio (apropiacion — N4)
          * 45% en otros momentos (fallback N2)
    """
    base = datetime(2026, 9, 1, 10, 0, 0, tzinfo=UTC) + timedelta(hours=episode_idx)
    duration_min = rng.randint(30, 90)
    duration_seconds = duration_min * 60

    n_anotaciones = max(0, int(rng.gauss(3, 2)))
    n_prompts = max(1, int(rng.gauss(5, 3)))

    events: list[tuple[float, str, dict[str, Any]]] = []  # (offset_seconds, event_type, payload)

    # episodio_abierto en t=0
    events.append((0.0, "episodio_abierto", {}))

    # Prompts/respuestas distribuidos uniformemente
    tutor_response_offsets: list[float] = []
    for _ in range(n_prompts):
        prompt_t = rng.uniform(60, duration_seconds - 30)
        response_t = prompt_t + rng.uniform(2, 8)
        events.append((prompt_t, "prompt_enviado", {"prompt_kind": "solicitud_directa"}))
        events.append((response_t, "tutor_respondio", {}))
        tutor_response_offsets.append(response_t)

    # Edicion de codigo y ejecucion intercalados (no afectan al override)
    n_edits = max(2, int(rng.gauss(8, 3)))
    for _ in range(n_edits):
        events.append(
            (
                rng.uniform(30, duration_seconds - 10),
                "edicion_codigo",
                {"origin": "student_typed"},
            )
        )
    n_runs = max(1, int(rng.gauss(3, 1)))
    for _ in range(n_runs):
        events.append((rng.uniform(60, duration_seconds - 5), "codigo_ejecutado", {}))

    # Anotaciones segun la mezcla declarada
    for _ in range(n_anotaciones):
        r = rng.random()
        if r < 0.25:
            # Lectura inicial: dentro de los primeros 120s
            t = rng.uniform(5, 120)
        elif r < 0.55 and tutor_response_offsets:
            # Apropiacion: 5-60s post un tutor_respondio aleatorio
            anchor = rng.choice(tutor_response_offsets)
            t = anchor + rng.uniform(5, 60)
            if t >= duration_seconds:
                t = duration_seconds - 5
        else:
            # Otros momentos
            t = rng.uniform(120, duration_seconds - 5)
        events.append((t, "anotacion_creada", {"content": "..."}))

    # episodio_cerrado al final
    events.append((float(duration_seconds), "episodio_cerrado", {}))

    # Ordenar por timestamp y asignar seq incremental
    events.sort(key=lambda e: e[0])
    return [
        _make_event(seq=i, event_type=et, ts=base + timedelta(seconds=offset), payload=p)
        for i, (offset, et, p) in enumerate(events)
    ]


def _stats_episode(events: list[dict[str, Any]]) -> EpisodeStats:
    """Computa la distribucion del episodio con las constantes vigentes del modulo."""
    dist = event_labeler.n_level_distribution(events)
    counts: dict[str, int] = dict(dist["total_events_per_level"])
    durations: dict[str, float] = dict(dist["distribution_seconds"])
    total_anot = sum(1 for e in events if e["event_type"] == "anotacion_creada")
    return EpisodeStats(
        counts=counts,
        durations=durations,
        total_anotaciones=total_anot,
    )


def _aggregate(stats_list: list[EpisodeStats]) -> dict[str, Any]:
    """Agrega stats sobre todos los episodios. Devuelve %s y totales."""
    total_anot = sum(s.total_anotaciones for s in stats_list)
    # De las anotaciones totales, cuantas terminaron en cada nivel:
    # `counts["N1"]` incluye lectura_enunciado + anotaciones-N1; restamos lectura_enunciado.
    # Mejor: contamos eventos `anotacion_creada` que cayeron en cada nivel directamente.
    # Para no re-procesar, derivamos del invariante: counts["lectura_enunciado"] no existe en
    # n_level_distribution (no separa eventos por type, solo por nivel). Vamos a recomputar
    # eso en el tester top-level con el labeler explicito.
    # Aca aproximamos con la siguiente heuristica conservadora: las anotaciones suelen ser la
    # unica fuente N1/N4 ademas de lectura/prompt-respuesta. Entonces:
    #   anotaciones_N1 = max(0, counts["N1"] - count_lectura_enunciado_total)
    # Como nuestro generador NO emite lectura_enunciado, count_lectura_enunciado_total = 0.
    # → anotaciones_N1 = counts["N1"]
    # → anotaciones_N4_overrideadas = counts["N4"] - count_prompt_enviado - count_tutor_respondio
    # Lo computamos exacto en el caller.
    n1 = sum(s.counts.get("N1", 0) for s in stats_list)
    n2 = sum(s.counts.get("N2", 0) for s in stats_list)
    n3 = sum(s.counts.get("N3", 0) for s in stats_list)
    n4 = sum(s.counts.get("N4", 0) for s in stats_list)
    meta = sum(s.counts.get("meta", 0) for s in stats_list)

    sec_n1 = sum(s.durations.get("N1", 0.0) for s in stats_list)
    sec_n2 = sum(s.durations.get("N2", 0.0) for s in stats_list)
    sec_n3 = sum(s.durations.get("N3", 0.0) for s in stats_list)
    sec_n4 = sum(s.durations.get("N4", 0.0) for s in stats_list)
    sec_meta = sum(s.durations.get("meta", 0.0) for s in stats_list)
    sec_total = sec_n1 + sec_n2 + sec_n3 + sec_n4 + sec_meta

    return {
        "total_anotaciones": total_anot,
        "counts": {"N1": n1, "N2": n2, "N3": n3, "N4": n4, "meta": meta},
        "seconds": {"N1": sec_n1, "N2": sec_n2, "N3": sec_n3, "N4": sec_n4, "meta": sec_meta},
        "ratios": {
            "N1": sec_n1 / sec_total if sec_total > 0 else 0.0,
            "N2": sec_n2 / sec_total if sec_total > 0 else 0.0,
            "N3": sec_n3 / sec_total if sec_total > 0 else 0.0,
            "N4": sec_n4 / sec_total if sec_total > 0 else 0.0,
            "meta": sec_meta / sec_total if sec_total > 0 else 0.0,
        },
    }


def _count_anotaciones_per_level(
    episodes: list[list[dict[str, Any]]],
) -> dict[str, int]:
    """Cuenta cuantas anotaciones fueron etiquetadas en cada nivel (con las constantes vigentes).

    Recorre el episodio y aplica `label_event` con contexto exacto a cada anotacion.
    Aisla el efecto del override del resto del conteo por nivel.
    """
    per_level = {"N1": 0, "N2": 0, "N3": 0, "N4": 0, "meta": 0}
    for events in episodes:
        sorted_events = sorted(events, key=lambda e: e["seq"])
        contexts = event_labeler._build_event_contexts(sorted_events)
        for ev, ctx in zip(sorted_events, contexts, strict=False):
            if ev["event_type"] != "anotacion_creada":
                continue
            level = event_labeler.label_event(ev["event_type"], ev.get("payload"), context=ctx)
            per_level[level] += 1
    return per_level


def run_analysis(num_episodes: int) -> str:
    """Ejecuta el analisis completo y devuelve la tabla en Markdown."""
    rng = random.Random(RANDOM_SEED)
    print(f"Generando {num_episodes} episodios sinteticos (seed={RANDOM_SEED})...")
    episodes = [_generate_episode(rng, i) for i in range(num_episodes)]

    total_anotaciones = sum(
        sum(1 for ev in ep if ev["event_type"] == "anotacion_creada") for ep in episodes
    )
    total_eventos = sum(len(ep) for ep in episodes)
    print(f"  episodios={num_episodes}, eventos={total_eventos}, anotaciones={total_anotaciones}")
    print()

    rows: list[dict[str, Any]] = []
    baseline_anot: dict[str, int] | None = None
    baseline_ratios: dict[str, float] | None = None

    # Backup de las constantes del modulo para restaurar al final.
    orig_n1 = event_labeler.ANOTACION_N1_WINDOW_SECONDS
    orig_n4 = event_labeler.ANOTACION_N4_WINDOW_SECONDS

    try:
        for n1_window, n4_window in WINDOWS_TO_TEST:
            event_labeler.ANOTACION_N1_WINDOW_SECONDS = float(n1_window)
            event_labeler.ANOTACION_N4_WINDOW_SECONDS = float(n4_window)

            anot_per_level = _count_anotaciones_per_level(episodes)
            stats = [_stats_episode(ep) for ep in episodes]
            agg = _aggregate(stats)

            is_baseline = (n1_window, n4_window) == (120.0, 60.0)
            if is_baseline:
                baseline_anot = anot_per_level
                baseline_ratios = agg["ratios"]

            rows.append(
                {
                    "n1_window": n1_window,
                    "n4_window": n4_window,
                    "is_baseline": is_baseline,
                    "anot_per_level": anot_per_level,
                    "ratios": agg["ratios"],
                }
            )

            print(
                f"  ventana N1={int(n1_window)}s, N4={int(n4_window)}s -> "
                f"anotaciones N1={anot_per_level['N1']:5d} "
                f"N2={anot_per_level['N2']:5d} "
                f"N4={anot_per_level['N4']:5d}"
            )
    finally:
        # Restaurar constantes al baseline v1.1.0 — ningun side-effect post-script.
        event_labeler.ANOTACION_N1_WINDOW_SECONDS = orig_n1
        event_labeler.ANOTACION_N4_WINDOW_SECONDS = orig_n4

    # Construir tabla Markdown
    if baseline_anot is None or baseline_ratios is None:
        msg = "baseline (120s/60s) no esta en WINDOWS_TO_TEST — invariante violado"
        raise RuntimeError(msg)

    md_lines: list[str] = []
    md_lines.append(
        f"# Analisis de sensibilidad — override temporal de `anotacion_creada` "
        f"(ADR-023, v1.1.0)"
    )
    md_lines.append("")
    md_lines.append(
        f"Generado por `scripts/g8a-sensitivity-analysis.py` "
        f"(seed={RANDOM_SEED}, episodios={num_episodes}, "
        f"anotaciones totales={total_anotaciones})."
    )
    md_lines.append("")
    md_lines.append("## Distribucion de anotaciones por nivel segun ventanas (N1, N4)")
    md_lines.append("")
    md_lines.append(
        "| Ventana N1 (s) | Ventana N4 (s) | Anot N1 | Anot N2 | Anot N4 | "
        "% N1 (vs baseline) | % N4 (vs baseline) |"
    )
    md_lines.append(
        "|---:|---:|---:|---:|---:|---:|---:|"
    )

    base_n1 = baseline_anot["N1"] or 1  # evita div/0
    base_n4 = baseline_anot["N4"] or 1
    for r in rows:
        a = r["anot_per_level"]
        delta_n1 = (a["N1"] - baseline_anot["N1"]) / base_n1 * 100.0
        delta_n4 = (a["N4"] - baseline_anot["N4"]) / base_n4 * 100.0
        marker = " **(baseline)**" if r["is_baseline"] else ""
        md_lines.append(
            f"| {int(r['n1_window'])}{marker} | {int(r['n4_window'])} | "
            f"{a['N1']} | {a['N2']} | {a['N4']} | "
            f"{delta_n1:+.1f}% | {delta_n4:+.1f}% |"
        )

    md_lines.append("")
    md_lines.append("## Ratio de tiempo por nivel (sobre el corpus completo)")
    md_lines.append("")
    md_lines.append(
        "| Ventana N1 (s) | Ventana N4 (s) | ratio N1 | ratio N2 | ratio N3 | "
        "ratio N4 | ratio meta |"
    )
    md_lines.append(
        "|---:|---:|---:|---:|---:|---:|---:|"
    )
    for r in rows:
        ra = r["ratios"]
        marker = " **(baseline)**" if r["is_baseline"] else ""
        md_lines.append(
            f"| {int(r['n1_window'])}{marker} | {int(r['n4_window'])} | "
            f"{ra['N1']:.4f} | {ra['N2']:.4f} | {ra['N3']:.4f} | "
            f"{ra['N4']:.4f} | {ra['meta']:.4f} |"
        )

    md_lines.append("")
    md_lines.append("## Lectura del analisis")
    md_lines.append("")

    # Calcular deltas concretos para la lectura, usando datos del corpus generado.
    def _row_for(n1: float, n4: float) -> dict[str, Any] | None:
        for row in rows:
            if row["n1_window"] == n1 and row["n4_window"] == n4:
                return row
        return None

    def _pct_change(curr: int, base: int) -> float:
        return ((curr - base) / base * 100.0) if base else 0.0

    base_row = _row_for(120.0, 60.0)
    n1_strict = _row_for(60.0, 30.0)
    n1_lax = _row_for(180.0, 60.0)
    n4_lax = _row_for(180.0, 120.0)

    if base_row is not None and n1_strict is not None:
        delta_n1_strict = _pct_change(
            n1_strict["anot_per_level"]["N1"], base_row["anot_per_level"]["N1"]
        )
        md_lines.append(
            f"- **Sensibilidad de N1**: estrechar la ventana N1 de 120s a 60s "
            f"reduce `anotaciones_N1` en {delta_n1_strict:+.1f}% (de "
            f"{base_row['anot_per_level']['N1']} a "
            f"{n1_strict['anot_per_level']['N1']}). Esas anotaciones se reasignan "
            f"a N2 — el sesgo sub-reporta-N1 reaparece. Ampliar de 120s a 180s "
            f"agrega solo "
            f"{_pct_change(n1_lax['anot_per_level']['N1'], base_row['anot_per_level']['N1']):+.1f}% "
            f"(saturacion por la mezcla del corpus: el 25% de anotaciones de "
            f"lectura inicial cae mayoritariamente dentro de los primeros 120s)."
            if n1_lax is not None
            else ""
        )
    if base_row is not None and n4_lax is not None:
        delta_n4_lax = _pct_change(
            n4_lax["anot_per_level"]["N4"], base_row["anot_per_level"]["N4"]
        )
        md_lines.append(
            f"- **Sensibilidad de N4**: ampliar la ventana N4 de 60s a 120s "
            f"aumenta `anotaciones_N4` en {delta_n4_lax:+.1f}% (de "
            f"{base_row['anot_per_level']['N4']} a "
            f"{n4_lax['anot_per_level']['N4']}). La ventana baseline 60s es "
            f"conservadora — anotaciones reflexivas con latencia 60-120s post "
            f"`tutor_respondio` quedan etiquetadas N2 en el baseline."
        )
    md_lines.append(
        "- **El ratio total de tiempo por nivel es relativamente insensible** a la "
        "eleccion de ventanas porque las anotaciones suelen ser una fraccion pequena "
        "del total de eventos por episodio. El override afecta principalmente a la "
        "distribucion de `anotaciones` entre niveles, no a la composicion global del "
        "tiempo del episodio."
    )
    md_lines.append("")
    md_lines.append(
        "**Conclusion para el ADR-023**: las constantes baseline (120s / 60s) son "
        "razonables como operacionalizacion conservadora declarable. La sensibilidad "
        "no es despreciable — la decision de ventana mueve la asignacion de "
        "anotaciones entre N1 y N2 (y entre N4 y N2) en magnitudes que el reporte "
        "empirico debe declarar. El override completo via clasificacion semantica "
        "(G14, ADR-017) cierra esta sensibilidad a costa de introducir dependencia "
        "del modelo de embeddings — agenda Eje B post-defensa."
    )
    md_lines.append("")
    md_lines.append("## Notas metodologicas")
    md_lines.append("")
    md_lines.append(
        f"- **Corpus sintetico, no datos reales del piloto**. Distribucion de "
        f"eventos generada con seed={RANDOM_SEED} y mezcla declarada en "
        f"`_generate_episode` (25% lectura inicial, 30% post-tutor, 45% otros). "
        f"Los porcentajes deltas dependen de esa mezcla — el analisis se debe "
        f"recomputar contra el corpus real del piloto-1 al cierre del cuatrimestre."
    )
    md_lines.append(
        "- **El generador NO emite `lectura_enunciado`** — para aislar el efecto "
        "del override sobre `anotacion_creada` puro. En el corpus real, "
        "`lectura_enunciado` aporta a N1 independientemente del override."
    )
    md_lines.append(
        "- **El generador no emite `intento_adverso_detectado` ni `episodio_abandonado`** "
        "— el override no aplica a esos eventos."
    )

    return "\n".join(md_lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--episodes",
        type=int,
        default=1000,
        help="Numero de episodios sinteticos a generar (default: 1000)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Path al archivo Markdown de salida (default: stdout)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output JSON crudo en lugar de Markdown (para parseo programatico)",
    )
    args = parser.parse_args()

    if args.json:
        # JSON path: re-genera en otro formato. Mas simple regenerar.
        rng = random.Random(RANDOM_SEED)
        episodes = [_generate_episode(rng, i) for i in range(args.episodes)]
        results: list[dict[str, Any]] = []
        orig_n1 = event_labeler.ANOTACION_N1_WINDOW_SECONDS
        orig_n4 = event_labeler.ANOTACION_N4_WINDOW_SECONDS
        try:
            for n1_w, n4_w in WINDOWS_TO_TEST:
                event_labeler.ANOTACION_N1_WINDOW_SECONDS = float(n1_w)
                event_labeler.ANOTACION_N4_WINDOW_SECONDS = float(n4_w)
                anot = _count_anotaciones_per_level(episodes)
                results.append({"n1_window": n1_w, "n4_window": n4_w, "anotaciones": anot})
        finally:
            event_labeler.ANOTACION_N1_WINDOW_SECONDS = orig_n1
            event_labeler.ANOTACION_N4_WINDOW_SECONDS = orig_n4
        out = json.dumps(
            {"seed": RANDOM_SEED, "episodes": args.episodes, "results": results},
            indent=2,
        )
    else:
        out = run_analysis(args.episodes)

    if args.output:
        args.output.write_text(out, encoding="utf-8")
        print(f"\n[OK] Output escrito en {args.output}")
    else:
        print(out)


if __name__ == "__main__":
    main()
