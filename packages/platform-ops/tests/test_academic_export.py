"""Tests de exportación académica anonimizada."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from platform_ops.academic_export import AcademicExporter


@dataclass
class FakeCohortDataSource:
    episodes: list[dict] = field(default_factory=list)
    events_by_episode: dict[str, list[dict]] = field(default_factory=dict)
    classifications: dict[str, dict] = field(default_factory=dict)

    async def list_episodes_in_comision(self, comision_id, since):
        return [e for e in self.episodes if UUID(e["comision_id"]) == comision_id]

    async def list_events_for_episode(self, episode_id):
        return self.events_by_episode.get(str(episode_id), [])

    async def get_current_classification(self, episode_id):
        return self.classifications.get(str(episode_id))


def _build_sample_cohort():
    """Genera una cohorte sintética con 3 estudiantes y 4 episodios."""
    comision_id = uuid4()
    student_a = uuid4()
    student_b = uuid4()
    student_c = uuid4()

    ep1, ep2, ep3, ep4 = uuid4(), uuid4(), uuid4(), uuid4()

    now = datetime.now(UTC)
    ts_open = (now - timedelta(days=5)).isoformat().replace("+00:00", "Z")
    ts_close = (now - timedelta(days=5, minutes=-30)).isoformat().replace("+00:00", "Z")

    episodes = [
        # Student A: episodio reflexivo (bien clasificado)
        {
            "id": str(ep1),
            "comision_id": str(comision_id),
            "student_pseudonym": str(student_a),
        },
        # Student A: episodio superficial
        {
            "id": str(ep2),
            "comision_id": str(comision_id),
            "student_pseudonym": str(student_a),
        },
        # Student B: delegación pasiva
        {
            "id": str(ep3),
            "comision_id": str(comision_id),
            "student_pseudonym": str(student_b),
        },
        # Student C: sin clasificación aún
        {
            "id": str(ep4),
            "comision_id": str(comision_id),
            "student_pseudonym": str(student_c),
        },
    ]

    events_by_episode = {
        str(ep1): [
            {"seq": 0, "event_type": "episodio_abierto", "ts": ts_open, "payload": {}},
            {
                "seq": 1,
                "event_type": "prompt_enviado",
                "ts": ts_open,
                "payload": {"content": "qué es recursión", "prompt_kind": "solicitud_directa"},
            },
            {"seq": 2, "event_type": "tutor_respondio", "ts": ts_open, "payload": {}},
            {"seq": 3, "event_type": "codigo_ejecutado", "ts": ts_open, "payload": {}},
            {"seq": 4, "event_type": "anotacion_creada", "ts": ts_open, "payload": {}},
            {"seq": 5, "event_type": "episodio_cerrado", "ts": ts_close, "payload": {}},
        ],
        str(ep2): [
            {"seq": 0, "event_type": "episodio_abierto", "ts": ts_open, "payload": {}},
            {"seq": 1, "event_type": "prompt_enviado", "ts": ts_open, "payload": {}},
            {"seq": 2, "event_type": "tutor_respondio", "ts": ts_open, "payload": {}},
            {"seq": 3, "event_type": "episodio_cerrado", "ts": ts_close, "payload": {}},
        ],
        str(ep3): [
            {"seq": 0, "event_type": "episodio_abierto", "ts": ts_open, "payload": {}},
            {"seq": 1, "event_type": "codigo_ejecutado", "ts": ts_open, "payload": {}},
            {"seq": 2, "event_type": "codigo_ejecutado", "ts": ts_open, "payload": {}},
            {"seq": 3, "event_type": "episodio_cerrado", "ts": ts_close, "payload": {}},
        ],
        str(ep4): [
            {"seq": 0, "event_type": "episodio_abierto", "ts": ts_open, "payload": {}},
        ],
    }

    classifications = {
        str(ep1): {
            "appropiation": "apropiacion_reflexiva",
            "classifier_config_hash": "d" * 64,
            "ct_summary": 0.82,
            "ccd_mean": 0.78,
            "ccd_orphan_ratio": 0.10,
            "cii_stability": 0.65,
            "cii_evolution": 0.70,
        },
        str(ep2): {
            "appropiation": "apropiacion_superficial",
            "classifier_config_hash": "d" * 64,
            "ct_summary": 0.45,
            "ccd_mean": 0.40,
            "ccd_orphan_ratio": 0.50,
            "cii_stability": 0.30,
            "cii_evolution": 0.30,
        },
        str(ep3): {
            "appropiation": "delegacion_pasiva",
            "classifier_config_hash": "d" * 64,
            "ct_summary": 0.20,
            "ccd_mean": 0.10,
            "ccd_orphan_ratio": 0.95,
            "cii_stability": 0.15,
            "cii_evolution": 0.10,
        },
        # ep4: sin clasificar
    }

    return FakeCohortDataSource(episodes, events_by_episode, classifications), comision_id


# ── Tests principales ─────────────────────────────────────────────────


async def test_export_incluye_todos_los_episodios() -> None:
    ds, comision_id = _build_sample_cohort()
    exporter = AcademicExporter(ds, salt="test_salt_for_testing_12345", cohort_alias="TEST")
    dataset = await exporter.export_cohort(comision_id, period_days=30)

    assert dataset.total_episodes == 4
    assert dataset.total_students == 3  # A, B, C
    assert dataset.cohort_alias == "TEST"


async def test_export_anonimiza_determinísticamente() -> None:
    """Mismo UUID + mismo salt → mismo alias (para que investigadores
    con el mismo salt puedan cross-referenciar)."""
    ds, comision_id = _build_sample_cohort()
    e1 = AcademicExporter(ds, salt="salt_one_research_group_abc")
    e2 = AcademicExporter(ds, salt="salt_one_research_group_abc")

    d1 = await e1.export_cohort(comision_id)
    d2 = await e2.export_cohort(comision_id)

    aliases1 = sorted(e.student_alias for e in d1.episodes)
    aliases2 = sorted(e.student_alias for e in d2.episodes)
    assert aliases1 == aliases2


async def test_salt_distinto_produce_aliases_distintos() -> None:
    """Dos investigadores con salts distintos NO pueden cross-referenciar.
    Esto es la propiedad crítica de la anonimización."""
    ds, comision_id = _build_sample_cohort()
    e1 = AcademicExporter(ds, salt="investigador_uno_xxxxxx")
    e2 = AcademicExporter(ds, salt="investigador_dos_xxxxxx")

    d1 = await e1.export_cohort(comision_id)
    d2 = await e2.export_cohort(comision_id)

    # Ningún alias de e1 debe aparecer en e2
    aliases1 = {e.student_alias for e in d1.episodes}
    aliases2 = {e.student_alias for e in d2.episodes}
    assert aliases1.isdisjoint(aliases2)


async def test_salt_corto_se_rechaza() -> None:
    ds, _ = _build_sample_cohort()
    with pytest.raises(ValueError, match="salt"):
        AcademicExporter(ds, salt="corto")  # < 16 chars


async def test_export_preserva_clasificaciones_y_coherencias() -> None:
    ds, comision_id = _build_sample_cohort()
    exporter = AcademicExporter(ds, salt="research_salt_analysis_2026")
    dataset = await exporter.export_cohort(comision_id)

    reflexivo = next(e for e in dataset.episodes if e.appropriation == "apropiacion_reflexiva")
    assert reflexivo.ct_summary == pytest.approx(0.82)
    assert reflexivo.ccd_orphan_ratio == pytest.approx(0.10)
    assert reflexivo.cii_stability == pytest.approx(0.65)


async def test_export_cuenta_eventos_por_tipo() -> None:
    ds, comision_id = _build_sample_cohort()
    exporter = AcademicExporter(ds, salt="research_salt_analysis_2026")
    dataset = await exporter.export_cohort(comision_id)

    # Episodio 1: 1 prompt, 1 code_exec, 1 anotacion
    ep1 = next(e for e in dataset.episodes if e.appropriation == "apropiacion_reflexiva")
    assert ep1.prompt_count == 1
    assert ep1.code_execution_count == 1
    assert ep1.annotation_count == 1

    # Episodio 3 (delegación): 0 prompts, 2 code_exec, 0 anotaciones
    ep3 = next(e for e in dataset.episodes if e.appropriation == "delegacion_pasiva")
    assert ep3.prompt_count == 0
    assert ep3.code_execution_count == 2
    assert ep3.annotation_count == 0


async def test_distribution_summary_correcto() -> None:
    ds, comision_id = _build_sample_cohort()
    exporter = AcademicExporter(ds, salt="research_salt_analysis_2026")
    dataset = await exporter.export_cohort(comision_id)

    assert dataset.distribution_summary["apropiacion_reflexiva"] == 1
    assert dataset.distribution_summary["apropiacion_superficial"] == 1
    assert dataset.distribution_summary["delegacion_pasiva"] == 1
    assert dataset.distribution_summary["sin_clasificar"] == 1


async def test_include_prompts_false_por_default_no_incluye_texto() -> None:
    """Por default los prompts se excluyen (minimización de riesgo de re-identificación)."""
    ds, comision_id = _build_sample_cohort()
    exporter = AcademicExporter(ds, salt="research_salt_analysis_2026")
    dataset = await exporter.export_cohort(comision_id)

    for ep in dataset.episodes:
        assert ep.prompts == []


async def test_include_prompts_true_incluye_texto() -> None:
    ds, comision_id = _build_sample_cohort()
    exporter = AcademicExporter(ds, salt="research_salt_analysis_2026")
    dataset = await exporter.export_cohort(comision_id, include_prompts=True)

    # El episodio 1 tiene 1 prompt con content
    ep1 = next(
        e
        for e in dataset.episodes
        if e.prompt_count > 0 and e.appropriation == "apropiacion_reflexiva"
    )
    assert len(ep1.prompts) == 1
    assert ep1.prompts[0]["content"] == "qué es recursión"


async def test_dataset_serializable_a_json() -> None:
    """El to_dict debe producir un dict serializable."""
    import json

    ds, comision_id = _build_sample_cohort()
    exporter = AcademicExporter(ds, salt="research_salt_analysis_2026")
    dataset = await exporter.export_cohort(comision_id)

    serialized = json.dumps(dataset.to_dict(), ensure_ascii=False)
    # No debe fallar + no debe contener el UUID real de ningún estudiante
    assert '"schema_version": "1.0.0"' in serialized
    parsed = json.loads(serialized)
    assert parsed["total_episodes"] == 4
    assert len(parsed["episodes"]) == 4


async def test_salt_hash_se_incluye_para_reproducibilidad() -> None:
    """El hash del salt se incluye para que otros puedan verificar que dos
    exports con el mismo salt son compatibles."""
    ds, comision_id = _build_sample_cohort()
    exporter = AcademicExporter(ds, salt="research_salt_analysis_2026")
    dataset = await exporter.export_cohort(comision_id)

    assert dataset.salt_hash
    assert len(dataset.salt_hash) == 16
    # No debe ser el salt en claro
    assert "research" not in dataset.salt_hash


async def test_episodio_sin_clasificar_queda_registrado() -> None:
    """Episodios sin clasificación aún deben aparecer en el dataset con appropriation=None."""
    ds, comision_id = _build_sample_cohort()
    exporter = AcademicExporter(ds, salt="research_salt_analysis_2026")
    dataset = await exporter.export_cohort(comision_id)

    unclassified = [e for e in dataset.episodes if e.appropriation is None]
    assert len(unclassified) == 1
    assert unclassified[0].ct_summary is None


# ── Privacy guarantees (OBJ-10) ───────────────────────────────────────


async def test_export_no_filtra_uuids_crudos_de_estudiantes_ni_episodios() -> None:
    """OBJ-10 / RN-085: el JSON serializado NO debe contener ningún UUID
    crudo de estudiante o episodio. Toda PII debe pasar por _pseudonymize.

    Esta es la propiedad central del compromiso ético del piloto UTN:
    el dataset exportado a investigadores no permite re-identificación
    sin el salt.
    """
    import json

    ds, comision_id = _build_sample_cohort()
    exporter = AcademicExporter(ds, salt="pilot_utn_salt_strong_2026")
    dataset = await exporter.export_cohort(comision_id, include_prompts=True)
    serialized = json.dumps(dataset.to_dict(), ensure_ascii=False)

    # Recolectar TODOS los UUIDs crudos que NO deben aparecer en el output
    raw_student_uuids = {ep["student_pseudonym"] for ep in ds.episodes}
    raw_episode_uuids = {ep["id"] for ep in ds.episodes}

    for raw_uuid in raw_student_uuids:
        assert raw_uuid not in serialized, (
            f"FUGA DE PII: el UUID crudo del estudiante {raw_uuid} aparece en el export. "
            "El salt no se está aplicando a student_pseudonym."
        )
    for raw_uuid in raw_episode_uuids:
        assert raw_uuid not in serialized, (
            f"FUGA DE PII: el UUID crudo del episodio {raw_uuid} aparece en el export. "
            "El salt no se está aplicando a episode_id."
        )

    # Y el salt en claro tampoco debe aparecer (sólo su hash truncado)
    assert "pilot_utn_salt_strong_2026" not in serialized
    assert dataset.salt_hash in serialized


async def test_export_es_byte_identico_con_mismo_salt_y_misma_data() -> None:
    """GAP-7 / Reproducibilidad: dos exports con el mismo salt sobre la
    misma data deben producir un JSON canónico byte-idéntico (excepto
    el timestamp `exported_at`/`period`, que dependen de wall-clock).

    Sin esta propiedad, la auditabilidad académica de la tesis no se
    sostiene: un revisor no podría regenerar el mismo dataset.
    """
    import json

    ds, comision_id = _build_sample_cohort()
    salt = "thesis_reproducibility_salt_2026"

    e1 = AcademicExporter(ds, salt=salt, cohort_alias="REPRO")
    e2 = AcademicExporter(ds, salt=salt, cohort_alias="REPRO")
    d1 = await e1.export_cohort(comision_id, period_days=30)
    d2 = await e2.export_cohort(comision_id, period_days=30)

    # Normalizamos los campos no-deterministas dependientes de wall-clock
    def _strip_volatile(d: dict) -> dict:
        out = {k: v for k, v in d.items() if k not in {"exported_at", "period"}}
        return out

    body1 = _strip_volatile(d1.to_dict())
    body2 = _strip_volatile(d2.to_dict())

    j1 = json.dumps(body1, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    j2 = json.dumps(body2, sort_keys=True, ensure_ascii=False, separators=(",", ":"))

    assert j1 == j2, "El export NO es reproducible byte-a-byte con el mismo salt"
    # Y las propiedades anonimizadas también coinciden
    assert d1.salt_hash == d2.salt_hash
    assert sorted(e.student_alias for e in d1.episodes) == sorted(
        e.student_alias for e in d2.episodes
    )
    assert sorted(e.episode_alias for e in d1.episodes) == sorted(
        e.episode_alias for e in d2.episodes
    )


# ── ADR-035: include_reflections + audit log ────────────────────────────


def _build_cohort_with_reflections():
    """Cohorte sintetica con un episodio que tiene `reflexion_completada`."""
    comision_id = uuid4()
    student = uuid4()
    ep = uuid4()

    now = datetime.now(UTC)
    ts_open = (now - timedelta(days=2)).isoformat().replace("+00:00", "Z")
    ts_close = (now - timedelta(days=2, minutes=-25)).isoformat().replace("+00:00", "Z")
    ts_reflect = (now - timedelta(days=2, minutes=-30)).isoformat().replace("+00:00", "Z")

    episodes = [
        {
            "id": str(ep),
            "comision_id": str(comision_id),
            "student_pseudonym": str(student),
        }
    ]
    events_by_episode = {
        str(ep): [
            {"seq": 0, "event_type": "episodio_abierto", "ts": ts_open, "payload": {}},
            {"seq": 1, "event_type": "prompt_enviado", "ts": ts_open, "payload": {}},
            {"seq": 2, "event_type": "tutor_respondio", "ts": ts_open, "payload": {}},
            {"seq": 3, "event_type": "codigo_ejecutado", "ts": ts_open, "payload": {}},
            {"seq": 4, "event_type": "episodio_cerrado", "ts": ts_close, "payload": {}},
            {
                "seq": 5,
                "event_type": "reflexion_completada",
                "ts": ts_reflect,
                "payload": {
                    "que_aprendiste": "como pensar el caso base",
                    "dificultad_encontrada": "el tracking del stack mental",
                    "que_haria_distinto": "dibujar el arbol primero",
                    "prompt_version": "reflection/v1.0.0",
                    "tiempo_completado_ms": 5500,
                },
            },
        ]
    }
    classifications = {
        str(ep): {
            "appropiation": "apropiacion_superficial",
            "classifier_config_hash": "d" * 64,
            "ct_summary": 0.5,
            "ccd_mean": 0.5,
            "ccd_orphan_ratio": 0.3,
            "cii_stability": 0.5,
            "cii_evolution": 0.5,
        }
    }

    ds = FakeCohortDataSource(
        episodes=episodes,
        events_by_episode=events_by_episode,
        classifications=classifications,
    )
    return ds, comision_id


async def test_include_reflections_false_por_default_redacta_textos() -> None:
    """Sin flag explicito, los 3 campos textuales se reemplazan por '[redacted]'."""
    ds, comision_id = _build_cohort_with_reflections()
    exporter = AcademicExporter(ds, salt="research_salt_analysis_2026")
    dataset = await exporter.export_cohort(comision_id)

    ep = dataset.episodes[0]
    assert ep.reflection_count == 1
    assert len(ep.reflections) == 1
    r = ep.reflections[0]
    # Metadata SIEMPRE viaja (no identificable)
    assert r["prompt_version"] == "reflection/v1.0.0"
    assert r["tiempo_completado_ms"] == 5500
    # Textos redactados
    assert r["que_aprendiste"] == "[redacted]"
    assert r["dificultad_encontrada"] == "[redacted]"
    assert r["que_haria_distinto"] == "[redacted]"


async def test_include_reflections_true_expone_textos_y_emite_audit_log(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Con flag explicito, los textos viajan integros y se emite audit log.

    El audit log obligatorio se captura via stdout porque structlog escribe
    a su propio sink (configurado por el observability bootstrap en runtime).
    En tests, consume_existing flush + capsys.readouterr() es suficiente para
    verificar que la linea se emitio.
    """
    ds, comision_id = _build_cohort_with_reflections()
    exporter = AcademicExporter(ds, salt="research_salt_analysis_2026")

    dataset = await exporter.export_cohort(comision_id, include_reflections=True)

    ep = dataset.episodes[0]
    r = ep.reflections[0]
    assert r["que_aprendiste"] == "como pensar el caso base"
    assert r["dificultad_encontrada"] == "el tracking del stack mental"
    assert r["que_haria_distinto"] == "dibujar el arbol primero"

    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert "reflections_exported_with_consent" in combined, (
        "Audit log 'reflections_exported_with_consent' no fue emitido"
    )


async def test_include_reflections_false_no_emite_audit_log(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Sin flag, no se emite audit log (no hay consent que registrar)."""
    ds, comision_id = _build_cohort_with_reflections()
    exporter = AcademicExporter(ds, salt="research_salt_analysis_2026")

    await exporter.export_cohort(comision_id)

    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert "reflections_exported_with_consent" not in combined


# ── multi-language-research-integrity (sección 5): lenguaje por episodio ──


def _build_mixed_language_cohort():
    """Cohorte con episodios Java y Python sobre estudiantes DISTINTOS.

    Clave para la prueba de anonimización: el mismo `java` lo comparten dos
    estudiantes distintos (A y B) — el lenguaje no es una huella individual.
    """
    comision_id = uuid4()
    student_a, student_b, student_c = uuid4(), uuid4(), uuid4()
    ep_java_a, ep_java_b, ep_py_c, ep_default_a = uuid4(), uuid4(), uuid4(), uuid4()

    now = datetime.now(UTC)
    ts_open = (now - timedelta(days=3)).isoformat().replace("+00:00", "Z")
    ts_close = (now - timedelta(days=3, minutes=-20)).isoformat().replace("+00:00", "Z")

    def _events(lang_payload: dict) -> list[dict]:
        return [
            {"seq": 0, "event_type": "episodio_abierto", "ts": ts_open, "payload": lang_payload},
            {"seq": 1, "event_type": "episodio_cerrado", "ts": ts_close, "payload": {}},
        ]

    episodes = [
        {"id": str(ep_java_a), "comision_id": str(comision_id), "student_pseudonym": str(student_a)},
        {"id": str(ep_java_b), "comision_id": str(comision_id), "student_pseudonym": str(student_b)},
        {"id": str(ep_py_c), "comision_id": str(comision_id), "student_pseudonym": str(student_c)},
        {
            "id": str(ep_default_a),
            "comision_id": str(comision_id),
            "student_pseudonym": str(student_a),
        },
    ]
    events_by_episode = {
        str(ep_java_a): _events({"language": "java"}),
        str(ep_java_b): _events({"language": "java"}),
        str(ep_py_c): _events({}),  # campo ausente → default python
        str(ep_default_a): _events({"language": "python"}),  # explícito
    }

    ds = FakeCohortDataSource(
        episodes=episodes, events_by_episode=events_by_episode, classifications={}
    )
    ids = {
        "java_a": ep_java_a,
        "java_b": ep_java_b,
        "py_c": ep_py_c,
        "default_a": ep_default_a,
    }
    return ds, comision_id, ids


async def test_5_1_lenguaje_por_episodio_desde_payload_apertura() -> None:
    """5.1: cada episodio declara su lenguaje, tomado del payload de apertura;
    el campo ausente cae a python (episodio legacy)."""
    ds, comision_id, ids = _build_mixed_language_cohort()
    exporter = AcademicExporter(ds, salt="mixed_lang_research_salt_2026")
    dataset = await exporter.export_cohort(comision_id)

    by_alias = {e.episode_alias: e for e in dataset.episodes}
    lang_of = lambda ep_id: by_alias[exporter._pseudonymize(ep_id, prefix="e_")].language

    assert lang_of(ids["java_a"]) == "java"
    assert lang_of(ids["java_b"]) == "java"
    assert lang_of(ids["py_c"]) == "python"  # ausente → default
    assert lang_of(ids["default_a"]) == "python"  # explícito
    # Y viaja en el dict serializable
    ep_dict = dataset.to_dict()["episodes"][0]
    assert "language" in ep_dict


async def test_5_2_encabezado_declara_lenguajes_presentes() -> None:
    """5.2: el encabezado del dataset declara los lenguajes presentes,
    ordenados y sin duplicados — visible sin recorrer episodio por episodio."""
    ds, comision_id, _ = _build_mixed_language_cohort()
    exporter = AcademicExporter(ds, salt="mixed_lang_research_salt_2026")
    dataset = await exporter.export_cohort(comision_id)

    assert dataset.languages_present == ["java", "python"]
    assert dataset.to_dict()["languages_present"] == ["java", "python"]


async def test_5_3_lenguaje_no_debilita_la_anonimizacion() -> None:
    """5.3: agregar el lenguaje NO debilita la anonimización vigente.

    El lenguaje es un atributo GRUESO (baja cardinalidad, cerrado) y
    COMPARTIDO entre estudiantes — no aporta a la reidentificación. Se prueba
    que dos estudiantes distintos comparten el mismo lenguaje, que el campo no
    introduce ningún UUID crudo, y que los `student_alias` siguen siendo el
    hash salteado de siempre.
    """
    import json

    ds, comision_id, ids = _build_mixed_language_cohort()
    exporter = AcademicExporter(ds, salt="mixed_lang_research_salt_2026")
    dataset = await exporter.export_cohort(comision_id)

    by_alias = {e.episode_alias: e for e in dataset.episodes}
    rec_a = by_alias[exporter._pseudonymize(ids["java_a"], prefix="e_")]
    rec_b = by_alias[exporter._pseudonymize(ids["java_b"], prefix="e_")]

    # Mismo lenguaje, estudiantes distintos → el lenguaje no es huella individual
    assert rec_a.language == rec_b.language == "java"
    assert rec_a.student_alias != rec_b.student_alias

    # Baja cardinalidad y conjunto cerrado
    assert set(dataset.languages_present) <= {"python", "java"}

    # El campo nuevo no introduce PII: ni UUIDs crudos ni el salt en claro
    serialized = json.dumps(dataset.to_dict(), ensure_ascii=False)
    for ep in ds.episodes:
        assert ep["student_pseudonym"] not in serialized
        assert ep["id"] not in serialized
    assert "mixed_lang_research_salt_2026" not in serialized
