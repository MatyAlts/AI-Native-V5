"""Fixtures compartidas de los tests de entregas del evaluation-service.

`scope_setup` siembra el escenario minimo de BUG-10: un docente asignado a UNA
comision y entregas en esa comision y en otra ajena. Lo usan los tests del
scope de correccion (`test_scope_comision_*.py`) y los del estado de la
re-calificacion (`test_recalificar_estado.py`).

Pega contra el Postgres local (academic_main) como superuser `postgres`
(bypasa RLS). Los ids academicos (tenant, comisiones, tareas_practicas) salen
del seed real, no se inventan; solo los actores efimeros (docente / alumnos /
entregas) se crean por test y se limpian al final. La membresia del docente se
inserta con la misma forma que emite `scripts/seed-demo-data.py:363`
(`rol='titular'`, `fecha_desde`).

## Procedencia y la unica adaptacion

Estos tests vienen del PR #71 (`fix/calificacion-scope-comision`), que se cerro
sin mergear porque su codigo de produccion ya habia entrado a `main` por otro
camino: el guard de hoy es `_assert_comision_visible`, cableado en 8 endpoints.
Los tests se rescatan porque el CI ya los espera —`ci.yml` corre
`apps/*/tests/*.py` con un comentario que menciona "los ~40 tests de scope de
comision del evaluation-service", que hasta ahora no existian.

La adaptacion es UNA sola y esta centralizada en `rechazo_ajeno` (abajo): el
PR #71 devolvia **403 con un detalle que nombraba la comision**; `main` devuelve
**404 con el mismo texto que el not-found genuino**, a proposito. Un 403
confirma que la entrega existe, y ahi el `entrega_id` de una comision ajena se
vuelve un oraculo de existencia. La intencion original ("el docente ajeno no
llega") se conserva; la respuesta que se verifica es la mas fuerte de las dos.

## No-determinismo encontrado y corregido (2026-10-06)

`_fetch_dos_comisiones` tomaba *las primeras dos comisiones con TP que haya en
la base* sin filtrar por nada mas, y `scope_setup` sembraba la entrega con
`ejercicio_estados='[]'::jsonb` asumiendo, sin escribirlo en ningun lado, que
esa TP no tenia `tp_ejercicios`. Si la TP elegida SI tenia ejercicios
declarados, `submit_entrega` (`routes/entregas.py`) rechaza el submit por DOS
validaciones independientes y ninguna de las dos se arregla sembrando estados:

1. `incompletos` (linea ~335): exige que todo `ejercicio_estados` este
   `completado=True` — esto SI se puede simular sembrando el estado completo.
2. El chequeo de codigo (linea ~347): exige que el **body del POST /submit**
   traiga el codigo de cada ejercicio esperado (`body.artefactos`). Ninguno de
   los tests de este fixture manda body — llaman a `/submit` sin `json=` — asi
   que este chequeo rechaza SIEMPRE que `_ejercicios_esperados` no sea vacio,
   sin importar que tan completo este `ejercicio_estados`. Se intento primero
   el camino (1) solo y quedo demostrado en rojo que no alcanza (422 cambia de
   "Ejercicios incompletos" a "Falta el código de los ejercicios").

**La correccion real es otra: elegir TPs sin ejercicios, no simular que los
tienen completos.** Estos tests verifican el guard de autorizacion por
comision (`_assert_comision_visible`), NO la feature de completitud de
ejercicios — que la TP sorteada tuviera o no `tp_ejercicios` era un
confundidor ajeno a lo que el test declara probar, no cobertura real de nada.
`_fetch_dos_comisiones` ahora filtra con
`NOT EXISTS (SELECT 1 FROM tp_ejercicios ...)`, controlando esa variable en
vez de dejarla azarosa — asi el escenario es el mismo (una TP sin exigencia de
ejercicios) en cualquier entorno, determinista.

**Por que esto no se vio en CI antes de este fix.** El step "Seed minimo para
los tests con DB" de `.github/workflows/ci.yml` corre `scripts/seed-ci-tests.py`
+ `scripts/seed-ejercicios-piloto.py`. Ninguno de los dos inserta una sola fila
en `tp_ejercicios` (verificado con `grep -rn tp_ejercicios
scripts/seed-ci-tests.py scripts/seed-ejercicios-piloto.py` → cero matches):
`seed-ejercicios-piloto.py` carga un banco standalone de 25 ejercicios en la
tabla `ejercicios`, pero nunca los asocia a una TP via `tp_ejercicios`.
Entonces las TPs de CI siempre calificaban para el filtro por pura
coincidencia — nunca se habia notado que dependia de eso. Se detecto porque en
un Postgres de desarrollo local (con `seed-smoke.py` corrido alguna vez) la TP
"propia" que le tocaba a este fixture SI tenia 2 `tp_ejercicios`, y 5 tests
(`test_scope_comision_submit.py` x3, `test_recalificar_estado.py` x2) fallaban
con 422 en vez del 200 esperado.

**Agujero de cobertura que esto deja (a proposito, sin tapar — ver GAP-10 en
`docs/research/BUGS-PILOTO.md`)**: con el filtro, estos tests eligen a
proposito una TP SIN `tp_ejercicios`. Es lo correcto para lo que prueban (el
guard de comision no tiene nada que ver con ejercicios), pero significa que
"entrega/submit de una TP que SI exige ejercicios completos bajo un guard de
comision cruzado" queda sin cobertura tanto en CI (por el seed) como aca (por
el filtro, ahora explicito). Nadie ejercita esa combinacion hoy.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator
from datetime import date, timedelta

import pytest
from evaluation_service.auth import get_db
from evaluation_service.main import app
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

DB_URL = os.environ.get(
    "EVAL_TEST_DB_URL",
    "postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/academic_main",
)

# Docente asignado SOLO a la comision "propia". El leak de BUG-10 era que
# tambien podia escribir sobre la "ajena".
DOCENTE_ID = uuid.UUID("d0ced0ce-0001-0001-0001-000000000001")
# Oversight academico del tenant: escribe en cualquier comision a proposito.
ADMIN_ID = uuid.UUID("d0ced0ce-0002-0002-0002-000000000002")


def rechazo_ajeno(resp) -> None:
    """Asserta el rechazo que `_assert_comision_visible` produce HOY.

    404 y no 403, y con el detalle EXACTO del not-found genuino. Las dos mitades
    importan: el status para no confirmar existencia, y el texto para que el
    body no reabra el oraculo que el status cerro. `_get_or_404` repite ese
    mismo literal a proposito — el comentario de produccion dice "si se toca uno,
    se tocan los dos", y este assert es lo que lo hace cierto.

    Se expone via `scope_setup["rechazo_ajeno"]` porque `conftest` no es
    importable desde los modulos de test con `--import-mode=importlib` (no hay
    `__init__.py` en `tests/`, y agregarlo colapsaria los `test_health.py` de
    los 11 servicios en un mismo modulo — ver CLAUDE.md).
    """
    assert resp.status_code == 404, resp.text
    assert resp.json()["detail"] == "Entrega no existe", resp.text


def build_headers(user_id: uuid.UUID, tenant_id: uuid.UUID, roles: str) -> dict[str, str]:
    """Headers X-* que el api-gateway inyecta a los servicios internos."""
    return {
        "X-User-Id": str(user_id),
        "X-Tenant-Id": str(tenant_id),
        "X-User-Email": f"{user_id}@test.local",
        "X-User-Roles": roles,
    }


async def _fetch_dos_comisiones(engine) -> tuple[uuid.UUID, list[tuple[uuid.UUID, uuid.UUID]]]:
    """(tenant_id, [(tarea_practica_id, comision_id), ...]) de DOS comisiones del seed.

    Filtra TPs con `tp_ejercicios` propios: estos tests prueban el guard de
    comision (`_assert_comision_visible`), no la completitud de ejercicios, y
    `submit_entrega` exige codigo en el body para cada ejercicio esperado — algo
    que ningun test de `scope_setup` manda. Una TP con ejercicios declarados
    siempre rechaza el submit con 422, sin importar el guard. Ver "No-
    determinismo encontrado y corregido" en el docstring del modulo para el
    detalle completo (incluye por que esto no se notaba en CI y que agujero de
    cobertura deja este mismo filtro).
    """
    async with engine.connect() as conn:
        rows = (
            await conn.execute(
                text(
                    "SELECT DISTINCT ON (tp.comision_id) tp.tenant_id, tp.id, tp.comision_id "
                    "FROM tareas_practicas tp "
                    "WHERE tp.deleted_at IS NULL "
                    "AND NOT EXISTS ("
                    "    SELECT 1 FROM tp_ejercicios te "
                    "    WHERE te.tarea_practica_id = tp.id"
                    ") "
                    "ORDER BY tp.comision_id, tp.id"
                )
            )
        ).all()
    if len(rows) < 2:
        return (uuid.uuid4(), [])
    tenant_id = rows[0][0]
    del_mismo_tenant = [(r[1], r[2]) for r in rows if r[0] == tenant_id]
    return (tenant_id, del_mismo_tenant[:2])


@pytest.fixture
async def scope_setup() -> AsyncIterator[dict]:
    """Docente de la comision A + entregas en A (propia) y B (ajena).

    Entregas creadas (claves del dict devuelto):
      - `propia_draft`      (comision A, 'draft', sin calificacion)
      - `propia_submitted`  (comision A, 'submitted', sin calificacion)
      - `propia_returned`   (comision A, 'returned', con calificacion 5.00)
      - `ajena_submitted`   (comision B, 'submitted', sin calificacion)
      - `ajena_returned`    (comision B, 'returned', sin calificacion)
      - `ajena_graded`      (comision B, 'graded', con calificacion 5.00)

    Los estados `draft` y `returned` existen a proposito en las dos comisiones:
    son los unicos que `submit_entrega` y `mark_ejercicio_completado` aceptan,
    asi que sin ellos un guard de autorizacion no se distingue de un 409 de
    estado.

    `ejercicio_estados` nace `[]`: las TPs que `_fetch_dos_comisiones` elige
    estan filtradas para no tener `tp_ejercicios` (ver su docstring), asi que
    `[]` es siempre la lista completa — no hay ejercicio pendiente posible.

    Ademas: `tenant_id`, `docente` / `admin` (headers listos), `headers`
    (callable generico) y `alumno_de(key)` (headers del dueño de esa entrega).
    """
    engine = create_async_engine(DB_URL)
    try:
        tenant_id, pares = await _fetch_dos_comisiones(engine)
    except Exception as exc:  # DB no disponible
        await engine.dispose()
        pytest.skip(f"Postgres local no disponible: {exc}")

    if len(pares) < 2:
        await engine.dispose()
        # Mensaje DISTINTO del generico ("el seed no tiene tareas_practicas en
        # dos comisiones distintas"): ese mensaje manda a buscar donde no es
        # cuando el problema real es que las comisiones SI existen pero sus
        # TPs tienen `tp_ejercicios` enganchados (ver `_fetch_dos_comisiones`
        # y "No-determinismo encontrado y corregido" en el modulo).
        pytest.skip(
            "El seed no tiene dos comisiones con TPs SIN tp_ejercicios "
            "(scope_setup necesita TPs sin ejercicios declarados: estos tests "
            "prueban el guard de comision, no la completitud de ejercicios, y "
            "ninguno manda codigo en el body del submit)"
        )

    (tp_propia, comision_propia), (tp_ajena, comision_ajena) = pares
    membresia_id = uuid.uuid4()

    entregas = {
        "propia_draft": (tp_propia, comision_propia, "draft", None),
        "propia_submitted": (tp_propia, comision_propia, "submitted", None),
        "propia_returned": (tp_propia, comision_propia, "returned", uuid.uuid4()),
        "ajena_submitted": (tp_ajena, comision_ajena, "submitted", None),
        "ajena_returned": (tp_ajena, comision_ajena, "returned", None),
        "ajena_graded": (tp_ajena, comision_ajena, "graded", uuid.uuid4()),
    }
    ids = {k: uuid.uuid4() for k in entregas}
    # El alumno dueño de cada entrega, para poder actuar como el sin tener que
    # leerlo de vuelta por la API (leerlo con el docente ajeno es justo lo que
    # varios de estos tests prohiben).
    alumnos = {k: uuid.uuid4() for k in entregas}

    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def _set_tenant(s) -> None:
        await s.execute(
            text("SELECT set_config('app.current_tenant', :t, true)"),
            {"t": str(tenant_id)},
        )

    async with factory() as s:
        await _set_tenant(s)
        # Membresia del docente: SOLO la comision propia.
        await s.execute(
            text(
                "INSERT INTO usuarios_comision "
                "(id, tenant_id, comision_id, user_id, rol, fecha_desde) "
                "VALUES (:id, :t, :c, :u, 'titular', :fd)"
            ),
            {
                "id": str(membresia_id),
                "t": str(tenant_id),
                "c": str(comision_propia),
                "u": str(DOCENTE_ID),
                "fd": date.today() - timedelta(days=60),
            },
        )

        for key, (tp_id, comision_id, estado, cal_id) in entregas.items():
            await s.execute(
                text(
                    "INSERT INTO entregas (id, tenant_id, tarea_practica_id, "
                    "student_pseudonym, comision_id, estado, ejercicio_estados) "
                    "VALUES (:id, :t, :tp, :st, :c, :e, '[]'::jsonb)"
                ),
                {
                    "id": str(ids[key]),
                    "t": str(tenant_id),
                    "tp": str(tp_id),
                    "st": str(alumnos[key]),
                    "c": str(comision_id),
                    "e": estado,
                },
            )
            if cal_id is not None:
                await s.execute(
                    text(
                        "INSERT INTO calificaciones (id, tenant_id, entrega_id, "
                        "graded_by, nota_final, detalle_criterios) "
                        "VALUES (:id, :t, :e, :g, 5.00, '[]'::jsonb)"
                    ),
                    {
                        "id": str(cal_id),
                        "t": str(tenant_id),
                        "e": str(ids[key]),
                        "g": str(uuid.uuid4()),
                    },
                )
        await s.commit()

    async def _override_get_db() -> AsyncIterator:
        async with factory() as session:
            await _set_tenant(session)
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = _override_get_db

    try:
        yield {
            "tenant_id": tenant_id,
            "comision_propia": comision_propia,
            "comision_ajena": comision_ajena,
            # Las TPs de cada comision, para los guards que reciben el
            # `tarea_practica_id` directo en la URL en vez de una entrega
            # (`_assert_tp_de_mi_comision` en `routes/activeia.py`).
            "tp_propia": tp_propia,
            "tp_ajena": tp_ajena,
            "docente_id": DOCENTE_ID,
            "docente": build_headers(DOCENTE_ID, tenant_id, "docente"),
            # La MISMA identidad, con los roles que el gateway emite de verdad
            # (`clerk_base_roles = "estudiante,docente"`). Ver el docstring de
            # `tests/unit/test_scope_con_roles_de_produccion.py`: un test de
            # autorizacion con un usuario de UN solo rol no prueba nada en este
            # deploy.
            "docente_prod": build_headers(DOCENTE_ID, tenant_id, "estudiante,docente"),
            "admin": build_headers(ADMIN_ID, tenant_id, "docente_admin"),
            "headers": lambda uid, roles: build_headers(uid, tenant_id, roles),
            "rechazo_ajeno": rechazo_ajeno,
            # Headers del alumno dueño de la entrega `<key>`.
            "alumno_de": lambda key: build_headers(alumnos[key], tenant_id, "estudiante"),
            **ids,
        }
    finally:
        app.dependency_overrides.pop(get_db, None)
        async with factory() as s:
            await _set_tenant(s)
            for entrega_id in ids.values():
                await s.execute(
                    text("DELETE FROM calificaciones WHERE entrega_id = :e"),
                    {"e": str(entrega_id)},
                )
                await s.execute(text("DELETE FROM entregas WHERE id = :e"), {"e": str(entrega_id)})
            await s.execute(
                text("DELETE FROM usuarios_comision WHERE id = :id"),
                {"id": str(membresia_id)},
            )
            await s.commit()
        await engine.dispose()
