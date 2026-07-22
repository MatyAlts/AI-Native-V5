"""Lógica de dominio."""

from academic_service.services.carrera_service import CarreraService
from academic_service.services.comision_service import (
    ComisionService,
    PeriodoService,
)
from academic_service.services.facultad_service import FacultadService
from academic_service.services.materia_service import MateriaService
from academic_service.services.plan_service import PlanService
from academic_service.services.tarea_practica_service import TareaPracticaService
from academic_service.services.universidad_service import UniversidadService

__all__ = [
    "CarreraService",
    "ComisionService",
    "FacultadService",
    "MateriaService",
    "PeriodoService",
    "PlanService",
    "TareaPracticaService",
    "UniversidadService",
]
