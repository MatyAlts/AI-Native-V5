"""Tests CRUD del service de Tarea Práctica (TP).

Mock-based: cubre lógica de dominio (validación FK comisión, audit log,
inmutabilidad de versiones publicadas, soft delete, filtros, RLS por
tenant) sin requerir Postgres real. Sigue el estilo de
test_facultades_crud.py.

El test de RLS multi-tenant a nivel DB vive en test_rls_isolation.py.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from academic_service.auth.dependencies import User
from academic_service.models import AuditLog, Comision, TareaPractica
from academic_service.schemas.tarea_practica import (
    TareaPracticaCreate,
    TareaPracticaUpdate,
)
from academic_service.services.tarea_practica_service import TareaPracticaService
from fastapi import HTTPException
from pydantic import ValidationError


@pytest.fixture
def mock_session():
    session = MagicMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    session.add = MagicMock()
    return session


def _fake_comision(cid: UUID, tenant_id: UUID) -> MagicMock:
    c = MagicMock(spec=Comision)
    c.id = cid
    c.tenant_id = tenant_id
    c.codigo = "COM-1"
    return c


def _fake_tarea(
    tid: UUID,
    tenant_id: UUID,
    comision_id: UUID,
    estado: str = "draft",
    **kw,
) -> MagicMock:
    t = MagicMock(spec=TareaPractica)
    t.id = tid
    t.tenant_id = tenant_id
    t.comision_id = comision_id
    t.codigo = kw.get("codigo", "TP1")
    t.titulo = kw.get("titulo", "Trabajo Práctico 1")
    t.enunciado = kw.get("enunciado", "Resolver el problema...")
    t.inicial_codigo = kw.get("inicial_codigo")
    t.fecha_inicio = kw.get("fecha_inicio")
    t.fecha_fin = kw.get("fecha_fin")
    t.peso = kw.get("peso", Decimal("1.0"))
    t.rubrica = kw.get("rubrica")
    t.estado = estado
    t.version = kw.get("version", 1)
    t.parent_tarea_id = kw.get("parent_tarea_id")
    t.template_id = kw.get("template_id")
    t.has_drift = kw.get("has_drift", False)
    t.created_by = kw.get("created_by", uuid4())
    t.deleted_at = kw.get("deleted_at")
    return t


async def test_create_happy_path(
    mock_session, user_docente_admin_a: User, tenant_a_id: UUID
) -> None:
    """POST devuelve TP en draft con version=1 y registra audit log (RN-016)."""
    svc = TareaPracticaService(mock_session)

    comision_id = uuid4()
    comision = _fake_comision(comision_id, tenant_a_id)
    svc.comisiones.get_or_404 = AsyncMock(return_value=comision)

    fake_tarea = _fake_tarea(uuid4(), tenant_a_id, comision_id)
    svc.repo.create = AsyncMock(return_value=fake_tarea)

    data = TareaPracticaCreate(
        comision_id=comision_id,
        codigo="TP1",
        titulo="Variables y tipos",
        enunciado="Implementar...",
    )

    result = await svc.create(data, user_docente_admin_a)

    assert result is fake_tarea
    svc.repo.create.assert_called_once()
    create_payload = svc.repo.create.call_args.args[0]
    assert create_payload["estado"] == "draft"
    assert create_payload["version"] == 1
    assert create_payload["parent_tarea_id"] is None
    assert create_payload["created_by"] == user_docente_admin_a.id
    assert create_payload["tenant_id"] == tenant_a_id

    audit_calls = [
        c.args[0] for c in mock_session.add.call_args_list if isinstance(c.args[0], AuditLog)
    ]
    assert len(audit_calls) == 1
    audit = audit_calls[0]
    assert audit.action == "tarea_practica.create"
    assert audit.resource_type == "tarea_practica"
    assert audit.tenant_id == tenant_a_id


async def test_create_comision_inexistente_404(mock_session, user_docente_admin_a: User) -> None:
    """Si la comisión no existe, propaga HTTPException 404."""
    svc = TareaPracticaService(mock_session)

    svc.comisiones.get_or_404 = AsyncMock(
        side_effect=HTTPException(status_code=404, detail="Comisión no encontrada")
    )

    data = TareaPracticaCreate(
        comision_id=uuid4(),
        codigo="TP1",
        titulo="Fantasma",
        enunciado="...",
    )

    with pytest.raises(HTTPException) as exc_info:
        await svc.create(data, user_docente_admin_a)

    assert exc_info.value.status_code == 404


async def test_create_otra_universidad_403(
    mock_session, user_docente_admin_a: User, tenant_b_id: UUID
) -> None:
    """Cross-tenant: si el repo (con RLS simulada) niega el acceso a una
    comisión de otra universidad devolviendo 404, el service propaga.

    En producción el RLS impide al user del tenant A leer comisiones del
    tenant B; el repo devuelve 404. Reproducimos eso acá.
    """
    svc = TareaPracticaService(mock_session)

    svc.comisiones.get_or_404 = AsyncMock(
        side_effect=HTTPException(status_code=404, detail="Comisión no encontrada")
    )

    data = TareaPracticaCreate(
        comision_id=uuid4(),
        codigo="TP1",
        titulo="Cross-tenant",
        enunciado="...",
    )

    with pytest.raises(HTTPException) as exc_info:
        await svc.create(data, user_docente_admin_a)

    assert exc_info.value.status_code == 404


async def test_list_filtra_por_comision(
    mock_session, user_docente_admin_a: User, tenant_a_id: UUID
) -> None:
    """list(comision_id=X) propaga el filtro al repo."""
    svc = TareaPracticaService(mock_session)

    target_comision = uuid4()
    fake = [_fake_tarea(uuid4(), tenant_a_id, target_comision)]
    svc.repo.list = AsyncMock(return_value=fake)

    result = await svc.list(comision_id=target_comision, limit=50)

    assert result == fake
    svc.repo.list.assert_called_once_with(
        limit=50, cursor=None, filters={"comision_id": target_comision}
    )


async def test_list_filtra_por_estado(mock_session, tenant_a_id: UUID) -> None:
    """list(estado=draft) propaga el filtro."""
    svc = TareaPracticaService(mock_session)

    fake = [_fake_tarea(uuid4(), tenant_a_id, uuid4(), estado="draft")]
    svc.repo.list = AsyncMock(return_value=fake)

    result = await svc.list(estado="draft", limit=50)

    assert result == fake
    svc.repo.list.assert_called_once_with(limit=50, cursor=None, filters={"estado": "draft"})


async def test_get_one_404(mock_session) -> None:
    """get(id) propaga 404 cuando el repo no encuentra el row."""
    svc = TareaPracticaService(mock_session)

    svc.repo.get_or_404 = AsyncMock(
        side_effect=HTTPException(status_code=404, detail="TareaPractica no encontrada")
    )

    with pytest.raises(HTTPException) as exc_info:
        await svc.get(uuid4())

    assert exc_info.value.status_code == 404


async def test_update_happy_path_solo_si_draft(
    mock_session, user_docente_admin_a: User, tenant_a_id: UUID
) -> None:
    """PATCH sobre TP en draft aplica los cambios y registra audit log."""
    svc = TareaPracticaService(mock_session)

    tid = uuid4()
    obj = _fake_tarea(tid, tenant_a_id, uuid4(), estado="draft", titulo="Vieja")
    svc.repo.get_or_404 = AsyncMock(return_value=obj)

    data = TareaPracticaUpdate(titulo="Nueva versión")
    result = await svc.update(tid, data, user_docente_admin_a)

    assert result.titulo == "Nueva versión"

    audit_calls = [
        c.args[0] for c in mock_session.add.call_args_list if isinstance(c.args[0], AuditLog)
    ]
    assert len(audit_calls) == 1
    assert audit_calls[0].action == "tarea_practica.update"
    assert audit_calls[0].resource_id == tid


async def test_update_published_falla_409(
    mock_session, user_docente_admin_a: User, tenant_a_id: UUID
) -> None:
    """PATCH sobre TP publicada retorna 409 (inmutabilidad)."""
    svc = TareaPracticaService(mock_session)

    tid = uuid4()
    obj = _fake_tarea(tid, tenant_a_id, uuid4(), estado="published")
    svc.repo.get_or_404 = AsyncMock(return_value=obj)

    data = TareaPracticaUpdate(titulo="Cambio prohibido")

    with pytest.raises(HTTPException) as exc_info:
        await svc.update(tid, data, user_docente_admin_a)

    assert exc_info.value.status_code == 409
    # No debe haber audit log de update sobre published
    audit_updates = [
        c.args[0]
        for c in mock_session.add.call_args_list
        if isinstance(c.args[0], AuditLog) and c.args[0].action == "tarea_practica.update"
    ]
    assert len(audit_updates) == 0


async def test_soft_delete(mock_session, user_docente_admin_a: User, tenant_a_id: UUID) -> None:
    """DELETE invoca repo.soft_delete y registra audit log."""
    svc = TareaPracticaService(mock_session)

    tid = uuid4()
    obj = _fake_tarea(tid, tenant_a_id, uuid4())
    svc.repo.soft_delete = AsyncMock(return_value=obj)

    result = await svc.soft_delete(tid, user_docente_admin_a)

    assert result is obj
    svc.repo.soft_delete.assert_called_once_with(tid)

    audit_calls = [
        c.args[0] for c in mock_session.add.call_args_list if isinstance(c.args[0], AuditLog)
    ]
    assert len(audit_calls) == 1
    assert audit_calls[0].action == "tarea_practica.delete"
    assert audit_calls[0].changes == {"soft_delete": True}


async def test_rls_isolation(
    mock_session,
    user_docente_admin_a: User,
    user_docente_admin_b: User,
    tenant_a_id: UUID,
    tenant_b_id: UUID,
) -> None:
    """Aislamiento por tenant a nivel service.

    Cada service escribe audit logs con el tenant_id de SU user; el repo
    del tenant B retorna vacío al listar TPs creadas por A (RLS simulada).
    El aislamiento real a nivel DB lo cubre test_rls_isolation.py.
    """
    svc_a = TareaPracticaService(mock_session)
    comision_a_id = uuid4()
    comision_a = _fake_comision(comision_a_id, tenant_a_id)
    svc_a.comisiones.get_or_404 = AsyncMock(return_value=comision_a)
    svc_a.repo.create = AsyncMock(return_value=_fake_tarea(uuid4(), tenant_a_id, comision_a_id))

    await svc_a.create(
        TareaPracticaCreate(
            comision_id=comision_a_id,
            codigo="TP1",
            titulo="Solo A",
            enunciado="...",
        ),
        user_docente_admin_a,
    )

    svc_b = TareaPracticaService(mock_session)
    svc_b.repo.list = AsyncMock(return_value=[])

    result = await svc_b.list(comision_id=comision_a_id, limit=50)

    assert result == []

    audit_logs = [
        c.args[0] for c in mock_session.add.call_args_list if isinstance(c.args[0], AuditLog)
    ]
    assert all(a.tenant_id == tenant_a_id for a in audit_logs)
    assert not any(a.tenant_id == tenant_b_id for a in audit_logs)


# ---------------------------------------------------------------------------
# Versionado: publish / archive / new_version / list_versions
# ---------------------------------------------------------------------------


def _audit_actions(mock_session) -> list[str]:
    return [
        c.args[0].action for c in mock_session.add.call_args_list if isinstance(c.args[0], AuditLog)
    ]


async def test_publish_draft_to_published_happy_path(
    mock_session, user_docente_admin_a: User, tenant_a_id: UUID
) -> None:
    """publish() sobre draft setea estado=published y registra audit log."""
    svc = TareaPracticaService(mock_session)

    tid = uuid4()
    obj = _fake_tarea(tid, tenant_a_id, uuid4(), estado="draft")
    svc.repo.get_or_404 = AsyncMock(return_value=obj)

    result = await svc.publish(tid, user_docente_admin_a)

    assert result is obj
    assert obj.estado == "published"

    actions = _audit_actions(mock_session)
    assert actions == ["tarea_practica.publish"]


async def test_publish_already_published_es_idempotente(
    mock_session, user_docente_admin_a: User, tenant_a_id: UUID
) -> None:
    """publish() sobre ya publicada devuelve la tarea sin error ni audit log."""
    svc = TareaPracticaService(mock_session)

    tid = uuid4()
    obj = _fake_tarea(tid, tenant_a_id, uuid4(), estado="published")
    svc.repo.get_or_404 = AsyncMock(return_value=obj)

    result = await svc.publish(tid, user_docente_admin_a)

    assert result is obj
    assert obj.estado == "published"
    assert _audit_actions(mock_session) == []


async def test_publish_archived_falla_409(
    mock_session, user_docente_admin_a: User, tenant_a_id: UUID
) -> None:
    """publish() sobre archived retorna 409 (transición inválida)."""
    svc = TareaPracticaService(mock_session)

    tid = uuid4()
    obj = _fake_tarea(tid, tenant_a_id, uuid4(), estado="archived")
    svc.repo.get_or_404 = AsyncMock(return_value=obj)

    with pytest.raises(HTTPException) as exc_info:
        await svc.publish(tid, user_docente_admin_a)

    assert exc_info.value.status_code == 409
    assert _audit_actions(mock_session) == []


async def test_archive_published_to_archived_happy_path(
    mock_session, user_docente_admin_a: User, tenant_a_id: UUID
) -> None:
    """archive() sobre published setea estado=archived y registra audit log."""
    svc = TareaPracticaService(mock_session)

    tid = uuid4()
    obj = _fake_tarea(tid, tenant_a_id, uuid4(), estado="published")
    svc.repo.get_or_404 = AsyncMock(return_value=obj)

    result = await svc.archive(tid, user_docente_admin_a)

    assert result is obj
    assert obj.estado == "archived"
    assert _audit_actions(mock_session) == ["tarea_practica.archive"]


async def test_archive_draft_falla_409(
    mock_session, user_docente_admin_a: User, tenant_a_id: UUID
) -> None:
    """archive() sobre draft retorna 409 (debe publicar primero)."""
    svc = TareaPracticaService(mock_session)

    tid = uuid4()
    obj = _fake_tarea(tid, tenant_a_id, uuid4(), estado="draft")
    svc.repo.get_or_404 = AsyncMock(return_value=obj)

    with pytest.raises(HTTPException) as exc_info:
        await svc.archive(tid, user_docente_admin_a)

    assert exc_info.value.status_code == 409
    assert _audit_actions(mock_session) == []


async def test_archive_already_archived_falla_409(
    mock_session, user_docente_admin_a: User, tenant_a_id: UUID
) -> None:
    """archive() sobre archived retorna 409 (no idempotente)."""
    svc = TareaPracticaService(mock_session)

    tid = uuid4()
    obj = _fake_tarea(tid, tenant_a_id, uuid4(), estado="archived")
    svc.repo.get_or_404 = AsyncMock(return_value=obj)

    with pytest.raises(HTTPException) as exc_info:
        await svc.archive(tid, user_docente_admin_a)

    assert exc_info.value.status_code == 409
    assert _audit_actions(mock_session) == []


async def test_new_version_de_published_crea_nuevo_draft(
    mock_session, user_docente_admin_a: User, tenant_a_id: UUID
) -> None:
    """new_version() sobre published crea nueva fila con version=2, parent_id."""
    svc = TareaPracticaService(mock_session)

    parent_id = uuid4()
    comision_id = uuid4()
    parent = _fake_tarea(
        parent_id,
        tenant_a_id,
        comision_id,
        estado="published",
        version=1,
        codigo="TP1",
        titulo="Original",
        enunciado="enunciado v1",
    )
    svc.repo.get_or_404 = AsyncMock(return_value=parent)

    new_tarea_mock = _fake_tarea(
        uuid4(),
        tenant_a_id,
        comision_id,
        estado="draft",
        version=2,
        parent_tarea_id=parent_id,
        codigo="TP1",
        titulo="Nueva v2",
    )
    svc.repo.create = AsyncMock(return_value=new_tarea_mock)

    patch = TareaPracticaUpdate(titulo="Nueva v2")
    result = await svc.new_version(parent_id, patch, user_docente_admin_a)

    assert result is new_tarea_mock
    svc.repo.create.assert_called_once()
    payload = svc.repo.create.call_args.args[0]
    assert payload["estado"] == "draft"
    assert payload["version"] == 2
    assert payload["parent_tarea_id"] == parent_id
    assert payload["comision_id"] == comision_id
    assert payload["codigo"] == "TP1"
    assert payload["titulo"] == "Nueva v2"
    # los campos no provistos en el patch heredan del padre
    assert payload["enunciado"] == "enunciado v1"
    assert payload["created_by"] == user_docente_admin_a.id
    assert payload["tenant_id"] == tenant_a_id

    assert _audit_actions(mock_session) == ["tarea_practica.new_version"]


async def test_new_version_de_archived_crea_nuevo_draft(
    mock_session, user_docente_admin_a: User, tenant_a_id: UUID
) -> None:
    """new_version() sobre archived también crea nueva versión (resucita TP)."""
    svc = TareaPracticaService(mock_session)

    parent_id = uuid4()
    comision_id = uuid4()
    parent = _fake_tarea(
        parent_id,
        tenant_a_id,
        comision_id,
        estado="archived",
        version=3,
    )
    svc.repo.get_or_404 = AsyncMock(return_value=parent)

    new_mock = _fake_tarea(
        uuid4(),
        tenant_a_id,
        comision_id,
        estado="draft",
        version=4,
        parent_tarea_id=parent_id,
    )
    svc.repo.create = AsyncMock(return_value=new_mock)

    patch = TareaPracticaUpdate(titulo="Resucitada")
    result = await svc.new_version(parent_id, patch, user_docente_admin_a)

    assert result is new_mock
    payload = svc.repo.create.call_args.args[0]
    assert payload["estado"] == "draft"
    assert payload["version"] == 4
    assert payload["parent_tarea_id"] == parent_id


async def test_new_version_de_draft_falla_409(
    mock_session, user_docente_admin_a: User, tenant_a_id: UUID
) -> None:
    """new_version() sobre draft retorna 409 (no se forkea desde draft)."""
    svc = TareaPracticaService(mock_session)

    parent_id = uuid4()
    parent = _fake_tarea(parent_id, tenant_a_id, uuid4(), estado="draft", version=1)
    svc.repo.get_or_404 = AsyncMock(return_value=parent)
    svc.repo.create = AsyncMock()

    patch = TareaPracticaUpdate(titulo="Nope")
    with pytest.raises(HTTPException) as exc_info:
        await svc.new_version(parent_id, patch, user_docente_admin_a)

    assert exc_info.value.status_code == 409
    svc.repo.create.assert_not_called()
    assert _audit_actions(mock_session) == []


async def test_get_versions_devuelve_cadena_ordenada(mock_session, tenant_a_id: UUID) -> None:
    """list_versions() devuelve la cadena completa ordenada por version asc.

    Setup: v1 (archived) ← v2 (published) ← v3 (draft). El query parte
    desde v3 (la que llega por path), camina hacia atrás hasta el root
    (v1) y luego hacia adelante hasta agotar descendientes. Todas las
    consultas pasan por `session.execute` — mockeamos esa cadena.
    """
    svc = TareaPracticaService(mock_session)

    comision_id = uuid4()
    v1_id = uuid4()
    v2_id = uuid4()
    v3_id = uuid4()
    v1 = _fake_tarea(
        v1_id,
        tenant_a_id,
        comision_id,
        estado="archived",
        version=1,
        parent_tarea_id=None,
    )
    v2 = _fake_tarea(
        v2_id,
        tenant_a_id,
        comision_id,
        estado="published",
        version=2,
        parent_tarea_id=v1_id,
    )
    v3 = _fake_tarea(
        v3_id,
        tenant_a_id,
        comision_id,
        estado="draft",
        version=3,
        parent_tarea_id=v2_id,
    )

    # El service primero pide get_or_404(v3) — devolvemos v3 ahí.
    svc.repo.get_or_404 = AsyncMock(return_value=v3)

    # Luego walks back a v2, después a v1 (parent_tarea_id IS NULL → corta).
    # Después walks forward desde v1 → hijos [v2], desde v2 → hijos [v3],
    # desde v3 → hijos [] (corta).
    walk_back_results = [v2, v1]
    walk_forward_children = [[v2], [v3], []]

    back_idx = {"i": 0}
    fwd_idx = {"i": 0}

    def make_result(scalar_one_value=None, scalars_value=None):
        r = MagicMock()
        r.scalar_one_or_none = MagicMock(return_value=scalar_one_value)
        scalars_obj = MagicMock()
        scalars_obj.all = MagicMock(return_value=scalars_value or [])
        r.scalars = MagicMock(return_value=scalars_obj)
        return r

    async def fake_execute(stmt):
        # Heurística: si pidieron walk back tenemos que devolver `parent`
        # con scalar_one_or_none. Si es walk-forward devolvemos children
        # con scalars().all(). Distinguimos por orden de invocación.
        # Primero se hacen TODOS los walk-back (2 calls), luego forward.
        if back_idx["i"] < len(walk_back_results):
            val = walk_back_results[back_idx["i"]]
            back_idx["i"] += 1
            return make_result(scalar_one_value=val)
        children = walk_forward_children[fwd_idx["i"]]
        fwd_idx["i"] += 1
        return make_result(scalars_value=children)

    mock_session.execute = AsyncMock(side_effect=fake_execute)

    chain = await svc.list_versions(v3_id)

    assert [t.version for t in chain] == [1, 2, 3]
    assert chain[0] is v1
    assert chain[1] is v2
    assert chain[2] is v3


# ---------------------------------------------------------------------------
# inicial_codigo: template de código que el docente provee al estudiante
# ---------------------------------------------------------------------------


async def test_create_with_inicial_codigo(
    mock_session, user_docente_admin_a: User, tenant_a_id: UUID
) -> None:
    """POST con `inicial_codigo` lo persiste tal cual en el repo."""
    svc = TareaPracticaService(mock_session)

    comision_id = uuid4()
    comision = _fake_comision(comision_id, tenant_a_id)
    svc.comisiones.get_or_404 = AsyncMock(return_value=comision)

    template = "def factorial(n):\n    pass\n"
    fake_tarea = _fake_tarea(uuid4(), tenant_a_id, comision_id, inicial_codigo=template)
    svc.repo.create = AsyncMock(return_value=fake_tarea)

    data = TareaPracticaCreate(
        comision_id=comision_id,
        codigo="TP1",
        titulo="Factorial",
        enunciado="Implementar factorial recursivo",
        inicial_codigo=template,
    )

    result = await svc.create(data, user_docente_admin_a)

    assert result is fake_tarea
    payload = svc.repo.create.call_args.args[0]
    assert payload["inicial_codigo"] == template


async def test_create_sin_inicial_codigo_es_null(
    mock_session, user_docente_admin_a: User, tenant_a_id: UUID
) -> None:
    """POST sin `inicial_codigo` lo persiste como None (significa "sin template")."""
    svc = TareaPracticaService(mock_session)

    comision_id = uuid4()
    comision = _fake_comision(comision_id, tenant_a_id)
    svc.comisiones.get_or_404 = AsyncMock(return_value=comision)

    fake_tarea = _fake_tarea(uuid4(), tenant_a_id, comision_id)
    svc.repo.create = AsyncMock(return_value=fake_tarea)

    data = TareaPracticaCreate(
        comision_id=comision_id,
        codigo="TP1",
        titulo="Sin template",
        enunciado="...",
    )

    await svc.create(data, user_docente_admin_a)

    payload = svc.repo.create.call_args.args[0]
    assert "inicial_codigo" in payload
    assert payload["inicial_codigo"] is None


async def test_update_inicial_codigo(
    mock_session, user_docente_admin_a: User, tenant_a_id: UUID
) -> None:
    """PATCH (sobre draft) actualiza `inicial_codigo` y registra audit log."""
    svc = TareaPracticaService(mock_session)

    tid = uuid4()
    obj = _fake_tarea(tid, tenant_a_id, uuid4(), estado="draft", inicial_codigo=None)
    svc.repo.get_or_404 = AsyncMock(return_value=obj)

    nuevo_template = "# TODO: completar\nresultado = None\n"
    data = TareaPracticaUpdate(inicial_codigo=nuevo_template)
    result = await svc.update(tid, data, user_docente_admin_a)

    assert result.inicial_codigo == nuevo_template

    audit_calls = [
        c.args[0] for c in mock_session.add.call_args_list if isinstance(c.args[0], AuditLog)
    ]
    assert len(audit_calls) == 1
    assert audit_calls[0].action == "tarea_practica.update"
    assert audit_calls[0].changes == {"after": {"inicial_codigo": nuevo_template}}


def test_inicial_codigo_demasiado_grande_falla_422() -> None:
    """`inicial_codigo` con > 5000 chars falla en validación de schema."""
    template_grande = "x" * 5001

    with pytest.raises(ValidationError) as exc_info:
        TareaPracticaCreate(
            comision_id=uuid4(),
            codigo="TP1",
            titulo="Demasiado grande",
            enunciado="...",
            inicial_codigo=template_grande,
        )

    errors = exc_info.value.errors()
    assert any(
        (e["loc"] == ("inicial_codigo",) and "5000" in str(e).lower())
        or (e["loc"] == ("inicial_codigo",) and e["type"] == "string_too_long")
        for e in errors
    )

    # En el borde (5000) sí pasa
    ok = TareaPracticaCreate(
        comision_id=uuid4(),
        codigo="TP1",
        titulo="Borde",
        enunciado="...",
        inicial_codigo="x" * 5000,
    )
    assert ok.inicial_codigo is not None
    assert len(ok.inicial_codigo) == 5000

    # En Update también valida
    with pytest.raises(ValidationError):
        TareaPracticaUpdate(inicial_codigo="x" * 5001)


# ---------------------------------------------------------------------------
# Drift detection (ADR-016)
# ---------------------------------------------------------------------------


async def test_update_instance_with_template_sets_drift_when_canonical_field_changes(
    mock_session, user_docente_admin_a: User, tenant_a_id: UUID
) -> None:
    """PATCH sobre instancia con `template_id` y cambio en campo canónico
    setea `has_drift=True` y lo refleja en audit log."""
    svc = TareaPracticaService(mock_session)

    tid = uuid4()
    template_id = uuid4()
    obj = _fake_tarea(
        tid,
        tenant_a_id,
        uuid4(),
        estado="draft",
        template_id=template_id,
        has_drift=False,
        enunciado="Enunciado original del template",
    )
    svc.repo.get_or_404 = AsyncMock(return_value=obj)

    data = TareaPracticaUpdate(enunciado="Enunciado divergente por comisión")
    await svc.update(tid, data, user_docente_admin_a)

    assert obj.has_drift is True
    assert obj.enunciado == "Enunciado divergente por comisión"

    audit_calls = [
        c.args[0] for c in mock_session.add.call_args_list if isinstance(c.args[0], AuditLog)
    ]
    assert len(audit_calls) == 1
    assert audit_calls[0].action == "tarea_practica.update"
    assert audit_calls[0].changes.get("drift_triggered") is True


async def test_update_instance_with_template_does_NOT_set_drift_on_non_canonical_change(
    mock_session, user_docente_admin_a: User, tenant_a_id: UUID
) -> None:
    """PATCH que solo cambia un campo canónico a su MISMO valor no dispara
    drift. El update actual no soporta campos 'no canónicos' vía patch
    genérico (estado/version se cambian por endpoints dedicados), así que
    reusamos el mismo valor para garantizar 'no hay cambio real'."""
    svc = TareaPracticaService(mock_session)

    tid = uuid4()
    template_id = uuid4()
    titulo_original = "Título original del template"
    obj = _fake_tarea(
        tid,
        tenant_a_id,
        uuid4(),
        estado="draft",
        template_id=template_id,
        has_drift=False,
        titulo=titulo_original,
    )
    svc.repo.get_or_404 = AsyncMock(return_value=obj)

    # Re-enviamos el mismo valor: no hay cambio → no drift.
    data = TareaPracticaUpdate(titulo=titulo_original)
    await svc.update(tid, data, user_docente_admin_a)

    assert obj.has_drift is False

    audit_calls = [
        c.args[0] for c in mock_session.add.call_args_list if isinstance(c.args[0], AuditLog)
    ]
    assert len(audit_calls) == 1
    assert "drift_triggered" not in audit_calls[0].changes


async def test_update_instance_without_template_does_not_set_drift(
    mock_session, user_docente_admin_a: User, tenant_a_id: UUID
) -> None:
    """TP huérfana (sin template_id) nunca pasa has_drift a True, aun
    cambiando campos canónicos."""
    svc = TareaPracticaService(mock_session)

    tid = uuid4()
    obj = _fake_tarea(
        tid,
        tenant_a_id,
        uuid4(),
        estado="draft",
        template_id=None,
        has_drift=False,
        enunciado="Original",
    )
    svc.repo.get_or_404 = AsyncMock(return_value=obj)

    data = TareaPracticaUpdate(enunciado="Cambio en TP huérfana")
    await svc.update(tid, data, user_docente_admin_a)

    assert obj.has_drift is False
    assert obj.enunciado == "Cambio en TP huérfana"

    audit_calls = [
        c.args[0] for c in mock_session.add.call_args_list if isinstance(c.args[0], AuditLog)
    ]
    assert "drift_triggered" not in audit_calls[0].changes


async def test_update_drifted_instance_stays_drifted(
    mock_session, user_docente_admin_a: User, tenant_a_id: UUID
) -> None:
    """Instancia ya drifteada: has_drift queda en True, el flag
    drift_triggered NO se agrega (el trigger ya pasó antes)."""
    svc = TareaPracticaService(mock_session)

    tid = uuid4()
    template_id = uuid4()
    obj = _fake_tarea(
        tid,
        tenant_a_id,
        uuid4(),
        estado="draft",
        template_id=template_id,
        has_drift=True,
        enunciado="Enunciado drifteado previo",
    )
    svc.repo.get_or_404 = AsyncMock(return_value=obj)

    data = TareaPracticaUpdate(enunciado="Otro cambio más")
    await svc.update(tid, data, user_docente_admin_a)

    assert obj.has_drift is True
    assert obj.enunciado == "Otro cambio más"

    audit_calls = [
        c.args[0] for c in mock_session.add.call_args_list if isinstance(c.args[0], AuditLog)
    ]
    assert len(audit_calls) == 1
    # No hay "drift_triggered" porque ya estaba drifteada al entrar.
    assert "drift_triggered" not in audit_calls[0].changes


async def test_new_version_inherits_drift_from_parent(
    mock_session, user_docente_admin_a: User, tenant_a_id: UUID
) -> None:
    """new_version() hereda template_id y has_drift del parent para no
    'lavar' drift creando una nueva versión."""
    svc = TareaPracticaService(mock_session)

    parent_id = uuid4()
    template_id = uuid4()
    comision_id = uuid4()
    parent = _fake_tarea(
        parent_id,
        tenant_a_id,
        comision_id,
        estado="published",
        version=1,
        template_id=template_id,
        has_drift=True,
    )
    svc.repo.get_or_404 = AsyncMock(return_value=parent)

    new_mock = _fake_tarea(
        uuid4(),
        tenant_a_id,
        comision_id,
        estado="draft",
        version=2,
        parent_tarea_id=parent_id,
        template_id=template_id,
        has_drift=True,
    )
    svc.repo.create = AsyncMock(return_value=new_mock)

    patch = TareaPracticaUpdate(titulo="Versión 2 aún drifteada")
    await svc.new_version(parent_id, patch, user_docente_admin_a)

    payload = svc.repo.create.call_args.args[0]
    assert payload["template_id"] == template_id
    assert payload["has_drift"] is True
    assert payload["parent_tarea_id"] == parent_id
    assert payload["version"] == 2
