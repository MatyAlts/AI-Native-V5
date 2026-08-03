"""Coherencia Estructural del Codigo (CEC) — sexta coherencia (R7 informeSoc.md).

Tres funciones puras sobre snapshots de codigo Python:
  - `depth_variance(snapshots)` — varianza de profundidad de anidamiento AST.
  - `function_granularity(code)` — promedio de lineas-por-funcion + outliers.
  - `naming_consistency(code)` — heuristica por regex de homogeneidad lexica.

Agregadas en `compute_cec(snapshots)` -> CECResult.

GUARD DE LENGUAJE (multi-language-research-integrity, seccion 6):
  Las 3 sub-coherencias se calibraron SOLO sobre codigo Python (Pyodide) —
  ver `subgrupo.py:14-18` sobre la calibracion original con datos de prod. El
  AST de este modulo es el de Python (`ast.parse`). Codigo de otro lenguaje
  (ej. Java) NO es medible con estos umbrales: `ast.parse` tiraria SyntaxError
  y el modulo lo confundiria con "Python a medio escribir", emitiendo
  puntuaciones-fantasma calibradas para Python (naming_consistency = 1.0,
  granularidad con 0 funciones). Por eso `compute_cec` recibe el `language`
  del episodio (dato de procedencia resuelto server-side, ver
  episode-language-provenance) y distingue TRES estados en `CECResult.status`:

    - `medido`            -> Python valido, las 3 coherencias computadas.
    - `error_transitorio` -> Python pero el codigo final no parsea (edicion en
                             curso). Se distingue de "lenguaje no soportado".
    - `no_aplicable`      -> lenguaje != python. NINGUNA puntuacion numerica
                             (todos los campos None). Se excluye de agregados.

  `SUPPORTED_LANGUAGES` es local al modulo a proposito: "CEC calibrado para X"
  es un concepto DISTINTO de "la plataforma soporta X". Java es lenguaje
  soportado por la plataforma (epic java-language-model) pero CEC NO esta
  calibrado para el — declararlo `no_aplicable` es integridad de datos, no una
  limitacion a esconder.

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
from typing import Any, Literal

CEC_VERSION = "1.0.0"

# Estado de aplicabilidad del computo CEC sobre un episodio (seccion 6).
CECStatus = Literal["medido", "error_transitorio", "no_aplicable"]

# Lenguajes para los que CEC esta calibrado. HOY solo Python (los umbrales de
# `subgrupo.py` y los rangos de este modulo se calibraron sobre Pyodide). NO es
# la lista de lenguajes que soporta la plataforma — es la lista para la que
# estas metricas estructurales tienen sentido. Ampliar SOLO tras recalibrar.
SUPPORTED_LANGUAGES = frozenset({"python"})
DEFAULT_CEC_LANGUAGE = "python"

# Rangos pedagogicos sugeridos (calibrar con docentes UTN antes de produccion).
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
    """Resultado agregado de las 3 sub-coherencias estructurales.

    Los campos numericos son `None` cuando `status == "no_aplicable"` (lenguaje
    no calibrado): CEC no emite puntuaciones-fantasma para codigo que no puede
    medir. En `medido` y `error_transitorio` los campos llevan valor (en el
    segundo, computado sobre un codigo final que no parsea — interpretar con el
    `status`, no a ciegas).
    """

    depth_variance: float | None
    function_granularity: FunctionGranularityResult | None
    naming_consistency_ratio: float | None  # [0, 1]
    cec_summary: float | None  # [0, 1] derivado de las 3 anteriores
    status: CECStatus = "medido"
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
        max_d = max(max_d, d)
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
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
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
    *,
    language: str = DEFAULT_CEC_LANGUAGE,
) -> CECResult:
    """Computa la Coherencia Estructural del Codigo (CEC) sobre un episodio.

    Args:
        snapshots: lista ordenada de estados del codigo a lo largo del episodio.
            Cada uno es un string del archivo entero. Snapshots con sintaxis
            invalida se descartan del depth_variance pero no rompen la funcion.
        final_code: el ultimo snapshot — si es None, se toma snapshots[-1].
            Util cuando el caller quiere especificar el snapshot final
            independientemente del muestreo.
        language: lenguaje de procedencia del episodio (resuelto server-side,
            ver episode-language-provenance). GUARD: si no esta en
            `SUPPORTED_LANGUAGES` (hoy solo "python"), NO se computa nada —
            se devuelve un CECResult `no_aplicable` sin ninguna puntuacion.
            El guard vive aca, en el modulo (seccion 6, tarea 6.7), no en los
            invocadores: cualquier caller que pase codigo Java obtiene
            `no_aplicable` sin poder saltearse el chequeo.

    Returns:
        CECResult con `status` en {medido, error_transitorio, no_aplicable}.
        Solo `medido`/`error_transitorio` llevan puntuaciones; `no_aplicable`
        las lleva en None.

    Funcion pura, deterministica.
    """
    # Guard de lenguaje ANTES de cualquier ast.parse (seccion 6, tarea 6.2):
    # codigo no-Python no es medible con umbrales calibrados para Python.
    if language not in SUPPORTED_LANGUAGES:
        return CECResult(
            depth_variance=None,
            function_granularity=None,
            naming_consistency_ratio=None,
            cec_summary=None,
            status="no_aplicable",
            diagnostics={
                "language": language,
                "reason": "cec_no_calibrado_para_este_lenguaje",
                "supported_languages": sorted(SUPPORTED_LANGUAGES),
            },
        )

    if final_code is None:
        final_code = snapshots[-1] if snapshots else ""

    # Python cuyo codigo final no parsea = edicion en curso (error transitorio),
    # NO lenguaje no soportado (tarea 6.5). Se distingue via `status`.
    status: CECStatus = "medido" if _safe_parse(final_code) is not None else "error_transitorio"

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
        status=status,
        diagnostics={
            "component_depth": component_depth,
            "component_granularity": component_granularity,
            "component_naming": component_naming,
            "n_snapshots_input": len(snapshots),
            "n_snapshots_parseables": sum(1 for s in snapshots if _safe_parse(s) is not None),
        },
    )


@dataclass(frozen=True)
class CECAggregate:
    """Agregado de CEC sobre varios episodios, con contabilidad de exclusiones.

    `no_aplicable` NUNCA entra al promedio (seccion 6, tarea 6.6): promediar un
    lenguaje no calibrado contra Python contaminaria la metrica. El agregado
    declara explicitamente cuantos excluyo para que quien lea el dato sepa sobre
    que universo se calculo — un promedio sin ese conteo es un dato que parece
    mas solido de lo que es.
    """

    mean_cec_summary: float | None  # None si no quedo ningun resultado medible
    n_total: int
    n_no_aplicable_excluded: int
    n_aggregated: int


def aggregate_cec(results: list[CECResult]) -> CECAggregate:
    """Promedia `cec_summary` sobre resultados medibles, excluyendo no-aplicables.

    Excluye todo `no_aplicable` (y cualquier resultado con `cec_summary is None`)
    del promedio, y reporta cuantos quedaron afuera. Si no queda ningun resultado
    medible, `mean_cec_summary` es None (no 0.0 — ausencia de dato, no un cero).

    Funcion pura, deterministica.
    """
    n_total = len(results)
    n_no_aplicable = sum(1 for r in results if r.status == "no_aplicable")
    medibles = [r.cec_summary for r in results if r.cec_summary is not None]
    mean = sum(medibles) / len(medibles) if medibles else None
    return CECAggregate(
        mean_cec_summary=mean,
        n_total=n_total,
        n_no_aplicable_excluded=n_no_aplicable,
        n_aggregated=len(medibles),
    )
