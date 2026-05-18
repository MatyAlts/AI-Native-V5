"""Análisis inter-rater del clasificador N4 vs etiquetado humano.

Cohen's Kappa mide el grado de acuerdo entre dos evaluadores
corrigiendo por el acuerdo esperado por azar. Es el estándar de la
literatura de investigación educativa para validar clasificadores.

Interpretación (Landis & Koch, 1977):
  κ < 0.20   Acuerdo pobre
  0.21–0.40  Acuerdo justo
  0.41–0.60  Acuerdo moderado
  0.61–0.80  Acuerdo sustancial
  0.81–1.00  Acuerdo casi perfecto

Para la tesis: el objetivo es κ ≥ 0.6 (acuerdo sustancial). Si el
clasificador cae por debajo, hay que refinar el árbol de decisión o
los umbrales del reference_profile.

Uso:
    ratings = [
        KappaRating(episode_id=..., rater_a="apropiacion_reflexiva", rater_b="apropiacion_reflexiva"),
        ...
    ]
    result = compute_cohen_kappa(ratings)
    print(f"Kappa = {result.kappa:.3f} ({result.interpretation})")
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field

CATEGORIES = (
    "delegacion_pasiva",
    "apropiacion_superficial",
    "apropiacion_reflexiva",
)


@dataclass
class KappaRating:
    """Un episodio evaluado por dos raters (ej modelo vs humano)."""

    episode_id: str
    rater_a: str  # etiqueta de rater A (ej clasificador automático)
    rater_b: str  # etiqueta de rater B (ej docente humano)


@dataclass
class KappaResult:
    kappa: float
    n_episodes: int
    observed_agreement: float
    expected_agreement: float
    confusion_matrix: dict[str, dict[str, int]] = field(default_factory=dict)
    per_class_agreement: dict[str, float] = field(default_factory=dict)

    @property
    def interpretation(self) -> str:
        k = self.kappa
        if k < 0.20:
            return "pobre"
        if k < 0.41:
            return "justo"
        if k < 0.61:
            return "moderado"
        if k < 0.81:
            return "sustancial"
        return "casi perfecto"


def compute_cohen_kappa(ratings: Sequence[KappaRating]) -> KappaResult:
    """Calcula Cohen's Kappa.

    Fórmula:
        κ = (p_o - p_e) / (1 - p_e)
    donde:
        p_o = proporción de acuerdo observado
        p_e = proporción de acuerdo esperado por azar
              = Σ (p_a(k) * p_b(k)) para cada categoría k

    Raises:
        ValueError si no hay ratings o categorías inválidas.
    """
    n = len(ratings)
    if n == 0:
        raise ValueError("Se necesitan al menos 1 rating para computar Kappa")

    # Validar categorías
    for r in ratings:
        if r.rater_a not in CATEGORIES:
            raise ValueError(f"Categoría inválida en rater_a: {r.rater_a}")
        if r.rater_b not in CATEGORIES:
            raise ValueError(f"Categoría inválida en rater_b: {r.rater_b}")

    # 1. Matriz de confusión (filas = rater_a, cols = rater_b)
    confusion: dict[str, dict[str, int]] = {c: dict.fromkeys(CATEGORIES, 0) for c in CATEGORIES}
    for r in ratings:
        confusion[r.rater_a][r.rater_b] += 1

    # 2. Acuerdo observado: diagonal / n
    diagonal = sum(confusion[c][c] for c in CATEGORIES)
    p_o = diagonal / n

    # 3. Marginales
    marg_a = Counter(r.rater_a for r in ratings)
    marg_b = Counter(r.rater_b for r in ratings)

    # 4. Acuerdo esperado por azar
    p_e = sum((marg_a[c] / n) * (marg_b[c] / n) for c in CATEGORIES)

    # 5. Kappa
    if p_e == 1.0:
        # Si todos los ratings son de una sola categoría en ambos raters,
        # Kappa no está definido. Convencionalmente lo reportamos como 1.0.
        kappa = 1.0
    else:
        kappa = (p_o - p_e) / (1 - p_e)

    # 6. Acuerdo por clase (útil para diagnóstico)
    per_class: dict[str, float] = {}
    for c in CATEGORIES:
        n_c = marg_a[c] + marg_b[c]
        if n_c == 0:
            per_class[c] = 0.0
            continue
        agree_c = 2 * confusion[c][c]  # contado en ambos sentidos
        per_class[c] = agree_c / n_c

    return KappaResult(
        kappa=round(kappa, 4),
        n_episodes=n,
        observed_agreement=round(p_o, 4),
        expected_agreement=round(p_e, 4),
        confusion_matrix=confusion,
        per_class_agreement={k: round(v, 4) for k, v in per_class.items()},
    )


def format_report(result: KappaResult) -> str:
    """Reporte legible para humanos."""
    lines = [
        f"Cohen's Kappa (n = {result.n_episodes})",
        "",
        f"  κ = {result.kappa:.4f}  ({result.interpretation})",
        f"  Acuerdo observado: {result.observed_agreement:.4f}",
        f"  Acuerdo esperado por azar: {result.expected_agreement:.4f}",
        "",
        "Acuerdo por clase:",
    ]
    for c, pct in sorted(result.per_class_agreement.items()):
        lines.append(f"  {c}: {pct:.4f}")

    lines.append("")
    lines.append("Matriz de confusión (rater_a × rater_b):")
    header = "                           | " + " | ".join(f"{c:>15}" for c in CATEGORIES)
    lines.append(header)
    lines.append("-" * len(header))
    for c in CATEGORIES:
        row = f"  {c:>25} | " + " | ".join(
            f"{result.confusion_matrix[c][cc]:>15}" for cc in CATEGORIES
        )
        lines.append(row)

    return "\n".join(lines)
