"""El RAG se puede APAGAR, y apagarlo no se parece a que se caiga.

El 2026-09-22 la API de embeddings de Google volvio a cortarse —402 Payment
Required esta vez, 429 la anterior—. El fail-soft del 2026-08-28 hizo su
trabajo: el tutor siguio respondiendo. Pero seguia PAGANDO el intento.

Cada mensaje del alumno disparaba la cadena completa: tutor -> content-service
-> Google, con el backoff del embedder de por medio (1s, despues 2s, despues
se rinde). Tres segundos por turno esperando una API que ya sabiamos que no
iba a contestar, y el alumno esperando los tres segundos.

De ahi `rag_enabled`. Cuando esta en `False` la llamada NO SE HACE. No es un
fail-soft mas rapido: es no salir.

LO QUE ESTE MODULO PROTEGE DE VERDAD
-------------------------------------
Hay dos maneras de que un turno llegue sin material de catedra, y son cosas
DISTINTAS:

    rag_no_disponible   lo intentamos y se rompio        -> hay algo que arreglar
    rag_desactivado     decidimos no intentarlo          -> es la configuracion

Escribir el mismo centinela para las dos es la tentacion barata: el `if` ya
esta escrito, el valor ya existe, y el turno se ve igual desde afuera. Pero
`chunks_used_hash` se PERSISTE en el `prompt_enviado` de cada turno, y esa
columna es con la que despues se afirma como se comporto el sistema.

Si las dos situaciones comparten valor, dentro de seis meses nadie puede
separar en los datos "se nos cayo Google tres dias" de "lo apagamos a
proposito en septiembre". Y el que mire la columna no va a saber que no puede:
va a leer `rag_no_disponible` y va a concluir que hubo una falla.

Un dato que mezcla dos causas es peor que un dato ausente. El ausente se nota.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import UUID, uuid4

import fakeredis.aioredis
import pytest
from tutor_service.services.clients import PromptConfig, RetrievalResult
from tutor_service.services.session import SessionManager
from tutor_service.services.tutor_core import (
    RAG_DESACTIVADO,
    RAG_NO_DISPONIBLE,
    TutorCore,
)

HASH_BUSQUEDA_VACIA = "0" * 64
"""Lo que devuelve el content-service cuando corrio y no encontro chunks."""


class FakeGovernanceClient:
    async def get_prompt(self, name: str, version: str) -> PromptConfig:
        return PromptConfig(
            name=name, version=version, content="Eres un tutor socratico.", hash="abc" + "0" * 61
        )


class ContentEspia:
    """Cuenta las llamadas. Que NO lo llamen es la propiedad que se prueba."""

    def __init__(self) -> None:
        self.llamadas = 0

    async def retrieve(self, **kwargs) -> RetrievalResult:
        self.llamadas += 1
        return RetrievalResult(chunks=[], chunks_used_hash=HASH_BUSQUEDA_VACIA, latency_ms=1.0)


class ContentCaido:
    """El content-service devuelve 500 (por dentro: Google sin credito)."""

    def __init__(self) -> None:
        self.llamadas = 0

    async def retrieve(self, **kwargs) -> RetrievalResult:
        self.llamadas += 1
        raise RuntimeError("Server error '500' for url '.../api/v1/retrieve'")


class ContentQueNoDeberianLlamar(ContentEspia):
    """Cuenta, no explota — y la diferencia importa mas de lo que parece.

    La primera version de este doble tiraba `AssertionError` al ser llamado,
    con un mensaje que explicaba el fallo. Se veia mejor. **No servia:** el
    `except Exception` del fail-soft se traga CUALQUIER excepcion, incluida la
    del test. Al revertir el `if` a proposito para comprobar que el test lo
    detectaba, el test siguio pasando: la llamada ocurria, la assertion se
    disparaba, el fail-soft la capturaba y el turno terminaba normal.

    Un test que pasa cuando el codigo esta roto es peor que no tener test.

    Contra un `except Exception` el unico doble confiable es el que NO depende
    de que su excepcion escape. El contador se lee despues, desde afuera.
    """


class FakeAI:
    async def stream(self, *args, **kwargs) -> AsyncIterator[dict]:
        for t in ("Que ", "pasa ", "si ", "n=0?"):
            yield {"type": "chunk", "content": t}


class FakeCTR:
    def __init__(self) -> None:
        self.published_events: list[dict] = []

    async def publish_event(self, event: dict, tenant_id: UUID, caller_id: UUID) -> str:
        self.published_events.append(event)
        return str(uuid4())

    async def find_open_episode(self, **kwargs) -> None:
        return None


@pytest.fixture
async def redis_client():
    r = fakeredis.aioredis.FakeRedis(decode_responses=True)
    yield r
    await r.aclose()


def _tutor(redis_client, content, ctr: FakeCTR, **kw) -> TutorCore:
    return TutorCore(
        governance=FakeGovernanceClient(),
        content=content,
        ai_gateway=FakeAI(),
        ctr=ctr,
        sessions=SessionManager(redis_client),
        **kw,
    )


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


# ── 1. Apagado quiere decir que no se llama ────────────────────────────────


async def test_con_el_flag_apagado_no_se_llama_al_content_service(redis_client) -> None:
    """La razon de existir del flag: no pagar el viaje que sabemos que falla."""
    espia = ContentQueNoDeberianLlamar()
    ctr = FakeCTR()
    tutor = _tutor(redis_client, espia, ctr, rag_enabled=False)

    texto = await _turno(tutor, await _episodio(tutor))

    assert espia.llamadas == 0, (
        f"se llamo {espia.llamadas} vez/veces al content-service con rag_enabled=False — "
        "el flag no corta la llamada, y el alumno sigue pagando el backoff del embedder"
    )
    assert "n=0" in texto, f"el alumno no recibio respuesta: {texto!r}"
    assert _evento(ctr, "tutor_respondio") is not None


async def test_por_default_el_rag_se_sigue_llamando(redis_client) -> None:
    """El control. Sin esto, un flag que apaga SIEMPRE pasa el test de arriba.

    Default `True` a proposito: el que despliega sin enterarse de esta variable
    tiene que quedar como estaba. Un flag que se apaga solo es un apagon.
    """
    espia = ContentEspia()
    tutor = _tutor(redis_client, espia, FakeCTR())

    await _turno(tutor, await _episodio(tutor))

    assert espia.llamadas == 1, "el default dejo de consultar el RAG"


async def test_el_flag_encendido_explicito_tambien_llama(redis_client) -> None:
    espia = ContentEspia()
    tutor = _tutor(redis_client, espia, FakeCTR(), rag_enabled=True)

    await _turno(tutor, await _episodio(tutor))

    assert espia.llamadas == 1


# ── 2. Apagado y caido no son lo mismo ─────────────────────────────────────


async def test_apagado_y_caido_dejan_centinelas_DISTINTOS(redis_client) -> None:
    """El test que justifica el modulo entero.

    Los dos turnos llegan al LLM sin material y se ven identicos desde afuera.
    Lo unico que los separa despues, en los datos, es este valor.
    """
    ctr_off = FakeCTR()
    await _turno(
        t := _tutor(redis_client, ContentQueNoDeberianLlamar(), ctr_off, rag_enabled=False),
        await _episodio(t),
    )
    ctr_caido = FakeCTR()
    await _turno(
        t2 := _tutor(redis_client, ContentCaido(), ctr_caido),
        await _episodio(t2),
    )

    off = _evento(ctr_off, "prompt_enviado")["payload"]["chunks_used_hash"]
    caido = _evento(ctr_caido, "prompt_enviado")["payload"]["chunks_used_hash"]

    assert off == RAG_DESACTIVADO
    assert caido == RAG_NO_DISPONIBLE
    assert off != caido, (
        "apagar el RAG quedo indistinguible de que se rompa. La columna "
        "`chunks_used_hash` ya no puede responder cual de las dos cosas paso, "
        "y quien la lea va a suponer una falla que nunca ocurrio"
    )


async def test_ninguno_de_los_dos_centinelas_se_confunde_con_busqueda_vacia(
    redis_client,
) -> None:
    """Tercer estado: el RAG CORRIO y no encontro nada. Los tres son distintos."""
    ctr = FakeCTR()
    await _turno(
        t := _tutor(redis_client, ContentQueNoDeberianLlamar(), ctr, rag_enabled=False),
        await _episodio(t),
    )
    off = _evento(ctr, "prompt_enviado")["payload"]["chunks_used_hash"]

    assert off != HASH_BUSQUEDA_VACIA, (
        "'no lo consultamos' quedo igual que 'lo consultamos y no habia nada' — "
        "la cadena estaria afirmando una consulta que no se hizo"
    )
    assert len({RAG_DESACTIVADO, RAG_NO_DISPONIBLE, HASH_BUSQUEDA_VACIA}) == 3


# ── 3. Lo que el fail-soft ya garantizaba, sigue ───────────────────────────


async def test_la_cadena_sigue_contigua_con_el_rag_apagado(redis_client) -> None:
    """Un hueco en la secuencia deja el episodio `integrity_compromised`.

    Seria cambiar tres segundos de latencia por algo bastante peor.
    """
    ctr = FakeCTR()
    await _turno(
        t := _tutor(redis_client, ContentQueNoDeberianLlamar(), ctr, rag_enabled=False),
        await _episodio(t),
    )

    seqs = sorted(e["seq"] for e in ctr.published_events)
    assert seqs == list(range(len(seqs))), f"hueco en la cadena: {seqs}"


async def test_apagar_el_rag_no_apaga_el_contexto_pedagogico(redis_client) -> None:
    """El RAG aporta la BIBLIOGRAFIA. El enunciado, la rubrica, los test_cases,
    el banco socratico y las misconceptions llegan por otras vias y no dependen
    de este flag. Apagarlo pierde las citas, no la clase.
    """
    ctr = FakeCTR()
    await _turno(
        t := _tutor(redis_client, ContentQueNoDeberianLlamar(), ctr, rag_enabled=False),
        await _episodio(t),
    )

    prompt = _evento(ctr, "prompt_enviado")
    assert prompt is not None, "sin `prompt_enviado` no hay turno que auditar"
    assert prompt["payload"].get("content"), "el turno viajo sin el mensaje del alumno"
