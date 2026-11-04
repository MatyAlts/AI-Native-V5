"""sha256 canónico de una versión del codebook al congelarla (design D8).

Cubre texto, esquema y anclas. Cada ancla se serializa con EXACTAMENTE estos
campos (sin `item_id` ni ids internos, que son aleatorios) y la lista se ordena
por `(uso, orden, episode_id)`. Misma fórmula JSON canónica que el `self_hash`
del CTR: `sort_keys=True, ensure_ascii=False, separators=(",", ":")`, UTF-8.

Cambiar campos, orden o parámetros de serialización cambia el sha de toda
versión que se congele después: el literal de
`tests/unit/test_estudio_codebook.py` lo detecta.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

CAMPOS_ANCLA = (
    "uso",
    "orden",
    "episode_id",
    "respuesta_esperada",
    "explicacion_md",
    "consensuado_por",
    "seq_tope",
    "chain_hash_tope",
)


def _ancla_canonica(ancla: dict[str, Any]) -> dict[str, Any]:
    canonica = {campo: ancla[campo] for campo in CAMPOS_ANCLA}
    canonica["episode_id"] = str(canonica["episode_id"]).lower()
    return canonica


def sha256_codebook(
    contenido_md: str, esquema: dict[str, Any], anclas: list[dict[str, Any]]
) -> str:
    canonicas = sorted(
        (_ancla_canonica(a) for a in anclas),
        key=lambda a: (a["uso"], a["orden"], a["episode_id"]),
    )
    documento = {"contenido_md": contenido_md, "esquema": esquema, "anclas": canonicas}
    serializado = json.dumps(documento, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(serializado.encode("utf-8")).hexdigest()
