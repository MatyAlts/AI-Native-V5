"""Tests del gate de lectura por comisión del CTR (A0.6).

Cierra el leak: un docente NO puede leer/verificar el CTR de comisiones ajenas.
El aislamiento lo da `usuarios_comision` (academic_main) — la RLS por tenant no
alcanza porque en prod todos los docentes comparten un tenant fijo.

Cubre dos capas:
  1. `assert_comision_member` (la lógica de autorización): oversight y
     service-accounts pasan; el flag OFF / sin academic_db_url es no-op;
     un docente NO-miembro recibe 403 y un docente miembro pasa.
  2. El handler `get_episode` (wiring): el gate se llama ANTES de servir los
     eventos, así que un docente ajeno recibe 403 y no ve el episodio. Como los
     aliases `/api/v1/audit/*` (ADR-031) apuntan al MISMO handler, el gate
     cubre ambos paths automáticamente.
"""

from __future__ import annotations

import types
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from ctr_service.auth import dependencies as deps
from ctr_service.auth.dependencies import User, assert_comision_member
from ctr_service.routes import events as events_route
from fastapi import HTTPException

TENANT = UUID("11111111-1111-1111-1111-111111111111")
COMISION_A = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")


def _user(roles: set[str], uid: UUID | None = None) -> User:
    return User(
        id=uid or uuid4(),
        tenant_id=TENANT,
        email="x@y.z",
        roles=frozenset(roles),
        realm=str(TENANT),
    )


# ── Capa 1: assert_comision_member ────────────────────────────────────────


@pytest.mark.parametrize("role", ["superadmin", "docente_admin", "tutor_service", "classifier_worker"])
async def test_oversight_y_service_accounts_pasan_sin_tocar_db(monkeypatch, role) -> None:
    """Los roles de `CTR_OVERSIGHT_ROLES` no consultan membresía: acceso total."""
    monkeypatch.setattr(deps.settings, "enforce_comision_access", True)
    monkeypatch.setattr(deps.settings, "academic_db_url", "postgresql://x")

    async def _boom(*a, **k):  # el DB seam NO debe llamarse
        raise AssertionError("oversight no debe consultar usuarios_comision")

    monkeypatch.setattr(deps, "_is_comision_member", _boom)
    await assert_comision_member(_user({role}), COMISION_A)  # no raise


async def test_flag_off_es_noop(monkeypatch) -> None:
    monkeypatch.setattr(deps.settings, "enforce_comision_access", False)
    monkeypatch.setattr(deps.settings, "academic_db_url", "postgresql://x")

    async def _boom(*a, **k):
        raise AssertionError("con el flag OFF no debe consultar membresía")

    monkeypatch.setattr(deps, "_is_comision_member", _boom)
    await assert_comision_member(_user({"docente"}), COMISION_A)  # no raise


async def test_sin_academic_db_url_es_noop(monkeypatch) -> None:
    """Dev/stub/tests con DB mockeada: guard inerte para no romper auditoría."""
    monkeypatch.setattr(deps.settings, "enforce_comision_access", True)
    monkeypatch.setattr(deps.settings, "academic_db_url", "")

    async def _boom(*a, **k):
        raise AssertionError("sin academic_db_url no debe consultar membresía")

    monkeypatch.setattr(deps, "_is_comision_member", _boom)
    await assert_comision_member(_user({"docente"}), COMISION_A)  # no raise


async def test_docente_miembro_pasa(monkeypatch) -> None:
    monkeypatch.setattr(deps.settings, "enforce_comision_access", True)
    monkeypatch.setattr(deps.settings, "academic_db_url", "postgresql://x")

    async def _member(tenant_id, user_id, comision_id):
        return True

    monkeypatch.setattr(deps, "_is_comision_member", _member)
    await assert_comision_member(_user({"docente"}), COMISION_A)  # no raise


async def test_docente_no_miembro_recibe_403(monkeypatch) -> None:
    monkeypatch.setattr(deps.settings, "enforce_comision_access", True)
    monkeypatch.setattr(deps.settings, "academic_db_url", "postgresql://x")

    async def _not_member(tenant_id, user_id, comision_id):
        return False

    monkeypatch.setattr(deps, "_is_comision_member", _not_member)
    with pytest.raises(HTTPException) as ei:
        await assert_comision_member(_user({"docente"}), COMISION_A)
    assert ei.value.status_code == 403


# ── Capa 2: wiring en el handler get_episode ──────────────────────────────


class _FakeResult:
    def __init__(self, scalar=None, scalars_list=None):
        self._scalar = scalar
        self._scalars_list = scalars_list or []

    def scalar_one_or_none(self):
        return self._scalar

    def scalars(self):
        parent = self

        class _S:
            def all(_self):  # noqa: N805 - stub, no real `self` binding needed
                return parent._scalars_list

        return _S()


class _FakeDB:
    """Stub de AsyncSession: 1ra execute devuelve el Episode, 2da los eventos."""

    def __init__(self, episode):
        self._episode = episode
        self._calls = 0

    async def execute(self, _stmt):
        self._calls += 1
        if self._calls == 1:
            return _FakeResult(scalar=self._episode)
        return _FakeResult(scalars_list=[])


def _fake_episode(comision_id: UUID) -> types.SimpleNamespace:
    now = datetime.now(UTC)
    return types.SimpleNamespace(
        id=uuid4(),
        tenant_id=TENANT,
        comision_id=comision_id,
        student_pseudonym=uuid4(),
        problema_id=uuid4(),
        estado="closed",
        opened_at=now,
        closed_at=now,
        events_count=0,
        last_chain_hash="0" * 64,
        integrity_compromised=False,
        prompt_system_hash="0" * 64,
        classifier_config_hash="0" * 64,
        curso_config_hash="0" * 64,
    )


async def test_get_episode_bloquea_docente_ajeno(monkeypatch) -> None:
    """El handler llama al gate ANTES de servir: docente ajeno → 403."""
    monkeypatch.setattr(events_route, "assert_comision_member", deps.assert_comision_member)
    monkeypatch.setattr(deps.settings, "enforce_comision_access", True)
    monkeypatch.setattr(deps.settings, "academic_db_url", "postgresql://x")

    async def _not_member(tenant_id, user_id, comision_id):
        return False

    monkeypatch.setattr(deps, "_is_comision_member", _not_member)

    ep = _fake_episode(COMISION_A)
    with pytest.raises(HTTPException) as ei:
        await events_route.get_episode(ep.id, user=_user({"docente"}), db=_FakeDB(ep))
    assert ei.value.status_code == 403


async def test_get_episode_permite_docente_miembro(monkeypatch) -> None:
    monkeypatch.setattr(events_route, "assert_comision_member", deps.assert_comision_member)
    monkeypatch.setattr(deps.settings, "enforce_comision_access", True)
    monkeypatch.setattr(deps.settings, "academic_db_url", "postgresql://x")

    async def _member(tenant_id, user_id, comision_id):
        return True

    monkeypatch.setattr(deps, "_is_comision_member", _member)

    ep = _fake_episode(COMISION_A)
    result = await events_route.get_episode(ep.id, user=_user({"docente"}), db=_FakeDB(ep))
    assert result.comision_id == COMISION_A
    assert result.events == []


async def test_get_episode_permite_oversight(monkeypatch) -> None:
    """superadmin lee cualquier episodio sin consultar membresía."""
    monkeypatch.setattr(events_route, "assert_comision_member", deps.assert_comision_member)
    monkeypatch.setattr(deps.settings, "enforce_comision_access", True)
    monkeypatch.setattr(deps.settings, "academic_db_url", "postgresql://x")

    async def _boom(*a, **k):
        raise AssertionError("oversight no debe consultar membresía")

    monkeypatch.setattr(deps, "_is_comision_member", _boom)

    ep = _fake_episode(COMISION_A)
    result = await events_route.get_episode(ep.id, user=_user({"superadmin"}), db=_FakeDB(ep))
    assert result.comision_id == COMISION_A
