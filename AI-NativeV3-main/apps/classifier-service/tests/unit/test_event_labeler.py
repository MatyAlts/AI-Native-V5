"""Tests del etiquetador de eventos N1-N4 (ADR-020 + ADR-023 v1.1.0)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from classifier_service.services.event_labeler import (
    ANOTACION_N1_WINDOW_SECONDS,
    ANOTACION_N4_WINDOW_SECONDS,
    EVENT_N_LEVEL_BASE,
    LABELER_VERSION,
    EpisodeContext,
    label_event,
    n_level_distribution,
    time_in_level,
)


def _ev(
    seq: int, event_type: str, sec_offset: int, payload: dict[str, Any] | None = None
) -> dict[str, Any]:
    base = datetime(2026, 9, 1, 10, 0, 0, tzinfo=UTC)
    return {
        "seq": seq,
        "event_type": event_type,
        "ts": (base + timedelta(seconds=sec_offset)).isoformat().replace("+00:00", "Z"),
        "payload": payload or {},
    }


# ---------------------------------------------------------------------------
# label_event
# ---------------------------------------------------------------------------


def test_mapping_base_cubre_todos_los_event_types_del_contrato() -> None:
    """Sanity check: el mapping cubre los 11 event_type clasificables que
    existen hoy en `packages/contracts/src/platform_contracts/ctr/events.py`.
    Si se agrega uno nuevo, este test recuerda actualizar el mapping (o
    agregarlo a `_EXCLUDED_FROM_FEATURES` si es side-channel — ej.
    `reflexion_completada` que NO aparece aca por diseno: ADR-035 lo excluye
    explicitamente del classifier para preservar reproducibilidad bit-a-bit).
    """
    expected_types = {
        "episodio_abierto",
        "episodio_cerrado",
        "episodio_abandonado",
        "lectura_enunciado",
        "anotacion_creada",
        "edicion_codigo",
        "codigo_ejecutado",
        "prompt_enviado",
        "tutor_respondio",
        "intento_adverso_detectado",  # ADR-019, G3 Fase A
        "tests_ejecutados",  # v1.2.0, ADR-033/034 (Sec 9 epic ai-native-completion)
    }
    assert set(EVENT_N_LEVEL_BASE.keys()) == expected_types


def test_intento_adverso_detectado_es_n4() -> None:
    """ADR-019: el evento adverso es N4 porque es interaccion con la IA."""
    from classifier_service.services.event_labeler import label_event

    assert label_event("intento_adverso_detectado") == "N4"


def test_meta_events() -> None:
    assert label_event("episodio_abierto") == "meta"
    assert label_event("episodio_cerrado") == "meta"
    assert label_event("episodio_abandonado") == "meta"


def test_lectura_enunciado_es_n1() -> None:
    assert label_event("lectura_enunciado") == "N1"


def test_anotacion_creada_sin_contexto_es_n2_compat_v1_0_0() -> None:
    """Sin EpisodeContext, label_event mantiene comportamiento v1.0.0 (N2 fijo).

    v1.1.0 (ADR-023, G8a) introduce override temporal pero solo cuando el
    caller pasa `context`. Callers que no construyen contexto (ej. tests
    directos del label_event) ven el comportamiento puro v1.0.0 — esto es
    intencional para mantener back-compat de la API publica.
    """
    assert label_event("anotacion_creada", {"content": "planeo dividir en pasos"}) == "N2"
    assert label_event("anotacion_creada", {"content": "ejecute y dio error"}) == "N2"
    assert label_event("anotacion_creada", None) == "N2"


def test_labeler_version_es_1_x_y_minor_refleja_overrides_temporales() -> None:
    """Sanity check: LABELER_VERSION es 1.MINOR.PATCH; v1.1.x tiene override
    temporal de anotacion_creada (G8a). Un salto de MAJOR (2.x) o de MINOR
    >= 2 (1.2+) implica cambio sustantivo (ej. clasificacion semantica del
    contenido del Eje B) y los tests deben ser revisados.
    """
    parts = LABELER_VERSION.split(".")
    major = int(parts[0])
    minor = int(parts[1])
    assert major == 1, (
        f"LABELER_VERSION saltó a {LABELER_VERSION}: revisar si la heuristica "
        "temporal de anotacion_creada sigue siendo valida o ya se introdujo "
        "override por contenido (Eje B post-defensa)."
    )
    assert minor >= 1, (
        f"LABELER_VERSION es {LABELER_VERSION} pero el override temporal de "
        "anotacion_creada (ADR-023, G8a) requiere v1.1.0 o superior."
    )


# ---------------------------------------------------------------------------
# Override temporal de anotacion_creada (ADR-023, G8a, v1.1.0)
# ---------------------------------------------------------------------------


def _ctx(
    event_offset: int,
    started_offset: int | None = 0,
    last_tutor_offset: int | None = None,
) -> EpisodeContext:
    """Helper para armar EpisodeContext con offsets en segundos sobre una base fija."""
    base = datetime(2026, 9, 1, 10, 0, 0, tzinfo=UTC)
    return EpisodeContext(
        event_ts=base + timedelta(seconds=event_offset),
        episode_started_at=(base + timedelta(seconds=started_offset))
        if started_offset is not None
        else None,
        last_tutor_respondio_at=(base + timedelta(seconds=last_tutor_offset))
        if last_tutor_offset is not None
        else None,
    )


def test_anotacion_dentro_de_120s_de_episodio_abierto_es_n1() -> None:
    """ADR-023: anotacion en los primeros 120s del episodio = lectura del enunciado = N1."""
    ctx = _ctx(event_offset=30, started_offset=0)
    assert label_event("anotacion_creada", {"content": "leyendo..."}, context=ctx) == "N1"
    # Borde inferior (justo en el inicio): N1
    ctx_zero = _ctx(event_offset=0, started_offset=0)
    assert label_event("anotacion_creada", {}, context=ctx_zero) == "N1"
    # Just-before-edge (119s): N1
    ctx_edge = _ctx(event_offset=int(ANOTACION_N1_WINDOW_SECONDS) - 1, started_offset=0)
    assert label_event("anotacion_creada", {}, context=ctx_edge) == "N1"


def test_anotacion_post_120s_sin_tutor_respondio_es_n2() -> None:
    """ADR-023: fuera de la ventana N1 y sin tutor_respondio previo => fallback N2."""
    ctx = _ctx(event_offset=int(ANOTACION_N1_WINDOW_SECONDS) + 1, started_offset=0)
    assert label_event("anotacion_creada", {}, context=ctx) == "N2"


def test_anotacion_dentro_de_60s_de_tutor_respondio_es_n4() -> None:
    """ADR-023: anotacion <60s post-tutor_respondio = apropiacion = N4."""
    # Tutor respondio en t=300, anotacion en t=320 => 20s de delta => N4.
    ctx = _ctx(event_offset=320, started_offset=0, last_tutor_offset=300)
    assert label_event(
        "anotacion_creada", {"content": "ahora me doy cuenta"}, context=ctx
    ) == "N4"
    # Borde just-before-edge: 59s post-tutor => N4.
    ctx_edge = _ctx(
        event_offset=300 + int(ANOTACION_N4_WINDOW_SECONDS) - 1,
        started_offset=0,
        last_tutor_offset=300,
    )
    assert label_event("anotacion_creada", {}, context=ctx_edge) == "N4"


def test_anotacion_post_60s_de_tutor_respondio_cae_a_n2() -> None:
    """ADR-023: fuera de la ventana N4 (>=60s post-tutor) cae al fallback N2."""
    # Tutor respondio en t=300, anotacion en t=400 => 100s de delta => fuera de N4.
    # El episodio_abierto fue en t=0, entonces tampoco esta en ventana N1 (>120s).
    ctx = _ctx(event_offset=400, started_offset=0, last_tutor_offset=300)
    assert label_event("anotacion_creada", {}, context=ctx) == "N2"


def test_anotacion_n4_gana_sobre_n1_si_ambas_ventanas_solapan() -> None:
    """ADR-023: si la anotacion esta dentro de ambas ventanas (N1 por reciencia
    al episodio_abierto Y N4 por reciencia al tutor_respondio), gana N4 — la
    senal "apropiacion tras respuesta del tutor" es pedagogicamente mas
    informativa que "lectura inicial".
    """
    # Episodio abrio en t=0, tutor respondio en t=50, anotacion en t=80.
    # Anotacion esta a 80s del open (<120 => ventana N1) Y a 30s del tutor
    # (<60 => ventana N4). Override resuelve a N4.
    ctx = _ctx(event_offset=80, started_offset=0, last_tutor_offset=50)
    assert label_event("anotacion_creada", {}, context=ctx) == "N4"


def test_anotacion_con_tutor_respondio_futuro_no_aplica_n4() -> None:
    """Defensa: si por desorden de seq el `last_tutor_respondio_at` quedara en
    el futuro relativo al evento (delta negativo), NO se aplica el override
    N4 — la heuristica solo cuenta respuestas EFECTIVAMENTE PREVIAS al evento.
    """
    # Anotacion a t=100, tutor "respondio" a t=200 (incoherente). NO override N4.
    # Como ademas esta fuera de ventana N1 (>120s desde t=0 si lo pongo asi), cae a N2.
    ctx = _ctx(event_offset=int(ANOTACION_N1_WINDOW_SECONDS) + 10, started_offset=0,
               last_tutor_offset=int(ANOTACION_N1_WINDOW_SECONDS) + 200)
    assert label_event("anotacion_creada", {}, context=ctx) == "N2"


def test_n_level_distribution_aplica_override_temporal_de_anotacion() -> None:
    """Integracion v1.1.0: el override temporal se ve en el conteo de
    n_level_distribution para flows reales del piloto.

    Episodio:
      t=0: episodio_abierto
      t=30: anotacion_creada (N1 — dentro de los 120s del open)
      t=180: tutor_respondio
      t=200: anotacion_creada (N4 — 20s post tutor)
      t=300: anotacion_creada (N2 — 120s post tutor, fuera de ventana N4)

    En v1.0.0 las 3 anotaciones eran N2 fijo => total_events_per_level["N2"] = 3.
    En v1.1.0 el override las separa => N1 = 1, N4 = 1, N2 = 1.
    """
    events = [
        _ev(0, "episodio_abierto", 0),
        _ev(1, "anotacion_creada", 30, {"content": "leyendo enunciado"}),
        _ev(2, "tutor_respondio", 180),
        _ev(3, "anotacion_creada", 200, {"content": "ahora me doy cuenta"}),
        _ev(4, "anotacion_creada", 300, {"content": "intento otra estrategia"}),
    ]
    r = n_level_distribution(events)
    counts = r["total_events_per_level"]
    # 1 anotacion en cada nivel — el override temporal se aplica.
    assert counts["meta"] == 1  # episodio_abierto
    assert counts["N4"] >= 2  # tutor_respondio + 1 anotacion N4
    assert counts["N1"] == 1  # 1 anotacion N1 (la de t=30)
    assert counts["N2"] == 1  # 1 anotacion N2 (la de t=300)
    # labeler_version reporta v1.1.0
    assert r["labeler_version"] == LABELER_VERSION
    # Sanity: si futuro Claude rompe el override accidentalmente, este assert
    # pasaria con todas las anotaciones en N2 — falla aca antes de llegar a prod.
    assert counts["N2"] != 3, (
        "REGRESION: las 3 anotaciones quedaron en N2 — el override temporal "
        "v1.1.0 NO se aplico (revisar event_labeler._build_event_contexts)."
    )


def test_codigo_ejecutado_es_n3() -> None:
    assert label_event("codigo_ejecutado") == "N3"


def test_prompts_y_respuestas_son_n4() -> None:
    assert label_event("prompt_enviado") == "N4"
    assert label_event("tutor_respondio") == "N4"


def test_edicion_codigo_student_typed_es_n2() -> None:
    assert label_event("edicion_codigo", {"origin": "student_typed"}) == "N2"


def test_edicion_codigo_legacy_sin_origin_es_n2() -> None:
    """Eventos pre-F6 no tienen `origin`. Cae al default N2."""
    assert label_event("edicion_codigo", {}) == "N2"
    assert label_event("edicion_codigo", None) == "N2"
    assert label_event("edicion_codigo", {"origin": None}) == "N2"


def test_edicion_codigo_copied_from_tutor_es_n4() -> None:
    """Override clave: codigo copiado del tutor es interaccion IA, no elaboracion."""
    assert label_event("edicion_codigo", {"origin": "copied_from_tutor"}) == "N4"


def test_edicion_codigo_pasted_external_es_n4() -> None:
    """Pegar codigo de afuera tampoco es elaboracion propia."""
    assert label_event("edicion_codigo", {"origin": "pasted_external"}) == "N4"


def test_event_type_desconocido_cae_a_meta() -> None:
    """Fallback conservador: nunca crashear ante un evento experimental o legacy."""
    assert label_event("evento_inventado_v9000") == "meta"
    assert label_event("future_event_g6_g7") == "meta"


def test_label_event_es_pura_y_deterministica() -> None:
    """Mismo input → mismo output, sin side-effects observables."""
    payload = {"origin": "copied_from_tutor"}
    a = label_event("edicion_codigo", payload)
    b = label_event("edicion_codigo", payload)
    c = label_event("edicion_codigo", dict(payload))
    assert a == b == c == "N4"


# ---------------------------------------------------------------------------
# time_in_level
# ---------------------------------------------------------------------------


def test_time_in_level_episodio_vacio() -> None:
    r = time_in_level([])
    assert r == {"N1": 0.0, "N2": 0.0, "N3": 0.0, "N4": 0.0, "meta": 0.0}


def test_time_in_level_un_solo_evento() -> None:
    """Sin evento siguiente no hay delta posible. Devuelve todo en 0."""
    r = time_in_level([_ev(0, "lectura_enunciado", 0)])
    assert sum(r.values()) == 0.0


def test_time_in_level_dos_eventos_acumula_en_el_primero() -> None:
    """La duracion de un evento es delta hasta el siguiente."""
    events = [
        _ev(0, "lectura_enunciado", 0),
        _ev(1, "edicion_codigo", 90, {"origin": "student_typed"}),
    ]
    r = time_in_level(events)
    assert r["N1"] == 90.0
    assert r["N2"] == 0.0  # el ultimo evento aporta 0


def test_time_in_level_episodio_mixto() -> None:
    """Episodio realista: lectura → edicion → ejecucion → prompt → respuesta."""
    events = [
        _ev(0, "episodio_abierto", 0),
        _ev(1, "lectura_enunciado", 10, {"duration_seconds": 20}),
        _ev(2, "edicion_codigo", 30, {"origin": "student_typed"}),
        _ev(3, "codigo_ejecutado", 90),
        _ev(4, "prompt_enviado", 130, {"prompt_kind": "validacion"}),
        _ev(5, "tutor_respondio", 145),
        _ev(6, "episodio_cerrado", 160),
    ]
    r = time_in_level(events)
    # meta(0→10)=10 + N1(10→30)=20 + N2(30→90)=60 + N3(90→130)=40 + N4(130→145)=15 + N4(145→160)=15
    # episodio_cerrado es el ultimo → no aporta delta
    assert r["meta"] == 10.0
    assert r["N1"] == 20.0
    assert r["N2"] == 60.0
    assert r["N3"] == 40.0
    assert r["N4"] == 30.0
    assert sum(r.values()) == 160.0  # duracion total del episodio


def test_time_in_level_edicion_copiada_del_tutor_acumula_en_n4() -> None:
    """Override de origin afecta a `time_in_level`."""
    events = [
        _ev(0, "edicion_codigo", 0, {"origin": "copied_from_tutor"}),
        _ev(1, "codigo_ejecutado", 50),
    ]
    r = time_in_level(events)
    assert r["N4"] == 50.0  # la edicion fue copia del tutor → N4
    assert r["N2"] == 0.0


def test_time_in_level_eventos_desordenados_se_ordenan_por_seq() -> None:
    """`seq` es la fuente de orden, no la posicion en la lista."""
    events = [
        _ev(2, "codigo_ejecutado", 100),
        _ev(0, "lectura_enunciado", 0),
        _ev(1, "edicion_codigo", 50, {"origin": "student_typed"}),
    ]
    r = time_in_level(events)
    assert r["N1"] == 50.0
    assert r["N2"] == 50.0
    assert r["N3"] == 0.0  # el ejecutado quedo ultimo, no aporta delta


def test_time_in_level_clampa_deltas_negativos_a_cero() -> None:
    """Reloj de cliente desincronizado puede producir ts invertidos. No crashear."""
    base = datetime(2026, 9, 1, 10, 0, 0, tzinfo=UTC)
    events = [
        {
            "seq": 0,
            "event_type": "lectura_enunciado",
            "ts": (base + timedelta(seconds=100)).isoformat().replace("+00:00", "Z"),
            "payload": {},
        },
        {
            "seq": 1,
            "event_type": "edicion_codigo",
            "ts": base.isoformat().replace("+00:00", "Z"),  # mas viejo que el seq=0
            "payload": {"origin": "student_typed"},
        },
    ]
    r = time_in_level(events)
    assert r["N1"] == 0.0  # delta negativo → clamp 0


# ---------------------------------------------------------------------------
# n_level_distribution
# ---------------------------------------------------------------------------


def test_distribution_episodio_vacio() -> None:
    r = n_level_distribution([])
    assert r["labeler_version"] == LABELER_VERSION
    assert r["distribution_seconds"] == {
        "N1": 0.0,
        "N2": 0.0,
        "N3": 0.0,
        "N4": 0.0,
        "meta": 0.0,
    }
    assert r["distribution_ratio"] == {
        "N1": 0.0,
        "N2": 0.0,
        "N3": 0.0,
        "N4": 0.0,
        "meta": 0.0,
    }
    assert r["total_events_per_level"] == {"N1": 0, "N2": 0, "N3": 0, "N4": 0, "meta": 0}


def test_distribution_cuenta_eventos_y_ratios() -> None:
    """El conteo de eventos es por evento; los segundos son por delta."""
    events = [
        _ev(0, "lectura_enunciado", 0),
        _ev(1, "edicion_codigo", 100, {"origin": "student_typed"}),
        _ev(2, "edicion_codigo", 200, {"origin": "copied_from_tutor"}),  # N4
        _ev(3, "codigo_ejecutado", 300),
    ]
    r = n_level_distribution(events)

    counts = r["total_events_per_level"]
    assert counts["N1"] == 1  # lectura
    assert counts["N2"] == 1  # student_typed
    assert counts["N4"] == 1  # copied_from_tutor
    assert counts["N3"] == 1  # ejecutado
    assert counts["meta"] == 0

    secs = r["distribution_seconds"]
    assert secs["N1"] == 100.0  # lectura → edicion
    assert secs["N2"] == 100.0  # edicion student → edicion tutor
    assert secs["N4"] == 100.0  # edicion tutor → ejecutado
    assert secs["N3"] == 0.0  # ejecutado es el ultimo

    ratios = r["distribution_ratio"]
    assert abs(ratios["N1"] - 1 / 3) < 1e-9
    assert abs(ratios["N2"] - 1 / 3) < 1e-9
    assert abs(ratios["N4"] - 1 / 3) < 1e-9
    assert ratios["N3"] == 0.0
    assert sum(ratios.values()) == 1.0


def test_distribution_ratio_es_cero_si_total_es_cero() -> None:
    """Un solo evento → 0 segundos totales → ratios todos en 0 (no NaN)."""
    r = n_level_distribution([_ev(0, "lectura_enunciado", 0)])
    assert all(v == 0.0 for v in r["distribution_ratio"].values())
    assert r["total_events_per_level"]["N1"] == 1


def test_distribution_incluye_labeler_version() -> None:
    """El endpoint debe propagar la version para que el analisis empirico
    sepa con que reglas se generaron los datos. Si bumpea LABELER_VERSION,
    los consumidores ven el cambio."""
    r = n_level_distribution([_ev(0, "lectura_enunciado", 0)])
    assert r["labeler_version"] == LABELER_VERSION
    assert isinstance(r["labeler_version"], str)


# ---------------------------------------------------------------------------
# tests_ejecutados (Sec 9 epic ai-native-completion / ADR-033/034, v1.2.0)
# ---------------------------------------------------------------------------


def test_tests_ejecutados_sin_contexto_es_n3() -> None:
    """Sin contexto, tests_ejecutados es base N3 (validacion funcional)."""
    from classifier_service.services.event_labeler import label_event

    assert (
        label_event(
            "tests_ejecutados",
            payload={"test_count_failed": 0, "test_count_passed": 5, "test_count_total": 5},
        )
        == "N3"
    )


def test_tests_ejecutados_con_fallos_es_n3_aunque_haya_tutor_reciente() -> None:
    """Si fallaron tests, NO promueve a N4 (no es apropiacion reflexiva)."""
    from datetime import UTC, datetime, timedelta

    from classifier_service.services.event_labeler import EpisodeContext, label_event

    base = datetime(2026, 5, 4, 10, 0, 0, tzinfo=UTC)
    ctx = EpisodeContext(
        event_ts=base + timedelta(seconds=120),  # 120s post-tutor (>= 60s)
        episode_started_at=base - timedelta(minutes=5),
        last_tutor_respondio_at=base,  # tutor 120s atras
    )
    assert (
        label_event(
            "tests_ejecutados",
            payload={"test_count_failed": 2, "test_count_passed": 3, "test_count_total": 5},
            context=ctx,
        )
        == "N3"
    )


def test_tests_ejecutados_todos_pass_y_tutor_lejano_es_n4() -> None:
    """Todos pass + tutor_respondio >= 60s ago => N4 (apropiacion reflexiva)."""
    from datetime import UTC, datetime, timedelta

    from classifier_service.services.event_labeler import EpisodeContext, label_event

    base = datetime(2026, 5, 4, 10, 0, 0, tzinfo=UTC)
    ctx = EpisodeContext(
        event_ts=base + timedelta(seconds=120),  # 120s post-tutor (>= 60s)
        episode_started_at=base - timedelta(minutes=5),
        last_tutor_respondio_at=base,
    )
    assert (
        label_event(
            "tests_ejecutados",
            payload={"test_count_failed": 0, "test_count_passed": 5, "test_count_total": 5},
            context=ctx,
        )
        == "N4"
    )


def test_tests_ejecutados_todos_pass_pero_tutor_muy_reciente_es_n3() -> None:
    """Todos pass + tutor_respondio < 60s ago => N3 (no es reflexivo,
    es validacion inmediata post-tutor)."""
    from datetime import UTC, datetime, timedelta

    from classifier_service.services.event_labeler import EpisodeContext, label_event

    base = datetime(2026, 5, 4, 10, 0, 0, tzinfo=UTC)
    ctx = EpisodeContext(
        event_ts=base + timedelta(seconds=30),  # 30s post-tutor (< 60s)
        episode_started_at=base - timedelta(minutes=5),
        last_tutor_respondio_at=base,
    )
    assert (
        label_event(
            "tests_ejecutados",
            payload={"test_count_failed": 0, "test_count_passed": 5, "test_count_total": 5},
            context=ctx,
        )
        == "N3"
    )


def test_tests_ejecutados_sin_tutor_previo_es_n3() -> None:
    """Todos pass + sin tutor_respondio previo => N3 (no hay baseline para
    medir apropiacion reflexiva)."""
    from datetime import UTC, datetime

    from classifier_service.services.event_labeler import EpisodeContext, label_event

    ctx = EpisodeContext(
        event_ts=datetime(2026, 5, 4, 10, 0, 0, tzinfo=UTC),
        episode_started_at=datetime(2026, 5, 4, 9, 55, 0, tzinfo=UTC),
        last_tutor_respondio_at=None,
    )
    assert (
        label_event(
            "tests_ejecutados",
            payload={"test_count_failed": 0, "test_count_passed": 5, "test_count_total": 5},
            context=ctx,
        )
        == "N3"
    )


def test_labeler_version_bumpeo_a_1_2_x() -> None:
    """v1.2.x introduce regla de tests_ejecutados (Sec 9 epic, ADR-033/034)."""
    parts = LABELER_VERSION.split(".")
    major = int(parts[0])
    minor = int(parts[1])
    assert major == 1
    assert minor >= 2, (
        f"LABELER_VERSION es {LABELER_VERSION} pero la regla N3/N4 de "
        "tests_ejecutados (ADR-033/034) requiere v1.2.0 o superior."
    )
