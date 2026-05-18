"""Tests CRUD del service de TareaPracticaTemplate (ADR-016).

Mock-based: cubre la lógica de fan-out, detección de conflicto de
`codigo` antes del INSERT, inmutabilidad de publicados, re-instanciación
condicional en `new_version`, y soft-delete que preserva las instancias.
Sigue el patrón de `test_tareas_practicas_crud.py` — no usa Postgres
real; el test de RLS a nivel DB vive en `test_rls_isolation.py`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from academic_service.auth.dependencies import User
from academic_service.models import (
    AuditLog,
    TareaPractica,
    TareaPracticaTemplate,
)
from academic_service.schemas.tarea_practica_template import (
    TareaPracticaTemplateCreate,
    TareaPracticaTemplateUpdate,
)
from academic_service.services.tarea_practica_template_service import (
    TareaPracticaTemplateService,
)
from fastapi import HTTPException

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_session():
    session = MagicMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    session.add = MagicMock()
    # execute se sobreescribe por cada test según la cadena de queries
    session.execute = AsyncMock()
    return session


def _fake_template(
    tid: UUID,
    tenant_id: UUID,
    materia_id: UUID,
    periodo_id: UUID,
    *,
    estado: str = "draft",
    version: int = 1,
    parent_template_id: UUID | None = None,
    codigo: str = "TP1",
    titulo: str = "Trabajo Práctico 1",
    enunciado: str = "Resolver...",
    inicial_codigo: str | None = None,
    rubrica: dict | None = None,
    peso: Decimal | None = None,
    fecha_inicio=None,
    fecha_fin=None,
    deleted_at=None,
) -> MagicMock:
    t = MagicMock(spec=TareaPracticaTemplate)
    t.id = tid
    t.tenant_id = tenant_id
    t.materia_id = materia_id
    t.periodo_id = periodo_id
    t.codigo = codigo
    t.titulo = titulo
    t.enunciado = enunciado
    t.inicial_codigo = inicial_codigo
    t.rubrica = rubrica
    t.peso = peso if peso is not None else Decimal("1.0")
    t.fecha_inicio = fecha_inicio
    t.fecha_fin = fecha_fin
    t.estado = estado
    t.version = version
    t.parent_template_id = parent_template_id
    t.deleted_at = deleted_at
    t.created_by = uuid4()
    return t


def _fake_tp_instance(
    tid: UUID,
    tenant_id: UUID,
    comision_id: UUID,
    template_id: UUID,
    *,
    estado: str = "draft",
    version: int = 1,
    codigo: str = "TP1",
    titulo: str = "Trabajo Práctico 1",
    enunciado: str = "Resolver...",
    inicial_codigo: str | None = None,
    rubrica: dict | None = None,
    peso: Decimal | None = None,
    has_drift: bool = False,
    deleted_at=None,
) -> MagicMock:
    t = MagicMock(spec=TareaPractica)
    t.id = tid
    t.tenant_id = tenant_id
    t.comision_id = comision_id
    t.template_id = template_id
    t.codigo = codigo
    t.titulo = titulo
    t.enunciado = enunciado
    t.inicial_codigo = inicial_codigo
    t.fecha_inicio = None
    t.fecha_fin = None
    t.peso = peso if peso is not None else Decimal("1.0")
    t.rubrica = rubrica
    t.estado = estado
    t.version = version
    t.parent_tarea_id = None
    t.has_drift = has_drift
    t.deleted_at = deleted_at
    t.created_by = uuid4()
    return t


def _scalars_result(values: list) -> MagicMock:
    """Simula el return de `session.execute(stmt)` cuando el service hace `.scalars().all()`."""
    result = MagicMock()
    scalars_obj = MagicMock()
    scalars_obj.all = MagicMock(return_value=list(values))
    result.scalars = MagicMock(return_value=scalars_obj)
    result.scalar_one_or_none = MagicMock(return_value=None)
    return result


def _audit_entries(mock_session) -> list[AuditLog]:
    return [c.args[0] for c in mock_session.add.call_args_list if isinstance(c.args[0], AuditLog)]


def _audit_actions(mock_session) -> list[str]:
    return [a.action for a in _audit_entries(mock_session)]


# ---------------------------------------------------------------------------
# create: fan-out + detección de conflicto
# ---------------------------------------------------------------------------


async def test_create_template_auto_instances_in_all_comisiones(
    mock_session, user_docente_admin_a: User, tenant_a_id: UUID
) -> None:
    """Crea 2 comisiones en (materia, periodo); al crear el template se insertan
    2 instancias de TP con `template_id` seteado y `has_drift=False`."""
    svc = TareaPracticaTemplateService(mock_session)

    materia_id = uuid4()
    periodo_id = uuid4()
    com_1 = uuid4()
    com_2 = uuid4()

    # Primera llamada execute: lookup de comisiones (scalars().all() → [com_1, com_2]).
    # Segunda: detección de conflicto (scalars().all() → []).
    mock_session.execute = AsyncMock(
        side_effect=[
            _scalars_result([com_1, com_2]),
            _scalars_result([]),
        ]
    )

    created_template = _fake_template(uuid4(), tenant_a_id, materia_id, periodo_id)
    svc.repo.create = AsyncMock(return_value=created_template)

    created_instances = []

    async def fake_tp_create(payload: dict):
        tp = _fake_tp_instance(
            payload["id"],
            payload["tenant_id"],
            payload["comision_id"],
            payload["template_id"],
        )
        created_instances.append(payload)
        return tp

    svc.tp_repo.create = AsyncMock(side_effect=fake_tp_create)

    data = TareaPracticaTemplateCreate(
        materia_id=materia_id,
        periodo_id=periodo_id,
        codigo="TP1",
        titulo="Variables y tipos",
        enunciado="Implementar...",
    )

    result = await svc.create(data, user_docente_admin_a)

    assert result is created_template
    assert len(created_instances) == 2
    assert {p["comision_id"] for p in created_instances} == {com_1, com_2}
    for p in created_instances:
        assert p["template_id"] == created_template.id
        assert p["has_drift"] is False
        assert p["codigo"] == "TP1"
        assert p["estado"] == "draft"
        assert p["version"] == 1
        assert p["parent_tarea_id"] is None
        assert p["tenant_id"] == tenant_a_id

    actions = _audit_actions(mock_session)
    # 2 audit de instancias + 1 audit del template
    assert actions.count("tarea_practica.create_from_template") == 2
    assert actions.count("tarea_practica_template.create") == 1

    # El audit del template lleva el contador correcto
    template_audit = next(
        a for a in _audit_entries(mock_session) if a.action == "tarea_practica_template.create"
    )
    assert template_audit.changes["instances_created"] == 2


async def test_create_template_no_conflict_with_existing_tps_different_code(
    mock_session, user_docente_admin_a: User, tenant_a_id: UUID
) -> None:
    """Comisión tiene TP con `codigo='X'`; creo template `codigo='Y'` → OK."""
    svc = TareaPracticaTemplateService(mock_session)

    materia_id = uuid4()
    periodo_id = uuid4()
    com_1 = uuid4()

    # Primera: 1 comisión. Segunda (filtrado por codigo='Y'): vacío → no conflict.
    mock_session.execute = AsyncMock(
        side_effect=[
            _scalars_result([com_1]),
            _scalars_result([]),
        ]
    )

    created_template = _fake_template(uuid4(), tenant_a_id, materia_id, periodo_id, codigo="Y")
    svc.repo.create = AsyncMock(return_value=created_template)
    svc.tp_repo.create = AsyncMock(
        return_value=_fake_tp_instance(uuid4(), tenant_a_id, com_1, created_template.id, codigo="Y")
    )

    data = TareaPracticaTemplateCreate(
        materia_id=materia_id,
        periodo_id=periodo_id,
        codigo="Y",
        titulo="Sin conflicto",
        enunciado="...",
    )

    result = await svc.create(data, user_docente_admin_a)

    assert result is created_template
    svc.tp_repo.create.assert_called_once()


async def test_create_template_409_on_codigo_conflict(
    mock_session, user_docente_admin_a: User, tenant_a_id: UUID
) -> None:
    """Comisión con TP `codigo='TP1'` pre-existente + nuevo template `codigo='TP1'`
    → 409 con `detail.error='codigo_conflict'`. NO se crea template ni instancias.
    """
    svc = TareaPracticaTemplateService(mock_session)

    materia_id = uuid4()
    periodo_id = uuid4()
    com_1 = uuid4()
    com_2 = uuid4()

    # Primera: 2 comisiones. Segunda: una de ellas ya tiene `codigo='TP1'`.
    mock_session.execute = AsyncMock(
        side_effect=[
            _scalars_result([com_1, com_2]),
            _scalars_result([com_1]),
        ]
    )

    svc.repo.create = AsyncMock()
    svc.tp_repo.create = AsyncMock()

    data = TareaPracticaTemplateCreate(
        materia_id=materia_id,
        periodo_id=periodo_id,
        codigo="TP1",
        titulo="Colisionante",
        enunciado="...",
    )

    with pytest.raises(HTTPException) as exc_info:
        await svc.create(data, user_docente_admin_a)

    assert exc_info.value.status_code == 409
    detail = exc_info.value.detail
    assert isinstance(detail, dict)
    assert detail["error"] == "codigo_conflict"
    assert str(com_1) in detail["comisiones"]
    assert len(detail["comisiones"]) == 1

    # Rollback: ni el template ni las instancias se crearon
    svc.repo.create.assert_not_called()
    svc.tp_repo.create.assert_not_called()

    # Y no hay audit logs (no se alcanzó el add del template)
    assert _audit_actions(mock_session) == []


# ---------------------------------------------------------------------------
# update / publish / archive
# ---------------------------------------------------------------------------


async def test_update_template_rejects_if_published(
    mock_session, user_docente_admin_a: User, tenant_a_id: UUID
) -> None:
    """Template publicado → 409 en update."""
    svc = TareaPracticaTemplateService(mock_session)

    tid = uuid4()
    published = _fake_template(tid, tenant_a_id, uuid4(), uuid4(), estado="published")
    svc.repo.get_by_id = AsyncMock(return_value=published)

    patch = TareaPracticaTemplateUpdate(titulo="No puedo")
    with pytest.raises(HTTPException) as exc_info:
        await svc.update(tid, patch, user_docente_admin_a)

    assert exc_info.value.status_code == 409
    # No debe haber audit log de update
    assert "tarea_practica_template.update" not in _audit_actions(mock_session)


async def test_publish_template_does_not_publish_instances(
    mock_session, user_docente_admin_a: User, tenant_a_id: UUID
) -> None:
    """publish(template) marca el template como published pero NO toca instancias.

    Se verifica: (a) state del template → published; (b) `tp_repo.create`
    no se invoca en publish; (c) la instancia mockeada sigue en `draft`
    (el service nunca accede a ella).
    """
    svc = TareaPracticaTemplateService(mock_session)

    tid = uuid4()
    template = _fake_template(tid, tenant_a_id, uuid4(), uuid4(), estado="draft")
    svc.repo.get_by_id = AsyncMock(return_value=template)

    # Instancia ficticia — el service NO debería tocarla
    instance = _fake_tp_instance(uuid4(), tenant_a_id, uuid4(), tid, estado="draft")
    svc.tp_repo.create = AsyncMock()

    result = await svc.publish(tid, user_docente_admin_a)

    assert result is template
    assert template.estado == "published"
    assert instance.estado == "draft"  # sigue intacta
    svc.tp_repo.create.assert_not_called()
    assert _audit_actions(mock_session) == ["tarea_practica_template.publish"]


# ---------------------------------------------------------------------------
# new_version: re-instanciación condicional
# ---------------------------------------------------------------------------


async def test_new_version_reinstance_non_drifted(
    mock_session, user_docente_admin_a: User, tenant_a_id: UUID
) -> None:
    """new_version(reinstance_non_drifted=True) crea TP nueva solo para instancias
    sin drift; la drifted queda intacta."""
    svc = TareaPracticaTemplateService(mock_session)

    materia_id = uuid4()
    periodo_id = uuid4()
    old_template_id = uuid4()
    parent = _fake_template(
        old_template_id,
        tenant_a_id,
        materia_id,
        periodo_id,
        estado="published",
        version=1,
    )
    svc.repo.get_by_id = AsyncMock(return_value=parent)

    new_template_id = uuid4()
    new_template = _fake_template(
        new_template_id,
        tenant_a_id,
        materia_id,
        periodo_id,
        estado="draft",
        version=2,
        parent_template_id=old_template_id,
        titulo="v2 Titulo",
    )
    svc.repo.create = AsyncMock(return_value=new_template)

    # Dos instancias del template viejo: una drifted, otra no
    com_a = uuid4()
    com_b = uuid4()
    inst_clean = _fake_tp_instance(
        uuid4(),
        tenant_a_id,
        com_a,
        old_template_id,
        estado="published",
        version=1,
        has_drift=False,
    )
    inst_drift = _fake_tp_instance(
        uuid4(),
        tenant_a_id,
        com_b,
        old_template_id,
        estado="published",
        version=1,
        has_drift=True,
    )

    # session.execute es llamado una vez por el service para listar las instancias
    mock_session.execute = AsyncMock(return_value=_scalars_result([inst_clean, inst_drift]))

    created_tp_payloads = []

    async def fake_tp_create(payload):
        created_tp_payloads.append(payload)
        return _fake_tp_instance(
            payload["id"],
            payload["tenant_id"],
            payload["comision_id"],
            payload["template_id"],
            version=payload["version"],
        )

    svc.tp_repo.create = AsyncMock(side_effect=fake_tp_create)

    patch = TareaPracticaTemplateUpdate(titulo="v2 Titulo")
    result = await svc.new_version(
        old_template_id,
        patch,
        user_docente_admin_a,
        reinstance_non_drifted=True,
    )

    assert result is new_template
    # Sólo la instancia limpia se re-instancia
    assert len(created_tp_payloads) == 1
    p = created_tp_payloads[0]
    assert p["comision_id"] == com_a
    assert p["template_id"] == new_template_id
    assert p["parent_tarea_id"] == inst_clean.id
    assert p["version"] == inst_clean.version + 1
    assert p["has_drift"] is False
    assert p["titulo"] == "v2 Titulo"
    assert p["codigo"] == parent.codigo

    # Audit log del new_version con reinstanced_count=1
    nv_audit = next(
        a for a in _audit_entries(mock_session) if a.action == "tarea_practica_template.new_version"
    )
    assert nv_audit.changes["reinstanced_count"] == 1
    assert nv_audit.changes["old_id"] == str(old_template_id)
    assert nv_audit.changes["new_id"] == str(new_template_id)


# ---------------------------------------------------------------------------
# soft_delete: no toca instancias
# ---------------------------------------------------------------------------


async def test_soft_delete_does_not_delete_instances(
    mock_session, user_docente_admin_a: User, tenant_a_id: UUID
) -> None:
    """soft_delete del template marca `deleted_at` pero las TPs siguen vivas."""
    svc = TareaPracticaTemplateService(mock_session)

    tid = uuid4()
    template = _fake_template(tid, tenant_a_id, uuid4(), uuid4(), estado="draft")
    svc.repo.get_by_id = AsyncMock(return_value=template)

    # Dos instancias vivas — el service las usa solo para contar
    instances_alive = [
        _fake_tp_instance(uuid4(), tenant_a_id, uuid4(), tid),
        _fake_tp_instance(uuid4(), tenant_a_id, uuid4(), tid),
    ]
    svc.repo.list_instances = AsyncMock(return_value=instances_alive)

    async def fake_soft_delete(session, obj):
        obj.deleted_at = datetime.now(UTC)

    svc.repo.soft_delete = AsyncMock(side_effect=fake_soft_delete)

    result = await svc.soft_delete(tid, user_docente_admin_a)

    assert result is template
    assert template.deleted_at is not None

    # Instancias NO se tocaron (siguen con deleted_at None)
    for inst in instances_alive:
        assert inst.deleted_at is None

    # Audit log con instances_remaining=2
    delete_audit = next(
        a for a in _audit_entries(mock_session) if a.action == "tarea_practica_template.delete"
    )
    assert delete_audit.changes["instances_remaining"] == 2
    assert delete_audit.changes["template_id"] == str(tid)
