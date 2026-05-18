"""Schemas de eventos compartidos — lado Python.

Los contratos viven acá para que emisores y consumidores usen la misma
definición. Cambios de schema siguen versionado semántico.
"""

from platform_contracts.academic.events import (
    CarreraCreada,
    ComisionCreada,
    EstudianteInscripto,
    MaterialIngerido,
    UniversidadCreada,
)
from platform_contracts.ctr.events import (
    AnotacionCreada,
    CodigoEjecutado,
    CTRBaseEvent,
    EdicionCodigo,
    EpisodioAbandonado,
    EpisodioAbierto,
    EpisodioCerrado,
    LecturaEnunciado,
    PromptEnviado,
    TutorRespondio,
)

__version__ = "0.1.0"

__all__ = [
    "AnotacionCreada",
    # CTR
    "CTRBaseEvent",
    "CarreraCreada",
    "CodigoEjecutado",
    "ComisionCreada",
    "EdicionCodigo",
    "EpisodioAbandonado",
    "EpisodioAbierto",
    "EpisodioCerrado",
    "EstudianteInscripto",
    "LecturaEnunciado",
    "MaterialIngerido",
    "PromptEnviado",
    "TutorRespondio",
    # Academic
    "UniversidadCreada",
]
