"""Seed minimo de `academic_main` para el job `Unit tests` del CI.

Por que existe
--------------
El job levanta Postgres y corre `alembic upgrade head`, y ahi se planta: la
base queda **con esquema y sin una sola fila**. Los tests `*_db.py` del
evaluation-service y los `test_scope_comision_*` no piden "una base", piden
una base **sembrada**, y cuando no la encuentran se apagan solos:

    45  "El seed no tiene tareas_practicas en dos comisiones distintas"
    19  "la base no tiene comisiones sembradas"
    15  "la base no tiene entregas"
    12  "la base necesita dos comisiones sembradas para distinguirlas"
     9  "la base no tiene comisiones/ejercicios sembrados"
     5  "la base no tiene TPs/comisiones"
     3  "la base no tiene ejercicios con rubrica"
     2  "Sin seed de tareas_practicas/comisiones para las FKs"

Son 110 tests que el CI **colectaba y nunca ejecutaba**, entre ellos los 45 de
scope de comision que se agregaron al glob de `ci.yml` justamente porque "un
cambio de autorizacion entraba sin una sola verificacion automatica". El job
salia verde igual: un skip no rompe nada.

Este script siembra exactamente lo que esos skips piden, ni una fila mas.

Por que NO se reusa `seed-3-comisiones.py`
------------------------------------------
Ese seed cubre el plano academico que hace falta, pero ademas escribe en
`ctr_store` y `classifier_db` (episodios con cadena SHA-256 + classifications),
que el job de unit tests **no migra**: correrlo ahi implicaria dos `alembic
upgrade head` mas y ~94 episodios que ningun test de este job mira. Ademas es
DESTRUCTIVO sobre el tenant.

`seed-smoke.py` es aditivo pero crea **una sola** comision, y la mitad de los
skips de arriba piden dos para poder distinguir "propia" de "ajena".

Asi que este es el subconjunto academico de `seed-3-comisiones.py` — mismos
UUIDs canonicos de la jerarquia y de las comisiones A y B, para no inventar un
universo paralelo — mas lo unico que ningun seed del repo crea hoy: **entregas**.

Los ejercicios NO los crea este script: los pone `seed-ejercicios-piloto.py`
(25 ejercicios con `rubrica` y 47 test cases ocultos, que es lo que
`test_activeia_payload_db.py` verifica). El CI corre los dos, en ese orden.

Shape resultante (tenant aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa)
--------------------------------------------------------------
- 1 universidad / facultad / carrera / plan / materia / periodo
- 2 comisiones: A-Manana y B-Tarde (las mismas de `seed-3-comisiones.py`)
- 1 docente titular en A, 2 alumnos inscriptos (uno por comision)
- 2 tareas_practicas `published`, UNA POR COMISION — el `DISTINCT ON
  (tp.comision_id)` de `tests/conftest.py::_fetch_dos_comisiones` necesita
  filas en dos comisiones distintas del MISMO tenant
- 2 entregas `submitted`, una por comision

Idempotencia
------------
ADITIVO y re-corrible: todo va con `ON CONFLICT DO NOTHING`. NO borra nada, no
pisa otros tenants. Correrlo dos veces no duplica ni rompe.

Ejecucion
---------
    uv run python scripts/seed-ci-tests.py

    ACADEMIC_DB_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/academic_main \\
        uv run python scripts/seed-ci-tests.py

Ojo con el rol: las policies RLS de `academic_main` son FORCE, asi que un rol
NOBYPASSRLS solo ve lo que matchea `app.current_tenant`. El script setea el
tenant igual, pero en CI se conecta como `postgres` (superuser) como el resto
del job.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
from datetime import UTC, date, datetime, timedelta
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# ---------------------------------------------------------------------
# Constantes — compartidas con scripts/seed-3-comisiones.py a proposito.
# Si alguna cambia alla, cambiarla aca: son el mismo mundo, no dos.
# ---------------------------------------------------------------------

TENANT_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")

UNIVERSIDAD_ID = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
FACULTAD_ID = UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
CARRERA_ID = UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")
PLAN_ID = UUID("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee")
MATERIA_ID = UUID("ffffffff-ffff-ffff-ffff-ffffffffffff")
PERIODO_ID = UUID("12345678-1234-1234-1234-123456789abc")

DOCENTE_USER_ID = UUID("11111111-1111-1111-1111-111111111111")

COMISION_A = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")  # A-Manana
COMISION_B = UUID("bbbb0002-bbbb-bbbb-bbbb-bbbbbbbb0002")  # B-Tarde

ALUMNO_A = UUID("b1b1b1b1-0001-0001-0001-000000000001")
ALUMNO_B = UUID("b2b2b2b2-0001-0001-0001-000000000002")

# IDs propios (prefijo c1...) y `codigo` propio (TPCI-*): las TPs de este seed
# NO son las del demo. Si algun dia los dos seeds conviven en la misma base, el
# UNIQUE (tenant, comision, codigo, version) no choca.
TP_A_ID = UUID("c1c1c1c1-0001-0001-0001-000000000001")
TP_B_ID = UUID("c1c1c1c1-0002-0002-0002-000000000002")

ENTREGA_A_ID = UUID("c1c1c1c1-000a-000a-000a-00000000000a")
ENTREGA_B_ID = UUID("c1c1c1c1-000b-000b-000b-00000000000b")

CURSO_CONFIG_HASH = hashlib.sha256(b"curso-config-ci-v1").hexdigest()

DEFAULT_DB_URL = "postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/academic_main"

_ENUNCIADO = (
    "# TP del seed de CI\n\n"
    "Existe para que los tests de scope de comision, de entregas y de "
    "correccion tengan FKs reales contra las que insertar. No es material "
    "pedagogico.\n"
)


async def _set_tenant(session: AsyncSession) -> None:
    """RLS: fija el tenant de la sesion (no-op util bajo superuser)."""
    await session.execute(
        text("SELECT set_config('app.current_tenant', :t, true)"),
        {"t": str(TENANT_ID)},
    )


async def seed(db_url: str) -> None:
    engine = create_async_engine(db_url)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    hoy = date.today()

    try:
        async with maker() as s:
            await _set_tenant(s)

            await s.execute(
                text(
                    "INSERT INTO universidades "
                    "(id, tenant_id, nombre, codigo, dominio_email, keycloak_realm, config) "
                    "VALUES (:id, :t, 'UTN demo', 'UTN-DEMO', 'utn.edu.ar', 'demo_uni', "
                    "'{}'::jsonb) ON CONFLICT (id) DO NOTHING"
                ),
                {"id": str(UNIVERSIDAD_ID), "t": str(TENANT_ID)},
            )
            await s.execute(
                text(
                    "INSERT INTO facultades (id, tenant_id, universidad_id, nombre, codigo) "
                    "VALUES (:id, :t, :uni, 'FCFMyN demo', 'FCFMYN') "
                    "ON CONFLICT (id) DO NOTHING"
                ),
                {"id": str(FACULTAD_ID), "t": str(TENANT_ID), "uni": str(UNIVERSIDAD_ID)},
            )
            await s.execute(
                text(
                    "INSERT INTO carreras "
                    "(id, tenant_id, universidad_id, facultad_id, nombre, codigo) "
                    "VALUES (:id, :t, :uni, :fac, 'TSU IA', 'TSU-IA') "
                    "ON CONFLICT (id) DO NOTHING"
                ),
                {
                    "id": str(CARRERA_ID),
                    "t": str(TENANT_ID),
                    "uni": str(UNIVERSIDAD_ID),
                    "fac": str(FACULTAD_ID),
                },
            )
            await s.execute(
                text(
                    "INSERT INTO planes_estudio (id, tenant_id, carrera_id, version, año_inicio) "
                    "VALUES (:id, :t, :car, '2024', 2024) ON CONFLICT (id) DO NOTHING"
                ),
                {"id": str(PLAN_ID), "t": str(TENANT_ID), "car": str(CARRERA_ID)},
            )
            await s.execute(
                text(
                    "INSERT INTO materias (id, tenant_id, plan_id, nombre, codigo) "
                    "VALUES (:id, :t, :p, 'Programacion 1', 'PROG1') "
                    "ON CONFLICT (id) DO NOTHING"
                ),
                {"id": str(MATERIA_ID), "t": str(TENANT_ID), "p": str(PLAN_ID)},
            )
            await s.execute(
                text(
                    "INSERT INTO periodos "
                    "(id, tenant_id, codigo, nombre, fecha_inicio, fecha_fin, estado) "
                    "VALUES (:id, :t, :codigo, :nombre, :ini, :fin, 'abierto') "
                    "ON CONFLICT (id) DO NOTHING"
                ),
                {
                    "id": str(PERIODO_ID),
                    "t": str(TENANT_ID),
                    "codigo": f"{hoy.year}-S1",
                    "nombre": f"Cuatrimestre {hoy.year}-S1",
                    "ini": hoy - timedelta(days=60),
                    "fin": hoy + timedelta(days=60),
                },
            )

            # DOS comisiones. Es el punto entero del script: casi todos los
            # skips piden poder distinguir una comision "propia" de una "ajena".
            for comision_id, codigo, nombre in (
                (COMISION_A, "A", "A-Manana"),
                (COMISION_B, "B", "B-Tarde"),
            ):
                await s.execute(
                    text(
                        "INSERT INTO comisiones "
                        "(id, tenant_id, materia_id, periodo_id, codigo, nombre, "
                        "curso_config_hash) "
                        "VALUES (:id, :t, :m, :p, :codigo, :nombre, :cch) "
                        "ON CONFLICT (id) DO NOTHING"
                    ),
                    {
                        "id": str(comision_id),
                        "t": str(TENANT_ID),
                        "m": str(MATERIA_ID),
                        "p": str(PERIODO_ID),
                        "codigo": codigo,
                        "nombre": nombre,
                        "cch": CURSO_CONFIG_HASH,
                    },
                )

            # El docente es titular SOLO de A. Los tests de scope montan su
            # propia membresia efimera, pero varios endpoints leen esta.
            await s.execute(
                text(
                    "INSERT INTO usuarios_comision "
                    "(tenant_id, comision_id, user_id, rol, fecha_desde) "
                    "VALUES (:t, :c, :u, 'titular', :fd) "
                    "ON CONFLICT ON CONSTRAINT uq_usuario_comision DO NOTHING"
                ),
                {
                    "t": str(TENANT_ID),
                    "c": str(COMISION_A),
                    "u": str(DOCENTE_USER_ID),
                    "fd": hoy - timedelta(days=60),
                },
            )

            for comision_id, alumno in ((COMISION_A, ALUMNO_A), (COMISION_B, ALUMNO_B)):
                await s.execute(
                    text(
                        "INSERT INTO inscripciones "
                        "(tenant_id, comision_id, student_pseudonym, rol, estado, "
                        "fecha_inscripcion) "
                        "VALUES (:t, :c, :s, 'regular', 'cursando', :fi) "
                        "ON CONFLICT ON CONSTRAINT uq_inscripcion_student DO NOTHING"
                    ),
                    {
                        "t": str(TENANT_ID),
                        "c": str(comision_id),
                        "s": str(alumno),
                        "fi": hoy - timedelta(days=45),
                    },
                )

            fecha_inicio = datetime.combine(
                hoy - timedelta(days=15), datetime.min.time(), tzinfo=UTC
            )
            fecha_fin = datetime.combine(hoy + timedelta(days=30), datetime.min.time(), tzinfo=UTC)

            for tp_id, comision_id, codigo in (
                (TP_A_ID, COMISION_A, "TPCI-01"),
                (TP_B_ID, COMISION_B, "TPCI-02"),
            ):
                await s.execute(
                    text(
                        "INSERT INTO tareas_practicas ("
                        "id, tenant_id, comision_id, codigo, titulo, enunciado, peso, "
                        "fecha_inicio, fecha_fin, estado, version, created_by"
                        ") VALUES ("
                        ":id, :t, :c, :codigo, :titulo, :enunciado, 0.25, :fi, :ff, "
                        "'published', 1, :cb"
                        ") ON CONFLICT (id) DO NOTHING"
                    ),
                    {
                        "id": str(tp_id),
                        "t": str(TENANT_ID),
                        "c": str(comision_id),
                        "codigo": codigo,
                        "titulo": f"{codigo} - fixture del CI",
                        "enunciado": _ENUNCIADO,
                        "fi": fecha_inicio,
                        "ff": fecha_fin,
                        "cb": str(DOCENTE_USER_ID),
                    },
                )

            # Entregas: lo unico que ningun otro seed del repo crea, y lo que
            # apagaba los 15 tests de `test_correccion_ia_db.py`.
            for entrega_id, tp_id, comision_id, alumno in (
                (ENTREGA_A_ID, TP_A_ID, COMISION_A, ALUMNO_A),
                (ENTREGA_B_ID, TP_B_ID, COMISION_B, ALUMNO_B),
            ):
                await s.execute(
                    text(
                        "INSERT INTO entregas ("
                        "id, tenant_id, tarea_practica_id, student_pseudonym, comision_id, "
                        "estado, ejercicio_estados, submitted_at"
                        ") VALUES ("
                        ":id, :t, :tp, :s, :c, 'submitted', '[]'::jsonb, :sa"
                        ") ON CONFLICT (id) DO NOTHING"
                    ),
                    {
                        "id": str(entrega_id),
                        "t": str(TENANT_ID),
                        "tp": str(tp_id),
                        "s": str(alumno),
                        "c": str(comision_id),
                        "sa": datetime.now(UTC) - timedelta(days=1),
                    },
                )

            await s.commit()
    finally:
        await engine.dispose()


async def _verificar(db_url: str) -> None:
    """Fail-loud: si el seed no dejo lo que los tests piden, el CI tiene que
    enterarse ACA y no 110 skips despues, que es exactamente como llegamos a
    esta situacion."""
    engine = create_async_engine(db_url)
    try:
        async with engine.connect() as c:
            await c.execute(
                text("SELECT set_config('app.current_tenant', :t, true)"),
                {"t": str(TENANT_ID)},
            )
            comisiones = (
                await c.execute(
                    text("SELECT count(*) FROM comisiones WHERE tenant_id = :t"),
                    {"t": str(TENANT_ID)},
                )
            ).scalar_one()
            tps_en_comisiones_distintas = (
                await c.execute(
                    text(
                        "SELECT count(DISTINCT comision_id) FROM tareas_practicas "
                        "WHERE tenant_id = :t AND deleted_at IS NULL"
                    ),
                    {"t": str(TENANT_ID)},
                )
            ).scalar_one()
            entregas = (
                await c.execute(
                    text("SELECT count(*) FROM entregas WHERE tenant_id = :t"),
                    {"t": str(TENANT_ID)},
                )
            ).scalar_one()
    finally:
        await engine.dispose()

    problemas = []
    if comisiones < 2:
        problemas.append(f"comisiones={comisiones} (<2)")
    if tps_en_comisiones_distintas < 2:
        problemas.append(f"comisiones con TP={tps_en_comisiones_distintas} (<2)")
    if entregas < 1:
        problemas.append(f"entregas={entregas} (<1)")
    if problemas:
        raise SystemExit("[seed-ci] FAIL: " + ", ".join(problemas))

    print(
        f"[seed-ci] OK: comisiones={comisiones}, "
        f"comisiones con TP={tps_en_comisiones_distintas}, entregas={entregas}"
    )


async def main() -> None:
    db_url = os.environ.get("ACADEMIC_DB_URL", DEFAULT_DB_URL)
    print(f"[seed-ci] tenant   = {TENANT_ID}")
    print(f"[seed-ci] academic -> {db_url.split('@')[-1]}")
    await seed(db_url)
    await _verificar(db_url)


if __name__ == "__main__":
    asyncio.run(main())
