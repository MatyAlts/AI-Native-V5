"""Aceptacion HU-031 (orquestador, antes de construir; el constructor no la
modifica).

N03  Los diagramas no agregan eventos al CTR ni tocan el prompt del tutor:
     mirar un diagrama no es una accion que el estudio mida (por ahora). Si
     algun dia se mide, es otra historia con su decision sobre la traza ciega.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[3]

# Huella de los contratos de eventos en la base de HU-031 (feat/hu-030-pseint, ad4e280).
HUELLA_EVENTOS = "97de18d9aa16b90a531c946cb6644016152d51a84aa33cef4d55c7844952acd7"
# Huella de `ai-native-prompts/prompts/tutor/` (la misma que fija HU-030).
HUELLA_PROMPTS_TUTOR = "cbc856dc08142a6c65895e8cbd52424b15a6d546f7b7bd0ee596fe72c131acbe"


def test_n03_los_eventos_del_ctr_no_cambian() -> None:
    eventos = RAIZ / "packages/contracts/src/platform_contracts/ctr/events.py"
    assert hashlib.sha256(eventos.read_bytes()).hexdigest() == HUELLA_EVENTOS


def test_n03_prompts_del_tutor_intactos() -> None:
    base = RAIZ / "ai-native-prompts" / "prompts" / "tutor"
    h = hashlib.sha256()
    for p in sorted(base.rglob("*")):
        if p.is_file():
            h.update(str(p.relative_to(base)).encode())
            h.update(b"\0")
            h.update(p.read_bytes())
            h.update(b"\0")
    assert h.hexdigest() == HUELLA_PROMPTS_TUTOR
