"""Resolución del lenguaje de programación por episodio (multi-language-research-integrity).

El lenguaje de un episodio NO se lee de `TareaPractica.language` (valor vivo,
puede cambiar después de abierto el episodio) sino del `payload['language']`
del evento `episodio_abierto` (seq=0) en `ctr_store` — un snapshot del momento
de apertura. Ver `openspec/changes/multi-language-research-integrity/design.md`
(decisión D2, sección Risks: "el valor del payload es un snapshot del momento
de apertura, no una referencia viva. Es lo correcto para trazabilidad: la
cadena CTR registra qué pasó, no qué pasa ahora").

Episodios sin el campo (legacy, previos a esta change) o sin evento de
apertura resuelto se interpretan como `"python"` — único lenguaje soportado
antes de la epic `java-language-model` (ver ADR-058 y el spec
`episode-language-provenance`).

Este módulo vive en `platform_ops` (no en `analytics-service`) porque lo
consumen tanto los 6 endpoints de analytics (sección 4 de la change) como el
export académico (sección 5, `academic_export.py`) — ambos ya dependen de
`platform_ops` para su lógica de agregación cross-DB.
"""

from __future__ import annotations

from collections.abc import Iterable
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

DEFAULT_LANGUAGE = "python"

__all__ = ["DEFAULT_LANGUAGE", "resolve_episode_languages", "languages_present"]


async def resolve_episode_languages(
    ctr_session: AsyncSession,
    tenant_id: UUID,
    episode_ids: Iterable[UUID],
) -> dict[UUID, str]:
    """Resuelve `{episode_id: language}` desde el evento `episodio_abierto`.

    Query batch en UNA sola sesión de `ctr_store` (sin join cross-base):
    `WHERE event_type = 'episodio_abierto' AND episode_id IN (...)`, leyendo
    `payload.get('language', 'python')`.

    Devuelve una entrada para CADA id de `episode_ids` (con el default
    aplicado), no solo para los que tienen evento de apertura resuelto —
    así el caller no tiene que manejar el caso "falta la key" por separado.

    Lista vacía → `{}` sin ejecutar query (evita el IN clause vacío que
    falla en Postgres, mismo guard que `list_unidades_by_ids`).
    """
    # dict.fromkeys en vez de set(): preserva orden de aparición (determinismo
    # en tests), aunque el resultado es un dict así que el orden final no
    # importa para el caller.
    unique_ids = list(dict.fromkeys(episode_ids))
    if not unique_ids:
        return {}

    from ctr_service.models import Event

    stmt = (
        select(Event.episode_id, Event.payload)
        .where(Event.tenant_id == tenant_id)
        .where(Event.event_type == "episodio_abierto")
        .where(Event.episode_id.in_(unique_ids))
    )
    result = await ctr_session.execute(stmt)

    languages: dict[UUID, str] = {}
    for episode_id, payload in result.all():
        # `payload.get(...)` no alcanza cuando la key existe con valor `None`
        # explícito (payload viejo con el campo pero sin setear) — por eso el
        # `or DEFAULT_LANGUAGE` además del default del `.get`.
        languages[episode_id] = (payload or {}).get("language") or DEFAULT_LANGUAGE

    # Episodios sin evento de apertura resuelto (legacy / no encontrado en
    # este tenant): se interpretan como Python — ver docstring del módulo.
    for episode_id in unique_ids:
        languages.setdefault(episode_id, DEFAULT_LANGUAGE)

    return languages


def languages_present(languages: Iterable[str]) -> list[str]:
    """Lista ordenada y sin duplicados de lenguajes presentes.

    Acepta cualquier iterable de strings — típicamente `dict.values()` de
    `resolve_episode_languages()`, ya restringido al subconjunto de episodios
    que efectivamente componen el resultado (post-filtro).
    """
    return sorted(set(languages))
