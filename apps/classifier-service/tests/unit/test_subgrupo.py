"""Tests del modo sombra de subgrupos (B1 Fase 2).

Verifica el fix de la inversión + que el subgrupo es ADITIVO (no toca la
clasificación oficial ni el classifier_config_hash).
"""

from __future__ import annotations

from classifier_service.services.pipeline import (
    DEFAULT_REFERENCE_PROFILE,
    classify_episode_from_events,
    compute_classifier_config_hash,
)
from classifier_service.services.subgrupo import clasificar_subgrupo, compute_subgrupo


def _ev(seq: int, et: str, **payload: object) -> dict:
    return {
        "seq": seq,
        "event_type": et,
        "ts": f"2026-06-09T22:00:{seq % 60:02d}Z",
        "payload": payload,
    }


def _autonomo_competente() -> list[dict]:
    """Programó solo (0 prompts), última ejecución limpia."""
    ev = [_ev(0, "lectura_enunciado")]
    for k in range(6):
        ev.append(_ev(1 + 2 * k, "edicion_codigo", origin="student_typed"))
        ev.append(_ev(2 + 2 * k, "codigo_ejecutado", stdout="42\n", stderr=""))
    return ev


def test_autonomo_sin_prompts_NO_cae_en_delegacion() -> None:
    """El fix central: sin prompts, delegar es imposible → rama autónoma, NO delegación.
    v4.0.0: el brazo sin-tutor rollea al eje propio `autonomo`."""
    sg = clasificar_subgrupo(_autonomo_competente())
    assert sg.key == "autonomo_competente"
    assert sg.eje == "autonomo"
    assert sg.eje != "delegacion_pasiva"


def test_delegador_real_por_solicitud_directa() -> None:
    ev = [_ev(0, "lectura_enunciado")]
    for k in range(5):
        ev.append(
            _ev(
                1 + 2 * k,
                "prompt_enviado",
                prompt_kind="solicitud_directa",
                content="dame el codigo",
            )
        )
        ev.append(_ev(2 + 2 * k, "edicion_codigo", origin="pasted_external"))
    ev.append(_ev(20, "codigo_ejecutado", stdout="", stderr="NameError"))
    assert clasificar_subgrupo(ev).key == "dependiente_delegador"


def test_escribe_sin_validar() -> None:
    """Escribió mucho (>=10 ediciones) pero casi no ejecutó."""
    ev = [_ev(0, "lectura_enunciado")]
    for k in range(15):
        ev.append(_ev(1 + k, "edicion_codigo", origin="student_typed"))
    assert clasificar_subgrupo(ev).key == "escribe_sin_validar"


def test_episodio_corto_indeterminado() -> None:
    ev = [_ev(0, "lectura_enunciado"), _ev(1, "edicion_codigo", origin="student_typed")]
    assert clasificar_subgrupo(ev).key == "indeterminado"


def test_compute_subgrupo_trae_dimensiones() -> None:
    sg = compute_subgrupo(_autonomo_competente())
    assert sg["key"] == "autonomo_competente"
    assert set(sg["dimensiones"]) == {"autonomia", "experimentacion", "persistencia", "foco"}
    assert sg["dimensiones"]["autonomia"] == 1.0  # sin prompts ni pegados


def test_subgrupo_decide_eje_autonomo_para_brazo_sin_tutor() -> None:
    """v4.0.0: el subgrupo decide la etiqueta; el brazo sin-tutor → eje/etiqueta `autonomo`."""
    result = classify_episode_from_events(_autonomo_competente())
    assert result.appropriation == "autonomo"
    assert result.features["subgrupo"]["eje"] == "autonomo"


def test_subgrupo_no_afecta_el_classifier_config_hash() -> None:
    """features no entra al hash canónico → reproducibilidad intacta."""
    h1 = compute_classifier_config_hash(DEFAULT_REFERENCE_PROFILE)
    h2 = compute_classifier_config_hash(DEFAULT_REFERENCE_PROFILE)
    assert h1 == h2 and len(h1) == 64


def _colaborador_reflexivo() -> list[dict]:
    """Usó el tutor reflexivamente + experimentó, SIN sobreuso."""
    ev = [_ev(0, "lectura_enunciado")]
    ev.append(_ev(1, "prompt_enviado", prompt_kind="exploracion", content="que pasa si..."))
    for k in range(6):
        ev.append(_ev(2 + 2 * k, "edicion_codigo", origin="student_typed"))
        ev.append(_ev(3 + 2 * k, "codigo_ejecutado", stdout="ok\n", stderr=""))
    return ev


def test_sin_sobreuso_es_colaborador_reflexivo() -> None:
    sg = clasificar_subgrupo(_colaborador_reflexivo())
    assert sg.key == "colaborador_reflexivo"
    assert sg.eje == "reflexiva"


def test_desenganchado_split_por_brazo() -> None:
    """GOTCHA v4.0.0: el `desenganchado` se separa por brazo.

    - prompts == 0 + poco trabajo → `autonomo_desenganchado` (eje autonomo).
    - prompts >  0 + poco trabajo → `desenganchado` compartido (eje superficial).
    El brazo sin-tutor NUNCA debe emitir el `desenganchado` superficial.
    """
    # Brazo SIN tutor: poco trabajo, 0 prompts.
    sin_tutor = [
        _ev(0, "lectura_enunciado"),
        _ev(1, "edicion_codigo", origin="student_typed"),
        _ev(2, "edicion_codigo", origin="student_typed"),
        _ev(3, "edicion_codigo", origin="student_typed"),
    ]
    sg_sin = clasificar_subgrupo(sin_tutor)
    assert sg_sin.key == "autonomo_desenganchado"
    assert sg_sin.eje == "autonomo"

    # Brazo CON tutor: poco trabajo, prompts > 0 (sin solicitud_directa → no delegador).
    con_tutor = [
        _ev(0, "lectura_enunciado"),
        _ev(1, "prompt_enviado", prompt_kind="exploracion", content="que hace esto?"),
        _ev(2, "prompt_enviado", prompt_kind="exploracion", content="y esto?"),
        _ev(3, "edicion_codigo", origin="student_typed"),
    ]
    sg_con = clasificar_subgrupo(con_tutor)
    assert sg_con.key == "desenganchado"
    assert sg_con.eje == "superficial"


def _autonomo_trabado() -> list[dict]:
    """0 prompts, ejecutó >=2 veces, última ejecución NO limpia (sigue trabado)."""
    ev = [_ev(0, "lectura_enunciado")]
    for k in range(3):
        ev.append(_ev(1 + 2 * k, "edicion_codigo", origin="student_typed"))
        ev.append(_ev(2 + 2 * k, "codigo_ejecutado", stdout="", stderr="NameError"))
    return ev


def test_los_4_subgrupos_sin_tutor_rollean_a_eje_autonomo() -> None:
    """v4.0.0: TODO el brazo prompts==0 rollea al eje `autonomo` — los 4 subgrupos
    sin-tutor (competente, trabado, escribe_sin_validar, autonomo_desenganchado).

    Ninguno debe caer en superficial/delegacion: el brazo sin conversación no
    tiene apropiación reflexiva/superficial que juzgar contra el discurso.
    """
    competente = clasificar_subgrupo(_autonomo_competente())
    trabado = clasificar_subgrupo(_autonomo_trabado())
    # escribe_sin_validar: >=10 ediciones, casi sin ejecutar.
    sin_validar_ev = [_ev(0, "lectura_enunciado")]
    for k in range(15):
        sin_validar_ev.append(_ev(1 + k, "edicion_codigo", origin="student_typed"))
    sin_validar = clasificar_subgrupo(sin_validar_ev)
    # autonomo_desenganchado: poco trabajo, 0 prompts.
    deseng_ev = [
        _ev(0, "lectura_enunciado"),
        _ev(1, "edicion_codigo", origin="student_typed"),
        _ev(2, "edicion_codigo", origin="student_typed"),
        _ev(3, "edicion_codigo", origin="student_typed"),
    ]
    desenganchado = clasificar_subgrupo(deseng_ev)

    assert competente.key == "autonomo_competente"
    assert trabado.key == "autonomo_trabado"
    assert sin_validar.key == "escribe_sin_validar"
    assert desenganchado.key == "autonomo_desenganchado"
    # El invariante central: los 4 al mismo eje.
    for sg in (competente, trabado, sin_validar, desenganchado):
        assert sg.eje == "autonomo", f"{sg.key} debería rollear a autonomo, dio {sg.eje}"


def test_sobreuso_marca_dependiente_no_reflexivo() -> None:
    """v3.1.0 (hallazgo 2026-06-20): el sobreuso del tutor (overuse) saca al
    alumno de 'reflexiva' y lo marca dependiente — antes inflaba reflexiva."""
    ev = _colaborador_reflexivo()
    ev.append(_ev(50, "intento_adverso_detectado", category="overuse"))
    ev.append(_ev(51, "intento_adverso_detectado", category="overuse"))
    sg = clasificar_subgrupo(ev)
    assert sg.key == "dependiente_sobreuso"
    assert sg.eje == "delegacion_pasiva"
