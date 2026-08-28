"""El tutor responde aunque el RAG este caido.

El 2026-08-28 se acabo el credito de la API de embeddings de Google —USD 10
prepagos de mayo, sin recarga automatica—. Google empezo a devolver 429, el
content-service lo convirtio en 500, y la llamada del tutor al RAG no tenia
`try`: se llevo puesto al tutor entero. Los alumnos vieron "no disponible" y
no pudieron preguntar nada.

Diez dolares dejaron sin tutor a la cursada, y nadie se entero hasta que un
alumno lo intento.

Lo desproporcionado es lo que importa: el RAG aporta la BIBLIOGRAFIA de
catedra, no lo pedagogico. El enunciado, la rubrica, los test_cases, el banco
socratico N1-N4, las misconceptions y el codigo que el alumno esta escribiendo
ya llegan al modelo por otras vias. El tutor sabe casi todo sin el RAG: perder
el RAG es perder las CITAS, no la clase.

Dos propiedades, y las dos hacen falta:

  1. un fallo del RAG NO tumba el turno — el alumno recibe su respuesta
  2. la cadena del CTR NO miente sobre lo que paso — `chunks_used_hash` sale
     como `rag_no_disponible`, que es distinto del hash de una busqueda vacia

La (2) no es un detalle. Si un fallo del RAG produjera el mismo hash que una
busqueda que corrio y no encontro nada, la cadena afirmaria "se consulto el
material y no habia nada relevante" sobre un turno donde el material nunca se
consulto. El CTR existe justamente para que eso no pase.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import UUID, uuid4

import fakeredis.aioredis
import pytest
from tutor_service.services.clients import PromptConfig, RetrievalResult
from tutor_service.services.session import SessionManager
from tutor_service.services.tutor_core import RAG_NO_DISPONIBLE, TutorCore

HASH_BUSQUEDA_VACIA = "0" * 64
"""Lo que devuelve el content-service cuando corrio y no encontro chunks."""


class FakeGovernanceClient:
    async def get_prompt(self, name: str, version: str) -> PromptConfig:
        return PromptConfig(
            name=name, version=version, content="Eres un tutor socratico.", hash="abc" + "0" * 61
        )


class ContentOK:
    """Corre y no encuentra nada. Es el CONTROL, no el caso de falla."""

    async def retrieve(self, **kwargs) -> RetrievalResult:
        return RetrievalResult(chunks=[], chunks_used_hash=HASH_BUSQUEDA_VACIA, latency_ms=1.0)


class ContentCaido:
    """El content-service devuelve 500 (por dentro: Google sin credito)."""

    def __init__(self, exc: Exception | None = None) -> None:
        self.exc = exc or RuntimeError(
            "Server error '500 Internal Server Error' for url '.../api/v1/retrieve'"
        )
        self.llamadas = 0

    async def retrieve(self, **kwargs) -> RetrievalResult:
        self.llamadas += 1
        raise self.exc


class FakeAI:
    async def stream(self, *args, **kwargs) -> AsyncIterator[dict]:
        # El contrato del stream son dicts con `type`, no strings sueltos.
        for t in ("Que ", "pasa ", "si ", "n=0?"):
            yield {"type": "chunk", "content": t}


class FakeCTR:
    def __init__(self) -> None:
        self.published_events: list[dict] = []

    async def publish_event(self, event: dict, tenant_id: UUID, caller_id: UUID) -> str:
        self.published_events.append(event)
        return str(uuid4())

    async def find_open_episode(self, **kwargs) -> None:
        # `open_episode` la consulta para no abrir un episodio duplicado.
        # Sin este metodo el core caia al fail-soft y ensuciaba el log con un
        # AttributeError que no tiene nada que ver con lo que se prueba acá.
        return None


@pytest.fixture
async def redis_client():
    r = fakeredis.aioredis.FakeRedis(decode_responses=True)
    yield r
    await r.aclose()


async def _episodio(tutor: TutorCore) -> UUID:
    return await tutor.open_episode(
        tenant_id=uuid4(),
        comision_id=uuid4(),
        student_pseudonym=uuid4(),
        problema_id=uuid4(),
        curso_config_hash="c" * 64,
        classifier_config_hash="b" * 64,
    )


def _evento(ctr: FakeCTR, tipo: str) -> dict | None:
    for e in ctr.published_events:
        if e.get("event_type") == tipo:
            return e
    return None


async def _turno(tutor: TutorCore, episode_id: UUID) -> str:
    partes = []
    async for evento in tutor.interact(episode_id, "no entiendo la recursion"):
        if isinstance(evento, dict) and evento.get("type") == "chunk":
            partes.append(evento.get("content", ""))
    return "".join(partes)


# ── 1. El alumno recibe su respuesta ───────────────────────────────────────


async def test_el_tutor_responde_aunque_el_rag_falle(redis_client) -> None:
    """La propiedad principal: el turno no muere."""
    contenido = ContentCaido()
    ctr = FakeCTR()
    tutor = TutorCore(
        governance=FakeGovernanceClient(),
        content=contenido,
        ai_gateway=FakeAI(),
        ctr=ctr,
        sessions=SessionManager(redis_client),
    )
    episode_id = await _episodio(tutor)

    texto = await _turno(tutor, episode_id)

    assert contenido.llamadas == 1, "el RAG se intento (no se salteo silenciosamente)"
    assert "n=0" in texto, f"el alumno no recibio respuesta: {texto!r}"
    assert _evento(ctr, "tutor_respondio") is not None, "no se emitio tutor_respondio"


@pytest.mark.parametrize(
    "exc",
    [
        RuntimeError("500 del content-service"),
        TimeoutError("el content-service no contesto"),
        ConnectionError("content-service caido"),
        ValueError("respuesta ilegible del content-service"),
    ],
    ids=["500", "timeout", "conexion", "respuesta-rota"],
)
async def test_ningun_modo_de_falla_del_rag_tumba_el_turno(redis_client, exc) -> None:
    """El `except Exception` es deliberado: es un servicio de TERCER nivel.

    tutor -> content-service -> Google. Enumerar los modos de falla de esa
    cadena es apostar a conocerlos todos, y el que se escape deja al alumno
    sin tutor.
    """
    ctr = FakeCTR()
    tutor = TutorCore(
        governance=FakeGovernanceClient(),
        content=ContentCaido(exc),
        ai_gateway=FakeAI(),
        ctr=ctr,
        sessions=SessionManager(redis_client),
    )
    texto = await _turno(tutor, await _episodio(tutor))
    assert "n=0" in texto, f"{type(exc).__name__} tumbo el turno"


# ── 2. La cadena no miente ─────────────────────────────────────────────────


async def test_la_cadena_distingue_rag_caido_de_busqueda_vacia(redis_client) -> None:
    """`chunks_used_hash` tiene que decir la verdad sobre lo que paso."""
    ctr_caido = FakeCTR()
    tutor_caido = TutorCore(
        governance=FakeGovernanceClient(),
        content=ContentCaido(),
        ai_gateway=FakeAI(),
        ctr=ctr_caido,
        sessions=SessionManager(redis_client),
    )
    await _turno(tutor_caido, await _episodio(tutor_caido))

    prompt = _evento(ctr_caido, "prompt_enviado")
    assert prompt is not None
    hash_caido = prompt["payload"]["chunks_used_hash"]
    assert hash_caido == RAG_NO_DISPONIBLE, (
        f"la cadena no marca que el RAG no corrio: {hash_caido!r}"
    )
    assert hash_caido != HASH_BUSQUEDA_VACIA, (
        "'el RAG no corrio' quedo indistinguible de 'corrio y no encontro nada' — "
        "la cadena estaria afirmando que se consulto el material"
    )


async def test_una_busqueda_vacia_LEGITIMA_sigue_con_su_hash(redis_client) -> None:
    """El control. Sin esto, marcar TODO como caido tambien pasa el test de arriba."""
    ctr = FakeCTR()
    tutor = TutorCore(
        governance=FakeGovernanceClient(),
        content=ContentOK(),
        ai_gateway=FakeAI(),
        ctr=ctr,
        sessions=SessionManager(redis_client),
    )
    await _turno(tutor, await _episodio(tutor))

    prompt = _evento(ctr, "prompt_enviado")
    assert prompt is not None
    assert prompt["payload"]["chunks_used_hash"] == HASH_BUSQUEDA_VACIA
    assert prompt["payload"]["chunks_used_hash"] != RAG_NO_DISPONIBLE


async def test_la_cadena_sigue_contigua_con_el_rag_caido(redis_client) -> None:
    """El fallo del RAG no puede dejar un hueco en la secuencia del CTR.

    Un hueco deja el episodio `integrity_compromised` de forma permanente:
    seria cambiar 'el alumno se queda sin tutor' por algo peor.
    """
    ctr = FakeCTR()
    tutor = TutorCore(
        governance=FakeGovernanceClient(),
        content=ContentCaido(),
        ai_gateway=FakeAI(),
        ctr=ctr,
        sessions=SessionManager(redis_client),
    )
    await _turno(tutor, await _episodio(tutor))

    seqs = sorted(e["seq"] for e in ctr.published_events)
    assert seqs == list(range(len(seqs))), f"hueco en la cadena: {seqs}"
