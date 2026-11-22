"""Bordes de `platform_ops.tropiezos` que la aceptacion de HU-011 no cubre."""

from __future__ import annotations

from platform_ops.tropiezos import (
    TROPIEZOS_VERSION,
    serie_juez,
    tipo_de_error,
    trayectoria_alumno,
    tropiezos_de_episodio,
)


def _ejec(seq: int, stderr: str = "", code: str = "x = 1") -> dict:
    return {
        "seq": seq,
        "event_type": "codigo_ejecutado",
        "payload": {"code": code, "stdout": "", "stderr": stderr, "duration_ms": 1},
    }


def _probar(seq: int, total: int, failed: int) -> dict:
    return {
        "seq": seq,
        "event_type": "tests_ejecutados",
        "payload": {
            "test_count_total": total,
            "test_count_passed": total - failed,
            "test_count_failed": failed,
        },
    }


def _prompt(seq: int) -> dict:
    return {"seq": seq, "event_type": "prompt_enviado", "payload": {"content": "?"}}


TRACEBACK = (
    "Traceback (most recent call last):\n"
    '  File "<editor>", line 3, in <module>\n'
    "    edad = int(input())\n"
    "ValueError: invalid literal for int() with base 10: 'hola'\n"
    "\n"
)


def test_version_literal() -> None:
    assert TROPIEZOS_VERSION == "1.0.0"


def test_traceback_de_varias_lineas_toma_la_ultima_no_vacia() -> None:
    assert tipo_de_error(TRACEBACK) == "ValueError"


def test_stderr_solo_con_espacios_es_ejecucion_limpia() -> None:
    t = tropiezos_de_episodio([_ejec(1, "NameError: x"), _ejec(2, "   \n\t\n")])
    assert [(x["tipo"], x["resolucion"], x["seq_fin"]) for x in t] == [("NameError", "solo", 2)]


def test_probar_con_cero_casos_no_resuelve() -> None:
    t = tropiezos_de_episodio([_ejec(1, "TypeError: x"), _probar(2, 0, 0)])
    assert t[0]["resolucion"] == "sin_resolver"
    assert t[0]["seq_fin"] is None


def test_episodio_sin_eventos() -> None:
    assert tropiezos_de_episodio([]) == []
    tray = trayectoria_alumno([{"episode_id": "e1", "opened_at": "2026-11-01", "events": []}])
    assert tray == {"version": "1.0.0", "por_tipo": {}}


def test_ordena_por_seq_aunque_lleguen_desordenados() -> None:
    t = tropiezos_de_episodio([_ejec(3), _prompt(2), _ejec(1, "ValueError: x")])
    assert t[0]["resolucion"] == "con_tutor"


def test_clase_propia_del_alumno_es_otro_error() -> None:
    assert tipo_de_error("MiError: algo") == "OtroError"
    assert tipo_de_error("algo raro sin clase") == "OtroError"


def test_java_por_el_codigo_no_es_tropiezo() -> None:
    # El error de Java llega al CTR ya parseado por javaError.ts.
    code = "public class Main { public static void main(String[] a) {} }"
    assert tipo_de_error("';' expected", code) is None


def test_mensaje_de_plataforma_entre_errores_no_corta_el_tropiezo() -> None:
    timeout = "⏱ La ejecucion supero los 5 segundos y fue interrumpida."
    t = tropiezos_de_episodio(
        [_ejec(1, "ValueError: x"), _ejec(2, timeout), _ejec(3, "ValueError: y")]
    )
    assert [(x["tipo"], x["intentos"], x["resolucion"]) for x in t] == [
        ("ValueError", 2, "sin_resolver")
    ]


def test_opened_at_iguales_desempata_por_episode_id() -> None:
    def ep(eid: str, tp: str) -> dict:
        return {
            "episode_id": eid,
            "tarea_practica_id": tp,
            "opened_at": "2026-11-01T10:00:00Z",
            "events": [_ejec(1, "NameError: x"), _ejec(2)],
        }

    a = trayectoria_alumno([ep("b", "TP2"), ep("a", "TP1")])
    b = trayectoria_alumno([ep("a", "TP1"), ep("b", "TP2")])
    assert a == b
    ap = a["por_tipo"]["NameError"]["apariciones"]
    assert [x["episode_id"] for x in ap] == ["a", "b"]


def test_mejora_en_el_mismo_episodio_no_cuenta() -> None:
    eps = [
        {
            "episode_id": "e1",
            "tarea_practica_id": "TP1",
            "opened_at": "2026-11-01",
            "events": [
                _ejec(1, "ValueError: x"),
                _prompt(2),
                _ejec(3),
                _ejec(4, "ValueError: x"),
                _ejec(5),
            ],
        },
        {
            "episode_id": "e2",
            "tarea_practica_id": "TP1",
            "opened_at": "2026-11-02",
            "events": [_ejec(1, "ValueError: x"), _prompt(2), _ejec(3)],
        },
    ]
    # e1: con_tutor y despues solo, en el MISMO episodio; e2: con_tutor. El
    # "solo" de e1 no es de un episodio posterior al con_tutor de e1.
    assert trayectoria_alumno(eps)["por_tipo"]["ValueError"]["tendencia"] == "sin_cambio"


def test_serie_juez_raw_sin_forma_conocida_queda_afuera() -> None:
    c = {
        "episode_id": "x",
        "opened_at": "2026-11-01",
        "features": {"regimen_llm": {"estado": "ok", "raw": {}}},
    }
    assert serie_juez([c]) == []


def test_serie_juez_valor_desconocido_es_no_evaluable() -> None:
    raw = {
        "d1_verbalizacion": {"valor": "quizas"},
        "d2_verificacion": {"valor": "presente"},
        "d3_justificacion": {},
        "d4_autonomia": {"valor": "transferencia"},
    }
    c = {
        "episode_id": "x",
        "opened_at": "2026-11-01",
        "features": {"regimen_llm": {"estado": "ok", "raw": raw}},
    }
    assert serie_juez([c]) == [
        {
            "episode_id": "x",
            "d1": "no_evaluable",
            "d2": "presente",
            "d3": "no_evaluable",
            "d4": "transferencia",
        }
    ]


# ── Segunda ronda: lenguaje, Java por el codigo, mensajes anclados, fechas ──


def _ep(eid: str, opened_at: object, err: str = "NameError: x") -> dict:
    return {
        "episode_id": eid,
        "tarea_practica_id": "TP1",
        "opened_at": opened_at,
        "events": [_ejec(1, err), _ejec(2)],
    }


def _orden(eps: list[dict]) -> list[str]:
    ap = trayectoria_alumno(eps)["por_tipo"]["NameError"]["apariciones"]
    return [a["episode_id"] for a in ap]


def test_fecha_faltante_o_invalida_va_al_final() -> None:
    eps = [
        _ep("a_sin", None),
        _ep("b_mala", "ayer a la tarde"),
        _ep("c_nov", "2026-11-05T10:00:00Z"),
        _ep("d_oct", "2026-10-20T10:00:00+00:00"),
    ]
    assert _orden(eps) == ["d_oct", "c_nov", "a_sin", "b_mala"]


def test_fecha_sin_huso_se_toma_como_utc() -> None:
    # 2026-11-02T11:00 sin huso (UTC) va antes que 09:00 en -03:00 (12:00 UTC).
    eps = [_ep("ar", "2026-11-02T09:00:00-03:00"), _ep("naive", "2026-11-02T11:00:00")]
    assert _orden(eps) == ["naive", "ar"]


def test_serie_juez_ordena_por_fecha_real() -> None:
    raw = {"verbalizacion": {"presente": True}, "autonomia": {"presente": True}}
    juez = {"regimen_llm": {"estado": "ok", "raw": raw}}
    c = [
        {"episode_id": "ar", "opened_at": "2026-11-02T09:00:00-03:00", "features": juez},
        {"episode_id": "z", "opened_at": "2026-11-02T10:00:00Z", "features": juez},
    ]
    assert [s["episode_id"] for s in serie_juez(c)] == ["z", "ar"]


def test_sin_lenguaje_la_clase_java_fuera_de_strings_sigue_descartando() -> None:
    code = 'public class Main {\n  public static void main(String[] a) { int x = "#"; }\n}'
    assert tipo_de_error("TypeError: x", code) is None


def test_clase_java_dentro_de_un_docstring_python_no_descarta() -> None:
    code = '"""\npublic class Main {\n"""\nint("hola")'
    assert tipo_de_error("ValueError: x", code) == "ValueError"


def test_numeral_dentro_de_un_string_no_oculta_codigo_java() -> None:
    code = 's = "#"; public static void main(String[] a) {}'
    assert tipo_de_error("TypeError: x", code) is None


def test_con_python_ni_el_formato_de_javac_descarta() -> None:
    assert tipo_de_error("Main.java:3: error: ';' expected", "", "python") == "OtroError"


def test_reloj_en_el_medio_de_un_error_real_cuenta() -> None:
    assert tipo_de_error("ValueError: tarde ⏱ mucho") == "ValueError"
