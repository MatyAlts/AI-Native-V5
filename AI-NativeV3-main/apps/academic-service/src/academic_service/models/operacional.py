"""Jerarquía operativa: Periodo → Comisión → Inscripción + Usuario_Comision."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

import sqlalchemy as sa
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from academic_service.models.base import (
    Base,
    TenantMixin,
    TimestampMixin,
    fk_uuid,
    utc_now,
    uuid_pk,
)

if TYPE_CHECKING:
    from academic_service.models.institucional import Materia


class Periodo(Base, TenantMixin, TimestampMixin):
    """Período lectivo (ej. 2026-S1, 2026-S2)."""

    __tablename__ = "periodos"

    id: Mapped[uuid.UUID] = uuid_pk()
    codigo: Mapped[str] = mapped_column(String(20), nullable=False)
    nombre: Mapped[str] = mapped_column(String(100), nullable=False)
    fecha_inicio: Mapped[date] = mapped_column(Date, nullable=False)
    fecha_fin: Mapped[date] = mapped_column(Date, nullable=False)
    estado: Mapped[str] = mapped_column(String(20), default="abierto")  # abierto|cerrado

    comisiones: Mapped[list[Comision]] = relationship(back_populates="periodo")

    __table_args__ = (UniqueConstraint("tenant_id", "codigo", name="uq_periodo_tenant_codigo"),)


class Comision(Base, TenantMixin, TimestampMixin):
    """Instancia concreta de una Materia en un Periodo específico.

    Es la unidad operativa principal del sistema: docentes asignados,
    estudiantes inscriptos, material de cátedra, tutor socrático y CTR
    viven TODOS al nivel de Comisión.
    """

    __tablename__ = "comisiones"

    id: Mapped[uuid.UUID] = uuid_pk()
    materia_id: Mapped[uuid.UUID] = fk_uuid("materias.id")
    periodo_id: Mapped[uuid.UUID] = fk_uuid("periodos.id")
    codigo: Mapped[str] = mapped_column(String(50), nullable=False)
    nombre: Mapped[str] = mapped_column(String(100), nullable=False)
    cupo_maximo: Mapped[int] = mapped_column(Integer, default=50)
    horario: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    # Hash de la configuración completa del curso AI-Native (prompt +
    # reference_profile + classifier_config); forma parte de cada evento
    # CTR de esta comisión, ver ADR-009.
    curso_config_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Presupuesto mensual de IA en USD
    ai_budget_monthly_usd: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), default=Decimal("100.00")
    )

    materia: Mapped[Materia] = relationship(back_populates="comisiones")
    periodo: Mapped[Periodo] = relationship(back_populates="comisiones")
    inscripciones: Mapped[list[Inscripcion]] = relationship(back_populates="comision")
    usuarios_comision: Mapped[list[UsuarioComision]] = relationship(back_populates="comision")

    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "materia_id",
            "periodo_id",
            "codigo",
            name="uq_comision_codigo",
        ),
    )


class Inscripcion(Base, TenantMixin, TimestampMixin):
    """Relación estudiante-comisión.

    El estudiante aparece por su pseudónimo. La identidad real vive en
    Keycloak (no en este monorepo); el pseudónimo es opaco — para
    des-identificar, ver packages/platform-ops/privacy.py.
    """

    __tablename__ = "inscripciones"

    id: Mapped[uuid.UUID] = uuid_pk()
    comision_id: Mapped[uuid.UUID] = fk_uuid("comisiones.id")
    student_pseudonym: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), nullable=False, index=True
    )
    rol: Mapped[str] = mapped_column(String(20), default="regular")  # regular|oyente|reinscripcion
    estado: Mapped[str] = mapped_column(String(20), default="activa")
    # activa|cursando|aprobado|desaprobado|abandono
    fecha_inscripcion: Mapped[date] = mapped_column(Date, nullable=False)
    nota_final: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    fecha_cierre: Mapped[date | None] = mapped_column(Date, nullable=True)

    comision: Mapped[Comision] = relationship(back_populates="inscripciones")

    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "comision_id",
            "student_pseudonym",
            name="uq_inscripcion_student",
        ),
    )


class UsuarioComision(Base, TenantMixin, TimestampMixin):
    """Asignación de rol de docente/auxiliar/JTP a una comisión.

    Es independiente de las Inscripciones (estudiantes) porque un mismo
    usuario puede ser docente en varias comisiones y estudiante en otras.
    """

    __tablename__ = "usuarios_comision"

    id: Mapped[uuid.UUID] = uuid_pk()
    comision_id: Mapped[uuid.UUID] = fk_uuid("comisiones.id")
    user_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    rol: Mapped[str] = mapped_column(String(20), nullable=False)
    # titular|adjunto|jtp|ayudante|corrector
    permisos_extra: Mapped[list[str]] = mapped_column(JSONB, default=list)
    fecha_desde: Mapped[date] = mapped_column(Date, nullable=False)
    fecha_hasta: Mapped[date | None] = mapped_column(Date, nullable=True)

    comision: Mapped[Comision] = relationship(back_populates="usuarios_comision")

    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "comision_id",
            "user_id",
            "rol",
            name="uq_usuario_comision",
        ),
    )


class Unidad(Base, TenantMixin, TimestampMixin):
    """Unidad temática que agrupa TPs dentro de una comisión (ADR-041).

    Permite al docente organizar TPs pedagógicamente (ej. "Condicionales",
    "Funciones") para habilitar trazabilidad longitudinal cuando
    template_id=NULL en las TPs.

    Restricciones:
    - UNIQUE (tenant_id, comision_id, nombre): sin duplicados por comisión.
    - UNIQUE DEFERRABLE (tenant_id, comision_id, orden): permite swaps
      atómicos de orden en una sola transacción.
    - ON DELETE SET NULL en tareas_practicas.unidad_id — borrar una Unidad
      huerfana las TPs (no las borra).
    """

    __tablename__ = "unidades"

    id: Mapped[uuid.UUID] = uuid_pk()
    comision_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("comisiones.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    nombre: Mapped[str] = mapped_column(String(100), nullable=False)
    descripcion: Mapped[str | None] = mapped_column(Text, nullable=True)
    orden: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, onupdate=datetime.utcnow
    )
    created_by: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)

    tareas_practicas: Mapped[list["TareaPractica"]] = relationship(
        back_populates="unidad"
    )

    __table_args__ = (
        UniqueConstraint("tenant_id", "comision_id", "nombre", name="uq_unidad_nombre"),
        # DEFERRABLE INITIALLY DEFERRED se crea en la migración con DDL
        # directo — Alembic/SQLAlchemy no expone el flag DEFERRABLE en
        # UniqueConstraint, entonces acá solo declaramos la constraint
        # para que el ORM la conozca, sin el parámetro DEFERRABLE.
        # La constraint real en la DB SÍ es deferrable (ver migración).
        UniqueConstraint("tenant_id", "comision_id", "orden", name="uq_unidad_orden"),
    )


class TareaPractica(Base, TenantMixin, TimestampMixin):
    """Trabajo Práctico (TP) asignado a una comisión.

    Entidad central del piloto UNSL. Cada estudiante abre episodios CTR
    referenciando un TP; el classifier agrupa resultados por TP. Las
    versiones publicadas son inmutables — una nueva versión crea una fila
    nueva con `version++` y `parent_tarea_id` apuntando a la predecesora.
    """

    __tablename__ = "tareas_practicas"

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    comision_id: Mapped[uuid.UUID] = fk_uuid("comisiones.id")

    codigo: Mapped[str] = mapped_column(String(20), nullable=False)
    titulo: Mapped[str] = mapped_column(String(200), nullable=False)
    enunciado: Mapped[str] = mapped_column(Text, nullable=False)
    inicial_codigo: Mapped[str | None] = mapped_column(Text, nullable=True)

    fecha_inicio: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    fecha_fin: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    peso: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False, default=Decimal("1.0"))

    rubrica: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    estado: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    parent_tarea_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("tareas_practicas.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )

    # ADR-016 — vínculo opcional con la plantilla de cátedra (fuente canónica
    # por (materia_id, periodo_id)). NULL para TPs creadas sin template.
    template_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("tareas_practicas_templates.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    # True si la instancia divergió del template (edición directa de campos
    # canónicos). El CHECK `ck_tp_drift_needs_template` impide has_drift=true
    # sin template_id.
    has_drift: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=sa.false()
    )

    # ADR-034 (Sec 9 epic ai-native-completion): test cases ejecutables como
    # JSONB. Cada elemento: {id, name, type, code, expected, is_public, weight}.
    # is_public=false NO viaja al cliente (filtrado en el endpoint de get).
    # El classifier IGNORA resultados de tests is_public=false (preserva
    # reproducibilidad bit-a-bit del classifier_config_hash).
    test_cases: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=sa.text("'[]'::jsonb")
    )

    # ADR-036 (Sec 11): TRUE si la TP fue creada via el wizard de generacion
    # asistida por IA y el docente la edito-y-publico. Trazabilidad academica
    # para defensa doctoral (que TPs del piloto involucraron IA en su autoria).
    created_via_ai: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=sa.false()
    )

    created_by: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)

    # ADR-041: agrupación temática por Unidad (nullable — TPs sin asignar
    # aparecen como "Sin unidad"). ON DELETE SET NULL: borrar la Unidad no
    # borra la TP, la deja huérfana.
    unidad_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("unidades.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    template: Mapped[TareaPracticaTemplate | None] = relationship(back_populates="instances")
    unidad: Mapped[Unidad | None] = relationship(back_populates="tareas_practicas")
    tp_ejercicios: Mapped[list[TpEjercicio]] = relationship(
        back_populates="tarea_practica",
        cascade="all, delete-orphan",
        order_by="TpEjercicio.orden",
    )

    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "comision_id",
            "codigo",
            "version",
            name="uq_tarea_codigo_version",
        ),
        CheckConstraint(
            "estado IN ('draft', 'published', 'archived')",
            name="ck_tareas_practicas_estado",
        ),
        CheckConstraint(
            "peso >= 0 AND peso <= 1",
            name="ck_tareas_practicas_peso",
        ),
        CheckConstraint(
            "version >= 1",
            name="ck_tareas_practicas_version",
        ),
        CheckConstraint(
            "has_drift = false OR template_id IS NOT NULL",
            name="ck_tp_drift_needs_template",
        ),
    )


class TareaPracticaTemplate(Base, TenantMixin, TimestampMixin):
    """Plantilla pedagógica (brief) de Trabajo Práctico por (Materia, Período).

    Refactor 2026-05-12: la plantilla deja de ser una copia parcial del TP
    y pasa a ser una directiva (consigna) que sirve como prompt para que el
    docente — o el wizard de generación con IA — arme el TP en cada comisión.

    Sin fan-out automático: crear una plantilla NO crea instancias. Los TPs
    se crean on-demand por comisión; al crearlos pueden referenciar la
    plantilla via `template_id` como trazabilidad (qué consigna inspiró el TP).

    Versionado inmutable: publicados no se editan, se versionan con
    `parent_template_id` apuntando a la fila previa.
    """

    __tablename__ = "tareas_practicas_templates"

    id: Mapped[uuid.UUID] = uuid_pk()
    materia_id: Mapped[uuid.UUID] = fk_uuid("materias.id")
    periodo_id: Mapped[uuid.UUID] = fk_uuid("periodos.id")

    codigo: Mapped[str] = mapped_column(String(20), nullable=False)
    titulo: Mapped[str] = mapped_column(String(200), nullable=False)
    # `consigna`: directiva pedagógica de qué debe cubrir el TP. NO es el
    # enunciado que ve el alumno — es el prompt para que el docente / la IA
    # generen el enunciado real y los ejercicios en la instancia.
    consigna: Mapped[str] = mapped_column(Text, nullable=False)
    peso: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False, default=Decimal("1.0"))

    estado: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    parent_template_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("tareas_practicas_templates.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )

    created_by: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)

    parent: Mapped[TareaPracticaTemplate | None] = relationship(
        "TareaPracticaTemplate",
        remote_side="TareaPracticaTemplate.id",
        foreign_keys=[parent_template_id],
    )
    instances: Mapped[list[TareaPractica]] = relationship(back_populates="template")

    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "materia_id",
            "periodo_id",
            "codigo",
            "version",
            name="uq_template_codigo_version",
        ),
        CheckConstraint(
            "estado IN ('draft', 'published', 'archived')",
            name="ck_template_estado",
        ),
        CheckConstraint(
            "peso >= 0 AND peso <= 1",
            name="ck_template_peso",
        ),
        CheckConstraint(
            "version >= 1",
            name="ck_template_version",
        ),
    )


class Ejercicio(Base, TenantMixin, TimestampMixin):
    """Ejercicio reusable de primera clase (ADR-047 + ADR-048).

    Entidad independiente con UUID propio. Puede referenciarse desde
    múltiples TPs via la tabla intermedia `tp_ejercicios`. El set
    completo de campos pedagógicos PID-UTN lo hace autosuficiente para
    que el tutor-service inyecte todo el contexto socrático al system
    message del LLM (ver ADR-049 para la propagación del `ejercicio_id`
    al CTR).

    Campos pedagógicos como JSONB tipados (validados por Pydantic en la
    boundary, ver `packages/contracts/.../academic/ejercicio.py`):
    - `tutor_rules`: reglas operativas específicas del ejercicio.
    - `banco_preguntas`: banco socrático estratificado por fase N1-N4.
    - `misconceptions`: confusiones anticipadas con pregunta diagnóstica.
    - `respuesta_pista`: anti-soluciones por nivel.
    - `heuristica_cierre`: condiciones de cierre del episodio.
    - `anti_patrones`: lo que el tutor NO debe hacer en este ejercicio.

    Patrón JSONB alineado con ADR-034 (test_cases en TP): tipado en
    Pydantic, persistido como dict semi-estructurado para baja
    queryability cross-row.
    """

    __tablename__ = "ejercicios"

    id: Mapped[uuid.UUID] = uuid_pk()

    # ── Identificación ─────────────────────────────────────────
    titulo: Mapped[str] = mapped_column(String(200), nullable=False)
    enunciado_md: Mapped[str] = mapped_column(Text, nullable=False)
    inicial_codigo: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── Clasificación pedagógica ───────────────────────────────
    # 'secuenciales' | 'condicionales' | 'repetitivas' | 'mixtos'
    unidad_tematica: Mapped[str] = mapped_column(String(30), nullable=False)
    # 'basica' | 'intermedia' | 'avanzada' | NULL
    dificultad: Mapped[str | None] = mapped_column(String(20), nullable=True)
    prerequisitos: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=sa.text("'{}'::jsonb")
    )

    # ── Tests ejecutables (mismo formato que ADR-034) ─────────
    test_cases: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=sa.text("'[]'::jsonb")
    )

    # ── Evaluación ────────────────────────────────────────────
    rubrica: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    # ── Pedagogía PID-UTN (ADR-048) ───────────────────────────
    tutor_rules: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    banco_preguntas: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    misconceptions: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=sa.text("'[]'::jsonb")
    )
    respuesta_pista: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=sa.text("'[]'::jsonb")
    )
    heuristica_cierre: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    anti_patrones: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=sa.text("'[]'::jsonb")
    )

    # ── Autoría ───────────────────────────────────────────────
    created_by: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    created_via_ai: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=sa.false()
    )

    tp_ejercicios: Mapped[list[TpEjercicio]] = relationship(back_populates="ejercicio")

    __table_args__ = (
        CheckConstraint(
            "unidad_tematica IN ('secuenciales', 'condicionales', 'repetitivas', 'mixtos')",
            name="ck_ejercicios_unidad_tematica",
        ),
        CheckConstraint(
            "dificultad IS NULL OR dificultad IN ('basica', 'intermedia', 'avanzada')",
            name="ck_ejercicios_dificultad",
        ),
    )


class TpEjercicio(Base, TenantMixin):
    """Asociación N:M entre TareaPractica y Ejercicio (ADR-047).

    El `orden` y `peso_en_tp` son propios de la relación, no del
    Ejercicio en sí: el mismo Ejercicio puede aparecer con distinto
    orden/peso en TPs distintas.

    No usa TimestampMixin completo — solo `created_at` (sin soft-delete).
    El ciclo de vida de la relación está acoplado al de la TP: si la
    TP se borra hard, los `tp_ejercicios` se cascade-deletan (los
    Ejercicios sobreviven, son entidades independientes).
    """

    __tablename__ = "tp_ejercicios"

    id: Mapped[uuid.UUID] = uuid_pk()
    tarea_practica_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("tareas_practicas.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    ejercicio_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("ejercicios.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    orden: Mapped[int] = mapped_column(Integer, nullable=False)
    peso_en_tp: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    tarea_practica: Mapped[TareaPractica] = relationship(back_populates="tp_ejercicios")
    ejercicio: Mapped[Ejercicio] = relationship(back_populates="tp_ejercicios")

    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "tarea_practica_id",
            "ejercicio_id",
            name="uq_tp_ejercicio_pair",
        ),
        UniqueConstraint(
            "tenant_id",
            "tarea_practica_id",
            "orden",
            name="uq_tp_ejercicio_orden",
        ),
        CheckConstraint(
            "peso_en_tp > 0 AND peso_en_tp <= 1",
            name="ck_tp_ejercicios_peso",
        ),
        CheckConstraint(
            "orden >= 1",
            name="ck_tp_ejercicios_orden",
        ),
    )
