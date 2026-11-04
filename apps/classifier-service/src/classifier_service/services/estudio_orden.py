"""Orden de la muestra por codificador (design D7). Función PURA.

Posición de cada ítem: su rango, en orden ascendente del hex, de
`sha256((str(semilla) + ":" + item_id).encode("utf-8"))`, con `semilla` en
decimal sin relleno e `item_id` en la forma canónica de 36 caracteres en
minúsculas con guiones. No depende de `random` ni de la versión de Python:
se recomputa con cualquier herramienta que calcule sha256 (el método del
paper y el ADR copian este procedimiento).
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from uuid import UUID


def _canonico(item_id: str | UUID) -> str:
    return str(UUID(str(item_id)))


def orden_codificador(semilla: int, item_ids: Iterable[str | UUID]) -> list[tuple[str, int]]:
    """`[(item_id canónico, posición desde 1)]` ordenado por posición."""
    claves = [
        (hashlib.sha256(f"{semilla}:{_canonico(i)}".encode()).hexdigest(), _canonico(i))
        for i in item_ids
    ]
    return [(item_id, posicion) for posicion, (_, item_id) in enumerate(sorted(claves), start=1)]
