"""FIX B: el retry de UI-8 no debe duplicar `prompt_enviado`.

`interact()` emite `prompt_enviado` ANTES del stream del LLM. Si el LLM falla a
mitad (el caso que UI-8 maneja) y el alumno clickea "Reintentar", `interact()`
corre de cero. Sin idempotencia se re-emitiria `prompt_enviado` → prompt huerfano
→ infla CCD_orphan_ratio y el conteo de prompts de la tesis.

Con el fix, EpisodePage reusa el MISMO `messageUuid` en el retry y lo manda como
`Idempotency-Key`; el server lo usa por la via idempotente atomica (FIX A) SOLO
para el `prompt_enviado`, asi el reintento devuelve el mismo seq sin re-publicar.
El `tutor_respondio` SI se emite fresco (es una respuesta nueva del LLM).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import UUID, uuid4

import fakeredis.aioredis
import pytest
from tutor_service.services.clients import PromptConfig, RetrievalResult
from tutor_service.services.session import SessionManager
from tutor_service.services.tutor_core import TutorCore


class FakeGovernanceClient:
    async def get_prompt(self, name: str, version: str) -> PromptConfig:
        return PromptConfig(
            name=name, version=version, content="Eres un tutor socratico.", hash="abc" + "0" * 61
        )


class FakeContentClient:
    async def retrieve(
        self,
        query: str,
        comision_id: UUID,
        top_k: int,
        tenant_id: UUID,
        caller_id: UUID,
        materia_id: UUID | None = None,
    ) -> RetrievalResult:
        return RetrievalResult(chunks=[], chunks_used_hash="0" * 64, latency_ms=1.0)


class FlakyAIGatewayClient:
    """Falla a mitad del stream la primera vez; responde OK a partir de la segunda."""

    def __init__(self) -> None:
        self.calls = 0

    async def stream(
        self,
        messages: list[dict],
        model: str,
        tenant_id: UUID,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        materia_id: UUID | None = None,
    ) -> AsyncIterator[dict]:
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("LLM saturado")
            yield  # pragma: no cover — hace de esto un generador
        yield {"type": "chunk", "content": "respuesta socratica"}


class FakeCTRClient:
    def __init__(self) -> None:
        self.published_events: list[dict] = []

    async def publish_event(self, event: dict, tenant_id: UUID, caller_id: UUID) -> str:
        self.published_events.append(event)
        return f"fake-msg-id-{len(self.published_events)}"


@pytest.fixture
async def redis_client():
    client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    yield client
    await client.aclose()


def _seqs_of(ctr: FakeCTRClient, event_type: str) -> list[int]:
    return [e["seq"] for e in ctr.published_events if e["event_type"] == event_type]


async def test_retry_reusa_key_no_duplica_prompt_enviado(redis_client) -> None:
    ctr = FakeCTRClient()
    ai = FlakyAIGatewayClient()
    tutor = TutorCore(
        governance=FakeGovernanceClient(),
        content=FakeContentClient(),
        ai_gateway=ai,
        ctr=ctr,
        sessions=SessionManager(redis_client),
    )
    episode_id = await tutor.open_episode(
        tenant_id=uuid4(),
        comision_id=uuid4(),
        student_pseudonym=uuid4(),
        problema_id=uuid4(),
        curso_config_hash="c" * 64,
        classifier_config_hash="b" * 64,
    )
    key = str(uuid4())

    # Intento 1: el LLM falla a mitad → prompt_enviado emitido, tutor_respondio NO.
    with pytest.raises(RuntimeError):
        async for _ in tutor.interact(episode_id, "hola tutor", prompt_idempotency_key=key):
            pass

    prompt_seqs = _seqs_of(ctr, "prompt_enviado")
    assert prompt_seqs == [1], "prompt_enviado debe emitirse una vez con seq 1 (tras abierto=0)"
    assert _seqs_of(ctr, "tutor_respondio") == [], "no debe haber respuesta: el LLM fallo"

    # Intento 2 (retry, MISMA key): prompt NO se re-emite; tutor_respondio SI.
    async for _ in tutor.interact(episode_id, "hola tutor", prompt_idempotency_key=key):
        pass

    assert _seqs_of(ctr, "prompt_enviado") == [1], "el prompt_enviado NO debe duplicarse"
    response_seqs = _seqs_of(ctr, "tutor_respondio")
    assert len(response_seqs) == 1, "el retry debe emitir exactamente un tutor_respondio"
    # Contiguidad de la cadena: prompt(1) → tutor_respondio(2), sin hueco.
    assert response_seqs[0] == prompt_seqs[0] + 1

    # La cadena publicada es contigua desde 0.
    all_seqs = sorted(e["seq"] for e in ctr.published_events)
    assert all_seqs == list(range(len(all_seqs))), f"hueco en la cadena: {all_seqs}"


async def test_sin_key_el_retry_si_reemitiria_prompt(redis_client) -> None:
    """Control: sin idempotency_key, dos interact con el mismo texto SI emiten
    dos prompt_enviado (comportamiento legacy) — confirma que es la key la que
    deduplica, no otra cosa."""
    ctr = FakeCTRClient()
    tutor = TutorCore(
        governance=FakeGovernanceClient(),
        content=FakeContentClient(),
        ai_gateway=FlakyAIGatewayClient(),
        ctr=ctr,
        sessions=SessionManager(redis_client),
    )
    episode_id = await tutor.open_episode(
        tenant_id=uuid4(),
        comision_id=uuid4(),
        student_pseudonym=uuid4(),
        problema_id=uuid4(),
        curso_config_hash="c" * 64,
        classifier_config_hash="b" * 64,
    )

    with pytest.raises(RuntimeError):
        async for _ in tutor.interact(episode_id, "hola"):
            pass
    async for _ in tutor.interact(episode_id, "hola"):
        pass

    assert len(_seqs_of(ctr, "prompt_enviado")) == 2  # sin dedup, se re-emite
