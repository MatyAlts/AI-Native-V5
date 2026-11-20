"""Unitarios de apoyo del juez v2 (HU-001): traza, verificador de citas y few-shot.

La aceptación de la historia vive en `tests/aceptacion_hu001/`; estos cubren
detalles de construcción que la aceptación no fija.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from uuid import UUID

import pytest
from classifier_service.services import juez_v2
from classifier_service.services.juez_v2 import (
    RegimenV2Raw,
    _elementos,
    _verificar_evidencia,
    armar_traza_v2,
    clasificar_regimen_v2,
)
from classifier_service.services.regla_mtac import regimen_segun_regla_mtac

TENANT = UUID("00000000-0000-0000-0000-0000000000aa")


def _ev(seq: int, tipo: str, payload: dict) -> dict:
    return {
        "seq": seq,
        "event_type": tipo,
        "ts": f"2026-11-20T10:00:{seq:02d}Z",
        "payload": payload,
    }


def _episodio() -> list[dict]:
    return [
        _ev(0, "episodio_abierto", {"language": "python"}),
        _ev(1, "prompt_enviado", {"content": "creo que el for se pasa de largo. Lo pruebo"}),
        _ev(2, "tutor_respondio", {"content": "Revisá el rango del for."}),
        _ev(3, "edicion_codigo", {"snapshot": "for i in range(4):\n    print(i)"}),
        _ev(4, "edicion_codigo", {"snapshot": "for i in range(3):\n    print(i)"}),
        _ev(5, "edicion_codigo", {"snapshot": "for i in range(3):\n    print(i * 2)"}),
        _ev(
            6,
            "codigo_ejecutado",
            {"code": "for i in range(3):\n    print(i * 2)", "stdout": "0\n2\n4\n"},
        ),
        _ev(
            7, "anotacion_creada", {"content": "el rango arranca en cero, por eso son tres vueltas"}
        ),
        _ev(8, "prompt_enviado", {"content": "ya está"}),
    ]


def _dim(valor: str, localizador: str = "", cita: str = "") -> dict:
    return {"valor": valor, "localizador": localizador, "cita": cita}


def _raw(**dims) -> RegimenV2Raw:
    base = {
        "d1_verbalizacion": _dim("presente", "mensaje 1", "creo que el for se pasa de largo"),
        "d2_verificacion": _dim("presente", "ejecución 1", ""),
        "d3_justificacion": _dim("presente", "nota 1", "por eso son tres vueltas"),
        "d4_autonomia": _dim("interlocutor", "mensaje 1", "Lo pruebo"),
        "regimen": "REFLEXIVA",
        "confianza": 0.9,
        "justificacion_global": "x",
    }
    base.update(dims)
    return RegimenV2Raw.model_validate(base)


# ── Traza ───────────────────────────────────────────────────────────────────
def test_traza_agrupa_ediciones_consecutivas_con_diff():
    traza = armar_traza_v2(_episodio())
    assert "edición 1 a edición 3" in traza
    assert "3 ediciones" in traza
    # La primera edición del episodio muestra el código completo del último snapshot.
    assert "print(i * 2)" in traza
    assert "nota 1 · NOTA DEL ALUMNO: el rango arranca en cero" in traza


def test_traza_ordena_por_seq_aunque_lleguen_desordenados():
    eventos = list(reversed(_episodio()))
    traza = armar_traza_v2(eventos)
    assert traza.index("mensaje 1") < traza.index("ejecución 1") < traza.index("mensaje 2")


def test_traza_vacia():
    assert armar_traza_v2([]) == "(traza vacía)"


def test_localizadores_de_ediciones_agrupadas_existen_uno_por_uno():
    raw = _raw(d2_verificacion=_dim("presente", "edición 2, ejecución 1", ""))
    assert _verificar_evidencia(raw, _elementos(_episodio())) is None


# ── Verificador de citas y localizadores ───────────────────────────────────
def test_cita_de_una_nota_del_alumno_vale():
    assert _verificar_evidencia(_raw(), _elementos(_episodio())) is None


def test_localizador_sin_tilde_se_acepta():
    raw = _raw(d2_verificacion=_dim("presente", "Ejecucion 1", ""))
    assert _verificar_evidencia(raw, _elementos(_episodio())) is None


@pytest.mark.parametrize(
    "loc", ["ejecuciones 1 a 2", "mensaje", "turno 1", "mensaje 1 y mensaje 2"]
)
def test_localizador_mal_formado_es_salida_invalida(loc):
    raw = _raw(d2_verificacion=_dim("presente", loc, ""))
    fallo = _verificar_evidencia(raw, _elementos(_episodio()))
    assert fallo is not None and fallo[0] == "salida_invalida"
    assert "formato" in fallo[1]


def test_cita_con_puntos_suspensivos_en_el_mismo_texto_vale():
    raw = _raw(d1_verbalizacion=_dim("presente", "mensaje 1", '"creo que el for… Lo pruebo"'))
    assert _verificar_evidencia(raw, _elementos(_episodio())) is None


def test_fragmentos_de_textos_distintos_no_arman_una_cita():
    raw = _raw(d1_verbalizacion=_dim("presente", "mensaje 1", "se pasa de largo ... ya está"))
    fallo = _verificar_evidencia(raw, _elementos(_episodio()))
    assert fallo is not None and fallo[0] == "salida_invalida"


def test_cita_del_tutor_es_salida_invalida_aunque_la_dimension_sea_ausente():
    raw = _raw(d3_justificacion=_dim("ausente", "", "Revisá el rango del for"))
    fallo = _verificar_evidencia(raw, _elementos(_episodio()))
    assert fallo is not None and fallo[0] == "salida_invalida"


# ── Citas copiadas de un diff de la traza ──────────────────────────────────
@pytest.mark.parametrize(
    "cita",
    [
        "+for i in range(3):",  # línea agregada
        "+    print(i * 2)",  # con la indentación del código
        "-for i in range(4):",  # línea borrada: también la escribió el alumno
        " for i in range(3):",  # línea de contexto
        "-for i in range(4):\n+for i in range(3):",  # bloque del diff
    ],
)
def test_cita_de_codigo_con_marcas_de_diff_vale(cita):
    raw = _raw(d3_justificacion=_dim("presente", "edición 3", cita))
    assert _verificar_evidencia(raw, _elementos(_episodio())) is None


@pytest.mark.parametrize("cita", ["+Revisá el rango del for", "-Revisá el rango del for."])
def test_marcas_de_diff_no_habilitan_texto_del_tutor(cita):
    raw = _raw(d3_justificacion=_dim("presente", "edición 3", cita))
    fallo = _verificar_evidencia(raw, _elementos(_episodio()))
    assert fallo is not None and fallo[0] == "salida_invalida"


def test_marcas_de_diff_no_habilitan_codigo_que_el_alumno_no_escribio():
    raw = _raw(d3_justificacion=_dim("presente", "edición 3", "+while True:"))
    fallo = _verificar_evidencia(raw, _elementos(_episodio()))
    assert fallo is not None and fallo[0] == "salida_invalida"


def test_d4_oraculo_sin_cita_es_derivado():
    raw = _raw(d4_autonomia=_dim("oraculo", "mensaje 2", ""))
    fallo = _verificar_evidencia(raw, _elementos(_episodio()))
    assert fallo is not None and fallo[0] == "derivado_evidencia_insuficiente"


def test_d2_presente_con_solo_localizador_de_mensaje_es_derivado():
    raw = _raw(d2_verificacion=_dim("presente", "mensaje 1", ""))
    fallo = _verificar_evidencia(raw, _elementos(_episodio()))
    assert fallo is not None and fallo[0] == "derivado_evidencia_insuficiente"


# ── Few-shot: sus salidas son las que el propio código acepta ──────────────
@pytest.mark.parametrize("sid", list(juez_v2._SALIDAS_FEWSHOT))
def test_fewshot_pasa_la_verificacion_y_la_regla(sid):
    clave = {"s-7f3a": "PASIVA", "s-2c9e": "SUPERFICIAL", "s-b41d": "REFLEXIVA"}
    raw = RegimenV2Raw.model_validate(juez_v2._SALIDAS_FEWSHOT[sid])
    elementos = juez_v2.SINTETICOS_ALBERTO[sid]["elementos"]
    assert _verificar_evidencia(raw, elementos) is None
    d = (raw.d1_verbalizacion, raw.d2_verificacion, raw.d3_justificacion, raw.d4_autonomia)
    assert regimen_segun_regla_mtac(*(x.valor for x in d)) == raw.regimen == clave[sid]


def test_mensajes_tienen_system_fewshot_y_episodio_al_final():
    msgs = juez_v2.construir_mensajes_v2("TRAZA", "ENUNCIADO", "id-1")
    roles = [m["role"] for m in msgs]
    assert roles == ["system"] + ["user", "assistant"] * 3 + ["user"]
    assert "TRAZA" in msgs[-1]["content"]


# ── clasificar_regimen_v2: estados que la aceptación no cubre ──────────────
class _Completar:
    def __init__(self, contenido: str, output_tokens: int = 100):
        self.contenido = contenido
        self.output_tokens = output_tokens
        self.llamadas = 0

    async def __call__(self, **kw):
        self.llamadas += 1
        return SimpleNamespace(
            content=self.contenido, output_tokens=self.output_tokens, provider="openrouter"
        )


async def _juzgar(contenido: str, **kw):
    completar = _Completar(contenido)
    res = await clasificar_regimen_v2(
        events=_episodio(),
        enunciado="e",
        episode_id="id",
        complete=completar,
        model="m",
        tenant_id=TENANT,
        **kw,
    )
    return res, completar


async def test_json_roto_no_truncado_se_reintenta_y_da_error_parseo():
    res, completar = await _juzgar("{no es json")
    assert res.estado == "error_parseo"
    assert completar.llamadas == 3
    assert "trunc" not in res.razon.lower()


async def test_evidencia_insuficiente_cuando_la_regla_decide_es_inconsistente():
    datos = _raw().model_dump()
    datos["d4_autonomia"] = _dim("no_evaluable")
    datos["d1_verbalizacion"] = _dim("ausente")  # la regla decide SUPERFICIAL
    datos["regimen"] = "EVIDENCIA_INSUFICIENTE"
    res, _ = await _juzgar(json.dumps(datos))
    assert res.estado == "inconsistente"


async def test_baja_confianza():
    datos = _raw().model_dump()
    datos["confianza"] = 0.5
    res, _ = await _juzgar(json.dumps(datos))
    assert (res.estado, res.regimen) == ("baja_confianza", None)


async def test_salida_invalida_se_chequea_antes_que_la_regla():
    datos = _raw().model_dump()
    datos["d1_verbalizacion"] = _dim("presente", "mensaje 1", "inventado por el modelo")
    datos["regimen"] = "PASIVA"  # además inconsistente: gana la evidencia
    res, _ = await _juzgar(json.dumps(datos))
    assert res.estado == "salida_invalida"
