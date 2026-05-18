"""Schemas de request/response del ctr-service.

Los schemas de los EVENTOS como tales viven en packages/contracts
(compartidos entre emisor y consumer). Acá solo tenemos los schemas
de la API HTTP del servicio (publicar, leer episodio completo,
verificar integridad).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class EventPublishRequest(BaseModel):
    """Request para publicar un evento al stream (sync API).

    El cliente normalmente es el tutor-service. El payload ya debe venir
    validado estructuralmente contra el schema del event_type correspondiente.
    """

    event_uuid: UUID
    episode_id: UUID
    tenant_id: UUID
    seq: int = Field(ge=0)
    event_type: str
    ts: datetime
    payload: dict[str, Any]
    prompt_system_hash: str = Field(min_length=64, max_length=64)
    prompt_system_version: str
    classifier_config_hash: str = Field(min_length=64, max_length=64)


class EventPublishResponse(BaseModel):
    message_id: str
    partition: int


class EventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    event_uuid: UUID
    episode_id: UUID
    seq: int
    event_type: str
    ts: datetime
    payload: dict[str, Any]
    self_hash: str
    chain_hash: str
    prev_chain_hash: str
    prompt_system_hash: str
    prompt_system_version: str
    classifier_config_hash: str
    persisted_at: datetime


class EpisodeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    comision_id: UUID
    student_pseudonym: UUID
    problema_id: UUID
    estado: str
    opened_at: datetime
    closed_at: datetime | None
    events_count: int
    last_chain_hash: str
    integrity_compromised: bool
    prompt_system_hash: str
    classifier_config_hash: str
    curso_config_hash: str


class EpisodeWithEvents(EpisodeOut):
    events: list[EventOut]


class ChainVerificationResult(BaseModel):
    episode_id: UUID
    valid: bool
    events_count: int
    failing_seq: int | None = None
    integrity_compromised: bool
    message: str
