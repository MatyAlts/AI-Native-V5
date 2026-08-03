"""Tests de `resolve_episode_languages` (multi-language-research-integrity, sección 4.1).

Usa SQLite in-memory para `ctr_store` (mismo patrón que `test_real_datasources.py`).
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles

ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(ROOT / "apps/ctr-service/src"))


@compiles(JSONB, "sqlite")
def _compile_jsonb_for_sqlite(element, compiler, **kw):
    return "JSON"


from platform_ops.language_segmentation import (
    DEFAULT_LANGUAGE,
    languages_present,
    resolve_episode_languages,
)

TENANT = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
OTHER_TENANT = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")


@pytest_asyncio.fixture
async def ctr_session() -> AsyncSession:
    from ctr_service.models import Base as CtrBase

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(CtrBase.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        yield session
    await engine.dispose()


async def _add_episode(session: AsyncSession, *, tenant_id: UUID = TENANT) -> UUID:
    from ctr_service.models import Episode

    ep_id = uuid4()
    ep = Episode(
        id=ep_id,
        tenant_id=tenant_id,
        comision_id=uuid4(),
        student_pseudonym=uuid4(),
        problema_id=uuid4(),
        opened_at=datetime.now(UTC),
        prompt_system_hash="p" * 64,
        prompt_system_version="v1.0.0",
        classifier_config_hash="c" * 64,
        curso_config_hash="d" * 64,
        events_count=0,
        last_chain_hash="0" * 64,
    )
    session.add(ep)
    await session.commit()
    return ep_id


async def _add_open_event(
    session: AsyncSession,
    *,
    episode_id: UUID,
    tenant_id: UUID = TENANT,
    payload: dict | None = None,
    seq: int = 0,
    event_type: str = "episodio_abierto",
) -> None:
    from ctr_service.models import Event
    from sqlalchemy import func

    max_id_result = await session.execute(select(func.max(Event.id)))
    max_id = max_id_result.scalar() or 0

    ev = Event(
        id=max_id + 1,
        event_uuid=uuid4(),
        episode_id=episode_id,
        tenant_id=tenant_id,
        seq=seq,
        event_type=event_type,
        ts=datetime.now(UTC),
        payload=payload or {},
        self_hash="a" * 64,
        chain_hash="b" * 64,
        prev_chain_hash="0" * 64,
        prompt_system_hash="p" * 64,
        prompt_system_version="v1.0.0",
        classifier_config_hash="c" * 64,
    )
    session.add(ev)
    await session.commit()


async def test_resuelve_lenguaje_del_payload_de_apertura(ctr_session: AsyncSession) -> None:
    ep = await _add_episode(ctr_session)
    await _add_open_event(ctr_session, episode_id=ep, payload={"language": "java"})

    result = await resolve_episode_languages(ctr_session, TENANT, [ep])

    assert result == {ep: "java"}


async def test_episodio_legacy_sin_campo_language_default_python(
    ctr_session: AsyncSession,
) -> None:
    """Evento episodio_abierto sin `language` en el payload (legacy) → default python."""
    ep = await _add_episode(ctr_session)
    await _add_open_event(ctr_session, episode_id=ep, payload={"comision_id": str(uuid4())})

    result = await resolve_episode_languages(ctr_session, TENANT, [ep])

    assert result == {ep: DEFAULT_LANGUAGE}


async def test_episodio_con_language_explicito_none_default_python(
    ctr_session: AsyncSession,
) -> None:
    """El campo existe pero con valor `null` explícito → default python (no None)."""
    ep = await _add_episode(ctr_session)
    await _add_open_event(ctr_session, episode_id=ep, payload={"language": None})

    result = await resolve_episode_languages(ctr_session, TENANT, [ep])

    assert result == {ep: DEFAULT_LANGUAGE}


async def test_episodio_sin_evento_de_apertura_default_python(ctr_session: AsyncSession) -> None:
    """episode_id que no tiene NINGÚN evento episodio_abierto → default python."""
    ep_sin_evento = uuid4()

    result = await resolve_episode_languages(ctr_session, TENANT, [ep_sin_evento])

    assert result == {ep_sin_evento: DEFAULT_LANGUAGE}


async def test_resuelve_batch_de_varios_episodios_mixtos(ctr_session: AsyncSession) -> None:
    ep_py = await _add_episode(ctr_session)
    ep_java = await _add_episode(ctr_session)
    ep_legacy = await _add_episode(ctr_session)
    await _add_open_event(ctr_session, episode_id=ep_py, payload={"language": "python"})
    await _add_open_event(ctr_session, episode_id=ep_java, payload={"language": "java"})
    await _add_open_event(ctr_session, episode_id=ep_legacy, payload={})

    result = await resolve_episode_languages(ctr_session, TENANT, [ep_py, ep_java, ep_legacy])

    assert result == {ep_py: "python", ep_java: "java", ep_legacy: "python"}


async def test_ignora_eventos_de_otro_tenant(ctr_session: AsyncSession) -> None:
    """Doble filtro (event_type + tenant_id): un episodio con evento en OTRO
    tenant no debe resolverse desde ese evento — cae al default."""
    ep = await _add_episode(ctr_session, tenant_id=OTHER_TENANT)
    await _add_open_event(
        ctr_session, episode_id=ep, tenant_id=OTHER_TENANT, payload={"language": "java"}
    )

    result = await resolve_episode_languages(ctr_session, TENANT, [ep])

    assert result == {ep: DEFAULT_LANGUAGE}


async def test_ignora_eventos_que_no_son_episodio_abierto(ctr_session: AsyncSession) -> None:
    """Un `edicion_codigo` con `language` en el payload NO debe usarse — solo
    el evento de apertura (seq=0, event_type=episodio_abierto) es la fuente."""
    ep = await _add_episode(ctr_session)
    await _add_open_event(ctr_session, episode_id=ep, payload={})  # apertura sin language
    await _add_open_event(
        ctr_session,
        episode_id=ep,
        seq=1,
        event_type="edicion_codigo",
        payload={"language": "java"},
    )

    result = await resolve_episode_languages(ctr_session, TENANT, [ep])

    assert result == {ep: DEFAULT_LANGUAGE}


async def test_lista_vacia_no_ejecuta_query_y_devuelve_dict_vacio(
    ctr_session: AsyncSession,
) -> None:
    result = await resolve_episode_languages(ctr_session, TENANT, [])

    assert result == {}


async def test_dedup_de_ids_repetidos_en_el_input(ctr_session: AsyncSession) -> None:
    ep = await _add_episode(ctr_session)
    await _add_open_event(ctr_session, episode_id=ep, payload={"language": "java"})

    result = await resolve_episode_languages(ctr_session, TENANT, [ep, ep, ep])

    assert result == {ep: "java"}


def test_languages_present_ordena_y_deduplica() -> None:
    assert languages_present(["java", "python", "java", "python"]) == ["java", "python"]


def test_languages_present_de_iterable_vacio_es_lista_vacia() -> None:
    assert languages_present([]) == []
