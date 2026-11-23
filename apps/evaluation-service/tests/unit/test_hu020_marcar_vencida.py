"""HU-020, N03 (prueba de apoyo del constructor, no es la aceptación).

El bloqueo por plazo de `mark_ejercicio_completado` es solo para DES-marcar.
Marcar completado con la TP vencida tiene que seguir andando: es lo que hace el
cierre de un episodio que el alumno abrió antes del vencimiento. Si el chequeo
dejara de mirar `completado`, ese cierre daría 409 y el ejercicio quedaría
pendiente para siempre.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

from evaluation_service.auth.dependencies import User
from evaluation_service.models.entregas import Entrega
from evaluation_service.routes import entregas as ruta
from evaluation_service.schemas.entrega import MarkEjercicioBody

TENANT = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
COMISION = UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
EJ = UUID("11111111-1111-1111-1111-111111111111")
PASADO = datetime.now(UTC) - timedelta(hours=3)


def _entrega_draft_pendiente() -> Entrega:
    e = Entrega(
        id=uuid4(),
        tenant_id=TENANT,
        tarea_practica_id=uuid4(),
        student_pseudonym=uuid4(),
        comision_id=COMISION,
        estado="draft",
        ejercicio_estados=[
            {
                "ejercicio_id": str(EJ),
                "orden": 1,
                "episode_id": None,
                "completado": False,
                "completed_at": None,
            }
        ],
    )
    e.artefactos = []
    e.legacy = False
    e.artefacto_sha256 = None
    e.deleted_at = None
    e.submitted_at = None
    e.created_at = datetime(2026, 11, 1, tzinfo=UTC)
    return e


def _db(entrega: Entrega) -> MagicMock:
    llamadas = {"n": 0}

    async def _execute(*_a: Any, **_k: Any) -> MagicMock:
        llamadas["n"] += 1
        if llamadas["n"] == 1:
            return MagicMock(scalar_one_or_none=MagicMock(return_value=entrega))
        if llamadas["n"] == 2:
            return MagicMock(first=MagicMock(return_value=(str(COMISION),)))
        return MagicMock(first=MagicMock(return_value=None), all=MagicMock(return_value=[]))

    db = MagicMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    db.execute = AsyncMock(side_effect=_execute)
    return db


async def test_n03_marcar_completado_con_la_tp_vencida_funciona(monkeypatch) -> None:
    async def _vencida(db: Any, tarea_practica_id: UUID) -> datetime | None:
        return PASADO

    monkeypatch.setattr(ruta, "_fecha_fin_de_la_tp", _vencida)
    entrega = _entrega_draft_pendiente()
    episodio = uuid4()
    user = User(
        id=entrega.student_pseudonym,
        tenant_id=TENANT,
        email="a@utn.edu.ar",
        roles=frozenset({"estudiante"}),
        realm="utn",
    )
    body = MarkEjercicioBody(completado=True, ejercicio_id=EJ, episode_id=episodio)

    await ruta.mark_ejercicio_completado(entrega.id, 1, body, user, _db(entrega))

    estado = (entrega.ejercicio_estados or [{}])[0]
    assert estado["completado"] is True
    assert estado["episode_id"] == str(episodio)
