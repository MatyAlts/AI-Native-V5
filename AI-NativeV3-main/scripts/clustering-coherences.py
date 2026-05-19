"""Clustering alternativo sobre las 5 coherencias (CS19).

Origen: plan1Socra.md CS19 (P2). Recomendación C3.2 del informeSocra1.md.
Objetivo: aplicar k-means (k=3) sobre las 5 coherencias y comparar los
clusters emergentes con la categorización del árbol de decisión.

Si los clusters emergentes coinciden con las tres categorías del árbol
(matching alto, κ ≥ 0.70 — ADR-046), hay **validez convergente** del árbol con un
approach guiado por los datos.
Si divergen sistemáticamente, el árbol opera con umbrales que no reflejan
agrupaciones naturales en el espacio de coherencias — vale revisarlo.

BLOQUEO CRÍTICO — NO EJECUTAR ANTES DE A1
=========================================
Depende de A1 cerrado (106 históricas con `classifier_config_hash` actual).

Salida esperada:
  - `clustering-comparison.csv` — tabla de contingencia clusters vs árbol.
  - `clustering-kappa.txt` — κ de Cohen + matriz de confusión.
  - `clustering-report.md` — interpretación + visualización pendiente.

Algoritmo
=========
- k-means con k=3, inicialización k-means++, 100 iteraciones.
- Standardización previa (z-score) de las 5 coherencias.
- ccd_orphan_ratio invertido (1 - x) para que "alto = bueno" sea consistente
  con las otras 4.
- Asignación de etiquetas a clusters: el cluster con mayor media en
  sum_coherences → "reflexiva", el menor → "delegacion", intermedio → "superficial".
  (Esto es heurístico: el algoritmo no sabe los nombres, los asignamos
  post-hoc por orden.)
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass(frozen=True)
class ClusteringResult:
    """Resultado del clustering."""

    cluster_labels: np.ndarray  # n vector con cluster id (0, 1, 2)
    cluster_centers: np.ndarray  # 3 x 5 matriz
    inertia: float
    iterations: int


def _kmeans_pp_init(X: np.ndarray, k: int, seed: int = 42) -> np.ndarray:
    """k-means++ inicialización (Arthur & Vassilvitskii, 2007).

    Devuelve k × dim centros iniciales.
    """
    rng = np.random.default_rng(seed)
    n, dim = X.shape
    centers = np.empty((k, dim))
    # Primer centro: aleatorio
    idx = int(rng.integers(n))
    centers[0] = X[idx]
    for i in range(1, k):
        # Distancia mínima de cada punto al centro más cercano ya elegido
        dists_sq = np.min(
            np.sum((X[:, None, :] - centers[:i, :]) ** 2, axis=2), axis=1
        )
        # Sample siguiente centro con probabilidad ∝ dist²
        if dists_sq.sum() == 0:
            idx = int(rng.integers(n))
        else:
            probs = dists_sq / dists_sq.sum()
            idx = int(rng.choice(n, p=probs))
        centers[i] = X[idx]
    return centers


def kmeans(X: np.ndarray, k: int, max_iter: int = 100, tol: float = 1e-4, seed: int = 42) -> ClusteringResult:
    """k-means estándar.

    No usa sklearn — implementación pura numpy.
    """
    centers = _kmeans_pp_init(X, k, seed=seed)
    for iteration in range(max_iter):
        # Asignar puntos al centro más cercano
        dists = np.sqrt(((X[:, None, :] - centers[None, :, :]) ** 2).sum(axis=2))
        labels = dists.argmin(axis=1)
        # Recomputar centros
        new_centers = np.zeros_like(centers)
        for c in range(k):
            mask = labels == c
            if mask.any():
                new_centers[c] = X[mask].mean(axis=0)
            else:
                new_centers[c] = centers[c]
        # Convergencia
        if np.max(np.abs(new_centers - centers)) < tol:
            centers = new_centers
            break
        centers = new_centers

    # Inertia (suma cuadrados intra-cluster)
    dists = np.sqrt(((X[:, None, :] - centers[None, :, :]) ** 2).sum(axis=2))
    inertia = float((dists.min(axis=1) ** 2).sum())

    return ClusteringResult(
        cluster_labels=labels,
        cluster_centers=centers,
        inertia=inertia,
        iterations=iteration + 1,
    )


def assign_cluster_names(
    cluster_centers: np.ndarray, cluster_labels: np.ndarray
) -> np.ndarray:
    """Asigna nombres semánticos a los clusters por orden de sum_coherences.

    El cluster con mayor sum → "reflexiva", menor → "delegacion", medio → "superficial".
    Asume orden estándar de columnas: [ct, ccd_mean, ccd_orphan_invertido, cii_stab, cii_evol].
    """
    sums = cluster_centers.sum(axis=1)
    order = np.argsort(sums)  # ascending: bajo sum primero
    label_map = {
        int(order[0]): "delegacion_pasiva",
        int(order[1]): "apropiacion_superficial",
        int(order[2]): "apropiacion_reflexiva",
    }
    named = np.array([label_map[int(c)] for c in cluster_labels])
    return named


def cohen_kappa_categorical(a: np.ndarray, b: np.ndarray) -> float:
    """κ de Cohen entre dos arrays de etiquetas categóricas."""
    if len(a) != len(b) or len(a) == 0:
        return 0.0
    categories = np.unique(np.concatenate([a, b]))
    k = len(categories)
    # Matriz de confusión
    cm = np.zeros((k, k), dtype=float)
    cat_to_idx = {c: i for i, c in enumerate(categories)}
    for ai, bi in zip(a, b):
        cm[cat_to_idx[ai], cat_to_idx[bi]] += 1
    n = cm.sum()
    p_o = np.diag(cm).sum() / n
    p_e = ((cm.sum(axis=0) / n) * (cm.sum(axis=1) / n)).sum()
    if p_e == 1.0:
        return 1.0 if p_o == 1.0 else 0.0
    return float((p_o - p_e) / (1 - p_e))


def main() -> int:
    parser = argparse.ArgumentParser(description="Clustering vs árbol (CS19).")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.dry_run:
        print("Clustering dry-run — datos sintéticos.")
        rng = np.random.default_rng(42)
        n = 100
        # Generar 3 clusters sintéticos en espacio de 5 coherencias
        coherences = np.vstack(
            [
                rng.normal([0.8, 0.7, 0.7, 0.6, 0.7], 0.05, size=(40, 5)),  # reflexiva
                rng.normal([0.5, 0.5, 0.5, 0.4, 0.5], 0.08, size=(40, 5)),  # superficial
                rng.normal([0.3, 0.3, 0.4, 0.2, 0.3], 0.08, size=(20, 5)),  # delegacion
            ]
        )
        # Etiqueta "real" simulada (gold del árbol sintético)
        tree_labels = np.array(
            ["apropiacion_reflexiva"] * 40
            + ["apropiacion_superficial"] * 40
            + ["delegacion_pasiva"] * 20
        )

        # Invertir orphan (col 2) y standardize
        coherences_inv = coherences.copy()
        coherences_inv[:, 2] = 1.0 - coherences_inv[:, 2]
        coherences_std = (coherences_inv - coherences_inv.mean(axis=0)) / coherences_inv.std(axis=0)

        result = kmeans(coherences_std, k=3, seed=42)
        cluster_named = assign_cluster_names(result.cluster_centers, result.cluster_labels)
        kappa = cohen_kappa_categorical(cluster_named, tree_labels)

        print(f"  inertia: {result.inertia:.3f}")
        print(f"  iterations: {result.iterations}")
        print(f"  kappa (clusters vs tree synthetic): {kappa:.3f}")
        if kappa > 0.70:
            print("  -> convergencia esperada (sintetico): clusters coinciden con arbol")
        return 0

    raise NotImplementedError(
        "BLOQUEADO POR A1 (plan1Socra.md CS19). Ejecución requiere 106 "
        "históricas re-clasificadas. Estructura lista. Modo --dry-run "
        "verifica con clusters sintéticos."
    )


if __name__ == "__main__":
    sys.exit(main())
