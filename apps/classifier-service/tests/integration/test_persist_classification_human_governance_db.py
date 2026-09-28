"""Interacción entre `submit_review` (anulación humana) y
`persist_classification` (reclasificación automática) — contra Postgres real.

Bug encontrado por auditoría del orquestador sobre el informe del commit
anterior (declarado ahí como SUPUESTO, confirmado real): `persist_classification`
degradaba CUALQUIER fila `is_current=true` con hash distinto al que está
persistiendo — incluida una fila de procedencia humana, que SIEMPRE tiene un
hash distinto (el sintético de `_synthetic_review_config_hash`). Una corrida
automática posterior a una anulación humana pisaba la decisión del docente
sin error, sin log, sin marca. Con ~207 clasificaciones/día, esto no es un
escenario de laboratorio.

Regla implementada (gate 1.4 extendido): **la anulación humana gobierna hasta
que otro humano la cambie.** `is_current=true` deja de significar "la última
que corrió" y pasa a significar "la que gobierna". La reclasificación
automática posterior a una anulación humana se REGISTRA (queda persistida,
es información — el juez y el docente pueden discrepar sistemáticamente en
ese episodio, y eso es dato) pero NO gobierna: entra con `is_current=false`.

Los tres tests que pidió la ronda de revisión, en orden:
  1. Con anulación humana vigente, una reclasificación automática posterior
     NO la degrada (el test que importa — reproduce el bug exacto).
  2. La cola de revisión no vuelve a mostrar un episodio ya anulado aunque
     la máquina lo reclasifique después.
  3. El camino de idempotencia con una fila humana vigente de por medio: la
     máquina reclasifica con el MISMO hash que ya tenía antes de la
     anulación humana (episode_id, hash) ya existe como fila no-vigente).
     Sin fix, esto revienta `IntegrityError` en el UniqueConstraint.

Los tres corren contra Postgres real por la misma razón que
`test_review_service_db.py`: son afirmaciones sobre lo que la DB hace bajo
`UniqueConstraint` + RLS + UPDATE/INSERT concurrente-en-espíritu, no sobre
cómo el código da forma a filas ya decididas por un mock.
"""

from __future__ import annotations

import socket
from uuid import uuid4

import pytest
from classifier_service.services.pipeline import persist_classification
from classifier_service.services.review import list_review_queue, submit_review
from classifier_service.services.tree import ClassificationResult
from sqlalchemy import text


def _postgres_available() -> bool:
    try:
        with socket.create_connection(("127.0.0.1", 5432), timeout=1):
            return True
    except OSError:
        return False


# Duplicado a propósito — ver el comentario equivalente en
# `test_review_service_db.py` (gotcha de imports cruzados sin `__init__.py`
# de nivel superior en `tests/`).
requires_local_postgres = pytest.mark.skipif(
    not _postgres_available(),
    reason="platform-postgres no está corriendo en 127.0.0.1:5432",
)

MACHINE_HASH = "hash-maquina-v4"


def _machine_result(appropriation: str = "apropiacion_superficial") -> ClassificationResult:
    return ClassificationResult(
        appropriation=appropriation,
        reason="proxy conductual (fallback)",
        ct_summary=0.5,
        ccd_mean=0.5,
        ccd_orphan_ratio=0.3,
        cii_stability=0.4,
        cii_evolution=0.4,
        features={"needs_review": True, "needs_review_reason": "juez_eje_fino_abstencion_traza_insuficiente"},
    )


# ── Test 1 (el que importa): la reclasificación automática NO degrada ────
# a la fila humana vigente.
#
# RED verificado contra `pipeline.py::persist_classification` SIN el fix
# (commit de esta ronda, antes de tocar `pipeline.py`): los TRES tests de
# este archivo fallan en el mismo punto — el segundo `persist_classification`
# (la reclasificación automática posterior a la anulación) revienta con
#     sqlalchemy.exc.IntegrityError: ... duplicate key value violates unique
#     constraint "uq_classifications_episode_config"
# en el `flush()` del INSERT, NO en el setup del test. La causa es doble y
# las dos comparten la misma raíz (el `UPDATE` no excluye filas de
# procedencia humana): (a) el `UPDATE` original degrada la fila humana
# vigente porque su hash sintético es "otro hash", exactamente como describe
# la ronda de revisión; y (b) el `episode_id` + hash de máquina que se
# intenta insertar YA existe como fila no-vigente (la que dejó la anulación
# humana), así que el INSERT choca con el `UniqueConstraint` incluso antes de
# que la degradación (a) se note por sí sola. Esto NO es una guarda hacia
# adelante: reproduce el bug de la ronda de revisión, con síntoma incluso más
# severo que "pisa sin aviso" — acá ni siquiera llega a pisar en silencio,
# revienta la transacción.


@requires_local_postgres
@pytest.mark.asyncio
async def test_reclasificacion_automatica_no_degrada_anulacion_humana_vigente(db_session) -> None:
    session, tenant_id = db_session
    comision_id = uuid4()
    episode_id = uuid4()

    # 1. Clasificación de máquina original, marcada needs_review (como haría
    #    el pipeline real cuando el juez se abstiene).
    primera = await persist_classification(
        session=session,
        tenant_id=tenant_id,
        episode_id=episode_id,
        comision_id=comision_id,
        result=_machine_result(),
        classifier_config_hash=MACHINE_HASH,
    )
    assert primera.is_current is True

    # 2. El docente anula: reemplaza la etiqueta oficial.
    revision = await submit_review(
        session,
        tenant_id=tenant_id,
        episode_id=episode_id,
        reviewer_id=uuid4(),
        reviewer_role="docente",
        verdict="apropiacion_reflexiva",
        reason="Cita literal en el código, el juez se abstuvo de más.",
    )

    # 3. Corrida automática posterior con hash NUEVO (bump de tree_version,
    #    p.ej.) — reclasificación real, distinguible de la ruta idempotente
    #    que cubre el test 3 de este archivo (mismo hash de siempre).
    segunda_maquina = await persist_classification(
        session=session,
        tenant_id=tenant_id,
        episode_id=episode_id,
        comision_id=comision_id,
        result=_machine_result(),
        classifier_config_hash="hash-maquina-v4.1-post-anulacion",
    )

    # La fila humana SIGUE gobernando.
    humana_tras = await session.get(type(primera), revision.new_classification_id)
    await session.refresh(humana_tras)
    assert humana_tras.is_current is True, (
        "La anulación humana debe seguir gobernando (is_current=true) después "
        "de una reclasificación automática posterior. Si esto es False, el "
        "bug reportado por la ronda de revisión volvió: la máquina pisó al "
        "docente sin error, sin log, sin marca."
    )
    # La nueva fila de máquina se REGISTRA (fila nueva, hash nuevo) pero NO
    # gobierna — es información (el juez y el docente pueden discrepar), no
    # la etiqueta oficial.
    assert segunda_maquina.is_current is False
    assert segunda_maquina.id != primera.id
    assert segunda_maquina.id != humana_tras.id


# ── Test 2: la cola no vuelve a mostrar el episodio ya anulado ──────────


@requires_local_postgres
@pytest.mark.asyncio
async def test_cola_no_vuelve_a_mostrar_episodio_anulado_tras_reclasificacion(db_session) -> None:
    session, tenant_id = db_session
    comision_id = uuid4()
    episode_id = uuid4()

    await persist_classification(
        session=session,
        tenant_id=tenant_id,
        episode_id=episode_id,
        comision_id=comision_id,
        result=_machine_result(),
        classifier_config_hash=MACHINE_HASH,
    )
    await submit_review(
        session,
        tenant_id=tenant_id,
        episode_id=episode_id,
        reviewer_id=uuid4(),
        reviewer_role="docente",
        verdict="apropiacion_reflexiva",
        reason="Anulación previa a la reclasificación automática.",
    )

    # Reclasificación automática posterior — sigue marcando needs_review en
    # SU features (la máquina, si corriera de nuevo, seguiría abstiniéndose;
    # eso es correcto: es SU estado técnico, no gobierna la cola).
    await persist_classification(
        session=session,
        tenant_id=tenant_id,
        episode_id=episode_id,
        comision_id=comision_id,
        result=_machine_result(),
        classifier_config_hash=MACHINE_HASH,
    )

    items = await list_review_queue(session, comision_id=comision_id)

    assert episode_id not in {i.episode_id for i in items}


# ── Test 3: idempotencia con fila humana vigente de por medio ───────────
#
# Sin el fix, este camino no existía: el hash de máquina, tras una anulación
# humana, queda "usado" en una fila no-vigente. Una reclasificación
# posterior con ESE MISMO hash intentaría un INSERT que colisiona con
# `UniqueConstraint(episode_id, classifier_config_hash)` -> IntegrityError.


@requires_local_postgres
@pytest.mark.asyncio
async def test_idempotencia_con_hash_de_maquina_reutilizado_tras_anulacion_humana(db_session) -> None:
    session, tenant_id = db_session
    comision_id = uuid4()
    episode_id = uuid4()

    primera = await persist_classification(
        session=session,
        tenant_id=tenant_id,
        episode_id=episode_id,
        comision_id=comision_id,
        result=_machine_result(),
        classifier_config_hash=MACHINE_HASH,
    )
    await submit_review(
        session,
        tenant_id=tenant_id,
        episode_id=episode_id,
        reviewer_id=uuid4(),
        reviewer_role="docente",
        verdict="apropiacion_reflexiva",
        reason="Anulación previa.",
    )

    # Dos corridas automáticas más, mismo hash de máquina de siempre. Si
    # esto revienta con IntegrityError, el test falla ahí — no hace falta
    # un assert adicional para esa mitad del criterio.
    segunda = await persist_classification(
        session=session,
        tenant_id=tenant_id,
        episode_id=episode_id,
        comision_id=comision_id,
        result=_machine_result(),
        classifier_config_hash=MACHINE_HASH,
    )
    tercera = await persist_classification(
        session=session,
        tenant_id=tenant_id,
        episode_id=episode_id,
        comision_id=comision_id,
        result=_machine_result(),
        classifier_config_hash=MACHINE_HASH,
    )

    # La segunda corrida detecta que (episode_id, hash) ya existe (la
    # `primera`, aunque no vigente) y la devuelve tal cual — no inserta una
    # fila nueva ni la marca vigente. La tercera, ídem: devuelve la MISMA
    # fila que la segunda (no sigue multiplicando filas de máquina idénticas
    # en cada corrida).
    assert segunda.id == primera.id
    assert tercera.id == primera.id
    assert segunda.is_current is False

    rows = await session.execute(
        text("SELECT count(*) FROM classifications WHERE episode_id = :ep"),
        {"ep": str(episode_id)},
    )
    # Original (máquina) + humana. Las dos corridas "de más" con el mismo
    # hash no agregaron filas — son la misma fila devuelta de nuevo.
    assert rows.scalar_one() == 2
