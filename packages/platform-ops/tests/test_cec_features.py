"""Tests golden del modulo cec_features (R7 informeSoc.md, BLOQUEADO por A1).

Tests deterministicos sobre snippets sinteticos de codigo Python.
Validan que las 3 sub-coherencias se computan correctamente y que
`compute_cec` agrega sensatamente.

IMPORTANTE: las constantes (FUNCTION_GRANULARITY_MIN_LINES = 5, MAX_LINES = 30,
DEPTH_VARIANCE_NORM = 4.0) son operacionalizaciones iniciales. Si se calibran
empiricamente con docentes UTN, estos tests deben actualizarse en paralelo.
"""

from __future__ import annotations

from platform_ops.cec_features import (
    CEC_VERSION,
    DEPTH_VARIANCE_NORM,
    FUNCTION_GRANULARITY_MAX_LINES,
    FUNCTION_GRANULARITY_MIN_LINES,
    SUPPORTED_LANGUAGES,
    aggregate_cec,
    compute_cec,
    depth_variance,
    function_granularity,
    naming_consistency,
)

# ---------------------------------------------------------------------------
# depth_variance
# ---------------------------------------------------------------------------


def test_un_solo_snapshot_devuelve_varianza_cero() -> None:
    code = "def f():\n    return 1\n"
    assert depth_variance([code]) == 0.0


def test_dos_snapshots_con_misma_profundidad_devuelve_cero() -> None:
    code_a = "def f():\n    return 1\n"
    code_b = "def g():\n    return 2\n"
    assert depth_variance([code_a, code_b]) == 0.0


def test_snapshots_con_profundidad_creciente_dan_varianza_positiva() -> None:
    s1 = "x = 1\n"  # depth 0
    s2 = "def f():\n    return 1\n"  # depth 1
    s3 = "def f():\n    for i in range(10):\n        if i > 5:\n            print(i)\n"  # depth 3
    dv = depth_variance([s1, s2, s3])
    assert dv > 0.0


def test_snapshot_con_sintaxis_invalida_no_rompe_pero_se_excluye() -> None:
    s1 = "def f():\n    return 1\n"
    s2 = "def g(:"  # syntax error
    s3 = "def h():\n    return 2\n"
    # Los 2 parseables tienen misma profundidad => varianza 0.
    assert depth_variance([s1, s2, s3]) == 0.0


# ---------------------------------------------------------------------------
# function_granularity
# ---------------------------------------------------------------------------


def test_codigo_sin_funciones_devuelve_count_cero() -> None:
    code = "x = 1\ny = 2\nprint(x + y)\n"
    result = function_granularity(code)
    assert result.function_count == 0
    assert result.mean_lines == 0.0


def test_funcion_corta_cuenta_como_outlier_below() -> None:
    # 2 lineas — debajo de MIN_LINES = 5
    code = "def f():\n    return 1\n"
    result = function_granularity(code)
    assert result.function_count == 1
    assert result.outliers_below == 1
    assert result.outliers_above == 0


def test_funcion_dentro_de_rango_no_es_outlier() -> None:
    body = "\n".join(f"    x{i} = {i}" for i in range(10))
    code = f"def f():\n{body}\n    return x0\n"
    result = function_granularity(code)
    # 12 lineas — dentro de [5, 30]
    assert result.function_count == 1
    assert result.outliers_below == 0
    assert result.outliers_above == 0


def test_funcion_muy_larga_cuenta_como_outlier_above() -> None:
    body = "\n".join(f"    x{i} = {i}" for i in range(50))
    code = f"def f():\n{body}\n    return x0\n"
    result = function_granularity(code)
    # 52 lineas — encima de MAX_LINES = 30
    assert result.function_count == 1
    assert result.outliers_above == 1


def test_codigo_invalido_devuelve_count_cero_sin_romper() -> None:
    code = "def f(:\n    return 1\n"
    result = function_granularity(code)
    assert result.function_count == 0


# ---------------------------------------------------------------------------
# naming_consistency
# ---------------------------------------------------------------------------


def test_codigo_solo_snake_case_devuelve_1() -> None:
    code = "def my_function():\n    return 1\n\ndef another_function():\n    return 2\n"
    assert naming_consistency(code) == 1.0


def test_codigo_mezcla_snake_y_camel_devuelve_menor_a_1() -> None:
    code = "def my_function():\n    return 1\n\ndef anotherFunction():\n    return 2\n"
    result = naming_consistency(code)
    assert 0.0 < result < 1.0


def test_codigo_sin_identificadores_clasificables_devuelve_1() -> None:
    code = "x = 1\n"  # x es 1 caracter pero sigue snake
    result = naming_consistency(code)
    assert result == 1.0


def test_clase_pascal_y_funciones_snake_se_cuentan_separadas() -> None:
    code = "class MiClase:\n    pass\n\ndef mi_funcion():\n    return 1\n"
    # Una pascal, una snake => 0.5
    result = naming_consistency(code)
    assert result == 0.5


def test_codigo_invalido_devuelve_1_por_convencion() -> None:
    code = "def f(:"
    assert naming_consistency(code) == 1.0


# ---------------------------------------------------------------------------
# compute_cec (integracion)
# ---------------------------------------------------------------------------


def test_codigo_estructuralmente_coherente_da_cec_alto() -> None:
    code = (
        "def calcular_suma(numeros):\n"
        "    total = 0\n"
        "    for n in numeros:\n"
        "        total = total + n\n"
        "    return total\n"
        "\n"
        "def calcular_promedio(numeros):\n"
        "    suma = calcular_suma(numeros)\n"
        "    return suma / len(numeros)\n"
    )
    result = compute_cec([code, code])  # 2 snapshots identicos
    assert result.cec_summary > 0.7
    assert result.depth_variance == 0.0
    assert result.naming_consistency_ratio == 1.0
    assert result.cec_version == CEC_VERSION


def test_codigo_estructuralmente_inconsistente_da_cec_bajo() -> None:
    # Mezcla snake/camel + funciones muy cortas + sin estructura
    code = (
        "def myFunction():\n"
        "    return 1\n"
        "\n"
        "def otra_func():\n"
        "    return 2\n"
        "\n"
        "def F3():\n"
        "    return 3\n"
    )
    result = compute_cec([code])
    # Tres funciones cortas (outliers below) + mezcla snake/camel/pascal
    assert result.function_granularity.outliers_below == 3
    assert result.naming_consistency_ratio < 1.0
    # cec_summary debe estar bajo
    assert result.cec_summary < 0.7


def test_dos_llamadas_con_mismos_snapshots_dan_mismo_cec() -> None:
    code = "def f():\n    return 1\n"
    r1 = compute_cec([code])
    r2 = compute_cec([code])
    assert r1 == r2


def test_final_code_override_funciona() -> None:
    s1 = "def f(): return 1\n"
    s2 = "def f(): return 2\n"
    final_distinto = "def g(): return 3\n"
    # function_granularity se computa sobre final_distinto, no sobre s2
    result = compute_cec([s1, s2], final_code=final_distinto)
    assert result.function_granularity.function_count == 1


# ---------------------------------------------------------------------------
# Constantes vigentes (anti-regresion)
# ---------------------------------------------------------------------------


def test_constantes_vigentes() -> None:
    """Si se calibran las constantes, este test se actualiza coordinadamente."""
    assert FUNCTION_GRANULARITY_MIN_LINES == 5
    assert FUNCTION_GRANULARITY_MAX_LINES == 30
    assert DEPTH_VARIANCE_NORM == 4.0
    assert CEC_VERSION == "1.0.0"


# ---------------------------------------------------------------------------
# Guard de lenguaje (seccion 6, multi-language-research-integrity)
# ---------------------------------------------------------------------------


def test_solo_python_esta_soportado_hoy() -> None:
    # CEC calibrado solo para Python. Si se recalibra para otro lenguaje, este
    # test se actualiza coordinadamente (mismo criterio que test_constantes).
    assert SUPPORTED_LANGUAGES == frozenset({"python"})


def test_java_devuelve_no_aplicable_sin_ninguna_puntuacion() -> None:
    # Tarea 6.3: codigo Java -> no_aplicable y NINGUN campo numerico.
    java = (
        "public class Calculadora {\n"
        "    public int suma(int a, int b) {\n"
        "        return a + b;\n"
        "    }\n"
        "}\n"
    )
    result = compute_cec([java], language="java")
    assert result.status == "no_aplicable"
    assert result.cec_summary is None
    assert result.depth_variance is None
    assert result.function_granularity is None
    assert result.naming_consistency_ratio is None


def test_language_es_autoritativo_no_el_parseo() -> None:
    # Aunque el string parsee como Python, si el episodio es Java el guard manda:
    # el lenguaje es dato de procedencia, no se infiere del parseo (mismo
    # principio que episode-language-provenance).
    result = compute_cec(["x = 1\n"], language="java")
    assert result.status == "no_aplicable"
    assert result.cec_summary is None


def test_guard_vive_en_el_modulo_llamada_directa() -> None:
    # Tarea 6.7: el guard vive en compute_cec (el modulo), no en un invocador.
    # Llamada directa, sin wrapper: un lenguaje no soportado igual da no_aplicable.
    result = compute_cec(["BEGIN\n  DISPLAY 'hi'.\n"], language="cobol")
    assert result.status == "no_aplicable"
    assert result.diagnostics["language"] == "cobol"
    assert "python" in result.diagnostics["supported_languages"]


def test_python_default_identico_a_language_explicito() -> None:
    # Tarea 6.4 (parte 1): omitir el parametro preserva el comportamiento previo.
    code = "def calcular_suma(numeros):\n    total = 0\n    return total\n"
    sin_lang = compute_cec([code])
    con_lang = compute_cec([code], language="python")
    assert sin_lang == con_lang
    assert sin_lang.status == "medido"


def test_python_medido_conserva_valores_previos_al_guard() -> None:
    # Tarea 6.4 (parte 2): Python valido produce resultados identicos a los
    # previos a la seccion 6 (1 funcion corta, naming consistente, sin varianza).
    code = "def f():\n    return 1\n"
    result = compute_cec([code])
    assert result.status == "medido"
    assert result.depth_variance == 0.0
    assert result.naming_consistency_ratio == 1.0
    assert result.function_granularity is not None
    assert result.function_granularity.function_count == 1
    assert result.function_granularity.outliers_below == 1


def test_python_a_medio_escribir_es_error_transitorio_no_no_aplicable() -> None:
    # Tarea 6.5: un fragmento Python que no parsea es error transitorio, NO
    # "lenguaje no soportado". La distincion importa: transitorio = reintentar,
    # no_aplicable = nunca medible para ese lenguaje.
    incompleto = "def calcular(nums):\n    total = 0\n    for n in nu"  # cortado
    result = compute_cec([incompleto], language="python")
    assert result.status == "error_transitorio"
    assert result.status != "no_aplicable"


def test_aggregate_excluye_no_aplicables_y_declara_cuantos() -> None:
    # Tarea 6.6: el agregado excluye no_aplicables y reporta cuantos excluyo.
    py = compute_cec(["def f():\n    return 1\n"], language="python")
    java1 = compute_cec(["public class A {}\n"], language="java")
    java2 = compute_cec(["public class B {}\n"], language="java")
    agg = aggregate_cec([py, java1, java2])
    assert agg.n_total == 3
    assert agg.n_no_aplicable_excluded == 2
    assert agg.n_aggregated == 1
    assert agg.mean_cec_summary == py.cec_summary


def test_aggregate_todo_no_aplicable_da_media_none() -> None:
    # Ausencia de dato medible = None, NO 0.0 (un cero mentiria sobre la media).
    java = compute_cec(["public class A {}\n"], language="java")
    agg = aggregate_cec([java, java])
    assert agg.mean_cec_summary is None
    assert agg.n_aggregated == 0
    assert agg.n_no_aplicable_excluded == 2
