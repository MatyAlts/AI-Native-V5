"""Análisis Factorial Exploratorio sobre las 5 coherencias (CS17).

Origen: plan1Socra.md CS17 (P2). Recomendación C2.1 del informeSocra1.md.
Objetivo: validar la **discriminabilidad** de las 5 coherencias. Si todas
cargan en un único factor, son redundantes (colapsan en un constructo
implícito). Si cargan en factores distintos, son discriminantes.

BLOQUEO CRÍTICO — NO EJECUTAR ANTES DE A1
=========================================
Depende de:
  1. **A1 cerrado** — 106 classifications históricas re-clasificadas con
     `classifier_config_hash` actual (post-LABELER 1.2.0).
  2. **n ≥ 150 idealmente** — con n=106 el EFA es marginal (Tabachnick &
     Fidell, 2007, recomiendan n ≥ 5× variables, mínimo 50; pero para
     5 variables muchas fuentes recomiendan ≥ 150). Documentar caveat.

Salida esperada (post-ejecución):
  - `efa-kmo-bartlett.txt` — KMO + Bartlett test of sphericity.
  - `efa-parallel-analysis.csv` — análisis paralelo de Horn (eigenvalues
    observed vs random) para decidir n_factors.
  - `efa-loadings.csv` — matriz de cargas factoriales (con rotación oblimin).
  - `efa-report.md` — reporte agregado para Anexo D del paper.

Funciones puras del análisis
============================
Implementación en `numpy` + `scipy.stats`. No requiere `factor_analyzer`
o `R`. Las funciones son testeable con datasets sintéticos (`tests/test_factorial_analysis.py`
agendado para crear post-ejecución exitosa).
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass(frozen=True)
class KMOResult:
    """Resultado del test de Kaiser-Meyer-Olkin."""

    kmo_total: float  # overall KMO, debería ser >= 0.5 para adecuación muestral
    kmo_per_variable: dict[str, float]  # KMO por variable, debería ser >= 0.5 cada uno


@dataclass(frozen=True)
class BartlettResult:
    """Resultado del test de esfericidad de Bartlett."""

    chi_squared: float
    df: int  # degrees of freedom = k*(k-1)/2
    p_value: float  # debería ser < 0.05 para rechazar la H0 de matriz identidad


@dataclass(frozen=True)
class ParallelAnalysisResult:
    """Resultado del análisis paralelo de Horn (1965)."""

    n_variables: int
    n_iterations: int
    observed_eigenvalues: list[float]
    random_eigenvalues_p95: list[float]
    suggested_n_factors: int  # número de eigenvalues observados > p95 de random


@dataclass(frozen=True)
class EFAResult:
    """Resultado del EFA con rotación."""

    n_factors: int
    rotation: str  # "oblimin" | "varimax" | "none"
    loadings: dict[str, list[float]]  # var_name -> [factor_1, factor_2, ...]
    explained_variance: list[float]  # por factor
    cumulative_variance: list[float]


def compute_kmo(correlation_matrix: np.ndarray, var_names: list[str]) -> KMOResult:
    """Calcula KMO total y per-variable.

    KMO = sum(r_ij^2) / (sum(r_ij^2) + sum(a_ij^2))
    donde a_ij es la correlación parcial. Implementación canónica.
    """
    # Inversa de la matriz de correlación (para correlaciones parciales)
    try:
        inv = np.linalg.inv(correlation_matrix)
    except np.linalg.LinAlgError as e:
        raise ValueError(
            "Matriz de correlación singular — verificar redundancia entre variables."
        ) from e

    # Matriz de correlaciones parciales
    d = np.sqrt(np.diag(inv))
    partial_corr = -inv / np.outer(d, d)
    np.fill_diagonal(partial_corr, 1.0)

    # KMO total
    r_sq = correlation_matrix**2
    a_sq = partial_corr**2
    np.fill_diagonal(r_sq, 0.0)
    np.fill_diagonal(a_sq, 0.0)
    kmo_total = float(r_sq.sum() / (r_sq.sum() + a_sq.sum()))

    # KMO per variable
    kmo_per_var = {}
    for i, name in enumerate(var_names):
        r_row = r_sq[i, :].sum()
        a_row = a_sq[i, :].sum()
        kmo_per_var[name] = float(r_row / (r_row + a_row)) if (r_row + a_row) > 0 else 0.0

    return KMOResult(kmo_total=kmo_total, kmo_per_variable=kmo_per_var)


def compute_bartlett(correlation_matrix: np.ndarray, n_observations: int) -> BartlettResult:
    """Test de Bartlett de esfericidad.

    H0: la matriz de correlación es la matriz identidad (variables no correlacionadas).
    Rechazar H0 (p < 0.05) es pre-condición para que el EFA tenga sentido.

    scipy es opcional: si está disponible, se reporta p-value exacto;
    si no, p_value=-1.0 indica "no computable, usar tabla de chi^2 con
    el chi_squared y df reportados".
    """
    k = correlation_matrix.shape[0]
    det = np.linalg.det(correlation_matrix)
    if det <= 0:
        raise ValueError("Determinante de la matriz de correlación es no-positivo.")

    chi_sq = -(n_observations - 1 - (2 * k + 5) / 6) * np.log(det)
    df = k * (k - 1) // 2

    try:
        from scipy.stats import chi2

        p_value = float(1 - chi2.cdf(chi_sq, df))
    except ImportError:
        p_value = -1.0  # sentinel: scipy no disponible

    return BartlettResult(chi_squared=float(chi_sq), df=df, p_value=p_value)


def parallel_analysis(
    n_observations: int,
    n_variables: int,
    n_iterations: int = 1000,
    seed: int = 42,
) -> list[float]:
    """Análisis paralelo de Horn (1965).

    Genera n_iterations matrices de correlación aleatorias del mismo tamaño
    que la observada, computa eigenvalues, y devuelve el percentil 95 de
    cada eigenvalue ordenado descendentemente.
    """
    rng = np.random.default_rng(seed)
    all_eigenvalues = []
    for _ in range(n_iterations):
        # Datos aleatorios normales, n_observations x n_variables
        data = rng.standard_normal((n_observations, n_variables))
        corr = np.corrcoef(data, rowvar=False)
        eigvals = np.linalg.eigvalsh(corr)[::-1]  # descending
        all_eigenvalues.append(eigvals)
    all_eigenvalues = np.array(all_eigenvalues)
    return [float(np.percentile(all_eigenvalues[:, i], 95)) for i in range(n_variables)]


def suggest_n_factors(observed_eigvals: list[float], random_p95: list[float]) -> int:
    """Cuántos factores conservar: los que tienen eigenvalue observado > p95 random."""
    return sum(1 for obs, rnd in zip(observed_eigvals, random_p95) if obs > rnd)


def main() -> int:
    """Punto de entrada — BLOQUEADO POR A1.

    Estructura de funciones puras lista arriba. Para ejecutar:
    1. A1 cerrado (106 históricas re-clasificadas).
    2. Lectura desde `classifier_db.classifications` con `classifier_config_hash`
       actual.
    3. Construcción de matriz n_observations × 5 con las 5 coherencias.
    4. Aplicar funciones puras en este orden:
        - `compute_kmo(corr, var_names)` — verificar >= 0.5.
        - `compute_bartlett(corr, n)` — verificar p < 0.05.
        - `parallel_analysis(n, 5)` — obtener thresholds.
        - `suggest_n_factors(observed, random)` — decidir n_factors.
        - EFA con n_factors decidido (usar `factor_analyzer` si está disponible,
          o implementar maximum likelihood + rotación oblimin via scipy).
    """
    parser = argparse.ArgumentParser(description="EFA sobre 5 coherencias (CS17).")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.dry_run:
        print("EFA dry-run — verificación de imports y funciones puras.")
        # Test smoke: matriz 5x5 sintética
        test_corr = np.array(
            [
                [1.0, 0.3, 0.2, 0.1, 0.0],
                [0.3, 1.0, 0.4, 0.2, 0.1],
                [0.2, 0.4, 1.0, 0.3, 0.2],
                [0.1, 0.2, 0.3, 1.0, 0.4],
                [0.0, 0.1, 0.2, 0.4, 1.0],
            ]
        )
        var_names = ["ct", "ccd_mean", "ccd_orphan", "cii_stab", "cii_evol"]
        kmo = compute_kmo(test_corr, var_names)
        bartlett = compute_bartlett(test_corr, n_observations=150)
        random_p95 = parallel_analysis(n_observations=150, n_variables=5, n_iterations=100)
        observed = sorted(np.linalg.eigvalsh(test_corr)[::-1].tolist(), reverse=True)
        n_factors = suggest_n_factors(observed, random_p95)
        print(f"KMO total (synthetic): {kmo.kmo_total:.3f}")
        print(f"Bartlett p-value (synthetic, n=150): {bartlett.p_value:.6f}")
        print(f"Suggested n_factors (synthetic): {n_factors}")
        return 0

    raise NotImplementedError(
        "BLOQUEADO POR A1 (plan1Socra.md CS17). Ejecución requiere las 106 "
        "históricas re-clasificadas + lectura desde classifier_db. Estructura "
        "lista en este script. Modo --dry-run verifica con matriz sintética."
    )


if __name__ == "__main__":
    sys.exit(main())
