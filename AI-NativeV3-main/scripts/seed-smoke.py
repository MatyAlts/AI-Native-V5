"""Seed dedicado a la suite smoke E2E (`tests/e2e/smoke/`).

Para qué sirve
--------------
La suite smoke depende de UUIDs canónicos hardcoded:
  - tenant_id    = aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa
  - comision_id  = aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa  (A-Manana)
  - student_id   = b1b1b1b1-0001-0001-0001-000000000001  (A1)
  - docente_id   = 11111111-1111-1111-1111-111111111111
  - tarea_practica_id = 11110000-0000-0000-c0de-c0dec0dec0df  (TP01 instancia A)
  - episode_id   = 80000000-0000-0000-0000-0000000f69b4

Si la DB local NO tiene exactamente estos IDs, los siguientes tests fallan:
  - test_smoke_audit (3 tests)        → episode 80000000-... no existe
  - test_smoke_chain_e2e (1 test)     → idem
  - test_smoke_pedagogico (1+cascade) → TP 11110000-... no existe
  - test_smoke_entregas (3+cascade)   → TP no existe → 500 al crear entrega
  - test_smoke_analytics longitudinal → student no tiene episodios suficientes

`scripts/seed-3-comisiones.py` produce exactamente estos UUIDs (verificado por
construcción algebraica de los IDs determinísticos), pero es DESTRUCTIVO sobre
todo el tenant — borra cualquier comisión preexistente.

Diferencias con `seed-3-comisiones.py`
--------------------------------------
- ADITIVO: NO borra nada. Usa `INSERT ... ON CONFLICT DO NOTHING` en todo lado.
- IDEMPOTENTE: re-correr no duplica ni rompe. Si los IDs ya existen, no-op.
- COEXISTE: preserva otras comisiones/TPs/episodios del mismo tenant que
  hayan sido creadas por dev manual o E2E test runs previos.

Lo que SÍ crea (si no existe)
------------------------------
- 1 universidad / facultad / carrera / plan / materia / periodo
- 1 comisión "A-Manana" + 1 docente titular + 6 estudiantes inscriptos
- 2 plantillas de TP (TPL01, TPL02) + 1 instancia por plantilla en la
  comisión A → 2 TPs published
- 1 episodio canónico cerrado (80000000-...0f69b4) con 5 events SHA-256
  íntegros para los tests de audit/chain
- 5 episodios extra para el student A1 (3 sobre TPL01, 3 sobre TPL02 — el
  total real es 6 contando el canónico) para que `cii_evolution_longitudinal`
  tenga ≥3 episodios por template (RN-130, MIN_EPISODES_FOR_LONGITUDINAL)
- 1 classification por episodio (apropiacion_reflexiva determinístico)

Lo que NO crea
--------------
- Otras comisiones (B-Tarde / C-Noche del seed-3-comisiones)
- Otros estudiantes (A2-A6 del seed-3-comisiones)
- BYOK keys (los smoke tests las crean en runtime con cleanup)
- Casbin policies (asumimos `make seed-casbin` ya corrió)

Uso
---
    python scripts/seed-smoke.py

O via Makefile:
    make seed-smoke

Variables de entorno
--------------------
    ACADEMIC_DB_URL, CTR_STORE_URL, CLASSIFIER_DB_URL  — defaults a
    `postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/<db>`.

Idempotencia probada: 2 corridas consecutivas sin diff observable en counts.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from uuid import UUID

# Permitir imports de los services sin instalación editable (mismo patrón
# que seed-3-comisiones.py — el conftest raíz no aplica acá porque corremos
# como script.)
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "apps" / "ctr-service" / "src"))

from ctr_service.services.hashing import (
    GENESIS_HASH,
    compute_chain_hash,
    compute_self_hash,
)
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

# ---------------------------------------------------------------------
# Constantes canónicas — DEBEN matchear `tests/e2e/smoke/_helpers.py`
# y los UUIDs determinísticos que `seed-3-comisiones.py` produce.
# ---------------------------------------------------------------------

TENANT_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")

UNIVERSIDAD_ID = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
FACULTAD_ID = UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
CARRERA_ID = UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")
PLAN_ID = UUID("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee")
MATERIA_ID = UUID("ffffffff-ffff-ffff-ffff-ffffffffffff")
PERIODO_ID = UUID("12345678-1234-1234-1234-123456789abc")

COMISION_A_MANANA = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
DOCENTE_USER_ID = UUID("11111111-1111-1111-1111-111111111111")

# 6 estudiantes (A1-A6) de la comisión A-Manana del seed-3-comisiones
STUDENTS_A_MANANA = [
    UUID("b1b1b1b1-0001-0001-0001-000000000001"),  # A1 = STUDENT_A1 del smoke
    UUID("b1b1b1b1-0002-0002-0002-000000000002"),
    UUID("b1b1b1b1-0003-0003-0003-000000000003"),
    UUID("b1b1b1b1-0004-0004-0004-000000000004"),
    UUID("b1b1b1b1-0005-0005-0005-000000000005"),
    UUID("b1b1b1b1-0006-0006-0006-000000000006"),
]

# Plantillas de TP (ADR-016) y sus instancias en la comisión A.
# Las fórmulas vienen de `seed-3-comisiones.py::_instance_id_for(tpl, 0)`:
#   TPL01_INSTANCE_A = TPL01.int ^ (1 * 0xC0DE_C0DE_C0DE_C0DE)
#   = 11110000-0000-0000-c0de-c0dec0dec0df  ← ESTO usa el smoke como tarea_practica_id
TEMPLATE_01_ID = UUID("11110000-0000-0000-0000-000000000001")
TEMPLATE_02_ID = UUID("11110000-0000-0000-0000-000000000002")
TPL01_INSTANCE_A = UUID("11110000-0000-0000-c0de-c0dec0dec0df")  # canonical smoke TP
TPL02_INSTANCE_A = UUID("11110000-0000-0000-c0de-c0dec0dec0dc")

# Episodio canónico que el smoke audit/chain/recompute espera.
# Construido por `seed-3-comisiones.py` con cohort_idx=0 student_idx=0 ep_idx=0.
SEEDED_EPISODE_ID = UUID("80000000-0000-0000-0000-0000000f69b4")

# Hashes — alineados con `seed-3-comisiones.py` y con
# `Settings.default_prompt_version` del tutor-service.
PROMPT_SYSTEM_VERSION = "v1.0.1"
PROMPT_SYSTEM_HASH = "2ecfcdddd29681b24539114975b601f9ec432560dc3c3a066980bb2e3d36187b"
CLASSIFIER_CONFIG_HASH = hashlib.sha256(b"classifier-config-demo-v1").hexdigest()
CURSO_CONFIG_HASH = hashlib.sha256(b"curso-config-demo-v1").hexdigest()


def _episode_id_for(student_idx: int, ep_idx: int, cohort_idx: int = 0) -> UUID:
    """Replica de `seed-3-comisiones.py::seed_ctr` line ~715.

    Para `(cohort_idx=0, student_idx=0, ep_idx=0)` devuelve
    `80000000-0000-0000-0000-0000000f69b4` (el SEEDED_EPISODE_ID).
    """
    return UUID(
        int=(
            (cohort_idx + 1) * 1_000_000
            + (student_idx + 1) * 10_000
            + (ep_idx + 1) * 100
        )
        | (1 << 127)
    )


def _dt(ts: datetime) -> str:
    return ts.isoformat().replace("+00:00", "Z")


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
    """Construye la cadena SHA-256 de un episodio cerrado (5 events).

    Réplica EXACTA de `seed-3-comisiones.py::_build_events_for_episode` —
    necesitamos el mismo canonical buffer para que los hashes coincidan.
    """
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
        event_uuid = UUID(
            int=(episode_id.int ^ (seq + 1) * 0x9E3779B97F4A7C15) & ((1 << 128) - 1)
        )
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
# Seeds idempotentes — todos los INSERT con ON CONFLICT DO NOTHING.
# ---------------------------------------------------------------------


async def seed_academic(academic_url: str) -> None:
    """Inserta jerarquía + comisión A + 6 inscripciones + 2 TPs.

    No borra nada. Si los IDs ya existen, no-op silencioso.
    """
    engine = create_async_engine(academic_url, pool_size=2)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    today = date.today()

    try:
        async with maker() as session:
            await _set_tenant(session, TENANT_ID)

            await session.execute(
                text(
                    "INSERT INTO universidades (id, nombre, codigo, dominio_email, keycloak_realm, config) "
                    "VALUES (:id, :nombre, :codigo, :dominio, :realm, '{}'::jsonb) "
                    "ON CONFLICT (id) DO NOTHING"
                ),
                {
                    "id": str(UNIVERSIDAD_ID),
                    "nombre": "UNSL smoke",
                    "codigo": "UNSL-SMOKE",
                    "dominio": "unsl.edu.ar",
                    "realm": "smoke_uni",
                },
            )
            await session.execute(
                text(
                    "INSERT INTO facultades (id, tenant_id, universidad_id, nombre, codigo) "
                    "VALUES (:id, :t, :uni, :nombre, :codigo) "
                    "ON CONFLICT (id) DO NOTHING"
                ),
                {
                    "id": str(FACULTAD_ID),
                    "t": str(TENANT_ID),
                    "uni": str(UNIVERSIDAD_ID),
                    "nombre": "FCFMyN smoke",
                    "codigo": "FCFMYN-SMOKE",
                },
            )
            await session.execute(
                text(
                    "INSERT INTO carreras (id, tenant_id, universidad_id, facultad_id, nombre, codigo) "
                    "VALUES (:id, :t, :uni, :fac, :nombre, :codigo) "
                    "ON CONFLICT (id) DO NOTHING"
                ),
                {
                    "id": str(CARRERA_ID),
                    "t": str(TENANT_ID),
                    "uni": str(UNIVERSIDAD_ID),
                    "fac": str(FACULTAD_ID),
                    "nombre": "TSU IA smoke",
                    "codigo": "TSU-IA-SMOKE",
                },
            )
            await session.execute(
                text(
                    "INSERT INTO planes_estudio (id, tenant_id, carrera_id, version, año_inicio) "
                    "VALUES (:id, :t, :car, :v, :anio) "
                    "ON CONFLICT (id) DO NOTHING"
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
                    "VALUES (:id, :t, :p, :nombre, :codigo) "
                    "ON CONFLICT (id) DO NOTHING"
                ),
                {
                    "id": str(MATERIA_ID),
                    "t": str(TENANT_ID),
                    "p": str(PLAN_ID),
                    "nombre": "Programacion 2 (smoke)",
                    "codigo": "PROG2-SMOKE",
                },
            )
            await session.execute(
                text(
                    "INSERT INTO periodos (id, tenant_id, codigo, nombre, fecha_inicio, fecha_fin, estado) "
                    "VALUES (:id, :t, :codigo, :nombre, :ini, :fin, 'abierto') "
                    "ON CONFLICT (id) DO NOTHING"
                ),
                {
                    "id": str(PERIODO_ID),
                    "t": str(TENANT_ID),
                    "codigo": f"{today.year}-S1-SMOKE",
                    "nombre": f"Cuatrimestre {today.year}-S1 smoke",
                    "ini": today - timedelta(days=60),
                    "fin": today + timedelta(days=60),
                },
            )

            # Comisión A-Manana
            await session.execute(
                text(
                    "INSERT INTO comisiones "
                    "(id, tenant_id, materia_id, periodo_id, codigo, nombre, curso_config_hash) "
                    "VALUES (:id, :t, :m, :p, :codigo, :nombre, :cch) "
                    "ON CONFLICT (id) DO NOTHING"
                ),
                {
                    "id": str(COMISION_A_MANANA),
                    "t": str(TENANT_ID),
                    "m": str(MATERIA_ID),
                    "p": str(PERIODO_ID),
                    "codigo": "A",
                    "nombre": "A-Manana",
                    "cch": CURSO_CONFIG_HASH,
                },
            )
            # Docente como titular
            await session.execute(
                text(
                    "INSERT INTO usuarios_comision "
                    "(tenant_id, comision_id, user_id, rol, fecha_desde) "
                    "VALUES (:t, :c, :u, 'titular', :fd) "
                    "ON CONFLICT ON CONSTRAINT uq_usuario_comision DO NOTHING"
                ),
                {
                    "t": str(TENANT_ID),
                    "c": str(COMISION_A_MANANA),
                    "u": str(DOCENTE_USER_ID),
                    "fd": today - timedelta(days=60),
                },
            )
            # 6 inscripciones (A1-A6)
            for pseudo in STUDENTS_A_MANANA:
                await session.execute(
                    text(
                        "INSERT INTO inscripciones "
                        "(tenant_id, comision_id, student_pseudonym, rol, estado, fecha_inscripcion) "
                        "VALUES (:t, :c, :s, 'regular', 'cursando', :fi) "
                        "ON CONFLICT ON CONSTRAINT uq_inscripcion_student DO NOTHING"
                    ),
                    {
                        "t": str(TENANT_ID),
                        "c": str(COMISION_A_MANANA),
                        "s": str(pseudo),
                        "fi": today - timedelta(days=45),
                    },
                )

            # 2 templates de TP
            for tpl_id, codigo, titulo, peso in (
                (TEMPLATE_01_ID, "TP-01", "Recursion y complejidad temporal", 0.20),
                (TEMPLATE_02_ID, "TP-02", "Listas enlazadas simples", 0.25),
            ):
                await session.execute(
                    text(
                        "INSERT INTO tareas_practicas_templates ("
                        "id, tenant_id, materia_id, periodo_id, codigo, titulo, "
                        "enunciado, peso, estado, version, created_by"
                        ") VALUES ("
                        ":id, :t, :m, :p, :codigo, :titulo, :enunciado, :peso, "
                        "'published', 1, :cb"
                        ") ON CONFLICT (id) DO NOTHING"
                    ),
                    {
                        "id": str(tpl_id),
                        "t": str(TENANT_ID),
                        "m": str(MATERIA_ID),
                        "p": str(PERIODO_ID),
                        "codigo": codigo,
                        "titulo": titulo,
                        "enunciado": f"# {titulo}\n\nEnunciado del TP para smoke E2E.\n",
                        "peso": peso,
                        "cb": str(DOCENTE_USER_ID),
                    },
                )

            # 2 instancias TP (TPL01-A y TPL02-A) — apuntan a sus templates
            fecha_inicio = datetime.combine(
                today - timedelta(days=15), datetime.min.time(), tzinfo=UTC
            )
            fecha_fin = datetime.combine(
                today + timedelta(days=30), datetime.min.time(), tzinfo=UTC
            )
            for inst_id, tpl_id, codigo, titulo, peso in (
                (
                    TPL01_INSTANCE_A,
                    TEMPLATE_01_ID,
                    "TP-01",
                    "Recursion y complejidad temporal",
                    0.20,
                ),
                (
                    TPL02_INSTANCE_A,
                    TEMPLATE_02_ID,
                    "TP-02",
                    "Listas enlazadas simples",
                    0.25,
                ),
            ):
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
                        ") ON CONFLICT (id) DO NOTHING"
                    ),
                    {
                        "id": str(inst_id),
                        "t": str(TENANT_ID),
                        "c": str(COMISION_A_MANANA),
                        "tpl": str(tpl_id),
                        "codigo": codigo,
                        "titulo": titulo,
                        "enunciado": f"# {titulo}\n\nEnunciado del TP para smoke E2E.\n",
                        "peso": peso,
                        "fi": fecha_inicio,
                        "ff": fecha_fin,
                        "cb": str(DOCENTE_USER_ID),
                    },
                )

            await session.commit()
    finally:
        await engine.dispose()


# Episodios a crear para A1: 6 en total, alternando TPL01/TPL02 por ep_idx
# (igual al round-robin de seed-3-comisiones). El primero (ep_idx=0) es el
# canonical SEEDED_EPISODE_ID.
A1_STUDENT_IDX = 0  # A1 es students[0]
A1_NUM_EPISODES = 6  # ≥3 por template para cii_evolution_longitudinal


async def seed_ctr(ctr_url: str) -> list[tuple[UUID, datetime]]:
    """Crea episodios CTR para A1, idempotente.

    Returns: list de (episode_id, classified_at) para alimentar las
    classifications. Si los episodios ya existen, devuelve la misma lista
    pero los INSERTs son no-op.
    """
    engine = create_async_engine(ctr_url, pool_size=2)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    episode_refs: list[tuple[UUID, datetime]] = []

    try:
        async with maker() as session:
            await _set_tenant(session, TENANT_ID)
            base_time = datetime.now(UTC) - timedelta(days=45)

            tp_instance_ids = [TPL01_INSTANCE_A, TPL02_INSTANCE_A]
            student_pseudonym = STUDENTS_A_MANANA[A1_STUDENT_IDX]

            for ep_idx in range(A1_NUM_EPISODES):
                episode_id = _episode_id_for(A1_STUDENT_IDX, ep_idx, cohort_idx=0)
                problema_id = tp_instance_ids[ep_idx % len(tp_instance_ids)]
                opened_at = base_time + timedelta(
                    days=(A1_STUDENT_IDX * 0.2) + (ep_idx * 5)
                )
                closed_at = opened_at + timedelta(minutes=45)

                events = _build_events_for_episode(
                    episode_id=episode_id,
                    tenant_id=TENANT_ID,
                    comision_id=COMISION_A_MANANA,
                    student_pseudonym=student_pseudonym,
                    problema_id=problema_id,
                    opened_at=opened_at,
                    closed_at=closed_at,
                )
                last_chain_hash = events[-1]["chain_hash"]

                # Episode (PK = id)
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
                        ") ON CONFLICT (id) DO NOTHING"
                    ),
                    {
                        "id": str(episode_id),
                        "t": str(TENANT_ID),
                        "c": str(COMISION_A_MANANA),
                        "s": str(student_pseudonym),
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

                # Events (UNIQUE (episode_id, seq))
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
                            ") ON CONFLICT ON CONSTRAINT uq_events_episode_seq DO NOTHING"
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
                episode_refs.append((episode_id, classified_at))

            await session.commit()
    finally:
        await engine.dispose()
    return episode_refs


async def seed_classifications(
    classifier_url: str,
    episode_refs: list[tuple[UUID, datetime]],
) -> None:
    """Crea 1 classification por episodio (apropiacion_reflexiva fija).

    UNIQUE (episode_id, classifier_config_hash) → idempotente con ON CONFLICT.
    """
    engine = create_async_engine(classifier_url, pool_size=2)
    maker = async_sessionmaker(engine, expire_on_commit=False)

    try:
        async with maker() as session:
            await _set_tenant(session, TENANT_ID)

            for episode_id, classified_at in episode_refs:
                # Apropiacion fija "reflexiva" — irrelevante para los tests
                # que usan estos datos (cii_evolution_longitudinal sólo mira
                # el slope per-template, no la apropriation). Si en el futuro
                # un test expecta variabilidad, parametrizar acá.
                ct, ccd, orph, stab, evo = 0.85, 0.80, 0.05, 0.78, 0.20
                appropriation = "apropiacion_reflexiva"

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
                        "'{}'::jsonb, :ca, true"
                        ") ON CONFLICT ON CONSTRAINT uq_classifications_episode_config DO NOTHING"
                    ),
                    {
                        "eid": str(episode_id),
                        "t": str(TENANT_ID),
                        "c": str(COMISION_A_MANANA),
                        "cch": CLASSIFIER_CONFIG_HASH,
                        "app": appropriation,
                        "reason": "smoke seed: apropriacion reflexiva fija",
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
        "postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/academic_main",
    )
    ctr_url = os.environ.get(
        "CTR_STORE_URL",
        "postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/ctr_store",
    )
    classifier_url = os.environ.get(
        "CLASSIFIER_DB_URL",
        "postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/classifier_db",
    )

    print(f"[seed-smoke] tenant      = {TENANT_ID}")
    print(f"[seed-smoke] comision    = {COMISION_A_MANANA} (A-Manana)")
    print(f"[seed-smoke] student     = {STUDENTS_A_MANANA[0]} (A1)")
    print(f"[seed-smoke] tarea_pract = {TPL01_INSTANCE_A} (TPL01 instance)")
    print(f"[seed-smoke] episode     = {SEEDED_EPISODE_ID} (A1 ep#0)")
    print(f"[seed-smoke] academic    -> {academic_url.split('@')[-1]}")
    print(f"[seed-smoke] ctr_store   -> {ctr_url.split('@')[-1]}")
    print(f"[seed-smoke] classifier  -> {classifier_url.split('@')[-1]}")
    print("[seed-smoke] modo: ADITIVO (ON CONFLICT DO NOTHING — no borra nada)")

    print("[seed-smoke] 1/3 academic (jerarquia + comision A + 2 TPs + 6 inscripciones)...")
    await seed_academic(academic_url)

    print(f"[seed-smoke] 2/3 ctr_store ({A1_NUM_EPISODES} episodios cerrados de A1)...")
    episode_refs = await seed_ctr(ctr_url)

    print(f"[seed-smoke] 3/3 classifications ({len(episode_refs)} clasificaciones)...")
    await seed_classifications(classifier_url, episode_refs)

    print(f"[seed-smoke] OK: smoke baseline preparado ({len(episode_refs)} episodios A1).")
    print()
    print("Verificar con:")
    print("  make test-smoke-local")


if __name__ == "__main__":
    asyncio.run(main())
