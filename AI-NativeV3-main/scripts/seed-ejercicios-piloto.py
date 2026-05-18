"""Seed del banco de ejercicios PID-UTN al tenant demo (ADR-047 + ADR-048).

Lee `scripts/data/ejercicios-piloto.yaml` y carga los 25 ejercicios
canonicos del PID Linea 5 al banco standalone del tenant
`aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa`. Idempotente: skipea ejercicios
que ya existen (match por `titulo + unidad_tematica`).

Fuentes originales:
  - b1.docx — TP1 Estructuras Secuenciales (10 ejercicios)
  - condi.docx — TP2 Estructuras Condicionales (10 ejercicios)
  - mixtos.docx — TP Integrador (5 ejercicios)

Total: 25 ejercicios canonicos del piloto UNSL.

Ejecucion
---------

    python scripts/seed-ejercicios-piloto.py

Con env var custom:

    ACADEMIC_DB_URL=postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/academic_main \\
        python scripts/seed-ejercicios-piloto.py

Precondiciones
--------------
- Migracion `20260514_0001_ejercicio_primera_clase` aplicada (tabla
  `ejercicios` debe existir con todas las columnas pedagogicas JSONB).
- Tenant demo `aaaaaaaa-...` existe en la DB (creado por
  `seed-3-comisiones.py` o `seed-demo-data.py`). Este script NO crea
  el tenant — solo inserta ejercicios bajo el RLS del tenant existente.

NO destructivo
--------------
Este script es ADITIVO. NO borra ejercicios existentes. Re-correrlo es
seguro: cada ejercicio se busca por (tenant, titulo, unidad_tematica) y
se skipea si ya existe. Si querer regenerar el banco desde cero, borrar
manualmente la tabla `ejercicios` del tenant antes de re-correr.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from uuid import UUID, uuid4

import yaml
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

ROOT = Path(__file__).parent.parent
DATA_FILE = ROOT / "scripts" / "data" / "ejercicios-piloto.yaml"

# Mismo tenant del demo y de seed-3-comisiones.py
TENANT_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
# Mismo docente service-account que los demas seeds
DOCENTE_USER_ID = UUID("11111111-1111-1111-1111-111111111111")

DEFAULT_DB_URL = (
    "postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/academic_main"
)


async def _set_tenant(session: AsyncSession, tenant_id: UUID) -> None:
    """RLS: setea el tenant actual de la sesion."""
    await session.execute(
        text("SELECT set_config('app.current_tenant', :t, true)"),
        {"t": str(tenant_id)},
    )


def _load_ejercicios() -> list[dict]:
    """Lee y valida el YAML estructurado."""
    if not DATA_FILE.exists():
        print(f"[ERROR] No encontre {DATA_FILE}")
        print(
            "        Debe existir antes de correr este seed. Pedile al doctorando "
            "que provea el archivo o regeneralo via el sub-agente de extraccion."
        )
        sys.exit(1)
    with DATA_FILE.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict) or "ejercicios" not in data:
        raise SystemExit(
            f"[ERROR] {DATA_FILE} debe tener clave de nivel superior 'ejercicios: [...]'"
        )
    ejercicios = data["ejercicios"]
    if not isinstance(ejercicios, list):
        raise SystemExit("[ERROR] 'ejercicios' debe ser una lista")
    return ejercicios


def _normalize(ejercicio: dict) -> dict:
    """Aplica defaults para campos opcionales que el YAML puede omitir."""
    return {
        "titulo": ejercicio["titulo"],
        "enunciado_md": ejercicio["enunciado_md"],
        "inicial_codigo": ejercicio.get("inicial_codigo"),
        "unidad_tematica": ejercicio["unidad_tematica"],
        "dificultad": ejercicio.get("dificultad"),
        "prerequisitos": ejercicio.get(
            "prerequisitos", {"sintacticos": [], "conceptuales": []}
        ),
        "test_cases": ejercicio.get("test_cases", []),
        "rubrica": ejercicio.get("rubrica"),
        "tutor_rules": ejercicio.get("tutor_rules"),
        "banco_preguntas": ejercicio.get("banco_preguntas"),
        "misconceptions": ejercicio.get("misconceptions", []),
        "respuesta_pista": ejercicio.get("respuesta_pista", []),
        "heuristica_cierre": ejercicio.get("heuristica_cierre"),
        "anti_patrones": ejercicio.get("anti_patrones", []),
    }


async def _exists(
    session: AsyncSession, titulo: str, unidad: str
) -> bool:
    """Match idempotente: skipea si ya hay un ejercicio con mismo (titulo, unidad)."""
    result = await session.execute(
        text(
            "SELECT 1 FROM ejercicios "
            "WHERE tenant_id = :tid AND titulo = :t AND unidad_tematica = :u "
            "AND deleted_at IS NULL LIMIT 1"
        ),
        {"tid": str(TENANT_ID), "t": titulo, "u": unidad},
    )
    return result.scalar_one_or_none() is not None


async def _insert(session: AsyncSession, e: dict) -> None:
    """INSERT directo via SQL (mas defensivo que pasar por el modelo SQLAlchemy)."""
    ej_id = uuid4()
    await session.execute(
        text(
            """
            INSERT INTO ejercicios (
                id, tenant_id, titulo, enunciado_md, inicial_codigo,
                unidad_tematica, dificultad, prerequisitos,
                test_cases, rubrica,
                tutor_rules, banco_preguntas, misconceptions,
                respuesta_pista, heuristica_cierre, anti_patrones,
                created_by, created_via_ai
            ) VALUES (
                :id, :tid, :titulo, :enunciado, :codigo,
                :unidad, :dif, CAST(:prereq AS jsonb),
                CAST(:tests AS jsonb), CAST(:rubrica AS jsonb),
                CAST(:rules AS jsonb), CAST(:banco AS jsonb), CAST(:misc AS jsonb),
                CAST(:pista AS jsonb), CAST(:cierre AS jsonb), CAST(:anti AS jsonb),
                :cb, false
            )
            """
        ),
        {
            "id": str(ej_id),
            "tid": str(TENANT_ID),
            "titulo": e["titulo"],
            "enunciado": e["enunciado_md"],
            "codigo": e["inicial_codigo"],
            "unidad": e["unidad_tematica"],
            "dif": e["dificultad"],
            "prereq": json.dumps(e["prerequisitos"], ensure_ascii=False),
            "tests": json.dumps(e["test_cases"], ensure_ascii=False),
            "rubrica": (
                json.dumps(e["rubrica"], ensure_ascii=False)
                if e["rubrica"] is not None
                else None
            ),
            "rules": (
                json.dumps(e["tutor_rules"], ensure_ascii=False)
                if e["tutor_rules"] is not None
                else None
            ),
            "banco": (
                json.dumps(e["banco_preguntas"], ensure_ascii=False)
                if e["banco_preguntas"] is not None
                else None
            ),
            "misc": json.dumps(e["misconceptions"], ensure_ascii=False),
            "pista": json.dumps(e["respuesta_pista"], ensure_ascii=False),
            "cierre": (
                json.dumps(e["heuristica_cierre"], ensure_ascii=False)
                if e["heuristica_cierre"] is not None
                else None
            ),
            "anti": json.dumps(e["anti_patrones"], ensure_ascii=False),
            "cb": str(DOCENTE_USER_ID),
        },
    )


async def seed() -> None:
    db_url = os.environ.get("ACADEMIC_DB_URL", DEFAULT_DB_URL)
    print(f"[INFO] Leyendo ejercicios desde {DATA_FILE}")
    raw_ejercicios = _load_ejercicios()
    ejercicios = [_normalize(e) for e in raw_ejercicios]
    print(f"[INFO] {len(ejercicios)} ejercicios a procesar")

    engine = create_async_engine(db_url, pool_size=2)
    Session = async_sessionmaker(engine, expire_on_commit=False)

    inserted = 0
    skipped = 0
    by_unidad: dict[str, int] = {}

    try:
        async with Session() as session:
            await _set_tenant(session, TENANT_ID)
            for e in ejercicios:
                already = await _exists(session, e["titulo"], e["unidad_tematica"])
                if already:
                    skipped += 1
                    continue
                await _insert(session, e)
                inserted += 1
                by_unidad[e["unidad_tematica"]] = (
                    by_unidad.get(e["unidad_tematica"], 0) + 1
                )
            await session.commit()
    finally:
        await engine.dispose()

    print(f"[OK] Insertados: {inserted}")
    print(f"[OK] Skipped (ya existian): {skipped}")
    if by_unidad:
        print("[OK] Por unidad tematica:")
        for unidad, count in sorted(by_unidad.items()):
            print(f"     - {unidad}: {count}")


if __name__ == "__main__":
    asyncio.run(seed())
