"""Schemas de `pedidos_ayuda`: el alumno le pide ayuda a un docente de su comision.

El cliente NO manda la comision (la deriva el servidor de la TP), ni el estado
(nace `pendiente`), ni la hora. `extra="forbid"` hace que mandarlos sea un 422
y no un campo ignorado en silencio.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

Categoria = Literal["no_puedo_avanzar", "error_plataforma", "duda_consigna", "otro"]
Estado = Literal["pendiente", "resuelto"]
Pantalla = Literal["episodio", "episodio_error", "lista_ejercicios"]


class PedidoAyudaContexto(BaseModel):
    """Diagnostico minimo, con lista blanca.

    Nada de codigo del alumno, conversacion con el tutor ni URLs completas: el
    codigo y la conversacion ya estan en el episodio y el docente llega a ellos
    por el `episode_id`.
    """

    model_config = ConfigDict(extra="forbid")

    pantalla: Pantalla | None = None
    error_visible: str | None = Field(default=None, max_length=300)
    user_agent: str | None = Field(default=None, max_length=300)


class PedidoAyudaCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tarea_practica_id: UUID
    categoria: Categoria
    mensaje: str | None = Field(default=None, max_length=1000)
    ejercicio_orden: int | None = Field(default=None, ge=1, le=1000)
    # Sin validar contra el CTR: en "Episode no encontrado" ni existe, y ese es
    # justamente el dato para diagnosticar.
    episode_id: UUID | None = None
    entrega_id: UUID | None = None
    contexto: PedidoAyudaContexto = Field(default_factory=PedidoAyudaContexto)

    @field_validator("mensaje")
    @classmethod
    def _mensaje_en_blanco_es_ninguno(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        return v or None


class PedidoAyudaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    comision_id: UUID
    student_pseudonym: UUID
    tarea_practica_id: UUID
    entrega_id: UUID | None = None
    ejercicio_orden: int | None = None
    episode_id: UUID | None = None
    categoria: str
    mensaje: str | None = None
    contexto: dict[str, Any] = Field(default_factory=dict)
    estado: str
    resuelto_por: UUID | None = None
    resuelto_at: datetime | None = None
    created_at: datetime


class PedidoAyudaListMeta(BaseModel):
    pendientes: int
    total: int


class PedidoAyudaListResponse(BaseModel):
    data: list[PedidoAyudaOut]
    meta: PedidoAyudaListMeta
