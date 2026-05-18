"""Service de Tarea Práctica (TP).

Las versiones publicadas son inmutables: PATCH sobre una tarea con
`estado != 'draft'` retorna 409. Las transiciones de estado
(draft → published → archived) viven en `publish`/`archive`. Para
"editar" una tarea publicada/archivada se debe crear una nueva versión
vía `new_version`, que produce una nueva fila en draft con
`version=parent.version+1` y `parent_tarea_id=parent.id`. El soft
delete deberá validar que no haya episodios CTR activos referenciando
la tarea — DEFERRED hasta que exista mecanismo cross-service (bus o HTTP
client a ctr-service). Ver soft_delete() para el guard pendiente.

Drift detection (ADR-016)
-------------------------

Si la instancia tiene `template_id IS NOT NULL` y `has_drift=False`, un
PATCH que cambia alguno de los **campos canónicos** (los heredados del
template al instanciar) setea `has_drift=True` automáticamente. Una vez
drifteada, la instancia queda apuntando al template viejo y NO se
re-instancia al versionar el template. `new_version` hereda tanto el
`template_id` como el `has_drift` del parent para no "lavar" drift.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from academic_service.auth.dependencies import User
from academic_service.models import AuditLog, TareaPractica
from academic_service.repositories import (
    ComisionRepository,
    TareaPracticaRepository,
)
from academic_service.schemas.tarea_practica import (
    TareaPracticaCreate,
    TareaPracticaUpdate,
)

# Campos canónicos que disparan drift al editarse en una instancia con
# `template_id IS NOT NULL`. Son exactamente los campos que el template
# proyecta sobre la instancia al fan-out (ver
# `TareaPracticaTemplateService.create`). Cualquier otro campo (estado,
# version, parent_tarea_id, etc.) NO dispara drift porque no forma parte
# de la "fuente canónica" del template.
DRIFT_TRIGGERING_FIELDS: frozenset[str] = frozenset(
    {
        "titulo",
        "enunciado",
        "inicial_codigo",
        "rubrica",
        "peso",
        "fecha_inicio",
        "fecha_fin",
    }
)


class TareaPracticaService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = TareaPracticaRepository(session)
        self.comisiones = ComisionRepository(session)

    async def create(self, data: TareaPracticaCreate, user: User) -> TareaPractica:
        # Validar que la comisión existe (RLS la filtra por tenant)
        comision = await self.comisiones.get_or_404(data.comision_id)

        new_id = uuid4()
        tarea = await self.repo.create(
            {
                "id": new_id,
                "tenant_id": user.tenant_id,
                "comision_id": comision.id,
                "codigo": data.codigo,
                "titulo": data.titulo,
                "enunciado": data.enunciado,
                "inicial_codigo": data.inicial_codigo,
                "fecha_inicio": data.fecha_inicio,
                "fecha_fin": data.fecha_fin,
                "peso": data.peso,
                "rubrica": data.rubrica,
                "estado": "draft",
                "version": 1,
                "parent_tarea_id": None,
                "template_id": data.template_id,
                "has_drift": False,
                "created_by": user.id,
                # ADR-036: trazabilidad de TPs creadas via wizard IA
                "created_via_ai": data.created_via_ai,
                # ADR-041: propagate unidad_id at creation
                "unidad_id": getattr(data, "unidad_id", None),
            }
        )

        audit = AuditLog(
            tenant_id=user.tenant_id,
            user_id=user.id,
            action="tarea_practica.create",
            resource_type="tarea_practica",
            resource_id=new_id,
            changes={"after": data.model_dump(mode="json")},
        )
        self.session.add(audit)
        await self.session.flush()
        return tarea

    # Campos que se pueden actualizar en TPs published/archived (metadata
    # organizativa, NO contenido pedagógico inmutable).
    _MUTABLE_REGARDLESS_OF_ESTADO = {"unidad_id"}

    async def update(self, id_: UUID, data: TareaPracticaUpdate, user: User) -> TareaPractica:
        obj = await self.repo.get_or_404(id_)
        changes = data.model_dump(exclude_unset=True)
        change_keys = set(changes.keys())
        only_mutable = change_keys <= self._MUTABLE_REGARDLESS_OF_ESTADO
        if obj.estado != "draft" and not only_mutable:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Tarea en estado '{obj.estado}' es inmutable; cree una nueva versión",
            )

        # ADR-041: `unidad_id=null` significa "quitar TP de la Unidad".
        # `exclude_none=True` lo eliminaría, así que capturamos antes.
        unidad_id_explicitly_set = "unidad_id" in data.model_fields_set
        unidad_id_value = data.unidad_id  # puede ser None (quitar) o UUID (asignar)

        changes = data.model_dump(exclude_unset=True, exclude_none=True)
        # Quitar unidad_id de changes para aplicarlo por separado (acepta None)
        changes.pop("unidad_id", None)

        # Drift detection (ADR-016): si la instancia viene del template y todavía
        # no está drifteada, ver si alguno de los campos canónicos del patch
        # cambia de valor respecto al obj actual. Si sí, marcar drift.
        drift_triggered = False
        if obj.template_id is not None and obj.has_drift is False:
            for field, new_value in changes.items():
                if field not in DRIFT_TRIGGERING_FIELDS:
                    continue
                current_value = getattr(obj, field, None)
                if new_value != current_value:
                    drift_triggered = True
                    break
            if drift_triggered:
                obj.has_drift = True

        for k, v in changes.items():
            setattr(obj, k, v)

        # Aplicar unidad_id por separado para que null sea válido (quitar asignación)
        if unidad_id_explicitly_set:
            obj.unidad_id = unidad_id_value

        audit_changes: dict[str, Any] = {"after": data.model_dump(exclude_unset=True, mode="json")}
        if drift_triggered:
            audit_changes["drift_triggered"] = True

        audit = AuditLog(
            tenant_id=obj.tenant_id,
            user_id=user.id,
            action="tarea_practica.update",
            resource_type="tarea_practica",
            resource_id=id_,
            changes=audit_changes,
        )
        self.session.add(audit)
        await self.session.flush()
        await self.session.refresh(obj)
        return obj

    async def soft_delete(self, id_: UUID, user: User) -> TareaPractica:
        # DEFERRED: validar cross-service que no haya episodios CTR activos
        # referenciando esta tarea_practica_id. Bloqueante una vez exista
        # el mecanismo (HTTP client a ctr-service o evento sync via bus).
        # Hoy soft_delete procede sin guard — riesgo: episodios huérfanos.
        obj = await self.repo.soft_delete(id_)
        audit = AuditLog(
            tenant_id=obj.tenant_id,
            user_id=user.id,
            action="tarea_practica.delete",
            resource_type="tarea_practica",
            resource_id=id_,
            changes={"soft_delete": True},
        )
        self.session.add(audit)
        await self.session.flush()
        return obj

    async def publish(self, tarea_id: UUID, user: User) -> TareaPractica:
        obj = await self.repo.get_or_404(tarea_id)
        if obj.estado == "published":
            return obj
        if obj.estado != "draft":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"No se puede publicar una tarea en estado '{obj.estado}'; "
                    "cree una nueva versión"
                ),
            )

        obj.estado = "published"

        audit = AuditLog(
            tenant_id=obj.tenant_id,
            user_id=user.id,
            action="tarea_practica.publish",
            resource_type="tarea_practica",
            resource_id=tarea_id,
            changes={"estado": {"before": "draft", "after": "published"}},
        )
        self.session.add(audit)
        await self.session.flush()
        await self.session.refresh(obj)
        return obj

    async def archive(self, tarea_id: UUID, user: User) -> TareaPractica:
        obj = await self.repo.get_or_404(tarea_id)
        if obj.estado != "published":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"No se puede archivar una tarea en estado '{obj.estado}'; "
                    "sólo se archivan tareas publicadas"
                ),
            )

        obj.estado = "archived"

        audit = AuditLog(
            tenant_id=obj.tenant_id,
            user_id=user.id,
            action="tarea_practica.archive",
            resource_type="tarea_practica",
            resource_id=tarea_id,
            changes={"estado": {"before": "published", "after": "archived"}},
        )
        self.session.add(audit)
        await self.session.flush()
        await self.session.refresh(obj)
        return obj

    async def new_version(
        self, parent_id: UUID, patch: TareaPracticaUpdate, user: User
    ) -> TareaPractica:
        parent = await self.repo.get_or_404(parent_id)
        if parent.estado not in ("published", "archived"):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"No se puede versionar una tarea en estado '{parent.estado}'; "
                    "publique la versión draft primero"
                ),
            )

        overrides = patch.model_dump(exclude_unset=True, exclude_none=True)

        new_id = uuid4()
        # ADR-016: la nueva versión hereda template_id y has_drift del parent.
        # No "lavamos" drift creando una versión: si la v-N estaba drifteada,
        # la v-N+1 también lo está. Si el docente quiere "volver al template",
        # usa el endpoint dedicado de resync (scope futuro).

        new_tarea = await self.repo.create(
            {
                "id": new_id,
                "tenant_id": parent.tenant_id,
                "comision_id": parent.comision_id,
                "codigo": parent.codigo,
                "titulo": overrides.get("titulo", parent.titulo),
                "enunciado": overrides.get("enunciado", parent.enunciado),
                "inicial_codigo": overrides.get("inicial_codigo", parent.inicial_codigo),
                "fecha_inicio": overrides.get("fecha_inicio", parent.fecha_inicio),
                "fecha_fin": overrides.get("fecha_fin", parent.fecha_fin),
                "peso": overrides.get("peso", parent.peso),
                "rubrica": overrides.get("rubrica", parent.rubrica),
                "estado": "draft",
                "version": parent.version + 1,
                "parent_tarea_id": parent.id,
                "template_id": parent.template_id,
                "has_drift": parent.has_drift,
                "created_by": user.id,
                # ADR-041: la nueva versión hereda la asignación de Unidad del
                # parent. Si el patch sobreescribe unidad_id explícitamente,
                # se aplica en el update() posterior; aquí heredamos el parent.
                "unidad_id": parent.unidad_id,
            }
        )

        # ADR-047: clonar la composición de ejercicios del parent al new TP.
        # Las filas de `tp_ejercicios` apuntan al UUID del Ejercicio (estable),
        # solo cambian el `tarea_practica_id` y `id` propio. El Ejercicio en
        # sí NO se clona (sigue siendo el mismo). El patch del versionado NO
        # permite re-componer ejercicios — eso se hace con los endpoints de
        # composición sobre el nuevo TP en estado draft.
        from academic_service.models import TpEjercicio

        for tp_ej in parent.tp_ejercicios:
            clone = TpEjercicio(
                id=uuid4(),
                tenant_id=parent.tenant_id,
                tarea_practica_id=new_id,
                ejercicio_id=tp_ej.ejercicio_id,
                orden=tp_ej.orden,
                peso_en_tp=tp_ej.peso_en_tp,
            )
            self.session.add(clone)
        await self.session.flush()

        audit = AuditLog(
            tenant_id=parent.tenant_id,
            user_id=user.id,
            action="tarea_practica.new_version",
            resource_type="tarea_practica",
            resource_id=new_id,
            changes={
                "parent_id": str(parent.id),
                "parent_version": parent.version,
                "new_version": parent.version + 1,
                "overrides": patch.model_dump(mode="json", exclude_unset=True),
            },
        )
        self.session.add(audit)
        await self.session.flush()
        return new_tarea

    async def list_versions(self, tarea_id: UUID) -> list[TareaPractica]:
        anchor = await self.repo.get_or_404(tarea_id)

        root = anchor
        while root.parent_tarea_id is not None:
            stmt = select(TareaPractica).where(TareaPractica.id == root.parent_tarea_id)
            result = await self.session.execute(stmt)
            parent = result.scalar_one_or_none()
            if parent is None:
                break
            root = parent

        chain: list[TareaPractica] = [root]
        seen: set[UUID] = {root.id}
        frontier: list[UUID] = [root.id]
        while frontier:
            stmt = select(TareaPractica).where(
                TareaPractica.parent_tarea_id.in_(frontier),
            )
            result = await self.session.execute(stmt)
            children = list(result.scalars().all())
            new_frontier: list[UUID] = []
            for child in children:
                if child.id in seen:
                    continue
                seen.add(child.id)
                chain.append(child)
                new_frontier.append(child.id)
            frontier = new_frontier

        chain.sort(key=lambda t: t.version)
        return chain

    async def get(self, id_: UUID) -> TareaPractica:
        return await self.repo.get_or_404(id_)

    async def list(
        self,
        comision_id: UUID | None = None,
        estado: str | None = None,
        unidad_id: UUID | None = None,
        limit: int = 50,
        cursor: UUID | None = None,
    ) -> list[TareaPractica]:
        filters: dict[str, Any] = {}
        if comision_id:
            filters["comision_id"] = comision_id
        if estado:
            filters["estado"] = estado
        if unidad_id:
            # Fix QA A13: el filtro unidad_id no se propagaba al WHERE.
            filters["unidad_id"] = unidad_id
        return await self.repo.list(limit=limit, cursor=cursor, filters=filters)
