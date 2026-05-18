"""Seed determinista con 3 comisiones en el tenant demo.

Para qué sirve
--------------
Extiende el demo original (`seed-demo-data.py`, que crea 1 comision con 6
estudiantes) a 3 comisiones dentro del MISMO tenant, con cohortes
diferenciadas para que el dashboard comparativo del web-teacher muestre
progresiones distintas.

Shape resultante
----------------
- 1 Universidad / Facultad / Carrera / Plan / Materia / Periodo
- 3 Comisiones (codigo A, B, C; nombre "A-Manana", "B-Tarde", "C-Noche")
  con 1 docente asignado a las tres
- 18 estudiantes (6 por comision, pseudonyms distintos)
- 2 plantillas de TP -> 6 instancias (3 comisiones x 2 templates)
- ~94 episodios CTR (cadena SHA-256 valida por episodio); cada episodio
  apunta a una de las 6 instancias reales via round-robin
- ~94 classifications append-only (is_current=true)

Cohortes
--------
- Comision A "Manana"  -> balanceada (como el demo original)
- Comision B "Tarde"   -> cohorte fuerte (mayor proporcion reflexiva)
- Comision C "Noche"   -> cohorte con dificultades (mas empeorando/superficial)

Idempotencia y precondiciones
-----------------------------
- DESTRUCTIVO sobre el tenant `aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa`:
  borra y rehace todas las filas de academic/ctr/classifier para ese
  tenant. NO toca otros tenants. Seguro de re-correr.
- Requiere la migracion `20260430_0001_comision_nombre` aplicada
  (columna `nombre` NOT NULL en `comisiones`). Si la migracion no esta
  aplicada, el INSERT falla por columna inexistente.
- Reconstruye los hashes CTR desde cero (genesis -> ultimo evento) en
  cada corrida — append-only se preserva porque borramos antes de
  insertar.
- Bumpear `PROMPT_SYSTEM_VERSION` (este archivo) en lockstep con
  `Settings.default_prompt_version` y `ai-native-prompts/manifest.yaml`.
  Hoy: v1.0.1; el `PROMPT_SYSTEM_HASH` es el sha256 declarado en
  `ai-native-prompts/prompts/tutor/v1.0.1/manifest.yaml`.

Ejecucion
---------
    python scripts/seed-3-comisiones.py

Con env vars custom:
    ACADEMIC_DB_URL=...  CTR_STORE_URL=...  CLASSIFIER_DB_URL=...  \
    python scripts/seed-3-comisiones.py
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import cast
from uuid import UUID

# Permitir imports de los servicios sin instalacion editable
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "apps" / "ctr-service" / "src"))
sys.path.insert(0, str(ROOT / "apps" / "classifier-service" / "src"))
sys.path.insert(0, str(ROOT / "apps" / "academic-service" / "src"))

# Hashing helpers del proyecto (source of truth, ADR-010)
from ctr_service.services.hashing import (
    GENESIS_HASH,
    compute_chain_hash,
    compute_self_hash,
)
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# ---------------------------------------------------------------------
# Constantes del piloto
# ---------------------------------------------------------------------

TENANT_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")

# Jerarquia academica compartida por las 3 comisiones
UNIVERSIDAD_ID = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
FACULTAD_ID = UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
CARRERA_ID = UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")
PLAN_ID = UUID("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee")
MATERIA_ID = UUID("ffffffff-ffff-ffff-ffff-ffffffffffff")
PERIODO_ID = UUID("12345678-1234-1234-1234-123456789abc")

DOCENTE_USER_ID = UUID("11111111-1111-1111-1111-111111111111")

# UUID del header `x-user-id` hardcoded en `apps/web-admin/vite.config.ts:43`
# para dev mode sin Keycloak. El web-admin loguea con roles
# `docente_admin,superadmin` (header `x-user-roles` en el mismo proxy hook),
# y Casbin resuelve permisos por rol, no por user_id — por eso este UUID NO
# se inserta en `inscripciones`/`usuarios_comision` (el web-admin gestiona el
# catalogo institucional, no es ni alumno ni docente de comision). Aparece
# aca como constante documentada para satisfacer el gate
# `scripts/check-vite-seed-sync.py` que sincroniza vite.config <-> seed.
WEB_ADMIN_USER_ID = UUID("33333333-3333-3333-3333-333333333333")

# SHA-256 de `ai-native-prompts/prompts/tutor/v1.0.1/system.md`, declarado
# en el manifest firmado del prompt (campo `files.system.md`). Si bumpas
# la version del prompt, actualiza ambas constantes en lockstep — el
# governance-service verifica fail-loud que sha256(system.md) == hash
# declarado, y el seed registra ese mismo hash en cada evento CTR para
# alinear con `Settings.default_prompt_version` del tutor-service (G12).
PROMPT_SYSTEM_VERSION = "v1.0.1"
PROMPT_SYSTEM_HASH = "2ecfcdddd29681b24539114975b601f9ec432560dc3c3a066980bb2e3d36187b"
CLASSIFIER_CONFIG_HASH = hashlib.sha256(b"classifier-config-demo-v1").hexdigest()
CURSO_CONFIG_HASH = hashlib.sha256(b"curso-config-demo-v1").hexdigest()

# ---------------------------------------------------------------------
# Plantillas de TP (ADR-016) — fuente canonica por (materia, periodo)
# ---------------------------------------------------------------------
# Cada plantilla se auto-instancia en las 3 comisiones al seedear.
# Los estudiantes de A, B, C reciben el MISMO enunciado (cero divergencia).
# Si un docente edita una instancia directamente, queda con has_drift=true.

TEMPLATE_01_ID = UUID("11110000-0000-0000-0000-000000000001")
TEMPLATE_02_ID = UUID("11110000-0000-0000-0000-000000000002")

# Estudiantes "narrativos" para defensa (ADR-042 path 1 reforzado): cada uno
# debe tener >=4 episodios apuntando al MISMO template_id para ejercitar el
# path longitudinal sin caer borderline contra MIN_EPISODES_FOR_LONGITUDINAL=3
# (RN-130). Default: A1, A2, A3 (los primeros 3 estudiantes de A-Manana, los
# mas predecibles del seed). El loop de seed_ctr garantiza el invariante
# inyectando `EXTRA_NARRATIVE_EPISODES` adicionales por (estudiante, template_01)
# antes del round-robin original.
NARRATIVE_STUDENTS_LONGITUDINAL: dict[UUID, int] = {
    UUID("b1b1b1b1-0001-0001-0001-000000000001"): 4,  # A1
    UUID("b1b1b1b1-0002-0002-0002-000000000002"): 4,  # A2
    UUID("b1b1b1b1-0003-0003-0003-000000000003"): 4,  # A3
}
# Template canonico para los episodios "narrativos" extra. TEMPLATE_01
# (recursion/Fibonacci) es el que se usa en la narrativa de defensa.
NARRATIVE_TEMPLATE_ID = TEMPLATE_01_ID

TEMPLATES_DEMO: list[dict[str, str | float | UUID]] = [
    {
        "id": TEMPLATE_01_ID,
        "codigo": "TP-01",
        "titulo": "Recursion y complejidad temporal",
        "enunciado": (
            "# TP-01 - Recursion y complejidad temporal\n\n"
            "## Objetivos\n"
            "1. Implementar la secuencia de Fibonacci en **dos variantes**: "
            "recursiva clasica e iterativa con acumulador.\n"
            "2. Medir empiricamente el tiempo de ejecucion para N = 10, 20, 30, 40.\n"
            "3. Proponer una tercera variante con **memoization** y justificar "
            "la mejora de complejidad de O(2^n) a O(n).\n\n"
            "## Entregable\n"
            "Un archivo `fibonacci.py` con las tres funciones + un script "
            "`benchmark.py` que imprima una tabla comparativa.\n\n"
            "## Criterios de evaluacion\n"
            "- Correccion (tests unitarios pasan): 40%\n"
            "- Analisis de complejidad escrito: 30%\n"
            "- Benchmark reproducible: 30%\n"
        ),
        "peso": 0.20,
    },
    {
        "id": TEMPLATE_02_ID,
        "codigo": "TP-02",
        "titulo": "Listas enlazadas simples",
        "enunciado": (
            "# TP-02 - Listas enlazadas simples\n\n"
            "## Objetivos\n"
            "Implementar una clase `LinkedList` con las operaciones:\n\n"
            "- `insert(value)` - al final, O(n)\n"
            "- `insert_head(value)` - al principio, O(1)\n"
            "- `delete(value)` - primera ocurrencia, O(n)\n"
            "- `reverse()` - in-place, O(n)\n"
            "- `__len__()` y `__iter__()`\n\n"
            "## Restricciones\n"
            "- Prohibido usar `list` o `collections.deque` por dentro.\n"
            "- Cada metodo debe tener docstring con la complejidad temporal.\n\n"
            "## Entregable\n"
            "`linked_list.py` + suite de tests con al menos 8 casos, "
            "incluyendo edge cases (lista vacia, un solo elemento, reverse de "
            "lista vacia).\n"
        ),
        "peso": 0.25,
    },
]

# ---------------------------------------------------------------------
# Configuracion de las 3 comisiones
# ---------------------------------------------------------------------
# Los pseudonyms se prefijan con b1/b2/b3 para no chocar con los del
# seed-demo-data.py original (que usa a1a1a1a1-...).
# La comision A mantiene el UUID clasico del demo para retro-compat.

COHORTES = [
    {
        "comision_id": UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        "codigo": "A",
        "nombre": "Manana",
        "students": [
            UUID("b1b1b1b1-0001-0001-0001-000000000001"),
            UUID("b1b1b1b1-0002-0002-0002-000000000002"),
            UUID("b1b1b1b1-0003-0003-0003-000000000003"),
            UUID("b1b1b1b1-0004-0004-0004-000000000004"),
            UUID("b1b1b1b1-0005-0005-0005-000000000005"),
            UUID("b1b1b1b1-0006-0006-0006-000000000006"),
        ],
        # Patron balanceado (identico al demo original)
        "patterns": [
            ["apropiacion_superficial"] * 2 + ["apropiacion_reflexiva"] * 4,
            ["delegacion_pasiva"] * 2
            + ["apropiacion_superficial"] * 2
            + ["apropiacion_reflexiva"] * 2,
            ["apropiacion_superficial"] * 5,
            ["apropiacion_reflexiva"] * 5,
            ["apropiacion_reflexiva"] * 3 + ["apropiacion_superficial"] * 3,
            ["apropiacion_superficial"] * 2,
        ],
    },
    {
        "comision_id": UUID("bbbb0002-bbbb-bbbb-bbbb-bbbbbbbb0002"),
        "codigo": "B",
        "nombre": "Tarde",
        "students": [
            UUID("b2b2b2b2-0001-0001-0001-000000000001"),
            UUID("b2b2b2b2-0002-0002-0002-000000000002"),
            UUID("b2b2b2b2-0003-0003-0003-000000000003"),
            UUID("b2b2b2b2-0004-0004-0004-000000000004"),
            UUID("b2b2b2b2-0005-0005-0005-000000000005"),
            UUID("b2b2b2b2-0006-0006-0006-000000000006"),
        ],
        # Cohorte fuerte: 4 reflexivas, 2 estables
        "patterns": [
            ["apropiacion_reflexiva"] * 6,
            ["apropiacion_superficial"] * 2 + ["apropiacion_reflexiva"] * 4,
            ["apropiacion_superficial"] * 1 + ["apropiacion_reflexiva"] * 5,
            ["apropiacion_reflexiva"] * 6,
            ["apropiacion_reflexiva"] * 4,
            ["apropiacion_superficial"] * 3 + ["apropiacion_reflexiva"] * 3,
        ],
    },
    {
        "comision_id": UUID("cccc0003-cccc-cccc-cccc-cccccccc0003"),
        "codigo": "C",
        "nombre": "Noche",
        "students": [
            UUID("b3b3b3b3-0001-0001-0001-000000000001"),
            UUID("b3b3b3b3-0002-0002-0002-000000000002"),
            UUID("b3b3b3b3-0003-0003-0003-000000000003"),
            UUID("b3b3b3b3-0004-0004-0004-000000000004"),
            UUID("b3b3b3b3-0005-0005-0005-000000000005"),
            UUID("b3b3b3b3-0006-0006-0006-000000000006"),
        ],
        # Cohorte con dificultades: empeoran, muchos superficiales
        "patterns": [
            ["apropiacion_reflexiva"] * 2 + ["apropiacion_superficial"] * 4,
            ["apropiacion_superficial"] * 6,
            ["delegacion_pasiva"] * 3 + ["apropiacion_superficial"] * 3,
            ["apropiacion_superficial"] * 5,
            ["apropiacion_reflexiva"] * 1 + ["apropiacion_superficial"] * 4,
            ["delegacion_pasiva"] * 2,
        ],
    },
]

# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------


def _dt(ts: datetime) -> str:
    return ts.isoformat().replace("+00:00", "Z")


def _instance_id_for(template_id: UUID, cohort_idx: int) -> UUID:
    """UUID deterministico de la instancia de TP para `(template, cohort)`.

    Misma formula que el INSERT en `seed_academic` — ambos lados deben
    producir el mismo UUID para que `Episode.problema_id` apunte a una
    fila real de `tareas_practicas` post-seed.
    """
    return UUID(
        int=(template_id.int ^ ((cohort_idx + 1) * 0xC0DE_C0DE_C0DE_C0DE))
        & ((1 << 128) - 1)
    )


def _build_event_canonical(
    *,
    event_uuid: UUID,
    episode_id: UUID,
    tenant_id: UUID,
    seq: int,
    event_type: str,
    ts: datetime,
    payload: dict,
) -> dict:
    return {
        "event_uuid": str(event_uuid),
        "episode_id": str(episode_id),
        "tenant_id": str(tenant_id),
        "seq": seq,
        "event_type": event_type,
        "ts": _dt(ts),
        "payload": payload,
        "prompt_system_hash": PROMPT_SYSTEM_HASH,
        "prompt_system_version": PROMPT_SYSTEM_VERSION,
        "classifier_config_hash": CLASSIFIER_CONFIG_HASH,
    }


def _build_events_for_episode(
    *,
    episode_id: UUID,
    tenant_id: UUID,
    comision_id: UUID,
    student_pseudonym: UUID,
    problema_id: UUID,
    opened_at: datetime,
    closed_at: datetime,
) -> list[dict]:
    specs = [
        {
            "event_type": "episodio_abierto",
            "ts": opened_at,
            "payload": {
                "student_pseudonym": str(student_pseudonym),
                "problema_id": str(problema_id),
                "comision_id": str(comision_id),
                "curso_config_hash": CURSO_CONFIG_HASH,
            },
        },
        {
            "event_type": "prompt_enviado",
            "ts": opened_at + timedelta(minutes=5),
            "payload": {
                "content": "Como encaro el problema de las listas enlazadas?",
                "prompt_kind": "aclaracion_enunciado",
                "chunks_used_hash": None,
            },
        },
        {
            "event_type": "tutor_respondio",
            "ts": opened_at + timedelta(minutes=6),
            "payload": {
                "content": "Pensemos juntos: que diferencia ves entre una lista y un array?",
                "model_used": "claude-sonnet-4-6",
                "socratic_compliance": 0.95,
                "violations": [],
            },
        },
        {
            "event_type": "codigo_ejecutado",
            "ts": opened_at + timedelta(minutes=20),
            "payload": {
                "passed": 3,
                "failed": 1,
                "total": 4,
                "stdout": "test_empty OK\ntest_single OK\ntest_multi OK\ntest_reverse FAILED",
                "failed_test_names": ["test_reverse"],
            },
        },
        {
            "event_type": "episodio_cerrado",
            "ts": closed_at,
            "payload": {
                "final_chain_hash": "",
                "total_events": 5,
                "duration_seconds": (closed_at - opened_at).total_seconds(),
            },
        },
    ]

    results: list[dict] = []
    prev_chain = GENESIS_HASH
    for seq, spec in enumerate(specs):
        event_uuid = UUID(int=(episode_id.int ^ (seq + 1) * 0x9E3779B97F4A7C15) & ((1 << 128) - 1))
        canonical = _build_event_canonical(
            event_uuid=event_uuid,
            episode_id=episode_id,
            tenant_id=tenant_id,
            seq=seq,
            event_type=spec["event_type"],
            ts=spec["ts"],
            payload=spec["payload"],
        )
        self_hash = compute_self_hash(canonical)
        chain_hash = compute_chain_hash(self_hash, prev_chain)
        results.append(
            {
                "event_uuid": event_uuid,
                "seq": seq,
                "event_type": spec["event_type"],
                "ts_dt": spec["ts"],
                "payload": spec["payload"],
                "self_hash": self_hash,
                "chain_hash": chain_hash,
                "prev_chain_hash": prev_chain,
            }
        )
        prev_chain = chain_hash
    return results


async def _set_tenant(session: AsyncSession, tenant_id: UUID) -> None:
    await session.execute(
        text("SELECT set_config('app.current_tenant', :t, true)"),
        {"t": str(tenant_id)},
    )


# ---------------------------------------------------------------------
# Seeds
# ---------------------------------------------------------------------


async def seed_academic(academic_url: str) -> dict[UUID, list[UUID]]:
    """Inserta jerarquia academica + comisiones + templates + instancias TP.

    Returns
    -------
    Mapping `comision_id -> [tp_instance_id, ...]` en orden estable
    (orden de `TEMPLATES_DEMO`). Cada comision recibe N instancias (una
    por template). El loop de episodios consume este dict para
    distribuir round-robin con `tp_instances_by_comision[c][ep_idx % N]`.
    """
    engine = create_async_engine(academic_url, pool_size=2)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    today = date.today()
    tp_instances_by_comision: dict[UUID, list[UUID]] = {
        cast(UUID, c["comision_id"]): [] for c in COHORTES
    }

    try:
        async with maker() as session:
            await _set_tenant(session, TENANT_ID)
            # Orden de DELETE respeta FKs:
            # - calificaciones -> entregas (FK)
            # - entregas -> tareas_practicas (FK; epic tp-entregas-correccion)
            # - tareas_practicas (instancias) -> tareas_practicas_templates (por template_id FK)
            # - usuarios_comision / inscripciones / tareas_practicas -> comisiones
            # - comisiones -> periodos / materias
            # - materias -> planes_estudio -> carreras -> facultades
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

            # Universidad (sin tenant_id: es el tenant)
            await session.execute(
                text(
                    "INSERT INTO universidades (id, nombre, codigo, dominio_email, keycloak_realm, config) "
                    "VALUES (:id, :nombre, :codigo, :dominio, :realm, '{}'::jsonb)"
                ),
                {
                    "id": str(UNIVERSIDAD_ID),
                    "nombre": "UNSL demo",
                    "codigo": "UNSL-DEMO",
                    "dominio": "unsl.edu.ar",
                    "realm": "demo_uni",
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
                    "nombre": "FCFMyN demo",
                    "codigo": "FCFMYN",
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
                    "nombre": "TSU IA",
                    "codigo": "TSU-IA",
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
                    "nombre": "Programacion 2",
                    "codigo": "PROG2",
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
                    "ini": today - timedelta(days=60),
                    "fin": today + timedelta(days=60),
                },
            )

            # 3 comisiones — `nombre` es etiqueta humana del selector
            # (e.g. "A-Manana"); la unicidad sigue siendo
            # (tenant, materia, periodo, codigo).
            for cohort in COHORTES:
                cohort_nombre = f"{cohort['codigo']}-{cohort['nombre']}"
                await session.execute(
                    text(
                        "INSERT INTO comisiones "
                        "(id, tenant_id, materia_id, periodo_id, codigo, nombre, curso_config_hash) "
                        "VALUES (:id, :t, :m, :p, :codigo, :nombre, :cch)"
                    ),
                    {
                        "id": str(cohort["comision_id"]),
                        "t": str(TENANT_ID),
                        "m": str(MATERIA_ID),
                        "p": str(PERIODO_ID),
                        "codigo": cohort["codigo"],
                        "nombre": cohort_nombre,
                        "cch": CURSO_CONFIG_HASH,
                    },
                )
                # Docente como titular en las 3 comisiones
                await session.execute(
                    text(
                        "INSERT INTO usuarios_comision "
                        "(tenant_id, comision_id, user_id, rol, fecha_desde) "
                        "VALUES (:t, :c, :u, 'titular', :fd)"
                    ),
                    {
                        "t": str(TENANT_ID),
                        "c": str(cohort["comision_id"]),
                        "u": str(DOCENTE_USER_ID),
                        "fd": today - timedelta(days=60),
                    },
                )
                # Inscripciones
                for pseudo in cohort["students"]:
                    await session.execute(
                        text(
                            "INSERT INTO inscripciones "
                            "(tenant_id, comision_id, student_pseudonym, rol, estado, fecha_inscripcion) "
                            "VALUES (:t, :c, :s, 'regular', 'cursando', :fi)"
                        ),
                        {
                            "t": str(TENANT_ID),
                            "c": str(cohort["comision_id"]),
                            "s": str(pseudo),
                            "fi": today - timedelta(days=45),
                        },
                    )

            # Plantillas de TP (ADR-016) — fuente canonica por (materia, periodo).
            # Cada plantilla se auto-instancia en las 3 comisiones con el mismo
            # codigo/titulo/enunciado. `template_id` del TP apunta al template.
            # `has_drift=false` al inicio — cambia a true si un docente edita
            # la instancia directamente (NO via template).
            for tpl in TEMPLATES_DEMO:
                await session.execute(
                    text(
                        "INSERT INTO tareas_practicas_templates ("
                        "id, tenant_id, materia_id, periodo_id, codigo, titulo, "
                        "consigna, peso, estado, version, created_by"
                        ") VALUES ("
                        ":id, :t, :m, :p, :codigo, :titulo, :consigna, :peso, "
                        "'published', 1, :cb"
                        ")"
                    ),
                    {
                        "id": str(tpl["id"]),
                        "t": str(TENANT_ID),
                        "m": str(MATERIA_ID),
                        "p": str(PERIODO_ID),
                        "codigo": tpl["codigo"],
                        "titulo": tpl["titulo"],
                        "consigna": tpl["enunciado"],
                        "peso": tpl["peso"],
                        "cb": str(DOCENTE_USER_ID),
                    },
                )

                # Instanciar en las 3 comisiones — UUID deterministico por
                # (template, cohort) para que el seed sea idempotente. La
                # misma formula vive en `_instance_id_for(template_id,
                # cohort_idx)`; el dict `tp_instances_by_comision` la usa
                # para que `Episode.problema_id` apunte a esta misma fila.
                for cohort_idx, cohort in enumerate(COHORTES):
                    instance_id = _instance_id_for(cast(UUID, tpl["id"]), cohort_idx)
                    tp_instances_by_comision[cast(UUID, cohort["comision_id"])].append(
                        instance_id
                    )
                    # Fechas: inicio hoy-15d, fin hoy+30d (TP en curso)
                    fecha_inicio = datetime.combine(
                        today - timedelta(days=15),
                        datetime.min.time(),
                        tzinfo=UTC,
                    )
                    fecha_fin = datetime.combine(
                        today + timedelta(days=30),
                        datetime.min.time(),
                        tzinfo=UTC,
                    )
                    await session.execute(
                        text(
                            "INSERT INTO tareas_practicas ("
                            "id, tenant_id, comision_id, template_id, has_drift, "
                            "codigo, titulo, enunciado, peso, fecha_inicio, fecha_fin, "
                            "estado, version, created_by"
                            ") VALUES ("
                            ":id, :t, :c, :tpl, false, "
                            ":codigo, :titulo, :enunciado, :peso, :fi, :ff, "
                            "'published', 1, :cb"
                            ")"
                        ),
                        {
                            "id": str(instance_id),
                            "t": str(TENANT_ID),
                            "c": str(cohort["comision_id"]),
                            "tpl": str(tpl["id"]),
                            "codigo": tpl["codigo"],
                            "titulo": tpl["titulo"],
                            "enunciado": tpl["enunciado"],
                            "peso": tpl["peso"],
                            "fi": fecha_inicio,
                            "ff": fecha_fin,
                            "cb": str(DOCENTE_USER_ID),
                        },
                    )

            await session.commit()
    finally:
        await engine.dispose()
    return tp_instances_by_comision


async def seed_ctr(
    ctr_url: str,
    tp_instances_by_comision: dict[UUID, list[UUID]],
) -> list[tuple[UUID, UUID, UUID, datetime]]:
    """Returns: list de (episode_id, comision_id, student_pseudonym, classified_at).

    `tp_instances_by_comision` viene de `seed_academic` y es la fuente de
    `Episode.problema_id` (round-robin sobre las N instancias de la
    comision). Asi cada episodio apunta a una `TareaPractica` real con
    `template_id` poblado, que es el JOIN que `cii-evolution-longitudinal`
    necesita para no devolver `insufficient_data`.
    """
    engine = create_async_engine(ctr_url, pool_size=2)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    episode_refs: list[tuple[UUID, UUID, UUID, datetime]] = []

    try:
        async with maker() as session:
            await _set_tenant(session, TENANT_ID)
            await session.execute(
                text("DELETE FROM events WHERE tenant_id = :t"),
                {"t": str(TENANT_ID)},
            )
            await session.execute(
                text("DELETE FROM dead_letters WHERE tenant_id = :t"),
                {"t": str(TENANT_ID)},
            )
            await session.execute(
                text("DELETE FROM episodes WHERE tenant_id = :t"),
                {"t": str(TENANT_ID)},
            )
            await session.commit()

        async with maker() as session:
            await _set_tenant(session, TENANT_ID)
            base_time = datetime.now(UTC) - timedelta(days=45)

            for cohort_idx, cohort in enumerate(COHORTES):
                comision_id = cast(UUID, cohort["comision_id"])
                tp_instance_ids = tp_instances_by_comision[comision_id]
                if not tp_instance_ids:
                    raise RuntimeError(
                        f"No hay instancias de TP para comision {comision_id} — "
                        "seed_academic debe correr antes que seed_ctr."
                    )
                for student_idx, (pseudo, pattern) in enumerate(
                    zip(cohort["students"], cohort["patterns"], strict=False)
                ):
                    for ep_idx in range(len(pattern)):
                        opened_at = base_time + timedelta(
                            days=(student_idx * 0.2) + (ep_idx * 5),
                            hours=cohort_idx * 2,  # desfasaje por comision
                        )
                        closed_at = opened_at + timedelta(minutes=45)

                        # Episode id deterministico (cohort_idx en bits altos)
                        episode_id = UUID(
                            int=(
                                (cohort_idx + 1) * 1_000_000
                                + (student_idx + 1) * 10_000
                                + (ep_idx + 1) * 100
                            )
                            | (1 << 127)
                        )

                        # Round-robin sobre las N instancias de TP de la
                        # comision (hoy N=2). Garantiza que cada
                        # template recibe ~mitad de los episodios del
                        # estudiante -> >= MIN_EPISODES_FOR_LONGITUDINAL
                        # cuando el patron tiene >= 6 episodios.
                        problema_id = tp_instance_ids[ep_idx % len(tp_instance_ids)]

                        events = _build_events_for_episode(
                            episode_id=episode_id,
                            tenant_id=TENANT_ID,
                            comision_id=comision_id,
                            student_pseudonym=pseudo,
                            problema_id=problema_id,
                            opened_at=opened_at,
                            closed_at=closed_at,
                        )
                        last_chain_hash = events[-1]["chain_hash"]

                        await session.execute(
                            text(
                                "INSERT INTO episodes ("
                                "id, tenant_id, comision_id, student_pseudonym, problema_id, "
                                "prompt_system_hash, prompt_system_version, "
                                "classifier_config_hash, curso_config_hash, "
                                "estado, opened_at, closed_at, "
                                "events_count, last_chain_hash, integrity_compromised, meta"
                                ") VALUES ("
                                ":id, :t, :c, :s, :pb, "
                                ":psh, :psv, :cch, :cuch, "
                                ":estado, :oa, :ca, "
                                ":ec, :lch, false, '{}'::jsonb"
                                ")"
                            ),
                            {
                                "id": str(episode_id),
                                "t": str(TENANT_ID),
                                "c": str(comision_id),
                                "s": str(pseudo),
                                "pb": str(problema_id),
                                "psh": PROMPT_SYSTEM_HASH,
                                "psv": PROMPT_SYSTEM_VERSION,
                                "cch": CLASSIFIER_CONFIG_HASH,
                                "cuch": CURSO_CONFIG_HASH,
                                "estado": "closed",
                                "oa": opened_at,
                                "ca": closed_at,
                                "ec": len(events),
                                "lch": last_chain_hash,
                            },
                        )

                        for ev in events:
                            await session.execute(
                                text(
                                    "INSERT INTO events ("
                                    "event_uuid, tenant_id, episode_id, seq, event_type, "
                                    "ts, payload, self_hash, chain_hash, prev_chain_hash, "
                                    "prompt_system_hash, prompt_system_version, classifier_config_hash"
                                    ") VALUES ("
                                    ":euid, :t, :eid, :seq, :et, "
                                    ":ts, CAST(:pl AS jsonb), :sh, :ch, :pch, "
                                    ":psh, :psv, :cch"
                                    ")"
                                ),
                                {
                                    "euid": str(ev["event_uuid"]),
                                    "t": str(TENANT_ID),
                                    "eid": str(episode_id),
                                    "seq": ev["seq"],
                                    "et": ev["event_type"],
                                    "ts": ev["ts_dt"],
                                    "pl": json.dumps(ev["payload"]),
                                    "sh": ev["self_hash"],
                                    "ch": ev["chain_hash"],
                                    "pch": ev["prev_chain_hash"],
                                    "psh": PROMPT_SYSTEM_HASH,
                                    "psv": PROMPT_SYSTEM_VERSION,
                                    "cch": CLASSIFIER_CONFIG_HASH,
                                },
                            )

                        classified_at = closed_at + timedelta(minutes=2)
                        episode_refs.append((episode_id, comision_id, pseudo, classified_at))

            # ADR-042 path 1 reforzado — episodios "narrativos" extra para
            # garantizar >=NARRATIVE_STUDENTS_LONGITUDINAL[s] por (estudiante,
            # template_id=NARRATIVE_TEMPLATE_ID). Sin esto, el round-robin del
            # loop principal deja a algunos estudiantes con 2-3 episodios por
            # template, borderline contra MIN_EPISODES_FOR_LONGITUDINAL=3.
            # Las clasificaciones se generan despues por seed_classifications
            # con appropriation="apropiacion_reflexiva" (cohorte trayectoria
            # positiva) — coherente con el panel de defensa.
            narrative_base_time = datetime.now(UTC) - timedelta(days=10)
            for cohort_idx, cohort in enumerate(COHORTES):
                comision_id = cast(UUID, cohort["comision_id"])
                # NARRATIVE_TEMPLATE_ID instance_id depende del cohort_idx
                narrative_instance_id = _instance_id_for(NARRATIVE_TEMPLATE_ID, cohort_idx)
                for student_idx, pseudo in enumerate(cohort["students"]):
                    n_extra = NARRATIVE_STUDENTS_LONGITUDINAL.get(pseudo, 0)
                    if n_extra <= 0:
                        continue
                    for ep_idx in range(n_extra):
                        opened_at = narrative_base_time + timedelta(
                            days=ep_idx, hours=cohort_idx * 2 + student_idx
                        )
                        closed_at = opened_at + timedelta(minutes=45)
                        # UUIDs deterministicos disjuntos del round-robin
                        # (bit alto distinto: 1<<126 vs 1<<127 del loop principal).
                        # +7 marca "narrative" (los del round-robin terminan en
                        # multiplos de 100, este offset evita colision).
                        episode_id = UUID(
                            int=(
                                (cohort_idx + 1) * 1_000_000
                                + (student_idx + 1) * 10_000
                                + (ep_idx + 1) * 100
                                + 7  # marker narrative
                            )
                            | (1 << 126)
                        )
                        events = _build_events_for_episode(
                            episode_id=episode_id,
                            tenant_id=TENANT_ID,
                            comision_id=comision_id,
                            student_pseudonym=pseudo,
                            problema_id=narrative_instance_id,
                            opened_at=opened_at,
                            closed_at=closed_at,
                        )
                        last_chain_hash = events[-1]["chain_hash"]
                        await session.execute(
                            text(
                                "INSERT INTO episodes ("
                                "id, tenant_id, comision_id, student_pseudonym, problema_id, "
                                "prompt_system_hash, prompt_system_version, "
                                "classifier_config_hash, curso_config_hash, "
                                "estado, opened_at, closed_at, "
                                "events_count, last_chain_hash, integrity_compromised, meta"
                                ") VALUES ("
                                ":id, :t, :c, :s, :pb, "
                                ":psh, :psv, :cch, :cuch, "
                                ":estado, :oa, :ca, "
                                ":ec, :lch, false, '{}'::jsonb"
                                ")"
                            ),
                            {
                                "id": str(episode_id),
                                "t": str(TENANT_ID),
                                "c": str(comision_id),
                                "s": str(pseudo),
                                "pb": str(narrative_instance_id),
                                "psh": PROMPT_SYSTEM_HASH,
                                "psv": PROMPT_SYSTEM_VERSION,
                                "cch": CLASSIFIER_CONFIG_HASH,
                                "cuch": CURSO_CONFIG_HASH,
                                "estado": "closed",
                                "oa": opened_at,
                                "ca": closed_at,
                                "ec": len(events),
                                "lch": last_chain_hash,
                            },
                        )
                        for ev in events:
                            await session.execute(
                                text(
                                    "INSERT INTO events ("
                                    "event_uuid, tenant_id, episode_id, seq, event_type, "
                                    "ts, payload, self_hash, chain_hash, prev_chain_hash, "
                                    "prompt_system_hash, prompt_system_version, classifier_config_hash"
                                    ") VALUES ("
                                    ":euid, :t, :eid, :seq, :et, "
                                    ":ts, CAST(:pl AS jsonb), :sh, :ch, :pch, "
                                    ":psh, :psv, :cch"
                                    ")"
                                ),
                                {
                                    "euid": str(ev["event_uuid"]),
                                    "t": str(TENANT_ID),
                                    "eid": str(episode_id),
                                    "seq": ev["seq"],
                                    "et": ev["event_type"],
                                    "ts": ev["ts_dt"],
                                    "pl": json.dumps(ev["payload"]),
                                    "sh": ev["self_hash"],
                                    "ch": ev["chain_hash"],
                                    "pch": ev["prev_chain_hash"],
                                    "psh": PROMPT_SYSTEM_HASH,
                                    "psv": PROMPT_SYSTEM_VERSION,
                                    "cch": CLASSIFIER_CONFIG_HASH,
                                },
                            )
                        classified_at = closed_at + timedelta(minutes=2)
                        episode_refs.append(
                            (episode_id, comision_id, pseudo, classified_at)
                        )

            await session.commit()
    finally:
        await engine.dispose()

    return episode_refs


async def seed_classifications(
    classifier_url: str,
    episode_refs: list[tuple[UUID, UUID, UUID, datetime]],
) -> None:
    engine = create_async_engine(classifier_url, pool_size=2)
    maker = async_sessionmaker(engine, expire_on_commit=False)

    try:
        async with maker() as session:
            await _set_tenant(session, TENANT_ID)
            await session.execute(
                text("DELETE FROM classifications WHERE tenant_id = :t"),
                {"t": str(TENANT_ID)},
            )
            await session.commit()

        async with maker() as session:
            await _set_tenant(session, TENANT_ID)

            # Reconstruccion del mapping: episode_refs esta ordenado
            # por (cohort_idx, student_idx, ep_idx) exactamente como
            # iteramos en seed_ctr. Asi cada appropriation se asocia
            # con su episodio correcto.
            idx = 0
            for cohort in COHORTES:
                for student_idx, pattern in enumerate(cohort["patterns"]):
                    for ep_idx, appropriation in enumerate(pattern):
                        episode_id, comision_id, _pseudo, classified_at = episode_refs[idx]
                        idx += 1

                        if appropriation == "apropiacion_reflexiva":
                            ct, ccd, orph, stab, evo = 0.85, 0.80, 0.05, 0.78, 0.20
                        elif appropriation == "apropiacion_superficial":
                            ct, ccd, orph, stab, evo = 0.55, 0.50, 0.25, 0.55, 0.00
                        else:  # delegacion_pasiva
                            ct, ccd, orph, stab, evo = 0.20, 0.25, 0.60, 0.30, -0.15

                        reason = (
                            f"[{cohort['codigo']}] Arbol N4 - {appropriation}: "
                            f"CT={ct:.2f}, CCD={ccd:.2f}, orph={orph:.2f}, "
                            f"stab={stab:.2f}, evo={evo:+.2f} "
                            f"(episodio {ep_idx + 1}, estudiante #{student_idx + 1})"
                        )

                        await session.execute(
                            text(
                                "INSERT INTO classifications ("
                                "episode_id, tenant_id, comision_id, classifier_config_hash, "
                                "appropriation, appropriation_reason, "
                                "ct_summary, ccd_mean, ccd_orphan_ratio, "
                                "cii_stability, cii_evolution, "
                                "features, classified_at, is_current"
                                ") VALUES ("
                                ":eid, :t, :c, :cch, :app, :reason, "
                                ":ct, :ccd, :orph, :stab, :evo, "
                                "'{}'::jsonb, :ca, true)"
                            ),
                            {
                                "eid": str(episode_id),
                                "t": str(TENANT_ID),
                                "c": str(comision_id),
                                "cch": CLASSIFIER_CONFIG_HASH,
                                "app": appropriation,
                                "reason": reason,
                                "ct": ct,
                                "ccd": ccd,
                                "orph": orph,
                                "stab": stab,
                                "evo": evo,
                                "ca": classified_at,
                            },
                        )

            # ADR-042 path 1 reforzado — clasificaciones de los episodios
            # "narrativos" extra (ver seed_ctr). Slope ascendente para que
            # `cii_evolution_longitudinal` devuelva slope no-null y la vista
            # `StudentLongitudinalView` muestre trayectoria real.
            for nidx, (episode_id, comision_id, _pseudo, classified_at) in enumerate(
                episode_refs[idx:], start=idx
            ):
                # Patron narrativo positivo: superficial -> reflexiva creciente.
                # nidx % 4 = 0,1 -> superficial; 2,3 -> reflexiva.
                # Asi el slope cardinal sobre datos ordinales (delegacion=0,
                # superficial=1, reflexiva=2) crece monotonicamente.
                slot = nidx % 4
                if slot < 2:
                    appropriation = "apropiacion_superficial"
                    ct, ccd, orph, stab, evo = 0.55, 0.50, 0.25, 0.55, 0.00
                else:
                    appropriation = "apropiacion_reflexiva"
                    ct, ccd, orph, stab, evo = 0.85, 0.80, 0.05, 0.78, 0.20

                reason = (
                    f"[NARRATIVE A] Arbol N4 - {appropriation}: "
                    f"CT={ct:.2f}, CCD={ccd:.2f} (episodio narrativo idx={nidx})"
                )

                await session.execute(
                    text(
                        "INSERT INTO classifications ("
                        "episode_id, tenant_id, comision_id, classifier_config_hash, "
                        "appropriation, appropriation_reason, "
                        "ct_summary, ccd_mean, ccd_orphan_ratio, "
                        "cii_stability, cii_evolution, "
                        "features, classified_at, is_current"
                        ") VALUES ("
                        ":eid, :t, :c, :cch, :app, :reason, "
                        ":ct, :ccd, :orph, :stab, :evo, "
                        "'{}'::jsonb, :ca, true) ON CONFLICT (episode_id, classifier_config_hash) DO NOTHING"
                    ),
                    {
                        "eid": str(episode_id),
                        "t": str(TENANT_ID),
                        "c": str(comision_id),
                        "cch": CLASSIFIER_CONFIG_HASH,
                        "app": appropriation,
                        "reason": reason,
                        "ct": ct,
                        "ccd": ccd,
                        "orph": orph,
                        "stab": stab,
                        "evo": evo,
                        "ca": classified_at,
                    },
                )

            await session.commit()
    finally:
        await engine.dispose()


# ---------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------


async def main() -> None:
    academic_url = os.environ.get(
        "ACADEMIC_DB_URL",
        "postgresql+asyncpg://academic_user:academic_pass@localhost:5432/academic_main",
    )
    ctr_url = os.environ.get(
        "CTR_STORE_URL",
        "postgresql+asyncpg://ctr_user:ctr_pass@localhost:5432/ctr_store",
    )
    classifier_url = os.environ.get(
        "CLASSIFIER_DB_URL",
        "postgresql+asyncpg://classifier_user:classifier_pass@localhost:5432/classifier_db",
    )

    total_students = sum(len(c["students"]) for c in COHORTES)
    total_episodes = sum(sum(len(p) for p in c["patterns"]) for c in COHORTES)

    print(f"[seed] tenant      = {TENANT_ID}")
    print(
        f"[seed] comisiones  = {len(COHORTES)} ({', '.join(c['codigo'] + '-' + c['nombre'] for c in COHORTES)})"
    )
    print(f"[seed] estudiantes = {total_students}")
    print(f"[seed] episodios   = {total_episodes}")
    print(
        f"[seed] plantillas  = {len(TEMPLATES_DEMO)} (auto-instanciadas en las {len(COHORTES)} comisiones -> {len(TEMPLATES_DEMO) * len(COHORTES)} TPs)"
    )
    print(f"[seed] academic    -> {academic_url.split('@')[-1]}")
    print(f"[seed] ctr_store   -> {ctr_url.split('@')[-1]}")
    print(f"[seed] classifier  -> {classifier_url.split('@')[-1]}")

    print("[seed] 1/3 academic...")
    tp_instances_by_comision = await seed_academic(academic_url)

    print("[seed] 2/3 ctr_store...")
    episode_refs = await seed_ctr(ctr_url, tp_instances_by_comision)

    print("[seed] 3/3 classifications...")
    await seed_classifications(classifier_url, episode_refs)

    print(
        f"[seed] OK: {len(COHORTES)} comisiones, {total_students} estudiantes, "
        f"{len(episode_refs)} episodios, {len(episode_refs)} classifications"
    )
    print()
    print("Verifica con:")
    for c in COHORTES:
        print(
            f"  curl -s 'http://127.0.0.1:8000/api/v1/analytics/cohort/{c['comision_id']}/progression' \\"
        )
        print("    -H 'X-User-Id: 11111111-1111-1111-1111-111111111111' \\")
        print(f"    -H 'X-Tenant-Id: {TENANT_ID}' \\")
        print("    -H 'X-User-Roles: docente'")


if __name__ == "__main__":
    asyncio.run(main())
