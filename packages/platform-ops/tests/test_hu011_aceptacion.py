"""Aceptacion HU-011, tramo 1 (orquestador, antes de construir; el constructor
no la modifica). Criterios aprobados por Juani el 22/11/2026 ("sisi dale").

Indicio de aprendizaje sin IA, en modo sombra: funciones puras en
`platform_ops.tropiezos` que, desde los eventos CTR y las clasificaciones,
arman la linea de tiempo de un alumno. No toca produccion ni pantallas.

Contrato que fija esta prueba:
  TROPIEZOS_VERSION: str
  tropiezos_de_episodio(events) -> list[{"tipo", "intentos", "resolucion", ...}]
      resolucion in {"solo", "con_tutor", "sin_resolver"}
  trayectoria_alumno(episodios) -> {"version", "por_tipo": {tipo: {
      "apariciones": [{"episode_id", "tarea_practica_id", "mismo_tp", "resolucion"}],
      "tendencia": "mejora" | "sin_cambio" | "sin_datos"}}}
      episodios = [{"episode_id", "tarea_practica_id", "opened_at", "events"}]
  serie_juez(clasificaciones) -> [{"episode_id", "d1", "d2", "d3", "d4"}]
      clasificaciones = [{"episode_id", "opened_at", "features"}]

C01  Cada Ejecutar con error de Python es un tropiezo con el tipo de la clase
     (ValueError, TypeError, ...; lo no reconocido es "OtroError"). El mismo
     error seguido es un solo tropiezo con varios intentos.
C02  Se resuelve con la siguiente ejecucion sin ese error o un Probar que pasa
     todo. Un error distinto resuelve el anterior y abre otro tropiezo.
C03  "solo" sin consultas al tutor en el medio; "con_tutor" con al menos una;
     "sin_resolver" si el episodio termina con ese error.
C04  La trayectoria ordena por fecha y marca si cada aparicion es del mismo TP
     que la anterior del mismo tipo (la primera: None).
C05  Tendencia por tipo: "mejora" si antes fue con_tutor o sin_resolver y en un
     episodio posterior fue solo; "sin_datos" si aparece en un solo episodio;
     si no, "sin_cambio".
C06  Serie del juez con las dos formas (v1 y MTAC v2/v3) normalizadas:
     d1..d3 in {presente, ausente, no_evaluable}; d4 in {interlocutor, oraculo,
     transferencia, no_evaluable}.
N01  Mensajes de la plataforma (dato cancelado, tiempo agotado) y errores de
     Java no son tropiezos.
N02  Episodios donde el juez no decidio (estado != "ok" o sin juez) no estan
     en la serie.
N03  Que un tipo deje de aparecer no es "mejora".
N04  No lee `reflexion_completada`.
N05  No toca el clasificador: el hash de referencia sigue igual.
"""

from __future__ import annotations

import pytest
from platform_ops.tropiezos import (
    TROPIEZOS_VERSION,
    serie_juez,
    trayectoria_alumno,
    tropiezos_de_episodio,
)

# ── helpers ──────────────────────────────────────────────────────────────


def _ev(seq: int, tipo: str, payload: dict | None = None) -> dict:
    return {
        "seq": seq,
        "event_type": tipo,
        "ts": f"2026-11-21T10:{seq:02d}:00Z",
        "payload": payload or {},
    }


def _ejec(seq: int, stderr: str = "", stdout: str = "ok\n") -> dict:
    return _ev(
        seq,
        "codigo_ejecutado",
        {
            "code": "x",
            "stdout": "" if stderr else stdout,
            "stderr": stderr,
            "duration_ms": 5,
            "runtime": "pyodide-0.26",
        },
    )


def _probar(seq: int, total: int, passed: int) -> dict:
    return _ev(
        seq,
        "tests_ejecutados",
        {
            "test_count_total": total,
            "test_count_passed": passed,
            "test_count_failed": total - passed,
        },
    )


def _prompt(seq: int) -> dict:
    return _ev(
        seq, "prompt_enviado", {"content": "no entiendo el error", "prompt_kind": "exploracion"}
    )


def _primero(tropiezos: list[dict]) -> dict:
    assert len(tropiezos) >= 1, f"se esperaba al menos un tropiezo y hubo {tropiezos!r}"
    return tropiezos[0]


def _tipo(trayectoria: dict, tipo: str) -> dict:
    por_tipo = trayectoria.get("por_tipo", {})
    assert tipo in por_tipo, f"falta el tipo {tipo} en {sorted(por_tipo)}"
    return por_tipo[tipo]


VALUE = "ValueError: invalid literal for int() with base 10: 'hola'"
TYPE = 'TypeError: can only concatenate str (not "int") to str'
NAME = "NameError: name 'edad' is not defined"
SYNTAX = "SyntaxError: invalid syntax"


# ── C01 ──────────────────────────────────────────────────────────────────


def test_version_declarada() -> None:
    assert isinstance(TROPIEZOS_VERSION, str) and TROPIEZOS_VERSION


def test_c01_un_error_es_un_tropiezo_con_su_tipo() -> None:
    t = tropiezos_de_episodio([_ev(0, "episodio_abierto"), _ejec(1, VALUE), _ejec(2)])
    assert [x["tipo"] for x in t] == ["ValueError"]


def test_c01_el_mismo_error_seguido_es_uno_con_intentos() -> None:
    t = tropiezos_de_episodio([_ejec(1, VALUE), _ejec(2, VALUE), _ejec(3, VALUE), _ejec(4)])
    assert len(t) == 1
    assert _primero(t)["intentos"] == 3


def test_c01_error_no_reconocido_es_otro() -> None:
    t = tropiezos_de_episodio([_ejec(1, "RecursionError: maximum recursion depth exceeded")])
    assert _primero(t)["tipo"] in {"RecursionError", "OtroError"}


@pytest.mark.parametrize(
    "stderr,tipo",
    [
        (TYPE, "TypeError"),
        (NAME, "NameError"),
        (SYNTAX, "SyntaxError"),
        ("IndentationError: unexpected indent", "IndentationError"),
        ("ZeroDivisionError: division by zero", "ZeroDivisionError"),
    ],
)
def test_c01_tipos_comunes(stderr: str, tipo: str) -> None:
    assert _primero(tropiezos_de_episodio([_ejec(1, stderr)]))["tipo"] == tipo


# ── C02 / C03 ────────────────────────────────────────────────────────────


def test_c02_c03_resuelto_solo_con_ejecucion_limpia() -> None:
    t = tropiezos_de_episodio([_ejec(1, VALUE), _ev(2, "edicion_codigo"), _ejec(3)])
    assert _primero(t)["resolucion"] == "solo"


def test_c02_c03_resuelto_con_probar_que_pasa_todo() -> None:
    t = tropiezos_de_episodio([_ejec(1, VALUE), _probar(2, 2, 2)])
    assert _primero(t)["resolucion"] == "solo"


def test_c02_probar_que_falla_no_resuelve() -> None:
    t = tropiezos_de_episodio([_ejec(1, VALUE), _probar(2, 2, 1)])
    assert _primero(t)["resolucion"] == "sin_resolver"


def test_c03_con_tutor_si_pregunto_en_el_medio() -> None:
    t = tropiezos_de_episodio([_ejec(1, VALUE), _prompt(2), _ev(3, "tutor_respondio"), _ejec(4)])
    assert _primero(t)["resolucion"] == "con_tutor"


def test_c03_preguntar_antes_del_error_no_cuenta() -> None:
    t = tropiezos_de_episodio([_prompt(1), _ejec(2, VALUE), _ejec(3)])
    assert _primero(t)["resolucion"] == "solo"


def test_c03_sin_resolver_si_termina_con_el_error() -> None:
    t = tropiezos_de_episodio([_ejec(1, VALUE), _ev(2, "episodio_cerrado")])
    assert _primero(t)["resolucion"] == "sin_resolver"


def test_c02_error_distinto_resuelve_el_anterior_y_abre_otro() -> None:
    t = tropiezos_de_episodio([_ejec(1, SYNTAX), _ejec(2, NAME), _ejec(3)])
    assert [(x["tipo"], x["resolucion"]) for x in t] == [
        ("SyntaxError", "solo"),
        ("NameError", "solo"),
    ]


# ── N01 / N04 ────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "stderr",
    [
        "KeyboardInterrupt: Cancelaste el pedido de dato, asi que la ejecucion se detuvo.",
        "Tu programa supero el limite de tiempo y se interrumpio. Suele ser un bucle que nunca termina.",
        "⏱ Tu programa tardo demasiado",
        "Main.java:3: error: ';' expected",
    ],
)
def test_n01_mensajes_de_plataforma_y_java_no_son_tropiezos(stderr: str) -> None:
    assert tropiezos_de_episodio([_ejec(1, stderr), _ejec(2)]) == []


def test_n04_no_lee_la_reflexion() -> None:
    base = [_ejec(1, VALUE), _ejec(2)]
    con_reflexion = [
        *base,
        _ev(3, "reflexion_completada", {"respuestas": {"q1": "ValueError: me trabe con int"}}),
    ]
    assert tropiezos_de_episodio(con_reflexion) == tropiezos_de_episodio(base)


# ── C04 / C05 / N03 ──────────────────────────────────────────────────────


def _episodio(eid: str, tp: str, dia: int, events: list[dict]) -> dict:
    return {
        "episode_id": eid,
        "tarea_practica_id": tp,
        "opened_at": f"2026-11-{dia:02d}T10:00:00Z",
        "events": events,
    }


def test_c04_ordena_por_fecha_y_marca_mismo_tp() -> None:
    eps = [
        _episodio("e3", "TP2", 15, [_ejec(1, VALUE), _ejec(2)]),
        _episodio("e1", "TP1", 1, [_ejec(1, VALUE), _prompt(2), _ejec(3)]),
        _episodio("e2", "TP1", 3, [_ejec(1, VALUE), _ejec(2)]),
    ]
    ap = _tipo(trayectoria_alumno(eps), "ValueError")["apariciones"]
    assert [a["episode_id"] for a in ap] == ["e1", "e2", "e3"]
    assert [a["mismo_tp"] for a in ap] == [None, True, False]


def test_c05_mejora_si_antes_con_tutor_y_despues_solo() -> None:
    eps = [
        _episodio("e1", "TP1", 1, [_ejec(1, VALUE), _prompt(2), _ejec(3)]),
        _episodio("e2", "TP2", 9, [_ejec(1, VALUE), _ejec(2)]),
    ]
    assert _tipo(trayectoria_alumno(eps), "ValueError")["tendencia"] == "mejora"


def test_c05_mejora_si_antes_sin_resolver_y_despues_solo() -> None:
    eps = [
        _episodio("e1", "TP1", 1, [_ejec(1, TYPE)]),
        _episodio("e2", "TP1", 2, [_ejec(1, TYPE), _ejec(2)]),
    ]
    assert _tipo(trayectoria_alumno(eps), "TypeError")["tendencia"] == "mejora"


def test_c05_sin_cambio_si_siempre_con_tutor() -> None:
    eps = [
        _episodio("e1", "TP1", 1, [_ejec(1, VALUE), _prompt(2), _ejec(3)]),
        _episodio("e2", "TP1", 2, [_ejec(1, VALUE), _prompt(2), _ejec(3)]),
    ]
    assert _tipo(trayectoria_alumno(eps), "ValueError")["tendencia"] == "sin_cambio"


def test_c05_empeorar_no_es_mejora() -> None:
    eps = [
        _episodio("e1", "TP1", 1, [_ejec(1, VALUE), _ejec(2)]),
        _episodio("e2", "TP1", 2, [_ejec(1, VALUE), _prompt(2), _ejec(3)]),
    ]
    assert _tipo(trayectoria_alumno(eps), "ValueError")["tendencia"] == "sin_cambio"


def test_c05_sin_datos_si_aparece_en_un_solo_episodio() -> None:
    eps = [
        _episodio(
            "e1", "TP1", 1, [_ejec(1, VALUE), _prompt(2), _ejec(3), _ejec(4, VALUE), _ejec(5)]
        )
    ]
    assert _tipo(trayectoria_alumno(eps), "ValueError")["tendencia"] == "sin_datos"


def test_n03_dejar_de_aparecer_no_es_mejora() -> None:
    eps = [
        _episodio("e1", "TP1", 1, [_ejec(1, NAME), _prompt(2), _ejec(3)]),
        _episodio("e2", "TP1", 2, [_ejec(1), _probar(2, 2, 2)]),
        _episodio("e3", "TP2", 9, [_ejec(1)]),
    ]
    assert _tipo(trayectoria_alumno(eps), "NameError")["tendencia"] != "mejora"


def test_trayectoria_declara_version() -> None:
    assert trayectoria_alumno([])["version"] == TROPIEZOS_VERSION


# ── C06 / N02 ────────────────────────────────────────────────────────────


def _clasif(eid: str, dia: int, regimen_llm: dict | None) -> dict:
    features: dict = {}
    if regimen_llm is not None:
        features["regimen_llm"] = regimen_llm
    return {"episode_id": eid, "opened_at": f"2026-11-{dia:02d}T10:00:00Z", "features": features}


V3_OK = {
    "estado": "ok",
    "regimen": "REFLEXIVA",
    "juez_version": "v3",
    "raw": {
        "d1_verbalizacion": {"valor": "presente", "localizador": "mensaje 1", "cita": "a"},
        "d2_verificacion": {"valor": "ausente", "localizador": "", "cita": ""},
        "d3_justificacion": {"valor": "no_evaluable", "localizador": "", "cita": ""},
        "d4_autonomia": {"valor": "interlocutor", "localizador": "mensaje 2", "cita": "b"},
        "regimen": "REFLEXIVA",
    },
}

V1_OK = {
    "estado": "ok",
    "regimen": "SUPERFICIAL",
    "raw": {
        "verbalizacion": {"presente": True, "evidencia": "a"},
        "verificacion": {"presente": False, "evidencia": ""},
        "justificacion": {"presente": "no_evaluable", "evidencia": ""},
        "autonomia": {"presente": False, "evidencia": ""},
    },
}


def test_c06_serie_con_las_dos_formas_y_en_orden() -> None:
    serie = serie_juez([_clasif("nuevo", 20, V3_OK), _clasif("viejo", 5, V1_OK)])
    assert serie == [
        {
            "episode_id": "viejo",
            "d1": "presente",
            "d2": "ausente",
            "d3": "no_evaluable",
            "d4": "oraculo",
        },
        {
            "episode_id": "nuevo",
            "d1": "presente",
            "d2": "ausente",
            "d3": "no_evaluable",
            "d4": "interlocutor",
        },
    ]


def test_n02_sin_decision_del_juez_no_esta_en_la_serie() -> None:
    abst = {"estado": "abstencion_traza_insuficiente", "regimen": None, "raw": V3_OK["raw"]}
    serie = serie_juez([_clasif("a", 1, abst), _clasif("b", 2, None), _clasif("c", 3, V3_OK)])
    assert [s["episode_id"] for s in serie] == ["c"]


# ── N05 ──────────────────────────────────────────────────────────────────


def test_n05_no_toca_el_clasificador() -> None:
    import inspect

    from classifier_service.routes import health
    from classifier_service.services.pipeline import compute_classifier_config_hash
    from platform_ops import tropiezos

    assert health._TREE_VERSION == "v4.3.0"
    assert (
        compute_classifier_config_hash(health.DEFAULT_REFERENCE_PROFILE)
        == "9a70c3a38997284c2e343d3cc7cbad835624fb7140379aa9548dbd2fc33bc901"
    )
    # El modulo nuevo no depende del clasificador ni escribe en ningun lado.
    fuente = inspect.getsource(tropiezos)
    assert "classifier_service" not in fuente
    assert "sqlalchemy" not in fuente.lower()
