"""Rutas del classifier-service."""

from classifier_service.routes import classify_ep, health

__all__ = ["classify_ep", "health"]
