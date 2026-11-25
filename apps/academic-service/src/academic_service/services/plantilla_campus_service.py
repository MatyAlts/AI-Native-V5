"""Plantillas de campus por materia (HU-036).

El docente guarda el campus de su comision como plantilla de la materia y otro
docente la aplica a su comision en un clic. Despues retoca fechas y textos.

Contenido (`PlantillaCampus.contenido`, version `campus_v1`)::

    {
      "version": "campus_v1",
      "bienvenida_html": "<h1>...</h1>" | None,
      "unidades": [
        {"nombre", "descripcion", "orden", "introduccion_html",
         "tps": [ficha, ...]},
        ...
      ],
    }

Una ficha de TP lleva solo los campos de `CAMPOS_FICHA`: nunca fechas, ni
estado, ni ids de la comision de origen. `ejercicio_ids` va en el orden de
`tp_ejercicios` y `ejercicio_pesos` en paralelo (el `peso_en_tp` de cada fila).

Reglas al aplicar:
- Misma materia o 422.
- No pisa: una unidad cuyo nombre ya existe en la comision destino se omite
  (con sus TPs) y se informa; la bienvenida se escribe solo si la comision no
  tenia una (vacia o solo espacios cuenta como "no tenia").
- Los TPs nacen en `draft`, version 1, sin fechas: ningun alumno los ve hasta
  que el docente los publica. Un TP cuyo `codigo` ya existe en la comision
  destino se saltea (el UNIQUE `(tenant, comision, codigo, version)` lo
  rechazaria).
- Todo en la transaccion del request: si algo falla no queda nada a medias.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from academic_service.auth.dependencies import User
from academic_service.models import (
    AuditLog,
    PlantillaCampus,
    TareaPractica,
    TpEjercicio,
    Unidad,
)
from academic_service.repositories import ComisionRepository
from academic_service.services.comision_service import assert_comision_member

VERSION_CONTENIDO = "campus_v1"

# Lo unico de un TP que viaja en la plantilla. Fechas, estado, version e ids
# de origen quedan afuera a proposito (N01).
CAMPOS_FICHA: tuple[str, ...] = (
    "codigo",
    "titulo",
    "enunciado",
    "inicial_codigo",
    "peso",
    "rubrica",
    "language",
    "permite_pausa",
    "test_cases",
    "template_id",
    "ejercicio_ids",
    "ejercicio_pesos",
)


# ── Funciones puras ────────────────────────────────────────────────────


def armar_contenido(
    bienvenida_html: str | None,
    unidades: Iterable[Any],
    tps_por_unidad: Mapping[Any, Sequence[Mapping[str, Any]]],
) -> dict[str, Any]:
    """Arma el `contenido` JSON de la plantilla (sin fechas ni ids de origen)."""
    salida: list[dict[str, Any]] = []
    for u in sorted(unidades, key=lambda x: x.orden):
        fichas = [
            {k: ficha[k] for k in CAMPOS_FICHA if k in ficha}
            for ficha in tps_por_unidad.get(u.id, [])
        ]
        salida.append(
            {
                "nombre": u.nombre,
                "descripcion": u.descripcion,
                "orden": u.orden,
                "introduccion_html": u.introduccion_html,
                "tps": fichas,
            }
        )
    return {
        "version": VERSION_CONTENIDO,
        "bienvenida_html": bienvenida_html,
        "unidades": salida,
    }


@dataclass(frozen=True)
class PlanAplicacion:
    unidades_a_crear: list[dict[str, Any]] = field(default_factory=list)
    unidades_omitidas: list[str] = field(default_factory=list)
    bienvenida: str | None = None


def planificar_aplicacion(
    contenido: Mapping[str, Any],
    nombres_existentes: set[str],
    bienvenida_actual: str | None,
) -> PlanAplicacion:
    """Que se crea y que se deja como esta. No pisa nada existente (N02)."""
    a_crear: list[dict[str, Any]] = []
    omitidas: list[str] = []
    for u in contenido.get("unidades", []):
        if u["nombre"] in nombres_existentes:
            omitidas.append(u["nombre"])
        else:
            a_crear.append(u)
    bienvenida: str | None = None
    if bienvenida_actual is None or bienvenida_actual.strip() == "":
        propuesta = contenido.get("bienvenida_html")
        if propuesta and propuesta.strip():
            bienvenida = propuesta
    return PlanAplicacion(
        unidades_a_crear=a_crear, unidades_omitidas=omitidas, bienvenida=bienvenida
    )


def validar_misma_materia(materia_plantilla: UUID, materia_comision: UUID) -> None:
    """422 si la plantilla es de otra materia que la comision (N03)."""
    if materia_plantilla != materia_comision:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="La plantilla es de otra materia que la comision",
        )


def _uuid_o_none(v: Any) -> UUID | None:
    if v is None or v == "":
        return None
    return v if isinstance(v, UUID) else UUID(str(v))


def datos_tp_aplicado(
    ficha: Mapping[str, Any],
    *,
    comision_id: UUID,
    unidad_id: UUID,
    created_by: UUID,
) -> dict[str, Any]:
    """Columnas del TP que se crea al aplicar: draft, v1, sin fechas (N05)."""
    return {
        "id": uuid4(),
        "comision_id": comision_id,
        "unidad_id": unidad_id,
        "codigo": ficha["codigo"],
        "titulo": ficha["titulo"],
        "enunciado": ficha["enunciado"],
        "inicial_codigo": ficha.get("inicial_codigo"),
        "fecha_inicio": None,
        "fecha_fin": None,
        "peso": Decimal(str(ficha.get("peso", "1.0"))),
        "rubrica": ficha.get("rubrica"),
        "language": ficha.get("language") or "python",
        "permite_pausa": bool(ficha.get("permite_pausa", True)),
        "test_cases": list(ficha.get("test_cases") or []),
        "estado": "draft",
        "version": 1,
        "parent_tarea_id": None,
        "template_id": _uuid_o_none(ficha.get("template_id")),
        "has_drift": False,
        "created_via_ai": False,
        "created_by": created_by,
    }


def _ficha_de_tp(tp: TareaPractica, filas: Sequence[TpEjercicio]) -> dict[str, Any]:
    return {
        "codigo": tp.codigo,
        "titulo": tp.titulo,
        "enunciado": tp.enunciado,
        "inicial_codigo": tp.inicial_codigo,
        "peso": str(tp.peso),
        "rubrica": tp.rubrica,
        "language": tp.language,
        "permite_pausa": tp.permite_pausa,
        "test_cases": list(tp.test_cases or []),
        "template_id": str(tp.template_id) if tp.template_id else None,
        "ejercicio_ids": [str(f.ejercicio_id) for f in filas],
        "ejercicio_pesos": [str(f.peso_en_tp) for f in filas],
    }


def _peso_por_defecto(n: int) -> Decimal:
    return (Decimal(1) / Decimal(n)).quantize(Decimal("0.0001")) if n else Decimal(1)


# ── Servicio ───────────────────────────────────────────────────────────


class PlantillaCampusService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.comisiones = ComisionRepository(session)

    async def guardar(self, comision_id: UUID, nombre: str, user: User) -> PlantillaCampus:
        """Guarda el campus de la comision como plantilla de su materia."""
        await assert_comision_member(self.session, user, comision_id)
        comision = await self.comisiones.get_or_404(comision_id)

        unidades = list(
            (
                await self.session.execute(
                    select(Unidad)
                    .where(Unidad.comision_id == comision_id, Unidad.deleted_at.is_(None))
                    .order_by(Unidad.orden)
                )
            )
            .scalars()
            .all()
        )
        tps_por_unidad: dict[UUID, list[dict[str, Any]]] = {u.id: [] for u in unidades}
        if unidades:
            tps = (
                (
                    await self.session.execute(
                        select(TareaPractica)
                        .where(
                            TareaPractica.comision_id == comision_id,
                            TareaPractica.unidad_id.in_(list(tps_por_unidad)),
                            TareaPractica.estado != "archived",
                            TareaPractica.deleted_at.is_(None),
                        )
                        .order_by(TareaPractica.codigo, TareaPractica.version)
                    )
                )
                .scalars()
                .all()
            )
            # Version vigente: de cada cadena (mismo codigo) solo la ultima.
            vigentes: dict[str, TareaPractica] = {}
            for tp in tps:
                actual = vigentes.get(tp.codigo)
                if actual is None or tp.version > actual.version:
                    vigentes[tp.codigo] = tp
            filas_por_tp: dict[UUID, list[TpEjercicio]] = {tp.id: [] for tp in vigentes.values()}
            if filas_por_tp:
                filas = (
                    (
                        await self.session.execute(
                            select(TpEjercicio)
                            .where(TpEjercicio.tarea_practica_id.in_(list(filas_por_tp)))
                            .order_by(TpEjercicio.tarea_practica_id, TpEjercicio.orden)
                        )
                    )
                    .scalars()
                    .all()
                )
                for f in filas:
                    filas_por_tp[f.tarea_practica_id].append(f)
            for tp in sorted(vigentes.values(), key=lambda t: t.codigo):
                if tp.unidad_id in tps_por_unidad:
                    tps_por_unidad[tp.unidad_id].append(_ficha_de_tp(tp, filas_por_tp[tp.id]))

        contenido = armar_contenido(comision.bienvenida_html, unidades, tps_por_unidad)
        plantilla = PlantillaCampus(
            id=uuid4(),
            tenant_id=user.tenant_id,
            materia_id=comision.materia_id,
            nombre=nombre,
            contenido=contenido,
            created_by=user.id,
        )
        self.session.add(plantilla)
        self.session.add(
            AuditLog(
                tenant_id=user.tenant_id,
                user_id=user.id,
                action="plantilla_campus.create",
                resource_type="plantilla_campus",
                resource_id=plantilla.id,
                changes={
                    "comision_id": str(comision_id),
                    "materia_id": str(comision.materia_id),
                    "nombre": nombre,
                    "unidades": len(contenido["unidades"]),
                    "tps": sum(len(u["tps"]) for u in contenido["unidades"]),
                },
            )
        )
        await self.session.flush()
        await self.session.refresh(plantilla)
        return plantilla

    async def listar(self, comision_id: UUID, user: User) -> list[PlantillaCampus]:
        """Plantillas de la materia de la comision, mas nuevas primero."""
        await assert_comision_member(self.session, user, comision_id)
        comision = await self.comisiones.get_or_404(comision_id)
        stmt = (
            select(PlantillaCampus)
            .where(
                PlantillaCampus.materia_id == comision.materia_id,
                PlantillaCampus.deleted_at.is_(None),
            )
            .order_by(PlantillaCampus.created_at.desc())
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def aplicar(self, plantilla_id: UUID, comision_id: UUID, user: User) -> dict[str, Any]:
        """Aplica la plantilla a la comision sin pisar lo existente."""
        await assert_comision_member(self.session, user, comision_id)
        plantilla = await self.session.get(PlantillaCampus, plantilla_id)
        if plantilla is None or plantilla.deleted_at is not None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Plantilla {plantilla_id} no encontrada",
            )
        comision = await self.comisiones.get_or_404(comision_id)
        validar_misma_materia(plantilla.materia_id, comision.materia_id)

        # Nombres y ordenes ocupados incluyen las unidades borradas: los UNIQUE
        # `uq_unidad_nombre` y `uq_unidad_orden` no miran `deleted_at`.
        filas = (
            await self.session.execute(
                select(Unidad.nombre, Unidad.orden).where(Unidad.comision_id == comision_id)
            )
        ).all()
        nombres_existentes = {r[0] for r in filas}
        siguiente_orden = max((r[1] for r in filas), default=-1) + 1

        plan = planificar_aplicacion(
            plantilla.contenido, nombres_existentes, comision.bienvenida_html
        )

        codigos_existentes = set(
            (
                await self.session.execute(
                    select(func.distinct(TareaPractica.codigo)).where(
                        TareaPractica.comision_id == comision_id
                    )
                )
            )
            .scalars()
            .all()
        )

        tps_creados = 0
        tps_omitidos: list[str] = []
        for i, u in enumerate(plan.unidades_a_crear):
            unidad = Unidad(
                id=uuid4(),
                tenant_id=user.tenant_id,
                comision_id=comision_id,
                nombre=u["nombre"],
                descripcion=u.get("descripcion"),
                orden=siguiente_orden + i,
                introduccion_html=u.get("introduccion_html"),
                fecha_apertura=None,
                created_by=user.id,
            )
            self.session.add(unidad)
            for ficha in u.get("tps", []):
                if ficha["codigo"] in codigos_existentes:
                    tps_omitidos.append(ficha["codigo"])
                    continue
                codigos_existentes.add(ficha["codigo"])
                datos = datos_tp_aplicado(
                    ficha, comision_id=comision_id, unidad_id=unidad.id, created_by=user.id
                )
                self.session.add(TareaPractica(tenant_id=user.tenant_id, **datos))
                ejercicios = list(ficha.get("ejercicio_ids") or [])
                pesos = list(ficha.get("ejercicio_pesos") or [])
                for orden, ej_id in enumerate(ejercicios, start=1):
                    peso = (
                        Decimal(str(pesos[orden - 1]))
                        if len(pesos) == len(ejercicios)
                        else _peso_por_defecto(len(ejercicios))
                    )
                    self.session.add(
                        TpEjercicio(
                            id=uuid4(),
                            tenant_id=user.tenant_id,
                            tarea_practica_id=datos["id"],
                            ejercicio_id=UUID(str(ej_id)),
                            orden=orden,
                            peso_en_tp=peso,
                        )
                    )
                tps_creados += 1

        if plan.bienvenida is not None:
            comision.bienvenida_html = plan.bienvenida

        resultado = {
            "unidades_creadas": len(plan.unidades_a_crear),
            "unidades_omitidas": plan.unidades_omitidas,
            "tps_creados": tps_creados,
            "bienvenida_aplicada": plan.bienvenida is not None,
            "tps_omitidos": tps_omitidos,
        }
        self.session.add(
            AuditLog(
                tenant_id=user.tenant_id,
                user_id=user.id,
                action="plantilla_campus.aplicar",
                resource_type="plantilla_campus",
                resource_id=plantilla.id,
                changes={
                    **resultado,
                    "comision_id": str(comision_id),
                },
            )
        )
        await self.session.flush()
        return resultado
