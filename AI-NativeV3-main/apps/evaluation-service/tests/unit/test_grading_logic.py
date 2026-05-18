"""Tests unitarios de la logica de calificacion.

Valida las reglas de transicion de estado que NO requieren DB:
- schema de CalificacionCreate
- validaciones de nota_final
- estructura de detalle_criterios

Los tests de integracion (llamadas HTTP reales + DB) se documentan
para cuando se agregue testcontainers a este servicio.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from evaluation_service.schemas.entrega import CalificacionCreate, CriterioCalificacion


class TestCalificacionRules:
    """Valida las reglas de negocio de calificacion via schemas."""

    def test_nota_maximo(self) -> None:
        cal = CalificacionCreate(nota_final=Decimal("10.00"))
        assert cal.nota_final == Decimal("10.00")

    def test_nota_minimo(self) -> None:
        cal = CalificacionCreate(nota_final=Decimal("0.00"))
        assert cal.nota_final == Decimal("0.00")

    def test_nota_decimal_valida(self) -> None:
        cal = CalificacionCreate(nota_final=Decimal("7.50"))
        assert cal.nota_final == Decimal("7.50")

    def test_rechaza_nota_negativa(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            CalificacionCreate(nota_final=Decimal("-0.01"))
        assert "nota_final" in str(exc_info.value)

    def test_rechaza_nota_mayor_diez(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            CalificacionCreate(nota_final=Decimal("10.01"))
        assert "nota_final" in str(exc_info.value)

    def test_criterios_opcionales(self) -> None:
        """Sin criterios es valido: la rubrica puede no tener items."""
        cal = CalificacionCreate(nota_final=Decimal("8.0"))
        assert cal.detalle_criterios == []

    def test_criterios_multiples(self) -> None:
        cal = CalificacionCreate(
            nota_final=Decimal("9.0"),
            detalle_criterios=[
                CriterioCalificacion(
                    criterio="Correctitud",
                    puntaje=Decimal("4.0"),
                    max_puntaje=Decimal("5.0"),
                ),
                CriterioCalificacion(
                    criterio="Legibilidad",
                    puntaje=Decimal("3.0"),
                    max_puntaje=Decimal("3.0"),
                    comentario="Muy claro",
                ),
                CriterioCalificacion(
                    criterio="Eficiencia",
                    puntaje=Decimal("2.0"),
                    max_puntaje=Decimal("2.0"),
                ),
            ],
        )
        assert len(cal.detalle_criterios) == 3

    def test_feedback_general_opcional(self) -> None:
        cal = CalificacionCreate(nota_final=Decimal("5.0"))
        assert cal.feedback_general is None

    def test_feedback_general_presente(self) -> None:
        cal = CalificacionCreate(
            nota_final=Decimal("5.0"),
            feedback_general="Buen intento, revisar la eficiencia.",
        )
        assert cal.feedback_general == "Buen intento, revisar la eficiencia."
