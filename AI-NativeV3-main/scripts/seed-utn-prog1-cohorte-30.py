"""Seed determinista para UTN Programacion I — Comision 1 con 30 alumnos.

Para que sirve
--------------
Pobla COM-1 (UTN PROG1) con 30 alumnos sinteticos + 1 unidad nueva
("Variables y Tipos") + 3 TPs nuevos + ~300 episodios CTR con cadena
SHA-256 valida + ~300 classifications append-only + reflexiones
metacognitivas. Objetivo: darle volumen suficiente al docente para
validar todas las vistas de analitica (cohorte, cuartiles CII, alertas,
progresion, instrumentos cohorte) con N=30 >> MIN_STUDENTS_FOR_QUARTILES=5.

Shape resultante (delta sobre lo existente)
-------------------------------------------
- 1 unidad nueva: "Variables y Tipos" (orden=3, las existentes 1+2 intactas)
- 3 TPs publicados: TP-VAR-01, TP-VAR-02, TP-VAR-03 (vinculados a la unidad)
- 30 alumnos: pseudonyms c1c1c1c1-0001-... a c1c1c1c1-0030-...
  (no chocan con los del seed-3-comisiones que usan b1b1b1b1-...)
- ~300 episodios CTR cerrados: 30 alumnos x ~10 episodios cada uno,
  apuntando a 4 TPs publicados (Tp2 existente + 3 nuevos)
- ~300 classifications con LABELER_VERSION=1.2.0 (mismo hash que las
  existentes para reproducibilidad bit-a-bit)
- ~150 reflexiones metacognitivas (la mitad de los episodios cerrados)
- 2 alumnos con eventos `intento_adverso_detectado` para que aparezca
  badge "Adversarial events" en el dashboard docente

Cohorte distribuida (no todos iguales)
--------------------------------------
- 6 alumnos N4 reflexivos (slope positivo, mayormente reflexiva)
- 10 alumnos N3 superficiales (bajo CT, sin profundidad)
- 8 alumnos mixtos (oscilan entre N2 y N3)
- 4 alumnos N1-N2 con dificultades (bottom quartile, alertas activas)
- 2 alumnos con intentos adversos (severidad 2 — guardrails ADR-019)

Idempotencia
------------
Borra solo lo que tiene `c1c1c1c1-...` o el rango UUID de este seed
(unidades + TPs + episodios + classifications + reflexiones + inscripciones)
antes de re-insertar. NO toca:
- La unica inscripcion existente (e19354fb-...) ni sus episodios
- Los TPs existentes (Tpp4, Tp2, etc.) ni sus eventos
- Las 2 unidades existentes (Repetitivas, Secuenciales)
- Ningun otro tenant

Ejecucion
---------
    uv run python scripts/seed-utn-prog1-cohorte-30.py

ADR-010/020 (CTR append-only + reproducibilidad bit-a-bit) garantizados:
cada evento se construye con compute_self_hash + compute_chain_hash
usando GENESIS_HASH al inicio de cada episodio. `make check-rls` sigue
pasando porque RLS se respeta via `_set_tenant` antes de cada INSERT.
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

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "apps" / "ctr-service" / "src"))

from ctr_service.services.hashing import (
    GENESIS_HASH,
    compute_chain_hash,
    compute_self_hash,
)
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# ---------------------------------------------------------------------
# Constantes — UTN Programacion I, Comision 1
# ---------------------------------------------------------------------

TENANT_UTN = UUID("7a7a143c-31f8-461b-be08-d86ac36b41a3")
MATERIA_PROG1 = UUID("e8057c30-f7e2-4610-83c5-906e855d4ce7")
COMISION_1 = UUID("7b18f4d8-24b7-4034-979e-1fd464939f0e")
DOCENTE_COM1 = UUID("c8a54501-e2a5-434f-b043-83e11600eabc")

# Unidad nueva a crear
UNIDAD_VARIABLES_ID = UUID("c0c0c0c0-0001-0001-0001-000000000001")

# 3 TPs nuevos a crear
TP_VAR_01_ID = UUID("c0c0c0c0-1001-1001-1001-000000000001")
TP_VAR_02_ID = UUID("c0c0c0c0-1002-1002-1002-000000000002")
TP_VAR_03_ID = UUID("c0c0c0c0-1003-1003-1003-000000000003")

# TPs publicados ya existentes que los alumnos van a "haber hecho"
TP_EXISTENTE_PUB_2 = UUID("8c76cf91-46f3-43da-a02d-b1123add34bc")  # Tp2 — Repetitivas

# 30 pseudonyms de alumnos
STUDENT_PSEUDONYMS: list[UUID] = [
    UUID(f"c1c1c1c1-{i:04x}-{i:04x}-{i:04x}-{i:012x}") for i in range(1, 31)
]

# Hashes — alineados con los del seed-3-comisiones para reproducibilidad
PROMPT_SYSTEM_VERSION = "v1.0.1"
PROMPT_SYSTEM_HASH = "2ecfcdddd29681b24539114975b601f9ec432560dc3c3a066980bb2e3d36187b"
CLASSIFIER_CONFIG_HASH = hashlib.sha256(b"classifier-config-demo-v1").hexdigest()
CURSO_CONFIG_HASH = hashlib.sha256(b"curso-config-utn-prog1-v1").hexdigest()

# 4 TPs sobre los cuales se generan episodios (round-robin)
TP_ROTATION: list[tuple[UUID, str, str]] = [
    (TP_EXISTENTE_PUB_2, "Tp2", "Repetitivas — existente"),
    (TP_VAR_01_ID, "TP-VAR-01", "Variables: tipos primitivos"),
    (TP_VAR_02_ID, "TP-VAR-02", "Variables: conversiones de tipo"),
    (TP_VAR_03_ID, "TP-VAR-03", "Variables: scope y mutabilidad"),
]

# Distribucion de cohorte: 30 alumnos en 5 patrones
# Cada string es la "appropriation" del classifier para ese episodio
COHORT_PATTERNS: list[tuple[str, list[str]]] = [
    # 6 reflexivos: mayormente reflexiva, slope positivo
    *[
        (
            "reflexivo",
            ["apropiacion_superficial"] * 2 + ["apropiacion_reflexiva"] * 8,
        )
        for _ in range(6)
    ],
    # 10 superficiales: bajo CT, sin profundidad
    *[
        (
            "superficial",
            ["apropiacion_superficial"] * 8 + ["apropiacion_reflexiva"] * 2,
        )
        for _ in range(10)
    ],
    # 8 mixtos: oscilan, semilla de aprendizaje
    *[
        (
            "mixto",
            ["delegacion_pasiva"] * 2
            + ["apropiacion_superficial"] * 4
            + ["apropiacion_reflexiva"] * 4,
        )
        for _ in range(8)
    ],
    # 4 con dificultades: bottom quartile, mucha delegacion
    *[
        (
            "dificultades",
            ["delegacion_pasiva"] * 5 + ["apropiacion_superficial"] * 3,
        )
        for _ in range(4)
    ],
    # 2 adversos: severidad 2, ADR-019 — generan evento intento_adverso_detectado
    *[
        (
            "adverso",
            ["apropiacion_superficial"] * 4 + ["delegacion_pasiva"] * 4,
        )
        for _ in range(2)
    ],
]

assert len(COHORT_PATTERNS) == 30, "Cohorte debe tener exactamente 30 alumnos"


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------


def _dt(ts: datetime) -> str:
    return ts.isoformat().replace("+00:00", "Z")


async def _set_tenant(session: AsyncSession, tenant_id: UUID) -> None:
    await session.execute(
        text("SELECT set_config('app.current_tenant', :t, true)"),
        {"t": str(tenant_id)},
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
    appropriation: str,
    include_adverso: bool = False,
    include_reflexion: bool = False,
) -> list[dict]:
    """Genera la lista de eventos para un episodio con cadena SHA-256 valida.

    `appropriation` modula el contenido del prompt + el resultado del codigo
    para que sea coherente con la classification que vamos a generar despues.
    """
    is_reflexive = appropriation == "apropiacion_reflexiva"
    is_passive = appropriation == "delegacion_pasiva"

    specs: list[dict] = [
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
    ]

    if include_adverso:
        specs.append(
            {
                "event_type": "intento_adverso_detectado",
                "ts": opened_at + timedelta(minutes=2),
                "payload": {
                    "severity": 2,
                    "category": "jailbreak",
                    "pattern_id": "ignore_previous_instructions",
                    "guardrails_corpus_hash": hashlib.sha256(b"guardrails-v1.2.0").hexdigest(),
                },
            }
        )

    prompt_content = (
        "Que pasa si una variable apunta a otra variable? Entiendo que en Python "
        "todo es objeto pero no me cierra el caso de las listas mutables."
        if is_reflexive
        else "decime la respuesta del ejercicio 1"
        if is_passive
        else "como hago el ejercicio?"
    )
    tutor_response = (
        "Buena pregunta. Antes de avanzar: que pasa si haces a = [1,2,3]; b = a; "
        "b.append(4)? que esperas que tenga a? Probalo y volve."
        if is_reflexive
        else "Pensemos paso a paso. Que tipo de datos te parece mas natural para esto?"
    )

    specs.extend(
        [
            {
                "event_type": "prompt_enviado",
                "ts": opened_at + timedelta(minutes=5),
                "payload": {
                    "content": prompt_content,
                    "prompt_kind": "exploracion" if is_reflexive else "aclaracion_enunciado",
                    "chunks_used_hash": None,
                },
            },
            {
                "event_type": "tutor_respondio",
                "ts": opened_at + timedelta(minutes=6),
                "payload": {
                    "content": tutor_response,
                    "model_used": "mistral-small-latest",
                    "socratic_compliance": 0.95 if is_reflexive else 0.80,
                    "violations": [],
                    "tokens_input": 1200 if is_reflexive else 800,
                    "tokens_output": 95 if is_reflexive else 40,
                    "provider": "mistral",
                    "cost_usd": 0.00018 if is_reflexive else 0.00012,
                },
            },
            {
                "event_type": "edicion_codigo",
                "ts": opened_at + timedelta(minutes=15),
                "payload": {
                    "origin": "human_typed" if is_reflexive else "copied_from_tutor",
                    "char_delta": 142 if is_reflexive else 35,
                },
            },
            {
                "event_type": "tests_ejecutados",
                "ts": opened_at + timedelta(minutes=22),
                "payload": {
                    "test_count_total": 5,
                    "test_count_passed": 5 if is_reflexive else 3 if appropriation == "apropiacion_superficial" else 1,
                    "test_count_failed": 0 if is_reflexive else 2 if appropriation == "apropiacion_superficial" else 4,
                },
            },
            {
                "event_type": "episodio_cerrado",
                "ts": closed_at,
                "payload": {
                    "total_events": 0,  # placeholder, se sobreescribe abajo
                    "duration_seconds": (closed_at - opened_at).total_seconds(),
                },
            },
        ]
    )

    if include_reflexion:
        specs.append(
            {
                "event_type": "reflexion_completada",
                "ts": closed_at + timedelta(minutes=1),
                "payload": {
                    "prompt_version": "reflection/v1.0.0",
                    "que_aprendiste": (
                        "Entendi que las listas se pasan por referencia, no por valor."
                        if is_reflexive
                        else "Que tengo que pensar mas antes de copiar codigo del tutor."
                    ),
                    "que_explicarias": (
                        "Que cuando asignas b = a, los dos apuntan al mismo objeto."
                        if is_reflexive
                        else ""
                    ),
                    "que_quedo_pendiente": (
                        "Quiero entender cuando hacer copy.deepcopy."
                        if is_reflexive
                        else ""
                    ),
                },
            }
        )

    # Ahora seteamos el total_events real
    for spec in specs:
        if spec["event_type"] == "episodio_cerrado":
            spec["payload"]["total_events"] = len(specs)

    results: list[dict] = []
    prev_chain = GENESIS_HASH
    for seq, spec in enumerate(specs):
        # UUID deterministico del evento (Fibonacci-hash variant)
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


# ---------------------------------------------------------------------
# Seeders
# ---------------------------------------------------------------------


async def seed_unidad_y_tps(academic_url: str) -> None:
    """Crea la unidad nueva 'Variables y Tipos' + 3 TPs nuevos."""
    engine = create_async_engine(academic_url, pool_size=2)
    maker = async_sessionmaker(engine, expire_on_commit=False)

    try:
        async with maker() as session:
            await _set_tenant(session, TENANT_UTN)

            # Limpieza idempotente — solo lo nuestro
            await session.execute(
                text("DELETE FROM tareas_practicas WHERE id IN (:a, :b, :c)"),
                {"a": str(TP_VAR_01_ID), "b": str(TP_VAR_02_ID), "c": str(TP_VAR_03_ID)},
            )
            await session.execute(
                text("DELETE FROM unidades WHERE id = :u"),
                {"u": str(UNIDAD_VARIABLES_ID)},
            )

            # Unidad nueva orden=3 (las existentes son 1 y 2)
            await session.execute(
                text(
                    "INSERT INTO unidades (id, tenant_id, comision_id, nombre, "
                    "descripcion, orden, created_by) VALUES "
                    "(:id, :t, :c, :n, :d, :o, :cb)"
                ),
                {
                    "id": str(UNIDAD_VARIABLES_ID),
                    "t": str(TENANT_UTN),
                    "c": str(COMISION_1),
                    "n": "Variables y Tipos",
                    "d": "Tipos primitivos, mutabilidad, scope y pasaje por referencia en Python.",
                    "o": 3,
                    "cb": str(DOCENTE_COM1),
                },
            )

            now = datetime.now(UTC)
            fecha_inicio = now - timedelta(days=20)
            fecha_fin = now + timedelta(days=40)

            tps_data = [
                (
                    TP_VAR_01_ID,
                    "TP-VAR-01",
                    "Tipos primitivos",
                    "# TP-VAR-01 — Tipos primitivos\n\n"
                    "Implementar una funcion `clasificar(x)` que reciba un valor y devuelva "
                    "su tipo como string: `'int'`, `'float'`, `'str'`, `'bool'`, `'list'`, "
                    "`'dict'`, `'none'` u `'otro'`.\n\n"
                    "## Test cases\n"
                    "- `clasificar(42)` => `'int'`\n"
                    "- `clasificar(3.14)` => `'float'`\n"
                    "- `clasificar('hola')` => `'str'`\n"
                    "- `clasificar(True)` => `'bool'` (cuidado: bool es subclase de int)\n",
                ),
                (
                    TP_VAR_02_ID,
                    "TP-VAR-02",
                    "Conversiones de tipo",
                    "# TP-VAR-02 — Conversiones de tipo\n\n"
                    "Escribir `parsear(s: str)` que reciba un string y devuelva el valor "
                    "convertido al tipo mas especifico posible: int > float > bool > str.\n\n"
                    "**Ejemplos**:\n"
                    "- `parsear('42')` => `42` (int)\n"
                    "- `parsear('3.14')` => `3.14` (float)\n"
                    "- `parsear('true')` => `True` (bool, case-insensitive)\n"
                    "- `parsear('hola')` => `'hola'` (str)\n",
                ),
                (
                    TP_VAR_03_ID,
                    "TP-VAR-03",
                    "Scope y mutabilidad",
                    "# TP-VAR-03 — Scope y mutabilidad\n\n"
                    "Implementar `acumular(lista, valor)` que appendea `valor` a `lista` "
                    "**sin** modificar la lista original (devolver una nueva).\n\n"
                    "**Caso de error a evitar**: si haces `lista.append(valor)` mutas la "
                    "lista del caller. La funcion debe ser **pura**.\n\n"
                    "Bonus: documentar en docstring por que `def f(x=[]):` es un anti-patron.\n",
                ),
            ]

            for tp_id, codigo, titulo, enunciado in tps_data:
                await session.execute(
                    text(
                        "INSERT INTO tareas_practicas ("
                        "id, tenant_id, comision_id, codigo, titulo, enunciado, "
                        "fecha_inicio, fecha_fin, peso, estado, version, "
                        "created_by, unidad_id, test_cases"
                        ") VALUES ("
                        ":id, :t, :c, :code, :tit, :enun, :fi, :ff, :peso, "
                        "'published', 1, :cb, :u, '[]'::jsonb"
                        ")"
                    ),
                    {
                        "id": str(tp_id),
                        "t": str(TENANT_UTN),
                        "c": str(COMISION_1),
                        "code": codigo,
                        "tit": titulo,
                        "enun": enunciado,
                        "fi": fecha_inicio,
                        "ff": fecha_fin,
                        "peso": 0.10,
                        "cb": str(DOCENTE_COM1),
                        "u": str(UNIDAD_VARIABLES_ID),
                    },
                )

            await session.commit()
            print(f"[OK] 1 unidad + 3 TPs creados en COM-1")

    finally:
        await engine.dispose()


async def seed_inscripciones(academic_url: str) -> None:
    """Inscribe 30 alumnos en COM-1."""
    engine = create_async_engine(academic_url, pool_size=2)
    maker = async_sessionmaker(engine, expire_on_commit=False)

    try:
        async with maker() as session:
            await _set_tenant(session, TENANT_UTN)
            # Limpieza idempotente — solo las nuestras (c1c1c1c1-...)
            await session.execute(
                text(
                    "DELETE FROM inscripciones WHERE comision_id = :c "
                    "AND student_pseudonym::text LIKE 'c1c1c1c1-%'"
                ),
                {"c": str(COMISION_1)},
            )

            fecha_inscripcion = date(2026, 3, 1)
            for pseudo in STUDENT_PSEUDONYMS:
                await session.execute(
                    text(
                        "INSERT INTO inscripciones ("
                        "tenant_id, comision_id, student_pseudonym, "
                        "rol, estado, fecha_inscripcion"
                        ") VALUES ("
                        ":t, :c, :s, 'regular', 'activa', :fi"
                        ")"
                    ),
                    {
                        "t": str(TENANT_UTN),
                        "c": str(COMISION_1),
                        "s": str(pseudo),
                        "fi": fecha_inscripcion,
                    },
                )
            await session.commit()
            print(f"[OK] 30 alumnos inscriptos en COM-1")
    finally:
        await engine.dispose()


async def seed_episodes_y_eventos(
    ctr_url: str,
) -> list[tuple[UUID, UUID, UUID, datetime, str, bool]]:
    """Genera los ~300 episodios + eventos CTR.

    Returns: lista de (episode_id, comision_id, pseudo, classified_at,
                       appropriation, include_reflexion) para alimentar a
                       seed_classifications.
    """
    engine = create_async_engine(ctr_url, pool_size=2)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    episode_refs: list[tuple[UUID, UUID, UUID, datetime, str, bool]] = []

    try:
        async with maker() as session:
            await _set_tenant(session, TENANT_UTN)

            # Limpieza idempotente — solo episodios de nuestros alumnos
            await session.execute(
                text(
                    "DELETE FROM events WHERE episode_id IN ("
                    "SELECT id FROM episodes WHERE tenant_id = :t "
                    "AND comision_id = :c "
                    "AND student_pseudonym::text LIKE 'c1c1c1c1-%'"
                    ")"
                ),
                {"t": str(TENANT_UTN), "c": str(COMISION_1)},
            )
            await session.execute(
                text(
                    "DELETE FROM episodes WHERE tenant_id = :t "
                    "AND comision_id = :c "
                    "AND student_pseudonym::text LIKE 'c1c1c1c1-%'"
                ),
                {"t": str(TENANT_UTN), "c": str(COMISION_1)},
            )
            await session.commit()

        async with maker() as session:
            await _set_tenant(session, TENANT_UTN)
            base_time = datetime.now(UTC) - timedelta(days=35)

            for student_idx, (pseudo, (cohort_label, pattern)) in enumerate(
                zip(STUDENT_PSEUDONYMS, COHORT_PATTERNS, strict=True)
            ):
                is_adverso = cohort_label == "adverso"
                for ep_idx, appropriation in enumerate(pattern):
                    # Episodio se distribuye en el tiempo: cada alumno empieza
                    # un dia distinto y va haciendo 1 episodio cada 2-3 dias
                    opened_at = base_time + timedelta(
                        days=student_idx * 0.5 + ep_idx * 3,
                        hours=(ep_idx * 4) % 24,
                    )
                    closed_at = opened_at + timedelta(
                        minutes=35 + (ep_idx * 5) % 25
                    )

                    # Episode id deterministico
                    episode_id = UUID(
                        int=(
                            0xC0DEC0DEC0DEC0DEC0DEC0DE00000000
                            | ((student_idx + 1) << 16)
                            | (ep_idx + 1)
                        )
                        & ((1 << 128) - 1)
                    )

                    # Round-robin sobre los 4 TPs disponibles
                    tp_id, tp_codigo, _ = TP_ROTATION[ep_idx % len(TP_ROTATION)]

                    # Adverso solo en el primer episodio
                    include_adverso = is_adverso and ep_idx == 0

                    # Reflexion: 50% chance, mas probable si es reflexivo
                    include_reflexion = (
                        ep_idx % 2 == 0
                        if appropriation == "apropiacion_reflexiva"
                        else ep_idx % 3 == 0
                    )

                    events = _build_events_for_episode(
                        episode_id=episode_id,
                        tenant_id=TENANT_UTN,
                        comision_id=COMISION_1,
                        student_pseudonym=pseudo,
                        problema_id=tp_id,
                        opened_at=opened_at,
                        closed_at=closed_at,
                        appropriation=appropriation,
                        include_adverso=include_adverso,
                        include_reflexion=include_reflexion,
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
                            "'closed', :oa, :ca, "
                            ":ec, :lch, false, '{}'::jsonb"
                            ")"
                        ),
                        {
                            "id": str(episode_id),
                            "t": str(TENANT_UTN),
                            "c": str(COMISION_1),
                            "s": str(pseudo),
                            "pb": str(tp_id),
                            "psh": PROMPT_SYSTEM_HASH,
                            "psv": PROMPT_SYSTEM_VERSION,
                            "cch": CLASSIFIER_CONFIG_HASH,
                            "cuch": CURSO_CONFIG_HASH,
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
                                "t": str(TENANT_UTN),
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
                        (
                            episode_id,
                            COMISION_1,
                            pseudo,
                            classified_at,
                            appropriation,
                            include_reflexion,
                        )
                    )

            await session.commit()
            print(f"[OK] {len(episode_refs)} episodios CTR generados con cadena valida")

    finally:
        await engine.dispose()

    return episode_refs


async def seed_classifications(
    classifier_url: str,
    episode_refs: list[tuple[UUID, UUID, UUID, datetime, str, bool]],
) -> None:
    """Inserta classifications coherentes con la appropriation del episodio."""
    engine = create_async_engine(classifier_url, pool_size=2)
    maker = async_sessionmaker(engine, expire_on_commit=False)

    try:
        async with maker() as session:
            await _set_tenant(session, TENANT_UTN)
            await session.execute(
                text(
                    "DELETE FROM classifications WHERE tenant_id = :t "
                    "AND comision_id = :c "
                    "AND episode_id IN :eids"
                ).bindparams(text("eids").bindparams(expanding=True)),
                {
                    "t": str(TENANT_UTN),
                    "c": str(COMISION_1),
                    "eids": tuple(str(r[0]) for r in episode_refs),
                },
            )
            await session.commit()
    except Exception:
        # El bindparam expanding puede no funcionar segun version sqla; fallback simple
        async with maker() as session:
            await _set_tenant(session, TENANT_UTN)
            for ref in episode_refs:
                await session.execute(
                    text("DELETE FROM classifications WHERE episode_id = :eid"),
                    {"eid": str(ref[0])},
                )
            await session.commit()

    try:
        async with maker() as session:
            await _set_tenant(session, TENANT_UTN)

            for ref_idx, (episode_id, comision_id, pseudo, classified_at, appropriation, _) in enumerate(
                episode_refs
            ):
                if appropriation == "apropiacion_reflexiva":
                    ct, ccd, orph, stab, evo = 0.85, 0.80, 0.05, 0.78, 0.20
                elif appropriation == "apropiacion_superficial":
                    ct, ccd, orph, stab, evo = 0.55, 0.50, 0.25, 0.55, 0.00
                else:  # delegacion_pasiva
                    ct, ccd, orph, stab, evo = 0.20, 0.25, 0.60, 0.30, -0.15

                reason = (
                    f"[UTN-COM1] Arbol N4 - {appropriation}: "
                    f"CT={ct:.2f}, CCD={ccd:.2f}, orph={orph:.2f}, "
                    f"stab={stab:.2f}, evo={evo:+.2f}"
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
                        "'{}'::jsonb, :ca, true"
                        ") ON CONFLICT (episode_id, classifier_config_hash) DO NOTHING"
                    ),
                    {
                        "eid": str(episode_id),
                        "t": str(TENANT_UTN),
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
            print(f"[OK] {len(episode_refs)} classifications generadas")

    finally:
        await engine.dispose()


# ---------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------


async def main() -> None:
    academic_url = os.environ.get(
        "ACADEMIC_DB_URL",
        "postgresql+asyncpg://postgres:postgres@localhost:5432/academic_main",
    )
    ctr_url = os.environ.get(
        "CTR_STORE_URL",
        "postgresql+asyncpg://postgres:postgres@localhost:5432/ctr_store",
    )
    classifier_url = os.environ.get(
        "CLASSIFIER_DB_URL",
        "postgresql+asyncpg://postgres:postgres@localhost:5432/classifier_db",
    )

    print("=" * 60)
    print("SEED UTN — Programacion I — Comision 1 con 30 alumnos")
    print("=" * 60)

    await seed_unidad_y_tps(academic_url)
    await seed_inscripciones(academic_url)
    episode_refs = await seed_episodes_y_eventos(ctr_url)
    await seed_classifications(classifier_url, episode_refs)

    print()
    print("=" * 60)
    print("Seed completo:")
    print(f"  - 1 unidad nueva (Variables y Tipos, orden=3)")
    print(f"  - 3 TPs publicados (TP-VAR-01/02/03)")
    print(f"  - 30 alumnos inscriptos")
    print(f"  - {len(episode_refs)} episodios CTR (cadena SHA-256 valida)")
    print(f"  - {len(episode_refs)} classifications")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
