"""Concurrencia entre dos `submit_review` sobre el MISMO episodio — contra
Postgres real, con dos sesiones independientes que commitean de verdad
(igual que dos requests HTTP reales), reproduciendo el hallazgo de QA
(2026-09-27, ALTA): lost update clásico.

Sin optimistic concurrency en el `UPDATE` de `submit_review`, el `WHERE`
filtraba por `episode_id` + `is_current=true` pero NO por el `id` de la fila
`previous` leída. Cuando la revisión B corre después del commit de la
revisión A, la vigente ya es la fila que dejó A — el `UPDATE` de B la
degrada a ESA (no a la que B dice haber revisado en su propio registro de
auditoría) y el resultado es incoherente: `classification_reviews` queda
con dos filas diciendo `previous=<la original>` y ninguna con
`previous=<la de A>`, que desaparece como gobernante sin que nada lo explique.

Fix: el `UPDATE` ahora incluye `Classification.id == previous.id` en el
`WHERE`. Si afecta CERO filas, alguien se adelantó — se levanta
`ReviewConflictError` (traducido a 409 por la ruta HTTP) en vez de seguir
adelante como si nada. Este archivo no usa el patrón "una sesión, nunca
commitea" del resto de `tests/integration/`: necesita DOS sesiones reales
con `commit()` real para que la condición de carrera exista. Limpia sus
propias filas al final (no dependen de rollback).

**Auditoría (2026-09-27): el primer test de este archivo NO discrimina la
causa del conflicto — corregido acá.** `test_dos_revisiones_concurrentes_no_pierden_la_primera`
sigue siendo verdadero, pero el auditor revirtió el `id == previous.id` en
una copia sombra y sus mismas aserciones (`len(results)==1`,
`len(current_ids)==1`) pasaron 10/10 veces igual. La razón: bajo
`asyncio.gather` con dos `UPDATE`s peleando por el lock de la MISMA fila
(339), Postgres bloquea al perdedor hasta que el ganador comitea, y al
reanudar reevalúa el predicado `is_current=true` SOLO contra la fila que
tenía bloqueada (339, ya `false`) — no contra la fila nueva del ganador
(340). El perdedor obtiene `rowcount==0` **por el row-lock de Postgres**,
no por mi filtro de `id`. Ese test queda documentado como lo que
efectivamente prueba (que la contienda por el MISMO row-lock no pierde la
decisión), y `test_segunda_revision_tras_commit_de_la_primera_no_pisa`
(más abajo) es el que aísla la causa real: la SEGUNDA revisión arranca
DESPUÉS de que la primera ya comiteó — sin lock que bloquee nada — y ahí
el predicado viejo SÍ matchearía la fila del ganador si el `id` no
estuviera en el `WHERE`.
"""

from __future__ import annotations

import asyncio
import socket
from uuid import uuid4

import pytest
from classifier_service.models import Classification, ClassificationReview
from classifier_service.services.pipeline import persist_classification
from classifier_service.services.review import ReviewConflictError, submit_review
from classifier_service.services.tree import ClassificationResult
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

TEST_DB_URL = "postgresql+asyncpg://classifier_user:classifier_pass@127.0.0.1:5432/classifier_db"


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


async def _run_review(
    tenant_id,
    episode_id,
    reviewer_role: str,
    verdict: str,
    idx: int,
    results: dict,
    errors: dict,
) -> None:
    """Corre `submit_review` en su PROPIA sesión/engine y commitea de
    verdad. Cada coroutine es, a todos los efectos de Postgres, un request
    HTTP independiente."""
    engine = create_async_engine(TEST_DB_URL)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        await session.execute(
            text("SELECT set_config('app.current_tenant', :t, true)"),
            {"t": str(tenant_id)},
        )
        try:
            result = await submit_review(
                session,
                tenant_id=tenant_id,
                episode_id=episode_id,
                reviewer_id=uuid4(),
                reviewer_role=reviewer_role,
                verdict=verdict,
                reason=f"revisión concurrente #{idx}",
            )
            await session.commit()
            results[idx] = result
        except ReviewConflictError as exc:
            await session.rollback()
            errors[idx] = exc
    await engine.dispose()


@requires_local_postgres
@pytest.mark.asyncio
async def test_dos_revisiones_concurrentes_no_pierden_la_primera() -> None:
    tenant_id = uuid4()
    episode_id = uuid4()
    comision_id = uuid4()

    setup_engine = create_async_engine(TEST_DB_URL)
    setup_factory = async_sessionmaker(setup_engine, expire_on_commit=False)
    try:
        async with setup_factory() as setup_session:
            await setup_session.execute(
                text("SELECT set_config('app.current_tenant', :t, true)"),
                {"t": str(tenant_id)},
            )
            setup_session.add(
                Classification(
                    tenant_id=tenant_id,
                    episode_id=episode_id,
                    comision_id=comision_id,
                    classifier_config_hash="hash-concurrencia",
                    appropriation="apropiacion_superficial",
                    appropriation_reason="original (máquina)",
                    features={"needs_review": True, "needs_review_reason": "test"},
                    is_current=True,
                )
            )
            await setup_session.commit()

        results: dict[int, object] = {}
        errors: dict[int, object] = {}

        # El cuerpo desde acá va en un único try/finally: el cleanup de
        # las filas commiteadas de verdad (`Classification`,
        # `ClassificationReview`) tiene que correr AUNQUE cualquiera de las
        # asserts de abajo falle — de lo contrario un RED deja basura en
        # `classifier_db` (pasó exactamente eso en la corrida manual de
        # verificación de esta ronda: el `finally` viejo envolvía solo el
        # bloque de lectura, no las asserts de `results`/`errors`, así que
        # un fallo ahí saltaba el cleanup entero).
        check_engine = create_async_engine(TEST_DB_URL)
        check_factory = async_sessionmaker(check_engine, expire_on_commit=False)
        try:
            await asyncio.gather(
                _run_review(tenant_id, episode_id, "docente", "apropiacion_reflexiva", 0, results, errors),
                _run_review(tenant_id, episode_id, "docente_admin", "delegacion_pasiva", 1, results, errors),
            )

            # Exactamente una tuvo éxito; la otra chocó con el conflicto de
            # concurrencia — NUNCA las dos "éxito" a la vez (eso es el lost
            # update) y NUNCA las dos en error (una de las dos SÍ tiene que
            # poder registrar su decisión).
            assert len(results) == 1, (
                f"Se esperaba exactamente 1 éxito, hubo {len(results)}. "
                f"results={results} errors={errors}"
            )
            assert len(errors) == 1
            assert isinstance(next(iter(errors.values())), ReviewConflictError)

            async with check_factory() as check_session:
                await check_session.execute(
                    text("SELECT set_config('app.current_tenant', :t, true)"),
                    {"t": str(tenant_id)},
                )
                rows = await check_session.execute(
                    select(Classification.id).where(
                        Classification.episode_id == episode_id,
                        Classification.is_current.is_(True),
                    )
                )
                current_ids = [r[0] for r in rows.all()]
                # NO cierra la hipótesis de QA sobre `MultipleResultsFound`
                # (corregido en auditoría 2026-09-27) — este test ejercita
                # dos UPDATEs peleando por el lock de la MISMA fila, y ahí
                # el row-lock de Postgres ya evita las dos filas vigentes
                # aunque el `WHERE` no tenga `id`. La hipótesis la cierra
                # (o no) `test_segunda_revision_tras_commit_de_la_primera_no_pisa`,
                # que es el escenario sin contienda de lock que QA señaló.
                assert len(current_ids) == 1, (
                    "No debe haber más de una fila is_current=true para el "
                    "episodio tras la concurrencia."
                )

                winner = next(iter(results.values()))
                assert current_ids[0] == winner.new_classification_id, (
                    "La fila vigente en DB tiene que ser la que devolvió la "
                    "revisión que ganó — ninguna otra fila puede haber "
                    "quedado vigente por error."
                )

                # `classification_reviews`: debe haber exactamente 1 fila (la
                # ganadora) apuntando a la Classification original como
                # `previous`. La que perdió NUNCA llegó a insertar su fila de
                # auditoría (levantó antes del INSERT).
                review_rows = await check_session.execute(
                    select(ClassificationReview).where(ClassificationReview.episode_id == episode_id)
                )
                reviews = review_rows.scalars().all()
                assert len(reviews) == 1
                assert reviews[0].id == winner.review_id
        finally:
            async with check_factory() as cleanup_session:
                await cleanup_session.execute(
                    text("SELECT set_config('app.current_tenant', :t, true)"),
                    {"t": str(tenant_id)},
                )
                await cleanup_session.execute(
                    delete(ClassificationReview).where(ClassificationReview.episode_id == episode_id)
                )
                await cleanup_session.execute(
                    delete(Classification).where(Classification.episode_id == episode_id)
                )
                await cleanup_session.commit()
            await check_engine.dispose()
    finally:
        await setup_engine.dispose()


async def _run_review_pausing_before_update(
    tenant_id,
    episode_id,
    reviewer_role: str,
    verdict: str,
    idx: int,
    results: dict,
    errors: dict,
    ready_event: asyncio.Event,
    resume_event: asyncio.Event,
) -> None:
    """Como `_run_review`, pero instrumenta `session.execute` para pausar la
    coroutine JUSTO DESPUÉS del SELECT que lee `previous` y ANTES del
    `UPDATE` que lo degrada. `ready_event` señala "ya leí, estoy a punto de
    escribir"; `resume_event` es la señal externa de "ya podés escribir" —
    el llamador la setea DESPUÉS de que la otra revisión ya haya comiteado.

    Es el único modo de forzar, de forma determinística (no a merced de
    cómo interlee `asyncio.gather`), el escenario que señaló la auditoría:
    esta sesión lee la fila vigente ANTES de que exista contienda alguna,
    pero escribe DESPUÉS de que la otra revisión ya es historia — sin ningún
    row-lock de por medio, porque para cuando este `UPDATE` se emite la
    transacción de la otra revisión ya cerró.
    """
    engine = create_async_engine(TEST_DB_URL)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        await session.execute(
            text("SELECT set_config('app.current_tenant', :t, true)"),
            {"t": str(tenant_id)},
        )
        original_execute = session.execute

        async def _paused_execute(stmt, *args, **kwargs):
            if str(stmt).strip().upper().startswith("UPDATE"):
                ready_event.set()
                await resume_event.wait()
            return await original_execute(stmt, *args, **kwargs)

        session.execute = _paused_execute
        try:
            result = await submit_review(
                session,
                tenant_id=tenant_id,
                episode_id=episode_id,
                reviewer_id=uuid4(),
                reviewer_role=reviewer_role,
                verdict=verdict,
                reason=f"revisión secuencial pausada #{idx}",
            )
            await session.commit()
            results[idx] = result
        except ReviewConflictError as exc:
            await session.rollback()
            errors[idx] = exc
    await engine.dispose()


@requires_local_postgres
@pytest.mark.asyncio
async def test_segunda_revision_tras_commit_de_la_primera_no_pisa() -> None:
    """El escenario que efectivamente aísla la causa (auditoría 2026-09-27,
    sección 1): B lee `previous` (fila X, `is_current=true`) ANTES de que A
    toque nada. A corre COMPLETO —SELECT, UPDATE, INSERT, commit— sin que B
    haya intentado escribir todavía (B está pausado, nunca tomó ningún
    lock). Recién ENTONCES se deja correr el `UPDATE` de B, contra un estado
    donde X ya NO es vigente (A la degradó) y la vigente es la fila que A
    dejó. No hay contienda de row-lock en ningún punto de este camino — es
    justo el caso que `test_dos_revisiones_concurrentes_no_pierden_la_primera`
    NO ejercita (ahí las dos peleaban por el lock de la MISMA fila).

    Sin `id == previous.id` en el `WHERE`, `episode_id=... AND is_current=true`
    matchearía —sin ningún lock que lo bloquee, A ya comiteó— la fila NUEVA
    de A, y B la degradaría: lost update silencioso, sin `ReviewConflictError`.
    Con el fix, `id=X AND is_current=true` no matchea NINGUNA fila (X ya es
    `false`) → `ReviewConflictError`, y la fila de A queda intacta.

    RED verificado (2026-09-27) contra una copia de `review.py` con el
    `WHERE` revertido a `episode_id + is_current` (sin `id`): este test
    FALLA — `errors` queda vacío, las dos revisiones "tienen éxito", y la
    fila vigente final es la de B (`delegacion_pasiva`) en vez de la de A
    (`apropiacion_reflexiva`) — el lost update exacto, sin ningún
    `IntegrityError` ni bloqueo de por medio. Confirma que ACÁ el fix (y no
    el row-lock, que no interviene en este camino) es lo que cierra el
    conflicto.
    """
    tenant_id = uuid4()
    episode_id = uuid4()
    comision_id = uuid4()

    setup_engine = create_async_engine(TEST_DB_URL)
    setup_factory = async_sessionmaker(setup_engine, expire_on_commit=False)
    check_engine = create_async_engine(TEST_DB_URL)
    check_factory = async_sessionmaker(check_engine, expire_on_commit=False)
    try:
        async with setup_factory() as setup_session:
            await setup_session.execute(
                text("SELECT set_config('app.current_tenant', :t, true)"),
                {"t": str(tenant_id)},
            )
            setup_session.add(
                Classification(
                    tenant_id=tenant_id,
                    episode_id=episode_id,
                    comision_id=comision_id,
                    classifier_config_hash="hash-secuencial",
                    appropriation="apropiacion_superficial",
                    appropriation_reason="original (máquina)",
                    features={"needs_review": True, "needs_review_reason": "test"},
                    is_current=True,
                )
            )
            await setup_session.commit()

        results: dict[int, object] = {}
        errors: dict[int, object] = {}
        try:
            ready_event = asyncio.Event()
            resume_event = asyncio.Event()

            b_task = asyncio.create_task(
                _run_review_pausing_before_update(
                    tenant_id,
                    episode_id,
                    "docente_admin",
                    "delegacion_pasiva",
                    1,
                    results,
                    errors,
                    ready_event,
                    resume_event,
                )
            )
            # Esperar a que B haya leído `previous` y esté parado justo
            # antes de emitir su UPDATE — todavía no tocó la fila, no tomó
            # ningún lock.
            await asyncio.wait_for(ready_event.wait(), timeout=5)

            # A corre COMPLETO: SELECT + UPDATE + INSERT + commit. B sigue
            # pausado — no hay contienda de lock posible en este punto.
            await _run_review(
                tenant_id, episode_id, "docente", "apropiacion_reflexiva", 0, results, errors
            )

            # Recién ahora se deja correr a B, contra el estado YA commiteado
            # por A.
            resume_event.set()
            await asyncio.wait_for(b_task, timeout=5)

            assert 0 in results, f"La revisión A (primera) debe tener éxito. errors={errors}"
            assert 1 in errors, (
                "La revisión B (leyó `previous` antes de que A corriera, "
                "pero escribe DESPUÉS de que A comiteó) tiene que chocar "
                f"con ReviewConflictError. results={results} errors={errors}"
            )
            assert isinstance(errors[1], ReviewConflictError)
            # Hallazgo de QA (2026-09-27, ronda 5): quien ganó la carrera fue
            # OTRO DOCENTE (A es `submit_review`, deja `revision_humana` en
            # `features`) — el mensaje no puede sonar a "el sistema
            # reclasificó", y NO hay que sugerir reintentar a ciegas: hay que
            # leer la decisión del otro antes de insistir.
            assert errors[1].retryable is False, (
                "Cuando gana OTRO DOCENTE, retryable debe ser False — "
                "reintentar a ciegas pisaría la lectura de la decisión ajena."
            )
            assert "docente" in str(errors[1]).lower()

            async with check_factory() as check_session:
                await check_session.execute(
                    text("SELECT set_config('app.current_tenant', :t, true)"),
                    {"t": str(tenant_id)},
                )
                rows = await check_session.execute(
                    select(Classification.id, Classification.appropriation).where(
                        Classification.episode_id == episode_id,
                        Classification.is_current.is_(True),
                    )
                )
                current = rows.all()
                assert len(current) == 1
                # La vigente sigue siendo la decisión de A — B nunca llegó a
                # pisarla (levantó ANTES de intentar el INSERT).
                assert current[0][0] == results[0].new_classification_id
                assert current[0][1] == "apropiacion_reflexiva"
        finally:
            async with check_factory() as cleanup_session:
                await cleanup_session.execute(
                    text("SELECT set_config('app.current_tenant', :t, true)"),
                    {"t": str(tenant_id)},
                )
                await cleanup_session.execute(
                    delete(ClassificationReview).where(ClassificationReview.episode_id == episode_id)
                )
                await cleanup_session.execute(
                    delete(Classification).where(Classification.episode_id == episode_id)
                )
                await cleanup_session.commit()
    finally:
        await setup_engine.dispose()
        await check_engine.dispose()


def _machine_result(appropriation: str = "delegacion_pasiva") -> ClassificationResult:
    return ClassificationResult(
        appropriation=appropriation,
        reason="reclasificación automática concurrente",
        ct_summary=0.5,
        ccd_mean=0.5,
        ccd_orphan_ratio=0.3,
        cii_stability=0.4,
        cii_evolution=0.4,
        features={},
    )


async def _run_persist_classification_full(
    tenant_id, episode_id, comision_id, classifier_config_hash: str
) -> None:
    """Corre `persist_classification` completo (SELECT+UPDATE+INSERT) en su
    propia sesión/engine y commitea de verdad — simula la reclasificación
    automática (worker o `classify_episode`), no una revisión humana."""
    engine = create_async_engine(TEST_DB_URL)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        await session.execute(
            text("SELECT set_config('app.current_tenant', :t, true)"),
            {"t": str(tenant_id)},
        )
        await persist_classification(
            session=session,
            tenant_id=tenant_id,
            episode_id=episode_id,
            comision_id=comision_id,
            result=_machine_result(),
            classifier_config_hash=classifier_config_hash,
        )
        await session.commit()
    await engine.dispose()


@requires_local_postgres
@pytest.mark.asyncio
async def test_conflicto_contra_reclasificacion_automatica_sugiere_reintentar() -> None:
    """La carrera en el OTRO sentido (hallazgo de QA, ronda 5, punto 1): gana
    la reclasificación AUTOMÁTICA (`persist_classification`, sin
    `revision_humana` en `features`), no otro docente. `submit_review` (B)
    lee `previous` ANTES de que la reclasificación toque nada, pero escribe
    DESPUÉS de que esa reclasificación ya comiteó — mismo patrón de pausa
    que `test_segunda_revision_tras_commit_de_la_primera_no_pisa`, ahora con
    `persist_classification` en el rol de "A".

    El dato en base queda correcto en cualquier caso (QA lo confirmó
    probando la carrera en los dos órdenes) — lo que faltaba era que el
    docente no se entere de que fue el SISTEMA el que le ganó la carrera, no
    un colega. El mensaje tiene que decirlo, y `retryable=True`: la decisión
    de este docente sigue siendo válida contra el estado nuevo (una
    reclasificación automática no "vio" nada que el docente no haya visto).

    RED verificado (ver informe): antes de este fix, `ReviewConflictError`
    no distinguía — mismo mensaje genérico y sin atributo `retryable` para
    los dos casos.
    """
    tenant_id = uuid4()
    episode_id = uuid4()
    comision_id = uuid4()

    setup_engine = create_async_engine(TEST_DB_URL)
    setup_factory = async_sessionmaker(setup_engine, expire_on_commit=False)
    check_engine = create_async_engine(TEST_DB_URL)
    check_factory = async_sessionmaker(check_engine, expire_on_commit=False)
    try:
        async with setup_factory() as setup_session:
            await setup_session.execute(
                text("SELECT set_config('app.current_tenant', :t, true)"),
                {"t": str(tenant_id)},
            )
            setup_session.add(
                Classification(
                    tenant_id=tenant_id,
                    episode_id=episode_id,
                    comision_id=comision_id,
                    classifier_config_hash="hash-maquina-original",
                    appropriation="apropiacion_superficial",
                    appropriation_reason="original (máquina)",
                    features={"needs_review": True, "needs_review_reason": "test"},
                    is_current=True,
                )
            )
            await setup_session.commit()

        results: dict[int, object] = {}
        errors: dict[int, object] = {}
        try:
            ready_event = asyncio.Event()
            resume_event = asyncio.Event()

            b_task = asyncio.create_task(
                _run_review_pausing_before_update(
                    tenant_id,
                    episode_id,
                    "docente",
                    "apropiacion_reflexiva",
                    1,
                    results,
                    errors,
                    ready_event,
                    resume_event,
                )
            )
            await asyncio.wait_for(ready_event.wait(), timeout=5)

            # La reclasificación automática corre COMPLETA — hash NUEVO
            # (config distinta, el caso real de una reclasificación real),
            # sin ningún `revision_humana` en sus `features`.
            await _run_persist_classification_full(
                tenant_id, episode_id, comision_id, "hash-maquina-reclasificada"
            )

            resume_event.set()
            await asyncio.wait_for(b_task, timeout=5)

            assert 1 in errors, f"La revisión B tiene que chocar. results={results} errors={errors}"
            error = errors[1]
            assert isinstance(error, ReviewConflictError)
            assert error.retryable is True, (
                "Cuando gana una reclasificación AUTOMÁTICA (sin "
                "revision_humana), retryable debe ser True — la decisión "
                "del docente sigue siendo válida, puede reintentar."
            )
            mensaje = str(error).lower()
            assert "sistema" in mensaje or "automátic" in mensaje, (
                f"El mensaje tiene que decir que fue el SISTEMA, no un "
                f"colega. Mensaje real: {error}"
            )
            assert "docente" not in mensaje and "colega" not in mensaje

            async with check_factory() as check_session:
                await check_session.execute(
                    text("SELECT set_config('app.current_tenant', :t, true)"),
                    {"t": str(tenant_id)},
                )
                rows = await check_session.execute(
                    select(Classification.id, Classification.features).where(
                        Classification.episode_id == episode_id,
                        Classification.is_current.is_(True),
                    )
                )
                current = rows.all()
                assert len(current) == 1
                # La ganadora es la de máquina — sin `revision_humana`.
                assert "revision_humana" not in (current[0][1] or {})
        finally:
            async with check_factory() as cleanup_session:
                await cleanup_session.execute(
                    text("SELECT set_config('app.current_tenant', :t, true)"),
                    {"t": str(tenant_id)},
                )
                await cleanup_session.execute(
                    delete(ClassificationReview).where(ClassificationReview.episode_id == episode_id)
                )
                await cleanup_session.execute(
                    delete(Classification).where(Classification.episode_id == episode_id)
                )
                await cleanup_session.commit()
    finally:
        await setup_engine.dispose()
        await check_engine.dispose()
