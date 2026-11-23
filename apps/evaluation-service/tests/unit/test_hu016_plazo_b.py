"""Aceptacion HU-016, ronda de arreglos (orquestador, antes de corregir; el
constructor no la modifica). Sale de la verificacion independiente del PR #147
(22/11). Juani: "vos terminas todo entonces".

R03  El 409 por plazo sale ANTES de cualquier escritura: ni `flush` ni
     cambios en `ejercicio_estados`. (La verificacion movio el chequeo despues
     de reescribir los estados y la aceptacion C03 siguio en verde.)
"""

from __future__ import annotations

import copy
import importlib.util
from pathlib import Path

import pytest
from evaluation_service.routes import entregas as ruta
from evaluation_service.schemas.entrega import ArtefactoItem, EntregaSubmitBody
from fastapi import HTTPException

_spec = importlib.util.spec_from_file_location(
    "hu016_plazo", Path(__file__).with_name("test_hu016_plazo.py")
)
assert _spec is not None and _spec.loader is not None
base = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(base)


async def test_r03_el_rechazo_por_plazo_no_escribe_nada(monkeypatch) -> None:
    entrega = base._entrega("draft")
    antes = copy.deepcopy(entrega.ejercicio_estados)

    async def _fecha_fin(db, tarea_practica_id):
        return base.PASADO

    monkeypatch.setattr(ruta, "_fecha_fin_de_la_tp", _fecha_fin)
    db = base._db(entrega)
    body = EntregaSubmitBody(artefactos=[ArtefactoItem(orden=1, ejercicio_id=base.EJ, codigo="x")])
    with pytest.raises(HTTPException) as exc:
        await ruta.submit_entrega(entrega.id, body, base._student(entrega), db)
    assert exc.value.status_code == 409
    db.flush.assert_not_awaited()
    db.add.assert_not_called()
    assert entrega.ejercicio_estados == antes
