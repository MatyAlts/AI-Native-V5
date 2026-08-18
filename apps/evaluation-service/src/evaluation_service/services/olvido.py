"""Lo que el derecho al olvido tiene que borrar de la corrección asistida.

Es el adaptador que `platform_ops.privacy.anonymize_student` consume para la
parte de este servicio. Vive acá y no en el paquete porque toca tablas que son
de acá.

**La asimetría es deliberada**: el artefacto y el PDF se BORRAN; la fila de la
corrección se rota. El artefacto es el código que escribió esa persona y el
PDF lleva su nombre y la devolución sobre su trabajo — son el dato personal,
no una referencia a él, y rotar un identificador los dejaría igual de legibles.
Que hubo una corrección es trazabilidad del piloto; quién fue, no.
"""

from __future__ import annotations

from uuid import UUID

import structlog
from sqlalchemy import and_, delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from evaluation_service.models.correcciones_ia import CorreccionIA
from evaluation_service.models.entregas import Entrega, EntregaArtefacto
from evaluation_service.services.correccion_pdf import borrar as borrar_pdf

log = structlog.get_logger()


class OlvidoCorreccionAdapter:
    """Las cinco operaciones que `anonymize_student` necesita de este servicio."""

    def __init__(self, db: AsyncSession, tenant_id: UUID) -> None:
        self._db = db
        self._tenant_id = tenant_id

    async def list_correcciones_by_student(self, pseudonym: UUID) -> list[dict]:
        """Las correcciones del alumno, con su `pdf_storage_key`.

        Se llega por `entregas` porque `correcciones_ia` no lleva el
        pseudónimo: la corrección es de una ENTREGA, y la entrega es de un
        alumno.
        """
        stmt = (
            select(CorreccionIA.id, CorreccionIA.pdf_storage_key)
            .join(Entrega, Entrega.id == CorreccionIA.entrega_id)
            .where(
                and_(
                    CorreccionIA.tenant_id == self._tenant_id,
                    Entrega.student_pseudonym == pseudonym,
                )
            )
        )
        return [{"id": r[0], "pdf_storage_key": r[1]} for r in (await self._db.execute(stmt)).all()]

    async def delete_pdf(self, storage_key: str) -> bool:
        return await borrar_pdf(storage_key)

    async def delete_artefactos_by_student(self, pseudonym: UUID) -> int:
        """Borra el código entregado.

        `DELETE` y no rotación: el artefacto ES el dato. Y se borra la fila
        entera en vez de vaciar la columna `codigo` para que no quede un
        registro que diga "acá hubo código de alguien" con el `sha256` al
        lado — el hash de un archivo chico es reversible por fuerza bruta si
        alguien tiene el enunciado.
        """
        entregas = select(Entrega.id).where(
            and_(
                Entrega.tenant_id == self._tenant_id,
                Entrega.student_pseudonym == pseudonym,
            )
        )
        res = await self._db.execute(
            delete(EntregaArtefacto).where(EntregaArtefacto.entrega_id.in_(entregas))
        )
        n = getattr(res, "rowcount", 0) or 0
        # Y el hash del conjunto, que también describe lo entregado.
        await self._db.execute(
            update(Entrega)
            .where(
                and_(
                    Entrega.tenant_id == self._tenant_id,
                    Entrega.student_pseudonym == pseudonym,
                )
            )
            .values(artefacto_sha256=None)
        )
        return int(n)

    async def update_correcciones_pseudonym(self, original: UUID, new: UUID) -> int:
        """Rota el pseudónimo de las ENTREGAS del alumno.

        `correcciones_ia` no lleva el pseudónimo, así que lo que se rota es la
        entrega — que es de donde cuelga. Rotarla desvincula de una vez la
        entrega, sus artefactos (ya borrados) y sus correcciones.
        """
        res = await self._db.execute(
            update(Entrega)
            .where(
                and_(
                    Entrega.tenant_id == self._tenant_id,
                    Entrega.student_pseudonym == original,
                )
            )
            .values(student_pseudonym=new)
        )
        return int(getattr(res, "rowcount", 0) or 0)

    async def borrar_en_activeia(self, pseudonym: UUID) -> bool:
        """Pide el borrado del alumno del lado de Active-IA.

        **Todavía no existe el endpoint** (pedido 3.6 de
        `activeia-cambios-pedidos.md`). Levanta `NotImplementedError` a
        propósito para que el informe quede en `borrado_externo_ok=None`, que
        significa "no se intentó" — y NO `False`, que significaría "se pidió y
        dijo que no". De esa distinción depende saber si queda una copia
        afuera.
        """
        raise NotImplementedError(
            "Active-IA no expone borrado por alumno todavía (pedido 3.6). "
            "El código subido sigue allá: hay que borrarlo desde su panel."
        )
