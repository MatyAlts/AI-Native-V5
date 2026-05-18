"""Service de Inscripcion (estudiante-comision).

ADR-029 (B.1): destraba el alta masiva via CSV bulk-import. La identidad real
del estudiante vive en Keycloak; aca solo registramos el pseudonimo + comision
+ rol/estado/fecha_inscripcion. El bulk-import (`bulk_import.BulkImportService`)
delega al `create()` de este service por cada fila valida.

Multi-tenancy: el `tenant_id` se toma del `User.tenant_id` (header autoritativo
del api-gateway). RLS de Postgres garantiza el aislamiento — este service NO
filtra por tenant en queries (lo hace SET LOCAL app.current_tenant en el driver).

Idempotencia: el constraint `uq_inscripcion_student(tenant_id, comision_id,
student_pseudonym)` previene duplicados a nivel DB. El service NO hace
upsert — la segunda inscripcion del mismo estudiante en la misma comision
falla con 409. Esto es deliberado: re-inscripciones legitimas usan
rol="reinscripcion" y van en una fila separada, pero distinto periodo o
distinto estado.
"""

from __future__ import annotations

from uuid import UUID, uuid4

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from academic_service.auth.dependencies import User
from academic_service.models import AuditLog, Inscripcion
from academic_service.repositories import ComisionRepository, InscripcionRepository
from academic_service.schemas.inscripcion import InscripcionCreate


class InscripcionService:
    """Crea inscripciones de estudiantes en comisiones.

    Hoy expone solo `create()` para soportar bulk-import. CRUD individual
    (read/update/delete) es agenda futura — el caso central del piloto es
    cargar masivamente al inicio del cuatrimestre.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = InscripcionRepository(session)
        self.comisiones = ComisionRepository(session)

    async def create(self, data: InscripcionCreate, user: User) -> Inscripcion:
        # Defense in depth: la comision debe existir en el tenant del caller.
        # `bulk_import._check_fk_existence` ya valida lo mismo, pero el service
        # se llama tambien desde tests o futuros endpoints REST sin pasar por
        # el bulk — replicar el chequeo evita inscripciones huerfanas.
        await self.comisiones.get_or_404(data.comision_id)

        new_id = uuid4()
        try:
            inscripcion = await self.repo.create(
                {
                    "id": new_id,
                    "tenant_id": user.tenant_id,
                    "comision_id": data.comision_id,
                    "student_pseudonym": data.student_pseudonym,
                    "rol": data.rol,
                    "estado": data.estado,
                    "fecha_inscripcion": data.fecha_inscripcion,
                    "nota_final": data.nota_final,
                    "fecha_cierre": data.fecha_cierre,
                }
            )
        except IntegrityError as exc:
            await self.session.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Inscripcion duplicada: estudiante {data.student_pseudonym} "
                    f"ya esta inscripto en la comision {data.comision_id}"
                ),
            ) from exc

        audit = AuditLog(
            tenant_id=user.tenant_id,
            user_id=user.id,
            action="inscripcion.create",
            resource_type="inscripcion",
            resource_id=new_id,
            changes={"after": data.model_dump(mode="json")},
        )
        self.session.add(audit)
        await self.session.flush()
        return inscripcion

    async def get(self, id_: UUID) -> Inscripcion:
        return await self.repo.get_or_404(id_)

    async def list(
        self,
        limit: int = 50,
        cursor: UUID | None = None,
    ) -> list[Inscripcion]:
        return await self.repo.list(limit=limit, cursor=cursor)
