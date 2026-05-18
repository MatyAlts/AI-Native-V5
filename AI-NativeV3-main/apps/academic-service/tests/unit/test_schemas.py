"""Tests unitarios de validación de schemas Pydantic.

Son rápidos (no DB, no red) y se corren en cada PR.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from academic_service.schemas.carrera import CarreraCreate
from academic_service.schemas.comision import ComisionCreate, PeriodoCreate
from academic_service.schemas.universidad import UniversidadCreate
from pydantic import ValidationError


class TestUniversidadSchema:
    def test_valida_codigo_sin_espacios(self) -> None:
        """El código solo admite alfanuméricos, guiones y underscores."""
        with pytest.raises(ValidationError) as exc_info:
            UniversidadCreate(
                nombre="Test U",
                codigo="con espacios",
                keycloak_realm="test",
            )
        assert "codigo" in str(exc_info.value)

    def test_crea_minimo(self) -> None:
        u = UniversidadCreate(
            nombre="Universidad Nacional de San Luis",
            codigo="unsl",
            keycloak_realm="unsl",
        )
        assert u.nombre == "Universidad Nacional de San Luis"
        assert u.config == {}

    def test_rechaza_nombre_corto(self) -> None:
        with pytest.raises(ValidationError):
            UniversidadCreate(nombre="X", codigo="x", keycloak_realm="x")


class TestCarreraSchema:
    def test_duracion_en_rango(self) -> None:
        with pytest.raises(ValidationError):
            CarreraCreate(
                facultad_id=uuid4(),
                nombre="Sistemas",
                codigo="LIS",
                duracion_semestres=30,  # fuera de rango
            )

    def test_modalidad_valida(self) -> None:
        with pytest.raises(ValidationError):
            CarreraCreate(
                facultad_id=uuid4(),
                nombre="Sistemas",
                codigo="LIS",
                modalidad="presencial-hibrida-mixta",  # no está en Literal
            )

    def test_facultad_id_required(self) -> None:
        """`facultad_id` es NOT NULL en DB y required en el payload."""
        with pytest.raises(ValidationError) as exc_info:
            CarreraCreate(
                nombre="Sistemas",
                codigo="LIS",
            )
        assert "facultad_id" in str(exc_info.value)

    def test_crea_correctamente(self) -> None:
        c = CarreraCreate(
            facultad_id=uuid4(),
            nombre="Licenciatura en Sistemas",
            codigo="LIS",
            duracion_semestres=10,
            modalidad="presencial",
        )
        assert c.duracion_semestres == 10


class TestPeriodoSchema:
    def test_fecha_fin_posterior_a_inicio(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            PeriodoCreate(
                codigo="2026-S1",
                nombre="Primer semestre 2026",
                fecha_inicio=date(2026, 6, 1),
                fecha_fin=date(2026, 3, 1),  # antes del inicio
            )
        assert "fecha_fin" in str(exc_info.value)

    def test_crea_correctamente(self) -> None:
        p = PeriodoCreate(
            codigo="2026-S1",
            nombre="Primer semestre 2026",
            fecha_inicio=date(2026, 3, 1),
            fecha_fin=date(2026, 7, 31),
        )
        assert p.estado == "abierto"


class TestComisionSchema:
    def test_budget_no_negativo(self) -> None:
        with pytest.raises(ValidationError):
            ComisionCreate(
                materia_id=uuid4(),
                periodo_id=uuid4(),
                codigo="A",
                nombre="A-Manana",
                ai_budget_monthly_usd=Decimal("-10"),
            )

    def test_cupo_en_rango(self) -> None:
        with pytest.raises(ValidationError):
            ComisionCreate(
                materia_id=uuid4(),
                periodo_id=uuid4(),
                codigo="A",
                nombre="A-Manana",
                cupo_maximo=1000,
            )

    def test_nombre_required(self) -> None:
        """`nombre` es required en el payload — no hay default."""
        with pytest.raises(ValidationError) as exc_info:
            ComisionCreate(
                materia_id=uuid4(),
                periodo_id=uuid4(),
                codigo="A",
            )
        assert "nombre" in str(exc_info.value)

    def test_nombre_empty_rejected(self) -> None:
        """`nombre=""` viola min_length=1 -> ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            ComisionCreate(
                materia_id=uuid4(),
                periodo_id=uuid4(),
                codigo="A",
                nombre="",
            )
        assert "nombre" in str(exc_info.value)

    def test_nombre_max_length(self) -> None:
        """`nombre` mas largo que 100 chars -> ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            ComisionCreate(
                materia_id=uuid4(),
                periodo_id=uuid4(),
                codigo="A",
                nombre="x" * 101,
            )
        assert "nombre" in str(exc_info.value)

    def test_crea_correctamente(self) -> None:
        c = ComisionCreate(
            materia_id=uuid4(),
            periodo_id=uuid4(),
            codigo="A",
            nombre="A-Manana",
        )
        assert c.codigo == "A"
        assert c.nombre == "A-Manana"
