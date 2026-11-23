"""Apoyo de HU-016: la consulta real de `fecha_fin` y la comparación con UTC.

La aceptación (`test_hu016_plazo.py`) reemplaza `_fecha_fin_de_la_tp`, así que
esto cubre lo que ella no ve: qué devuelve la consulta y cómo se compara.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from evaluation_service.routes.entregas import _fecha_fin_de_la_tp, _ya_vencio


def _db(fila: tuple | None) -> MagicMock:
    db = MagicMock()
    db.execute = AsyncMock(return_value=MagicMock(first=MagicMock(return_value=fila)))
    return db


async def test_devuelve_la_fecha_y_filtra_por_tp_viva() -> None:
    fin = datetime(2026, 11, 22, 3, 0, tzinfo=UTC)
    tp = uuid4()
    db = _db((fin,))
    assert await _fecha_fin_de_la_tp(db, tp) == fin
    sql = str(db.execute.await_args.args[0])
    assert "fecha_fin" in sql
    assert "deleted_at IS NULL" in sql
    assert db.execute.await_args.args[1] == {"tp": str(tp)}


@pytest.mark.parametrize("fila", [None, (None,)])
async def test_sin_tp_o_sin_plazo_es_none(fila) -> None:
    assert await _fecha_fin_de_la_tp(_db(fila), uuid4()) is None


def test_ya_vencio_compara_con_utc() -> None:
    assert _ya_vencio(datetime.now(UTC) - timedelta(minutes=1)) is True
    assert _ya_vencio(datetime.now(UTC) + timedelta(minutes=1)) is False


def test_fecha_sin_zona_se_toma_como_utc() -> None:
    naive = (datetime.now(UTC) - timedelta(minutes=1)).replace(tzinfo=None)
    assert _ya_vencio(naive) is True
