"""Tests del exporter Caliper Analytics 1.2 + xAPI 1.0.3 (P3-1).

Cubren:
- Mapeo CTR event_type → Caliper Event type + action IRI.
- Mapeo CTR event_type → xAPI verb IRI + display.
- Envelope Caliper (sensor + sendTime + data list).
- Statements xAPI (lista self-contained).
- Preservacion bit-exacta de hashes versionados en extensions.
- Diferenciacion actor: student (Person/Agent) vs tutor-service (SoftwareApplication/Agent+account).

NO cubren:
- Validacion contra JSON Schema oficial de Caliper/xAPI (requeriria descargar
  los schemas + jsonschema lib). El test sintactico es OK pero acotado.
- Endpoints HTTP (necesitan app + DB). Eso seria integration test.

ADR de respaldo: paper §5.1, PlanMejora.md P3-1.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from analytics_service.services.caliper_xapi_exporter import (
    AI_NATIVE_VOCAB_BASE,
    CALIPER_CONTEXT,
    XAPI_VERSION,
    to_caliper,
    to_xapi,
)


# ============================================================================
# Fixtures: eventos CTR sintéticos
# ============================================================================


@pytest.fixture
def episode_id() -> str:
    return str(uuid4())


@pytest.fixture
def student_id() -> str:
    return "b1b1b1b1-0001-0001-0001-000000000001"


@pytest.fixture
def sample_events(student_id: str) -> list[dict]:
    """Una secuencia tipica: abrir → leer → prompt → responder → ejecutar → tests → cerrar."""
    return [
        {
            "id": "evt-001",
            "seq": 1,
            "event_type": "episodio_abierto",
            "ts": "2026-05-17T10:00:00Z",
            "self_hash": "a" * 64,
            "chain_hash": "b" * 64,
            "prev_chain_hash": "0" * 64,
            "labeler_version": "1.2.0",
            "n_level": "meta",
            "student_pseudonym": student_id,
            "payload": {},
        },
        {
            "id": "evt-002",
            "seq": 2,
            "event_type": "lectura_enunciado",
            "ts": "2026-05-17T10:00:10Z",
            "self_hash": "c" * 64,
            "chain_hash": "d" * 64,
            "prev_chain_hash": "b" * 64,
            "labeler_version": "1.2.0",
            "n_level": "N1",
            "student_pseudonym": student_id,
            "payload": {},
        },
        {
            "id": "evt-003",
            "seq": 3,
            "event_type": "prompt_enviado",
            "ts": "2026-05-17T10:01:00Z",
            "self_hash": "e" * 64,
            "chain_hash": "f" * 64,
            "prev_chain_hash": "d" * 64,
            "labeler_version": "1.2.0",
            "n_level": "N4",
            "student_pseudonym": student_id,
            "payload": {
                "content": "Cual es la complejidad de O(n log n) vs O(n^2)?",
                "prompt_system_hash": "1" * 64,
                "chunks_used_hash": "2" * 64,
            },
        },
        {
            "id": "evt-004",
            "seq": 4,
            "event_type": "tutor_respondio",
            "ts": "2026-05-17T10:01:05Z",
            "self_hash": "g" * 64,
            "chain_hash": "h" * 64,
            "prev_chain_hash": "f" * 64,
            "labeler_version": "1.2.0",
            "n_level": "N4",
            "student_pseudonym": None,  # tutor, no es student
            "payload": {
                "content": "Buena pregunta — pensa primero: ¿que hace cada algoritmo?",
                "prompt_system_version": "v1.0.1",
                "chunks_used_hash": "2" * 64,
            },
        },
        {
            "id": "evt-005",
            "seq": 5,
            "event_type": "tests_ejecutados",
            "ts": "2026-05-17T10:05:00Z",
            "self_hash": "i" * 64,
            "chain_hash": "j" * 64,
            "prev_chain_hash": "h" * 64,
            "labeler_version": "1.2.0",
            "n_level": "N3",
            "student_pseudonym": student_id,
            "payload": {
                "test_count_passed": 5,
                "test_count_failed": 0,
            },
        },
        {
            "id": "evt-006",
            "seq": 6,
            "event_type": "episodio_cerrado",
            "ts": "2026-05-17T10:10:00Z",
            "self_hash": "k" * 64,
            "chain_hash": "l" * 64,
            "prev_chain_hash": "j" * 64,
            "labeler_version": "1.2.0",
            "n_level": "meta",
            "student_pseudonym": student_id,
            "payload": {},
        },
    ]


# ============================================================================
# Caliper tests
# ============================================================================


class TestCaliperEnvelope:
    def test_envelope_shape(self, sample_events: list[dict], episode_id: str) -> None:
        envelope = to_caliper(sample_events, {"episode_id": episode_id})
        assert envelope["dataVersion"] == CALIPER_CONTEXT
        assert "sensor" in envelope
        assert "sendTime" in envelope
        assert "data" in envelope
        assert len(envelope["data"]) == len(sample_events)

    def test_missing_episode_id_raises(self, sample_events: list[dict]) -> None:
        with pytest.raises(ValueError, match="episode_id"):
            to_caliper(sample_events, {})

    def test_each_event_has_context(self, sample_events: list[dict], episode_id: str) -> None:
        envelope = to_caliper(sample_events, {"episode_id": episode_id})
        for event in envelope["data"]:
            assert event["@context"] == CALIPER_CONTEXT
            assert "type" in event
            assert "actor" in event
            assert "action" in event
            assert "object" in event
            assert "eventTime" in event


class TestCaliperActorMapping:
    def test_student_event_actor_is_person(
        self, sample_events: list[dict], episode_id: str, student_id: str
    ) -> None:
        envelope = to_caliper(sample_events, {"episode_id": episode_id})
        prompt_event = next(e for e in envelope["data"] if "MessageEvent" in e["type"] and "student" in e["actor"]["id"])
        assert prompt_event["actor"]["type"] == "Person"
        assert student_id in prompt_event["actor"]["id"]

    def test_tutor_event_actor_is_software(
        self, sample_events: list[dict], episode_id: str
    ) -> None:
        envelope = to_caliper(sample_events, {"episode_id": episode_id})
        tutor_event = next(
            e for e in envelope["data"] if e["actor"]["type"] == "SoftwareApplication"
        )
        assert "tutor-service" in tutor_event["actor"]["id"]
        assert tutor_event["actor"]["name"] == "tutor-service"


class TestCaliperEventTypeMapping:
    @pytest.mark.parametrize(
        "ctr_event,expected_caliper_type",
        [
            ("episodio_abierto", "SessionEvent"),
            ("lectura_enunciado", "ViewEvent"),
            ("anotacion_creada", "AnnotationEvent"),
            ("prompt_enviado", "MessageEvent"),
            ("tutor_respondio", "MessageEvent"),
            ("codigo_ejecutado", "ToolUseEvent"),
            ("tests_ejecutados", "AssessmentItemEvent"),
            ("episodio_cerrado", "SessionEvent"),
        ],
    )
    def test_mapping(self, ctr_event: str, expected_caliper_type: str, episode_id: str) -> None:
        evt = {
            "id": "x",
            "event_type": ctr_event,
            "ts": "2026-05-17T10:00:00Z",
            "payload": {},
        }
        envelope = to_caliper([evt], {"episode_id": episode_id})
        assert envelope["data"][0]["type"] == expected_caliper_type

    def test_unknown_event_falls_to_generic_event(self, episode_id: str) -> None:
        evt = {"id": "x", "event_type": "completamente_inventado", "ts": "2026-05-17T10:00:00Z", "payload": {}}
        envelope = to_caliper([evt], {"episode_id": episode_id})
        assert envelope["data"][0]["type"] == "Event"
        assert AI_NATIVE_VOCAB_BASE in envelope["data"][0]["action"]


class TestCaliperExtensions:
    def test_preserves_self_chain_hashes(
        self, sample_events: list[dict], episode_id: str
    ) -> None:
        envelope = to_caliper(sample_events, {"episode_id": episode_id})
        first = envelope["data"][0]
        assert first["extensions"]["self_hash"] == "a" * 64
        assert first["extensions"]["chain_hash"] == "b" * 64

    def test_preserves_labeler_version(
        self, sample_events: list[dict], episode_id: str
    ) -> None:
        envelope = to_caliper(sample_events, {"episode_id": episode_id})
        for ev in envelope["data"]:
            assert ev["extensions"]["labeler_version"] == "1.2.0"

    def test_preserves_prompt_system_hash_in_prompt_event(
        self, sample_events: list[dict], episode_id: str
    ) -> None:
        envelope = to_caliper(sample_events, {"episode_id": episode_id})
        prompt = next(e for e in envelope["data"] if e["object"].get("type") == "Message" and "complejidad" in e["object"].get("body", ""))
        assert prompt["extensions"]["prompt_system_hash"] == "1" * 64
        assert prompt["extensions"]["chunks_used_hash"] == "2" * 64


# ============================================================================
# xAPI tests
# ============================================================================


class TestXapiStatements:
    def test_returns_list(self, sample_events: list[dict], episode_id: str) -> None:
        statements = to_xapi(sample_events, {"episode_id": episode_id})
        assert isinstance(statements, list)
        assert len(statements) == len(sample_events)

    def test_missing_episode_id_raises(self, sample_events: list[dict]) -> None:
        with pytest.raises(ValueError, match="episode_id"):
            to_xapi(sample_events, {})

    def test_each_statement_has_required_fields(
        self, sample_events: list[dict], episode_id: str
    ) -> None:
        statements = to_xapi(sample_events, {"episode_id": episode_id})
        for st in statements:
            assert "actor" in st
            assert "verb" in st
            assert "object" in st
            assert "timestamp" in st
            assert st["version"] == XAPI_VERSION


class TestXapiVerbMapping:
    @pytest.mark.parametrize(
        "ctr_event,expected_verb_substring",
        [
            ("episodio_abierto", "launched"),
            ("lectura_enunciado", "experienced"),
            ("prompt_enviado", "asked"),
            ("tutor_respondio", "answered"),
            ("codigo_ejecutado", "attempted"),
            ("tests_ejecutados", "completed"),
            ("episodio_cerrado", "terminated"),
            ("episodio_abandonado", "suspended"),
            ("reflexion_completada", "reflected"),
        ],
    )
    def test_verb_iri(
        self, ctr_event: str, expected_verb_substring: str, episode_id: str
    ) -> None:
        evt = {"id": "x", "event_type": ctr_event, "ts": "2026-05-17T10:00:00Z", "payload": {}}
        statements = to_xapi([evt], {"episode_id": episode_id})
        assert expected_verb_substring in statements[0]["verb"]["id"]


class TestXapiActorMapping:
    def test_student_actor_has_account(
        self, sample_events: list[dict], episode_id: str, student_id: str
    ) -> None:
        statements = to_xapi(sample_events, {"episode_id": episode_id})
        prompt_st = next(s for s in statements if "asked" in s["verb"]["id"])
        assert prompt_st["actor"]["objectType"] == "Agent"
        assert prompt_st["actor"]["account"]["name"] == student_id

    def test_tutor_actor_is_software_agent(
        self, sample_events: list[dict], episode_id: str
    ) -> None:
        statements = to_xapi(sample_events, {"episode_id": episode_id})
        tutor_st = next(s for s in statements if "answered" in s["verb"]["id"])
        assert tutor_st["actor"]["account"]["name"] == "tutor-service"


class TestXapiResultMapping:
    def test_tests_ejecutados_passed_has_success_true(
        self, sample_events: list[dict], episode_id: str
    ) -> None:
        statements = to_xapi(sample_events, {"episode_id": episode_id})
        tests_st = next(s for s in statements if "completed" in s["verb"]["id"])
        assert "result" in tests_st
        assert tests_st["result"]["success"] is True
        assert tests_st["result"]["completion"] is True

    def test_tests_ejecutados_failed_has_success_false(self, episode_id: str) -> None:
        evt = {
            "id": "x",
            "event_type": "tests_ejecutados",
            "ts": "2026-05-17T10:00:00Z",
            "payload": {"test_count_passed": 3, "test_count_failed": 2},
        }
        statements = to_xapi([evt], {"episode_id": episode_id})
        assert statements[0]["result"]["success"] is False


class TestXapiExtensions:
    def test_context_extensions_have_episode_id(
        self, sample_events: list[dict], episode_id: str
    ) -> None:
        statements = to_xapi(sample_events, {"episode_id": episode_id})
        for st in statements:
            ext_key = next(k for k in st["context"]["extensions"] if "episode_id" in k)
            assert st["context"]["extensions"][ext_key] == episode_id

    def test_preserves_hashes_in_extensions(
        self, sample_events: list[dict], episode_id: str
    ) -> None:
        statements = to_xapi(sample_events, {"episode_id": episode_id})
        prompt_st = next(s for s in statements if "asked" in s["verb"]["id"])
        ext = prompt_st["context"]["extensions"]
        prompt_hash_key = next(k for k in ext if "prompt_system_hash" in k)
        assert ext[prompt_hash_key] == "1" * 64
