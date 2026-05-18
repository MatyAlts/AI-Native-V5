"""Service de Comisión.

Valida que el período esté abierto antes de crear, que la materia
pertenezca al tenant del user, y emite ComisionCreada al bus.
"""

from __future__ import annotations

import builtins
from datetime import date
from uuid import UUID, uuid4

from fastapi import HTTPException, status
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from academic_service.auth.dependencies import User
from academic_service.models import AuditLog, Comision, Inscripcion, Periodo, UsuarioComision
from academic_service.repositories import (
    ComisionRepository,
    InscripcionRepository,
    MateriaRepository,
    PeriodoRepository,
    UsuarioComisionRepository,
)
from academic_service.schemas.comision import (
    ComisionCreate,
    ComisionUpdate,
    PeriodoCreate,
    PeriodoUpdate,
)
from academic_service.schemas.inscripcion import InscripcionCreateIndividual
from academic_service.schemas.usuario_comision import UsuarioComisionCreate


class PeriodoService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = PeriodoRepository(session)
        self.comisiones = ComisionRepository(session)

    async def _find_overlapping(
        self,
        fecha_inicio: date,
        fecha_fin: date,
        exclude_id: UUID | None = None,
    ) -> list[Periodo]:
        """Busca periodos soft-non-deleted que se solapen con el rango dado.

        Dos rangos [A.inicio, A.fin] y [B.inicio, B.fin] se solapan sii
        `A.inicio <= B.fin AND A.fin >= B.inicio`. Los adyacentes
        (A.fin == B.inicio) NO se consideran overlap — se usa `<` estricto
        en los extremos (A.inicio < B.fin AND A.fin > B.inicio) para
        permitir que el cierre de un periodo coincida con el inicio del
        siguiente.

        Respeta RLS: el tenant se aplica automáticamente vía
        `SET LOCAL app.current_tenant` en la sesión.
        """
        stmt = select(Periodo).where(
            and_(
                Periodo.deleted_at.is_(None),
                Periodo.fecha_inicio < fecha_fin,
                Periodo.fecha_fin > fecha_inicio,
            )
        )
        if exclude_id is not None:
            stmt = stmt.where(Periodo.id != exclude_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def create(self, data: PeriodoCreate, user: User) -> Periodo:
        overlapping = await self._find_overlapping(data.fecha_inicio, data.fecha_fin)
        if overlapping:
            codigos = ", ".join(p.codigo for p in overlapping)
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(f"Las fechas solapan con periodo(s) existente(s): [{codigos}]"),
            )

        new_id = uuid4()
        periodo = await self.repo.create(
            {
                "id": new_id,
                "tenant_id": user.tenant_id,
                "codigo": data.codigo,
                "nombre": data.nombre,
                "fecha_inicio": data.fecha_inicio,
                "fecha_fin": data.fecha_fin,
                "estado": data.estado,
            }
        )
        audit = AuditLog(
            tenant_id=user.tenant_id,
            user_id=user.id,
            action="periodo.create",
            resource_type="periodo",
            resource_id=new_id,
            changes={"after": data.model_dump(mode="json")},
        )
        self.session.add(audit)
        await self.session.flush()
        return periodo

    async def list(self, limit: int = 50, cursor: UUID | None = None) -> list[Periodo]:
        return await self.repo.list(limit=limit, cursor=cursor)

    async def get(self, id_: UUID) -> Periodo:
        return await self.repo.get_or_404(id_)

    async def update(self, id_: UUID, data: PeriodoUpdate, user: User) -> Periodo:
        """Update parcial de periodo.

        Reglas:
        - Si el periodo ya está `cerrado`, no se permite ningún cambio
          (409 Conflict). El cierre es one-way para preservar el
          invariante CTR ("el CTR se sella al cierre del ciclo").
        - La transición `cerrado → abierto` NO está permitida (409).
        - `abierto → cerrado` OK.
        - `fecha_fin > fecha_inicio` si ambos están presentes (ya
          validado por el schema, pero además chequeamos contra los
          valores persistidos cuando solo uno está en el payload).
        - Emite audit log `periodo.update` (RN-016) con los campos
          modificados.
        """
        obj = await self.repo.get_or_404(id_)

        changes = data.model_dump(exclude_unset=True, exclude_none=True)

        # Si el periodo está cerrado, está frozen: no se puede editar nada.
        if obj.estado == "cerrado":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Periodo cerrado, no se puede modificar. "
                    "Si necesitás trazabilidad de un cambio, usá el audit log."
                ),
            )

        # Transición de estado: cerrado → abierto NO permitida.
        new_estado = changes.get("estado")
        if new_estado == "abierto" and obj.estado != "abierto":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "No se puede reabrir un periodo cerrado — "
                    "usar audit log si se necesita trazabilidad"
                ),
            )

        # Validar fecha_fin > fecha_inicio contra valores persistidos
        # cuando solo uno viene en el payload.
        new_inicio = changes.get("fecha_inicio", obj.fecha_inicio)
        new_fin = changes.get("fecha_fin", obj.fecha_fin)
        if new_fin <= new_inicio:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="fecha_fin debe ser posterior a fecha_inicio",
            )

        # Overlap check: si el PATCH toca fechas, verificar que no pisen
        # a otros periodos del tenant (excluyendo el propio).
        if "fecha_inicio" in changes or "fecha_fin" in changes:
            overlapping = await self._find_overlapping(new_inicio, new_fin, exclude_id=obj.id)
            if overlapping:
                codigos = ", ".join(p.codigo for p in overlapping)
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(f"Las fechas solapan con periodo(s) existente(s): [{codigos}]"),
                )

        for k, v in changes.items():
            setattr(obj, k, v)

        audit = AuditLog(
            tenant_id=obj.tenant_id,
            user_id=user.id,
            action="periodo.update",
            resource_type="periodo",
            resource_id=id_,
            changes={"after": changes},
        )
        self.session.add(audit)
        await self.session.flush()
        await self.session.refresh(obj)
        return obj

    async def soft_delete(self, id_: UUID, user: User) -> Periodo:
        comisiones_activas = await self.comisiones.count(filters={"periodo_id": id_})
        if comisiones_activas > 0:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Periodo tiene {comisiones_activas} comisiones activas",
            )

        obj = await self.repo.soft_delete(id_)
        audit = AuditLog(
            tenant_id=obj.tenant_id,
            user_id=user.id,
            action="periodo.delete",
            resource_type="periodo",
            resource_id=id_,
            changes={"soft_delete": True},
        )
        self.session.add(audit)
        await self.session.flush()
        return obj


class ComisionService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = ComisionRepository(session)
        self.materias = MateriaRepository(session)
        self.periodos = PeriodoRepository(session)
        self.inscripciones = InscripcionRepository(session)
        self.usuarios_comision = UsuarioComisionRepository(session)

    async def create(self, data: ComisionCreate, user: User) -> Comision:
        # 1. Validar que la materia existe (RLS la filtra por tenant)
        materia = await self.materias.get_or_404(data.materia_id)

        # 2. Validar que el periodo está abierto
        periodo = await self.periodos.get_or_404(data.periodo_id)
        if periodo.estado != "abierto":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"No se pueden crear comisiones en el periodo '{periodo.codigo}' (estado: {periodo.estado})",
            )

        # 3. Crear
        new_id = uuid4()
        comision = await self.repo.create(
            {
                "id": new_id,
                "tenant_id": user.tenant_id,
                "materia_id": materia.id,
                "periodo_id": periodo.id,
                "codigo": data.codigo,
                "nombre": data.nombre,
                "cupo_maximo": data.cupo_maximo,
                "horario": data.horario,
                "ai_budget_monthly_usd": data.ai_budget_monthly_usd,
            }
        )

        audit = AuditLog(
            tenant_id=user.tenant_id,
            user_id=user.id,
            action="comision.create",
            resource_type="comision",
            resource_id=new_id,
            changes={"after": data.model_dump(mode="json")},
        )
        self.session.add(audit)
        await self.session.flush()

        # DEFERRED F3: publish ComisionCreada event al bus (Redis Streams).
        # Requiere event_bus client + contrato del evento en platform-contracts.
        return comision

    async def update(self, id_: UUID, data: ComisionUpdate, user: User) -> Comision:
        obj = await self.repo.get_or_404(id_)
        changes = data.model_dump(exclude_unset=True, exclude_none=True)
        for k, v in changes.items():
            setattr(obj, k, v)

        audit = AuditLog(
            tenant_id=obj.tenant_id,
            user_id=user.id,
            action="comision.update",
            resource_type="comision",
            resource_id=id_,
            changes={"after": changes},
        )
        self.session.add(audit)
        await self.session.flush()
        await self.session.refresh(obj)
        return obj

    async def soft_delete(self, id_: UUID, user: User) -> Comision:
        inscripciones_activas = await self.inscripciones.count(filters={"comision_id": id_})
        if inscripciones_activas > 0:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Comisión tiene {inscripciones_activas} inscripciones activas",
            )

        obj = await self.repo.soft_delete(id_)
        audit = AuditLog(
            tenant_id=obj.tenant_id,
            user_id=user.id,
            action="comision.delete",
            resource_type="comision",
            resource_id=id_,
            changes={"soft_delete": True},
        )
        self.session.add(audit)
        await self.session.flush()
        return obj

    async def get(self, id_: UUID) -> Comision:
        return await self.repo.get_or_404(id_)

    async def list(
        self,
        limit: int = 50,
        cursor: UUID | None = None,
        materia_id: UUID | None = None,
        periodo_id: UUID | None = None,
    ) -> builtins.list[Comision]:
        filters: dict = {}
        if materia_id:
            filters["materia_id"] = materia_id
        if periodo_id:
            filters["periodo_id"] = periodo_id
        return await self.repo.list(limit=limit, cursor=cursor, filters=filters)

    # ── Docentes de comision ───────────────────────────────────────────

    async def list_docentes(self, comision_id: UUID) -> builtins.list[UsuarioComision]:
        """Devuelve los docentes activos (no soft-deleted) de una comision."""
        await self.repo.get_or_404(comision_id)
        stmt = (
            select(UsuarioComision)
            .where(
                UsuarioComision.comision_id == comision_id,
                UsuarioComision.deleted_at.is_(None),
            )
            .order_by(UsuarioComision.id)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def add_docente(
        self, comision_id: UUID, data: UsuarioComisionCreate, user: User
    ) -> UsuarioComision:
        """Crea un UsuarioComision para la comision dada."""
        comision = await self.repo.get_or_404(comision_id)
        uc = UsuarioComision(
            id=uuid4(),
            tenant_id=comision.tenant_id,
            comision_id=comision_id,
            user_id=data.user_id,
            rol=data.rol,
            fecha_desde=data.fecha_desde,
            fecha_hasta=data.fecha_hasta,
        )
        self.session.add(uc)
        audit = AuditLog(
            tenant_id=comision.tenant_id,
            user_id=user.id,
            action="usuario_comision.create",
            resource_type="usuario_comision",
            resource_id=uc.id,
            changes={"after": data.model_dump(mode="json")},
        )
        self.session.add(audit)
        await self.session.flush()
        await self.session.refresh(uc)
        return uc

    async def remove_docente(self, comision_id: UUID, uc_id: UUID, user: User) -> None:
        """Soft-delete de un UsuarioComision."""
        from academic_service.models.base import utc_now

        stmt = select(UsuarioComision).where(
            UsuarioComision.id == uc_id,
            UsuarioComision.comision_id == comision_id,
            UsuarioComision.deleted_at.is_(None),
        )
        result = await self.session.execute(stmt)
        uc = result.scalar_one_or_none()
        if uc is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asignacion no encontrada")
        uc.deleted_at = utc_now()
        audit = AuditLog(
            tenant_id=uc.tenant_id,
            user_id=user.id,
            action="usuario_comision.delete",
            resource_type="usuario_comision",
            resource_id=uc_id,
            changes={"soft_delete": True},
        )
        self.session.add(audit)
        await self.session.flush()

    # ── Inscripciones de comision ──────────────────────────────────────

    # Roles privilegiados que pueden ver pseudonyms de toda la comisión.
    # Cualquier otro rol (estudiante, oyente, etc.) recibe SOLO su propia
    # inscripción (filtrada por student_pseudonym = user.id) — fix QA A11
    # contra el leak de student_pseudonyms a estudiantes.
    _PRIVILEGED_ROLES_INSCRIPCIONES: frozenset[str] = frozenset(
        {"docente", "docente_admin", "superadmin", "jtp", "auxiliar"}
    )

    async def list_inscripciones(
        self, comision_id: UUID, user: User | None = None
    ) -> builtins.list[Inscripcion]:
        """Devuelve las inscripciones activas de una comision.

        Filtrado por rol (fix QA A11):
          - Roles privilegiados (docente / docente_admin / superadmin /
            jtp / auxiliar) → ven todos los pseudonyms.
          - Cualquier otro caller (estudiante) → solo ve su propia
            inscripción (`WHERE student_pseudonym = user.id`); si no
            está inscripto, response vacío.

        `user=None` mantiene compat con callers internos que ya filtraron
        autorización aguas arriba — tratado como privilegiado.
        """
        await self.repo.get_or_404(comision_id)
        stmt = (
            select(Inscripcion)
            .where(
                Inscripcion.comision_id == comision_id,
                Inscripcion.deleted_at.is_(None),
            )
            .order_by(Inscripcion.id)
        )
        if user is not None and not (
            user.roles & self._PRIVILEGED_ROLES_INSCRIPCIONES
        ):
            # Caller no privilegiado (estudiante) — solo su propia fila
            stmt = stmt.where(Inscripcion.student_pseudonym == user.id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def add_inscripcion(
        self, comision_id: UUID, data: InscripcionCreateIndividual, user: User
    ) -> Inscripcion:
        """Crea una Inscripcion para la comision dada."""
        comision = await self.repo.get_or_404(comision_id)
        insc = Inscripcion(
            id=uuid4(),
            tenant_id=comision.tenant_id,
            comision_id=comision_id,
            student_pseudonym=data.student_pseudonym,
            rol=data.rol,
            estado=data.estado,
            fecha_inscripcion=data.fecha_inscripcion,
            nota_final=data.nota_final,
            fecha_cierre=data.fecha_cierre,
        )
        self.session.add(insc)
        audit = AuditLog(
            tenant_id=comision.tenant_id,
            user_id=user.id,
            action="inscripcion.create",
            resource_type="inscripcion",
            resource_id=insc.id,
            changes={"after": data.model_dump(mode="json")},
        )
        self.session.add(audit)
        await self.session.flush()
        await self.session.refresh(insc)
        return insc

    async def remove_inscripcion(self, comision_id: UUID, insc_id: UUID, user: User) -> None:
        """Soft-delete de una Inscripcion."""
        from academic_service.models.base import utc_now

        stmt = select(Inscripcion).where(
            Inscripcion.id == insc_id,
            Inscripcion.comision_id == comision_id,
            Inscripcion.deleted_at.is_(None),
        )
        result = await self.session.execute(stmt)
        insc = result.scalar_one_or_none()
        if insc is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Inscripcion no encontrada")
        insc.deleted_at = utc_now()
        audit = AuditLog(
            tenant_id=insc.tenant_id,
            user_id=user.id,
            action="inscripcion.delete",
            resource_type="inscripcion",
            resource_id=insc_id,
            changes={"soft_delete": True},
        )
        self.session.add(audit)
        await self.session.flush()

    async def list_for_user(
        self,
        user_id: UUID,
        limit: int = 50,
        cursor: UUID | None = None,
    ) -> builtins.list[Comision]:
        """Devuelve las Comisiones donde `user_id` tiene un rol activo.

        Sólo considera filas de `usuarios_comision` no soft-deleted. La
        ventana de vigencia (`fecha_desde`/`fecha_hasta`) NO se filtra
        acá: la responsabilidad de mostrar comisiones futuras o
        históricas queda en el front (selector). RLS del tenant aplica
        automáticamente vía `tenant_session()`.
        """
        stmt = (
            select(Comision)
            .join(UsuarioComision, UsuarioComision.comision_id == Comision.id)
            .where(
                UsuarioComision.user_id == user_id,
                UsuarioComision.deleted_at.is_(None),
                Comision.deleted_at.is_(None),
            )
        )
        if cursor:
            stmt = stmt.where(Comision.id > cursor)
        stmt = stmt.order_by(Comision.id).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().unique().all())
