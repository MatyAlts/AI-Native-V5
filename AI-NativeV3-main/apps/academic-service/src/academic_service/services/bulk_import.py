"""Servicio de importación bulk vía CSV.

Permite a docentes administradores cargar múltiples entidades del dominio
académico desde un archivo CSV. Soporta dry-run (validación sin commit) y
commit atómico (todo o nada). Cada fila confirmada genera su entrada de
audit_log (RN-016).

CSV esperado por entidad (los headers deben coincidir con los campos del
schema Pydantic correspondiente):

- facultades: nombre, codigo, universidad_id, decano_user_id (opcional)
- carreras: nombre, codigo, duracion_semestres, modalidad, facultad_id,
  director_user_id (opcional)
- planes: version, año_inicio, ordenanza (opcional), vigente, carrera_id
- materias: nombre, codigo, horas_totales, cuatrimestre_sugerido,
  objetivos (opcional), correlativas_cursar (JSON list, opcional),
  correlativas_rendir (JSON list, opcional), plan_id
- periodos: codigo, nombre, fecha_inicio, fecha_fin, estado
- comisiones: codigo, cupo_maximo, horario (JSON, opcional),
  ai_budget_monthly_usd, materia_id, periodo_id
- tareas_practicas: comision_id, codigo, titulo, enunciado,
  fecha_inicio (opcional), fecha_fin (opcional), peso (opcional),
  rubrica (JSON, opcional)
- inscripciones: comision_id, student_pseudonym, fecha_inscripcion,
  rol (regular|oyente|reinscripcion, default regular),
  estado (activa|cursando|aprobado|desaprobado|abandono, default activa),
  nota_final (opcional), fecha_cierre (opcional). ADR-029 (B.1) — destraba
  el alta masiva de estudiantes para el piloto UNSL.
"""

from __future__ import annotations

import csv
import io
import json
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from pydantic import BaseModel, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from academic_service.auth.dependencies import User
from academic_service.schemas.carrera import CarreraCreate
from academic_service.schemas.comision import ComisionCreate, PeriodoCreate
from academic_service.schemas.facultad import FacultadCreate
from academic_service.schemas.inscripcion import InscripcionCreate
from academic_service.schemas.materia import MateriaCreate
from academic_service.schemas.plan import PlanCreate
from academic_service.schemas.tarea_practica import TareaPracticaCreate
from academic_service.services.carrera_service import CarreraService
from academic_service.services.comision_service import (
    ComisionService,
    PeriodoService,
)
from academic_service.services.facultad_service import FacultadService
from academic_service.services.inscripcion_service import InscripcionService
from academic_service.services.materia_service import MateriaService
from academic_service.services.plan_service import PlanService
from academic_service.services.tarea_practica_service import TareaPracticaService

# Tope superior del payload CSV. El piloto UNSL importa Materias/Comisiones
# para 1 carrera (≈ 30-50 filas máx), así que 5 MB cubre con holgura cualquier
# caso legítimo. Evita que un upload patológico (ej. 100 MB) entre entero a
# memoria — la verificación se hace en parse_csv (servicio) y en la ruta antes
# de bufferizar a través de UploadFile.read().
MAX_CSV_BYTES = 5 * 1024 * 1024  # 5 MB

SUPPORTED_ENTITIES: tuple[str, ...] = (
    "facultades",
    "carreras",
    "planes",
    "materias",
    "periodos",
    "comisiones",
    "tareas_practicas",
    "inscripciones",
)

# JSON-list columns (parsed de string CSV a list[UUID] antes de la validación)
_JSON_LIST_COLUMNS: dict[str, tuple[str, ...]] = {
    "materias": ("correlativas_cursar", "correlativas_rendir"),
}

# JSON-object columns (parsed a dict antes de la validación)
_JSON_OBJECT_COLUMNS: dict[str, tuple[str, ...]] = {
    "comisiones": ("horario",),
}

# Boolean columns
_BOOL_COLUMNS: dict[str, tuple[str, ...]] = {
    "planes": ("vigente",),
}


def _entity_registry() -> dict[str, tuple[type[BaseModel], Any]]:
    """entity_name → (schema_class, service_factory(session))."""
    return {
        "facultades": (FacultadCreate, FacultadService),
        "carreras": (CarreraCreate, CarreraService),
        "planes": (PlanCreate, PlanService),
        "materias": (MateriaCreate, MateriaService),
        "periodos": (PeriodoCreate, PeriodoService),
        "comisiones": (ComisionCreate, ComisionService),
        "tareas_practicas": (TareaPracticaCreate, TareaPracticaService),
        "inscripciones": (InscripcionCreate, InscripcionService),
    }


class BulkImportRowError(BaseModel):
    row_number: int
    column: str | None = None
    message: str


class BulkImportReport(BaseModel):
    total_rows: int
    valid_rows: int
    invalid_rows: int
    errors: list[BulkImportRowError]


class BulkImportCommitResult(BaseModel):
    created_count: int
    created_ids: list[UUID]


def _coerce_row(entity: str, row: dict[str, str]) -> dict[str, Any]:
    """Coerce raw CSV strings al tipo esperado por el schema."""
    coerced: dict[str, Any] = {}
    json_lists = _JSON_LIST_COLUMNS.get(entity, ())
    json_objects = _JSON_OBJECT_COLUMNS.get(entity, ())
    bools = _BOOL_COLUMNS.get(entity, ())

    for key, value in row.items():
        if key is None:
            continue
        clean_key = key.lstrip("﻿").strip()
        if not clean_key:
            continue
        if value is None or value == "":
            continue
        stripped = value.strip()
        if stripped == "":
            continue

        if clean_key in json_lists or clean_key in json_objects:
            coerced[clean_key] = json.loads(stripped)
        elif clean_key in bools:
            coerced[clean_key] = stripped.lower() in ("true", "1", "yes", "si", "sí")
        else:
            coerced[clean_key] = stripped

    return coerced


class BulkImportService:
    """Importación bulk de entidades académicas desde CSV."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.registry = _entity_registry()

    def _check_entity(self, entity: str) -> None:
        if entity not in self.registry:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Entidad '{entity}' no soportada para bulk import. "
                    f"Soportadas: {', '.join(SUPPORTED_ENTITIES)}"
                ),
            )

    def parse_csv(self, content: bytes, entity: str) -> list[dict[str, str]]:
        self._check_entity(entity)
        if len(content) > MAX_CSV_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=(
                    f"CSV demasiado grande ({len(content)} bytes); "
                    f"máximo permitido: {MAX_CSV_BYTES} bytes (5 MB)"
                ),
            )
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"CSV no es UTF-8 válido: {exc}",
            ) from exc

        try:
            reader = csv.DictReader(io.StringIO(text))
            if reader.fieldnames is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="CSV vacío o sin headers",
                )
            return [dict(row) for row in reader]
        except csv.Error as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"CSV malformado: {exc}",
            ) from exc

    def validate_row(
        self, entity: str, row: dict[str, str]
    ) -> tuple[BaseModel | None, BulkImportRowError | None]:
        """Devuelve (instancia validada, None) o (None, error)."""
        self._check_entity(entity)
        schema_cls, _ = self.registry[entity]

        if entity == "tareas_practicas":
            rubrica_raw = row.get("rubrica")
            if rubrica_raw is not None and rubrica_raw.strip() != "":
                try:
                    json.loads(rubrica_raw.strip())
                except json.JSONDecodeError:
                    return None, BulkImportRowError(
                        row_number=0,
                        column="rubrica",
                        message="rubrica must be valid JSON",
                    )
            # ADR-034 (Sec 9 epic): test_cases es JSONB; el bulk-import lo
            # acepta como columna CSV con un JSON array stringified.
            test_cases_raw = row.get("test_cases")
            if test_cases_raw is not None and test_cases_raw.strip() != "":
                try:
                    parsed = json.loads(test_cases_raw.strip())
                except json.JSONDecodeError:
                    return None, BulkImportRowError(
                        row_number=0,
                        column="test_cases",
                        message="test_cases must be valid JSON array",
                    )
                if not isinstance(parsed, list):
                    return None, BulkImportRowError(
                        row_number=0,
                        column="test_cases",
                        message="test_cases must be a JSON array",
                    )

        try:
            coerced = _coerce_row(entity, row)
            if entity == "tareas_practicas" and "rubrica" in coerced:
                coerced["rubrica"] = json.loads(coerced["rubrica"])
            if entity == "tareas_practicas" and "test_cases" in coerced:
                coerced["test_cases"] = json.loads(coerced["test_cases"])
        except (json.JSONDecodeError, ValueError) as exc:
            return None, BulkImportRowError(
                row_number=0, column=None, message=f"Fila no parseable: {exc}"
            )

        try:
            instance = schema_cls(**coerced)
        except ValidationError as exc:
            first = exc.errors()[0]
            column = ".".join(str(p) for p in first.get("loc", ())) or None
            return None, BulkImportRowError(
                row_number=0, column=column, message=first.get("msg", "validación falló")
            )
        return instance, None

    async def dry_run(
        self, entity: str, rows: list[dict[str, str]], user: User
    ) -> BulkImportReport:
        self._check_entity(entity)
        errors: list[BulkImportRowError] = []
        valid_count = 0

        for idx, row in enumerate(rows):
            row_number = idx + 2  # header es fila 1
            instance, error = self.validate_row(entity, row)
            if error is not None:
                errors.append(
                    BulkImportRowError(
                        row_number=row_number,
                        column=error.column,
                        message=error.message,
                    )
                )
                continue

            assert instance is not None  # narrowing: si no hay error, hay instance
            fk_error = await self._check_fk_existence(entity, instance, user)
            if fk_error is not None:
                errors.append(
                    BulkImportRowError(
                        row_number=row_number,
                        column=fk_error.column,
                        message=fk_error.message,
                    )
                )
                continue

            valid_count += 1

        return BulkImportReport(
            total_rows=len(rows),
            valid_rows=valid_count,
            invalid_rows=len(errors),
            errors=errors,
        )

    async def commit(
        self, entity: str, rows: list[dict[str, str]], user: User
    ) -> BulkImportCommitResult:
        self._check_entity(entity)

        report = await self.dry_run(entity, rows, user)
        if report.invalid_rows > 0:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "message": (f"Bulk import abortado: {report.invalid_rows} fila(s) inválida(s)"),
                    "report": report.model_dump(mode="json"),
                },
            )

        _, service_factory = self.registry[entity]
        service = service_factory(self.session)
        created_ids: list[UUID] = []

        for row in rows:
            instance, _ = self.validate_row(entity, row)
            assert instance is not None  # garantizado por dry_run previo
            obj = await service.create(instance, user)
            created_ids.append(obj.id)

        return BulkImportCommitResult(created_count=len(created_ids), created_ids=created_ids)

    async def _check_fk_existence(
        self, entity: str, instance: BaseModel, user: User
    ) -> BulkImportRowError | None:
        """Chequeo read-only de existencia de FKs (sin escribir)."""
        try:
            if entity == "facultades":
                from academic_service.repositories import UniversidadRepository

                await UniversidadRepository(self.session).get_or_404(
                    instance.universidad_id  # type: ignore[attr-defined]
                )
            elif entity == "carreras":
                from academic_service.repositories import FacultadRepository

                await FacultadRepository(self.session).get_or_404(
                    instance.facultad_id  # type: ignore[attr-defined]
                )
            elif entity == "planes":
                from academic_service.repositories import CarreraRepository

                await CarreraRepository(self.session).get_or_404(
                    instance.carrera_id  # type: ignore[attr-defined]
                )
            elif entity == "materias":
                from academic_service.repositories import PlanEstudiosRepository

                await PlanEstudiosRepository(self.session).get_or_404(
                    instance.plan_id  # type: ignore[attr-defined]
                )
            elif entity == "comisiones":
                from academic_service.repositories import (
                    MateriaRepository,
                    PeriodoRepository,
                )

                await MateriaRepository(self.session).get_or_404(
                    instance.materia_id  # type: ignore[attr-defined]
                )
                periodo = await PeriodoRepository(self.session).get_or_404(
                    instance.periodo_id  # type: ignore[attr-defined]
                )
                if getattr(periodo, "estado", "abierto") != "abierto":
                    return BulkImportRowError(
                        row_number=0,
                        column="periodo_id",
                        message=f"Periodo {periodo.codigo} está cerrado",
                    )
            elif entity == "tareas_practicas":
                from academic_service.repositories import ComisionRepository

                await ComisionRepository(self.session).get_or_404(
                    instance.comision_id  # type: ignore[attr-defined]
                )
            elif entity == "inscripciones":
                # ADR-029: la inscripcion requiere que la comision exista en
                # el tenant del caller. NO validamos `student_pseudonym` contra
                # Keycloak — la identidad real vive alla; el bulk-import asume
                # que el CSV ya trae pseudonimos derivados (federacion LDAP).
                from academic_service.repositories import ComisionRepository

                await ComisionRepository(self.session).get_or_404(
                    instance.comision_id  # type: ignore[attr-defined]
                )
        except HTTPException as exc:
            return BulkImportRowError(
                row_number=0,
                column=None,
                message=str(exc.detail),
            )
        return None
