"""Endpoints de export a estandares Caliper Analytics 1.2 + xAPI 1.0.3 (P3-1).

Cierran P3-1 del PlanMejora.md — el paper §5.1 declara como "agenda de
extension del sistema instrumental" la compatibilidad con estos estandares.
Esta MVP la materializa con dos endpoints pull-based on-demand:

- `GET /api/v1/export/caliper/{episode_id}` → envelope Caliper 1.2
- `GET /api/v1/export/xapi/{episode_id}` → lista de xAPI 1.0.3 statements

NO son endpoints que envien automaticamente — son pull-based para auditores
externos que pidan formato estandar. El CTR sigue siendo la fuente de verdad
bit-exacta del piloto (paper §5.1, §7.2).

Auth: mismos roles que las consultas analiticas read-only del piloto. La
identidad (X-User-Id, X-Tenant-Id, X-User-Roles) viene por headers, mismo
patron que el resto de analytics-service.

ADR de respaldo: paper §5.1 (agenda explicita), PlanMejora.md P3-1.
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from analytics_service.config import settings
from analytics_service.routes.analytics import get_tenant_id, get_user_id
from analytics_service.services.caliper_xapi_exporter import to_caliper, to_xapi

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/export", tags=["export-standards"])


async def _fetch_episode_events(
    episode_id: UUID, tenant_id: UUID
) -> list[dict]:
    """Fetch eventos del episodio del ctr_store con RLS por tenant.

    Replica el patron de `analytics.py` para fetch de eventos. NO duplica la
    helper porque el original es local a otra funcion — extraerla sin sub-clase
    excederia el scope del MVP.
    """
    # Imports diferidos para evitar startup cost (mismo pattern que analytics.py)
    from ctr_service.models import Event
    from platform_ops import set_tenant_rls

    if not settings.ctr_store_url:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ctr_store_url no configurado (modo dev sin DB real)",
        )

    ctr_engine = create_async_engine(settings.ctr_store_url, pool_size=2)
    try:
        ctr_maker = async_sessionmaker(ctr_engine, expire_on_commit=False)
        async with ctr_maker() as ctr_s:
            await set_tenant_rls(ctr_s, tenant_id)
            stmt = (
                select(Event)
                .where(Event.episode_id == episode_id)
                .where(Event.tenant_id == tenant_id)
                .order_by(Event.seq.asc())
            )
            result = await ctr_s.execute(stmt)
            events = [
                {
                    "id": str(ev.id) if hasattr(ev, "id") else str(ev.seq),
                    "seq": ev.seq,
                    "event_type": ev.event_type,
                    "ts": ev.ts.isoformat().replace("+00:00", "Z") if ev.ts else None,
                    "payload": ev.payload or {},
                    "self_hash": getattr(ev, "self_hash", None),
                    "chain_hash": getattr(ev, "chain_hash", None),
                    "prev_chain_hash": getattr(ev, "prev_chain_hash", None),
                    "labeler_version": getattr(ev, "labeler_version", None),
                    "n_level": getattr(ev, "n_level", None),
                    "student_pseudonym": str(getattr(ev, "student_pseudonym", "")) or None,
                }
                for ev in result.scalars().all()
            ]
    finally:
        await ctr_engine.dispose()

    if not events:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Episode {episode_id} no encontrado o sin eventos en este tenant",
        )
    return events


@router.get("/caliper/{episode_id}")
async def export_caliper(
    episode_id: UUID,
    tenant_id: UUID = Depends(get_tenant_id),
    _user_id: UUID = Depends(get_user_id),
) -> dict:
    """Exporta los eventos del episodio en formato Caliper Analytics 1.2.

    Devuelve envelope con `data: [Event, ...]`. NO altera el CTR (read-only).
    Para verificacion sintactica del output: validar contra JSON Schema de
    Caliper 1.2 (https://www.imsglobal.org/spec/caliper/v1p2/schema).
    """
    events = await _fetch_episode_events(episode_id, tenant_id)
    context = {"episode_id": str(episode_id)}
    return to_caliper(events, context)


@router.get("/xapi/{episode_id}")
async def export_xapi(
    episode_id: UUID,
    tenant_id: UUID = Depends(get_tenant_id),
    _user_id: UUID = Depends(get_user_id),
) -> list[dict]:
    """Exporta los eventos del episodio como lista de xAPI 1.0.3 statements.

    A diferencia de Caliper que envuelve, xAPI cada statement es self-contained.
    Para verificacion sintactica: validar contra xAPI 1.0.3 statement schema
    (https://github.com/adlnet/xapi-spec/blob/master/xAPI-Data.md).
    """
    events = await _fetch_episode_events(episode_id, tenant_id)
    context = {"episode_id": str(episode_id)}
    return to_xapi(events, context)
