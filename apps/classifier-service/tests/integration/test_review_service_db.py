"""Tests del SERVICE LAYER de revisión humana (`classifier_service.services.review`)
contra Postgres real (`classifier_db` local, contenedor `platform-postgres`).

Por qué contra DB real y no mocks: la consulta de la cola (D7.c) filtra por
una clave de JSONB (`features->>'needs_review'`) más un anti-join contra
`classification_reviews` — mockear `session.execute` para devolver "lo que la
query debería traer" no ejercita el filtro en sí, solo la forma en que el
service da forma a filas ya filtradas. Los criterios de aceptación de la
tarea 5.9 ("la cola devuelve los retenidos y SOLO los retenidos") son
afirmaciones sobre el filtro SQL, no sobre el shaping en Python.

Seguridad: cada test abre su propia sesión, hace SET LOCAL app.current_tenant
con un tenant_id aleatorio (uuid4, no colisiona con datos existentes) y
NUNCA commitea — solo `flush()` dentro de la transacción y `rollback()` al
final del test (fixture `db_session`). No se persiste nada. Se corre contra
`classifier_db` del contenedor de desarrollo local (`platform-postgres`),
NO contra la base del piloto — confirmado por medición directa (2026-09-27):
esta base local tiene 106 clasificaciones sembradas por los scripts de seed,
`features={}` en las 106, cero con clave `needs_review`. Los 47 retenidos
vigentes que cita la propuesta viven en una base a la que este entorno no
tiene acceso (ver informe del implementador, tarea 5.10).

Requiere Docker con `platform-postgres` corriendo y la migración
`20260906_0006_add_classification_reviews` aplicada. Se salta automáticamente
si no hay conexión.
"""

from __future__ import annotations

import socket
from uuid import uuid4

import pytest
from sqlalchemy import text

from classifier_service.models import Classification, ClassificationReview
from classifier_service.services.review import (
    ReviewTargetNotFoundError,
    list_review_queue,
    submit_review,
)


def _postgres_available() -> bool:
    try:
        with socket.create_connection(("127.0.0.1", 5432), timeout=1):
            return True
    except OSError:
        return False


# Duplicado a propósito en cada archivo de este directorio (mismo criterio
# que `_make_classification` duplicado entre `test_classify_episode_idempotent.py`
# y `test_persist_classification_idempotent.py`): un import cruzado entre
# módulos de test bajo un paquete `tests/` sin `__init__.py` de nivel
# superior (gotcha documentado en CLAUDE.md) es más fragil que 5 líneas
# repetidas. La fixture `db_session`, en cambio, SÍ se compila sola desde
# `conftest.py` — eso es autodiscovery de pytest, no un import de Python.
requires_local_postgres = pytest.mark.skipif(
    not _postgres_available(),
    reason="platform-postgres no está corriendo en 127.0.0.1:5432",
)


def _classification(
    *,
    tenant_id,
    episode_id,
    comision_id,
    needs_review: bool,
    is_current: bool = True,
    classifier_config_hash: str = "hash-maquina-v4",
    regimen_llm: dict | None = None,
) -> Classification:
    features: dict = {}
    if needs_review:
        features["needs_review"] = True
        features["needs_review_reason"] = "juez_eje_fino_abstencion_traza_insuficiente"
    if regimen_llm is not None:
        features["regimen_llm"] = regimen_llm
    return Classification(
        tenant_id=tenant_id,
        episode_id=episode_id,
        comision_id=comision_id,
        classifier_config_hash=classifier_config_hash,
        appropriation="apropiacion_superficial",
        appropriation_reason="proxy conductual (fallback)",
        features=features,
        is_current=is_current,
    )


# ── Criterio 5.9 #1: la cola devuelve los retenidos y SOLO los retenidos ──


@requires_local_postgres
@pytest.mark.asyncio
async def test_cola_devuelve_retenidos_y_solo_los_retenidos(db_session) -> None:
    session, tenant_id = db_session
    comision_id = uuid4()

    retenido = uuid4()
    no_retenido = uuid4()
    retenido_pero_superado = uuid4()

    session.add(_classification(tenant_id=tenant_id, episode_id=retenido, comision_id=comision_id, needs_review=True))
    session.add(_classification(tenant_id=tenant_id, episode_id=no_retenido, comision_id=comision_id, needs_review=False))
    # is_current=False: fue retenido en su momento pero una fila más nueva lo superó.
    session.add(
        _classification(
            tenant_id=tenant_id,
            episode_id=retenido_pero_superado,
            comision_id=comision_id,
            needs_review=True,
            is_current=False,
        )
    )
    session.add(
        _classification(
            tenant_id=tenant_id,
            episode_id=retenido_pero_superado,
            comision_id=comision_id,
            needs_review=False,
            is_current=True,
            # Distinto hash: es la ÚNICA forma en que dos filas de un mismo
            # episodio coexisten bajo `uq_classifications_episode_config`
            # (una reclasificación real con config nueva, no una revisión
            # humana — esa usa el hash sintético de `submit_review`).
            classifier_config_hash="hash-maquina-v4-reclasificado",
        )
    )
    await session.flush()

    items = await list_review_queue(session)

    episode_ids = {i.episode_id for i in items}
    assert episode_ids == {retenido}


# ── Criterio 5.9 #2: una revisión lo saca de la cola ──────────────────────


@requires_local_postgres
@pytest.mark.asyncio
async def test_una_revision_saca_el_episodio_de_la_cola(db_session) -> None:
    session, tenant_id = db_session
    comision_id = uuid4()
    episode_id = uuid4()

    session.add(_classification(tenant_id=tenant_id, episode_id=episode_id, comision_id=comision_id, needs_review=True))
    await session.flush()

    antes = await list_review_queue(session)
    assert episode_id in {i.episode_id for i in antes}

    await submit_review(
        session,
        tenant_id=tenant_id,
        episode_id=episode_id,
        reviewer_id=uuid4(),
        reviewer_role="docente",
        verdict="apropiacion_reflexiva",
        reason="Reviso evidencia y el episodio sí cita literalmente.",
    )

    despues = await list_review_queue(session)
    assert episode_id not in {i.episode_id for i in despues}


# ── Criterio 5.9 #3: un segundo POST apila historial, no lo pisa ─────────


@requires_local_postgres
@pytest.mark.asyncio
async def test_segunda_revision_apila_historial_en_vez_de_pisarlo(db_session) -> None:
    session, tenant_id = db_session
    comision_id = uuid4()
    episode_id = uuid4()
    regimen_llm_original = {"estado": "abstencion_traza_insuficiente", "prompt_version": "eje_fino_v1.2.0"}

    session.add(
        _classification(
            tenant_id=tenant_id,
            episode_id=episode_id,
            comision_id=comision_id,
            needs_review=True,
            regimen_llm=regimen_llm_original,
        )
    )
    await session.flush()

    primera = await submit_review(
        session,
        tenant_id=tenant_id,
        episode_id=episode_id,
        reviewer_id=uuid4(),
        reviewer_role="docente",
        verdict="apropiacion_reflexiva",
        reason="Primera revisión.",
    )
    segunda = await submit_review(
        session,
        tenant_id=tenant_id,
        episode_id=episode_id,
        reviewer_id=uuid4(),
        reviewer_role="docente_admin",
        verdict="apropiacion_superficial",
        reason="La primera revisión se equivocó, corrijo.",
    )

    # Nunca UPDATE de una revisión existente: dos filas, no una.
    assert primera.review_id != segunda.review_id

    # La segunda revisión encadena sobre la Classification que dejó la primera.
    assert segunda.previous_classification_id == primera.new_classification_id

    # Las TRES Classification (original + 2 reemplazos) siguen existiendo:
    # append-only en `classifications` significa que nunca se borran filas,
    # solo se marca is_current=false (D7, corrección sobre la premisa falsa
    # de "append-only estricto" — el patrón real es UPDATE+INSERT).
    rows = await session.execute(
        text("SELECT count(*) FROM classifications WHERE episode_id = :ep"),
        {"ep": str(episode_id)},
    )
    assert rows.scalar_one() == 3

    # El estado técnico del juez NO se sobrescribe con ninguna revisión
    # humana (gate 1.4: dos campos de estado, no uno) — sigue siendo el de
    # la clasificación ORIGINAL de la máquina en la fila final.
    final = await session.execute(
        text("SELECT features FROM classifications WHERE id = :id"),
        {"id": segunda.new_classification_id},
    )
    final_features = final.scalar_one()
    assert final_features["regimen_llm"] == regimen_llm_original
    # Y la marca de procedencia humana (D7.b) apunta a ESTA revisión.
    assert final_features["revision_humana"]["review_id"] == segunda.review_id


# ── Auditoría (2026-09-27): el anti-join en sí, aislado de los otros dos ──
# mecanismos que ya podrían sacar un episodio de la cola sin que el
# anti-join intervenga.
#
# El auditor borró `~ya_revisado` de `list_review_queue` y los 214 tests
# pasaron igual: `test_una_revision_saca_el_episodio_de_la_cola` pasa porque
# `submit_review` borra `needs_review` de `features` (mecanismo 1), y
# `test_cola_no_vuelve_a_mostrar_episodio_anulado_tras_reclasificacion`
# (en `test_persist_classification_human_governance_db.py`) pasa porque la
# fila de máquina reclasificada entra con `is_current=false` (mecanismo 2).
# Ninguno de los dos ejercita el `NOT EXISTS` contra `classification_reviews`
# en sí. Este test construye el ÚNICO caso donde el anti-join es la ÚNICA
# razón por la que el episodio no aparece: `needs_review` SIGUE puesto,
# `is_current` SIGUE en `true`, y hay una fila en `classification_reviews`
# para ese episodio (sin pasar por `submit_review` — a propósito, para no
# heredar sus efectos secundarios sobre `features`).


@requires_local_postgres
@pytest.mark.asyncio
async def test_anti_join_aislado_needs_review_puesto_e_is_current_true(db_session) -> None:
    session, tenant_id = db_session
    comision_id = uuid4()
    episode_id = uuid4()

    classification = _classification(
        tenant_id=tenant_id, episode_id=episode_id, comision_id=comision_id, needs_review=True
    )
    session.add(classification)
    await session.flush()

    # Confirmar el setup: SIN la fila de revisión, este episodio SÍ entra a
    # la cola (si esto fallara, sería un fallo de SETUP, no del anti-join).
    antes = await list_review_queue(session)
    assert episode_id in {i.episode_id for i in antes}

    # Fila de revisión directa (sin `submit_review`, a propósito: no
    # queremos que borre `needs_review` ni cambie `is_current` — eso
    # activaría los otros dos mecanismos y volvería a ocultar el aislamiento).
    session.add(
        ClassificationReview(
            tenant_id=tenant_id,
            episode_id=episode_id,
            reviewer_id=uuid4(),
            reviewer_role="docente",
            previous_classification_id=classification.id,
            new_classification_id=None,
            verdict="apropiacion_reflexiva",
            reason="revisión insertada directamente, sin pasar por submit_review",
        )
    )
    await session.flush()

    # `needs_review` SIGUE puesto y `is_current` SIGUE true — si el
    # episodio desaparece de la cola ahora, es EXCLUSIVAMENTE por el
    # anti-join.
    check = await session.execute(
        text(
            "SELECT is_current, features->>'needs_review' FROM classifications "
            "WHERE id = :id"
        ),
        {"id": classification.id},
    )
    is_current_db, needs_review_db = check.one()
    assert is_current_db is True
    assert needs_review_db == "true"

    despues = await list_review_queue(session)
    assert episode_id not in {i.episode_id for i in despues}, (
        "El episodio tiene needs_review=true e is_current=true — la ÚNICA "
        "razón por la que puede estar fuera de la cola es el anti-join "
        "contra classification_reviews. Si esto falla, el anti-join no "
        "está haciendo nada."
    )


# ── Filtro por comisión (tarea 5.3) ───────────────────────────────────────


@requires_local_postgres
@pytest.mark.asyncio
async def test_filtro_por_comision(db_session) -> None:
    session, tenant_id = db_session
    comision_a = uuid4()
    comision_b = uuid4()
    episodio_a = uuid4()
    episodio_b = uuid4()

    session.add(_classification(tenant_id=tenant_id, episode_id=episodio_a, comision_id=comision_a, needs_review=True))
    session.add(_classification(tenant_id=tenant_id, episode_id=episodio_b, comision_id=comision_b, needs_review=True))
    await session.flush()

    items = await list_review_queue(session, comision_id=comision_a)

    assert {i.episode_id for i in items} == {episodio_a}


# ── Sin clasificación vigente para el episodio ────────────────────────────


@requires_local_postgres
@pytest.mark.asyncio
async def test_submit_review_sin_clasificacion_vigente_lanza_error(db_session) -> None:
    session, tenant_id = db_session

    with pytest.raises(ReviewTargetNotFoundError):
        await submit_review(
            session,
            tenant_id=tenant_id,
            episode_id=uuid4(),
            reviewer_id=uuid4(),
            reviewer_role="docente",
            verdict="apropiacion_reflexiva",
            reason="no debería llegar a ejecutar nada",
        )
