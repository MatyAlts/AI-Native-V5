"""Seed minimal para deploy a VPS — Plataforma N4 UTN.

Que crea
--------
Estructura academica minima para que un docente y un alumno puedan loguear
y trabajar el dia 1 del piloto en el VPS:

    Universidad UTN
        Facultad Regional
            Carrera "Tecnicatura Universitaria en Programacion"
                Plan de estudio 2024
                    Materia "Programacion I" (PROG1)
                        Periodo {anio_actual}-S1
                            Comision "Comision 1" (COM-1)
                                Docente titular (1) — el que aparece logueado
                                Alumno inscripto (1) — el que aparece en student dashboard
                                5 Unidades tematicas
                                3 Templates de TP publicados + auto-instancias

UUIDs determinisicos namespace `d0d0d0d0-...` para no chocar con:
- seed-3-comisiones (b1/b2/b3-...)
- seed-utn-prog1-cohorte-30 (c1c1c1c1-...)
- otros seeds del repo

Sincronizacion con vite.config.ts del web-student y web-teacher
---------------------------------------------------------------
El web-student inyecta header `x-user-id` hardcoded en su proxy de dev. Para
que el alumno seedeado aparezca en pantalla, su pseudonym debe ser:
    d0d0d0d0-a100-a100-a100-d0d0d0a10001

El web-teacher hace lo mismo con un docente_admin. Su user_id es:
    d0d0d0d0-d0c1-d0c1-d0c1-d0d0d0d0c001

Cuando subas a VPS con Keycloak real, ya no inyectaras headers — el JWT
trae el sub. Pero estos UUIDs son los que devuelve el seed y debes
referenciarlos en Keycloak (o en el realm-export.json del piloto) como
los `sub` de los usuarios de demo.

Materiales (NO en este script)
------------------------------
Este seed no sube los PDF/DOCX de `documentos/` al RAG. Eso se hace
DESPUES de levantar el stack porque requiere el academic-service +
ai-gateway corriendo (embedder + storage). Ver:
    scripts/upload-utn-materiales.sh

Idempotencia
------------
Borra todo lo de UUID range `d0d0d0d0-...` antes de re-insertar. NO toca
otros tenants, otros seeds, ni la inscripcion del piloto real si existe.

Ejecucion
---------
    # Desde la raiz del repo, con el stack de infra arriba (postgres+redis):
    ACADEMIC_DB_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/academic_main \\
    uv run python scripts/seed-utn-vps.py
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine, AsyncSession

ROOT = Path(__file__).parent.parent

# ---------------------------------------------------------------------
# UUIDs determinisicos namespace d0d0d0d0- — VPS-deploy seed
# ---------------------------------------------------------------------

TENANT_ID = UUID("d0d0d0d0-0000-0000-0000-d0d0d0d00000")
UNIVERSIDAD_ID = TENANT_ID  # universidades.id == tenant_id
FACULTAD_ID = UUID("d0d0d0d0-fac0-fac0-fac0-d0d0d0d0fac0")
CARRERA_ID = UUID("d0d0d0d0-caaa-caaa-caaa-d0d0d0d0caaa")
PLAN_ID = UUID("d0d0d0d0-a1a0-a1a0-a1a0-d0d0d0d0a1a0")
MATERIA_ID = UUID("d0d0d0d0-aa01-aa01-aa01-d0d0d0d0aa01")
PERIODO_ID = UUID("d0d0d0d0-3eb0-3eb0-3eb0-d0d0d0d03eb0")
COMISION_ID = UUID("d0d0d0d0-c001-c001-c001-d0d0d0d0c001")

# Usuarios — referenciados por web-student/web-teacher vite.config.ts en dev
DOCENTE_USER_ID = UUID("d0d0d0d0-d0c1-d0c1-d0c1-d0d0d0d0c001")
ALUMNO_PSEUDONYM = UUID("d0d0d0d0-a100-a100-a100-d0d0d0a10001")

# Hashes deterministas — alineados al patron de los otros seeds
CURSO_CONFIG_HASH = hashlib.sha256(b"curso-config-utn-vps-v1").hexdigest()

# Unidades tematicas — orden visible en sidebar del estudiante
UNIDADES = [
    {"id": UUID("d0d0d0d0-0010-0010-0010-d0d0d0d00010"), "nombre": "Variables y Tipos", "orden": 1, "descripcion": "Tipos primitivos, mutabilidad, scope y pasaje por referencia en Python."},
    {"id": UUID("d0d0d0d0-0020-0020-0020-d0d0d0d00020"), "nombre": "Secuenciales", "orden": 2, "descripcion": "Operadores, expresiones y entrada/salida basica."},
    {"id": UUID("d0d0d0d0-0030-0030-0030-d0d0d0d00030"), "nombre": "Condicionales", "orden": 3, "descripcion": "Estructuras de decision: if/elif/else, operadores logicos."},
    {"id": UUID("d0d0d0d0-0040-0040-0040-d0d0d0d00040"), "nombre": "Repetitivas", "orden": 4, "descripcion": "for, while, control de iteracion (break, continue)."},
    {"id": UUID("d0d0d0d0-0050-0050-0050-d0d0d0d00050"), "nombre": "Funciones", "orden": 5, "descripcion": "Definicion, parametros, retorno, scope local vs global."},
]

# 3 TP templates publicados (uno por las primeras 3 unidades)
TEMPLATES = [
    {
        "id": UUID("d0d0d0d0-7001-7001-7001-d0d0d0d07001"),
        "unidad_id": UNIDADES[0]["id"],
        "codigo": "TP-VAR-01",
        "titulo": "Tipos primitivos",
        "consigna": (
            "Implementar una funcion `clasificar(x)` que reciba un valor y "
            "devuelva su tipo como string: `'int'`, `'float'`, `'str'`, "
            "`'bool'`, `'list'`, `'dict'`, `'none'` u `'otro'`.\n\n"
            "Test cases:\n"
            "- clasificar(42) => 'int'\n"
            "- clasificar(3.14) => 'float'\n"
            "- clasificar('hola') => 'str'\n"
            "- clasificar(True) => 'bool' (cuidado: bool es subclase de int)\n"
        ),
        "peso": 1.0,
    },
    {
        "id": UUID("d0d0d0d0-7002-7002-7002-d0d0d0d07002"),
        "unidad_id": UNIDADES[1]["id"],
        "codigo": "TP-SEQ-01",
        "titulo": "Datos del usuario",
        "consigna": (
            "Escribir un programa que pida al usuario su nombre, apellido, "
            "edad y lugar de residencia (`input()`) e imprima una oracion "
            "que combine los 4 datos.\n"
        ),
        "peso": 1.0,
    },
    {
        "id": UUID("d0d0d0d0-7003-7003-7003-d0d0d0d07003"),
        "unidad_id": UNIDADES[3]["id"],
        "codigo": "TP-REP-01",
        "titulo": "Suma de pares",
        "consigna": (
            "Escribir una funcion `suma_pares(n)` que reciba un entero "
            "positivo `n` y devuelva la suma de todos los numeros pares "
            "entre 0 y n (incluido n si es par).\n"
        ),
        "peso": 1.0,
    },
]


async def _set_tenant(session: AsyncSession, tenant_id: UUID) -> None:
    await session.execute(
        text("SELECT set_config('app.current_tenant', :t, true)"),
        {"t": str(tenant_id)},
    )


def _instance_id(template_id: UUID, comision_id: UUID) -> UUID:
    """Generar UUID deterministico para una instancia de TP en una comision."""
    raw = f"instance:{template_id}:{comision_id}".encode()
    digest = hashlib.sha256(raw).digest()[:16]
    return UUID(bytes=digest)


async def main() -> None:
    db_url = os.environ.get(
        "ACADEMIC_DB_URL",
        "postgresql+asyncpg://postgres:postgres@localhost:5432/academic_main",
    )
    engine = create_async_engine(db_url, echo=False)
    maker = async_sessionmaker(engine, expire_on_commit=False)

    today = date.today()
    now = datetime.now(UTC)

    print(f"[seed-utn-vps] target DB: {db_url.split('@')[-1]}")
    print(f"[seed-utn-vps] tenant_id={TENANT_ID}")

    async with maker() as session:
        # Borrar todo lo del namespace d0d0d0d0- (idempotente).
        # Orden FK-safe (mismo del seed-3-comisiones, ver comentario alli).
        for table in (
            "calificaciones",
            "entregas",
            "tareas_practicas",
            "tareas_practicas_templates",
            "unidades",
            "usuarios_comision",
            "inscripciones",
            "comisiones",
            "periodos",
            "materias",
            "planes_estudio",
            "carreras",
            "facultades",
        ):
            await session.execute(
                text(f"DELETE FROM {table} WHERE tenant_id = :t"),
                {"t": str(TENANT_ID)},
            )
        await session.execute(
            text("DELETE FROM universidades WHERE id = :u"),
            {"u": str(UNIVERSIDAD_ID)},
        )
        await session.commit()

    async with maker() as session:
        await _set_tenant(session, TENANT_ID)

        # Universidad (id == tenant_id en este modelo; columna NOT NULL).
        await session.execute(
            text(
                "INSERT INTO universidades (id, tenant_id, nombre, codigo, dominio_email, keycloak_realm, config) "
                "VALUES (:id, :t, :nombre, :codigo, :dominio, :realm, '{}'::jsonb)"
            ),
            {
                "id": str(UNIVERSIDAD_ID),
                "t": str(TENANT_ID),
                "nombre": "UTN",
                "codigo": "UTN-VPS",
                "dominio": "utn.edu.ar",
                "realm": "utn-vps",
            },
        )
        await session.execute(
            text(
                "INSERT INTO facultades (id, tenant_id, universidad_id, nombre, codigo) "
                "VALUES (:id, :t, :uni, :nombre, :codigo)"
            ),
            {
                "id": str(FACULTAD_ID),
                "t": str(TENANT_ID),
                "uni": str(UNIVERSIDAD_ID),
                "nombre": "Facultad Regional",
                "codigo": "FR",
            },
        )
        await session.execute(
            text(
                "INSERT INTO carreras (id, tenant_id, universidad_id, facultad_id, nombre, codigo) "
                "VALUES (:id, :t, :uni, :fac, :nombre, :codigo)"
            ),
            {
                "id": str(CARRERA_ID),
                "t": str(TENANT_ID),
                "uni": str(UNIVERSIDAD_ID),
                "fac": str(FACULTAD_ID),
                "nombre": "Tecnicatura Universitaria en Programacion",
                "codigo": "TUP",
            },
        )
        await session.execute(
            text(
                "INSERT INTO planes_estudio (id, tenant_id, carrera_id, version, año_inicio) "
                "VALUES (:id, :t, :car, :v, :anio)"
            ),
            {
                "id": str(PLAN_ID),
                "t": str(TENANT_ID),
                "car": str(CARRERA_ID),
                "v": "2024",
                "anio": 2024,
            },
        )
        await session.execute(
            text(
                "INSERT INTO materias (id, tenant_id, plan_id, nombre, codigo) "
                "VALUES (:id, :t, :p, :nombre, :codigo)"
            ),
            {
                "id": str(MATERIA_ID),
                "t": str(TENANT_ID),
                "p": str(PLAN_ID),
                "nombre": "Programacion I",
                "codigo": "PROG1",
            },
        )
        await session.execute(
            text(
                "INSERT INTO periodos (id, tenant_id, codigo, nombre, fecha_inicio, fecha_fin, estado) "
                "VALUES (:id, :t, :codigo, :nombre, :ini, :fin, 'abierto')"
            ),
            {
                "id": str(PERIODO_ID),
                "t": str(TENANT_ID),
                "codigo": f"{today.year}-S1",
                "nombre": f"Cuatrimestre {today.year}-S1",
                "ini": today - timedelta(days=30),
                "fin": today + timedelta(days=90),
            },
        )
        await session.execute(
            text(
                "INSERT INTO comisiones (id, tenant_id, materia_id, periodo_id, codigo, nombre, curso_config_hash) "
                "VALUES (:id, :t, :m, :p, :codigo, :nombre, :cch)"
            ),
            {
                "id": str(COMISION_ID),
                "t": str(TENANT_ID),
                "m": str(MATERIA_ID),
                "p": str(PERIODO_ID),
                "codigo": "COM-1",
                "nombre": "Comision 1",
                "cch": CURSO_CONFIG_HASH,
            },
        )

        # Docente titular de la comision
        await session.execute(
            text(
                "INSERT INTO usuarios_comision "
                "(tenant_id, comision_id, user_id, rol, fecha_desde) "
                "VALUES (:t, :c, :u, 'titular', :fd)"
            ),
            {
                "t": str(TENANT_ID),
                "c": str(COMISION_ID),
                "u": str(DOCENTE_USER_ID),
                "fd": today - timedelta(days=30),
            },
        )

        # Alumno inscripto
        await session.execute(
            text(
                "INSERT INTO inscripciones "
                "(tenant_id, comision_id, student_pseudonym, rol, estado, fecha_inscripcion) "
                "VALUES (:t, :c, :s, 'regular', 'cursando', :fi)"
            ),
            {
                "t": str(TENANT_ID),
                "c": str(COMISION_ID),
                "s": str(ALUMNO_PSEUDONYM),
                "fi": today - timedelta(days=20),
            },
        )

        # 5 Unidades tematicas (scope por comision, no por materia)
        for u in UNIDADES:
            await session.execute(
                text(
                    "INSERT INTO unidades (id, tenant_id, comision_id, nombre, descripcion, orden, created_by) "
                    "VALUES (:id, :t, :c, :nombre, :desc, :orden, :cb)"
                ),
                {
                    "id": str(u["id"]),
                    "t": str(TENANT_ID),
                    "c": str(COMISION_ID),
                    "nombre": u["nombre"],
                    "desc": u["descripcion"],
                    "orden": u["orden"],
                    "cb": str(DOCENTE_USER_ID),
                },
            )

        # 3 templates publicados + auto-instancias en la comision
        for tpl in TEMPLATES:
            await session.execute(
                text(
                    "INSERT INTO tareas_practicas_templates "
                    "(id, tenant_id, materia_id, periodo_id, codigo, titulo, "
                    " consigna, peso, estado, version, created_by) "
                    "VALUES (:id, :t, :m, :p, :codigo, :titulo, :consigna, :peso, "
                    " 'published', 1, :cb)"
                ),
                {
                    "id": str(tpl["id"]),
                    "t": str(TENANT_ID),
                    "m": str(MATERIA_ID),
                    "p": str(PERIODO_ID),
                    "codigo": tpl["codigo"],
                    "titulo": tpl["titulo"],
                    "consigna": tpl["consigna"],
                    "peso": tpl["peso"],
                    "cb": str(DOCENTE_USER_ID),
                },
            )

            # Instancia auto-derivada para esta comision
            instance_id = _instance_id(tpl["id"], COMISION_ID)
            await session.execute(
                text(
                    "INSERT INTO tareas_practicas "
                    "(id, tenant_id, comision_id, unidad_id, template_id, codigo, titulo, "
                    " enunciado, peso, estado, version, has_drift, created_by, fecha_inicio, fecha_fin) "
                    "VALUES (:id, :t, :c, :u, :tpl, :codigo, :titulo, :enunciado, :peso, "
                    " 'published', 1, false, :cb, :fi, :ff)"
                ),
                {
                    "id": str(instance_id),
                    "t": str(TENANT_ID),
                    "c": str(COMISION_ID),
                    "u": str(tpl["unidad_id"]),
                    "tpl": str(tpl["id"]),
                    "codigo": tpl["codigo"],
                    "titulo": tpl["titulo"],
                    "enunciado": tpl["consigna"],
                    "peso": tpl["peso"],
                    "cb": str(DOCENTE_USER_ID),
                    "fi": now - timedelta(days=10),
                    "ff": now + timedelta(days=30),
                },
            )

        await session.commit()

    await engine.dispose()

    print("")
    print("[seed-utn-vps] OK — estructura UTN creada:")
    print(f"  Universidad:  UTN ({UNIVERSIDAD_ID})")
    print(f"  Facultad:     Facultad Regional ({FACULTAD_ID})")
    print(f"  Materia:      Programacion I ({MATERIA_ID})")
    print(f"  Comision:     COM-1 ({COMISION_ID})")
    print(f"  Docente:      user_id={DOCENTE_USER_ID}")
    print(f"  Alumno:       pseudonym={ALUMNO_PSEUDONYM}")
    print(f"  Unidades:     {len(UNIDADES)} ({', '.join(u['nombre'] for u in UNIDADES)})")
    print(f"  TPs templates:{len(TEMPLATES)} publicados (cada uno auto-instanciado en la comision)")
    print("")
    print("Proximo paso para tener material en el RAG:")
    print("  bash scripts/upload-utn-materiales.sh")


if __name__ == "__main__":
    asyncio.run(main())
