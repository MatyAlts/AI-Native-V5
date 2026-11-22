"""Aceptación HU-001: juez v2 alineado al codebook MTAC v1.

Escrita por el orquestador ANTES de construir (método Rein, nivel L). El
constructor NO modifica este archivo ni `datos/`. Cada prueba lleva el
criterio de `HISTORIAS.md` que decide.

Contrato que estas pruebas fijan (lo que el constructor tiene que crear):

`classifier_service.services.regla_mtac`
    regimen_segun_regla_mtac(d1, d2, d3, d4) -> "REFLEXIVA" | "SUPERFICIAL" | "PASIVA" | "INDETERMINADO"
    d1..d3 en {"presente","ausente","no_evaluable"}; d4 en {"interlocutor","oraculo","transferencia","no_evaluable"}.
    Único lugar del código con la regla MTAC v1 (K02).

`classifier_service.services.juez_v2`
    JUEZ_VERSION = "v2"; PROMPT_VERSION_V2 (empieza con "mtac_v1_juez_v2");
    SYSTEM_PROMPT_V2; EJEMPLOS_FRONTERA_V2 (lista de {"d4","fuente","texto"});
    HUELLA_PROMPT_V2 y huella_prompt_v2(); RegimenV2Raw; RESPONSE_JSON_SCHEMA_V2;
    RegimenV2Result; SUBGRUPOS_JUZGADOS_POR_JUEZ_V2; SUBGRUPOS_PASIVA_ETAPA_DURA;
    REGIMEN_V2_TO_APPROPRIATION; armar_traza_v2(events); construir_mensajes_v2(traza, enunciado, episode_id);
    async clasificar_regimen_v2(*, events, enunciado, episode_id, complete, model, tenant_id,
                                materia_id=None, confianza_min=0.70, max_tokens=6000).

`classifier_service.config.settings.eje_fino_juez_version` en {"v1","v2"}, default "v1".
`classifier_service.routes.classify_ep` importa `clasificar_regimen_v2` a nivel de módulo y
`_aplicar_juez_eje_fino` elige el juez según esa configuración.

Precisión de C05 (20/11, ver HISTORIAS): la evidencia de cada dimensión es
`{valor, localizador, cita}`. Los localizadores siguen la numeración que ven los
codificadores humanos en la traza ciega (`mensaje N`, `ejecución N`, `prueba N`,
`nota N`, `edición N`). La `cita` tiene que ser textual de algo que escribió el
alumno (mensaje, nota o código), nunca del tutor. D2 puede probarse sin cita con
un localizador de ejecución o prueba que exista (el codebook acepta verificación
por acciones).
"""

from __future__ import annotations

import hashlib
import json
import logging
import pathlib
import re
from itertools import product
from types import SimpleNamespace
from uuid import UUID

import pytest

DATOS = pathlib.Path(__file__).parent / "datos"
RAIZ = pathlib.Path(__file__).resolve().parents[4]
TENANT = UUID("00000000-0000-0000-0000-0000000000aa")

D123 = ("presente", "ausente", "no_evaluable")
D4 = ("interlocutor", "oraculo", "transferencia", "no_evaluable")


# ── Episodio sintético (inventado, no viene de ningún alumno) ───────────────
def _ev(seq: int, tipo: str, payload: dict) -> dict:
    return {
        "seq": seq,
        "event_type": tipo,
        "ts": f"2026-11-20T10:{seq // 60:02d}:{seq % 60:02d}Z",
        "payload": payload,
    }


MSG1 = "uso un while porque no sé cuántas veces el usuario va a ingresar datos"
MSG2 = "corta cuando ingresa cero, espero que la suma dé 15 si cargo 5 y 10"
MSG3 = "dio 15 como esperaba, entonces el acumulador arranca bien en cero"
TUTOR1 = "¿Qué condición debería cortar el ciclo? Pensá en el valor centinela."
CODIGO = (
    "suma = 0\nn = int(input())\nwhile n != 0:\n    suma += n\n    n = int(input())\nprint(suma)"
)


def episodio() -> list[dict]:
    return [
        _ev(0, "episodio_abierto", {"language": "python"}),
        _ev(1, "prompt_enviado", {"content": MSG1}),
        _ev(2, "tutor_respondio", {"content": TUTOR1}),
        _ev(3, "prompt_enviado", {"content": MSG2}),
        _ev(4, "edicion_codigo", {"snapshot": CODIGO, "language": "python"}),
        _ev(5, "codigo_ejecutado", {"code": CODIGO, "stdout": "15\n", "stderr": ""}),
        _ev(6, "intento_adverso_detectado", {"category": "overuse", "severity": 1}),
        _ev(
            7,
            "tests_ejecutados",
            {"test_count_total": 2, "test_count_passed": 2, "test_count_failed": 0},
        ),
        _ev(8, "prompt_enviado", {"content": MSG3}),
        _ev(9, "episodio_cerrado", {}),
    ]


def _dim(valor: str, localizador: str = "", cita: str = "") -> dict:
    return {"valor": valor, "localizador": localizador, "cita": cita}


def salida(
    d1=("presente", "mensaje 1", "uso un while porque no sé cuántas veces"),
    d2=("presente", "mensaje 3", "dio 15 como esperaba"),
    d3=("presente", "mensaje 1", "no sé cuántas veces el usuario va a ingresar datos"),
    d4=("interlocutor", "mensaje 2", "espero que la suma dé 15"),
    regimen="REFLEXIVA",
    confianza=0.9,
) -> dict:
    return {
        "d1_verbalizacion": _dim(*d1),
        "d2_verificacion": _dim(*d2),
        "d3_justificacion": _dim(*d3),
        "d4_autonomia": _dim(*d4),
        "regimen": regimen,
        "confianza": confianza,
        "justificacion_global": "texto",
    }


class Completar:
    """Mock del cliente del ai-gateway: registra cada llamada."""

    def __init__(self, contenido: str, output_tokens: int = 200, provider: str = "openrouter"):
        self.contenido = contenido
        self.output_tokens = output_tokens
        self.provider = provider
        self.llamadas: list[dict] = []

    async def __call__(self, **kw):
        self.llamadas.append(kw)
        return SimpleNamespace(
            content=self.contenido,
            output_tokens=self.output_tokens,
            provider=self.provider,
            model=kw.get("model"),
        )


async def juzgar(datos: dict | str, **kw):
    from classifier_service.services.juez_v2 import clasificar_regimen_v2

    contenido = datos if isinstance(datos, str) else json.dumps(datos, ensure_ascii=False)
    completar = kw.pop("completar", None) or Completar(contenido)
    res = await clasificar_regimen_v2(
        events=kw.pop("events", episodio()),
        enunciado="Sumar números hasta que se ingrese cero.",
        episode_id="00000000-0000-0000-0000-00000000e001",
        complete=completar,
        model="google/gemini-2.5-flash",
        tenant_id=TENANT,
        **kw,
    )
    return res, completar


# ── C01 / N02: con la configuración por defecto nada cambia ─────────────────
HUELLA_V1 = "08d6383160392a5d3852f8e60de6653c09576c35594a654a8d016e5662d05fbc"


def test_c01_config_por_defecto_es_v1():
    from classifier_service.config import settings

    assert settings.eje_fino_juez_version == "v1"


def test_c01_prompt_y_regla_v1_intactos():
    from classifier_service.services import regimen_llm as r

    huella = hashlib.sha256(
        (
            r.SYSTEM_PROMPT
            + json.dumps(r._FEWSHOT, ensure_ascii=False, sort_keys=True)
            + json.dumps(r.RESPONSE_JSON_SCHEMA, sort_keys=True)
        ).encode()
    ).hexdigest()
    assert huella == HUELLA_V1
    assert r.PROMPT_VERSION == "eje_fino_v1.2.0"


def test_c01_classifier_config_hash_intacto():
    from classifier_service.services.pipeline import (
        DEFAULT_REFERENCE_PROFILE,
        compute_classifier_config_hash,
    )

    # Lo que este criterio protege es que el JUEZ no entre al hash. HU-009
    # (20/11) sube tree_version a proposito (Probar cuenta en el subgrupo), asi
    # que se fija el hash de v4.1.0 con su tree_version explicito: si el juez
    # entrara a la formula, este valor se moveria igual.
    assert (
        compute_classifier_config_hash(DEFAULT_REFERENCE_PROFILE, "v4.1.0")
        == "56f3905858c19def2f20741a03378e9d5e3dfe1a4f0e4dd75d7440367fdc1180"
    )


def _resultado(subgrupo: str, appropriation: str):
    return SimpleNamespace(
        appropriation=appropriation,
        reason="proxy",
        features={"subgrupo": {"key": subgrupo}},
    )


def _instrumentar(monkeypatch, version: str, v1=None, v2=None):
    from classifier_service.config import settings
    from classifier_service.routes import classify_ep

    llamados = {"v1": 0, "v2": 0}

    async def _v1(**kw):
        llamados["v1"] += 1
        return v1

    async def _v2(**kw):
        llamados["v2"] += 1
        return v2

    monkeypatch.setattr(settings, "eje_fino_llm_enabled", True)
    monkeypatch.setattr(settings, "eje_fino_juez_version", version)
    monkeypatch.setattr(classify_ep, "clasificar_regimen_llm", _v1)
    monkeypatch.setattr(classify_ep, "clasificar_regimen_v2", _v2)
    monkeypatch.setattr(classify_ep, "AIGatewayClient", lambda **kw: SimpleNamespace(complete=None))
    return classify_ep, llamados


def _res_v1_ok():
    from classifier_service.services.regimen_llm import RegimenLLMResult

    return RegimenLLMResult(
        estado="ok",
        regimen="REFLEXIVA",
        confianza=0.9,
        raw=None,
        razon="ok",
        model_used="m",
        prompt_version="eje_fino_v1.2.0",
    )


async def test_c01_por_defecto_corre_el_juez_v1_y_no_el_v2(monkeypatch):
    classify_ep, llamados = _instrumentar(monkeypatch, "v1", v1=_res_v1_ok())
    res = _resultado("colaborador_funcional", "apropiacion_superficial")
    await classify_ep._aplicar_juez_eje_fino(res, episodio(), UUID(int=1), {}, TENANT)
    assert llamados == {"v1": 1, "v2": 0}
    assert res.appropriation == "apropiacion_reflexiva"


async def test_n02_por_defecto_la_pasiva_sigue_en_la_etapa_dura(monkeypatch):
    classify_ep, llamados = _instrumentar(monkeypatch, "v1", v1=_res_v1_ok())
    for sg in ("dependiente_sobreuso", "dependiente_delegador"):
        res = _resultado(sg, "delegacion_pasiva")
        await classify_ep._aplicar_juez_eje_fino(res, episodio(), UUID(int=1), {}, TENANT)
        assert res.appropriation == "delegacion_pasiva"
    assert llamados == {"v1": 0, "v2": 0}


# ── C02: contrato de salida ─────────────────────────────────────────────────
def test_c02_schema_acepta_la_salida_valida():
    from classifier_service.services.juez_v2 import RegimenV2Raw

    raw = RegimenV2Raw.model_validate(salida())
    assert raw.d4_autonomia.valor == "interlocutor"


@pytest.mark.parametrize(
    "campo,valor",
    [
        ("d4_autonomia", "presente"),
        ("d1_verbalizacion", "interlocutor"),
        ("d2_verificacion", "oraculo"),
    ],
)
def test_c02_schema_rechaza_valores_fuera_de_dominio(campo, valor):
    from classifier_service.services.juez_v2 import RegimenV2Raw
    from pydantic import ValidationError

    datos = salida()
    datos[campo]["valor"] = valor
    with pytest.raises(ValidationError):
        RegimenV2Raw.model_validate(datos)


def test_c02_schema_rechaza_claves_extra():
    from classifier_service.services.juez_v2 import RegimenV2Raw
    from pydantic import ValidationError

    datos = salida()
    datos["subgrupo"] = "dependiente_sobreuso"
    with pytest.raises(ValidationError):
        RegimenV2Raw.model_validate(datos)


def test_c02_json_schema_que_viaja_al_modelo():
    from classifier_service.services.juez_v2 import RESPONSE_JSON_SCHEMA_V2

    props = RESPONSE_JSON_SCHEMA_V2["json_schema"]["schema"]["properties"]
    for d in ("d1_verbalizacion", "d2_verificacion", "d3_justificacion"):
        assert set(props[d]["properties"]["valor"]["enum"]) == set(D123)
        assert set(props[d]["required"]) == {"valor", "localizador", "cita"}
    assert set(props["d4_autonomia"]["properties"]["valor"]["enum"]) == set(D4)
    assert set(props["regimen"]["enum"]) == {
        "REFLEXIVA",
        "SUPERFICIAL",
        "PASIVA",
        "EVIDENCIA_INSUFICIENTE",
    }


# ── C03: la regla en código, tabla de verdad completa ───────────────────────
def _k(v):
    return {"presente": True, "ausente": False}.get(v)


def _y(*xs):
    if any(x is False for x in xs):
        return False
    if any(x is None for x in xs):
        return None
    return True


def _o(*xs):
    if any(x is True for x in xs):
        return True
    if any(x is None for x in xs):
        return None
    return False


def _no(x):
    return None if x is None else not x


def oraculo_regla(d1, d2, d3, d4):
    """Implementación independiente de la regla MTAC v1 con Kleene fuerte."""
    d4i = None if d4 == "no_evaluable" else d4 == "interlocutor"
    d4t = None if d4 == "no_evaluable" else d4 == "transferencia"
    reflexiva = _y(_k(d1), _o(_k(d2), _k(d3)), d4i)
    pasiva = _y(d4t, _no(_o(_k(d1), _k(d2), _k(d3))))
    if reflexiva is True:
        return "REFLEXIVA"
    if pasiva is True:
        return "PASIVA"
    if reflexiva is False and pasiva is False:
        return "SUPERFICIAL"
    return "INDETERMINADO"


def test_c03_tabla_de_verdad_completa_108_combinaciones():
    from classifier_service.services.regla_mtac import regimen_segun_regla_mtac

    combinaciones = list(product(D123, D123, D123, D4))
    assert len(combinaciones) == 108
    distintas = [
        (c, regimen_segun_regla_mtac(*c), oraculo_regla(*c))
        for c in combinaciones
        if regimen_segun_regla_mtac(*c) != oraculo_regla(*c)
    ]
    assert distintas == []


ESQUEMA_ESTUDIO = json.loads((DATOS / "esquema_mtac_v1_estudio.json").read_text())


def test_c03_coincide_con_la_regla_del_estudio_en_las_24_combinaciones_evaluables():
    """La regla del juez es la misma que derivó el régimen de los codificadores."""
    from classifier_service.services.estudio_esquema import derivar_regimen
    from classifier_service.services.regla_mtac import regimen_segun_regla_mtac

    claves = ("d1_verbalizacion", "d2_verificacion", "d3_justificacion", "d4_autonomia")
    for combo in product(
        ("presente", "ausente"), ("presente", "ausente"), ("presente", "ausente"), D4[:3]
    ):
        respuestas = {
            k: {"valor": v, "cita": "mensaje 1"} for k, v in zip(claves, combo, strict=False)
        }
        estudio = derivar_regimen(ESQUEMA_ESTUDIO, respuestas).upper()
        assert regimen_segun_regla_mtac(*combo) == estudio, combo


@pytest.mark.parametrize(
    "dims,esperado",
    [
        (("presente", "presente", "presente", "interlocutor"), "REFLEXIVA"),  # ancla 9a54cd3b
        (("ausente", "presente", "ausente", "interlocutor"), "SUPERFICIAL"),  # ancla 11007e5f
        (("ausente", "presente", "ausente", "oraculo"), "SUPERFICIAL"),  # ancla 2c3a952b
        (("ausente", "ausente", "ausente", "transferencia"), "PASIVA"),  # ancla 622a9ba0
        (("presente", "ausente", "ausente", "transferencia"), "SUPERFICIAL"),
        (("ausente", "ausente", "ausente", "no_evaluable"), "INDETERMINADO"),
    ],
)
def test_c03_anclas_consensuadas(dims, esperado):
    from classifier_service.services.regla_mtac import regimen_segun_regla_mtac

    assert regimen_segun_regla_mtac(*dims) == esperado


# ── C04 / N03: el régimen lo decide la regla, no el modelo ──────────────────
async def test_c04_n03_reflexiva_con_d4_oraculo_no_termina_reflexiva():
    res, _ = await juzgar(
        salida(d4=("oraculo", "mensaje 2", "espero que la suma dé 15"), regimen="REFLEXIVA")
    )
    assert res.estado == "inconsistente"
    assert res.regimen is None
    assert res.raw is not None  # se conserva todo para auditar


async def test_c04_superficial_cuando_la_regla_dice_pasiva_es_inconsistente():
    datos = salida(
        d1=("ausente", "", ""),
        d2=("ausente", "", ""),
        d3=("ausente", "", ""),
        d4=("transferencia", "mensaje 2", "espero que la suma dé 15"),
        regimen="SUPERFICIAL",
    )
    res, _ = await juzgar(datos)
    assert res.estado == "inconsistente"


async def test_c04_regimen_consistente_gobierna():
    res, _ = await juzgar(salida())
    assert (res.estado, res.regimen) == ("ok", "REFLEXIVA")


async def test_c04_pasiva_consistente_gobierna():
    datos = salida(
        d1=("ausente", "", ""),
        d2=("ausente", "", ""),
        d3=("ausente", "", ""),
        d4=("transferencia", "mensaje 2", "espero que la suma dé 15"),
        regimen="PASIVA",
    )
    res, _ = await juzgar(datos)
    assert (res.estado, res.regimen) == ("ok", "PASIVA")


async def test_caso_4_regla_indecisa_se_abstiene():
    datos = salida(
        d1=("no_evaluable", "", ""),
        d2=("no_evaluable", "", ""),
        d3=("no_evaluable", "", ""),
        d4=("no_evaluable", "", ""),
        regimen="EVIDENCIA_INSUFICIENTE",
    )
    res, _ = await juzgar(datos)
    assert res.estado == "abstencion_traza_insuficiente"
    assert res.regimen is None


# ── C05 / N04: las citas se verifican contra la traza ───────────────────────
async def test_c05_cita_textual_tolera_mayusculas_y_espacios():
    datos = salida(d1=("presente", "mensaje 1", "USO un   while porque"))
    res, _ = await juzgar(datos)
    assert res.estado == "ok"


async def test_c05_cita_del_tutor_da_salida_invalida():
    datos = salida(d1=("presente", "mensaje 1", "Pensá en el valor centinela"))
    res, _ = await juzgar(datos)
    assert res.estado == "salida_invalida"
    assert res.regimen is None


async def test_n04_parafrasis_no_pasa_como_cita():
    datos = salida(d1=("presente", "mensaje 1", "usa while porque no conoce la cantidad de datos"))
    res, _ = await juzgar(datos)
    assert res.estado == "salida_invalida"


async def test_c05_dimension_presente_sin_cita_ni_localizador_verificable():
    datos = salida(d3=("presente", "", ""))
    res, _ = await juzgar(datos)
    assert res.estado == "derivado_evidencia_insuficiente"
    assert res.regimen is None


async def test_c05_verificacion_por_acciones_con_localizador_de_ejecucion():
    datos = salida(d2=("presente", "ejecución 1, prueba 1", ""))
    res, _ = await juzgar(datos)
    assert res.estado == "ok"


@pytest.mark.parametrize("localizador", ["ejecución 7", "mensaje 9", "prueba 3"])
async def test_c05_localizador_inexistente_da_salida_invalida(localizador):
    datos = salida(d2=("presente", localizador, ""))
    res, _ = await juzgar(datos)
    assert res.estado == "salida_invalida"


async def test_c05_cita_del_codigo_del_alumno_vale():
    datos = salida(d3=("presente", "edición 1", "while n != 0:"))
    res, _ = await juzgar(datos)
    assert res.estado == "ok"


# ── Traza: el juez ve la misma evidencia que el codificador humano ──────────
def test_traza_v2_tiene_localizadores_salidas_y_pruebas():
    from classifier_service.services.juez_v2 import armar_traza_v2

    traza = armar_traza_v2(episodio())
    for esperado in (
        "mensaje 1",
        "mensaje 2",
        "mensaje 3",
        "ejecución 1",
        "prueba 1",
        MSG1,
        TUTOR1,
    ):
        assert esperado in traza, esperado
    assert "15" in traza.split("ejecución 1", 1)[1]  # la salida de la ejecución viaja
    assert "2/2" in traza.split("prueba 1", 1)[1] or "2 de 2" in traza.split("prueba 1", 1)[1]


def test_traza_v2_es_ciega_a_las_marcas_del_sistema():
    from classifier_service.services.juez_v2 import armar_traza_v2

    traza = armar_traza_v2(episodio()).lower()
    assert "overuse" not in traza
    assert "intento_adverso" not in traza
    assert "sobreuso" not in traza


def test_mensajes_v2_llevan_prompt_y_traza():
    from classifier_service.services.juez_v2 import (
        SYSTEM_PROMPT_V2,
        armar_traza_v2,
        construir_mensajes_v2,
    )

    traza = armar_traza_v2(episodio())
    msgs = construir_mensajes_v2(traza, "enunciado X", "id-1")
    assert msgs[0] == {"role": "system", "content": SYSTEM_PROMPT_V2}
    assert traza in msgs[-1]["content"] and "enunciado X" in msgs[-1]["content"]


# ── C06: frontera explicada con ejemplos de afuera de los 150 ───────────────
def test_c06_dos_ejemplos_por_valor_de_d4_y_dentro_del_prompt():
    from classifier_service.services.juez_v2 import EJEMPLOS_FRONTERA_V2, SYSTEM_PROMPT_V2

    for valor in ("interlocutor", "oraculo", "transferencia"):
        ejemplos = [e for e in EJEMPLOS_FRONTERA_V2 if e["d4"] == valor]
        assert len(ejemplos) >= 2, valor
        for e in ejemplos:
            assert e["texto"] in SYSTEM_PROMPT_V2
            assert e["fuente"].strip()


@pytest.mark.parametrize(
    "idea",
    [
        r"narrar no es razonar",
        r"ejecutar no es verificar",
        r"predomin",  # D4 por patrón predominante
        r"falta de evidencia",  # la pasiva no se asigna por falta de evidencia
        r"(cantidad|ritmo).{0,80}(mensajes|ejecuciones)",  # la actividad no decide
        r"construye|incorpora",  # frontera pasiva/superficial
    ],
)
def test_c06_prompt_contiene_las_fronteras_del_codebook(idea):
    from classifier_service.services.juez_v2 import SYSTEM_PROMPT_V2

    assert re.search(idea, SYSTEM_PROMPT_V2, re.IGNORECASE | re.DOTALL), idea


# ── C07: lo persistido es auditable y se sigue leyendo lo viejo ─────────────
async def test_c07_resultado_persistible_completo():
    res, _ = await juzgar(salida())
    dump = res.model_dump(mode="json")
    from classifier_service.services.juez_v2 import JUEZ_VERSION, PROMPT_VERSION_V2

    assert dump["prompt_version"] == PROMPT_VERSION_V2
    assert dump["juez_version"] == JUEZ_VERSION == "v2"
    assert dump["model_used"] == "google/gemini-2.5-flash"
    assert dump["estado"] == "ok" and dump["razon"]
    for d in ("d1_verbalizacion", "d2_verificacion", "d3_justificacion", "d4_autonomia"):
        assert set(dump["raw"][d]) >= {"valor", "localizador", "cita"}


async def test_c07_normalizar_lee_registros_v1_y_v2():
    from classifier_service.services.regimen_llm import normalizar_regimen_llm_persistido

    v1_legado = {
        "estado": "ok",
        "regimen": "SUPERFICIAL",
        "confianza": 0.8,
        "raw": {
            "verbalizacion": {"presente": False, "evidencia": ""},
            "verificacion": {"presente": False, "evidencia": ""},
            "justificacion": {"presente": False, "evidencia": ""},
            "autonomia": {"oraculo": True, "evidencia": "x"},
            "regimen": "SUPERFICIAL",
            "confianza": 0.8,
            "justificacion_global": "x",
        },
        "razon": "x",
        "model_used": "m",
        "prompt_version": "eje_fino_v1.1.0",
    }
    assert normalizar_regimen_llm_persistido(v1_legado)["raw"]["autonomia"]["presente"] == "ausente"

    res, _ = await juzgar(salida())
    v2 = normalizar_regimen_llm_persistido(res.model_dump(mode="json"))
    assert v2["juez_version"] == "v2"
    assert v2["regimen"] == "REFLEXIVA"
    assert v2["raw"]["d4_autonomia"]["valor"] == "interlocutor"


# ── C08: sin proveedor real no hay mock silencioso ──────────────────────────
async def test_c08_proveedor_mock_da_estado_explicito_y_log(caplog):
    caplog.set_level(logging.WARNING)
    completar = Completar(json.dumps(salida()), provider="mock")
    res, _ = await juzgar(salida(), completar=completar)
    assert res.estado == "proveedor_no_disponible"
    assert res.regimen is None
    assert any(
        "mock" in r.getMessage().lower() or "mock" in str(r.__dict__).lower()
        for r in caplog.records
    )


# ── C09: reproducibilidad y truncado ────────────────────────────────────────
async def test_c09_temperatura_cero_modelo_y_techo_viajan():
    from classifier_service.services.juez_v2 import RESPONSE_JSON_SCHEMA_V2

    _, completar = await juzgar(salida(), max_tokens=4321)
    llamada = completar.llamadas[0]
    assert llamada["temperature"] == 0.0
    assert llamada["model"] == "google/gemini-2.5-flash"
    assert llamada["max_tokens"] == 4321
    assert llamada["response_format"] == RESPONSE_JSON_SCHEMA_V2


async def test_c09_respuesta_truncada_no_se_reintenta():
    truncada = json.dumps(salida())[:120]
    completar = Completar(truncada, output_tokens=6000)
    res, _ = await juzgar(salida(), completar=completar, max_tokens=6000)
    assert res.estado == "error_parseo"
    assert len(completar.llamadas) == 1
    assert "trunc" in res.razon.lower()


# ── C10: prompt congelado por huella ────────────────────────────────────────
def test_c10_huella_del_prompt_v2_declarada():
    from classifier_service.services import juez_v2

    assert juez_v2.huella_prompt_v2() == juez_v2.HUELLA_PROMPT_V2
    assert re.fullmatch(r"[0-9a-f]{64}", juez_v2.HUELLA_PROMPT_V2)
    assert juez_v2.PROMPT_VERSION_V2.startswith("mtac_v1_juez_v2")


# ── C11: con v2 la pasiva sale del juez ─────────────────────────────────────
def _res_v2(estado: str, regimen: str | None):
    return SimpleNamespace(
        estado=estado,
        regimen=regimen,
        razon="r",
        model_dump=lambda mode="json": {"estado": estado, "regimen": regimen, "juez_version": "v2"},
    )


@pytest.mark.parametrize(
    "regimen,esperado",
    [
        ("PASIVA", "delegacion_pasiva"),
        ("SUPERFICIAL", "apropiacion_superficial"),
        ("REFLEXIVA", "apropiacion_reflexiva"),
    ],
)
async def test_c11_sobreuso_pasa_por_el_juez_v2(monkeypatch, regimen, esperado):
    classify_ep, llamados = _instrumentar(monkeypatch, "v2", v2=_res_v2("ok", regimen))
    res = _resultado("dependiente_sobreuso", "delegacion_pasiva")
    await classify_ep._aplicar_juez_eje_fino(res, episodio(), UUID(int=1), {}, TENANT)
    assert llamados == {"v1": 0, "v2": 1}
    assert res.appropriation == esperado
    assert res.features["regimen_llm"]["juez_version"] == "v2"


async def test_c11_sin_veredicto_la_ex_pasiva_no_vuelve_a_pasiva(monkeypatch):
    classify_ep, _ = _instrumentar(monkeypatch, "v2", v2=_res_v2("salida_invalida", None))
    res = _resultado("dependiente_delegador", "delegacion_pasiva")
    await classify_ep._aplicar_juez_eje_fino(res, episodio(), UUID(int=1), {}, TENANT)
    assert res.appropriation == "sin_clasificar"
    assert res.features["needs_review"] is True


async def test_c11_sin_veredicto_un_colaborador_conserva_el_proxy(monkeypatch):
    classify_ep, _ = _instrumentar(monkeypatch, "v2", v2=_res_v2("baja_confianza", None))
    res = _resultado("colaborador_funcional", "apropiacion_superficial")
    await classify_ep._aplicar_juez_eje_fino(res, episodio(), UUID(int=1), {}, TENANT)
    assert res.appropriation == "apropiacion_superficial"
    assert res.features["needs_review"] is True


async def test_c11_el_eje_autonomo_no_pasa_por_el_juez(monkeypatch):
    classify_ep, llamados = _instrumentar(monkeypatch, "v2", v2=_res_v2("ok", "PASIVA"))
    res = _resultado("autonomo_resolutor", "autonomo")
    await classify_ep._aplicar_juez_eje_fino(res, episodio(), UUID(int=1), {}, TENANT)
    assert llamados == {"v1": 0, "v2": 0}
    assert res.appropriation == "autonomo"


# ── N01: nada de los 150 en el prompt ───────────────────────────────────────
HUELLAS = json.loads((DATOS / "huellas_muestra_150.json").read_text())


def _h(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()[:16]


def coincidencias_con_la_muestra(texto: str) -> list[str]:
    ids = set(HUELLAS["ids"])
    frag = set(HUELLAS["fragmentos"])
    hallados = []
    for tok in re.findall(
        r"[0-9a-f]{8}(?:-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})?", texto.lower()
    ):
        if _h(tok) in ids:
            hallados.append(f"id:{_h(tok)}")
    palabras = re.findall(r"\w+", texto.lower())
    for i in range(len(palabras) - 7):
        if _h(" ".join(palabras[i : i + 8])) in frag:
            hallados.append(f"frag:{i}")
    return hallados


def test_n01_el_detector_detecta():
    """El detector no es decorativo: encuentra una huella plantada."""
    frase = "esta es una frase plantada de ocho palabras exactas"
    HUELLAS["fragmentos"].append(_h(" ".join(re.findall(r"\w+", frase)[:8])))
    try:
        assert coincidencias_con_la_muestra("bla " + frase + " bla")
    finally:
        HUELLAS["fragmentos"].pop()


def test_n01_ningun_episodio_de_los_150_en_el_prompt_ni_en_los_ejemplos():
    from classifier_service.services.juez_v2 import (
        EJEMPLOS_FRONTERA_V2,
        SYSTEM_PROMPT_V2,
        construir_mensajes_v2,
    )

    fijo = json.dumps(construir_mensajes_v2("", "", ""), ensure_ascii=False)
    texto = SYSTEM_PROMPT_V2 + json.dumps(EJEMPLOS_FRONTERA_V2, ensure_ascii=False) + fijo
    assert coincidencias_con_la_muestra(texto) == []


# ── N05: no se tocan los prompts del tutor ni F15 ───────────────────────────
def _huella_arbol(p: pathlib.Path, excluir: str | None = None) -> str:
    h = hashlib.sha256()
    for f in sorted(p.rglob("*")):
        if f.is_file() and f.relative_to(p).parts[0] != excluir:
            h.update(str(f.relative_to(p)).encode())
            h.update(f.read_bytes())
    return h.hexdigest()


def test_n05_prompts_del_tutor_intactos():
    # HU-009 (20/11/2026): Juani autorizo un prompt nuevo del tutor ("los promts
    # podes tocarlos tranquilo"). Lo que sigue intacto son las versiones que ya
    # existian: se excluye solo la carpeta v1.11.0.
    assert (
        _huella_arbol(RAIZ / "ai-native-prompts/prompts/tutor", excluir="v1.11.0")
        == "d862193c219a9f45bceb3cfcdc42e2441c6327d2c5d5cf11a15ea8102c0dc595"
    )


def test_n05_f15_intacto():
    f15 = RAIZ / "apps/evaluation-service/src/evaluation_service/services/correccion_nativa.py"
    assert (
        hashlib.sha256(f15.read_bytes()).hexdigest()
        == "bf5463c59f9df30e1aa2eaa45f2da70bbaa6e7663d4e6fd91a5cb064af3d5745"
    )
