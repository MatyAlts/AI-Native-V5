"""Aceptacion HU-016, plazo de entrega (orquestador, antes de construir; el
constructor no la modifica). Juani (22/11): "merega y segui con los proximos".

Hallazgo F18 de HU-014: con la TP vencida (`fecha_fin` en el pasado) el
servidor aceptaba la entrega igual (`submitted` 22:57 con `fecha_fin` 00:00).

Contrato:
  - `routes.entregas._fecha_fin_de_la_tp(db, tarea_practica_id) -> datetime | None`
    (async). Las pruebas lo reemplazan; no depende del orden de las consultas.

C03  Primera entrega (draft) con la TP vencida -> 409 que habla del plazo, y la
     entrega queda en draft.
C04  Una re-entrega (returned: el docente pidio correccion) se acepta aunque la
     TP este vencida. Decision del orquestador, a revisar en la demo: el
     docente reabrio a proposito y no tiene otra forma de habilitarla.
N01  Sin `fecha_fin`, o con `fecha_fin` en el futuro, se entrega como siempre.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from evaluation_service.auth.dependencies import User
from evaluation_service.models.entregas import Entrega, EntregaArtefacto
from evaluation_service.routes import entregas as ruta
from evaluation_service.schemas.entrega import ArtefactoItem, EntregaSubmitBody
from fastapi import HTTPException

TENANT = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
COMISION = UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
EJ = UUID("11111111-1111-1111-1111-111111111111")
EP = uuid4()

PASADO = datetime.now(UTC) - timedelta(hours=3)
FUTURO = datetime.now(UTC) + timedelta(days=3)


def _estado(marca: bool | None = None) -> dict[str, Any]:
    e: dict[str, Any] = {
        "ejercicio_id": str(EJ),
        "orden": 1,
        "episode_id": str(EP),
        "completado": True,
        "completed_at": "2026-11-22T14:00:00+00:00",
    }
    if marca is not None:
        e["reabierto_por_docente"] = marca
    return e


def _entrega(estado: str) -> Entrega:
    e = Entrega(
        id=uuid4(),
        tenant_id=TENANT,
        tarea_practica_id=uuid4(),
        student_pseudonym=uuid4(),
        comision_id=COMISION,
        estado=estado,
        ejercicio_estados=[_estado(marca=True if estado == "returned" else None)],
    )
    if estado == "returned":
        cod = "print(1)"
        e.artefactos = [
            EntregaArtefacto(
                id=uuid4(),
                tenant_id=TENANT,
                orden=1,
                episode_id=EP,
                ejercicio_id=EJ,
                codigo=cod,
                language="python",
                sha256=hashlib.sha256(cod.encode()).hexdigest(),
            )
        ]
    else:
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
    db = MagicMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            MagicMock(scalar_one_or_none=MagicMock(return_value=entrega)),
            MagicMock(first=MagicMock(return_value=(str(COMISION),))),
            MagicMock(all=MagicMock(return_value=[(1, str(EJ))])),
        ]
    )
    return db


async def _submit(monkeypatch, entrega: Entrega, fecha_fin: datetime | None) -> Any:
    async def _fecha_fin(db: Any, tarea_practica_id: UUID) -> datetime | None:
        return fecha_fin

    monkeypatch.setattr(ruta, "_fecha_fin_de_la_tp", _fecha_fin, raising=False)
    body = EntregaSubmitBody(
        artefactos=[ArtefactoItem(orden=1, ejercicio_id=EJ, codigo="print(2)")]
    )
    return await ruta.submit_entrega(entrega.id, body, _student(entrega), _db(entrega))


# ── C03 ────────────────────────────────────────────────────────────────


async def test_c03_primera_entrega_con_la_tp_vencida_se_rechaza(monkeypatch) -> None:
    entrega = _entrega("draft")
    with pytest.raises(HTTPException) as exc:
        await _submit(monkeypatch, entrega, PASADO)
    assert exc.value.status_code == 409
    assert "plazo" in str(exc.value.detail).lower()
    assert entrega.estado == "draft"


# ── C04 ────────────────────────────────────────────────────────────────


async def test_c04_la_reentrega_pedida_por_el_docente_se_acepta_vencida(monkeypatch) -> None:
    entrega = _entrega("returned")
    await _submit(monkeypatch, entrega, PASADO)
    assert entrega.estado == "submitted"


# ── N01 ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("fecha_fin", [None, FUTURO])
async def test_n01_sin_plazo_o_en_plazo_se_entrega(monkeypatch, fecha_fin) -> None:
    entrega = _entrega("draft")
    await _submit(monkeypatch, entrega, fecha_fin)
    assert entrega.estado == "submitted"
