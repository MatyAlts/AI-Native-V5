"""Tests del SessionManager usando fakeredis."""

from __future__ import annotations

from uuid import uuid4

import fakeredis.aioredis
import pytest
from tutor_service.services.session import SessionManager, SessionState


@pytest.fixture
async def redis_client():
    client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    yield client
    await client.aclose()


def _make_state() -> SessionState:
    return SessionState(
        episode_id=uuid4(),
        tenant_id=uuid4(),
        comision_id=uuid4(),
        student_pseudonym=uuid4(),
        seq=0,
        messages=[{"role": "system", "content": "prompt base"}],
        prompt_system_hash="a" * 64,
        prompt_system_version="v1.0.0",
        classifier_config_hash="b" * 64,
        curso_config_hash="c" * 64,
    )


async def test_get_no_existe_devuelve_none(redis_client) -> None:
    mgr = SessionManager(redis_client)
    result = await mgr.get(uuid4())
    assert result is None


async def test_set_y_get_round_trip(redis_client) -> None:
    mgr = SessionManager(redis_client)
    state = _make_state()
    await mgr.set(state)

    loaded = await mgr.get(state.episode_id)
    assert loaded is not None
    assert loaded.episode_id == state.episode_id
    assert loaded.tenant_id == state.tenant_id
    assert loaded.seq == 0
    assert loaded.messages == state.messages
    assert loaded.prompt_system_hash == "a" * 64


async def test_next_seq_es_incremental(redis_client) -> None:
    mgr = SessionManager(redis_client)
    state = _make_state()
    await mgr.set(state)

    s0 = await mgr.next_seq(state)
    s1 = await mgr.next_seq(state)
    s2 = await mgr.next_seq(state)
    assert (s0, s1, s2) == (0, 1, 2)

    # El state se persistió con el seq incrementado
    reloaded = await mgr.get(state.episode_id)
    assert reloaded.seq == 3


async def test_delete_remueve_session(redis_client) -> None:
    mgr = SessionManager(redis_client)
    state = _make_state()
    await mgr.set(state)

    assert await mgr.get(state.episode_id) is not None
    await mgr.delete(state.episode_id)
    assert await mgr.get(state.episode_id) is None


async def test_sessions_son_independientes(redis_client) -> None:
    mgr = SessionManager(redis_client)
    s1 = _make_state()
    s2 = _make_state()
    await mgr.set(s1)
    await mgr.set(s2)
    await mgr.next_seq(s1)
    await mgr.next_seq(s1)

    loaded1 = await mgr.get(s1.episode_id)
    loaded2 = await mgr.get(s2.episode_id)
    assert loaded1.seq == 2
    assert loaded2.seq == 0
