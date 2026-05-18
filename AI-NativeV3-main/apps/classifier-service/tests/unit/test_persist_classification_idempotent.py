"""Tests de idempotencia de `persist_classification` (deuda QA 2026-05-07).

Cubren la regla del ADR-010 + el bug documentado en CLAUDE.md:
> POST /classify_episode/{id} no es idempotente: re-POST devuelve 500 con
> duplicate-key, deberia responder no-op con la classification existente.

Escenarios:
  - Test A: primera persistencia (no existe fila previa) -> INSERT nueva.
  - Test B: segunda persistencia con MISMO classifier_config_hash ->
    no-op idempotente, devuelve la existente sin INSERT (no se viola el
    UniqueConstraint(episode_id, classifier_config_hash)).
  - Test C: segunda persistencia con OTRO classifier_config_hash
    (simula bump de LABELER_VERSION o profile distinto) -> marca la vieja
    is_current=false e INSERTA la nueva (append-only ADR-010). Cross-version
    NO es idempotente, eso es comportamiento correcto.

Estrategia: mockeamos `AsyncSession` (el handler corre con session real
contra Postgres en runtime, pero la logica de SELECT-then-decide es DB-
agnostica y testeable a nivel unitario). El test simula los 3 paths de
ramas dentro de `persist_classification`.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

from classifier_service.models import Classification
from classifier_service.services.pipeline import (
    compute_classifier_config_hash,
    persist_classification,
)
from classifier_service.services.tree import (
    DEFAULT_REFERENCE_PROFILE,
    ClassificationResult,
)

# ── Helpers ──────────────────────────────────────────────────────────────


def _make_result() -> ClassificationResult:
    return ClassificationResult(
        appropriation="apropiacion_superficial",
        reason="caso de prueba",
        ct_summary=0.5,
        ccd_mean=0.5,
        ccd_orphan_ratio=0.3,
        cii_stability=0.4,
        cii_evolution=0.4,
        features={"k": 1},
    )


def _make_classification(
    *,
    episode_id: UUID,
    tenant_id: UUID,
    comision_id: UUID,
    classifier_config_hash: str,
    is_current: bool = True,
) -> Classification:
    """Construye una fila Classification "como si viniera de la DB", con
    todos los campos materializados (no la pasamos por session.add → flush).
    """
    return Classification(
        id=42,
        tenant_id=tenant_id,
        episode_id=episode_id,
        comision_id=comision_id,
        classifier_config_hash=classifier_config_hash,
        appropriation="apropiacion_superficial",
        appropriation_reason="caso de prueba",
        ct_summary=0.5,
        ccd_mean=0.5,
        ccd_orphan_ratio=0.3,
        cii_stability=0.4,
        cii_evolution=0.4,
        features={"k": 1},
        is_current=is_current,
    )


def _make_session_returning(existing: Classification | None) -> Any:
    """Mock de AsyncSession.

    - `session.execute(SELECT...)` devuelve un Result cuyo
      `scalar_one_or_none()` retorna `existing` (la fila previa o None).
    - `session.execute(UPDATE...)` se traga sin payload.
    - `session.add(obj)` se registra en `session.added_rows` para asserts.
    - `session.flush()` es no-op (no asignamos id real porque no se usa).
    """
    session = MagicMock()
    session.added_rows = []

    def _add(obj: Any) -> None:
        session.added_rows.append(obj)

    session.add = _add
    session.flush = AsyncMock(return_value=None)

    select_result = MagicMock()
    select_result.scalar_one_or_none = MagicMock(return_value=existing)
    update_result = MagicMock()

    session.execute_calls: list[Any] = []

    async def _execute(stmt: Any, *args: Any, **kwargs: Any) -> Any:
        session.execute_calls.append(stmt)
        # Distingue SELECT vs UPDATE por el tipo del statement.
        # Los SELECT que hace persist_classification piden una columna
        # de Classification; los UPDATE setean values. Heuristica simple:
        # si el statement tiene atributo `_returning_clauses` o el repr
        # contiene "UPDATE", es un update.
        repr_stmt = str(stmt)
        if repr_stmt.strip().startswith("UPDATE"):
            return update_result
        return select_result

    session.execute = _execute
    return session


# ── Test A: primera persistencia ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_idempotent_persist_inserta_cuando_no_existe() -> None:
    """Test A: primera persistencia → INSERT (path normal)."""
    tenant_id = uuid4()
    episode_id = uuid4()
    comision_id = uuid4()
    config_hash = compute_classifier_config_hash(DEFAULT_REFERENCE_PROFILE, "v1.0.0")
    result = _make_result()

    session = _make_session_returning(existing=None)

    persisted = await persist_classification(
        session=session,
        tenant_id=tenant_id,
        episode_id=episode_id,
        comision_id=comision_id,
        result=result,
        classifier_config_hash=config_hash,
    )

    # Se agregó UNA fila nueva
    assert len(session.added_rows) == 1
    new = session.added_rows[0]
    assert new is persisted
    assert new.episode_id == episode_id
    assert new.classifier_config_hash == config_hash
    assert new.is_current is True
    # flush() se llamó (persistencia real)
    session.flush.assert_awaited()


# ── Test B: re-persistencia con MISMO hash es idempotente ───────────────


@pytest.mark.asyncio
async def test_idempotent_persist_no_op_cuando_existe_misma_config() -> None:
    """Test B: misma `(episode_id, classifier_config_hash)` con
    `is_current=true` → devuelve la existente, NO ejecuta INSERT.

    Esto cierra el bug 500 duplicate-key del POST /classify_episode/{id}.
    """
    tenant_id = uuid4()
    episode_id = uuid4()
    comision_id = uuid4()
    config_hash = compute_classifier_config_hash(DEFAULT_REFERENCE_PROFILE, "v1.0.0")
    result = _make_result()

    existing = _make_classification(
        episode_id=episode_id,
        tenant_id=tenant_id,
        comision_id=comision_id,
        classifier_config_hash=config_hash,
        is_current=True,
    )
    session = _make_session_returning(existing=existing)

    persisted = await persist_classification(
        session=session,
        tenant_id=tenant_id,
        episode_id=episode_id,
        comision_id=comision_id,
        result=result,
        classifier_config_hash=config_hash,
    )

    # CRITICA: NO se agregó ninguna fila nueva
    assert session.added_rows == [], (
        "persist_classification no debe ejecutar INSERT cuando ya existe "
        "una fila con el mismo (episode_id, classifier_config_hash) e "
        "is_current=true. Hacer INSERT viola el UniqueConstraint y rompe "
        "el contrato de idempotencia (deuda QA 2026-05-07)."
    )
    # NO se llamó flush (no hay nada que flushear)
    session.flush.assert_not_awaited()
    # Devuelve la fila existente — mismo objeto
    assert persisted is existing
    assert persisted.classifier_config_hash == config_hash
    assert persisted.is_current is True


# ── Test C: re-persistencia con OTRO hash hace reclasificación ──────────


@pytest.mark.asyncio
async def test_idempotent_persist_reclasifica_cuando_cambia_hash() -> None:
    """Test C: misma `episode_id` pero DISTINTO `classifier_config_hash`
    (ej. bump de LABELER_VERSION o profile cambiado) → marca la vieja
    is_current=false + INSERT nueva. Cross-version NO es idempotente
    por diseño, esto es comportamiento correcto (ADR-010).
    """
    tenant_id = uuid4()
    episode_id = uuid4()
    comision_id = uuid4()
    old_hash = compute_classifier_config_hash(DEFAULT_REFERENCE_PROFILE, "v1.0.0")
    new_hash = compute_classifier_config_hash(DEFAULT_REFERENCE_PROFILE, "v1.1.0")
    assert old_hash != new_hash  # sanity
    result = _make_result()

    # SELECT con NEW hash → no encuentra (por eso reclasifica).
    # El UPDATE marca el viejo (con OLD hash) is_current=false.
    session = _make_session_returning(existing=None)

    persisted = await persist_classification(
        session=session,
        tenant_id=tenant_id,
        episode_id=episode_id,
        comision_id=comision_id,
        result=result,
        classifier_config_hash=new_hash,
    )

    # Se agregó UNA fila nueva con el NEW hash
    assert len(session.added_rows) == 1
    new_row = session.added_rows[0]
    assert new_row.classifier_config_hash == new_hash
    assert new_row.is_current is True
    assert persisted is new_row
    # Ejecutó al menos 2 statements: 1 SELECT (idempotency check) +
    # 1 UPDATE (marcar vieja) + (puede haber más). Verificamos que hubo
    # un UPDATE en la traza de calls.
    has_update = any(
        str(stmt).strip().startswith("UPDATE") for stmt in session.execute_calls
    )
    assert has_update, (
        "Reclasificación con hash distinto debe emitir UPDATE para marcar "
        "la fila vieja como is_current=false (ADR-010 append-only)."
    )
    session.flush.assert_awaited()
