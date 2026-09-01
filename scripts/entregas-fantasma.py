"""Encuentra —y opcionalmente destraba— a los alumnos atrapados por BUG-1.

QUE ES UNA ENTREGA FANTASMA
---------------------------

Una entrega en `draft` con TODOS sus ejercicios en `completado: true`.

El alumno la ve terminada: cinco tildes verdes, cinco "Completado". Aprieta
Entregar y recibe

    "Falta el codigo de los ejercicios: [2,3,4,5]. Abri cada ejercicio una vez
     antes de entregar."

Y no puede abrirlos: `canStart` no DESHABILITA el boton de un ejercicio
completado, no lo RENDERIZA. El sistema le exige lo unico que le hizo
imposible. La entrega queda en `draft`: el alumno cree que entrego, el docente
ve un casillero vacio, y ninguno de los dos tiene motivo para sospechar del
otro.

**Lo peor no es el bug: es que es silencioso.** Un alumno puede quedar asi sin
enterarse nunca, y del lado del docente se ve igual que no haber entregado. Por
eso hace falta buscarlas: no van a aparecer solas.

QUE HACE ESTE SCRIPT
--------------------

Por defecto SOLO LISTA. Con `--destrabar` des-marca los ejercicios de las
entregas que encuentra (`completado: false`), que es la accion C del reporte de
QA del 31/08: un PATCH por ejercicio, sin deploy.

Desde el fix del 31/08 el alumno tiene el boton "Volver a abrir" y puede
destrabarse solo, asi que `--destrabar` es para los que ya estaban adentro
ANTES del deploy — o para no hacerlos pasar por descubrir un boton nuevo.

Que NO toca:
  - el `episode_id` de cada estado, que apunta al episodio del intento anterior
    (cerrado y firmado) y es lo unico con lo que se puede recuperar el codigo
    viejo cuando no hay borrador local;
  - el CTR, que es append-only;
  - las entregas en `submitted`, `graded` o `returned` — esas ya salieron.

USO
---

    ACADEMIC_DB_URL=postgresql+asyncpg://... uv run python scripts/entregas-fantasma.py
    ... uv run python scripts/entregas-fantasma.py --destrabar
    ... uv run python scripts/entregas-fantasma.py --tenant <uuid>

Sin `--tenant` recorre todo, y para eso hace falta un usuario que no quede
atrapado por RLS. Con `--tenant` setea `app.current_tenant` y alcanza el
usuario normal de la app.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Sólo las entregas que el alumno todavía tiene en la mano. Una `submitted` o
# `graded` ya salió: destrabarla ahí sería reabrir algo que el docente puede
# estar corrigiendo en este momento.
_ESTADO_ATRAPADO = "draft"


def es_fantasma(estados: list[dict[str, Any]] | None) -> bool:
    """Todos los ejercicios completados y la entrega sin enviar.

    La lista vacía NO cuenta: una entrega recién creada tiene
    `ejercicio_estados` sembrado o vacío, y `all([])` es True en Python. Sin
    este guard, el script reportaría como atrapadas a todas las entregas que
    el alumno ni empezó — que son la mayoría, y ahí el informe deja de servir.
    """
    if not estados:
        return False
    # `is True` y no truthiness: el string "false" es truthy en Python, y con
    # un dato corrupto de esa forma el script marcaria atrapado a alguien que
    # no lo esta — y `--destrabar` le des-marcaria ejercicios que si termino.
    # `completado` siempre nace como bool de Pydantic, asi que exigirlo exacto
    # no rechaza ningun dato legitimo.
    return all(e.get("completado") is True for e in estados)


async def _buscar(db: AsyncSession) -> list[dict[str, Any]]:
    filas = await db.execute(
        text(
            "SELECT e.id, e.tenant_id, e.student_pseudonym, e.comision_id, "
            "       e.tarea_practica_id, e.ejercicio_estados, e.updated_at, "
            "       tp.codigo AS tp_codigo, tp.titulo AS tp_titulo "
            "FROM entregas e "
            "LEFT JOIN tareas_practicas tp ON tp.id = e.tarea_practica_id "
            "WHERE e.estado = :estado "
            "ORDER BY e.updated_at DESC"
        ),
        {"estado": _ESTADO_ATRAPADO},
    )
    salida: list[dict[str, Any]] = []
    for fila in filas.mappings():
        estados = fila["ejercicio_estados"]
        # JSONB puede volver ya deserializado o como texto según el driver.
        if isinstance(estados, str):
            estados = json.loads(estados)
        if es_fantasma(estados):
            salida.append({**dict(fila), "ejercicio_estados": estados})
    return salida


async def _destrabar(db: AsyncSession, entrega_id: UUID, estados: list[dict[str, Any]]) -> None:
    """Des-marca los ejercicios, dejando todo lo demás como estaba.

    Se reescribe la lista entera en vez de un `jsonb_set` por ejercicio: es una
    sola escritura por entrega, y así no queda un estado a medio destrabar si
    la conexión se corta en el medio.
    """
    nuevos = [{**e, "completado": False, "completed_at": None} for e in estados]
    await db.execute(
        text("UPDATE entregas SET ejercicio_estados = CAST(:v AS jsonb) WHERE id = :id"),
        {"v": json.dumps(nuevos), "id": str(entrega_id)},
    )


async def main() -> int:
    destrabar = "--destrabar" in sys.argv
    tenant = None
    if "--tenant" in sys.argv:
        tenant = sys.argv[sys.argv.index("--tenant") + 1]

    dsn = os.environ.get("ACADEMIC_DB_URL")
    if not dsn:
        print("ERROR: falta ACADEMIC_DB_URL", file=sys.stderr)
        return 3

    engine = create_async_engine(dsn)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db:
        if tenant:
            await db.execute(
                text("SELECT set_config('app.current_tenant', :t, true)"), {"t": tenant}
            )
        atrapadas = await _buscar(db)

        print("=" * 74)
        print(f"ENTREGAS FANTASMA: {len(atrapadas)}")
        print("(en 'draft', con TODOS los ejercicios marcados como completados)")
        print("=" * 74)

        for e in atrapadas:
            n = len(e["ejercicio_estados"])
            print(f"\n  entrega    : {e['id']}")
            print(f"  alumno     : {e['student_pseudonym']}")
            print(f"  comision   : {e['comision_id']}")
            print(f"  TP         : {e['tp_codigo'] or '?'} - {e['tp_titulo'] or '?'}")
            print(f"  ejercicios : {n} completados, entrega sin enviar")
            print(f"  ultima act.: {e['updated_at']}")

        if destrabar and atrapadas:
            for e in atrapadas:
                await _destrabar(db, e["id"], e["ejercicio_estados"])
            await db.commit()
            print(f"\n  [OK] {len(atrapadas)} entregas destrabadas.")
            print("  Los alumnos van a ver los ejercicios pendientes y su boton de vuelta.")
            print("  El codigo que hayan escrito NO se toca: el episode_id sigue apuntando")
            print("  al episodio cerrado del intento anterior.")
        elif atrapadas:
            await db.rollback()
            print("\n  [DRY-RUN] No se escribio nada. Volve a correr con --destrabar.")
        else:
            print("\n  Ninguna. Nadie atrapado.")

    await engine.dispose()
    print("=" * 74)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
