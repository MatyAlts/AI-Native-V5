"""Schemas Pydantic del Ejercicio como entidad de primera clase reusable.

Define los contratos para la API REST `/api/v1/ejercicios` y para la
tabla intermedia `tp_ejercicios` (asociación N:M con `TareaPractica`).

Ver ADR-047 (Ejercicio primera clase) y ADR-048 (schema pedagógico).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

UnidadTematica = Literal["secuenciales", "condicionales", "repetitivas", "mixtos"]
Dificultad = Literal["basica", "intermedia", "avanzada"]
NivelN4 = Literal[1, 2, 3, 4]


# ─── Sub-schemas pedagógicos PID-UTN (ADR-048) ──────────────────────


class PreguntaSocraticaSchema(BaseModel):
    """Pregunta socrática del banco PID-UTN.

    Cada pregunta documenta su señal de comprensión (✓) y señal de
    alerta (✗) para que el tutor sepa cómo continuar según la respuesta
    del estudiante.
    """

    texto: str = Field(min_length=1)
    senal_comprension: str = Field(min_length=1)
    senal_alerta: str = Field(min_length=1)


class BancoPreguntasSchema(BaseModel):
    """Banco socrático estratificado por fase N1-N4.

    Replica la estructura de los bancos PID-UTN (b1.docx, condi.docx,
    mixtos.docx). El tutor selecciona preguntas según el nivel cognitivo
    inferido del turno actual.
    """

    n1: list[PreguntaSocraticaSchema] = Field(default_factory=list)
    n2: list[PreguntaSocraticaSchema] = Field(default_factory=list)
    n3: list[PreguntaSocraticaSchema] = Field(default_factory=list)
    n4: list[PreguntaSocraticaSchema] = Field(default_factory=list)


class MisconceptionSchema(BaseModel):
    """Misconception anticipada del estudiante para este ejercicio.

    `probabilidad_estimada` es el juicio del docente sobre qué tan
    frecuente es la confusión en el corpus estudiantil del piloto.
    `pregunta_diagnostica` es la pregunta que la hace observable sin
    nombrarla directamente.
    """

    descripcion: str = Field(min_length=1)
    probabilidad_estimada: float = Field(ge=0.0, le=1.0)
    pregunta_diagnostica: str = Field(min_length=1)


class PistaSchema(BaseModel):
    """Anti-solución que el tutor entrega cuando el estudiante pide código.

    `nivel` (N1-N4) indica cuánto razonamiento previo asume la pista —
    pistas de nivel más alto contienen más estructura sin entregar
    solución directa.
    """

    nivel: NivelN4
    pista: str = Field(min_length=1)


class HeuristicaCierreSchema(BaseModel):
    """Condiciones verificables para declarar el episodio cerrado."""

    tests_min_pasados: int = Field(ge=0, default=0)
    heuristica: str = Field(min_length=1)


class AntiPatronSchema(BaseModel):
    """Anti-patrón específico de este ejercicio — qué el tutor NO debe hacer."""

    patron: str = Field(min_length=1)
    descripcion: str = Field(min_length=1)
    mensaje_orientacion: str = Field(min_length=1)


class PrerequisitosSchema(BaseModel):
    """Prerrequisitos sintácticos y conceptuales del ejercicio."""

    sintacticos: list[str] = Field(default_factory=list)
    conceptuales: list[str] = Field(default_factory=list)


class TutorRulesSchema(BaseModel):
    """Reglas operativas del tutor para este ejercicio.

    Se inyectan al system message del tutor al abrir el episodio.
    """

    prohibido_dar_solucion: bool = True
    forzar_pregunta_antes_de_hint: bool = False
    nivel_socratico_minimo: NivelN4 = 1
    instrucciones_adicionales: str | None = None


# ─── Rúbrica (baja del nivel TP al ejercicio) ───────────────────────


class CriterioRubricaSchema(BaseModel):
    nombre: str = Field(min_length=1)
    descripcion: str = Field(min_length=1)
    puntaje_max: Decimal = Field(gt=0)


class RubricaEjercicioSchema(BaseModel):
    """Rúbrica de evaluación específica del ejercicio."""

    criterios: list[CriterioRubricaSchema] = Field(default_factory=list)


# ─── Test cases (mismo formato que ADR-034) ─────────────────────────


class TestCaseSchema(BaseModel):
    """Test case ejecutable del ejercicio.

    Mismo shape que `tareas_practicas.test_cases` (ADR-034). Replicado
    acá para que el ejercicio sea autosuficiente.
    """

    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    type: Literal["stdin_stdout", "pytest_assert"]
    code: str = Field(default="")
    expected: str | None = None
    is_public: bool = True
    weight: float = Field(ge=0.0)


# ─── Base compartido por Create/Update/Read ─────────────────────────


class _EjercicioBase(BaseModel):
    """Campos compartidos por Create / Update / Read."""

    titulo: str = Field(min_length=1, max_length=200)
    enunciado_md: str = Field(min_length=1)
    inicial_codigo: str | None = None

    unidad_tematica: UnidadTematica
    dificultad: Dificultad | None = None
    prerequisitos: PrerequisitosSchema = Field(default_factory=PrerequisitosSchema)

    test_cases: list[TestCaseSchema] = Field(default_factory=list)
    rubrica: RubricaEjercicioSchema | None = None

    tutor_rules: TutorRulesSchema | None = None
    banco_preguntas: BancoPreguntasSchema | None = None
    misconceptions: list[MisconceptionSchema] = Field(default_factory=list)
    respuesta_pista: list[PistaSchema] = Field(default_factory=list)
    heuristica_cierre: HeuristicaCierreSchema | None = None
    anti_patrones: list[AntiPatronSchema] = Field(default_factory=list)


# ─── Schemas de API ─────────────────────────────────────────────────


class EjercicioCreate(_EjercicioBase):
    """Payload del `POST /api/v1/ejercicios`."""

    created_via_ai: bool = False


class EjercicioUpdate(BaseModel):
    """Payload del `PATCH /api/v1/ejercicios/{id}`.

    Todos los campos opcionales (PATCH parcial). `created_via_ai` no es
    editable post-creación.
    """

    titulo: str | None = Field(default=None, min_length=1, max_length=200)
    enunciado_md: str | None = Field(default=None, min_length=1)
    inicial_codigo: str | None = None
    unidad_tematica: UnidadTematica | None = None
    dificultad: Dificultad | None = None
    prerequisitos: PrerequisitosSchema | None = None
    test_cases: list[TestCaseSchema] | None = None
    rubrica: RubricaEjercicioSchema | None = None
    tutor_rules: TutorRulesSchema | None = None
    banco_preguntas: BancoPreguntasSchema | None = None
    misconceptions: list[MisconceptionSchema] | None = None
    respuesta_pista: list[PistaSchema] | None = None
    heuristica_cierre: HeuristicaCierreSchema | None = None
    anti_patrones: list[AntiPatronSchema] | None = None


class EjercicioRead(_EjercicioBase):
    """Response del `GET /api/v1/ejercicios/{id}`."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    created_by: UUID
    created_via_ai: bool
    created_at: datetime
    deleted_at: datetime | None = None


# ─── Tabla intermedia tp_ejercicios ─────────────────────────────────


class TpEjercicioCreate(BaseModel):
    """Payload del `POST /api/v1/tareas-practicas/{tp_id}/ejercicios`."""

    ejercicio_id: UUID
    orden: int = Field(ge=1)
    peso_en_tp: Decimal = Field(gt=0, le=1)


class TpEjercicioUpdate(BaseModel):
    """Payload del `PATCH /api/v1/tareas-practicas/{tp_id}/ejercicios/{ejercicio_id}`.

    Permite reordenar y reponderar un ejercicio dentro de una TP sin
    quitarlo y volver a agregarlo.
    """

    orden: int | None = Field(default=None, ge=1)
    peso_en_tp: Decimal | None = Field(default=None, gt=0, le=1)


class TpEjercicioRead(BaseModel):
    """Response del `GET /api/v1/tareas-practicas/{tp_id}/ejercicios`.

    Incluye el `Ejercicio` embebido para evitar un roundtrip adicional
    desde el frontend o el tutor-service.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tarea_practica_id: UUID
    ejercicio_id: UUID
    orden: int
    peso_en_tp: Decimal
    ejercicio: EjercicioRead


class TpEjerciciosValidator(BaseModel):
    """Validator del set completo de ejercicios de una TP.

    Reemplaza al viejo `EjerciciosValidator` del JSONB (ADR-047 deprecation).

    Reglas:
    1. `orden` único dentro de la TP.
    2. `ejercicio_id` único dentro de la TP (un ejercicio no aparece dos veces).
    3. Suma de `peso_en_tp` = 1.0 (tolerancia 0.001).
    """

    tp_ejercicios: list[TpEjercicioCreate] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_set(self) -> TpEjerciciosValidator:
        if not self.tp_ejercicios:
            return self

        ordenes = [e.orden for e in self.tp_ejercicios]
        if len(ordenes) != len(set(ordenes)):
            raise ValueError("Los ordenes de tp_ejercicios deben ser unicos dentro de una TP")

        ejercicio_ids = [e.ejercicio_id for e in self.tp_ejercicios]
        if len(ejercicio_ids) != len(set(ejercicio_ids)):
            raise ValueError("Un ejercicio no puede aparecer dos veces en la misma TP")

        peso_total = sum(e.peso_en_tp for e in self.tp_ejercicios)
        if abs(float(peso_total) - 1.0) > 0.001:
            raise ValueError(
                f"La suma de peso_en_tp debe ser 1.0 (actual: {peso_total})"
            )

        return self
