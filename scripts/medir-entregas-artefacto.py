#!/usr/bin/env python3
"""Mide cuantas entregas del piloto se pueden corregir con artefacto.

Antes de conectar la correccion asistida hay que saber sobre que universo
opera. Una entrega solo es corregible si tiene el codigo que el alumno
entregO persistido. Este script cuenta las tres poblaciones:

    ENSAMBLABLE  entrega con artefactos persistidos, uno por ejercicio
                 esperado. Es la unica poblacion corregible.
    PARCIAL      tiene artefactos, pero menos que ejercicios espera la TP.
                 Se puede corregir lo que hay, nombrando lo que falta.
    MONOLITICA   TP sin `tp_ejercicios`: un solo bloque de codigo, sin
                 rubrica por ejercicio contra la cual corregir.
    LEGACY       anterior a la persistencia del artefacto. Su codigo no
                 existe: lo unico reconstruible es una lectura del CTR,
                 que no es lo que el alumno entregO.

Usar:
    ACADEMIC_DB_URL=postgresql+asyncpg://... python scripts/medir-entregas-artefacto.py

**Corre cross-tenant, con el owner de las tablas** (`postgres`), no con
`academic_user`. Es una medicion del piloto entero, asi que a proposito NO
setea `app.current_tenant`: con el usuario de la app la RLS lo dejaria ver
cero filas (o reventaria, segun la policy) y el resultado seria un cero
silencioso presentado como medicion. Un cero que no distingue "no hay" de
"no puedo ver" es peor que un error.

Exit code:
    0 = midio bien (aunque el numero sea malo: medir no es aprobar)
    2 = no se pudo conectar, o la query fallo (el mensaje distingue cual)
"""

from __future__ import annotations

import asyncio
import os
import sys

from sqlalchemy.ext.asyncio import create_async_engine

# ASCII a proposito: la consola de Windows (cp1252) rompe el encoding con
# caracteres no-ASCII y devuelve exit non-zero, tumbando gates de CI.
_QUERY = """
WITH esperados AS (
    SELECT tarea_practica_id, count(*) AS n_esperados
    FROM tp_ejercicios
    GROUP BY tarea_practica_id
),
persistidos AS (
    SELECT entrega_id, count(*) AS n_persistidos
    FROM entrega_artefactos
    GROUP BY entrega_id
)
SELECT
    e.id,
    e.estado,
    e.legacy,
    coalesce(sp.n_esperados, 0) AS n_esperados,
    coalesce(p.n_persistidos, 0) AS n_persistidos,
    (e.artefacto_sha256 IS NOT NULL) AS tiene_hash
FROM entregas e
LEFT JOIN esperados sp ON sp.tarea_practica_id = e.tarea_practica_id
LEFT JOIN persistidos p ON p.entrega_id = e.id
WHERE e.deleted_at IS NULL
"""


def clasificar(row: tuple) -> str:
    _id, _estado, legacy, n_esperados, n_persistidos, _hash = row
    if legacy:
        return "LEGACY"
    if n_esperados == 0:
        return "MONOLITICA"
    if n_persistidos == 0:
        return "SIN_ARTEFACTO"
    if n_persistidos < n_esperados:
        return "PARCIAL"
    return "ENSAMBLABLE"


async def main() -> int:
    dsn = os.environ.get("ACADEMIC_DB_URL")
    if not dsn:
        print("[FAIL] falta ACADEMIC_DB_URL")
        return 2

    engine = create_async_engine(dsn)
    try:
        async with engine.connect() as conn:
            # La conexion y la query se reportan por separado. Juntas, un error
            # de permisos de RLS salia como "no se pudo conectar" y mandaba a
            # revisar la red cuando el problema era el usuario.
            try:
                rows = (await conn.exec_driver_sql(_QUERY)).fetchall()
            except Exception as exc:
                print(f"[FAIL] conecte, pero la query fallo: {exc}")
                print(
                    "       Si menciona 'app.current_tenant' o un uuid vacio, "
                    "estas corriendo con el usuario de la app y la RLS te tapa. "
                    "Corre con el owner de las tablas."
                )
                return 2
    except Exception as exc:
        print(f"[FAIL] no se pudo conectar: {exc}")
        return 2
    finally:
        await engine.dispose()

    if not rows:
        print("[OK] no hay entregas para medir")
        return 0

    conteo: dict[str, int] = {}
    entregadas = 0
    for row in rows:
        conteo[clasificar(row)] = conteo.get(clasificar(row), 0) + 1
        if row[1] in ("submitted", "graded", "returned"):
            entregadas += 1

    total = len(rows)
    print(f"Entregas totales (no borradas): {total}")
    print(f"De ellas, ya enviadas:          {entregadas}")
    print("")
    for categoria in ("ENSAMBLABLE", "PARCIAL", "SIN_ARTEFACTO", "MONOLITICA", "LEGACY"):
        n = conteo.get(categoria, 0)
        pct = (n / total * 100) if total else 0.0
        print(f"  {categoria:<14} {n:>5}  ({pct:5.1f}%)")
    print("")
    corregibles = conteo.get("ENSAMBLABLE", 0)
    print(f"[OK] corregibles hoy con artefacto completo: {corregibles} de {total}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
