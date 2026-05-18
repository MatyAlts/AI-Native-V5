"""Schemas Pydantic para request/response."""

from academic_service.schemas.base import (
    BaseResponse,
    ListMeta,
    ListResponse,
    ProblemDetail,
)
from academic_service.schemas.carrera import CarreraCreate, CarreraOut, CarreraUpdate
from academic_service.schemas.comision import (
    ComisionCreate,
    ComisionOut,
    ComisionUpdate,
    ConfigHashesOut,
    PeriodoCreate,
    PeriodoOut,
    PeriodoUpdate,
)
from academic_service.schemas.facultad import (
    FacultadCreate,
    FacultadOut,
    FacultadUpdate,
)
from academic_service.schemas.inscripcion import (
    InscripcionCreate,
    InscripcionCreateIndividual,
    InscripcionOut,
    MateriaInscripta,
)
from academic_service.schemas.usuario_comision import (
    UsuarioComisionCreate,
    UsuarioComisionOut,
)
from academic_service.schemas.materia import MateriaCreate, MateriaOut, MateriaUpdate
from academic_service.schemas.plan import PlanCreate, PlanOut, PlanUpdate
from academic_service.schemas.tarea_practica import (
    TareaPracticaCreate,
    TareaPracticaOut,
    TareaPracticaUpdate,
    TareaPracticaVersionRef,
)
from academic_service.schemas.unidad import (
    UnidadCreate,
    UnidadOut,
    UnidadReorderItem,
    UnidadReorderRequest,
    UnidadUpdate,
)
from academic_service.schemas.universidad import (
    UniversidadCreate,
    UniversidadOut,
    UniversidadUpdate,
)

__all__ = [
    "BaseResponse",
    "CarreraCreate",
    "CarreraOut",
    "CarreraUpdate",
    "ComisionCreate",
    "ComisionOut",
    "ComisionUpdate",
    "ConfigHashesOut",
    "FacultadCreate",
    "FacultadOut",
    "FacultadUpdate",
    "InscripcionCreate",
    "InscripcionCreateIndividual",
    "InscripcionOut",
    "UsuarioComisionCreate",
    "UsuarioComisionOut",
    "ListMeta",
    "ListResponse",
    "MateriaCreate",
    "MateriaInscripta",
    "MateriaOut",
    "MateriaUpdate",
    "PeriodoCreate",
    "PeriodoOut",
    "PeriodoUpdate",
    "PlanCreate",
    "PlanOut",
    "PlanUpdate",
    "ProblemDetail",
    "TareaPracticaCreate",
    "TareaPracticaOut",
    "TareaPracticaUpdate",
    "TareaPracticaVersionRef",
    "UnidadCreate",
    "UnidadOut",
    "UnidadReorderItem",
    "UnidadReorderRequest",
    "UnidadUpdate",
    "UniversidadCreate",
    "UniversidadOut",
    "UniversidadUpdate",
]
