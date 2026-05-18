"""Rutas HTTP del content-service."""

from content_service.routes import health, materiales, retrieve

__all__ = ["health", "materiales", "retrieve"]
