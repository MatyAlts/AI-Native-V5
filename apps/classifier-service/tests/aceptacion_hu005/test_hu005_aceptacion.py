"""Aceptación HU-005: juez v3, el juez de la HU-001 aplicando el codebook MTAC v2.

Escrita por el orquestador ANTES de construir. El constructor no la modifica.
El codebook v2 es el v1 con la D4 reescrita (quién decide en cada intercambio,
preguntas P1-P8, P1b, regla de conteo por mayoría con desempate por P3). D1, D2,
D3 y la regla de régimen no cambian: el juez v3 usa la MISMA regla en código
(`regla_mtac`) y el MISMO verificador de evidencia que el v2.

Contrato:
`classifier_service.services.juez_v3`
    JUEZ_VERSION = "v3"; PROMPT_VERSION_V3 (empieza con "mtac_v2_juez_v3");
    SYSTEM_PROMPT_V3; EJEMPLOS_FRONTERA_V3; HUELLA_PROMPT_V3 y huella_prompt_v3();
    RegimenV3Raw = salida del v2 + `es_frontera: bool` + `frontera_entre: list[str]`
    (vacía, o dos regímenes entre REFLEXIVA/SUPERFICIAL/PASIVA/EVIDENCIA_INSUFICIENTE);
    RESPONSE_JSON_SCHEMA_V3; RegimenV3Result (como RegimenV2Result, juez_version "v3");
    construir_mensajes_v3(traza, enunciado, episode_id);
    async clasificar_regimen_v3(...) con la misma firma que clasificar_regimen_v2.
    La traza es `juez_v2.armar_traza_v2` (misma evidencia).
`settings.eje_fino_juez_version` admite "v3"; el default sigue "v1".
`routes.classify_ep` importa `clasificar_regimen_v3` a nivel de módulo; con "v3" enruta como el v2.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import re
from types import SimpleNamespace
from uuid import UUID

import pytest

RAIZ = pathlib.Path(__file__).resolve().parents[4]
HUELLAS = json.loads(
    (
        RAIZ / "apps/classifier-service/tests/aceptacion_hu001/datos/huellas_muestra_150.json"
    ).read_text()
)
TENANT = UUID("00000000-0000-0000-0000-0000000000aa")


def _ev(seq, tipo, payload):
    return {
        "seq": seq,
        "event_type": tipo,
        "ts": f"2026-11-20T11:00:{seq:02d}Z",
        "payload": payload,
    }


MSG1 = "escribí el while pero no sé si la condición de corte va con cero"
MSG2 = "creo que el problema es que leo el dato afuera del ciclo y nunca cambia"
TUTOR1 = "Mirá dónde se actualiza la variable que controla el ciclo."
CODIGO = "n = int(input())\nwhile n != 0:\n    print(n)\n    n = int(input())"


def episodio():
    return [
        _ev(0, "episodio_abierto", {"language": "python"}),
        _ev(1, "edicion_codigo", {"snapshot": CODIGO, "language": "python"}),
        _ev(2, "prompt_enviado", {"content": MSG1}),
        _ev(3, "tutor_respondio", {"content": TUTOR1}),
        _ev(4, "prompt_enviado", {"content": MSG2}),
        _ev(5, "codigo_ejecutado", {"code": CODIGO, "stdout": "3\n2\n", "stderr": ""}),
        _ev(6, "episodio_cerrado", {}),
    ]


def _dim(v, loc="", cita=""):
    return {"valor": v, "localizador": loc, "cita": cita}


def salida(
    regimen="REFLEXIVA",
    d4=("interlocutor", "mensaje 2", "creo que el problema es que leo el dato afuera del ciclo"),
    es_frontera=False,
    frontera_entre=None,
):
    return {
        "d1_verbalizacion": _dim(
            "presente", "mensaje 2", "creo que el problema es que leo el dato afuera del ciclo"
        ),
        "d2_verificacion": _dim("presente", "ejecución 1", ""),
        "d3_justificacion": _dim("ausente"),
        "d4_autonomia": _dim(*d4),
        "regimen": regimen,
        "confianza": 0.85,
        "justificacion_global": "texto",
        "es_frontera": es_frontera,
        "frontera_entre": frontera_entre or [],
    }


class Completar:
    def __init__(self, contenido, output_tokens=200, provider="openrouter"):
        self.contenido, self.output_tokens, self.provider, self.llamadas = (
            contenido,
            output_tokens,
            provider,
            [],
        )

    async def __call__(self, **kw):
        self.llamadas.append(kw)
        return SimpleNamespace(
            content=self.contenido, output_tokens=self.output_tokens, provider=self.provider
        )


async def juzgar(datos, **kw):
    from classifier_service.services.juez_v3 import clasificar_regimen_v3

    completar = kw.pop("completar", None) or Completar(json.dumps(datos, ensure_ascii=False))
    res = await clasificar_regimen_v3(
        events=episodio(),
        enunciado="Mostrar números hasta que se ingrese cero.",
        episode_id="00000000-0000-0000-0000-00000000e005",
        complete=completar,
        model="anthropic/claude-sonnet",
        tenant_id=TENANT,
        **kw,
    )
    return res, completar


# ── C01: nada de lo anterior cambia ─────────────────────────────────────────
def test_c01_default_v1_y_v3_disponible():
    from typing import get_args

    from classifier_service.config import Settings, settings

    assert settings.eje_fino_juez_version == "v1"
    assert "v3" in get_args(Settings.model_fields["eje_fino_juez_version"].annotation)


def test_c01_juez_v2_intacto():
    from classifier_service.services import juez_v2

    assert (
        juez_v2.huella_prompt_v2()
        == juez_v2.HUELLA_PROMPT_V2
        == ("553e0f33001f4c261670574070fa36de8b3e09284e8584612fbd34d3744c62e8")
    )
    assert juez_v2.PROMPT_VERSION_V2 == "mtac_v1_juez_v2.0.0"


# ── C02: misma regla y misma evidencia que el v2 ────────────────────────────
def test_c02_misma_regla_en_codigo():
    from classifier_service.services import juez_v3, regla_mtac

    assert juez_v3.regimen_segun_regla_mtac is regla_mtac.regimen_segun_regla_mtac


def test_c02_misma_traza():
    from classifier_service.services import juez_v2, juez_v3

    traza = juez_v2.armar_traza_v2(episodio())
    msgs = juez_v3.construir_mensajes_v3(traza, "enunciado", "id")
    assert msgs[0] == {"role": "system", "content": juez_v3.SYSTEM_PROMPT_V3}
    assert traza in msgs[-1]["content"]


async def test_c02_verificacion_de_evidencia_igual_que_v2():
    res, _ = await juzgar(
        salida(d4=("interlocutor", "mensaje 2", "Mirá dónde se actualiza la variable"))
    )
    assert res.estado == "salida_invalida"  # cita del tutor
    res, _ = await juzgar(salida(regimen="SUPERFICIAL"))
    assert res.estado == "inconsistente"  # la regla dice REFLEXIVA
    res, _ = await juzgar(salida(), completar=Completar(json.dumps(salida()), provider="mock"))
    assert res.estado == "proveedor_no_disponible"
    res, completar = await juzgar(
        salida(),
        completar=Completar(json.dumps(salida())[:80], output_tokens=6000),
        max_tokens=6000,
    )
    assert res.estado == "error_parseo" and len(completar.llamadas) == 1


async def test_c02_ok_con_juez_version_v3():
    res, completar = await juzgar(salida())
    assert (res.estado, res.regimen, res.juez_version) == ("ok", "REFLEXIVA", "v3")
    assert completar.llamadas[0]["temperature"] == 0.0


# ── C03: la salida nueva marca frontera ─────────────────────────────────────
def test_c03_schema_exige_marca_de_frontera():
    from classifier_service.services.juez_v3 import RESPONSE_JSON_SCHEMA_V3, RegimenV3Raw
    from pydantic import ValidationError

    RegimenV3Raw.model_validate(
        salida(es_frontera=True, frontera_entre=["REFLEXIVA", "SUPERFICIAL"])
    )
    sin = salida()
    del sin["es_frontera"]
    with pytest.raises(ValidationError):
        RegimenV3Raw.model_validate(sin)
    with pytest.raises(ValidationError):
        RegimenV3Raw.model_validate(
            salida(es_frontera=True, frontera_entre=["REFLEXIVA", "INTERLOCUTOR"])
        )
    props = RESPONSE_JSON_SCHEMA_V3["json_schema"]["schema"]
    assert {"es_frontera", "frontera_entre"} <= set(props["required"])


async def test_c03_frontera_se_persiste():
    res, _ = await juzgar(salida(es_frontera=True, frontera_entre=["REFLEXIVA", "SUPERFICIAL"]))
    dump = res.model_dump(mode="json")
    assert dump["raw"]["es_frontera"] is True
    assert dump["raw"]["frontera_entre"] == ["REFLEXIVA", "SUPERFICIAL"]


# ── C04: el prompt aplica la D4 del codebook v2 ─────────────────────────────
@pytest.mark.parametrize(
    "idea",
    [
        r"qui[eé]n decide",  # la D4 mide quién decide
        r"no (mide|eval[uú]a) si (el alumno )?razona",  # D4 separada de D1
        r"intercambio",  # se trabaja por intercambio
        r"dato.{0,40}sintaxis|sintaxis.{0,40}dato",  # P5
        r"falla ajena",  # P6
        r"producci[oó]n propia",  # P1 / P1b
        r"confirm.{0,120}no cuenta",  # P1b
        r"hip[oó]tesis",  # P2
        r"nombra primero la causa",  # P3
        r"algo que la respuesta no le dio",  # P4
        r"eventos de c[oó]digo",  # P7
        r"ninguna respuesta del tutor produce un cambio",  # P8
        r"mayor[ií]a",  # regla de conteo
        r"empate",  # desempate por P3
    ],
)
def test_c04_prompt_contiene_la_d4_del_v2(idea):
    from classifier_service.services.juez_v3 import SYSTEM_PROMPT_V3

    assert re.search(idea, SYSTEM_PROMPT_V3, re.IGNORECASE | re.DOTALL), idea


def test_c04_el_prompt_ya_no_usa_el_patron_predominante_libre():
    from classifier_service.services.juez_v3 import SYSTEM_PROMPT_V3

    assert not re.search(r"patr[oó]n PREDOMINANTE", SYSTEM_PROMPT_V3)


def test_c04_ejemplos_de_frontera():
    from classifier_service.services.juez_v3 import EJEMPLOS_FRONTERA_V3, SYSTEM_PROMPT_V3

    for valor in ("interlocutor", "oraculo", "transferencia"):
        ej = [e for e in EJEMPLOS_FRONTERA_V3 if e["d4"] == valor]
        assert len(ej) >= 2, valor
        assert all(e["texto"] in SYSTEM_PROMPT_V3 for e in ej)


# ── C05: versión y huella propias ───────────────────────────────────────────
def test_c05_version_y_huella():
    from classifier_service.services import juez_v2, juez_v3

    assert juez_v3.JUEZ_VERSION == "v3"
    assert juez_v3.PROMPT_VERSION_V3.startswith("mtac_v2_juez_v3")
    assert juez_v3.huella_prompt_v3() == juez_v3.HUELLA_PROMPT_V3
    assert re.fullmatch(r"[0-9a-f]{64}", juez_v3.HUELLA_PROMPT_V3)
    assert juez_v3.HUELLA_PROMPT_V3 != juez_v2.HUELLA_PROMPT_V2


# ── C06: enrutamiento igual que el v2 ───────────────────────────────────────
def _instrumentar(monkeypatch, res_v3):
    from classifier_service.config import settings
    from classifier_service.routes import classify_ep

    llamados = {"v1": 0, "v2": 0, "v3": 0}

    def contar(clave, res):
        async def _f(**kw):
            llamados[clave] += 1
            return res

        return _f

    monkeypatch.setattr(settings, "eje_fino_llm_enabled", True)
    monkeypatch.setattr(settings, "eje_fino_juez_version", "v3")
    monkeypatch.setattr(classify_ep, "clasificar_regimen_llm", contar("v1", None))
    monkeypatch.setattr(classify_ep, "clasificar_regimen_v2", contar("v2", None))
    monkeypatch.setattr(classify_ep, "clasificar_regimen_v3", contar("v3", res_v3))
    monkeypatch.setattr(classify_ep, "AIGatewayClient", lambda **kw: SimpleNamespace(complete=None))
    return classify_ep, llamados


def _res(estado, regimen):
    return SimpleNamespace(
        estado=estado,
        regimen=regimen,
        razon="r",
        model_dump=lambda mode="json": {"estado": estado, "regimen": regimen, "juez_version": "v3"},
    )


@pytest.mark.parametrize(
    "subgrupo,estado,regimen,esperado",
    [
        ("dependiente_sobreuso", "ok", "PASIVA", "delegacion_pasiva"),
        ("dependiente_delegador", "ok", "SUPERFICIAL", "apropiacion_superficial"),
        ("dependiente_sobreuso", "salida_invalida", None, "sin_clasificar"),
        ("colaborador_funcional", "ok", "REFLEXIVA", "apropiacion_reflexiva"),
        ("colaborador_funcional", "baja_confianza", None, "apropiacion_superficial"),
    ],
)
async def test_c06_enruta_como_el_v2(monkeypatch, subgrupo, estado, regimen, esperado):
    classify_ep, llamados = _instrumentar(monkeypatch, _res(estado, regimen))
    proxy = "delegacion_pasiva" if subgrupo.startswith("dependiente") else "apropiacion_superficial"
    res = SimpleNamespace(
        appropriation=proxy, reason="proxy", features={"subgrupo": {"key": subgrupo}}
    )
    await classify_ep._aplicar_juez_eje_fino(res, episodio(), UUID(int=1), {}, TENANT)
    assert llamados == {"v1": 0, "v2": 0, "v3": 1}
    assert res.appropriation == esperado
    assert res.features["regimen_llm"]["juez_version"] == "v3"


async def test_c06_autonomo_no_pasa_por_el_juez(monkeypatch):
    classify_ep, llamados = _instrumentar(monkeypatch, _res("ok", "PASIVA"))
    res = SimpleNamespace(
        appropriation="autonomo", reason="p", features={"subgrupo": {"key": "autonomo_resolutor"}}
    )
    await classify_ep._aplicar_juez_eje_fino(res, episodio(), UUID(int=1), {}, TENANT)
    assert llamados["v3"] == 0 and res.appropriation == "autonomo"


# ── C07: lectura de lo persistido ───────────────────────────────────────────
async def test_c07_normalizar_lee_v3():
    from classifier_service.services.regimen_llm import normalizar_regimen_llm_persistido

    res, _ = await juzgar(salida(es_frontera=True, frontera_entre=["REFLEXIVA", "SUPERFICIAL"]))
    v3 = normalizar_regimen_llm_persistido(res.model_dump(mode="json"))
    assert v3["juez_version"] == "v3" and v3["raw"]["es_frontera"] is True


# ── N01: nada de los 150 ────────────────────────────────────────────────────
def _h(s):
    return hashlib.sha256(s.encode()).hexdigest()[:16]


def test_n01_ningun_episodio_de_los_150():
    from classifier_service.services.juez_v3 import (
        EJEMPLOS_FRONTERA_V3,
        SYSTEM_PROMPT_V3,
        construir_mensajes_v3,
    )

    texto = (
        SYSTEM_PROMPT_V3
        + json.dumps(EJEMPLOS_FRONTERA_V3, ensure_ascii=False)
        + json.dumps(construir_mensajes_v3("", "", ""), ensure_ascii=False)
    ).lower()
    ids = set(HUELLAS["ids"])
    frag = set(HUELLAS["fragmentos"])
    malos = [
        t
        for t in re.findall(
            r"[0-9a-f]{8}(?:-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})?", texto
        )
        if _h(t) in ids
    ]
    p = re.findall(r"\w+", texto)
    malos += [i for i in range(len(p) - 7) if _h(" ".join(p[i : i + 8])) in frag]
    assert malos == []


# ── N02: no se tocan prompts del tutor, F15 ni la aceptación de la HU-001 ───
def test_n02_intactos():
    def arbol(p):
        h = hashlib.sha256()
        for f in sorted(p.rglob("*")):
            if f.is_file():
                h.update(str(f.relative_to(p)).encode())
                h.update(f.read_bytes())
        return h.hexdigest()

    assert (
        arbol(RAIZ / "ai-native-prompts/prompts/tutor")
        == "d862193c219a9f45bceb3cfcdc42e2441c6327d2c5d5cf11a15ea8102c0dc595"
    )
    f15 = RAIZ / "apps/evaluation-service/src/evaluation_service/services/correccion_nativa.py"
    assert (
        hashlib.sha256(f15.read_bytes()).hexdigest()
        == "bf5463c59f9df30e1aa2eaa45f2da70bbaa6e7663d4e6fd91a5cb064af3d5745"
    )
    acept = RAIZ / "apps/classifier-service/tests/aceptacion_hu001/test_hu001_aceptacion.py"
    assert hashlib.sha256(acept.read_bytes()).hexdigest() == HUELLA_ACEPTACION_HU001


# Huella tras el reformateo de ruff del 20/11 (sólo orden de imports, formato y
# `zip(..., strict=False)`); antes: f813d2d0f0f7dbf46673e1fd89dafccdcf67b63d9b344dc3991f68532ca0a622.
HUELLA_ACEPTACION_HU001 = "d16f3f120544c599dbd341160620ae252fed618d7b9a6290ad0c6071d92be23d"
