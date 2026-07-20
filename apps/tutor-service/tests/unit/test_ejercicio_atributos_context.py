"""F2: los atributos pedagógicos del ejercicio llegan al contexto del tutor.

Verifica que `TutorCore.open_episode` inyecta al system message del LLM TODOS
los atributos relevantes del ejercicio (ADR-048 + F2), en dos casos:

  1. Ejercicio del banco (ADR-047): `tutor_rules` (flags + instrucciones),
     `test_cases` (incluyendo los ocultos con su `expected`, porque el tutor
     es servicio interno), `misconceptions`, `anti_patrones`, `heuristica_cierre`,
     `banco_preguntas`.
  2. TP monolítica (sin `ejercicio_id`): los atributos vienen de la propia TP —
     al menos `enunciado`, `rubrica` y `test_cases`.

NO se toca el prompt template del governance-service: el contexto se CONCATENA
a `prompt.content`. El `prompt_system_hash` sigue siendo el hash del prompt base
(no del system message ensamblado), preservando reproducibilidad del CTR.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import fakeredis.aioredis
import pytest
from tutor_service.services.academic_client import TareaPracticaResponse
from tutor_service.services.clients import PromptConfig, RetrievalResult
from tutor_service.services.session import SessionManager
from tutor_service.services.tutor_core import TutorCore

PROMPT_BASE = "Eres un tutor socrático."
PROMPT_HASH = "a" * 64


class _FakeGov:
    async def get_prompt(self, name: str, version: str) -> PromptConfig:
        return PromptConfig(name=name, version=version, content=PROMPT_BASE, hash=PROMPT_HASH)


class _FakeContent:
    async def retrieve(self, **kwargs) -> RetrievalResult:
        return RetrievalResult(chunks=[], chunks_used_hash="0" * 64, latency_ms=1.0)


class _FakeAI:
    async def stream(self, **kwargs):
        if False:
            yield {"type": "chunk", "content": ""}


def _rich_ejercicio() -> dict:
    """Ejercicio del banco con TODOS los campos pedagógicos poblados."""
    return {
        "titulo": "Suma de una lista",
        "enunciado_md": "Escribí una función que sume los elementos de una lista.",
        "inicial_codigo": "def suma(xs):\n    ...",
        "tutor_rules": {
            "prohibido_dar_solucion": True,
            "forzar_pregunta_antes_de_hint": True,
            "nivel_socratico_minimo": 3,
            "instrucciones_adicionales": "Evitá mencionar la función sum() nativa.",
        },
        "rubrica": {
            "criterios": [
                {"nombre": "Correctitud", "descripcion": "La función devuelve la suma."},
            ]
        },
        "test_cases": [
            {
                "id": "tc1",
                "name": "lista basica",
                "type": "stdin_stdout",
                "code": "[1, 2, 3]",
                "expected": "6",
                "is_public": True,
                "weight": 1.0,
            },
            {
                "id": "tc_hidden",
                "name": "lista vacia oculta",
                "type": "stdin_stdout",
                "code": "[]",
                "expected": "0",
                "is_public": False,
                "weight": 1.0,
            },
        ],
        "banco_preguntas": {
            "n3": [
                {
                    "texto": "¿Cómo acumularías el total mientras recorrés la lista?",
                    "senal_comprension": "menciona un acumulador",
                    "senal_alerta": "quiere indexar sin recorrer",
                }
            ],
        },
        "misconceptions": [
            {
                "descripcion": "Cree que hay que ordenar antes de sumar.",
                "probabilidad_estimada": 0.3,
                "pregunta_diagnostica": "¿El orden cambia la suma total?",
            }
        ],
        "respuesta_pista": [
            {"nivel": 2, "pista": "Pensá en una variable que arranque en cero."},
        ],
        "heuristica_cierre": {
            "tests_min_pasados": 1,
            "heuristica": "El alumno explica por qué el acumulador arranca en 0.",
        },
        "anti_patrones": [
            {
                "patron": "Dar el código completo",
                "descripcion": "Entregar la solución impide el aprendizaje.",
                "mensaje_orientacion": "Preguntá cómo recorrería la lista.",
            }
        ],
    }


def _rich_tp() -> dict:
    """TP monolítica: enunciado propio + rúbrica + test_cases (sin banco)."""
    return {
        "id": str(uuid4()),
        "titulo": "TP1 - Estructuras condicionales",
        "enunciado": "Resolvé el problema de clasificación de un número como par o impar.",
        "inicial_codigo": "n = int(input())\n",
        "rubrica": {"criterios": [{"nombre": "Lógica", "descripcion": "Condición correcta."}]},
        "test_cases": [
            {
                "id": "t1",
                "name": "par",
                "type": "stdin_stdout",
                "code": "4",
                "expected": "par",
                "is_public": True,
                "weight": 0.5,
            },
            {
                "id": "t2",
                "name": "impar oculto",
                "type": "stdin_stdout",
                "code": "7",
                "expected": "impar",
                "is_public": False,
                "weight": 0.5,
            },
        ],
    }


def _published_tp_response(
    tarea_id: UUID, comision_id: UUID, tenant_id: UUID
) -> TareaPracticaResponse:
    now = datetime.now(UTC)
    return TareaPracticaResponse(
        id=tarea_id,
        tenant_id=tenant_id,
        comision_id=comision_id,
        estado="published",
        fecha_inicio=now - timedelta(hours=1),
        fecha_fin=now + timedelta(hours=1),
        permite_pausa=True,
    )


@pytest.fixture
def fake_redis():
    return fakeredis.aioredis.FakeRedis()


def _make_tutor(fake_redis, academic):
    ctr = MagicMock()
    ctr.publish_event = AsyncMock()
    ctr.find_open_episode = AsyncMock(return_value=None)
    tutor = TutorCore(
        governance=_FakeGov(),
        content=_FakeContent(),
        ai_gateway=_FakeAI(),
        ctr=ctr,
        sessions=SessionManager(fake_redis),
        academic=academic,
        default_prompt_version="v1.0.0",
        default_model="claude-sonnet-4-6",
    )
    return tutor, ctr


@pytest.mark.asyncio
async def test_ejercicio_banco_inyecta_todos_los_atributos(fake_redis) -> None:
    """Ejercicio del banco: tutor_rules, test_cases (con ocultos), misconceptions,
    anti_patrones, heuristica y banco socrático llegan al system message."""
    tenant_id = uuid4()
    comision_id = uuid4()
    tarea_id = uuid4()
    ejercicio_id = uuid4()

    academic = AsyncMock()
    academic.get_tarea_practica.return_value = _published_tp_response(
        tarea_id, comision_id, tenant_id
    )
    academic.get_comision.return_value = None
    academic.get_ejercicio_by_id.return_value = _rich_ejercicio()
    academic.resolve_ejercicio_orden_in_tp.return_value = 1

    tutor, _ctr = _make_tutor(fake_redis, academic)

    episode_id = await tutor.open_episode(
        tenant_id=tenant_id,
        comision_id=comision_id,
        student_pseudonym=uuid4(),
        problema_id=tarea_id,
        curso_config_hash="b" * 64,
        classifier_config_hash="c" * 64,
        ejercicio_id=ejercicio_id,
    )

    state = await tutor.sessions.get(episode_id)
    assert state is not None
    system = state.messages[0]["content"]

    # El prompt base NO se reescribe: se concatena el contexto.
    assert system.startswith(PROMPT_BASE)
    # tutor_rules — flags + instrucciones (antes solo llegaba instrucciones).
    assert "Reglas específicas del tutor" in system
    assert "PROHIBIDO" in system
    assert "una pregunta" in system  # forzar_pregunta_antes_de_hint
    assert "N3" in system  # nivel_socratico_minimo
    assert "función sum() nativa" in system  # instrucciones_adicionales
    # test_cases — incluye el oculto y su expected (el tutor es interno).
    assert "Casos de prueba que se evalúan" in system
    assert "lista basica" in system
    assert "lista vacia oculta" in system
    assert "[oculto]" in system
    assert "Salida esperada: 0" in system
    # Resto del andamiaje pedagógico.
    assert "Misconceptions anticipadas" in system
    assert "Anti-patrones específicos del ejercicio" in system
    assert "Heurística de cierre" in system
    assert "Banco socrático" in system
    # El prompt_system_hash es el del prompt base (no del system ensamblado):
    # la inyección de contexto NO afecta la reproducibilidad del CTR.
    assert state.prompt_system_hash == PROMPT_HASH


@pytest.mark.asyncio
async def test_tp_monolitica_inyecta_atributos_de_la_tp(fake_redis) -> None:
    """TP monolítica (sin ejercicio_id): enunciado + rúbrica + test_cases de la
    propia TP llegan al system message del tutor."""
    tenant_id = uuid4()
    comision_id = uuid4()
    tarea_id = uuid4()
    tp_data = _rich_tp()

    academic = AsyncMock()
    academic.get_tarea_practica.return_value = _published_tp_response(
        tarea_id, comision_id, tenant_id
    )
    academic.get_comision.return_value = None
    academic.get_tarea_practica_full.return_value = tp_data

    tutor, _ctr = _make_tutor(fake_redis, academic)

    episode_id = await tutor.open_episode(
        tenant_id=tenant_id,
        comision_id=comision_id,
        student_pseudonym=uuid4(),
        problema_id=tarea_id,
        curso_config_hash="b" * 64,
        classifier_config_hash="c" * 64,
        # ejercicio_id omitido → TP monolítica
    )

    # Se consultó la TP completa para traer sus atributos.
    academic.get_tarea_practica_full.assert_awaited()

    state = await tutor.sessions.get(episode_id)
    assert state is not None
    system = state.messages[0]["content"]

    assert system.startswith(PROMPT_BASE)
    assert "[Trabajo Práctico]" in system
    assert "par o impar" in system  # enunciado de la TP
    assert "Criterios de evaluacion" in system  # rúbrica
    assert "Casos de prueba que se evalúan" in system
    assert "impar oculto" in system
    assert "[oculto]" in system
    assert "Salida esperada: impar" in system
    assert state.prompt_system_hash == PROMPT_HASH


@pytest.mark.asyncio
async def test_tp_monolitica_falla_soft_si_academic_no_responde(fake_redis) -> None:
    """Si get_tarea_practica_full falla, el episodio se abre igual (best-effort)
    con solo el prompt base — no rompe el flujo del alumno."""
    tenant_id = uuid4()
    comision_id = uuid4()
    tarea_id = uuid4()

    academic = AsyncMock()
    academic.get_tarea_practica.return_value = _published_tp_response(
        tarea_id, comision_id, tenant_id
    )
    academic.get_comision.return_value = None
    academic.get_tarea_practica_full.side_effect = RuntimeError("academic caído")

    tutor, _ctr = _make_tutor(fake_redis, academic)

    episode_id = await tutor.open_episode(
        tenant_id=tenant_id,
        comision_id=comision_id,
        student_pseudonym=uuid4(),
        problema_id=tarea_id,
        curso_config_hash="b" * 64,
        classifier_config_hash="c" * 64,
    )

    state = await tutor.sessions.get(episode_id)
    assert state is not None
    # Sin contexto pedagógico: el system message es exactamente el prompt base.
    assert state.messages[0]["content"] == PROMPT_BASE


def test_build_ejercicio_context_incluye_flags_y_test_cases() -> None:
    """Unit directo de _build_ejercicio_context: flags de tutor_rules y
    test_cases (con expected de ocultos) presentes en la salida."""
    tutor = TutorCore(
        governance=_FakeGov(),
        content=_FakeContent(),
        ai_gateway=_FakeAI(),
        ctr=MagicMock(),
        sessions=MagicMock(),
        academic=None,
        default_prompt_version="v1.0.0",
        default_model="claude-sonnet-4-6",
    )
    out = tutor._build_ejercicio_context(_rich_ejercicio(), orden=1)

    assert "[Ejercicio 1]" in out
    assert "PROHIBIDO" in out
    assert "una pregunta" in out
    assert "N3" in out
    assert "función sum() nativa" in out
    assert "lista vacia oculta" in out
    assert "[oculto]" in out
    assert "Salida esperada: 0" in out


def test_build_ejercicio_context_tp_kind_y_enunciado_fallback() -> None:
    """Con kind='Trabajo Práctico' y un dict que usa `enunciado` (no
    `enunciado_md`), el builder produce el bloque correcto."""
    tutor = TutorCore(
        governance=_FakeGov(),
        content=_FakeContent(),
        ai_gateway=_FakeAI(),
        ctr=MagicMock(),
        sessions=MagicMock(),
        academic=None,
        default_prompt_version="v1.0.0",
        default_model="claude-sonnet-4-6",
    )
    out = tutor._build_ejercicio_context(_rich_tp(), orden=None, kind="Trabajo Práctico")

    assert "[Trabajo Práctico]" in out
    assert "par o impar" in out  # vino de `enunciado`
    assert "Casos de prueba que se evalúan" in out
    assert "impar oculto" in out
