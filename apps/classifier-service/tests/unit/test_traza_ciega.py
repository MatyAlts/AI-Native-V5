"""Traza ciega (tareas 6.1 y 6.2, design D4, spec traza-ciega-episodio).

Entradas: dicts CRUDOS como los que devuelve `GET /api/v1/episodes/{id}` del
CTR (`EventOut`), con campos fuera del contrato y metadatos que nunca tienen
que llegar al codificador. Nada pasa por los modelos Pydantic del CTR.
"""

from __future__ import annotations

import json
import typing
from datetime import UTC, datetime, timedelta

import pytest
from classifier_service.services.traza_ciega import (
    TIPOS_INCLUIDOS,
    TIPOS_OMITIDOS,
    TRAZA_VERSION,
    filtrar_traza,
)

EPISODIO = "5d7e1c2a-0b6f-4c1e-9a77-3f1f0c2d4e5a"
INICIO = datetime(2026, 9, 1, 10, 0, 0, tzinfo=UTC)

CLAVES_PROHIBIDAS = {
    "episode_id",
    "student_pseudonym",
    "comision_id",
    "problema_id",
    "seq",
    "ts",
    "self_hash",
    "chain_hash",
    "prev_chain_hash",
    "user_id",
    "curso_config_hash",
    "classifier_config_hash",
    "prompt_system_hash",
    "event_uuid",
}


def ev(seq: int, tipo: str, segundos: float, **payload) -> dict:
    return {
        "event_uuid": f"00000000-0000-4000-8000-{seq:012d}",
        "episode_id": EPISODIO,
        "seq": seq,
        "event_type": tipo,
        "ts": (INICIO + timedelta(seconds=segundos)).isoformat().replace("+00:00", "Z"),
        "payload": payload,
        "self_hash": "1" * 64,
        "chain_hash": f"{seq:064d}",
        "prev_chain_hash": "0" * 64,
        "prompt_system_hash": "2" * 64,
        "prompt_system_version": "v1.0.0",
        "classifier_config_hash": "3" * 64,
        "persisted_at": "2026-09-01T10:30:00Z",
    }


def apertura(seq: int = 0) -> dict:
    return ev(
        seq,
        "episodio_abierto",
        0,
        student_pseudonym="b1b1b1b1-0001-0001-0001-000000000001",
        problema_id="7f000000-0000-4000-8000-000000000001",
        comision_id="c0000000-0000-4000-8000-000000000001",
        curso_config_hash="4" * 64,
        ejercicio_id=None,
        language="python",
    )


def episodio_completo() -> list[dict]:
    return [
        apertura(0),
        ev(1, "lectura_enunciado", 30, duration_seconds=30),
        ev(2, "lectura_enunciado", 60, duration_seconds=30),
        ev(3, "lectura_enunciado", 90, duration_seconds=30),
        ev(
            4,
            "prompt_enviado",
            100,
            content="no entiendo el for",
            prompt_kind="validacion",
            chunks_used_hash="5" * 64,
        ),
        ev(5, "intento_adverso_detectado", 101, category="overuse", severity=1, pattern_id="burst"),
        ev(
            6,
            "tutor_respondio",
            105,
            content="que esperas que imprima?",
            socratic_compliance=0.9,
            violations=["x"],
            model_used="m",
            provider="p",
            tokens_input=10,
            tokens_output=20,
            cost_usd=0.01,
            chunks_used_hash="5" * 64,
        ),
        ev(
            7,
            "edicion_codigo",
            120,
            snapshot="for i in range(3):\n    print(i)",
            diff_chars=20,
            language="python",
            origin="copied_from_tutor",
        ),
        ev(
            8,
            "codigo_ejecutado",
            125,
            code="for i in range(3): print(i)",
            stdout="0\n1\n2\n",
            stderr="",
            duration_ms=12,
            runtime="pyodide",
            passed=1,
            failed=0,
            total=1,
            failed_test_names=[],
            execution_engine="sandbox",
        ),
        ev(9, "lectura_enunciado", 130, duration_seconds=15),
        ev(10, "prompt_enviado", 140, content="y si es while?", prompt_kind="pregunta"),
        ev(11, "intento_adverso_detectado", 141, category="jailbreak_indirect", severity=3),
        ev(12, "tutor_respondio", 145, content="probalo", model_used="m"),
        ev(13, "copia_intentada", 150, seleccion_chars=12, metodo="shortcut"),
        ev(
            14,
            "pega_intentada",
            151,
            contenido_longitud=40,
            contenido_preview="texto secreto pegado",
            metodo="menu_contextual",
        ),
        ev(
            15,
            "tests_ejecutados",
            160,
            test_count_total=3,
            test_count_passed=2,
            test_count_failed=1,
            tests_publicos=3,
            tests_hidden=0,
            chunks_used_hash="5" * 64,
            ejecucion_ms=40,
        ),
        ev(16, "anotacion_creada", 170, content="me trabe con el rango", words=5),
        ev(17, "pestana_perdida", 171, duracion_ms=100),
        ev(
            18,
            "codigo_ejecutado",
            175,
            code="x",
            stdout="",
            stderr="NameError",
            duration_ms=3,
            runtime="pyodide",
        ),
        ev(19, "episodio_cerrado", 180, reason="completed"),
        ev(20, "reflexion_completada", 200, respuestas={"a": "b"}),
        ev(21, "tp_entregada", 210, entrega_id="e"),
        ev(22, "tp_calificada", 220, nota=8),
        ev(23, "episodio_reabierto", 230, motivo="docente"),
        ev(24, "pestana_recuperada", 231, duracion_ms=5),
        ev(25, "evento_del_futuro", 240, algo="x"),
    ]


def _recorrer(obj, claves: set[str]) -> None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            claves.add(k)
            _recorrer(v, claves)
    elif isinstance(obj, list):
        for v in obj:
            _recorrer(v, claves)


def test_version_de_la_lista_blanca() -> None:
    assert TRAZA_VERSION == "traza_v1"


def test_conjunto_exacto_de_elementos_y_claves_por_tipo() -> None:
    traza = filtrar_traza(episodio_completo(), seq_tope=25)
    esperado = [
        ("inicio", None, 0.0, {"language": "python"}),
        ("lectura", 1, 30.0, {"duration_seconds": 90}),
        ("mensaje_alumno", 1, 100.0, {"content": "no entiendo el for"}),
        ("respuesta_tutor", 1, 105.0, {"content": "que esperas que imprima?"}),
        (
            "codigo",
            1,
            120.0,
            {"snapshot": "for i in range(3):\n    print(i)", "language": "python"},
        ),
        (
            "ejecucion",
            1,
            125.0,
            {
                "code": "for i in range(3): print(i)",
                "stdout": "0\n1\n2\n",
                "stderr": "",
                "passed": 1,
                "failed": 0,
                "total": 1,
                "failed_test_names": [],
            },
        ),
        ("lectura", 2, 130.0, {"duration_seconds": 15}),
        ("mensaje_alumno", 2, 140.0, {"content": "y si es while?"}),
        ("respuesta_tutor", 2, 145.0, {"content": "probalo"}),
        ("copia", None, 150.0, {"seleccion_chars": 12, "metodo": "shortcut"}),
        ("pegado", None, 151.0, {"contenido_longitud": 40, "metodo": "menu_contextual"}),
        (
            "prueba",
            1,
            160.0,
            {
                "test_count_total": 3,
                "test_count_passed": 2,
                "test_count_failed": 1,
                "tests_publicos": 3,
                "tests_hidden": 0,
            },
        ),
        ("nota", 1, 170.0, {"content": "me trabe con el rango"}),
        (
            "ejecucion",
            2,
            175.0,
            {
                "code": "x",
                "stdout": "",
                "stderr": "NameError",
                "passed": None,
                "failed": None,
                "total": None,
                "failed_test_names": None,
            },
        ),
        ("fin_cerrado", None, 180.0, {}),
    ]
    assert [(e["tipo"], e["k"], e["t_seg"], e["datos"]) for e in traza] == esperado
    assert [e["n"] for e in traza] == list(range(1, len(esperado) + 1))
    assert all(set(e) == {"n", "tipo", "k", "t_seg", "datos"} for e in traza)


def test_sin_marcas_de_la_maquina_ni_identidad_en_ningun_nivel() -> None:
    traza = filtrar_traza(episodio_completo(), seq_tope=25)
    texto = json.dumps(traza, ensure_ascii=False)
    for prohibido in (
        "overuse",
        "jailbreak",
        "intento_adverso",
        "prompt_kind",
        "validacion",
        "copied_from_tutor",
        "origin",
        "contenido_preview",
        "texto secreto pegado",
        "socratic_compliance",
        "model_used",
        "execution_engine",
        "completed",
        "reason",
        EPISODIO,
        "b1b1b1b1",
    ):
        assert prohibido not in texto, prohibido
    claves: set[str] = set()
    _recorrer(traza, claves)
    assert not claves & CLAVES_PROHIBIDAS


def test_fin_abandonado_distinto_de_cerrado_y_sin_motivo() -> None:
    eventos = [
        apertura(),
        ev(1, "prompt_enviado", 5, content="hola"),
        ev(2, "episodio_abandonado", 1800, reason="timeout"),
    ]
    traza = filtrar_traza(eventos, seq_tope=2)
    assert traza[-1:] == [
        {"n": 3, "tipo": "fin_abandonado", "k": None, "t_seg": 1800.0, "datos": {}}
    ]
    assert "timeout" not in json.dumps(traza)


def test_eventos_posteriores_al_tope_se_omiten() -> None:
    eventos = [
        apertura(),
        ev(1, "prompt_enviado", 5, content="antes"),
        ev(2, "episodio_abandonado", 10),
    ]
    eventos += [
        ev(3, "prompt_enviado", 900, content="despues"),
        ev(4, "edicion_codigo", 901, snapshot="y", language="python"),
    ]
    traza = filtrar_traza(eventos, seq_tope=2)
    assert [e["tipo"] for e in traza] == ["inicio", "mensaje_alumno", "fin_abandonado"]
    assert "despues" not in json.dumps(traza)


def test_localizador_global_sin_huecos_con_un_omitido_en_el_medio() -> None:
    eventos = [
        apertura(0),
        ev(1, "prompt_enviado", 1, content="a"),
        ev(2, "tutor_respondio", 2, content="b"),
        ev(3, "intento_adverso_detectado", 3, category="overuse"),
        ev(4, "edicion_codigo", 4, snapshot="c", language="python"),
        ev(5, "episodio_cerrado", 5),
    ]
    traza = filtrar_traza(eventos, seq_tope=5)
    assert [e["n"] for e in traza] == [1, 2, 3, 4, 5]
    assert [e["tipo"] for e in traza] == [
        "inicio",
        "mensaje_alumno",
        "respuesta_tutor",
        "codigo",
        "fin_cerrado",
    ]


def test_orden_por_seq_aunque_lleguen_desordenados() -> None:
    eventos = [
        ev(2, "tutor_respondio", 2, content="b"),
        apertura(0),
        ev(1, "prompt_enviado", 1, content="a"),
    ]
    assert [e["tipo"] for e in filtrar_traza(eventos, seq_tope=2)] == [
        "inicio",
        "mensaje_alumno",
        "respuesta_tutor",
    ]


def test_latidos_separados_por_un_mensaje_dan_dos_lecturas() -> None:
    eventos = [
        apertura(),
        ev(1, "lectura_enunciado", 30, duration_seconds=30),
        ev(2, "lectura_enunciado", 60, duration_seconds=30),
        ev(3, "lectura_enunciado", 90, duration_seconds=30),
        ev(4, "prompt_enviado", 95, content="hola"),
        ev(5, "lectura_enunciado", 120, duration_seconds=30),
    ]
    traza = filtrar_traza(eventos, seq_tope=5)
    assert [(e["tipo"], e["k"], e["datos"]) for e in traza[1:]] == [
        ("lectura", 1, {"duration_seconds": 90}),
        ("mensaje_alumno", 1, {"content": "hola"}),
        ("lectura", 2, {"duration_seconds": 30}),
    ]


def test_un_omitido_entre_latidos_no_corta_el_grupo() -> None:
    eventos = [
        apertura(),
        ev(1, "lectura_enunciado", 30, duration_seconds=30),
        ev(2, "pestana_perdida", 40),
        ev(3, "lectura_enunciado", 60, duration_seconds=30),
    ]
    traza = filtrar_traza(eventos, seq_tope=3)
    assert [(e["tipo"], e["k"], e["datos"]) for e in traza[1:]] == [
        ("lectura", 1, {"duration_seconds": 60})
    ]


def test_turnos_ejecuciones_y_codigos_correlativos() -> None:
    eventos = [apertura()]
    seq = 1
    for i in range(3):
        eventos.append(ev(seq, "prompt_enviado", seq, content=f"p{i}"))
        eventos.append(ev(seq + 1, "tutor_respondio", seq + 1, content=f"r{i}"))
        eventos.append(ev(seq + 2, "tutor_respondio", seq + 2, content=f"r{i}bis"))
        eventos.append(ev(seq + 3, "edicion_codigo", seq + 3, snapshot=str(i), language="python"))
        eventos.append(
            ev(seq + 4, "codigo_ejecutado", seq + 4, code=str(i), duration_ms=1, runtime="pyodide")
        )
        seq += 5
    traza = filtrar_traza(eventos, seq_tope=seq)
    por_tipo: dict[str, list] = {}
    for e in traza:
        por_tipo.setdefault(e["tipo"], []).append(e["k"])
    assert por_tipo.get("mensaje_alumno") == [1, 2, 3]
    assert por_tipo.get("respuesta_tutor") == [1, 1, 2, 2, 3, 3]
    assert por_tipo.get("codigo") == [1, 2, 3]
    assert por_tipo.get("ejecucion") == [1, 2, 3]


def test_respuesta_del_tutor_antes_de_cualquier_mensaje_no_tiene_turno() -> None:
    traza = filtrar_traza(
        [apertura(), ev(1, "tutor_respondio", 1, content="bienvenida")], seq_tope=1
    )
    assert [(e["tipo"], e["k"]) for e in traza] == [("inicio", None), ("respuesta_tutor", None)]


def test_t_seg_relativo_al_primer_evento_aunque_el_tope_lo_corte() -> None:
    eventos = [apertura(), ev(1, "prompt_enviado", 61.5, content="a")]
    assert [e["t_seg"] for e in filtrar_traza(eventos, seq_tope=1)] == [0.0, 61.5]


def test_tipo_desconocido_se_omite() -> None:
    traza = filtrar_traza([apertura(), ev(1, "tipo_inventado", 1, content="x")], seq_tope=1)
    assert [e["tipo"] for e in traza] == ["inicio"]


def test_payload_sin_un_campo_permitido_lo_trae_nulo() -> None:
    traza = filtrar_traza([apertura(), ev(1, "pega_intentada", 1, metodo="shortcut")], seq_tope=1)
    assert [e["datos"] for e in traza[1:]] == [{"contenido_longitud": None, "metodo": "shortcut"}]


# ── 6.2 cobertura de tipos del contrato ──────────────────────────────────


def _tipos_del_contrato() -> set[str]:
    from platform_contracts.ctr import events

    tipos: set[str] = set()
    for nombre in dir(events):
        clase = getattr(events, nombre)
        campos = getattr(clase, "model_fields", None)
        if not isinstance(clase, type) or not campos or "event_type" not in campos:
            continue
        tipos.update(typing.get_args(campos["event_type"].annotation))
    return tipos


def test_el_contrato_tiene_tipos_de_evento() -> None:
    tipos = _tipos_del_contrato()
    assert {"episodio_abierto", "prompt_enviado", "intento_adverso_detectado"} <= tipos
    assert len(tipos) >= 19


@pytest.mark.parametrize("extra", [set(), {"tipo_ficticio_para_probar_el_test"}])
def test_cada_tipo_del_contrato_tiene_decision_explicita(extra: set[str]) -> None:
    tipos = _tipos_del_contrato() | extra
    decididos = set(TIPOS_INCLUIDOS) | TIPOS_OMITIDOS
    sin_decision = tipos - decididos
    if extra:
        assert sin_decision == extra
    else:
        assert sin_decision == set(), f"tipos sin decisión en traza_v1: {sorted(sin_decision)}"
    assert not set(TIPOS_INCLUIDOS) & TIPOS_OMITIDOS
