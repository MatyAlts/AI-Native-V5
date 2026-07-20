"""Factories para generar IDs y datos de test deterministas cuando se necesita."""

from __future__ import annotations

from uuid import UUID, uuid4


def make_tenant_id() -> UUID:
    """Genera un tenant_id para test."""
    return uuid4()


def make_episode_id() -> UUID:
    """Genera un episode_id para test."""
    return uuid4()


def make_pseudonym() -> UUID:
    """Genera un pseudónimo de estudiante para test."""
    return uuid4()


def deterministic_uuid(seed: int) -> UUID:
    """UUID determinista para tests reproducibles.

    Uso: deterministic_uuid(1) siempre devuelve el mismo UUID.
    """
    return UUID(int=seed, version=4)
