"""Schemas de respuesta estandarizados + problem+json para errores."""

from __future__ import annotations

from typing import TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class BaseResponse[T](BaseModel):
    """Response estándar de recursos individuales."""

    model_config = ConfigDict(from_attributes=True)

    data: T


class ListMeta(BaseModel):
    """Metadata de paginación por cursor."""

    cursor_next: str | None = None
    total: int | None = None


class ListResponse[T](BaseModel):
    """Response estándar de listados."""

    data: list[T]
    meta: ListMeta = Field(default_factory=ListMeta)


class ProblemDetail(BaseModel):
    """RFC 7807 problem+json."""

    type: str = "about:blank"
    title: str
    status: int
    detail: str | None = None
    instance: str | None = None
    errors: list[dict[str, str]] | None = None
