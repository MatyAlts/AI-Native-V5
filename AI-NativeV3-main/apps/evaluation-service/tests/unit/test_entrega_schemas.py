"""Tests unitarios del ciclo de vida de Entrega y Calificacion.

Cubre validacion de schemas Pydantic sin DB. Los tests de flujo completo
(create/submit/grade) requieren la integracion — se documentan en TODO
para cuando se agregue la fixture de testcontainers a este servicio.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from evaluation_service.schemas.entrega import (
    CalificacionCreate,
    CalificacionOut,
    CriterioCalificacion,
    EntregaCreate,
    EntregaOut,
)
from pydantic import ValidationError


class TestEntregaCreate:
    def test_crea_valido(self) -> None:
        e = EntregaCreate(
            tarea_practica_id=uuid4(),
            comision_id=uuid4(),
        )
        assert e.tarea_practica_id is not None
        assert e.comision_id is not None


class TestCalificacionCreate:
    def test_crea_valido(self) -> None:
        cal = CalificacionCreate(
            nota_final=Decimal("7.5"),
            feedback_general="Buen trabajo",
            detalle_criterios=[
                CriterioCalificacion(
                    criterio="Correctitud",
                    puntaje=Decimal("3.0"),
                    max_puntaje=Decimal("4.0"),
                    comentario="Funciona bien",
                )
            ],
        )
        assert cal.nota_final == Decimal("7.5")
        assert len(cal.detalle_criterios) == 1

    def test_rechaza_nota_negativa(self) -> None:
        with pytest.raises(ValidationError):
            CalificacionCreate(nota_final=Decimal("-1"))

    def test_rechaza_nota_mayor_diez(self) -> None:
        with pytest.raises(ValidationError):
            CalificacionCreate(nota_final=Decimal("10.5"))

    def test_nota_cero_valida(self) -> None:
        cal = CalificacionCreate(nota_final=Decimal("0"))
        assert cal.nota_final == Decimal("0")

    def test_nota_diez_valida(self) -> None:
        cal = CalificacionCreate(nota_final=Decimal("10"))
        assert cal.nota_final == Decimal("10")

    def test_sin_criterios_es_valido(self) -> None:
        cal = CalificacionCreate(nota_final=Decimal("5.0"))
        assert cal.detalle_criterios == []


class TestEntregaEstados:
    """Verifica que los estados validos del schema de entrega funcionan."""

    def _build_out(self, estado: str) -> EntregaOut:
        return EntregaOut(
            id=uuid4(),
            tenant_id=uuid4(),
            tarea_practica_id=uuid4(),
            student_pseudonym=uuid4(),
            comision_id=uuid4(),
            estado=estado,
            ejercicio_estados=[],
            submitted_at=None,
            created_at=datetime.utcnow(),
            deleted_at=None,
        )

    def test_estado_draft(self) -> None:
        e = self._build_out("draft")
        assert e.estado == "draft"

    def test_estado_submitted(self) -> None:
        e = self._build_out("submitted")
        assert e.estado == "submitted"

    def test_estado_graded(self) -> None:
        e = self._build_out("graded")
        assert e.estado == "graded"

    def test_estado_returned(self) -> None:
        e = self._build_out("returned")
        assert e.estado == "returned"

    def test_estado_invalido(self) -> None:
        with pytest.raises(ValidationError):
            self._build_out("pendiente")


class TestCalificacionOutSerialization:
    """Verifica que `nota_final` se serializa como `float` (number JSON), no
    como `Decimal` (string JSON).

    Backlog QA 2026-05-07: el wire format previo era `"8.50"` (string),
    los frontends lo tipan `number` y `.toFixed()` rompía. Tras el fix con
    `nota_final: float` + `field_validator(mode="before")`, el response
    devuelve `8.5` (number).
    """

    def _build_out(self, nota: Decimal | float | int) -> CalificacionOut:
        return CalificacionOut(
            id=uuid4(),
            tenant_id=uuid4(),
            entrega_id=uuid4(),
            graded_by=uuid4(),
            nota_final=nota,  # type: ignore[arg-type]
            feedback_general="Buen trabajo",
            detalle_criterios=[],
            graded_at=datetime.now(UTC),
            created_at=datetime.now(UTC),
        )

    def test_decimal_se_castea_a_float(self) -> None:
        """Decimal de la DB -> float en el modelo."""
        cal = self._build_out(Decimal("8.50"))
        assert isinstance(cal.nota_final, float)
        assert cal.nota_final == 8.5

    def test_float_directo_no_se_modifica(self) -> None:
        """Si ya viene float, el validator es no-op."""
        cal = self._build_out(7.25)
        assert isinstance(cal.nota_final, float)
        assert cal.nota_final == 7.25

    def test_int_se_acepta_y_castea(self) -> None:
        """Pydantic acepta int y lo promueve a float (10 -> 10.0)."""
        cal = self._build_out(10)
        assert isinstance(cal.nota_final, float)
        assert cal.nota_final == 10.0

    def test_json_serializa_como_number_no_string(self) -> None:
        """Wire format: `8.5` (number), NO `"8.50"` (string). Este es
        el contrato que el frontend espera (tipo TS = `number`)."""
        cal = self._build_out(Decimal("8.50"))
        json_str = cal.model_dump_json()
        # En JSON, un number no tiene comillas. Si el field fuese Decimal,
        # Pydantic serializaria como `"nota_final": "8.50"` (string).
        assert '"nota_final":8.5' in json_str
        assert '"nota_final":"8.5"' not in json_str
        assert '"nota_final":"8.50"' not in json_str

    def test_model_dump_python_es_float(self) -> None:
        """`model_dump()` (sin mode='json') tambien devuelve float."""
        cal = self._build_out(Decimal("6.75"))
        dumped = cal.model_dump()
        assert isinstance(dumped["nota_final"], float)
        assert dumped["nota_final"] == 6.75
