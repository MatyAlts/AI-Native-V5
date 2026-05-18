"""Eventos del CTR (Cognitive Trace Record).

Cada evento del episodio es registrado con cadena SHA-256 encadenada.
Ver docs/plan-detallado-fases.md → F3.1 para detalles de implementación.

Convención de naming (F1, alineada con runtime):
- Las clases Pydantic conservan PascalCase (idioma Python).
- El campo `event_type` es el string que viaja en el bus y se persiste:
  va en snake_case porque es lo que ya emite el tutor-service en producción.
  Cambiar el string en runtime obliga a migrar seeds, tests, dashboards y
  CTRs ya persistidos — por eso alineamos los contracts al código vigente.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CTRBaseEvent(BaseModel):
    """Base de todos los eventos del CTR.

    Los campos obligatorios son los que permiten reconstruir la cadena y
    verificar integridad. Los payloads específicos viven en subclases.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    event_uuid: UUID = Field(description="Identidad global del evento (idempotencia)")
    episode_id: UUID = Field(description="Clave de partición del stream")
    tenant_id: UUID = Field(description="Universidad (tenant raíz)")
    seq: int = Field(ge=0, description="Secuencia ordinal dentro del episodio")
    ts: datetime = Field(description="Timestamp del evento en UTC ISO 8601")
    event_type: str
    prompt_system_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    prompt_system_version: str = Field(description="Versión semver del prompt activo")
    classifier_config_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


# ── Eventos de apertura y cierre ──────────────────────────────────────


class EpisodioAbiertoPayload(BaseModel):
    student_pseudonym: UUID
    problema_id: UUID
    comision_id: UUID
    curso_config_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    # ADR-047 + ADR-049: identidad permanente del Ejercicio reusable del
    # banco standalone. None = TP monolítica (sin ejercicio específico).
    # Cuando hay ejercicio_id, `ejercicio_orden` debe estar seteado y vice
    # versa (assert de consistencia en el productor del tutor-service).
    ejercicio_id: UUID | None = Field(
        default=None,
        description=(
            "UUID del Ejercicio reusable del banco standalone. "
            "Identidad permanente del ejercicio, independiente de su posición "
            "dentro de la TP. Permite agrupar episodios por ejercicio entre "
            "cohortes (unidad analítica de la tesis)."
        ),
    )
    # Orden del ejercicio dentro de la TP (denormalizado desde tp_ejercicios
    # al momento del episodio — snapshot inmutable). Mantenido junto a
    # `ejercicio_id` para preservar la lógica de secuencialidad y para
    # queries analíticas sin JOIN (ADR-049).
    ejercicio_orden: int | None = Field(
        default=None,
        ge=1,
        description=(
            "Orden del ejercicio dentro de la TP al momento del episodio "
            "(1-based). Denormalizado desde tp_ejercicios. "
            "None para TPs monolíticas."
        ),
    )


class EpisodioAbierto(CTRBaseEvent):
    event_type: Literal["episodio_abierto"] = "episodio_abierto"
    payload: EpisodioAbiertoPayload


class EpisodioCerradoPayload(BaseModel):
    final_chain_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    total_events: int = Field(ge=1)
    duration_seconds: float = Field(ge=0)


class EpisodioCerrado(CTRBaseEvent):
    event_type: Literal["episodio_cerrado"] = "episodio_cerrado"
    payload: EpisodioCerradoPayload


class EpisodioAbandonadoPayload(BaseModel):
    reason: str  # "timeout", "beforeunload", "explicit"
    last_activity_seconds_ago: float


class EpisodioAbandonado(CTRBaseEvent):
    event_type: Literal["episodio_abandonado"] = "episodio_abandonado"
    payload: EpisodioAbandonadoPayload


# ── Interacción con el tutor ──────────────────────────────────────────


class PromptEnviadoPayload(BaseModel):
    content: str
    prompt_kind: Literal[
        "solicitud_directa",
        "comparativa",
        "epistemologica",
        "validacion",
        "aclaracion_enunciado",
    ]
    chunks_used_hash: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")


class PromptEnviado(CTRBaseEvent):
    event_type: Literal["prompt_enviado"] = "prompt_enviado"
    payload: PromptEnviadoPayload


# F2 + F8: renombrado RespuestaRecibida → TutorRespondio (alinea con runtime)
# y `socratic_compliance`/`violations` pasan a ser opcionales hasta que el
# postprocesamiento real (detección de jailbreak, cálculo de compliance)
# se implemente. Ver 02-cambios-codigo-grandes.md → G3.
#
# Backlog QA pass 2026-05-07 (gap auditoría doctoral de costos de LLM):
# se agregan `tokens_input`, `tokens_output` y `provider` como **opcionales**
# para no romper la deserialización de eventos legacy persistidos antes del
# fix (los 106 históricos quedan con `None` — "gap pre-bump" aceptado por
# auditoría). Los emisores nuevos del tutor-service los completan cuando el
# ai-gateway expone usage en el SSE `done`. `tutor_respondio` NO está en
# `_EXCLUDED_FROM_FEATURES` del classifier, pero el feature extraction solo
# usa `event_type` + `ts` de este evento (NO el payload) — agregar campos
# opcionales NO altera el `classifier_config_hash` ni rompe reproducibilidad
# bit-a-bit del piloto. **NO bumpear `LABELER_VERSION`** (cambio puro de
# auditoría, sin impacto en clasificación). Ver clasificador `pipeline.py:60`.
class TutorRespondioPayload(BaseModel):
    content: str
    model_used: str  # ej. "claude-sonnet-4-6"
    chunks_used_hash: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    socratic_compliance: float | None = Field(default=None, ge=0.0, le=1.0)
    violations: list[str] = Field(default_factory=list)
    # Trazabilidad de uso de LLM (gap auditoría 2026-05-07). Opcionales para
    # backwards-compat: eventos pre-fix quedan con None y siguen deserializando.
    tokens_input: int | None = Field(
        default=None,
        ge=0,
        description=(
            "Tokens consumidos en el prompt (input/prompt tokens reportados por "
            "el provider). None si el provider no expuso usage en streaming o "
            "el evento es pre-fix 2026-05-07."
        ),
    )
    tokens_output: int | None = Field(
        default=None,
        ge=0,
        description=(
            "Tokens generados en la respuesta (output/completion tokens). "
            "None si el provider no expuso usage en streaming o el evento es "
            "pre-fix 2026-05-07."
        ),
    )
    provider: str | None = Field(
        default=None,
        description=(
            "Nombre del proveedor LLM efectivamente usado por el ai-gateway "
            "(anthropic|openai|mistral|gemini|mock|...). None para eventos "
            "pre-fix 2026-05-07."
        ),
    )


class TutorRespondio(CTRBaseEvent):
    event_type: Literal["tutor_respondio"] = "tutor_respondio"
    payload: TutorRespondioPayload


# ADR-019 (G3 Fase A): detección preprocesamiento de intentos adversos en
# prompts del estudiante. El tutor emite este evento POR CADA match del corpus
# regex ANTES de enviar el prompt al LLM. NO bloquea el flow — el prompt se
# envía igual. `guardrails_corpus_hash` permite reproducibilidad bit-a-bit
# cuando el corpus de patrones evolucione (mismo patrón que `classifier_config_hash`).
# Fase B (postprocesamiento de respuesta + cálculo de `socratic_compliance`)
# queda como agenda futura.
class IntentoAdversoDetectadoPayload(BaseModel):
    pattern_id: str = Field(
        description="Identificador estable del patrón, ej. 'jailbreak_substitution_v1_p2'"
    )
    category: Literal[
        "jailbreak_indirect",
        "jailbreak_substitution",
        "jailbreak_fiction",
        "persuasion_urgency",
        "prompt_injection",
    ]
    severity: int = Field(ge=1, le=5)
    matched_text: str = Field(description="Fragmento del prompt que matcheó")
    guardrails_corpus_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


class IntentoAdversoDetectado(CTRBaseEvent):
    event_type: Literal["intento_adverso_detectado"] = "intento_adverso_detectado"
    payload: IntentoAdversoDetectadoPayload


# ── Actividad del estudiante ──────────────────────────────────────────


class LecturaEnunciadoPayload(BaseModel):
    duration_seconds: float = Field(ge=0)


class LecturaEnunciado(CTRBaseEvent):
    event_type: Literal["lectura_enunciado"] = "lectura_enunciado"
    payload: LecturaEnunciadoPayload


# F3: renombrado NotaPersonal → AnotacionCreada (alinea con runtime).
# "Anotación" es más neutra que "Nota" y transmite mejor la idea de marca
# reflexiva. La tesis sigue hablando de "Nota personal" en la teoría.
class AnotacionCreadaPayload(BaseModel):
    content: str
    words: int = Field(ge=0)


class AnotacionCreada(CTRBaseEvent):
    event_type: Literal["anotacion_creada"] = "anotacion_creada"
    payload: AnotacionCreadaPayload


# F6: campo `origin` opcional para distinguir "el estudiante tipeó" de
# "copió del tutor" o "pasteó externo". Permite evidencia directa de
# delegación/apropiación sin depender solo de inferencia temporal (CCD).
class EdicionCodigoPayload(BaseModel):
    snapshot: str  # código completo en el momento del evento
    diff_chars: int  # cantidad de caracteres cambiados desde evento anterior
    language: str
    origin: Literal["student_typed", "copied_from_tutor", "pasted_external"] | None = Field(
        default=None,
        description=(
            "Procedencia del cambio en el editor. None = legacy/desconocido. "
            "v1.0.0 emite student_typed y pasted_external desde web-student; "
            "copied_from_tutor está declarado en el contract pero requiere "
            "una afordancia de UI (botón 'Insertar código del tutor') aún "
            "no incorporada al editor del estudiante (ver G11). El "
            "event_labeler (ADR-020) reconoce los tres valores y aplica "
            "override a N4 para los dos no-typed (copied_from_tutor + "
            "pasted_external)."
        ),
    )


class EdicionCodigo(CTRBaseEvent):
    event_type: Literal["edicion_codigo"] = "edicion_codigo"
    payload: EdicionCodigoPayload


# F4: renombrado TestsEjecutados → CodigoEjecutado (alinea con runtime).
# El payload se ampliá: passed/failed/total son opcionales (ejecución
# genérica de Pyodide puede no llevar tests). Se agregan campos de
# ejecución que el frontend ya manda (code/stdout/stderr/duration_ms/runtime).
class CodigoEjecutadoPayload(BaseModel):
    code: str
    stdout: str | None = None
    stderr: str | None = None
    duration_ms: int = Field(ge=0)
    runtime: str  # "pyodide", "python", etc.
    # Opcionales: solo presentes si se ejecutaron tests
    passed: int | None = Field(default=None, ge=0)
    failed: int | None = Field(default=None, ge=0)
    total: int | None = Field(default=None, ge=0)
    failed_test_names: list[str] = Field(default_factory=list)


class CodigoEjecutado(CTRBaseEvent):
    event_type: Literal["codigo_ejecutado"] = "codigo_ejecutado"
    payload: CodigoEjecutadoPayload


# ── Reflexion metacognitiva post-cierre (ADR-035) ───────────────────────
#
# Se appendea al CTR DESPUES de `episodio_cerrado`. El CTR es append-only:
# un episodio con `estado=closed` sigue aceptando eventos posteriores y la
# cadena criptografica continua (chain_hash sigue ligando seq+1 al anterior).
#
# Privacy: el contenido textual viaja como string libre. El export academico
# (`packages/platform-ops/academic_export.py`) redacta los 3 campos textuales
# por default; investigador con consentimiento usa `--include-reflections`.
#
# Anti-regresion clave: el classifier IGNORA estos eventos. Test en
# `apps/classifier-service/tests/unit/test_pipeline_reproducibility.py` valida
# que dos episodios identicos (uno con reflexion, otro sin) producen mismo
# `classifier_config_hash` y mismas features.
class ReflexionCompletadaPayload(BaseModel):
    que_aprendiste: str = Field(max_length=500)
    dificultad_encontrada: str = Field(max_length=500)
    que_haria_distinto: str = Field(max_length=500)
    prompt_version: str = Field(
        description=(
            "Identificador del cuestionario, ej. 'reflection/v1.0.0'. "
            "Permite distinguir reflexiones capturadas con cuestionarios "
            "diferentes en analisis longitudinal."
        )
    )
    tiempo_completado_ms: int = Field(
        ge=0,
        description="Milisegundos transcurridos desde que el modal abrio hasta el submit.",
    )


class ReflexionCompletada(CTRBaseEvent):
    event_type: Literal["reflexion_completada"] = "reflexion_completada"
    payload: ReflexionCompletadaPayload


# ── Tests ejecutados (sandbox + test cases, ADR-033 / ADR-034) ──────────
#
# Evento side-channel de gobernanza pedagogica: el alumno corrio tests
# publicos sobre su codigo en Pyodide. NO incluye la lista detallada por
# test (solo conteos) — el classifier consume conteos publicos, no resultados
# por test individual. Tests hidden quedan en piloto-1 con `tests_hidden=0`
# siempre (no se ejecutan client-side); su agenda piloto-2 esta en ADR-033.
class TestsEjecutadosPayload(BaseModel):
    test_count_total: int = Field(ge=0, description="Total de tests ejecutados (publicos)")
    test_count_passed: int = Field(ge=0)
    test_count_failed: int = Field(ge=0)
    tests_publicos: int = Field(ge=0, description="Tests con is_public=true ejecutados")
    tests_hidden: int = Field(
        ge=0,
        description=(
            "Siempre 0 en piloto-1 — los tests hidden NO se ejecutan client-side. "
            "Reservado para piloto-2 cuando se implemente sandbox-service."
        ),
    )
    chunks_used_hash: str | None = Field(
        default=None,
        pattern=r"^[a-f0-9]{64}$",
        description=(
            "Propagado del ultimo `prompt_enviado` del episodio para correlacionar "
            "ejecucion de tests con el contexto RAG vigente. None si no hubo prompt."
        ),
    )
    ejecucion_ms: int = Field(ge=0, description="Duracion total de la corrida en ms")


class TestsEjecutados(CTRBaseEvent):
    event_type: Literal["tests_ejecutados"] = "tests_ejecutados"
    payload: TestsEjecutadosPayload


# ── Entregas y Calificaciones (tp-entregas-correccion) ───────────────────
#
# Meta-eventos de gobernanza academica — NO actividad pedagogica del episodio.
# Excluidos del classifier (mismo patron que reflexion_completada).
# Emitidos por evaluation-service (service account UUID-14).
class TpEntregadaPayload(BaseModel):
    tarea_practica_id: UUID
    entrega_id: UUID
    n_ejercicios: int = Field(ge=0)
    exercise_episode_ids: list[str] = Field(
        default_factory=list,
        description="UUIDs de los episodios de cada ejercicio completado",
    )


class TpEntregada(CTRBaseEvent):
    """Emitido cuando el alumno submite formalmente su entrega de TP."""

    event_type: Literal["tp_entregada"] = "tp_entregada"
    payload: TpEntregadaPayload


class TpCalificadaPayload(BaseModel):
    entrega_id: UUID
    nota_final: float = Field(ge=0, le=10)
    graded_by: UUID


class TpCalificada(CTRBaseEvent):
    """Emitido cuando el docente califica una entrega de TP."""

    event_type: Literal["tp_calificada"] = "tp_calificada"
    payload: TpCalificadaPayload
