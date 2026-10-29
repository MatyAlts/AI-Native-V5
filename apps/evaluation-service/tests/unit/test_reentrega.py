"""`es_reentrega`: una entrega `submitted` con calificacion vigente (design D1).

Las transiciones de la maquina de estados hacen que `submitted` + calificacion
solo se alcance por `graded -> returned -> submitted`, asi que alcanza con
derivarlo al leer. Estos tests fijan la definicion de `_entrega_out_con_tp`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from evaluation_service.models.entregas import Entrega
from evaluation_service.routes.entregas import _entrega_out_con_tp

AHORA = datetime(2026, 10, 28, 12, 0, tzinfo=UTC)


def _entrega(estado: str) -> Entrega:
    return Entrega(
        id=uuid4(),
        tenant_id=uuid4(),
        tarea_practica_id=uuid4(),
        student_pseudonym=uuid4(),
        comision_id=uuid4(),
        estado=estado,
        ejercicio_estados=[],
        legacy=False,
        created_at=AHORA,
    )


def _out(estado: str, *, con_nota: bool):
    e = _entrega(estado)
    notas = {e.id: (Decimal("6.00"), AHORA)} if con_nota else {}
    return _entrega_out_con_tp(e, {}, notas)


class TestEsReentrega:
    def test_submitted_con_nota_es_reentrega_y_trae_la_nota_anterior(self) -> None:
        out = _out("submitted", con_nota=True)
        assert out.es_reentrega is True
        assert out.nota_final == 6.0

    def test_submitted_sin_nota_es_entrega_nueva(self) -> None:
        assert _out("submitted", con_nota=False).es_reentrega is False

    @pytest.mark.parametrize("estado", ["graded", "returned", "draft"])
    def test_fuera_de_submitted_nunca_es_reentrega(self, estado: str) -> None:
        # Con nota: la re-calificada (graded) ya no esta pendiente; la devuelta
        # todavia no se re-entrego.
        assert _out(estado, con_nota=True).es_reentrega is False

    def test_por_defecto_es_false(self) -> None:
        from evaluation_service.schemas.entrega import EntregaOut

        assert EntregaOut.model_fields["es_reentrega"].default is False
