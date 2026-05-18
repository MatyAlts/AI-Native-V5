"""Service de Universidad.

Los services contienen lógica de dominio, coordinan repos, publican
eventos al bus y escriben el audit log. Los routers solo hacen
validación de request + llaman a services.
"""

from __future__ import annotations

from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from academic_service.auth.dependencies import User
from academic_service.models import AuditLog, Universidad
from academic_service.repositories import CarreraRepository, UniversidadRepository
from academic_service.schemas.universidad import UniversidadCreate, UniversidadUpdate


class UniversidadService:
    """Cada universidad ES su propio tenant (1:1).

    Por convencion enforzada en `create()`: `universidad.id == tenant_id`.
    Esto materializa el aislamiento academico: cada universidad tiene su
    banco de ejercicios, sus comisiones, sus alumnos y sus docentes
    completamente aislados de las otras universidades.

    Solo superadmin puede crearlas. Los docente_admin solo pueden leer/
    editar la propia universidad.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = UniversidadRepository(session)
        self.carreras = CarreraRepository(session)

    async def create(self, data: UniversidadCreate, user: User) -> Universidad:
        # superadmin-only: chequeado en el router con require_permission.
        # Convencion: tenant_id = id. Cada universidad ES su propio tenant.
        new_id = uuid4()
        # RLS forced exige que el INSERT respete `app.current_tenant`.
        # Como estamos creando un tenant NUEVO, lo seteamos en la sesion
        # antes del INSERT (LOCAL = solo dentro de la transaccion).
        await self.session.execute(
            text("SELECT set_config('app.current_tenant', :tid, true)"),
            {"tid": str(new_id)},
        )
        universidad = await self.repo.create(
            {
                "id": new_id,
                "tenant_id": new_id,
                "nombre": data.nombre,
                "codigo": data.codigo,
                "dominio_email": data.dominio_email,
                "keycloak_realm": data.keycloak_realm,
                "config": data.config,
            }
        )
        # DEFERRED F3: emitir UniversidadCreada al bus (Redis Streams).
        # Requiere event_bus client + contrato del evento en platform-contracts.
        # await event_bus.publish(UniversidadCreada(...))
        return universidad

    async def update(self, id_: UUID, data: UniversidadUpdate, user: User) -> Universidad:
        # Verificar que el user puede editar ESTA universidad
        if "superadmin" not in user.roles and user.tenant_id != id_:
            from fastapi import HTTPException, status

            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Solo puede editar la propia universidad",
            )

        obj = await self.repo.get_or_404(id_)
        changes = {k: v for k, v in data.model_dump(exclude_unset=True).items() if v is not None}
        for k, v in changes.items():
            setattr(obj, k, v)

        # Audit log en la misma transacción
        audit = AuditLog(
            tenant_id=user.tenant_id,
            user_id=user.id,
            action="universidad.update",
            resource_type="universidad",
            resource_id=id_,
            changes={"after": changes},
        )
        self.session.add(audit)
        await self.session.flush()
        await self.session.refresh(obj)
        return obj

    async def soft_delete(self, id_: UUID, user: User) -> Universidad:
        if "superadmin" not in user.roles:
            from fastapi import HTTPException, status

            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Solo superadmin puede eliminar universidades",
            )

        # RLS forced: para borrar una universidad de OTRO tenant (caso comun
        # cuando superadmin opera cross-tenant desde el web-admin),
        # necesitamos setear `app.current_tenant` al tenant de la universidad
        # target. Convencion enforzada en `create()`: `tenant_id == id`.
        await self.session.execute(
            text("SELECT set_config('app.current_tenant', :tid, true)"),
            {"tid": str(id_)},
        )

        carreras_activas = await self.carreras.count(filters={"universidad_id": id_})
        if carreras_activas > 0:
            from fastapi import HTTPException, status

            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Universidad tiene {carreras_activas} carreras activas",
            )

        obj = await self.repo.soft_delete(id_)
        audit = AuditLog(
            tenant_id=id_,  # audit en el tenant de la universidad borrada
            user_id=user.id,
            action="universidad.delete",
            resource_type="universidad",
            resource_id=id_,
            changes={"soft_delete": True},
        )
        self.session.add(audit)
        await self.session.flush()
        return obj

    async def get(self, id_: UUID) -> Universidad:
        # Igual que soft_delete: superadmin puede mirar cualquier universidad.
        # Para mantener simple el contrato, seteamos el tenant a la universidad
        # target (convencion tenant_id == id).
        await self.session.execute(
            text("SELECT set_config('app.current_tenant', :tid, true)"),
            {"tid": str(id_)},
        )
        return await self.repo.get_or_404(id_)

    async def list(
        self, limit: int = 50, cursor: UUID | None = None, user: User | None = None
    ) -> list[Universidad]:
        """Lista universidades.

        Por defecto la RLS filtra al tenant del caller. Pero superadmin necesita
        ver TODAS las universidades (para el selector dinamico del web-admin),
        asi que en ese caso desactivamos row_security localmente para la sesion.

        Nota: en dev conectamos como `postgres` (superuser de Postgres) que puede
        bypassear RLS. En produccion, `academic_user` no podra hacer esto y
        habria que migrar a una policy RLS adicional `superadmin_can_view_all`.
        """
        if user is not None and "superadmin" in user.roles:
            # Activa la policy `superadmin_view_all` para esta transaccion.
            await self.session.execute(
                text("SELECT set_config('app.user_roles', :r, true)"),
                {"r": ",".join(user.roles)},
            )
        return await self.repo.list(limit=limit, cursor=cursor)

    async def list_mine(self, user: User, limit: int = 50) -> list[Universidad]:
        """Lista universidades donde el caller tiene rol activo.

        - Superadmin → TODAS (equivalente a `list()` con policy `superadmin_view_all`).
        - Docente → universidades con `usuarios_comision.user_id = caller.id` activa.
        - Estudiante → universidades con `inscripciones.student_pseudonym = caller.id`
          y `inscripciones.estado = 'activa'`.

        Reemplaza la policy laxa `authenticated_can_list`. La policy nueva
        `user_can_view_own_unis` se apoya en la funcion SECURITY DEFINER
        `universidades_for_user(uuid)` (migration 20260515_0002), que bypassa
        RLS de las tablas intermedias pero filtra explicitamente por
        `user_id` / `student_pseudonym`. Solo seteamos `app.current_user_id`
        para que la policy fire.
        """
        if "superadmin" in user.roles:
            return await self.list(limit=limit, user=user)

        # Activa la policy `user_can_view_own_unis` para esta transaccion.
        await self.session.execute(
            text("SELECT set_config('app.current_user_id', :uid, true)"),
            {"uid": str(user.id)},
        )
        # Limit alto + cursor None: queremos todas las unis del caller (suelen
        # ser <10). La policy se encarga de filtrar; el repo solo aplica
        # `deleted_at IS NULL`.
        return await self.repo.list(limit=limit, cursor=None)
