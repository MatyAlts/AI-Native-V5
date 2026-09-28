"""Tests de `_compute_distribucion` (pedagogia.py), la agregación de
`por_apropiacion` / `n_indeterminados` / `n_sin_clasificar` a partir de las
filas `current` de `classifications`.

B2b (6.4): `sin_clasificar` (el árbol corrió y no pudo decidir un eje, B2b)
es un quinto valor real de `appropriation` desde 6.2. Antes de este fix caía
en `n_indeterminados` — rama que hoy el bloque de arriba (`if r.appropriation
in _ORDINAL`) deja "muerta" para cualquier valor fuera del continuo y de
`_APROPIACION_ORTOGONAL` ({"autonomo"}). `PedagogiaPage.tsx` describe
`n_indeterminados` como "sin perfil asignable" — descripción falsa para
`sin_clasificar`: el árbol SÍ asignó un perfil (dijo explícitamente que no
pudo decidir), no es que falte señal.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from analytics_service.routes.pedagogia import _compute_distribucion


@dataclass
class FakeClsRow:
    episode_id: object
    appropriation: str
    features: object = None


def test_sin_clasificar_tiene_bucket_propio_y_no_cuenta_como_indeterminado() -> None:
    rows = [
        FakeClsRow(uuid4(), "sin_clasificar"),
        FakeClsRow(uuid4(), "sin_clasificar"),
        FakeClsRow(uuid4(), "apropiacion_reflexiva"),
    ]

    distribucion, appr_por_episodio = _compute_distribucion(rows)

    assert distribucion.n_sin_clasificar == 2
    assert distribucion.n_indeterminados == 0
    assert distribucion.por_apropiacion["sin_clasificar"] == 2
    assert len(appr_por_episodio) == 1  # solo la reflexiva entra al continuo ordinal


def test_valor_realmente_desconocido_sigue_cayendo_en_indeterminados() -> None:
    """Triangulación: un `appropriation` que NO es ninguno de los valores
    oficiales conocidos (ni continuo, ni `autonomo`, ni `sin_clasificar`)
    sigue cayendo en `n_indeterminados` — el fix es específico de
    `sin_clasificar`, no vacía la rama genérica de desincronización."""
    rows = [
        FakeClsRow(uuid4(), "un_eje_que_no_existe_todavia"),
        FakeClsRow(uuid4(), "autonomo"),
    ]

    distribucion, _ = _compute_distribucion(rows)

    assert distribucion.n_indeterminados == 1
    assert distribucion.n_sin_clasificar == 0
