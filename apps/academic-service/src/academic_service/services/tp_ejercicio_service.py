"""Service de composición TP ↔ Ejercicio (ADR-047).

Gestiona la tabla intermedia `tp_ejercicios` que asocia ejercicios del
banco standalone con TPs específicas.

Reglas operativas:
- Solo se puede agregar / quitar / reordenar ejercicios sobre TPs en
  estado `draft`. Una vez publicada, los cambios requieren crear una
  nueva versión del TP (la composición se clona al nuevo TP, ver
  `TareaPracticaService.new_version`).
- El `orden` y `peso_en_tp` son únicos dentro de la TP (constraints en
  DB).
- Un mismo `ejercicio_id` no puede aparecer dos veces en la misma TP
  (UNIQUE constraint en DB).
- Todos los ejercicios de una TP comparten `language`, y coincide con el
  de la TP. Se bloquea al agregar (acá) y se re-verifica al publicar. El
  editor del alumno carga un único runtime por episodio: una TP mixta no
  es "inconsistente", es irresoluble.
- La suma de `peso_en_tp` NO se valida, ni acá ni al publicar. Medición
  sobre la base del piloto (2026-07-23): las 169 asociaciones tienen peso
  1.0000, ninguna calificación consume el campo, y exigir suma 1.0 habría
  impedido republicar 25 de las 27 TPs publicadas. Ver el docstring de
  `TpEjerciciosValidator`.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from academic_service.auth.dependencies import User
from academic_service.models import AuditLog, Ejercicio, TareaPractica, TpEjercicio
from academic_service.repositories import (
    EjercicioRepository,
    TareaPracticaRepository,
    TpEjercicioRepository,
)


class TpEjercicioService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.tp_repo = TareaPracticaRepository(session)
        self.ejercicio_repo = EjercicioRepository(session)
        self.pair_repo = TpEjercicioRepository(session)

    async def _assert_tp_draft(self, tarea_practica_id: UUID) -> TareaPractica:
        """Carga la TP y valida que esté en draft (única ventana mutable).

        Devuelve la TP para que el caller no tenga que volver a pedirla — la
        validación de lenguaje necesita su `language`.
        """
        tp = await self.tp_repo.get_or_404(tarea_practica_id)
        if tp.estado != "draft":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"No se puede modificar la composición de ejercicios de una "
                    f"TP en estado '{tp.estado}'; cree una nueva versión"
                ),
            )
        return tp

    async def list_by_tp(self, tarea_practica_id: UUID) -> list[tuple[TpEjercicio, Ejercicio]]:
        """Lista las asociaciones de una TP con su Ejercicio embebido.

        Devuelve tuplas ordenadas por `orden`. NO valida estado de la TP
        (lectura libre en cualquier estado).
        """
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload

        stmt = (
            select(TpEjercicio)
            .where(TpEjercicio.tarea_practica_id == tarea_practica_id)
            .options(selectinload(TpEjercicio.ejercicio))
            .order_by(TpEjercicio.orden)
        )
        result = await self.session.execute(stmt)
        pairs = list(result.scalars().all())
        return [(p, p.ejercicio) for p in pairs]

    async def add_ejercicio(
        self,
        tarea_practica_id: UUID,
        ejercicio_id: UUID,
        orden: int,
        peso_en_tp: Decimal,
        user: User,
    ) -> TpEjercicio:
        tp = await self._assert_tp_draft(tarea_practica_id)

        # Validar que el Ejercicio existe (y no esté soft-deleted). El objeto se
        # captura porque su `language` alimenta la validación de abajo — antes se
        # descartaba y esto era solo un chequeo de existencia.
        ejercicio = await self.ejercicio_repo.get_or_404(ejercicio_id)

        if ejercicio.language != tp.language:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    f"El ejercicio es de '{ejercicio.language}' pero la TP es de "
                    f"'{tp.language}'. Una TP admite un solo lenguaje: el editor "
                    f"del alumno carga un único entorno de ejecución por episodio."
                ),
            )

        pair = await self.pair_repo.create(
            tenant_id=user.tenant_id,
            tarea_practica_id=tarea_practica_id,
            ejercicio_id=ejercicio_id,
            orden=orden,
            peso_en_tp=peso_en_tp,
        )

        audit = AuditLog(
            tenant_id=user.tenant_id,
            user_id=user.id,
            action="tp_ejercicio.add",
            resource_type="tp_ejercicio",
            resource_id=pair.id,
            changes={
                "tarea_practica_id": str(tarea_practica_id),
                "ejercicio_id": str(ejercicio_id),
                "orden": orden,
                "peso_en_tp": str(peso_en_tp),
            },
        )
        self.session.add(audit)
        await self.session.flush()
        return pair

    async def update_pair(
        self,
        tarea_practica_id: UUID,
        ejercicio_id: UUID,
        orden: int | None,
        peso_en_tp: Decimal | None,
        user: User,
    ) -> TpEjercicio:
        await self._assert_tp_draft(tarea_practica_id)

        pair = await self.pair_repo.get_pair(tarea_practica_id, ejercicio_id)
        if pair is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=(f"Ejercicio {ejercicio_id} no está asociado a la TP {tarea_practica_id}"),
            )

        changes: dict[str, str | int] = {}
        if orden is not None:
            pair.orden = orden
            changes["orden"] = orden
        if peso_en_tp is not None:
            pair.peso_en_tp = peso_en_tp
            changes["peso_en_tp"] = str(peso_en_tp)

        await self.session.flush()
        await self.session.refresh(pair)

        audit = AuditLog(
            tenant_id=user.tenant_id,
            user_id=user.id,
            action="tp_ejercicio.update",
            resource_type="tp_ejercicio",
            resource_id=pair.id,
            changes=changes,
        )
        self.session.add(audit)
        await self.session.flush()
        return pair

    async def remove_ejercicio(
        self,
        tarea_practica_id: UUID,
        ejercicio_id: UUID,
        user: User,
    ) -> None:
        await self._assert_tp_draft(tarea_practica_id)

        pair = await self.pair_repo.get_pair(tarea_practica_id, ejercicio_id)
        if pair is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=(f"Ejercicio {ejercicio_id} no está asociado a la TP {tarea_practica_id}"),
            )

        pair_id = pair.id
        await self.pair_repo.delete(pair)

        audit = AuditLog(
            tenant_id=user.tenant_id,
            user_id=user.id,
            action="tp_ejercicio.remove",
            resource_type="tp_ejercicio",
            resource_id=pair_id,
            changes={
                "tarea_practica_id": str(tarea_practica_id),
                "ejercicio_id": str(ejercicio_id),
            },
        )
        self.session.add(audit)
        await self.session.flush()
