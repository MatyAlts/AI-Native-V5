"""Comparación de capacidad predictiva: tipológica vs dimensional (CS18).

Origen: plan1Socra.md CS18 (P2). Recomendación C3.1 del informeSocra1.md.
Objetivo: comparar el approach tipológico vigente (3 categorías de apropiación)
contra una operacionalización dimensional (variable latente continua via IRT
o suma ponderada de coherencias) en términos de capacidad predictiva sobre
el score de transfer (CS15).

BLOQUEO CRÍTICO — NO EJECUTAR ANTES DE A1 + CS15
=================================================
Depende de:
  1. **A1 cerrado** — 106 históricas re-clasificadas.
  2. **CS15 ejecutado** — test de transfer aplicado en piloto-2 y scores
     codificados. Sin transfer scores no hay variable criterial para comparar.

Salida esperada:
  - `typology-vs-dimensional-models.csv` — comparación de R² ajustado /
    pseudo-R² entre modelos.
  - `typology-vs-dimensional-report.md` — interpretación.

Modelos a comparar
==================
Modelo T (Tipológico):
    transfer_score ~ apropiation_category + autoeficacia_pretest
Modelo D-suma (Dimensional simple):
    transfer_score ~ sum(coherences) + autoeficacia_pretest
Modelo D-irt (Dimensional via Rasch/2PL):
    transfer_score ~ theta_irt + autoeficacia_pretest
Modelo D-pca (Dimensional via PCA primer componente):
    transfer_score ~ pc1 + autoeficacia_pretest

Criterio de comparación: R² ajustado (variables continuas) o pseudo-R² de
McFadden si transfer_score se trata como ordinal. AIC/BIC complementarios.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass(frozen=True)
class ModelComparisonResult:
    """Comparación entre modelos."""

    model_name: str
    r_squared: float  # R² ajustado para regresión continua
    aic: float  # Akaike Information Criterion
    n_parameters: int
    notes: str


def _ols_r_squared_adj(
    X: np.ndarray, y: np.ndarray, add_intercept: bool = True
) -> tuple[float, np.ndarray]:
    """OLS simple, devuelve (R²_adj, coeficientes).

    No usa scipy/sklearn — implementación pura numpy para portabilidad.
    """
    n = X.shape[0]
    if add_intercept:
        X_full = np.column_stack([np.ones(n), X])
    else:
        X_full = X
    k = X_full.shape[1]

    # OLS: beta = (X'X)^-1 X'y
    XtX = X_full.T @ X_full
    Xty = X_full.T @ y
    beta = np.linalg.solve(XtX, Xty)

    # Predicciones y residuos
    y_pred = X_full @ beta
    residuals = y - y_pred
    ss_res = (residuals**2).sum()
    ss_tot = ((y - y.mean()) ** 2).sum()
    if ss_tot == 0:
        return 0.0, beta
    r_sq = 1.0 - ss_res / ss_tot
    # Ajuste por número de parámetros
    if n - k > 0:
        r_sq_adj = 1.0 - (1.0 - r_sq) * (n - 1) / (n - k)
    else:
        r_sq_adj = r_sq
    return float(r_sq_adj), beta


def _aic(n: int, ss_residuals: float, k: int) -> float:
    """AIC para regresión OLS gaussiana."""
    if ss_residuals <= 0 or n <= 0:
        return float("inf")
    return float(n * np.log(ss_residuals / n) + 2 * k)


def fit_typological_model(
    apropiation_categorical: np.ndarray,
    transfer_score: np.ndarray,
    autoeficacia: np.ndarray,
) -> ModelComparisonResult:
    """Modelo T: transfer ~ category (dummy-encoded) + autoeficacia.

    apropiation_categorical: array de strings o ints (3 categorías).
    """
    # Dummy encoding (2 dummies para 3 categorías, evitar colinealidad)
    categories = np.unique(apropiation_categorical)
    if len(categories) < 2:
        return ModelComparisonResult(
            model_name="typological",
            r_squared=0.0,
            aic=float("inf"),
            n_parameters=1,
            notes="muestra con única categoría — modelo degenerado",
        )
    # Dummies para todas menos la primera (reference)
    dummies = np.column_stack(
        [(apropiation_categorical == cat).astype(float) for cat in categories[1:]]
    )
    X = np.column_stack([dummies, autoeficacia])
    r_sq_adj, beta = _ols_r_squared_adj(X, transfer_score)
    n = X.shape[0]
    k = X.shape[1] + 1  # +1 por intercept
    residuals = transfer_score - (np.column_stack([np.ones(n), X]) @ beta)
    aic = _aic(n, (residuals**2).sum(), k)
    return ModelComparisonResult(
        model_name="typological",
        r_squared=r_sq_adj,
        aic=aic,
        n_parameters=k,
        notes=f"{len(categories)} categorías observadas",
    )


def fit_dimensional_sum_model(
    coherences_matrix: np.ndarray,  # n × 5
    transfer_score: np.ndarray,
    autoeficacia: np.ndarray,
) -> ModelComparisonResult:
    """Modelo D-suma: transfer ~ sum_coherences + autoeficacia.

    Convierte las 5 coherencias en una suma simple (asumiendo que mayor coherencia
    en cada dimensión = "mejor proceso"). ccd_orphan_ratio se invierte (1 - x)
    porque alto orphan = peor.
    """
    # Asume orden: [ct, ccd_mean, ccd_orphan, cii_stab, cii_evol]
    coherences_inverted_orphan = coherences_matrix.copy()
    coherences_inverted_orphan[:, 2] = 1.0 - coherences_inverted_orphan[:, 2]
    sum_score = coherences_inverted_orphan.sum(axis=1)
    X = np.column_stack([sum_score, autoeficacia])
    r_sq_adj, beta = _ols_r_squared_adj(X, transfer_score)
    n = X.shape[0]
    k = X.shape[1] + 1
    residuals = transfer_score - (np.column_stack([np.ones(n), X]) @ beta)
    aic = _aic(n, (residuals**2).sum(), k)
    return ModelComparisonResult(
        model_name="dimensional_sum",
        r_squared=r_sq_adj,
        aic=aic,
        n_parameters=k,
        notes="suma simple de 5 coherencias con orphan invertido",
    )


def fit_dimensional_pca_model(
    coherences_matrix: np.ndarray,
    transfer_score: np.ndarray,
    autoeficacia: np.ndarray,
) -> ModelComparisonResult:
    """Modelo D-pca: transfer ~ PC1(coherencias) + autoeficacia.

    PCA primer componente sobre las 5 coherencias (orphan invertido para signo
    consistente). Más principled que D-suma porque pondera por varianza.
    """
    coherences_inverted = coherences_matrix.copy()
    coherences_inverted[:, 2] = 1.0 - coherences_inverted[:, 2]
    # Standardize
    coherences_std = (coherences_inverted - coherences_inverted.mean(axis=0)) / coherences_inverted.std(
        axis=0
    )
    # PCA via eigendecomposition de la matriz de covarianza
    cov = np.cov(coherences_std, rowvar=False)
    eigvals, eigvecs = np.linalg.eigh(cov)
    # Primer componente = eigenvector de mayor eigenvalue
    idx_max = int(np.argmax(eigvals))
    pc1 = coherences_std @ eigvecs[:, idx_max]
    X = np.column_stack([pc1, autoeficacia])
    r_sq_adj, beta = _ols_r_squared_adj(X, transfer_score)
    n = X.shape[0]
    k = X.shape[1] + 1
    residuals = transfer_score - (np.column_stack([np.ones(n), X]) @ beta)
    aic = _aic(n, (residuals**2).sum(), k)
    return ModelComparisonResult(
        model_name="dimensional_pca",
        r_squared=r_sq_adj,
        aic=aic,
        n_parameters=k,
        notes=f"PC1 explica {eigvals[idx_max]/eigvals.sum()*100:.1f}% de la varianza",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Tipológica vs dimensional (CS18).")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.dry_run:
        print("Tipológica vs dimensional dry-run — datos sintéticos.")
        rng = np.random.default_rng(42)
        n = 80
        coherences = rng.uniform(0.2, 0.8, size=(n, 5))
        # Crear apropiation correlacionado con coherencias (sintético)
        sum_coh = coherences[:, 0] + coherences[:, 1] - coherences[:, 2]
        apropriation = np.where(
            sum_coh > sum_coh.mean() + sum_coh.std(),
            "reflexiva",
            np.where(sum_coh < sum_coh.mean() - sum_coh.std(), "delegacion", "superficial"),
        )
        transfer_score = (5 * sum_coh + rng.normal(0, 1, size=n)).clip(0, 10)
        autoeficacia = rng.uniform(2, 7, size=n)

        m_typ = fit_typological_model(apropriation, transfer_score, autoeficacia)
        m_sum = fit_dimensional_sum_model(coherences, transfer_score, autoeficacia)
        m_pca = fit_dimensional_pca_model(coherences, transfer_score, autoeficacia)

        for m in [m_typ, m_sum, m_pca]:
            print(f"  {m.model_name}: R²_adj={m.r_squared:.3f}, AIC={m.aic:.2f}, k={m.n_parameters}")
        return 0

    raise NotImplementedError(
        "BLOQUEADO POR A1 + CS15 (plan1Socra.md CS18). Ejecución requiere "
        "transfer scores reales + 106 históricas re-clasificadas. Estructura "
        "lista. Modo --dry-run verifica con datos sintéticos."
    )


if __name__ == "__main__":
    sys.exit(main())
