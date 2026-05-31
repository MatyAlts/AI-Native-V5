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

Para la tesis: el objetivo es κ ≥ 0.70 (cómodamente en rango sustancial
Landis-Koch). Decisión vigente por ADR-046 (2026-05-10) alineando código
con el paper. Si el clasificador cae por debajo, hay que refinar el árbol
de decisión o los umbrales del reference_profile.

Uso:
    ratings = [
        KappaRating(episode_id=..., rater_a="apropiacion_reflexiva", rater_b="apropiacion_reflexiva"),
        ...
    ]
    result = compute_cohen_kappa(ratings)
    print(f"Kappa = {result.kappa:.3f} ({result.interpretation})")
"""

from __future__ import annotations

import math
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


def interpret_landis_koch(coefficient: float) -> str:
    """Interpretación cualitativa de un coeficiente de acuerdo (Landis & Koch, 1977).

    Aplica tanto a Cohen's Kappa como a Gwet's AC1 — ambos viven en la misma
    escala [-?, 1] donde 1 = acuerdo perfecto y los mismos cortes cualitativos
    son los que reporta la literatura de fiabilidad inter-rater.
    """
    k = coefficient
    if k < 0.20:
        return "pobre"
    if k < 0.41:
        return "justo"
    if k < 0.61:
        return "moderado"
    if k < 0.81:
        return "sustancial"
    return "casi perfecto"


@dataclass
class KappaResult:
    kappa: float
    n_episodes: int
    observed_agreement: float
    expected_agreement: float
    confusion_matrix: dict[str, dict[str, int]] = field(default_factory=dict)
    per_class_agreement: dict[str, float] = field(default_factory=dict)
    # Gwet's AC1: coeficiente robusto a la asimetría de prevalencia (paradoja de
    # Feinstein & Cicchetti, 1990). Defensa anticipada del paper §VII-A ante un
    # revisor que objete que Cohen's κ es sensible a la prevalencia.
    ac1: float = 0.0
    # Error estándar asintótico de κ y su IC 95% (low, high).
    kappa_se: float = 0.0
    kappa_ci_95: tuple[float, float] = (0.0, 0.0)

    @property
    def interpretation(self) -> str:
        return interpret_landis_koch(self.kappa)

    @property
    def ac1_interpretation(self) -> str:
        return interpret_landis_koch(self.ac1)


def compute_cohen_kappa(
    ratings: Sequence[KappaRating],
    categories: Sequence[str] | None = None,
) -> KappaResult:
    """Calcula Cohen's Kappa.

    Fórmula:
        κ = (p_o - p_e) / (1 - p_e)
    donde:
        p_o = proporción de acuerdo observado
        p_e = proporción de acuerdo esperado por azar
              = Σ (p_a(k) * p_b(k)) para cada categoría k

    Args:
        ratings: pares (rater_a, rater_b) sobre las mismas unidades.
        categories: conjunto de categorías válidas. Si es ``None`` (default)
            usa el módulo-global ``CATEGORIES`` (las 3 categorías de apropiación
            del Protocolo B) — preservando el comportamiento histórico. Pasarlo
            explícito habilita conjuntos arbitrarios (ej. los 4 niveles N1–N4
            del Protocolo A) sin tocar la constante del módulo. El orden se
            normaliza (dedup preservando primer-visto) para que la matriz de
            confusión sea determinista.

    Raises:
        ValueError si no hay ratings o categorías inválidas.
    """
    n = len(ratings)
    if n == 0:
        raise ValueError("Se necesitan al menos 1 rating para computar Kappa")

    # Conjunto de categorías efectivo: el pasado por el caller o el global.
    # Dedup preservando orden de aparición (determinismo de la matriz).
    cats_source = CATEGORIES if categories is None else categories
    cats: tuple[str, ...] = tuple(dict.fromkeys(cats_source))
    cat_set = set(cats)

    # Validar categorías
    for r in ratings:
        if r.rater_a not in cat_set:
            raise ValueError(f"Categoría inválida en rater_a: {r.rater_a}")
        if r.rater_b not in cat_set:
            raise ValueError(f"Categoría inválida en rater_b: {r.rater_b}")

    # 1. Matriz de confusión (filas = rater_a, cols = rater_b)
    confusion: dict[str, dict[str, int]] = {c: dict.fromkeys(cats, 0) for c in cats}
    for r in ratings:
        confusion[r.rater_a][r.rater_b] += 1

    # 2. Acuerdo observado: diagonal / n
    diagonal = sum(confusion[c][c] for c in cats)
    p_o = diagonal / n

    # 3. Marginales
    marg_a = Counter(r.rater_a for r in ratings)
    marg_b = Counter(r.rater_b for r in ratings)

    # 4. Acuerdo esperado por azar
    p_e = sum((marg_a[c] / n) * (marg_b[c] / n) for c in cats)

    # 5. Kappa
    if p_e == 1.0:
        # Si todos los ratings son de una sola categoría en ambos raters,
        # Kappa no está definido. Convencionalmente lo reportamos como 1.0.
        kappa = 1.0
    else:
        kappa = (p_o - p_e) / (1 - p_e)

    # 5b. Gwet's AC1 (Gwet, 2008) — robusto a la asimetría de prevalencia.
    #     π_k = proporción marginal media de la categoría k entre ambos raters
    #         = (marg_a[k] + marg_b[k]) / (2N)
    #     Pe_gwet = 1/(q-1) · Σ_k π_k·(1 - π_k),  q = nº de categorías
    #     AC1 = (p_o - Pe_gwet) / (1 - Pe_gwet)
    ac1 = _compute_ac1(p_o, marg_a, marg_b, n, cats)

    # 5c. IC 95% asintótico para Cohen's κ (ver _kappa_standard_error).
    kappa_se = _kappa_standard_error(confusion, marg_a, marg_b, n, p_o, p_e, cats)
    kappa_ci_95 = (
        round(kappa - 1.96 * kappa_se, 4),
        round(kappa + 1.96 * kappa_se, 4),
    )

    # 6. Acuerdo por clase (útil para diagnóstico)
    per_class: dict[str, float] = {}
    for c in cats:
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
        ac1=round(ac1, 4),
        kappa_se=round(kappa_se, 4),
        kappa_ci_95=kappa_ci_95,
    )


def _compute_ac1(
    p_o: float,
    marg_a: Counter[str],
    marg_b: Counter[str],
    n: int,
    categories: Sequence[str] = CATEGORIES,
) -> float:
    """Gwet's AC1 (Gwet, K. L., 2008, *British Journal of Mathematical and
    Statistical Psychology*, 61(1), 29-48).

    AC1 reemplaza el acuerdo esperado por azar de Cohen (producto de marginales)
    por una estimación robusta a la prevalencia: la probabilidad de que un rater
    asigne una categoría "por azar" se modela como uniforme sobre las categorías
    presentes, ponderada por π_k·(1-π_k). Esto neutraliza la *paradoja de la
    prevalencia* (Feinstein & Cicchetti, 1990) donde p_o alto convive con κ bajo.

        π_k     = (marg_a[k] + marg_b[k]) / (2N)
        Pe_gwet = 1/(q-1) · Σ_k π_k·(1 - π_k)
        AC1     = (p_o - Pe_gwet) / (1 - Pe_gwet)

    Casos borde:
      - q = 1 (una sola categoría observada): no hay riesgo de desacuerdo por
        azar → Pe_gwet := 0 por convención, con lo que AC1 = p_o (que vale 1.0
        cuando todo coincide). Evita la división por (q-1) = 0.
      - Pe_gwet = 1: AC1 := 1.0 (acuerdo perfecto degenerado).
    """
    # q = categorías efectivamente presentes en cualquiera de los dos raters.
    present = [c for c in categories if marg_a[c] + marg_b[c] > 0]
    q = len(present)
    if q <= 1:
        # Una sola categoría en juego: el azar no puede generar desacuerdo.
        return 1.0 if p_o == 1.0 else p_o

    pi = {c: (marg_a[c] + marg_b[c]) / (2 * n) for c in present}
    pe_gwet = sum(pi[c] * (1 - pi[c]) for c in present) / (q - 1)
    if pe_gwet >= 1.0:
        return 1.0
    return (p_o - pe_gwet) / (1 - pe_gwet)


def _kappa_standard_error(
    confusion: dict[str, dict[str, int]],
    marg_a: Counter[str],
    marg_b: Counter[str],
    n: int,
    p_o: float,
    p_e: float,
    categories: Sequence[str] = CATEGORIES,
) -> float:
    """Error estándar asintótico (large-sample) de Cohen's κ.

    Fórmula de Fleiss, Cohen & Everitt (1969), "Large sample standard errors of
    kappa and weighted kappa", *Psychological Bulletin*, 72(5), 323-327 — la
    varianza para κ no ponderado. Notación con proporciones (p_ij = n_ij/N,
    p_i. = marginal fila i, p_.i = marginal columna i):

        var(κ) = 1/(N·(1-p_e)^4) · ( A + B - C )

        A = Σ_i p_ii · [ (1 - p_e) - (p_i. + p_.i)·(1 - p_o) ]^2
        B = (1 - p_o)^2 · Σ_{i≠j} p_ij · (p_.i + p_j.)^2
        C = ( p_o·p_e - 2·p_e + p_o )^2

        SE(κ) = sqrt(var(κ))

    Esta es la SE estándar reportada por SPSS/SAS para el IC de κ. Con
    p_e = 1 (una sola categoría en ambos raters) la varianza es indefinida →
    SE := 0.0 por convención (κ ya se reporta como 1.0).
    """
    if p_e >= 1.0 or n == 0:
        return 0.0

    cats = list(categories)
    # Proporciones marginales.
    pa = {c: marg_a[c] / n for c in cats}  # p_i.  (filas, rater_a)
    pb = {c: marg_b[c] / n for c in cats}  # p_.i  (columnas, rater_b)

    # A: término diagonal.
    a = 0.0
    for c in cats:
        p_ii = confusion[c][c] / n
        a += p_ii * ((1 - p_e) - (pa[c] + pb[c]) * (1 - p_o)) ** 2

    # B: término off-diagonal.
    b = 0.0
    for i in cats:
        for j in cats:
            if i == j:
                continue
            p_ij = confusion[i][j] / n
            b += p_ij * (pb[i] + pa[j]) ** 2
    b *= (1 - p_o) ** 2

    # C: término de corrección.
    c_term = (p_o * p_e - 2 * p_e + p_o) ** 2

    variance = (a + b - c_term) / (n * (1 - p_e) ** 4)
    # Por error de redondeo en datos casi perfectos la varianza puede dar un
    # negativo minúsculo; lo clampeamos a 0 antes de la raíz.
    if variance <= 0.0:
        return 0.0
    return math.sqrt(variance)


def format_report(result: KappaResult) -> str:
    """Reporte legible para humanos."""
    lines = [
        f"Cohen's Kappa (n = {result.n_episodes})",
        "",
        f"  κ = {result.kappa:.4f}  ({result.interpretation})",
        f"  IC 95% de κ: [{result.kappa_ci_95[0]:.4f}, {result.kappa_ci_95[1]:.4f}]  (SE = {result.kappa_se:.4f})",
        f"  Gwet's AC1 = {result.ac1:.4f}  ({result.ac1_interpretation})",
        f"  Acuerdo observado: {result.observed_agreement:.4f}",
        f"  Acuerdo esperado por azar: {result.expected_agreement:.4f}",
        "",
        "Acuerdo por clase:",
    ]
    for c, pct in sorted(result.per_class_agreement.items()):
        lines.append(f"  {c}: {pct:.4f}")

    lines.append("")
    lines.append("Matriz de confusión (rater_a × rater_b):")
    # Las categorías del reporte salen de la propia matriz de confusión (en su
    # orden de inserción), no del módulo-global — así el reporte sirve también
    # para resultados sobre conjuntos de categorías arbitrarios (ej. N1–N4 del
    # Protocolo A).
    cats = list(result.confusion_matrix.keys()) or list(CATEGORIES)
    header = "                           | " + " | ".join(f"{c:>15}" for c in cats)
    lines.append(header)
    lines.append("-" * len(header))
    for c in cats:
        row = f"  {c:>25} | " + " | ".join(
            f"{result.confusion_matrix[c][cc]:>15}" for cc in cats
        )
        lines.append(row)

    return "\n".join(lines)


# ── Protocolo dual de fiabilidad inter-rater (paper §VII-A) ────────────────
#
# El paper define, para CADA protocolo de etiquetado (A: 200 eventos en 4
# niveles N1–N4; B: 50 episodios cerrados en 3 categorías de apropiación), un
# análisis de fiabilidad sobre TRES fuentes que etiquetan las MISMAS unidades:
#   - el Clasificador automático,
#   - el Anotador 1 (docente),
#   - el Anotador 2 (docente).
# Se reportan los TRES pares posibles — (Clasificador↔A1), (Clasificador↔A2),
# (A1↔A2) — cada uno con su Cohen's κ + IC95% + Gwet's AC1 + acuerdo observado
# (Po) + matriz de confusión, reusando `compute_cohen_kappa`.
#
# El veredicto de la hipótesis H3 es DELIBERADAMENTE TRANSPARENTE: NO colapsa a
# un único pass/fail opaco. Expone (a) en cuántos de los 3 pares κ ≥ umbral
# (criterio de la Tabla V: "κ ≥ 0,70 en al menos dos de los tres pares") y (b)
# por par, si al menos 2 de los 3 estadísticos (Cohen κ, Gwet AC1, Po) alcanzan
# el umbral sustancial (criterio combinado de §VII-A). Todos los números crudos
# quedan accesibles para que el lector audite el veredicto.

# Umbral de acuerdo "sustancial" objetivo del piloto (ADR-046). Default 0.70 —
# configurable por si un protocolo exige otro corte.
SUBSTANTIAL_THRESHOLD = 0.70


@dataclass
class PairVerdict:
    """Diagnóstico transparente del criterio combinado de §VII-A para UN par.

    Reporta, sin esconderlos, los 3 estadísticos del par contra el umbral y
    cuántos lo alcanzan. `combined_substantial` es True cuando al menos 2 de los
    3 (Cohen κ, Gwet AC1, Po) llegan al umbral — pero los componentes quedan
    expuestos para que el caller decida.
    """

    pair_name: str
    kappa: float
    ac1: float
    observed_agreement: float
    threshold: float
    kappa_reaches: bool
    ac1_reaches: bool
    po_reaches: bool
    n_statistics_reaching: int
    combined_substantial: bool


@dataclass
class ThreePairReliability:
    """Resultado del análisis de fiabilidad sobre 3 fuentes (paper §VII-A).

    Contiene los 3 `KappaResult` nombrados (cada uno con κ + IC95% + AC1 + Po +
    matriz de confusión + interpretación) y los campos del veredicto H3
    expuestos de forma transparente — componentes crudos, NO un pass/fail opaco.
    """

    # Los 3 reportes pareados (cada uno es un KappaResult completo).
    classifier_vs_annotator1: KappaResult
    classifier_vs_annotator2: KappaResult
    annotator1_vs_annotator2: KappaResult

    # Conjunto de categorías efectivamente usado (4 niveles N1–N4 en Protocolo A,
    # 3 categorías de apropiación en Protocolo B).
    categories: tuple[str, ...]
    n_units: int
    threshold: float

    # ── Veredicto H3 transparente ──────────────────────────────────────
    # (a) Criterio Tabla V: en cuántos de los 3 pares κ ≥ umbral.
    pairs_kappa_above_threshold: int
    # Conveniencia: el criterio "≥ 2 de 3 pares" (Tabla V). El número crudo
    # `pairs_kappa_above_threshold` queda al lado para auditarlo.
    h3_table_v_met: bool
    # (b) Criterio combinado §VII-A: diagnóstico por par (κ, AC1, Po).
    pair_verdicts: list[PairVerdict] = field(default_factory=list)

    @property
    def pairs(self) -> dict[str, KappaResult]:
        """Acceso por nombre a los 3 reportes pareados (orden estable)."""
        return {
            "classifier_vs_annotator1": self.classifier_vs_annotator1,
            "classifier_vs_annotator2": self.classifier_vs_annotator2,
            "annotator1_vs_annotator2": self.annotator1_vs_annotator2,
        }

    @property
    def pairs_combined_substantial(self) -> int:
        """Cuántos pares cumplen el criterio combinado (≥2 de 3 estadísticos)."""
        return sum(1 for v in self.pair_verdicts if v.combined_substantial)


def _infer_categories(*label_lists: Sequence[str]) -> tuple[str, ...]:
    """Deduce el conjunto de categorías a partir de los datos.

    Une las etiquetas vistas en todas las fuentes, ordenadas alfabéticamente
    para determinismo. Se usa cuando el caller no pasa `categories` explícito.
    """
    seen: set[str] = set()
    for labels in label_lists:
        seen.update(labels)
    return tuple(sorted(seen))


def compute_three_pair_reliability(
    classifier_labels: Sequence[str],
    annotator1_labels: Sequence[str],
    annotator2_labels: Sequence[str],
    categories: Sequence[str] | None = None,
    threshold: float = SUBSTANTIAL_THRESHOLD,
) -> ThreePairReliability:
    """Fiabilidad inter-rater sobre 3 fuentes que etiquetan las mismas unidades.

    Genérica sobre el conjunto de categorías → sirve tanto al Protocolo A
    (4 niveles N1–N4, 200 eventos) como al Protocolo B (3 categorías de
    apropiación, 50 episodios). Las tres listas de etiquetas deben estar
    ALINEADAS por posición: la unidad i es `classifier_labels[i]`,
    `annotator1_labels[i]`, `annotator2_labels[i]`.

    Args:
        classifier_labels: etiquetas del clasificador automático.
        annotator1_labels: etiquetas del Anotador 1 (docente).
        annotator2_labels: etiquetas del Anotador 2 (docente).
        categories: conjunto de categorías válidas. Si es ``None`` se infiere de
            los datos (unión de etiquetas vistas, orden alfabético determinista).
        threshold: umbral de acuerdo sustancial. Default 0.70 (ADR-046).

    Returns:
        ThreePairReliability con los 3 KappaResult nombrados + el veredicto H3
        transparente (componentes crudos expuestos, sin pass/fail opaco).

    Raises:
        ValueError si las 3 listas no tienen el mismo largo, están vacías, o
            contienen etiquetas fuera del conjunto de categorías.
    """
    n = len(classifier_labels)
    if not (n == len(annotator1_labels) == len(annotator2_labels)):
        raise ValueError(
            "Las 3 fuentes deben etiquetar las mismas unidades "
            f"(largos: clasificador={n}, a1={len(annotator1_labels)}, "
            f"a2={len(annotator2_labels)})"
        )
    if n == 0:
        raise ValueError("Se necesita al menos 1 unidad para computar fiabilidad")

    cats = (
        _infer_categories(classifier_labels, annotator1_labels, annotator2_labels)
        if categories is None
        else tuple(dict.fromkeys(categories))
    )

    def _pair(a: Sequence[str], b: Sequence[str]) -> KappaResult:
        ratings = [
            KappaRating(episode_id=f"u_{i}", rater_a=a[i], rater_b=b[i]) for i in range(n)
        ]
        return compute_cohen_kappa(ratings, categories=cats)

    clf_a1 = _pair(classifier_labels, annotator1_labels)
    clf_a2 = _pair(classifier_labels, annotator2_labels)
    a1_a2 = _pair(annotator1_labels, annotator2_labels)

    pairs_named = [
        ("classifier_vs_annotator1", clf_a1),
        ("classifier_vs_annotator2", clf_a2),
        ("annotator1_vs_annotator2", a1_a2),
    ]

    # (a) Criterio Tabla V: cuántos pares con κ ≥ umbral.
    pairs_kappa_above = sum(1 for _, r in pairs_named if r.kappa >= threshold)

    # (b) Criterio combinado §VII-A por par: ≥2 de 3 estadísticos ≥ umbral.
    verdicts: list[PairVerdict] = []
    for name, r in pairs_named:
        kappa_ok = r.kappa >= threshold
        ac1_ok = r.ac1 >= threshold
        po_ok = r.observed_agreement >= threshold
        n_reaching = int(kappa_ok) + int(ac1_ok) + int(po_ok)
        verdicts.append(
            PairVerdict(
                pair_name=name,
                kappa=r.kappa,
                ac1=r.ac1,
                observed_agreement=r.observed_agreement,
                threshold=threshold,
                kappa_reaches=kappa_ok,
                ac1_reaches=ac1_ok,
                po_reaches=po_ok,
                n_statistics_reaching=n_reaching,
                combined_substantial=n_reaching >= 2,
            )
        )

    return ThreePairReliability(
        classifier_vs_annotator1=clf_a1,
        classifier_vs_annotator2=clf_a2,
        annotator1_vs_annotator2=a1_a2,
        categories=cats,
        n_units=n,
        threshold=threshold,
        pairs_kappa_above_threshold=pairs_kappa_above,
        h3_table_v_met=pairs_kappa_above >= 2,
        pair_verdicts=verdicts,
    )


def format_three_pair_report(result: ThreePairReliability) -> str:
    """Reporte legible del análisis de 3 pares + veredicto H3 transparente."""
    lines = [
        f"Fiabilidad inter-rater — 3 fuentes (n = {result.n_units}, "
        f"umbral = {result.threshold:.2f})",
        f"Categorías ({len(result.categories)}): {', '.join(result.categories)}",
        "",
        "Veredicto H3 (transparente — componentes expuestos):",
        f"  (a) Tabla V: {result.pairs_kappa_above_threshold}/3 pares con "
        f"κ ≥ {result.threshold:.2f}  →  criterio '≥2 de 3' "
        f"{'CUMPLIDO' if result.h3_table_v_met else 'NO cumplido'}",
        f"  (b) §VII-A combinado: {result.pairs_combined_substantial}/3 pares con "
        "≥2 de 3 estadísticos (κ, AC1, Po) sustanciales",
        "",
        "Detalle por par:",
    ]
    for v in result.pair_verdicts:
        lines.append(
            f"  {v.pair_name}: κ={v.kappa:.4f}{'✓' if v.kappa_reaches else '✗'}  "
            f"AC1={v.ac1:.4f}{'✓' if v.ac1_reaches else '✗'}  "
            f"Po={v.observed_agreement:.4f}{'✓' if v.po_reaches else '✗'}  "
            f"({v.n_statistics_reaching}/3 → "
            f"{'sustancial' if v.combined_substantial else 'NO sustancial'})"
        )
    return "\n".join(lines)
