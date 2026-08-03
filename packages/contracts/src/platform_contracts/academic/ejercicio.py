"""Schemas Pydantic del Ejercicio como entidad de primera clase reusable.

Define los contratos para la API REST `/api/v1/ejercicios` y para la
tabla intermedia `tp_ejercicios` (asociación N:M con `TareaPractica`).

Ver ADR-047 (Ejercicio primera clase) y ADR-048 (schema pedagógico).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

# Texto libre: la taxonomia de unidades NO es fija — cada materia define las suyas.
# Se mantiene el alias por compatibilidad de imports.
UnidadTematica = str
Dificultad = Literal["basica", "intermedia", "avanzada"]
NivelN4 = Literal[1, 2, 3, 4]

# Lenguaje del ejercicio. El conjunto vive acá y NO como CHECK en la base: el
# precedente de `unidad_tematica` (migración 20260611_0001, que sacó su CHECK
# para hacerla texto libre) muestra el costo de cerrar un enum en el schema —
# cada valor nuevo pediria una migración. Agregar un lenguaje es tocar esta linea.
Language = Literal["python", "java"]
DEFAULT_LANGUAGE: Language = "python"


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
    # `pytest_assert` y `junit_assert` son los asserts de cada lenguaje;
    # `stdin_stdout` es agnóstico. El tipo NO se valida contra el `language`
    # del ejercicio: el contrato del test case es autosuficiente y no conoce a
    # su ejercicio. La coherencia entre ambos es responsabilidad del servicio.
    type: Literal["stdin_stdout", "pytest_assert", "junit_assert"]
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

    # Materia del ejercicio (Prog 1, Prog 2, …). El banco se filtra por esta
    # materia; nullable para compat con el banco histórico (global por tenant).
    materia_id: UUID | None = None

    unidad_tematica: UnidadTematica
    dificultad: Dificultad | None = None
    # El banco historico es integramente Python; el default preserva su
    # semantica sin necesidad de backfill.
    language: Language = DEFAULT_LANGUAGE
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
    materia_id: UUID | None = None
    unidad_tematica: UnidadTematica | None = None
    dificultad: Dificultad | None = None
    language: Language | None = None
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

    NO valida la suma de `peso_en_tp`, a proposito
    ---------------------------------------------
    La version anterior exigia que los pesos sumaran 1.0. Esa regla se retiro
    tras medir la base del piloto (2026-07-23), antes de invocar el validator
    por primera vez:

    - 169 de 169 asociaciones ejercicio-TP tienen peso `1.0000`. Sin excepciones.
    - 25 de 27 TPs publicadas suman su cantidad de ejercicios, no 1.0. Las 2 que
      cumplian la regla lo hacian por tener un unico ejercicio (1 x 1.0 = 1.0).
    - El valor sale del formulario del docente, que propone "1.0" por defecto y
      nadie modifica. No hay una convencion pensada detras.
    - Ningun calculo de calificacion consume el campo: `evaluation-service` no lo
      menciona en ningun punto.

    Aplicarla habria impedido republicar practicamente todas las TPs del piloto,
    para proteger la consistencia de un numero que no participa de ningun calculo.

    Si algun dia la ponderacion se implementa de verdad, la regla vuelve — pero
    junto con la migracion de los datos y el calculo que la use, no antes.

    Tampoco valida el lenguaje
    --------------------------
    La regla de "un solo lenguaje por TP" necesita los `Ejercicio` resueltos, y
    este validator solo ve `TpEjercicioCreate` (ejercicio_id / orden / peso). Vive
    en `validar_lenguaje_unico()`, que recibe los lenguajes ya resueltos por el
    servicio desde la base — no del cliente, que podria mentir.
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

        return self


def validar_tp_no_vacia(*, cantidad_ejercicios: int, cantidad_test_cases: int) -> None:
    """Una TP publicable tiene contenido resoluble.

    La regla NO es "tiene ejercicios": una TP monolitica legitima no tiene
    ninguna fila en `tp_ejercicios` y lleva sus propios `test_cases`. La regla es
    "tiene ejercicios de banco O test cases propios".

    Vive aparte de `TpEjerciciosValidator.validate_set` porque ese hace
    `if not self.tp_ejercicios: return self` — retorna conforme ante lista vacia,
    que es justo el caso que hay que rechazar cuando ademas no hay test cases.

    Raises:
        ValueError: si la TP no tiene ni ejercicios ni test cases propios.
    """
    if cantidad_ejercicios == 0 and cantidad_test_cases == 0:
        raise ValueError(
            "Una TP no se puede publicar vacia: agregue ejercicios del banco o test cases propios"
        )


def validar_lenguaje_unico(*, language_tp: Language, languages_ejercicios: list[Language]) -> None:
    """Todos los ejercicios de una TP comparten lenguaje, y es el de la TP.

    El editor del alumno carga un unico runtime por episodio, asi que una TP
    mixta no es "inconsistente": es irresoluble.

    Los lenguajes llegan ya resueltos desde la base (via
    `TpEjercicioService.list_by_tp`, que hace selectinload del `Ejercicio`). NO se
    aceptan del cliente: es un dato derivado y el cliente podria mentir.

    Args:
        language_tp: lenguaje declarado en la `TareaPractica`.
        languages_ejercicios: lenguaje de cada `Ejercicio` asociado, ya resuelto.

    Raises:
        ValueError: si hay mas de un lenguaje entre los ejercicios, o si el unico
            que hay no coincide con el de la TP.
    """
    if not languages_ejercicios:
        return

    distintos = sorted(set(languages_ejercicios))
    if len(distintos) > 1:
        raise ValueError(
            f"Una TP admite un solo lenguaje; los ejercicios mezclan: {', '.join(distintos)}"
        )

    (language_ejercicios,) = distintos
    if language_ejercicios != language_tp:
        raise ValueError(
            f"Los ejercicios son de '{language_ejercicios}' pero la TP declara '{language_tp}'"
        )
