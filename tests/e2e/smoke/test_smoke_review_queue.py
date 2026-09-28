"""Smoke — flujo completo de revisión humana (B3+B5, remediaciones-mtac-b2-b5).

Tarea 8.1 del change: episodio que deriva a revisión porque el juez no pudo
resolverlo -> aparece en la cola -> un docente lo revisa -> sale de la cola
con historial. Las piezas de este flujo (juez trivaluado, cola, endpoint de
revisión, anti-join) están probadas por separado contra Postgres real, pero
tres informes seguidos de este change declararon sin cubrir la composición
bajo el ROUTER completo del api-gateway: auth real + `tenant_session` real +
`clasificar_regimen_llm` real (LLM_PROVIDER=mock) + `persist_classification`
real + `submit_review` real, todo en un solo proceso vivo. Esto SÍ lo cubre.

Cómo se deriva "el juez no pudo resolverlo" sin controlar el LLM: con
`LLM_PROVIDER=mock` (default de dev, ver CLAUDE.md "Comandos"), el ai-gateway
devuelve `"[mock respuesta para: ...]"` — NO es JSON. `clasificar_regimen_llm`
(`regimen_llm.py`) no puede parsearlo tras los reintentos y degrada a estado
`error_parseo`, que entra por el mismo fallback (`_marcar_para_revision`) que
la abstención por traza insuficiente (caso 4 de la Tabla 3.11): conserva la
etiqueta del proxy conductual y marca `features['needs_review']=True`. Es el
camino determinista y reproducible para ejercitar "el juez no pudo
resolverlo" sin necesitar un LLM real ni mockear código en proceso.

Setup de datos: el episodio de prueba se inserta DIRECTO en `ctr_store` (no
vía tutor-service) porque la persistencia de eventos depende de los partition
workers async (single-writer, ver limitación declarada en README.md) que no
están garantizados en el ambiente de smoke. El insert replica el patrón ya
usado por `scripts/seed-smoke.py` (misma función de hashing SHA-256 real de
`ctr_service.services.hashing`), con eventos elegidos a propósito para caer
en el subgrupo `desenganchado` (`prompts=1`, poco trabajo) — es uno de los
tres subgrupos de `SUBGRUPOS_JUZGADOS_POR_JUEZ`, así que el juez SÍ corre.

Tenant/comisión/episodio son UUIDs frescos por test (no el tenant demo
compartido): la auth de classifier-service y ctr-service es 100% por headers
X-* (sin lookup a academic-service para roles `docente_admin`/`superadmin`,
ver `CTR_OVERSIGHT_ROLES`), así que no hace falta ninguna fila académica
preexistente. Usar un tenant fresco también evita que una resolución BYOK
del tenant demo (fuera del control de este test) interfiera con el mock del
ai-gateway.

Declarado explícitamente FUERA de este smoke (por qué, no silencio): que la
anulación humana siga gobernando frente a una reclasificación automática
POSTERIOR con un `classifier_config_hash` NUEVO (bump de `tree_version`) está
cubierto por `apps/classifier-service/tests/integration/test_classify_episode_review_composition_e2e_db.py`,
que mockea `compute_classifier_config_hash` para forzar el segundo hash. Un
smoke caja-negra no puede forzar ese segundo hash sin reiniciar el proceso
con otro `tree_version` — `classify_episode` es determinista dado el mismo
código corriendo, así que un segundo POST siempre pega el mismo hash y cae en
el atajo de idempotencia (200 no-op), sin ejercitar la exclusión de la fila
humana en `persist_classification`. Lo que SÍ prueba este smoke: la fila de
revisión gobierna (`is_current=true`, `appropriation` reemplazada) inmediata-
mente después de la revisión, bajo el router real.

Limpieza: cada test escribe en `ctr_store` y `classifier_db` (episodio real +
eventos + classifications + classification_reviews) y lo borra en un único
`finally` que envuelve TODO el cuerpo del test, asserts incluidos — dos
incidentes de este mismo change (ver tasks.md, 5.9/5.10) dejaron residuos
porque el `finally` envolvía solo una parte del cuerpo y un RED se lo
saltaba.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

import httpx
import psycopg2
import pytest
from _helpers import PG_CONN_STR, tail_log

# `ctr_service` vive en apps/ctr-service/src — el conftest.py RAIZ del repo
# (no el de esta carpeta) agrega src/ de cada paquete al sys.path, pero solo
# corre si pytest arranca desde la raíz del repo (que es como lo invoca
# `make test-smoke`). Import defensivo por las dudas, mismo patrón que
# `scripts/seed-smoke.py`.
_CTR_SRC = Path(__file__).resolve().parents[3] / "apps" / "ctr-service" / "src"
if str(_CTR_SRC) not in sys.path:
    sys.path.insert(0, str(_CTR_SRC))

from ctr_service.services.hashing import (
    GENESIS_HASH,
    compute_chain_hash,
    compute_self_hash,
)


def _pg_write(dbname: str, sql: str, params: dict) -> None:
    """INSERT/UPDATE/DELETE de una sola sentencia, con commit.

    Deliberadamente separado de `_helpers.fetch_pg` (que NUNCA commitea — es
    de sólo lectura por diseño). Este test es la excepción documentada: no
    existe otro camino para sembrar eventos CTR sin depender de los
    partition workers (ver docstring del módulo).
    """
    conn = psycopg2.connect(f"{PG_CONN_STR}/{dbname}")
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
        conn.commit()
    finally:
        conn.close()


def _pg_fetch_one(dbname: str, sql: str, params: dict) -> tuple | None:
    conn = psycopg2.connect(f"{PG_CONN_STR}/{dbname}")
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchone()
    finally:
        conn.close()


def _headers(role: str, *, tenant_id: UUID, user_id: UUID) -> dict[str, str]:
    """Headers X-* que el api-gateway acepta en dev mode (DEV_TRUST_HEADERS).

    `docente_admin` en vez de `docente` a propósito: cae en
    `CTR_OVERSIGHT_ROLES` (ctr-service) y evita el gate A0.6 de membership de
    comisión, que exige una fila real en `usuarios_comision` (academic_main)
    que este test no siembra — el tenant es fresco y no tiene jerarquía
    académica. Sigue siendo uno de los `REVIEW_ROLES` del classifier.
    """
    return {
        "X-User-Id": str(user_id),
        "X-Tenant-Id": str(tenant_id),
        "X-User-Email": f"{role}@smoke.test",
        "X-User-Roles": role,
    }


def _seed_episode_desenganchado(
    *, tenant_id: UUID, comision_id: UUID, episode_id: UUID
) -> None:
    """Inserta episodio + 5 eventos reales (hash-chain SHA-256 válida) en
    `ctr_store`, directo en la base — ver docstring del módulo para el
    porqué (partition workers no garantizados en smoke).

    Eventos elegidos para que `clasificar_subgrupo` (subgrupo.py) devuelva
    `desenganchado`: 1 prompt (rama con-tutor), 0 ediciones y 1 ejecución
    (`poco_trabajo = ediciones < EDIT_MIN and ejec < TRABADO_MIN_EJEC` →
    True), sin `solicitud_directa` ni overuse. `desenganchado` está en
    `SUBGRUPOS_JUZGADOS_POR_JUEZ` (regimen_llm.py) — el juez SÍ corre.
    """
    student_pseudonym = uuid4()
    problema_id = uuid4()
    opened_at = datetime.now(UTC) - timedelta(minutes=45)
    closed_at = datetime.now(UTC)

    specs = [
        {
            "event_type": "episodio_abierto",
            "ts": opened_at,
            "payload": {
                "student_pseudonym": str(student_pseudonym),
                "problema_id": str(problema_id),
                "comision_id": str(comision_id),
                "curso_config_hash": "smoke-curso-hash",
            },
        },
        {
            "event_type": "prompt_enviado",
            "ts": opened_at + timedelta(minutes=5),
            "payload": {
                "content": "no entiendo el enunciado",
                "prompt_kind": "aclaracion_enunciado",
                "chunks_used_hash": None,
            },
        },
        {
            "event_type": "tutor_respondio",
            "ts": opened_at + timedelta(minutes=6),
            "payload": {
                "content": "pensemos juntos",
                "model_used": "mock",
                "socratic_compliance": None,
                "violations": [],
            },
        },
        {
            "event_type": "codigo_ejecutado",
            "ts": opened_at + timedelta(minutes=20),
            "payload": {
                "passed": 1,
                "failed": 1,
                "total": 2,
                "stdout": "ok\nfail",
                "failed_test_names": ["t1"],
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

    events: list[dict] = []
    prev_chain = GENESIS_HASH
    for seq, spec in enumerate(specs):
        event_uuid = UUID(int=(episode_id.int ^ (seq + 1) * 0x9E3779B97F4A7C15) & ((1 << 128) - 1))
        canonical = {
            "event_uuid": str(event_uuid),
            "episode_id": str(episode_id),
            "tenant_id": str(tenant_id),
            "seq": seq,
            "event_type": spec["event_type"],
            "ts": cast("datetime", spec["ts"]).isoformat().replace("+00:00", "Z"),
            "payload": spec["payload"],
            "prompt_system_hash": "smoke-prompt-hash",
            "prompt_system_version": "v1.0.1",
            "classifier_config_hash": "smoke-classifier-hash",
        }
        self_hash = compute_self_hash(canonical)
        chain_hash = compute_chain_hash(self_hash, prev_chain)
        events.append(
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

    _pg_write(
        "ctr_store",
        "INSERT INTO episodes (id, tenant_id, comision_id, student_pseudonym, problema_id, "
        "prompt_system_hash, prompt_system_version, classifier_config_hash, curso_config_hash, "
        "estado, opened_at, closed_at, events_count, last_chain_hash, integrity_compromised, meta) "
        "VALUES (%(id)s, %(t)s, %(c)s, %(s)s, %(pb)s, %(psh)s, %(psv)s, %(cch)s, %(cuch)s, "
        "%(estado)s, %(oa)s, %(ca)s, %(ec)s, %(lch)s, false, '{}'::jsonb)",
        {
            "id": str(episode_id),
            "t": str(tenant_id),
            "c": str(comision_id),
            "s": str(student_pseudonym),
            "pb": str(problema_id),
            "psh": "smoke-prompt-hash",
            "psv": "v1.0.1",
            "cch": "smoke-classifier-hash",
            "cuch": "smoke-curso-hash",
            "estado": "closed",
            "oa": opened_at,
            "ca": closed_at,
            "ec": len(events),
            "lch": events[-1]["chain_hash"],
        },
    )
    for ev in events:
        _pg_write(
            "ctr_store",
            "INSERT INTO events (event_uuid, tenant_id, episode_id, seq, event_type, ts, payload, "
            "self_hash, chain_hash, prev_chain_hash, prompt_system_hash, prompt_system_version, "
            "classifier_config_hash) VALUES (%(euid)s, %(t)s, %(eid)s, %(seq)s, %(et)s, %(ts)s, "
            "%(pl)s::jsonb, %(sh)s, %(ch)s, %(pch)s, %(psh)s, %(psv)s, %(cch)s)",
            {
                "euid": str(ev["event_uuid"]),
                "t": str(tenant_id),
                "eid": str(episode_id),
                "seq": ev["seq"],
                "et": ev["event_type"],
                "ts": ev["ts_dt"],
                "pl": json.dumps(ev["payload"]),
                "sh": ev["self_hash"],
                "ch": ev["chain_hash"],
                "pch": ev["prev_chain_hash"],
                "psh": "smoke-prompt-hash",
                "psv": "v1.0.1",
                "cch": "smoke-classifier-hash",
            },
        )


def _cleanup_episode(episode_id: UUID) -> None:
    """Borra TODO lo que este test pudo haber escrito, en las dos bases.

    Best-effort por sentencia (no todas las filas existen siempre — depende
    de en qué paso falló el test), pero cada DELETE individual sigue
    fallando ruidoso si la sentencia SQL está mal — no hay un `except` amplio
    acá adentro.
    """
    _pg_write(
        "classifier_db",
        "DELETE FROM classification_reviews WHERE episode_id = %(eid)s",
        {"eid": str(episode_id)},
    )
    _pg_write(
        "classifier_db",
        "DELETE FROM classifications WHERE episode_id = %(eid)s",
        {"eid": str(episode_id)},
    )
    _pg_write(
        "ctr_store",
        "DELETE FROM events WHERE episode_id = %(eid)s",
        {"eid": str(episode_id)},
    )
    _pg_write(
        "ctr_store",
        "DELETE FROM episodes WHERE id = %(eid)s",
        {"eid": str(episode_id)},
    )


@pytest.mark.smoke
def test_episodio_deriva_a_revision_aparece_en_cola_docente_revisa_sale_con_historial(
    client: httpx.Client,
) -> None:
    """Flujo completo de la tarea 8.1, bajo el router real del api-gateway.

    1. Episodio con subgrupo `desenganchado` (con-tutor, juzgado por el LLM).
    2. POST classify_episode -> el juez (mock, no devuelve JSON) degrada a
       `error_parseo` -> `needs_review=True`, `appropriation` sigue siendo
       la del proxy conductual (el LLM NUNCA gobierna con un veredicto no-ok).
    3. GET review-queue -> el episodio aparece, con el motivo real.
    4. POST review con un verdict fuera de dominio -> 400, Y el episodio
       SIGUE en la cola (el 400 no debe tener efecto secundario).
    5. POST review válido -> 201 con historial (review_id, previous/new
       classification_id distintos) -> la fila de `classification_reviews`
       existe de verdad (leída por separado, sólo lectura).
    6. GET review-queue -> el episodio YA NO aparece (needs_review limpio).
    7. Anti-join aislado (mismo hallazgo que el audit de la tarea 5.9): si
       una fila vigente tuviera `needs_review=true` PERO ya existe una fila
       en `classification_reviews` para ese episodio, la cola igual la
       excluye — el anti-join solo, sin el needs_review limpio, alcanza.
    """
    tenant_id = uuid4()
    comision_id = uuid4()
    docente_id = uuid4()
    episode_id = uuid4()
    headers = _headers("docente_admin", tenant_id=tenant_id, user_id=docente_id)

    try:
        _seed_episode_desenganchado(
            tenant_id=tenant_id, comision_id=comision_id, episode_id=episode_id
        )

        # 2. Clasificar bajo el router real.
        classify_resp = client.post(
            f"/api/v1/classify_episode/{episode_id}", headers=headers
        )
        assert classify_resp.status_code == 201, (
            f"POST classify_episode debería 201 para un episodio nuevo. "
            f"status={classify_resp.status_code} body={classify_resp.text[:400]}\n\n"
            f"classifier-service.log:\n{tail_log('classifier-service')}"
        )

        current = client.get(f"/api/v1/classifications/{episode_id}", headers=headers)
        assert current.status_code == 200, current.text[:300]
        current_body = current.json()
        assert current_body["regimen_llm"] is not None, (
            "el juez debería haber corrido (subgrupo desenganchado está en "
            f"SUBGRUPOS_JUZGADOS_POR_JUEZ). body={current_body}"
        )
        assert current_body["regimen_llm"]["estado"] != "ok", (
            "con LLM_PROVIDER=mock el juez NUNCA debería devolver un veredicto "
            f"usable (el mock no emite JSON). estado={current_body['regimen_llm']['estado']}"
        )
        # El fallback conserva la etiqueta del proxy conductual — el juez NO
        # gobierna con un veredicto no-ok (contrato v4.0.0, classify_ep.py).
        assert current_body["appropriation"] == "apropiacion_superficial", (
            f"subgrupo desenganchado -> proxy superficial; el juez no-ok NO debe "
            f"sustituirlo. body={current_body}"
        )

        # 3. Aparece en la cola.
        queue_resp = client.get(
            "/api/v1/classifications/review-queue",
            params={"comision_id": str(comision_id)},
            headers=headers,
        )
        assert queue_resp.status_code == 200, queue_resp.text[:300]
        queue_body = queue_resp.json()
        queue_episode_ids = {item["episode_id"] for item in queue_body["items"]}
        assert str(episode_id) in queue_episode_ids, (
            f"el episodio derivado por el juez debería estar en la cola. "
            f"queue={queue_body}"
        )
        item = next(i for i in queue_body["items"] if i["episode_id"] == str(episode_id))
        assert item["needs_review_reason"], "la cola debe traer el motivo real, no vacío"

        # 4. Verdict fuera de dominio -> 400, SIN sacarlo de la cola.
        bad_review = client.post(
            f"/api/v1/classifications/{episode_id}/review",
            json={"verdict": "banana", "reason": "smoke: verdict inválido"},
            headers=headers,
        )
        assert bad_review.status_code == 400, (
            f"un verdict fuera del dominio conocido debe dar 400, nunca 500 ni "
            f"persistir. status={bad_review.status_code} body={bad_review.text[:300]}"
        )
        queue_after_bad = client.get(
            "/api/v1/classifications/review-queue",
            params={"comision_id": str(comision_id)},
            headers=headers,
        )
        assert str(episode_id) in {
            i["episode_id"] for i in queue_after_bad.json()["items"]
        }, "el 400 no debe tener efecto secundario: el episodio sigue en la cola"

        # 5. Revisión válida -> historial.
        review_resp = client.post(
            f"/api/v1/classifications/{episode_id}/review",
            json={
                "verdict": "apropiacion_reflexiva",
                "reason": "smoke: el docente revisa y anula la etiqueta del juez",
            },
            headers=headers,
        )
        assert review_resp.status_code == 201, (
            f"POST review válido debería 201. "
            f"status={review_resp.status_code} body={review_resp.text[:400]}"
        )
        review_body = review_resp.json()
        assert review_body["previous_classification_id"] != review_body["new_classification_id"], (
            "la revisión debe crear una fila NUEVA (ADR-010, append-only), "
            f"nunca reusar la anterior. body={review_body}"
        )

        # Historial real en `classification_reviews` — lectura directa (no hay
        # endpoint GET para esta tabla; confirmamos que el INSERT pasó).
        review_row = _pg_fetch_one(
            "classifier_db",
            "SELECT id, reviewer_role, verdict FROM classification_reviews "
            "WHERE id = %(rid)s",
            {"rid": review_body["review_id"]},
        )
        assert review_row is not None, "la fila de historial debería existir en classifier_db"
        assert review_row[1] == "docente_admin"
        assert review_row[2] == "apropiacion_reflexiva"

        # La etiqueta oficial quedó reemplazada (gate 1.4: reemplaza, no
        # queda al lado).
        current_after_review = client.get(
            f"/api/v1/classifications/{episode_id}", headers=headers
        )
        assert current_after_review.json()["appropriation"] == "apropiacion_reflexiva"

        # 6. Sale de la cola (needs_review limpio en la fila nueva).
        queue_after_review = client.get(
            "/api/v1/classifications/review-queue",
            params={"comision_id": str(comision_id)},
            headers=headers,
        )
        assert str(episode_id) not in {
            i["episode_id"] for i in queue_after_review.json()["items"]
        }, "un episodio ya revisado no debe seguir en la cola (needs_review limpio)"

        # 7. Anti-join aislado: si la fila vigente tuviera needs_review=true
        # PERO ya hay una fila en classification_reviews para el episodio, la
        # cola igual debe excluirlo (mismo hallazgo que el audit de 5.9 sobre
        # `~ya_revisado`). Forzamos ese estado a mano — es la ÚNICA forma de
        # ejercitar el anti-join aislado del mecanismo de needs_review, que
        # `submit_review` siempre limpia junto con la marca.
        _pg_write(
            "classifier_db",
            "UPDATE classifications SET features = features || '{\"needs_review\": true}'::jsonb "
            "WHERE episode_id = %(eid)s AND is_current = true",
            {"eid": str(episode_id)},
        )
        queue_after_forced_flag = client.get(
            "/api/v1/classifications/review-queue",
            params={"comision_id": str(comision_id)},
            headers=headers,
        )
        assert str(episode_id) not in {
            i["episode_id"] for i in queue_after_forced_flag.json()["items"]
        }, (
            "aunque la fila vigente tenga needs_review=true, el anti-join contra "
            "classification_reviews debe excluirla solo — si esto falla, alguien "
            "sacó `~ya_revisado` de `list_review_queue` (review.py)"
        )
    finally:
        _cleanup_episode(episode_id)

# ─────────────────────────────────────────────────────────────────────────────
# `test_dos_revisiones_concurrentes_dan_409_y_distinguen_retryable` VIVIA ACA
# y se saco el 2026-09-28, en la review del PR #96.
#
# Por que se saco: era NO DETERMINISTA por construccion, y encima con el modelo
# equivocado del contrato. Cuando las dos requests corren en SERIE —que es lo
# habitual— la segunda lee la fila que la primera acaba de escribir, la pisa
# legitimamente, y las dos devuelven 201. Eso NO es un bug: es la concurrencia
# optimista funcionando, y es para lo que existe la segunda FK del diseno.
# El 409 solo aparece si B leyo ANTES de que A commiteara.
#
# El test asertaba `[409, 201]` y `review_count == 1`; en el camino secuencial
# son `[201, 201]` y 2. El CI lo tumbo en la primera corrida, con razon.
#
# El docstring del propio test declaraba 1 fallo en 13 corridas con cliente por
# request y 0 en 8 con cliente compartido. **0 de 8 no es prueba de nada**, y un
# test no determinista en el smoke convierte en moneda al aire la red que
# bloquea el merge de TODOS los demas PRs.
#
# La garantia es real y tiene casa determinista, donde el row-lock de Postgres
# hace el trabajo en vez del azar:
#   apps/classifier-service/tests/integration/test_submit_review_concurrency_db.py
#     ::test_dos_revisiones_concurrentes_no_pierden_la_primera
#     ::test_segunda_revision_tras_commit_de_la_primera_no_pisa
#
# Si alguien quiere volver a cubrir esto desde el smoke, el camino NO es
# reintentar hasta que pinte: es forzar el interleaving, y eso no se hace por
# HTTP contra un stack real.
# ─────────────────────────────────────────────────────────────────────────────
