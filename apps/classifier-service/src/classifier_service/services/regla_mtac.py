"""Regla de decisión del codebook MTAC v1 (sección 4), con Kleene fuerte.

Es el ÚNICO lugar del código con la regla MTAC v1 (K02 de HU-001). La usa el
juez v2 (`juez_v2.py`) para decidir el régimen a partir de las dimensiones que
propone el modelo: el régimen lo decide esta función, no el LLM.

    reflexiva = D1 ∧ (D2 ∨ D3) ∧ D4 = interlocutor
    pasiva    = D4 = transferencia ∧ ¬(D1 ∨ D2 ∨ D3)
    superficial si las dos son falsas.

`no_evaluable` es el desconocido de Kleene: se propaga SOLO cuando puede
cambiar el resultado. Si el desconocido decide, la regla devuelve
`INDETERMINADO` (el juez se abstiene; no se fuerza una categoría, §4.4 del
codebook).

No confundir con `regimen_llm.regimen_segun_regla` (juez v1, regla de la Tabla
3.11 de la tesis, sin pasiva): esa queda intacta y versionada con su prompt.
"""

from __future__ import annotations

from typing import Literal

ValorDim = Literal["presente", "ausente", "no_evaluable"]
ValorD4 = Literal["interlocutor", "oraculo", "transferencia", "no_evaluable"]
RegimenRegla = Literal["REFLEXIVA", "SUPERFICIAL", "PASIVA", "INDETERMINADO"]

_Tri = bool | None


def _tri(valor: str) -> _Tri:
    if valor == "presente":
        return True
    if valor == "ausente":
        return False
    if valor == "no_evaluable":
        return None
    raise ValueError(f"valor de dimensión fuera de dominio: {valor!r}")


def _y(*xs: _Tri) -> _Tri:
    """AND fuerte de Kleene: un False gana sobre cualquier desconocido."""
    if any(x is False for x in xs):
        return False
    if any(x is None for x in xs):
        return None
    return True


def _o(*xs: _Tri) -> _Tri:
    """OR fuerte de Kleene: un True gana sobre cualquier desconocido."""
    if any(x is True for x in xs):
        return True
    if any(x is None for x in xs):
        return None
    return False


def _no(x: _Tri) -> _Tri:
    return None if x is None else not x


def regimen_segun_regla_mtac(d1: str, d2: str, d3: str, d4: str) -> RegimenRegla:
    """Régimen que da la regla MTAC v1 sobre las cuatro dimensiones."""
    if d4 not in ("interlocutor", "oraculo", "transferencia", "no_evaluable"):
        raise ValueError(f"valor de D4 fuera de dominio: {d4!r}")
    v1, v2, v3 = _tri(d1), _tri(d2), _tri(d3)
    interlocutor: _Tri = None if d4 == "no_evaluable" else d4 == "interlocutor"
    transferencia: _Tri = None if d4 == "no_evaluable" else d4 == "transferencia"

    reflexiva = _y(v1, _o(v2, v3), interlocutor)
    pasiva = _y(transferencia, _no(_o(v1, v2, v3)))
    if reflexiva is True:
        return "REFLEXIVA"
    if pasiva is True:
        return "PASIVA"
    if reflexiva is False and pasiva is False:
        return "SUPERFICIAL"
    return "INDETERMINADO"
