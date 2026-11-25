"""Desbloqueo secuencial de los ejercicios de un TP (HU-038).

Un ejercicio se puede abrir si todos los ejercicios QUE EXISTEN con `orden`
menor estan completados. Los numeros que no existen no cuentan: un TP con
ordenes 1, 2, 3, 101 deja abrir el 101 con el 1, el 2 y el 3 completos (antes
se exigia el `orden - 1`, que puede no existir, y el TP quedaba trabado).

Espejo de `estaBloqueado` del web-student (`apps/web-student/src/lib/
estaBloqueado.ts`). Funciones puras: `estados` es la lista `ejercicio_estados`
de la entrega (dicts con `orden` y `completado`).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any


def primer_anterior_sin_completar(
    ejercicio_orden: int, estados: Iterable[Mapping[str, Any]]
) -> int | None:
    """El menor `orden` anterior a `ejercicio_orden` que existe y no esta
    completado, o None si no hay ninguno."""
    pendientes = [
        e["orden"]
        for e in estados
        if isinstance(e.get("orden"), int)
        and e["orden"] < ejercicio_orden
        and not e.get("completado")
    ]
    return min(pendientes) if pendientes else None


def ejercicio_anterior_completado(
    ejercicio_orden: int, estados: Iterable[Mapping[str, Any]]
) -> bool:
    """True si todos los ejercicios que existen con orden menor estan
    completados (sin anteriores, True)."""
    return primer_anterior_sin_completar(ejercicio_orden, estados) is None
