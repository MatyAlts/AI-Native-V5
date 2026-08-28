"""Marca `depende_de_ejecucion` en los criterios de las rubricas (Active-IA §3.1).

Que es
------
Active-IA nos dio una garantia que pedimos: con `compila: false` no cierran
criterios del tipo "el programa funciona". La hicieron **deterministica en su
backend**, no como instruccion de prompt — y con razon: ponerlo en el prompt
seria repetir el bug 2 que les reportamos, donde la rubrica pedia 30% de
penalizacion y el motor aplico 0%. Una garantia declarativa no es una garantia.

Pero para que sea deterministica necesitan un dato que **solo la rubrica
tiene**: cual de los criterios necesita que el programa corra.

    "Produce la salida esperada"          -> depende_de_ejecucion: true
    "Uso la interfaz y no los concretos"  -> depende_de_ejecucion: false

Es opcional y por defecto va en falso. Si no viene, la garantia NO aplica.

Por que en dos fases
--------------------
Esto escribe sobre las rubricas de PRODUCCION, con las que se corrigen entregas
de ~87 alumnos. Decidir que criterio depende de la ejecucion es un juicio
pedagogico sobre el texto de cada criterio, y una heuristica sobre castellano
es una adivinanza con buena presentacion. Marcar de mas es peor que no marcar:
un criterio de diseno marcado como dependiente se cierra en 0 cada vez que el
alumno no compila, y eso SI le baja la nota por algo que si hizo.

Entonces:

    1. `--proponer` lee las rubricas y escribe un YAML con **todos** los
       criterios, su texto completo y un valor propuesto. Nadie toca la base.
    2. Una persona revisa y corrige ese archivo. Es el paso que importa.
    3. `--aplicar` lee el archivo revisado y escribe SOLO lo que difiere.

Ejecucion
---------

    # Fase 1 — propone, no toca nada
    ACADEMIC_DB_URL=postgresql+asyncpg://postgres:postgres@HOST:5432/academic_main \\
        python scripts/marcar-depende-de-ejecucion.py --proponer

    # (revisar scripts/data/depende-de-ejecucion.yaml a mano)

    # Fase 3 — escribe
    ACADEMIC_DB_URL=... python scripts/marcar-depende-de-ejecucion.py --aplicar

Idempotente: aplicar dos veces con el mismo archivo no escribe la segunda vez.

DESPUES DE APLICAR: hay que re-sincronizar los TPs
--------------------------------------------------
El campo viaja solo — `_payload_ejercicio` manda `ej["rubrica"]` verbatim, asi
que no hay que tocar el codigo del sync. Pero `hash_de_lo_enviado` cambia al
cambiar la rubrica, con lo cual los vinculos quedan marcados como
desactualizados y **hay que volver a sincronizar cada TP** desde el panel del
docente para que Active-IA reciba las marcas. Hasta que eso pase, la garantia
sigue sin aplicar.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any
from uuid import UUID

import yaml
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

ROOT = Path(__file__).parent.parent
ARCHIVO = ROOT / "scripts" / "data" / "depende-de-ejecucion.yaml"

TENANT_ID = UUID(os.environ.get("TENANT_ID", "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"))
DEFAULT_DB_URL = "postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/academic_main"

# Pistas para la PROPUESTA, no para la decision. Se eligieron pegadas al
# comportamiento observable —lo que solo se sabe corriendo el programa— y no a
# palabras que suenan tecnicas. Un criterio que menciona "metodo" puede ser de
# diseno o de funcionamiento; uno que dice "la salida" no.
_PISTAS_SI = (
    "salida esperada",
    "salida correcta",
    "produce la salida",
    "imprime",
    "muestra por pantalla",
    "resultado correcto",
    "funciona correctamente",
    "el programa funciona",
    "ejecuta sin errores",
    "casos de prueba",
    "pasa los tests",
    "calcula correctamente",
    "devuelve el valor",
)
# Gana sobre las de arriba: si un criterio habla de como esta escrito el codigo,
# no depende de que corra aunque mencione un resultado.
_PISTAS_NO = (
    "encapsulamiento",
    "interfaz",
    "herencia",
    "polimorfismo",
    "nombres",
    "nomenclatura",
    "indentacion",
    "comentarios",
    "documenta",
    "legibilidad",
    "estilo",
    "modulariza",
    "responsabilidad",
    "excepcion verificada",
)


def _proponer(texto: str) -> bool:
    """El valor SUGERIDO. No es la respuesta, es el borrador de la respuesta."""
    bajo = texto.lower()
    if any(p in bajo for p in _PISTAS_NO):
        return False
    return any(p in bajo for p in _PISTAS_SI)


async def _set_tenant(session: AsyncSession, tenant_id: UUID) -> None:
    """RLS: setea el tenant actual de la sesion."""
    await session.execute(
        text("SELECT set_config('app.current_tenant', :t, true)"),
        {"t": str(tenant_id)},
    )


async def _ejercicios_con_rubrica(session: AsyncSession) -> list[dict[str, Any]]:
    """Los ejercicios que tienen rubrica, con su TP si esta asociado.

    Se leen TODOS los que tienen rubrica y no solo los de Java: el campo aplica
    a cualquier criterio de funcionamiento, y limitar la lectura a un lenguaje
    dejaria a los de Python con la garantia apagada sin que nadie lo note.
    """
    filas = await session.execute(
        text(
            "SELECT e.id, e.titulo, e.rubrica, "
            "       COALESCE(MAX(tp.tarea_practica_id::text), '') AS tp_id "
            "FROM ejercicios e "
            "LEFT JOIN tp_ejercicios tp ON tp.ejercicio_id = e.id "
            "WHERE e.rubrica IS NOT NULL "
            "GROUP BY e.id, e.titulo, e.rubrica "
            "ORDER BY e.titulo"
        )
    )
    salida = []
    for fila in filas.all():
        rubrica = fila[2]
        if isinstance(rubrica, str):
            rubrica = json.loads(rubrica)
        criterios = (rubrica or {}).get("criterios")
        if not isinstance(criterios, list) or not criterios:
            continue
        salida.append({"id": str(fila[0]), "titulo": fila[1], "rubrica": rubrica, "tp_id": fila[3]})
    return salida


async def proponer(db_url: str) -> int:
    engine = create_async_engine(db_url, pool_size=2)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with Session() as session:
            await _set_tenant(session, TENANT_ID)
            ejercicios = await _ejercicios_con_rubrica(session)
    finally:
        await engine.dispose()

    if not ejercicios:
        print("[FAIL] No hay ejercicios con rubrica en este tenant. Nada que proponer.")
        return 1

    doc: dict[str, Any] = {
        "_lea_esto": (
            "Valor propuesto por heuristica. REVISAR CADA UNO. "
            "true = el criterio necesita que el programa corra para poder juzgarse. "
            "Marcar de mas le baja la nota al alumno por algo que si hizo."
        ),
        "tenant_id": str(TENANT_ID),
        "ejercicios": [],
    }
    total = 0
    propuestos_si = 0
    for e in ejercicios:
        criterios = []
        for c in e["rubrica"]["criterios"]:
            if not isinstance(c, dict):
                continue
            texto = " ".join(
                str(c.get(k, "")) for k in ("nombre", "descripcion", "criterio") if c.get(k)
            )
            sugerido = _proponer(texto)
            total += 1
            propuestos_si += int(sugerido)
            criterios.append(
                {
                    "nombre": str(c.get("nombre") or c.get("criterio") or ""),
                    "descripcion": str(c.get("descripcion") or "")[:300],
                    "puntaje_max": c.get("puntaje_max"),
                    "actual": c.get("depende_de_ejecucion"),
                    "depende_de_ejecucion": sugerido,
                }
            )
        doc["ejercicios"].append(
            {"id": e["id"], "titulo": e["titulo"], "tp_id": e["tp_id"], "criterios": criterios}
        )

    ARCHIVO.parent.mkdir(parents=True, exist_ok=True)
    ARCHIVO.write_text(
        yaml.safe_dump(doc, allow_unicode=True, sort_keys=False, width=100), encoding="utf-8"
    )
    print(f"[OK] {len(ejercicios)} ejercicios, {total} criterios -> {ARCHIVO}")
    print(f"[OK] Propuestos como dependientes de ejecucion: {propuestos_si}/{total}")
    print("[SIGUIENTE] Revisa el archivo A MANO. La heuristica propone, no decide.")
    return 0


def _marcar_rubrica(
    rubrica: dict[str, Any], querido: dict[str, bool], titulo: str
) -> tuple[bool, int, list[str]]:
    """Aplica el archivo revisado a UNA rubrica en memoria.

    Devuelve `(cambio, cuantos_quedaron_en_true, criterios_sin_match)`.

    Se empareja por NOMBRE dentro del ejercicio, no por posicion: si alguien
    reordena los criterios entre el `--proponer` y el `--aplicar`, la posicion
    marca el criterio equivocado y nadie se entera hasta que una nota sale mal.
    """
    cambio = False
    en_true = 0
    sin_match: list[str] = []
    for c in rubrica.get("criterios", []):
        if not isinstance(c, dict):
            continue
        nombre = str(c.get("nombre") or c.get("criterio") or "")
        if nombre not in querido:
            sin_match.append(f"{titulo} :: {nombre}")
            continue
        nuevo = querido[nombre]
        if c.get("depende_de_ejecucion") == nuevo:
            continue  # idempotencia
        c["depende_de_ejecucion"] = nuevo
        en_true += int(nuevo)
        cambio = True
    return cambio, en_true, sin_match


async def aplicar(db_url: str) -> int:
    if not ARCHIVO.exists():
        print(f"[FAIL] No existe {ARCHIVO}. Corre --proponer primero y revisalo.")
        return 1

    doc = yaml.safe_load(ARCHIVO.read_text(encoding="utf-8"))
    por_ejercicio = {e["id"]: e for e in doc.get("ejercicios", [])}
    if not por_ejercicio:
        print("[FAIL] El archivo no tiene ejercicios.")
        return 1

    engine = create_async_engine(db_url, pool_size=2)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    tocados = 0
    criterios_marcados = 0
    sin_match: list[str] = []

    try:
        async with Session() as session:
            await _set_tenant(session, TENANT_ID)
            for e in await _ejercicios_con_rubrica(session):
                deseado = por_ejercicio.get(e["id"])
                if deseado is None:
                    continue
                querido = {
                    str(c.get("nombre", "")): bool(c.get("depende_de_ejecucion"))
                    for c in deseado.get("criterios", [])
                }
                rubrica = e["rubrica"]
                cambio, en_true, huerfanos = _marcar_rubrica(rubrica, querido, e["titulo"])
                criterios_marcados += en_true
                sin_match.extend(huerfanos)

                if not cambio:
                    continue
                await session.execute(
                    text("UPDATE ejercicios SET rubrica = CAST(:r AS jsonb) WHERE id = :i"),
                    {"r": json.dumps(rubrica, ensure_ascii=False), "i": e["id"]},
                )
                tocados += 1
            await session.commit()
    finally:
        await engine.dispose()

    print(f"[OK] Ejercicios actualizados: {tocados}")
    print(f"[OK] Criterios que quedaron en true: {criterios_marcados}")
    if sin_match:
        # Silenciarlos dejaria criterios sin marcar creyendo que se marcaron.
        print(f"[WARN] {len(sin_match)} criterios del banco no figuran en el archivo:")
        for s in sin_match[:10]:
            print(f"        - {s}")
    if tocados:
        print(
            "[SIGUIENTE] Re-sincronizar cada TP desde el panel del docente: cambio la\n"
            "            rubrica, cambio su hash, y hasta que Active-IA no la reciba\n"
            "            de nuevo la garantia de `compila: false` NO aplica."
        )
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    grupo = p.add_mutually_exclusive_group(required=True)
    grupo.add_argument("--proponer", action="store_true", help="lee la base y escribe el YAML")
    grupo.add_argument("--aplicar", action="store_true", help="escribe el YAML revisado a la base")
    args = p.parse_args()

    db_url = os.environ.get("ACADEMIC_DB_URL", DEFAULT_DB_URL)
    if args.proponer:
        return asyncio.run(proponer(db_url))
    return asyncio.run(aplicar(db_url))


if __name__ == "__main__":
    sys.exit(main())
