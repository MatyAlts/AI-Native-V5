"""Aceptacion HU-020, reabrir con la TP vencida (orquestador, antes de construir;
el constructor no la modifica). Juani (23/11): "manda estos arreglos a hacerse
en una hu nueva" y "sisi" a los criterios.

Hallazgo F20 de la re-prueba en produccion: con la TP vencida, "Volver a abrir"
des-marca el ejercicio (3/3 pasa a 2/3) y despues el alumno no puede abrir el
episodio para volver a completarlo: queda trabado sin poder entregar.

Contrato: el PATCH `/entregas/{id}/ejercicio/{orden}` lee el plazo con
`routes.entregas._fecha_fin_de_la_tp(db, tarea_practica_id)` (el mismo de HU-016);
las pruebas lo reemplazan.

C01  draft + TP vencida + des-marcar (completado=False) -> 409 que habla del
     plazo, y el ejercicio sigue completado.
N01  Dentro del plazo (o sin plazo), des-marcar funciona como hoy.
N02  Una re-entrega pedida por el docente (returned) sigue pudiendo reabrir
     aunque la TP este vencida (coherente con C04 de HU-016).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from evaluation_service.auth.dependencies import User
from evaluation_service.models.entregas import Entrega
from evaluation_service.routes import entregas as ruta
from evaluation_service.schemas.entrega import MarkEjercicioBody
from fastapi import HTTPException

TENANT = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
COMISION = UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
EJ = UUID("11111111-1111-1111-1111-111111111111")

PASADO = datetime.now(UTC) - timedelta(hours=3)
FUTURO = datetime.now(UTC) + timedelta(days=3)


def _entrega(estado: str) -> Entrega:
    est: dict[str, Any] = {
        "ejercicio_id": str(EJ),
        "orden": 1,
        "episode_id": str(uuid4()),
        "completado": True,
        "completed_at": "2026-11-23T14:00:00+00:00",
    }
    if estado == "returned":
        est["completado"] = True
        est["reabierto_por_docente"] = True
    e = Entrega(
        id=uuid4(),
        tenant_id=TENANT,
        tarea_practica_id=uuid4(),
        student_pseudonym=uuid4(),
        comision_id=COMISION,
        estado=estado,
        ejercicio_estados=[est],
    )
    e.artefactos = []
    e.legacy = False
    e.artefacto_sha256 = None
    e.deleted_at = None
    e.submitted_at = None
    e.created_at = datetime(2026, 11, 1, tzinfo=UTC)
    return e


def _student(entrega: Entrega) -> User:
    return User(
        id=entrega.student_pseudonym,
        tenant_id=TENANT,
        email="a@utn.edu.ar",
        roles=frozenset({"estudiante"}),
        realm="utn",
    )


def _db(entrega: Entrega) -> MagicMock:
    """1ra consulta: la entrega; 2da: la comision visible; despues, nada."""
    llamadas = {"n": 0}

    async def _execute(*_a: Any, **_k: Any) -> MagicMock:
        llamadas["n"] += 1
        if llamadas["n"] == 1:
            return MagicMock(scalar_one_or_none=MagicMock(return_value=entrega))
        if llamadas["n"] == 2:
            return MagicMock(first=MagicMock(return_value=(str(COMISION),)))
        return MagicMock(
            first=MagicMock(return_value=None),
            all=MagicMock(return_value=[]),
            scalar_one_or_none=MagicMock(return_value=None),
        )

    db = MagicMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    db.execute = AsyncMock(side_effect=_execute)
    return db


async def _desmarcar(monkeypatch, entrega: Entrega, fecha_fin: datetime | None) -> Any:
    async def _fecha_fin(db: Any, tarea_practica_id: UUID) -> datetime | None:
        return fecha_fin

    monkeypatch.setattr(ruta, "_fecha_fin_de_la_tp", _fecha_fin, raising=False)
    body = MarkEjercicioBody(completado=False, ejercicio_id=EJ)
    return await ruta.mark_ejercicio_completado(
        entrega.id, 1, body, _student(entrega), _db(entrega)
    )


def _completado(entrega: Entrega) -> bool:
    return bool((entrega.ejercicio_estados or [{}])[0].get("completado"))


# ── C01 ────────────────────────────────────────────────────────────────


async def test_c01_desmarcar_con_la_tp_vencida_se_rechaza(monkeypatch) -> None:
    entrega = _entrega("draft")
    with pytest.raises(HTTPException) as exc:
        await _desmarcar(monkeypatch, entrega, PASADO)
    assert exc.value.status_code == 409
    assert "plazo" in str(exc.value.detail).lower()
    assert _completado(entrega) is True


# ── N01 ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("fecha_fin", [None, FUTURO])
async def test_n01_en_plazo_o_sin_plazo_se_desmarca(monkeypatch, fecha_fin) -> None:
    entrega = _entrega("draft")
    await _desmarcar(monkeypatch, entrega, fecha_fin)
    assert _completado(entrega) is False


# ── N02 ────────────────────────────────────────────────────────────────


async def test_n02_la_reentrega_pedida_por_el_docente_reabre_vencida(monkeypatch) -> None:
    entrega = _entrega("returned")
    await _desmarcar(monkeypatch, entrega, PASADO)
    assert _completado(entrega) is False
