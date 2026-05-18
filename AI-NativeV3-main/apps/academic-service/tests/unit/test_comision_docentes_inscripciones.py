"""Tests unitarios para los schemas de UsuarioComision e InscripcionCreateIndividual.

Validan que los payloads nuevos de los endpoints de docentes e inscripciones
individuales (task 1.1-1.4) se construyen y rechazan correctamente.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from academic_service.schemas.inscripcion import InscripcionCreateIndividual, InscripcionOut
from academic_service.schemas.usuario_comision import UsuarioComisionCreate, UsuarioComisionOut
from pydantic import ValidationError


class TestUsuarioComisionCreate:
    def test_crea_con_campos_obligatorios(self) -> None:
        uc = UsuarioComisionCreate(
            user_id=uuid4(),
            rol="titular",
            fecha_desde=date(2026, 3, 1),
        )
        assert uc.rol == "titular"
        assert uc.fecha_hasta is None

    def test_acepta_todos_los_roles(self) -> None:
        for rol in ("titular", "adjunto", "jtp", "ayudante", "corrector"):
            uc = UsuarioComisionCreate(
                user_id=uuid4(),
                rol=rol,
                fecha_desde=date(2026, 3, 1),
            )
            assert uc.rol == rol

    def test_rechaza_rol_invalido(self) -> None:
        with pytest.raises(ValidationError):
            UsuarioComisionCreate(
                user_id=uuid4(),
                rol="rectorado",  # no existe
                fecha_desde=date(2026, 3, 1),
            )

    def test_acepta_fecha_hasta(self) -> None:
        uc = UsuarioComisionCreate(
            user_id=uuid4(),
            rol="jtp",
            fecha_desde=date(2026, 3, 1),
            fecha_hasta=date(2026, 7, 31),
        )
        assert uc.fecha_hasta == date(2026, 7, 31)


class TestInscripcionCreateIndividual:
    def test_crea_con_campos_obligatorios(self) -> None:
        insc = InscripcionCreateIndividual(
            student_pseudonym=uuid4(),
            fecha_inscripcion=date(2026, 3, 1),
        )
        assert insc.rol == "regular"
        assert insc.estado == "activa"
        assert insc.nota_final is None

    def test_acepta_rol_oyente(self) -> None:
        insc = InscripcionCreateIndividual(
            student_pseudonym=uuid4(),
            fecha_inscripcion=date(2026, 3, 1),
            rol="oyente",
        )
        assert insc.rol == "oyente"

    def test_rechaza_rol_invalido(self) -> None:
        with pytest.raises(ValidationError):
            InscripcionCreateIndividual(
                student_pseudonym=uuid4(),
                fecha_inscripcion=date(2026, 3, 1),
                rol="superadmin",
            )

    def test_rechaza_estado_invalido(self) -> None:
        with pytest.raises(ValidationError):
            InscripcionCreateIndividual(
                student_pseudonym=uuid4(),
                fecha_inscripcion=date(2026, 3, 1),
                estado="desconocido",
            )

    def test_acepta_nota_final_en_rango(self) -> None:
        from decimal import Decimal

        insc = InscripcionCreateIndividual(
            student_pseudonym=uuid4(),
            fecha_inscripcion=date(2026, 3, 1),
            nota_final=Decimal("8.5"),
        )
        assert insc.nota_final == Decimal("8.5")

    def test_rechaza_nota_fuera_de_rango(self) -> None:
        with pytest.raises(ValidationError):
            InscripcionCreateIndividual(
                student_pseudonym=uuid4(),
                fecha_inscripcion=date(2026, 3, 1),
                nota_final=11,  # > 10
            )


class TestInscripcionOutSerialization:
    """Verifica que `nota_final` se serializa como `float` (number JSON), no
    como `Decimal` (string JSON).

    Backlog QA 2026-05-07 / sprint 2026-05-17: el wire format previo era
    `"8.50"` (string), el web-admin workaroundeaba tipándolo `string | null`.
    Tras el fix con `nota_final: float | None` + `field_validator(mode="before")`,
    el response devuelve `8.5` (number) y preserva `null`. Mismo patrón que
    `CalificacionOut.nota_final` (entregas) — replicado para nota de cursada.
    """

    def _build_out(self, nota: Decimal | float | int | None) -> InscripcionOut:
        return InscripcionOut(
            id=uuid4(),
            tenant_id=uuid4(),
            comision_id=uuid4(),
            student_pseudonym=uuid4(),
            rol="regular",
            estado="aprobado",
            fecha_inscripcion=date(2026, 3, 1),
            nota_final=nota,  # type: ignore[arg-type]
            fecha_cierre=date(2026, 7, 31),
            created_at=datetime.utcnow(),
        )

    def test_decimal_se_castea_a_float(self) -> None:
        """Decimal de la DB -> float en el modelo."""
        insc = self._build_out(Decimal("8.50"))
        assert isinstance(insc.nota_final, float)
        assert insc.nota_final == 8.5

    def test_none_se_preserva(self) -> None:
        """`nota_final` nullable: None se preserva (cursando, sin nota aún)."""
        insc = self._build_out(None)
        assert insc.nota_final is None

    def test_json_serializa_como_number_no_string(self) -> None:
        """Wire format: `8.5` (number), NO `"8.50"` (string). Este es
        el contrato que el frontend espera (tipo TS = `number | null`)."""
        insc = self._build_out(Decimal("8.50"))
        json_str = insc.model_dump_json()
        assert '"nota_final":8.5' in json_str
        assert '"nota_final":"8.5"' not in json_str
        assert '"nota_final":"8.50"' not in json_str

    def test_json_serializa_null_cuando_nota_es_none(self) -> None:
        """Wire format: `null` (no `"null"` string)."""
        insc = self._build_out(None)
        json_str = insc.model_dump_json()
        assert '"nota_final":null' in json_str

    def test_model_dump_python_es_float(self) -> None:
        """`model_dump()` (sin mode='json') tambien devuelve float."""
        insc = self._build_out(Decimal("6.75"))
        dumped = insc.model_dump()
        assert isinstance(dumped["nota_final"], float)
        assert dumped["nota_final"] == 6.75
