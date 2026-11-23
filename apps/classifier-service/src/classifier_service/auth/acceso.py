"""Acceso por comisión a las clasificaciones (HU-017).

Con Clerk toda cuenta trae ``estudiante,docente``: el rol solo no separa a un
alumno de un docente. Lo que separa es la MEMBRESÍA real en
``usuarios_comision`` (academic_main), igual que el gate de lectura del
ctr-service (``ctr_service.auth.dependencies.assert_comision_member``), y para
ver una clasificación, además, ser el dueño del episodio.

Reglas comunes a las dos funciones de abajo:
  - oversight (``superadmin``, ``docente_admin``) pasa sin consultar nada;
  - ``settings.enforce_comision_access = False`` (opt-out de dev) es no-op;
  - sin ``settings.academic_db_url`` falla CERRADO con 503 (salvo el dueño en
    la de ver);
  - si no, 403.

Los dos seams (``es_miembro_de_comision`` y ``es_duenio_del_episodio``) se
llaman por el global del módulo a propósito: las pruebas los reemplazan con
monkeypatch.
"""

from __future__ import annotations

import logging
from uuid import UUID

import httpx
from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from classifier_service.auth import User
from classifier_service.config import settings

logger = logging.getLogger(__name__)

# Visión total de las clasificaciones del tenant (lectura y revisión).
OVERSIGHT_ROLES = frozenset({"superadmin", "docente_admin"})

_academic_engine: AsyncEngine | None = None


def _get_academic_engine() -> AsyncEngine:
    """Engine de solo-lectura a academic_main, solo para resolver membresía."""
    global _academic_engine
    if _academic_engine is None:
        _academic_engine = create_async_engine(
            settings.academic_db_url,
            pool_size=1,
            max_overflow=2,
            pool_pre_ping=True,
            echo=settings.db_echo,
        )
    return _academic_engine


async def es_miembro_de_comision(tenant_id: UUID, user_id: UUID, comision_id: UUID) -> bool:
    """`True` si `user_id` está asignado a `comision_id` en `usuarios_comision`.

    Mismo SQL que ``ctr_service.auth.dependencies._is_comision_member``, con RLS
    por tenant. Conexión aparte: no hay joins cross-base.
    """
    from platform_ops import set_tenant_rls

    engine = _get_academic_engine()
    async with async_sessionmaker(engine, expire_on_commit=False)() as s:
        await set_tenant_rls(s, tenant_id)
        row = (
            await s.execute(
                text(
                    "SELECT 1 FROM usuarios_comision "
                    "WHERE comision_id = :c AND user_id = :u "
                    "AND deleted_at IS NULL LIMIT 1"
                ),
                {"c": str(comision_id), "u": str(user_id)},
            )
        ).first()
    return row is not None


async def es_duenio_del_episodio(user: User, episode_id: UUID) -> bool:
    """`True` si `user` es el alumno del episodio.

    La clasificación no guarda al alumno: se le pregunta al ctr-service con la
    identidad del propio usuario (como ``classify_ep._fetch_episode_from_ctr``)
    y se compara ``student_pseudonym``. El ctr-service deja leer al dueño sin
    consultar la base académica. Cualquier error (red, 403, 404, respuesta
    rara) es `False`: ante la duda, no es dueño.
    """
    headers = {
        "X-User-Id": str(user.id),
        "X-Tenant-Id": str(user.tenant_id),
        "X-User-Email": user.email,
        "X-User-Roles": ",".join(user.roles),
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(
                f"{settings.ctr_service_url}/api/v1/episodes/{episode_id}",
                headers=headers,
            )
        if r.status_code != 200:
            return False
        return str(r.json().get("student_pseudonym")) == str(user.id)
    except Exception:
        logger.warning("es_duenio_del_episodio: no se pudo consultar el ctr-service", exc_info=True)
        return False


def _sin_base_academica() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=(
            "No se puede verificar el acceso a la comision: falta ACADEMIC_DB_URL "
            "en el classifier-service."
        ),
    )


async def assert_docente_de_comision(user: User, comision_id: UUID) -> None:
    """Lanza 403/503 si `user` no puede revisar clasificaciones de `comision_id`."""
    if user.roles & OVERSIGHT_ROLES:
        return
    if not settings.enforce_comision_access:
        return
    if not settings.academic_db_url:
        raise _sin_base_academica()
    if not await es_miembro_de_comision(user.tenant_id, user.id, comision_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No sos docente asignado a la comision de este episodio.",
        )


async def assert_puede_ver_clasificacion(user: User, episode_id: UUID, comision_id: UUID) -> None:
    """Lanza 403/503 si `user` no puede ver la clasificación del episodio.

    Pasan oversight, los miembros de la comisión y el dueño del episodio. El
    dueño pasa aunque falte la base académica. La membresía se mira primero
    porque es una consulta local; el dueño cuesta un pedido al ctr-service.
    """
    if user.roles & OVERSIGHT_ROLES:
        return
    if not settings.enforce_comision_access:
        return
    if settings.academic_db_url and await es_miembro_de_comision(
        user.tenant_id, user.id, comision_id
    ):
        return
    if await es_duenio_del_episodio(user, episode_id):
        return
    if not settings.academic_db_url:
        raise _sin_base_academica()
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="No tenes acceso a la clasificacion de este episodio.",
    )


__all__ = [
    "OVERSIGHT_ROLES",
    "assert_docente_de_comision",
    "assert_puede_ver_clasificacion",
    "es_duenio_del_episodio",
    "es_miembro_de_comision",
]
