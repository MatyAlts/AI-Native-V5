"""F17: parity test entre los `event_type` declarados en Pydantic (Python)
y los declarados en la unión `CTREvent` (TypeScript / Zod).

Si alguien agrega un evento al Pydantic sin agregarlo al TS (o viceversa),
la unión Zod queda incompleta y un consumer TS que valide payloads contra
`CTREvent.parse(event)` rompe ante eventos reales.

Este test parsea el `index.ts` con regex (no ejecuta TS — sin dep de `tsx`)
y compara contra el set de `event_type` literales del Pydantic.
"""

from __future__ import annotations

import re
from pathlib import Path

from platform_contracts.ctr.events import (
    AnotacionCreada,
    CodigoEjecutado,
    EdicionCodigo,
    EpisodioAbandonado,
    EpisodioAbierto,
    EpisodioCerrado,
    IntentoAdversoDetectado,
    LecturaEnunciado,
    PromptEnviado,
    TutorRespondio,
)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_TS_INDEX = _REPO_ROOT / "packages" / "contracts" / "src" / "ctr" / "index.ts"


def _python_event_types() -> set[str]:
    classes = (
        EpisodioAbierto,
        EpisodioCerrado,
        EpisodioAbandonado,
        PromptEnviado,
        TutorRespondio,
        IntentoAdversoDetectado,
        LecturaEnunciado,
        AnotacionCreada,
        EdicionCodigo,
        CodigoEjecutado,
    )
    return {cls.model_fields["event_type"].default for cls in classes}


def _ts_event_types_in_union() -> set[str]:
    """Extrae los `event_type` literales declarados dentro de la unión CTREvent.

    Estrategia: detectar el bloque `z.discriminatedUnion("event_type", [...])`
    y capturar los nombres de los schemas listados; para cada uno extraer
    el `z.literal("...")` del propio schema en el archivo.
    """
    src = _TS_INDEX.read_text(encoding="utf-8")

    # 1. Bloque de la unión
    union_block = re.search(
        r'discriminatedUnion\("event_type",\s*\[([^\]]+)\]\)',
        src,
        flags=re.DOTALL,
    )
    assert union_block is not None, "No encuentro la unión CTREvent en el index.ts"
    schema_names = re.findall(r"\b([A-Z][A-Za-z0-9_]+)\b", union_block.group(1))

    # 2. Para cada schema, encontrar su declaración + el literal
    literals: set[str] = set()
    for name in schema_names:
        decl = re.search(
            rf"export const {re.escape(name)}\s*=\s*CTRBase\.extend\(\{{[^}}]*?"
            rf'event_type:\s*z\.literal\("([a-z_]+)"\)',
            src,
            flags=re.DOTALL,
        )
        if decl is None:
            continue  # un nombre que no es CTRBase.extend (ruido del split)
        literals.add(decl.group(1))
    return literals


def test_ts_index_file_exists() -> None:
    assert _TS_INDEX.exists(), f"index.ts no encontrado: {_TS_INDEX}"


def test_python_and_ts_event_types_match() -> None:
    py = _python_event_types()
    ts = _ts_event_types_in_union()

    missing_in_ts = py - ts
    missing_in_py = ts - py
    assert not missing_in_ts, (
        f"Eventos en Pydantic pero no en la unión TS Zod: {sorted(missing_in_ts)}. "
        "Agregalos a packages/contracts/src/ctr/index.ts y a CTREvent."
    )
    assert not missing_in_py, (
        f"Eventos en la unión TS pero no en Pydantic: {sorted(missing_in_py)}. "
        "Agregalos a packages/contracts/src/platform_contracts/ctr/events.py."
    )
