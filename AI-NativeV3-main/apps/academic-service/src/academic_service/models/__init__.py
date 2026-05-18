"""Modelos del dominio académico.

Importar todo desde aquí asegura que SQLAlchemy registre todas las tablas
en el metadata antes de generar migraciones o crear el schema.
"""

from academic_service.models.base import Base, TenantMixin, TimestampMixin
from academic_service.models.institucional import (
    Carrera,
    Facultad,
    Materia,
    PlanEstudios,
    Universidad,
)
from academic_service.models.instrumentos import (
    RespuestaCuestionarioIA,
    RespuestaPretestAutoeficacia,
    RespuestaTestTransferencia,
)
from academic_service.models.operacional import (
    Comision,
    Ejercicio,
    Inscripcion,
    Periodo,
    TareaPractica,
    TareaPracticaTemplate,
    TpEjercicio,
    Unidad,
    UsuarioComision,
)
from academic_service.models.transversal import AuditLog, CasbinRule

__all__ = [
    # Transversal
    "AuditLog",
    "Base",
    "Carrera",
    "CasbinRule",
    "Comision",
    "Ejercicio",
    "Facultad",
    "Inscripcion",
    "Materia",
    # Operacional
    "Periodo",
    "PlanEstudios",
    # Instrumentos research (P2-1, P2-2, P2-3 del PlanMejora.md)
    "RespuestaCuestionarioIA",
    "RespuestaPretestAutoeficacia",
    "RespuestaTestTransferencia",
    "TareaPractica",
    "TareaPracticaTemplate",
    "TenantMixin",
    "TimestampMixin",
    "TpEjercicio",
    "Unidad",
    # Institucional
    "Universidad",
    "UsuarioComision",
]
