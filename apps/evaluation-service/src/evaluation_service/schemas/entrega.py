"""Schemas Pydantic para Entrega y Calificacion."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class EjercicioEstadoSchema(BaseModel):
    """Estado de un ejercicio dentro de una Entrega.

    ADR-047: `ejercicio_id` es la identidad permanente del Ejercicio
    reusable del banco standalone. `orden` es la posición denormalizada
    al momento de la entrega (snapshot inmutable). Si el ejercicio
    cambia de orden en una nueva versión de TP, este estado sigue
    apuntando al ejercicio correcto por UUID.

    Entregas legacy creadas antes del refactor pueden tener `ejercicio_id=None`
    — el match cae al `orden` como fallback.
    """

    ejercicio_id: UUID | None = None
    orden: int
    episode_id: UUID | None = None
    completado: bool = False
    completed_at: datetime | None = None


class EntregaCreate(BaseModel):
    """Request de creacion de Entrega (draft).

    Idempotente: si ya existe una entrega para este (tarea_practica_id,
    student_pseudonym), el endpoint devuelve la existente.
    """

    tarea_practica_id: UUID
    comision_id: UUID


class ArtefactoItem(BaseModel):
    """El código de UN ejercicio, tal como lo manda el cliente en el submit.

    Las cotas de `orden` y `language` no son decorativas: sin ellas la
    violación salta recién en el flush, como `DataError` o
    `StringDataRightTruncation` sin capturar, o sea un 500 con stack trace
    sobre un campo que manda el cliente. `orden` sin techo además desborda el
    int32 de la columna. El resto del endpoint responde 422 a un body mal
    armado; esto también.

    `language` es un `Literal` y no un string con largo acotado porque el
    Epic 3 lo va a usar para elegir el runtime del sandbox: un valor
    desconocido ahí no es un rótulo feo, es ejecutar el código equivocado.
    """

    # 1000 ejercicios en una TP es absurdo y entra holgado en el int32.
    orden: int = Field(ge=1, le=1000)
    ejercicio_id: UUID | None = None
    episode_id: UUID | None = None
    codigo: str
    language: Literal["python", "java"] = "python"


class EntregaSubmitBody(BaseModel):
    """Body del POST /entregas/{id}/submit.

    Tiene que traer el código de cada ejercicio que la TP declara. El submit
    sin body es un cliente sin actualizar y se rechaza con 422: aceptarlo
    dejaría entregas `submitted` sin saber qué se entregó, que es
    exactamente lo que este cambio viene a cerrar.

    Una TP monolítica (sin `tp_ejercicios`) no tiene lista esperada contra la
    cual exigir, así que ahí el body vacío pasa.
    """

    artefactos: list[ArtefactoItem] = Field(default_factory=list)


class ArtefactoOut(BaseModel):
    """Un artefacto persistido, para la descarga del docente."""

    model_config = ConfigDict(from_attributes=True)

    orden: int
    ejercicio_id: UUID | None = None
    episode_id: UUID | None = None
    codigo: str
    language: str
    sha256: str
    created_at: datetime


class EntregaArtefactoOut(BaseModel):
    """Lo que el alumno entregó, entero."""

    entrega_id: UUID
    tarea_practica_id: UUID
    student_pseudonym: UUID
    submitted_at: datetime | None = None
    artefacto_sha256: str | None = None
    legacy: bool = False
    artefactos: list[ArtefactoOut] = Field(default_factory=list)


class EntregaOut(BaseModel):
    """Respuesta de Entrega."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    tarea_practica_id: UUID
    student_pseudonym: UUID
    comision_id: UUID
    estado: Literal["draft", "submitted", "graded", "returned"]
    ejercicio_estados: list[dict[str, Any]] = Field(default_factory=list)
    submitted_at: datetime | None = None
    artefacto_sha256: str | None = None
    legacy: bool = False
    created_at: datetime
    deleted_at: datetime | None = None


class CriterioCalificacion(BaseModel):
    criterio: str
    puntaje: Decimal
    max_puntaje: Decimal
    comentario: str | None = None


class MarkEjercicioBody(BaseModel):
    """Body del PATCH /entregas/{id}/ejercicio/{orden} (ADR-047).

    `ejercicio_id` es opcional para compat con frontends pre-refactor —
    si viene, se persiste en el dict de `ejercicio_estados` y el match
    al ejercicio existente lo prefiere por sobre el `orden` (más robusto
    ante reordenamientos de TP).
    """

    completado: bool = True
    episode_id: UUID | None = None
    ejercicio_id: UUID | None = None


class CalificacionCreate(BaseModel):
    nota_final: Decimal = Field(ge=0, le=10)
    feedback_general: str | None = None
    detalle_criterios: list[CriterioCalificacion] = Field(default_factory=list)


class CalificacionUpdate(BaseModel):
    """Body del PATCH /entregas/{id}/calificacion (NB-4: re-calificar).

    Update parcial: solo los campos presentes en el request se aplican
    (semantica PATCH via `model_fields_set` / `exclude_unset`). Permite al
    docente corregir una nota ya puesta actualizando la fila existente
    in-place, sin violar el `UNIQUE(entrega_id)` (no inserta una segunda
    calificacion). Al menos un campo debe venir.

    `nota_final` es opcional (para poder tocar solo el feedback), pero si
    viene NO puede ser null: la columna es NOT NULL.
    """

    nota_final: Decimal | None = Field(default=None, ge=0, le=10)
    feedback_general: str | None = None
    detalle_criterios: list[CriterioCalificacion] | None = None


class CalificacionOut(BaseModel):
    """Response model de Calificacion.

    `nota_final` se serializa como `float` (no `Decimal`) para evitar
    el wire-format `"8.50"` (string) que los frontends tipan como `number`
    y rompe con `.toFixed()`. La columna SQLAlchemy sigue siendo `Numeric(5,2)`
    — la conversión es solo en serialización. Para nota académica 0-10 con
    un decimal de precisión, `float` es adecuado y no introduce error.
    Backlog QA 2026-05-07.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    entrega_id: UUID
    graded_by: UUID
    nota_final: float
    feedback_general: str | None = None
    detalle_criterios: list[dict[str, Any]] = Field(default_factory=list)
    graded_at: datetime
    updated_at: datetime | None = None
    created_at: datetime

    @field_validator("nota_final", mode="before")
    @classmethod
    def _decimal_to_float(cls, v: object) -> object:
        """Castea Decimal -> float al construir desde el ORM.

        Pydantic acepta Decimal en `float` field, pero el cast explícito
        garantiza wire-format `8.5` (no `"8.50"`) sin depender del
        comportamiento implícito del serializer.
        """
        if isinstance(v, Decimal):
            return float(v)
        return v


class EntregaListMeta(BaseModel):
    """Metadata de paginacion para `GET /api/v1/entregas`.

    Cursor-based: `cursor_next` es el `id` (UUID) de la ultima entrega del
    batch actual; pasarlo como `?cursor=<uuid>&limit=<n>` en la siguiente
    llamada para continuar. `null` cuando no hay mas paginas.
    """

    cursor_next: str | None = None
    total: int | None = None
    limit: int


class EntregaListResponse(BaseModel):
    """Envelope de respuesta paginada para `GET /api/v1/entregas`.

    BC-incompatible vs v1.0 (lista plana). Frontends consumers tienen que
    leer `body.data` en vez de iterar el body directo.
    """

    data: list[EntregaOut]
    meta: EntregaListMeta
