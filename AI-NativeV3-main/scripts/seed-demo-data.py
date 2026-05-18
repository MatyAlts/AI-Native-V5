"""Seed determinista de data demo para el piloto UNSL.

Propósito
---------
Deja la plataforma con datos mínimos suficientes para que las vistas del
`web-teacher` (en particular `Progresión`) muestren algo significativo:

  - 1 Universidad / Facultad / Carrera / Plan / Materia / Periodo / Comisión
  - 6 inscripciones + 1 usuario-comisión (docente)
  - 30 episodios CTR + 30 eventos (cadena SHA-256 válida)
  - 30 classifications (append-only, is_current=true)

Idempotente
-----------
Cada corrida borra primero los datos del tenant demo antes de re-insertar.
Nunca toca tenants distintos (WHERE tenant_id = TENANT_ID).

Ejecución
---------
    export ACADEMIC_DB_URL="postgresql+asyncpg://academic_user:academic_pass@localhost:5432/academic_main"
    export CTR_STORE_URL="postgresql+asyncpg://ctr_user:ctr_pass@localhost:5432/ctr_store"
    export CLASSIFIER_DB_URL="postgresql+asyncpg://classifier_user:classifier_pass@localhost:5432/classifier_db"
    python scripts/seed-demo-data.py

Verificación
-------------
    curl -s "http://127.0.0.1:8000/api/v1/analytics/cohort/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa/progression" \
        -H "X-User-Id: 11111111-1111-1111-1111-111111111111" \
        -H "X-Tenant-Id: aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa" \
        -H "X-User-Roles: docente"
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

# Permitir imports de los servicios sin instalación editable
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "apps" / "ctr-service" / "src"))
sys.path.insert(0, str(ROOT / "apps" / "classifier-service" / "src"))
sys.path.insert(0, str(ROOT / "apps" / "academic-service" / "src"))

# Hashing helpers del proyecto (source of truth)
from ctr_service.services.hashing import (
    GENESIS_HASH,
    compute_chain_hash,
    compute_self_hash,
)
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# ── Constantes del piloto ─────────────────────────────────────────────

# El `analytics-service` hardcodea este tenant_id para la vista progression
# (ver apps/analytics-service/src/analytics_service/routes/analytics.py:260).
# Usamos el MISMO UUID que COMISION_ID porque el endpoint del progression
# lo filtra por ese tenant y el hardcode coincide con el ID de la cohorte.
TENANT_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")

COMISION_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")

UNIVERSIDAD_ID = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
FACULTAD_ID = UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
CARRERA_ID = UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")
PLAN_ID = UUID("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee")
MATERIA_ID = UUID("ffffffff-ffff-ffff-ffff-ffffffffffff")
PERIODO_ID = UUID("12345678-1234-1234-1234-123456789abc")

DOCENTE_USER_ID = UUID("11111111-1111-1111-1111-111111111111")

# Hashes deterministas — el mismo config hash debe viajar en episode y
# classification (regla de auditabilidad, ADR-009 + ADR-010)
PROMPT_SYSTEM_HASH = hashlib.sha256(b"prompt-system-demo-v1").hexdigest()
PROMPT_SYSTEM_VERSION = "v1.0.0"
CLASSIFIER_CONFIG_HASH = hashlib.sha256(b"classifier-config-demo-v1").hexdigest()
CURSO_CONFIG_HASH = hashlib.sha256(b"curso-config-demo-v1").hexdigest()

# Cohorte demo — 6 estudiantes con patrones distintos de progresión
STUDENT_PSEUDONYMS: list[UUID] = [
    UUID("a1a1a1a1-0001-0001-0001-000000000001"),  # mejorando
    UUID("a1a1a1a1-0002-0002-0002-000000000002"),  # mejorando (con delegacion inicial)
    UUID("a1a1a1a1-0003-0003-0003-000000000003"),  # estable superficial
    UUID("a1a1a1a1-0004-0004-0004-000000000004"),  # estable reflexiva
    UUID("a1a1a1a1-0005-0005-0005-000000000005"),  # empeorando
    UUID("a1a1a1a1-0006-0006-0006-000000000006"),  # insuficiente (<3)
]

# Patrones de classification por estudiante (primer tercio → último tercio)
PROGRESION_PATTERNS: list[list[str]] = [
    # 1 — mejorando: 2 superficial, 4 reflexiva
    [
        "apropiacion_superficial",
        "apropiacion_superficial",
        "apropiacion_reflexiva",
        "apropiacion_reflexiva",
        "apropiacion_reflexiva",
        "apropiacion_reflexiva",
    ],
    # 2 — mejorando: empieza en delegación, termina reflexiva
    [
        "delegacion_pasiva",
        "delegacion_pasiva",
        "apropiacion_superficial",
        "apropiacion_superficial",
        "apropiacion_reflexiva",
        "apropiacion_reflexiva",
    ],
    # 3 — estable: todo superficial
    [
        "apropiacion_superficial",
        "apropiacion_superficial",
        "apropiacion_superficial",
        "apropiacion_superficial",
        "apropiacion_superficial",
    ],
    # 4 — estable: todo reflexiva
    [
        "apropiacion_reflexiva",
        "apropiacion_reflexiva",
        "apropiacion_reflexiva",
        "apropiacion_reflexiva",
        "apropiacion_reflexiva",
    ],
    # 5 — empeorando: arranca reflexiva, termina superficial
    [
        "apropiacion_reflexiva",
        "apropiacion_reflexiva",
        "apropiacion_reflexiva",
        "apropiacion_superficial",
        "apropiacion_superficial",
        "apropiacion_superficial",
    ],
    # 6 — insuficiente: solo 2 episodios
    [
        "apropiacion_superficial",
        "apropiacion_superficial",
    ],
]


# ── Hashing determinista de eventos CTR ───────────────────────────────


def _dt(ts: datetime) -> str:
    """Serialización ISO-8601 con Z para UTC."""
    return ts.isoformat().replace("+00:00", "Z")


def build_event_canonical(
    *,
    event_uuid: UUID,
    episode_id: UUID,
    tenant_id: UUID,
    seq: int,
    event_type: str,
    ts: datetime,
    payload: dict,
) -> dict:
    """Diccionario canónico usado para calcular self_hash.

    Incluye TODOS los campos que viajan con el evento excepto
    self_hash/chain_hash/prev_chain_hash/id/persisted_at
    (compute_self_hash ya los filtra, pero los excluimos aquí para
    claridad y para que el dict sea el mismo que se podría persistir).
    """
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


# ── Helpers SQL ───────────────────────────────────────────────────────


async def set_tenant(session: AsyncSession, tenant_id: UUID) -> None:
    """Setea el tenant_id para que RLS permita insertar/seleccionar.

    Usamos `set_config(..., is_local=true)` porque es compatible con
    SQLAlchemy bind params (SET LOCAL no soporta binds).
    """
    await session.execute(
        text("SELECT set_config('app.current_tenant', :t, true)"),
        {"t": str(tenant_id)},
    )


async def seed_academic(academic_url: str) -> None:
    """Inserta la jerarquía academic (idempotente)."""
    engine = create_async_engine(academic_url, pool_size=2)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with maker() as session:
            await set_tenant(session, TENANT_ID)

            # Limpiar datos existentes del tenant (en orden inverso de FKs)
            for table in (
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
            await set_tenant(session, TENANT_ID)

            # Universidad (no tiene tenant_id, es el tenant)
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

            # Facultad
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

            # Carrera
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

            # Plan
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

            # Materia
            await session.execute(
                text(
                    "INSERT INTO materias (id, tenant_id, plan_id, nombre, codigo) "
                    "VALUES (:id, :t, :p, :nombre, :codigo)"
                ),
                {
                    "id": str(MATERIA_ID),
                    "t": str(TENANT_ID),
                    "p": str(PLAN_ID),
                    "nombre": "Programación 2",
                    "codigo": "PROG2",
                },
            )

            # Periodo (abarca la fecha actual para que esté vigente)
            today = date.today()
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

            # Comisión (con el id que el web-teacher espera)
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
                    "codigo": "A",
                    "nombre": "A",
                    "cch": CURSO_CONFIG_HASH,
                },
            )

            # Inscripciones (6 estudiantes)
            for pseudo in STUDENT_PSEUDONYMS:
                await session.execute(
                    text(
                        "INSERT INTO inscripciones "
                        "(tenant_id, comision_id, student_pseudonym, rol, estado, fecha_inscripcion) "
                        "VALUES (:t, :c, :s, 'regular', 'cursando', :fi)"
                    ),
                    {
                        "t": str(TENANT_ID),
                        "c": str(COMISION_ID),
                        "s": str(pseudo),
                        "fi": today - timedelta(days=45),
                    },
                )

            # UsuarioComision (docente)
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
                    "fd": today - timedelta(days=60),
                },
            )

            await session.commit()
    finally:
        await engine.dispose()


async def seed_ctr(ctr_url: str) -> list[tuple[UUID, UUID, datetime]]:
    """Inserta episodios + eventos con cadena válida.

    Returns:
        Lista de (episode_id, student_pseudonym, classified_at) para
        que el seed del classifier sepa qué episodios clasificar.
    """
    engine = create_async_engine(ctr_url, pool_size=2)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    episode_refs: list[tuple[UUID, UUID, datetime]] = []

    try:
        async with maker() as session:
            await set_tenant(session, TENANT_ID)

            # Limpiar eventos + dead_letters + episodios del tenant
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

        # El seed no reutiliza session entre commits — abrimos una nueva
        # por "bloque lógico" para mantener SET LOCAL vigente.
        async with maker() as session:
            await set_tenant(session, TENANT_ID)

            base_time = datetime.now(UTC) - timedelta(days=45)
            problema_id = UUID("99999999-9999-9999-9999-999999999999")

            for student_idx, (pseudo, pattern) in enumerate(
                zip(STUDENT_PSEUDONYMS, PROGRESION_PATTERNS, strict=False)
            ):
                for ep_idx in range(len(pattern)):
                    # Cada episodio espaciado ~5 días
                    opened_at = base_time + timedelta(days=(student_idx * 0.2) + (ep_idx * 5))
                    closed_at = opened_at + timedelta(minutes=45)

                    # Episode id determinístico (facilita idempotencia)
                    episode_id = UUID(
                        int=((student_idx + 1) * 10_000 + (ep_idx + 1) * 100) | (1 << 127)
                    )

                    # Construir 5 eventos con cadena válida
                    events_data = _build_events_for_episode(
                        episode_id=episode_id,
                        tenant_id=TENANT_ID,
                        student_pseudonym=pseudo,
                        problema_id=problema_id,
                        opened_at=opened_at,
                        closed_at=closed_at,
                    )

                    last_chain_hash = events_data[-1]["chain_hash"]

                    # Insertar episodio
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
                            "c": str(COMISION_ID),
                            "s": str(pseudo),
                            "pb": str(problema_id),
                            "psh": PROMPT_SYSTEM_HASH,
                            "psv": PROMPT_SYSTEM_VERSION,
                            "cch": CLASSIFIER_CONFIG_HASH,
                            "cuch": CURSO_CONFIG_HASH,
                            "estado": "closed",
                            "oa": opened_at,
                            "ca": closed_at,
                            "ec": len(events_data),
                            "lch": last_chain_hash,
                        },
                    )

                    # Insertar cada evento
                    for ev in events_data:
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

                    # classified_at = 2 min después del cierre del episodio
                    classified_at = closed_at + timedelta(minutes=2)
                    episode_refs.append((episode_id, pseudo, classified_at))

            await session.commit()
    finally:
        await engine.dispose()

    return episode_refs


def _build_events_for_episode(
    *,
    episode_id: UUID,
    tenant_id: UUID,
    student_pseudonym: UUID,
    problema_id: UUID,
    opened_at: datetime,
    closed_at: datetime,
) -> list[dict]:
    """Construye una cadena válida de 5 eventos para un episodio."""
    specs = [
        {
            "event_type": "episodio_abierto",
            "ts": opened_at,
            "payload": {
                "student_pseudonym": str(student_pseudonym),
                "problema_id": str(problema_id),
                "comision_id": str(COMISION_ID),
                "curso_config_hash": CURSO_CONFIG_HASH,
            },
        },
        {
            "event_type": "prompt_enviado",
            "ts": opened_at + timedelta(minutes=5),
            "payload": {
                "content": "¿Cómo abordo el problema de las listas enlazadas?",
                "prompt_kind": "aclaracion_enunciado",
                "chunks_used_hash": None,
            },
        },
        {
            "event_type": "tutor_respondio",
            "ts": opened_at + timedelta(minutes=6),
            "payload": {
                "content": "Pensemos juntos: ¿qué diferencia ves entre una lista y un array?",
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
                "final_chain_hash": "",  # se reemplaza al construir la cadena
                "total_events": 5,
                "duration_seconds": (closed_at - opened_at).total_seconds(),
            },
        },
    ]

    results: list[dict] = []
    prev_chain = GENESIS_HASH
    for seq, spec in enumerate(specs):
        event_uuid = UUID(int=(episode_id.int ^ (seq + 1) * 0x9E3779B97F4A7C15) & ((1 << 128) - 1))

        canonical = build_event_canonical(
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


async def seed_classifications(
    classifier_url: str,
    episode_refs: list[tuple[UUID, UUID, datetime]],
) -> None:
    """Inserta una classification por episodio siguiendo los patrones."""
    engine = create_async_engine(classifier_url, pool_size=2)
    maker = async_sessionmaker(engine, expire_on_commit=False)

    try:
        async with maker() as session:
            await set_tenant(session, TENANT_ID)
            await session.execute(
                text("DELETE FROM classifications WHERE tenant_id = :t"),
                {"t": str(TENANT_ID)},
            )
            await session.commit()

        async with maker() as session:
            await set_tenant(session, TENANT_ID)

            # Reconstruir el mapping (student_idx, ep_idx) desde episode_refs:
            # episode_refs está ordenado por (student_idx, ep_idx).
            idx = 0
            for student_idx, pattern in enumerate(PROGRESION_PATTERNS):
                for ep_idx, appropriation in enumerate(pattern):
                    episode_id, _pseudo, classified_at = episode_refs[idx]
                    idx += 1

                    # Coherencias sintéticas pero consistentes con la label
                    if appropriation == "apropiacion_reflexiva":
                        ct, ccd, orph, stab, evo = 0.85, 0.80, 0.05, 0.78, 0.20
                    elif appropriation == "apropiacion_superficial":
                        ct, ccd, orph, stab, evo = 0.55, 0.50, 0.25, 0.55, 0.00
                    else:  # delegacion_pasiva
                        ct, ccd, orph, stab, evo = 0.20, 0.25, 0.60, 0.30, -0.15

                    reason = (
                        f"Árbol N4 — patrón {appropriation}: "
                        f"CT={ct:.2f}, CCD={ccd:.2f}, orph={orph:.2f}, "
                        f"stab={stab:.2f}, evo={evo:+.2f} (episodio {ep_idx + 1} "
                        f"de estudiante #{student_idx + 1})"
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
                            "c": str(COMISION_ID),
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

    print(f"[seed] tenant_id  = {TENANT_ID}")
    print(f"[seed] comision   = {COMISION_ID}")
    print(f"[seed] academic   -> {academic_url.split('@')[-1]}")
    print(f"[seed] ctr_store  -> {ctr_url.split('@')[-1]}")
    print(f"[seed] classifier -> {classifier_url.split('@')[-1]}")

    print("[seed] 1/3 academic...")
    await seed_academic(academic_url)

    print("[seed] 2/3 ctr_store...")
    episode_refs = await seed_ctr(ctr_url)

    print("[seed] 3/3 classifications...")
    await seed_classifications(classifier_url, episode_refs)

    total_episodes = sum(len(p) for p in PROGRESION_PATTERNS)
    print(
        f"[seed] OK: {len(STUDENT_PSEUDONYMS)} estudiantes, "
        f"{total_episodes} episodios, {total_episodes} classifications "
        f"cargados en comision {COMISION_ID}"
    )


if __name__ == "__main__":
    asyncio.run(main())
