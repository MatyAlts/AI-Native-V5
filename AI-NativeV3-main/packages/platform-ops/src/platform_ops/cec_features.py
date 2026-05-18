"""Coherencia Estructural del Codigo (CEC) — sexta coherencia (R7 informeSoc.md).

Tres funciones puras sobre snapshots de codigo Python:
  - `depth_variance(snapshots)` — varianza de profundidad de anidamiento AST.
  - `function_granularity(code)` — promedio de lineas-por-funcion + outliers.
  - `naming_consistency(code)` — heuristica por regex de homogeneidad lexica.

Agregadas en `compute_cec(snapshots)` -> CECResult.

BLOQUEO CRITICO (design doc seccion 1):
  Este modulo NO debe conectarse al `pipeline.py` ni a `tree.py` hasta que
  A1 (re-clasificacion de las 106 classifications historicas con el
  classifier_config_hash actual) este ejecutado y verificado. Activarlo
  antes invalida el corpus auditable del piloto-1.

Por lo tanto: este modulo existe como utilidad de analisis offline. Puede
llamarse desde scripts ad-hoc o un endpoint preview, pero NO desde el
pipeline que genera `Classification.appropriation`. Esa conexion requiere
ADR-051 + bump de `classifier_config_hash` coordinado con A1.

Funciones puras, deterministicas, sin side-effects. Tests golden en
`tests/test_cec_features.py`.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from typing import Any

CEC_VERSION = "1.0.0"

# Rangos pedagogicos sugeridos (calibrar con docentes UNSL antes de produccion).
# Operacionalizacion inicial — no validados empiricamente.
FUNCTION_GRANULARITY_MIN_LINES = 5
FUNCTION_GRANULARITY_MAX_LINES = 30
DEPTH_VARIANCE_NORM = 4.0  # divisor para normalizar a [0, 1]


@dataclass(frozen=True)
class FunctionGranularityResult:
    """Resultado de granularidad funcional."""

    function_count: int
    mean_lines: float
    outliers_below: int  # funciones < FUNCTION_GRANULARITY_MIN_LINES
    outliers_above: int  # funciones > FUNCTION_GRANULARITY_MAX_LINES

    @property
    def outliers_total(self) -> int:
        return self.outliers_below + self.outliers_above


@dataclass(frozen=True)
class CECResult:
    """Resultado agregado de las 3 sub-coherencias estructurales."""

    depth_variance: float
    function_granularity: FunctionGranularityResult
    naming_consistency_ratio: float  # [0, 1]
    cec_summary: float  # [0, 1] derivado de las 3 anteriores
    cec_version: str = CEC_VERSION
    diagnostics: dict[str, Any] = field(default_factory=dict)


def _safe_parse(code: str) -> ast.AST | None:
    """Intenta parsear codigo Python. Devuelve None si falla.

    Sintaxis invalida es comun durante la edicion del estudiante. CEC debe
    degradar graciosamente (None se propaga como diagnostic).
    """
    try:
        return ast.parse(code)
    except SyntaxError:
        return None


def _max_depth(node: ast.AST, current: int = 0) -> int:
    """Profundidad maxima de anidamiento de bloques (recursion sobre el AST)."""
    max_d = current
    # Nodos que abren un nuevo bloque (cuerpo anidado)
    BLOCK_NODES = (
        ast.For,
        ast.AsyncFor,
        ast.While,
        ast.If,
        ast.With,
        ast.AsyncWith,
        ast.Try,
        ast.FunctionDef,
        ast.AsyncFunctionDef,
        ast.ClassDef,
    )
    for child in ast.iter_child_nodes(node):
        if isinstance(child, BLOCK_NODES):
            d = _max_depth(child, current + 1)
        else:
            d = _max_depth(child, current)
        if d > max_d:
            max_d = d
    return max_d


def depth_variance(snapshots: list[str]) -> float:
    """Varianza poblacional de la profundidad maxima de anidamiento.

    Args:
        snapshots: lista de strings de codigo Python, en orden temporal.

    Returns:
        Varianza poblacional [0, +inf). 0 si <2 snapshots parseables o si
        todos tienen igual profundidad. Snapshots con sintaxis invalida se
        excluyen del computo.
    """
    depths: list[int] = []
    for code in snapshots:
        tree = _safe_parse(code)
        if tree is None:
            continue
        depths.append(_max_depth(tree))
    n = len(depths)
    if n < 2:
        return 0.0
    mean = sum(depths) / n
    return sum((d - mean) ** 2 for d in depths) / n


def _function_lengths(tree: ast.AST) -> list[int]:
    """Devuelve la cantidad de lineas de cuerpo de cada FunctionDef del AST."""
    lengths: list[int] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.body and hasattr(node.body[-1], "end_lineno"):
                end = node.body[-1].end_lineno or node.lineno
                lengths.append(end - node.lineno + 1)
    return lengths


def function_granularity(code: str) -> FunctionGranularityResult:
    """Mide la granularidad funcional del codigo final del episodio.

    Args:
        code: string del ultimo snapshot del episodio.

    Returns:
        FunctionGranularityResult con conteos. Si el codigo no parsea o no
        tiene funciones, devuelve result con function_count=0 y mean_lines=0.0.
    """
    tree = _safe_parse(code)
    if tree is None:
        return FunctionGranularityResult(
            function_count=0,
            mean_lines=0.0,
            outliers_below=0,
            outliers_above=0,
        )
    lengths = _function_lengths(tree)
    if not lengths:
        return FunctionGranularityResult(
            function_count=0,
            mean_lines=0.0,
            outliers_below=0,
            outliers_above=0,
        )
    mean = sum(lengths) / len(lengths)
    outliers_below = sum(1 for length in lengths if length < FUNCTION_GRANULARITY_MIN_LINES)
    outliers_above = sum(1 for length in lengths if length > FUNCTION_GRANULARITY_MAX_LINES)
    return FunctionGranularityResult(
        function_count=len(lengths),
        mean_lines=mean,
        outliers_below=outliers_below,
        outliers_above=outliers_above,
    )


_SNAKE_CASE_RE = re.compile(r"^[a-z_][a-z0-9_]*$")
_CAMEL_CASE_RE = re.compile(r"^[a-z][a-zA-Z0-9]*$")
_PASCAL_CASE_RE = re.compile(r"^[A-Z][a-zA-Z0-9]*$")


def _classify_identifier(name: str) -> str | None:
    """Clasifica un identificador por convencion lexica.

    Devuelve `snake`, `camel`, `pascal` o None (no clasificable).
    Identificadores muy cortos (1-2 chars) o solo letras minusculas pueden
    matchear varias convenciones — se clasifican como `snake` por convencion
    pythonica (PEP 8) salvo cuando son CamelCase claramente.
    """
    if not name or name.startswith("_"):
        return None  # dunder/protegidos no cuentan
    if "_" in name:
        return "snake" if _SNAKE_CASE_RE.match(name) else None
    if _PASCAL_CASE_RE.match(name):
        return "pascal"
    if _CAMEL_CASE_RE.match(name):
        # Sin _ y sin mayuscula inicial. Si tiene mayusculas adentro es camel,
        # si no es snake (consistente con PEP 8 sobre variables).
        if any(c.isupper() for c in name):
            return "camel"
        return "snake"
    return None


def naming_consistency(code: str) -> float:
    """Heuristica de homogeneidad lexica de identificadores.

    Cuenta identificadores definidos por el codigo (funciones, clases,
    variables top-level) y mide la fraccion del estilo dominante.

    Args:
        code: string del ultimo snapshot del episodio.

    Returns:
        Ratio [0, 1]. 1.0 = todos los identificadores siguen el mismo estilo.
        0.0 = mezcla maxima (multiples estilos en igual proporcion).
        Si no hay identificadores clasificables, devuelve 1.0 por convencion
        (codigo trivial es trivialmente consistente).
    """
    tree = _safe_parse(code)
    if tree is None:
        return 1.0
    styles: list[str] = []
    for node in ast.walk(tree):
        # Funciones
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            style = _classify_identifier(node.name)
            if style:
                styles.append(style)
        # Clases (separadas, PEP 8 espera PascalCase)
        elif isinstance(node, ast.ClassDef):
            style = _classify_identifier(node.name)
            if style:
                styles.append(style)
        # Variables asignadas top-level
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    style = _classify_identifier(target.id)
                    if style:
                        styles.append(style)
    if not styles:
        return 1.0
    counts: dict[str, int] = {}
    for s in styles:
        counts[s] = counts.get(s, 0) + 1
    return max(counts.values()) / len(styles)


def _clip(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


def compute_cec(
    snapshots: list[str],
    final_code: str | None = None,
) -> CECResult:
    """Computa la Coherencia Estructural del Codigo (CEC) sobre un episodio.

    Args:
        snapshots: lista ordenada de estados del codigo a lo largo del episodio.
            Cada uno es un string del archivo entero. Snapshots con sintaxis
            invalida se descartan del depth_variance pero no rompen la funcion.
        final_code: el ultimo snapshot — si es None, se toma snapshots[-1].
            Util cuando el caller quiere especificar el snapshot final
            independientemente del muestreo.

    Returns:
        CECResult con las 3 sub-coherencias + cec_summary derivado + version.

    Funcion pura, deterministica.
    """
    if final_code is None:
        final_code = snapshots[-1] if snapshots else ""

    dv = depth_variance(snapshots)
    fg = function_granularity(final_code)
    nc = naming_consistency(final_code)

    # cec_summary: promedio de 3 componentes normalizados a [0, 1] (alto = bueno).
    component_depth = 1.0 - _clip(dv / DEPTH_VARIANCE_NORM)
    if fg.function_count == 0:
        # Sin funciones — neutral. No penalizamos ni premiamos.
        component_granularity = 0.5
    elif fg.outliers_total == 0:
        component_granularity = 1.0
    else:
        component_granularity = 1.0 - _clip(fg.outliers_total / max(fg.function_count, 1))
    component_naming = nc

    cec_summary = (component_depth + component_granularity + component_naming) / 3.0

    return CECResult(
        depth_variance=dv,
        function_granularity=fg,
        naming_consistency_ratio=nc,
        cec_summary=cec_summary,
        diagnostics={
            "component_depth": component_depth,
            "component_granularity": component_granularity,
            "component_naming": component_naming,
            "n_snapshots_input": len(snapshots),
            "n_snapshots_parseables": sum(1 for s in snapshots if _safe_parse(s) is not None),
        },
    )
