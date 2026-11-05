"""Meta-esquema del formulario, respuesta parcial, régimen según la regla y cierre
(tareas 3.1 y 3.2, design D9, specs codebook-versionado y estudio-codificacion).

Los esquemas se construyen acá con claves neutras (`d1`..`d4`, `reflexiva`,
`superficial`, `pasiva`, `evidencia_insuficiente`): ni texto ni esquema del
codebook v0. La regla de prueba tiene la FORMA del escenario de la spec
("reflexiva si D1 presente, D2 o D3 presente y D4 interlocutor; pasiva si D4
transferencia con cita y D1, D2 y D3 ausentes").
"""

from __future__ import annotations

import copy

import pytest
from classifier_service.services.estudio_esquema import (
    PedidoInvalidoError,
    derivar_regimen,
    errores_respuesta_esperada,
    evaluar_pedido,
    faltantes_cierre,
    validar_esquema,
)

PA = ["presente", "ausente"]


def _dim(clave: str, valores=None, cita=None) -> dict:
    return {
        "clave": clave,
        "nombre": f"Dimension {clave}",
        "valores": list(valores or PA),
        "cita_requerida_si": list(cita if cita is not None else ["presente"]),
    }


def _atomo(dimension: str, *valores: str, con_cita: bool | None = None) -> dict:
    atomo: dict = {"dimension": dimension, "en": list(valores)}
    if con_cita is not None:
        atomo["con_cita"] = con_cita
    return atomo


def esquema_base() -> dict:
    return {
        "dimensiones": [
            _dim("d1"),
            _dim("d2"),
            _dim("d3"),
            _dim("d4", ["interlocutor", "oraculo", "transferencia"], ["transferencia"]),
        ],
        "regimenes": [
            {"clave": "reflexiva", "nombre": "Reflexiva"},
            {"clave": "superficial", "nombre": "Superficial"},
            {"clave": "pasiva", "nombre": "Pasiva"},
            {"clave": "evidencia_insuficiente", "nombre": "Evidencia insuficiente"},
        ],
        "regimen_evidencia_insuficiente": "evidencia_insuficiente",
        "dimensiones_opcionales_si_regimen": ["evidencia_insuficiente"],
        "notas_obligatorias_si_regimen": ["evidencia_insuficiente"],
        "marca_frontera": True,
        "notas_obligatorias_si_frontera": True,
        "confianza": {"valores": ["alta", "media", "baja"], "obligatoria": False},
        "reglas_regimen": [
            {
                "regimen": "reflexiva",
                "condicion": [
                    [_atomo("d1", "presente")],
                    [_atomo("d2", "presente"), _atomo("d3", "presente")],
                    [_atomo("d4", "interlocutor")],
                ],
            },
            {
                "regimen": "pasiva",
                "condicion": [
                    [_atomo("d4", "transferencia", con_cita=True)],
                    [_atomo("d1", "ausente")],
                    [_atomo("d2", "ausente")],
                    [_atomo("d3", "ausente")],
                ],
            },
        ],
        "regimen_por_defecto": "superficial",
        "regimenes_exentos": ["evidencia_insuficiente"],
    }


def _r(valor: str | None, cita: str | None = "turno 1") -> dict:
    return {"valor": valor, "cita": cita}


REFLEXIVA = {
    "d1": _r("presente"),
    "d2": _r("presente"),
    "d3": _r("ausente", None),
    "d4": _r("interlocutor", None),
}


# ── 3.1 Validación del esquema ────────────────────────────────────────────


def test_esquema_con_regla_ordenada_es_valido() -> None:
    assert validar_esquema(esquema_base()) == []


def test_esquema_sin_reglas_y_sin_confianza_es_valido() -> None:
    esquema = esquema_base()
    esquema["reglas_regimen"] = []
    del esquema["regimen_por_defecto"]
    esquema["confianza"] = None
    assert validar_esquema(esquema) == []


def _con(cambio) -> list[str]:
    esquema = esquema_base()
    cambio(esquema)
    return validar_esquema(esquema)


@pytest.mark.parametrize(
    ("caso", "cambio"),
    [
        ("no es objeto", None),
        ("clave desconocida", lambda e: e.update(extra=1)),
        ("dimension con un valor", lambda e: e["dimensiones"][0].update(valores=["presente"])),
        ("dimension con 7 valores", lambda e: e["dimensiones"][0].update(valores=list("abcdefg"))),
        ("dimension con valor repetido", lambda e: e["dimensiones"][0].update(valores=["x", "x"])),
        ("sin dimensiones", lambda e: e.update(dimensiones=[])),
        ("9 dimensiones", lambda e: e.update(dimensiones=[_dim(f"x{i}") for i in range(9)])),
        ("clave de dimension repetida", lambda e: e["dimensiones"][1].update(clave="d1")),
        ("clave de dimension invalida", lambda e: e["dimensiones"][0].update(clave="D 1")),
        ("clave desconocida en dimension", lambda e: e["dimensiones"][0].update(peso=2)),
        (
            "cita requerida con valor ajeno",
            lambda e: e["dimensiones"][0].update(cita_requerida_si=["otro"]),
        ),
        ("un solo regimen", lambda e: e.update(regimenes=e["regimenes"][:1])),
        ("clave desconocida en regimen", lambda e: e["regimenes"][0].update(color="rojo")),
        (
            "evidencia insuficiente inexistente",
            lambda e: e.update(regimen_evidencia_insuficiente="nada"),
        ),
        (
            "opcionales con regimen inexistente",
            lambda e: e.update(dimensiones_opcionales_si_regimen=["nada"]),
        ),
        (
            "notas con regimen inexistente",
            lambda e: e.update(notas_obligatorias_si_regimen=["nada"]),
        ),
        ("marca_frontera no booleana", lambda e: e.update(marca_frontera="si")),
        ("notas por frontera sin marca", lambda e: e.update(marca_frontera=False)),
        (
            "confianza sin valores",
            lambda e: e.update(confianza={"valores": [], "obligatoria": True}),
        ),
        ("confianza con clave desconocida", lambda e: e["confianza"].update(escala=5)),
        (
            "regla con dimension inexistente",
            lambda e: e["reglas_regimen"][0]["condicion"][0][0].update(dimension="d9"),
        ),
        (
            "regla con valor inexistente",
            lambda e: e["reglas_regimen"][0]["condicion"][0][0].update(en=["quizas"]),
        ),
        ("regla con regimen inexistente", lambda e: e["reglas_regimen"][0].update(regimen="nada")),
        (
            "regla que deriva un exento",
            lambda e: e["reglas_regimen"][0].update(regimen="evidencia_insuficiente"),
        ),
        ("regla con condicion vacia", lambda e: e["reglas_regimen"][0].update(condicion=[])),
        ("regla con clausula vacia", lambda e: e["reglas_regimen"][0]["condicion"].append([])),
        (
            "atomo con clave desconocida",
            lambda e: e["reglas_regimen"][0]["condicion"][0][0].update(no=True),
        ),
        (
            "con_cita no booleano",
            lambda e: e["reglas_regimen"][0]["condicion"][0][0].update(con_cita="si"),
        ),
        ("reglas sin regimen por defecto", lambda e: e.pop("regimen_por_defecto")),
        ("regimen por defecto inexistente", lambda e: e.update(regimen_por_defecto="nada")),
        (
            "regimen por defecto exento",
            lambda e: e.update(regimen_por_defecto="evidencia_insuficiente"),
        ),
        ("por defecto sin reglas", lambda e: e.update(reglas_regimen=[])),
        ("exentos sin evidencia insuficiente", lambda e: e.update(regimenes_exentos=["pasiva"])),
        (
            "exentos con regimen inexistente",
            lambda e: e.update(regimenes_exentos=["evidencia_insuficiente", "nada"]),
        ),
    ],
)
def test_esquema_invalido_se_rechaza(caso: str, cambio) -> None:
    errores = validar_esquema([]) if cambio is None else _con(cambio)
    assert errores, f"el caso '{caso}' tenía que dar errores"


def test_dimension_con_un_valor_nombra_la_dimension() -> None:
    errores = _con(lambda e: e["dimensiones"][2].update(valores=["presente"]))
    assert any("d3" in error for error in errores), errores


# ── 3.2 Respuesta parcial: formato y valores ──────────────────────────────


def test_guardado_parcial_de_una_dimension_es_valido() -> None:
    ev = evaluar_pedido(esquema_base(), {"respuestas": {"d1": _r("presente")}})
    assert ev.respuestas == {"d1": {"valor": "presente", "cita": "turno 1"}}
    assert ev.regimen is None
    assert ev.regimen_regla is None


@pytest.mark.parametrize(
    "pedido",
    [
        {"respuestas": {"d9": _r("presente")}},
        {"respuestas": {"d1": _r("quizas")}},
        {"respuestas": {"d1": {"valor": "presente", "cita": "x", "peso": 1}}},
        {"respuestas": {"d1": "presente"}},
        {"respuestas": [], "notas": "x"},
        {"respuestas": {}, "otra_cosa": 1},
        {"regimen": "nada"},
        {"regimen_propuesto": "nada", "notas": "x"},
        {"confianza": "altisima"},
        {"es_frontera": "si"},
    ],
)
def test_pedido_fuera_del_esquema_da_400(pedido: dict) -> None:
    with pytest.raises(PedidoInvalidoError) as exc:
        evaluar_pedido(esquema_base(), pedido)
    assert exc.value.status == 400


def test_frontera_rechazada_si_el_esquema_no_la_ofrece() -> None:
    esquema = esquema_base()
    esquema["marca_frontera"] = False
    esquema["notas_obligatorias_si_frontera"] = False
    with pytest.raises(PedidoInvalidoError) as exc:
        evaluar_pedido(esquema, {"es_frontera": True})
    assert exc.value.status == 400


def test_confianza_rechazada_si_el_esquema_no_la_define() -> None:
    esquema = esquema_base()
    esquema["confianza"] = None
    with pytest.raises(PedidoInvalidoError) as exc:
        evaluar_pedido(esquema, {"confianza": "alta"})
    assert exc.value.status == 400


# ── 3.2 Régimen según la regla ────────────────────────────────────────────


def test_regla_deriva_reflexiva_sin_regimen_en_el_pedido() -> None:
    ev = evaluar_pedido(esquema_base(), {"respuestas": REFLEXIVA})
    assert ev.regimen == "reflexiva"
    assert ev.regimen_regla == "reflexiva"
    assert ev.disiente_de_regla is False


def test_regimen_igual_al_derivado_se_acepta() -> None:
    ev = evaluar_pedido(esquema_base(), {"respuestas": REFLEXIVA, "regimen": "reflexiva"})
    assert ev.regimen == "reflexiva"


def test_regimen_distinto_del_derivado_da_422() -> None:
    with pytest.raises(PedidoInvalidoError) as exc:
        evaluar_pedido(esquema_base(), {"respuestas": REFLEXIVA, "regimen": "superficial"})
    assert exc.value.status == 422


def test_regimen_propuesto_con_nota_se_acepta_y_no_reemplaza_al_derivado() -> None:
    ev = evaluar_pedido(
        esquema_base(),
        {"respuestas": REFLEXIVA, "regimen_propuesto": "superficial", "notas": "porque"},
    )
    assert ev.regimen == "reflexiva"
    assert ev.regimen_propuesto == "superficial"
    assert ev.disiente_de_regla is True


@pytest.mark.parametrize("notas", [None, "", "   \n"])
def test_regimen_propuesto_sin_nota_da_422(notas) -> None:
    with pytest.raises(PedidoInvalidoError) as exc:
        evaluar_pedido(
            esquema_base(),
            {"respuestas": REFLEXIVA, "regimen_propuesto": "superficial", "notas": notas},
        )
    assert exc.value.status == 422


def test_regimen_propuesto_igual_al_derivado_no_disiente() -> None:
    ev = evaluar_pedido(
        esquema_base(),
        {"respuestas": REFLEXIVA, "regimen_propuesto": "reflexiva", "notas": "coincido"},
    )
    assert ev.regimen_propuesto == "reflexiva"
    assert ev.disiente_de_regla is False


def test_exento_elegido_sin_dimensiones_se_acepta_y_cierra() -> None:
    ev = evaluar_pedido(
        esquema_base(), {"regimen": "evidencia_insuficiente", "notas": "traza corta"}
    )
    assert ev.regimen == "evidencia_insuficiente"
    assert ev.regimen_regla is None
    assert faltantes_cierre(esquema_base(), ev) == []


def test_exento_con_dimensiones_completas_guarda_el_regimen_de_la_regla() -> None:
    """R3-1: `regimen_regla` se guarda siempre que sea calculable."""
    ev = evaluar_pedido(
        esquema_base(),
        {"respuestas": REFLEXIVA, "regimen": "evidencia_insuficiente", "notas": "dudosa"},
    )
    assert ev.regimen == "evidencia_insuficiente"
    assert ev.regimen_regla == "reflexiva"


def test_dimensiones_incompletas_dejan_regimen_regla_nulo() -> None:
    respuestas = {"d1": _r("presente"), "d2": _r("presente")}
    ev = evaluar_pedido(esquema_base(), {"respuestas": respuestas})
    assert ev.regimen is None
    assert ev.regimen_regla is None


def test_regimen_no_exento_con_dimensiones_incompletas_da_422() -> None:
    respuestas = {"d1": _r("presente"), "d2": _r("presente")}
    with pytest.raises(PedidoInvalidoError) as exc:
        evaluar_pedido(esquema_base(), {"respuestas": respuestas, "regimen": "reflexiva"})
    assert exc.value.status == 422


def test_ninguna_regla_se_cumple_da_el_regimen_por_defecto() -> None:
    respuestas = {**REFLEXIVA, "d4": _r("oraculo", None)}
    assert derivar_regimen(esquema_base(), respuestas) == "superficial"


def test_pasiva_exige_cita_en_el_atomo_con_cita() -> None:
    sin_cita = {
        "d1": _r("ausente", None),
        "d2": _r("ausente", None),
        "d3": _r("ausente", None),
        "d4": _r("transferencia", "  "),
    }
    con_cita = {**sin_cita, "d4": _r("transferencia", "turno 4")}
    assert derivar_regimen(esquema_base(), con_cita) == "pasiva"
    assert derivar_regimen(esquema_base(), sin_cita) == "superficial"


def test_la_primera_regla_que_se_cumple_gana() -> None:
    esquema = esquema_base()
    esquema["reglas_regimen"] = [
        {"regimen": "reflexiva", "condicion": [[_atomo("d1", "presente")]]},
        {"regimen": "pasiva", "condicion": [[_atomo("d2", "presente")]]},
    ]
    assert validar_esquema(esquema) == []
    respuestas = {"d1": _r("presente"), "d2": _r("presente")}
    assert derivar_regimen(esquema, respuestas) == "reflexiva"
    assert derivar_regimen(esquema, {**respuestas, "d1": _r("ausente", None)}) == "pasiva"


def test_sin_reglas_el_codificador_elige_el_regimen() -> None:
    esquema = esquema_base()
    esquema["reglas_regimen"] = []
    del esquema["regimen_por_defecto"]
    ev = evaluar_pedido(esquema, {"respuestas": REFLEXIVA, "regimen": "pasiva"})
    assert ev.regimen == "pasiva"
    assert ev.regimen_regla is None


def test_esquema_del_pedido_no_se_modifica() -> None:
    esquema = esquema_base()
    copia = copy.deepcopy(esquema)
    evaluar_pedido(esquema, {"respuestas": REFLEXIVA})
    assert esquema == copia


# ── 3.2 Completitud para el cierre ────────────────────────────────────────


def _completo(**extra) -> dict:
    return {"respuestas": dict(REFLEXIVA), **extra}


def test_etiqueta_completa_no_tiene_faltantes() -> None:
    ev = evaluar_pedido(esquema_base(), _completo())
    assert faltantes_cierre(esquema_base(), ev) == []


def test_sin_regimen_falta_el_regimen() -> None:
    ev = evaluar_pedido(esquema_base(), {"respuestas": {"d1": _r("presente")}})
    assert "regimen" in faltantes_cierre(esquema_base(), ev)


@pytest.mark.parametrize("cita", [None, "", "   "])
def test_cita_requerida_vacia_o_con_espacios_falta(cita) -> None:
    ev = evaluar_pedido(
        esquema_base(), _completo(respuestas={**REFLEXIVA, "d1": _r("presente", cita)})
    )
    assert faltantes_cierre(esquema_base(), ev) == ["cita:d1"]


def test_cita_no_requerida_para_el_valor_no_falta() -> None:
    """`d3` vale `ausente`, que no está en su `cita_requerida_si`."""
    ev = evaluar_pedido(esquema_base(), _completo())
    assert ev.respuestas.get("d3") == {"valor": "ausente", "cita": None}
    assert "cita:d3" not in faltantes_cierre(esquema_base(), ev)


def test_exento_sin_notas_falta_la_nota() -> None:
    ev = evaluar_pedido(esquema_base(), {"regimen": "evidencia_insuficiente"})
    assert faltantes_cierre(esquema_base(), ev) == ["notas"]


def test_frontera_sin_notas_falta_la_nota() -> None:
    ev = evaluar_pedido(esquema_base(), _completo(es_frontera=True))
    assert faltantes_cierre(esquema_base(), ev) == ["notas"]


def test_confianza_obligatoria_ausente_falta() -> None:
    esquema = esquema_base()
    esquema["confianza"]["obligatoria"] = True
    ev = evaluar_pedido(esquema, _completo())
    assert faltantes_cierre(esquema, ev) == ["confianza"]


def test_dimension_sin_valor_falta_si_el_regimen_no_la_exceptua() -> None:
    esquema = esquema_base()
    esquema["reglas_regimen"] = []
    del esquema["regimen_por_defecto"]
    respuestas = {k: v for k, v in REFLEXIVA.items() if k != "d3"}
    ev = evaluar_pedido(esquema, {"respuestas": respuestas, "regimen": "pasiva"})
    assert faltantes_cierre(esquema, ev) == ["dimension:d3"]


# ── Respuesta esperada de un ancla contra el esquema vigente (verify-1, F1) ──


def test_ancla_coherente_con_la_regla_vale() -> None:
    esperada = {"respuestas": REFLEXIVA, "regimen": "reflexiva"}
    assert errores_respuesta_esperada(esquema_base(), esperada) == []


def test_ancla_con_regimen_que_la_regla_ya_no_da_no_vale() -> None:
    esquema = esquema_base()
    esquema["reglas_regimen"][0]["condicion"][2] = [{"dimension": "d4", "en": ["oraculo"]}]
    errores = errores_respuesta_esperada(esquema, {"respuestas": REFLEXIVA, "regimen": "reflexiva"})
    assert errores and "superficial" in errores[0]


def test_ancla_con_dimension_que_el_esquema_ya_no_tiene_no_vale() -> None:
    esquema = esquema_base()
    esquema["dimensiones"].append(_dim("d5"))
    esperada = {"respuestas": {**REFLEXIVA, "d9": _r("presente")}, "regimen": "reflexiva"}
    assert errores_respuesta_esperada(esquema, esperada) == [
        "respuestas: dimensión desconocida 'd9'"
    ]


def test_ancla_exenta_vale_aunque_la_regla_derive_otro() -> None:
    esperada = {"respuestas": REFLEXIVA, "regimen": "evidencia_insuficiente", "notas": "n"}
    assert errores_respuesta_esperada(esquema_base(), esperada) == []


def test_ancla_con_regimen_nulo_no_vale_si_la_regla_ya_deriva() -> None:
    esperada = {"respuestas": REFLEXIVA, "regimen": None}
    assert errores_respuesta_esperada(esquema_base(), esperada) == [
        "regimen: el ancla espera 'None' y la regla da 'reflexiva'"
    ]


def test_ancla_incompleta_con_regimen_nulo_vale() -> None:
    assert errores_respuesta_esperada(esquema_base(), {"respuestas": {"d1": _r("presente")}}) == []


def test_ancla_sin_reglas_con_regimen_elegido_vale() -> None:
    esquema = esquema_base()
    esquema["reglas_regimen"] = []
    del esquema["regimen_por_defecto"]
    esperada = {"respuestas": REFLEXIVA, "regimen": "pasiva"}
    assert errores_respuesta_esperada(esquema, esperada) == []


# ── Tipos inválidos donde va una clave (verify-1, F2 y F3) ───────────────────


@pytest.mark.parametrize("campo", ["regimen", "regimen_propuesto"])
@pytest.mark.parametrize("valor", [["reflexiva"], {"clave": "reflexiva"}])
def test_regimen_no_textual_es_400_y_no_excepcion(campo, valor) -> None:
    with pytest.raises(PedidoInvalidoError) as e:
        evaluar_pedido(esquema_base(), {"respuestas": {}, campo: valor, "notas": "n"})
    assert e.value.status == 400
    assert e.value.errores == [f"{campo}: fuera del esquema"]


@pytest.mark.parametrize(
    "cambio",
    [
        lambda e: e.update(regimen_evidencia_insuficiente=["evidencia_insuficiente"]),
        lambda e: e.update(regimen_por_defecto=["superficial"]),
        lambda e: e.update(regimenes_exentos=[["evidencia_insuficiente"]]),
        lambda e: e.update(notas_obligatorias_si_regimen=[{"x": 1}]),
        lambda e: e["reglas_regimen"][0].update(regimen=["reflexiva"]),
        lambda e: e["reglas_regimen"][0]["condicion"][0][0].update(dimension=["d1"]),
    ],
)
def test_esquema_con_lista_u_objeto_donde_va_una_clave_da_errores(cambio) -> None:
    assert _con(cambio)
