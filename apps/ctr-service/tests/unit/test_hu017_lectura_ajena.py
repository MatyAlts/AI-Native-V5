"""Aceptacion HU-017 parte 1, CTR ajeno (orquestador, antes de construir; el
constructor no la modifica). Juani (23/11): "sisi empeza por la parte 1" y
"sisi" a los criterios (nivel L).

Hallazgo F19 de HU-014: un alumno leyo la traza CTR completa del episodio de
OTRO alumno con `GET /api/v1/audit/episodes/{id}` -> 200. Causa: con Clerk toda
cuenta trae `estudiante,docente`, y `assert_comision_member` falla ABIERTO si
falta `ACADEMIC_DB_URL` (en produccion el ctr-service no la tiene).

Contrato nuevo en `ctr_service.auth.dependencies`:
  `async def assert_puede_leer_episodio(user, ep) -> None`
que deja pasar, en este orden:
  1. roles de `CTR_OVERSIGHT_ROLES` (sin consultar nada);
  2. el duenio: `ep.student_pseudonym == user.id` (sin consultar nada);
  3. con `settings.enforce_comision_access = False` (opt-out de dev): no-op;
  4. sin `settings.academic_db_url`: 503 (falla CERRADO);
  5. membresia real via `_is_comision_member` (el seam que ya existe): si no, 403.
`get_episode` y `verify_episode_chain` (y por lo tanto los alias
`/api/v1/audit/*`) lo llaman antes de servir.

C01  Un alumno ajeno recibe 403 al leer y al verificar.
C02  El duenio lee su episodio sin consultar la base academica.
C03  Docente miembro 200; docente no miembro 403.
C04  Oversight 200 sin consultar la base academica.
N01  Sin `academic_db_url`, un tercero recibe 503 (no 200).
N05  Con el opt-out de dev (`enforce_comision_access=False`) no se bloquea.
"""

from __future__ import annotations

import types
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from ctr_service.auth import dependencies as deps
from ctr_service.auth.dependencies import User
from ctr_service.routes import events as events_route
from fastapi import HTTPException

TENANT = UUID("11111111-1111-1111-1111-111111111111")
COMISION = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
CLERK = {"estudiante", "docente"}


def _user(roles: set[str], uid: UUID | None = None) -> User:
    return User(
        id=uid or uuid4(),
        tenant_id=TENANT,
        email="x@y.z",
        roles=frozenset(roles),
        realm=str(TENANT),
    )


def _episode(owner: UUID) -> types.SimpleNamespace:
    now = datetime.now(UTC)
    return types.SimpleNamespace(
        id=uuid4(),
        tenant_id=TENANT,
        comision_id=COMISION,
        student_pseudonym=owner,
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


class _Res:
    def __init__(self, scalar: Any = None) -> None:
        self._scalar = scalar

    def scalar_one_or_none(self) -> Any:
        return self._scalar

    def scalars(self) -> Any:
        return types.SimpleNamespace(all=lambda: [])


class _DB:
    def __init__(self, ep: Any) -> None:
        self._ep = ep
        self._n = 0

    async def execute(self, _stmt: Any) -> _Res:
        self._n += 1
        return _Res(self._ep if self._n == 1 else None)


def _prod(monkeypatch, *, miembro: bool | None) -> None:
    """Configuracion de produccion con la base academica cargada."""
    monkeypatch.setattr(deps.settings, "enforce_comision_access", True)
    monkeypatch.setattr(deps.settings, "academic_db_url", "postgresql://x")

    async def _membresia(tenant_id: UUID, user_id: UUID, comision_id: UUID) -> bool:
        if miembro is None:
            raise AssertionError("no debia consultar usuarios_comision")
        return miembro

    monkeypatch.setattr(deps, "_is_comision_member", _membresia)


def _wire(monkeypatch) -> None:
    """Las rutas llaman a la funcion real del modulo de dependencias."""
    f = getattr(deps, "assert_puede_leer_episodio", None)
    assert f is not None, "falta assert_puede_leer_episodio"
    monkeypatch.setattr(events_route, "assert_puede_leer_episodio", f, raising=False)


async def _leer(user: User, ep: Any) -> Any:
    return await events_route.get_episode(ep.id, user=user, db=_DB(ep))


async def _verificar(user: User, ep: Any) -> Any:
    return await events_route.verify_episode_chain(ep.id, user=user, db=_DB(ep))


# ── C01 ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("accion", [_leer, _verificar])
async def test_c01_alumno_ajeno_recibe_403(monkeypatch, accion) -> None:
    _prod(monkeypatch, miembro=False)
    _wire(monkeypatch)
    ep = _episode(owner=uuid4())
    with pytest.raises(HTTPException) as exc:
        await accion(_user(CLERK), ep)
    assert exc.value.status_code == 403


# ── C02 ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("accion", [_leer, _verificar])
async def test_c02_el_duenio_lee_sin_consultar_la_base(monkeypatch, accion) -> None:
    _prod(monkeypatch, miembro=None)
    _wire(monkeypatch)
    duenio = uuid4()
    ep = _episode(owner=duenio)
    await accion(_user(CLERK, uid=duenio), ep)


# ── C03 ────────────────────────────────────────────────────────────────


async def test_c03_docente_miembro_lee(monkeypatch) -> None:
    _prod(monkeypatch, miembro=True)
    _wire(monkeypatch)
    ep = _episode(owner=uuid4())
    res = await _leer(_user(CLERK), ep)
    assert res.comision_id == COMISION


async def test_c03_docente_no_miembro_recibe_403(monkeypatch) -> None:
    _prod(monkeypatch, miembro=False)
    _wire(monkeypatch)
    ep = _episode(owner=uuid4())
    with pytest.raises(HTTPException) as exc:
        await _leer(_user({"docente"}), ep)
    assert exc.value.status_code == 403


# ── C04 ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "rol", ["superadmin", "docente_admin", "tutor_service", "classifier_worker"]
)
async def test_c04_oversight_lee_sin_consultar(monkeypatch, rol) -> None:
    _prod(monkeypatch, miembro=None)
    _wire(monkeypatch)
    ep = _episode(owner=uuid4())
    await _leer(_user({rol}), ep)


# ── N01 ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("accion", [_leer, _verificar])
async def test_n01_sin_base_academica_un_tercero_recibe_503(monkeypatch, accion) -> None:
    monkeypatch.setattr(deps.settings, "enforce_comision_access", True)
    monkeypatch.setattr(deps.settings, "academic_db_url", "")
    _wire(monkeypatch)
    ep = _episode(owner=uuid4())
    with pytest.raises(HTTPException) as exc:
        await accion(_user(CLERK), ep)
    assert exc.value.status_code == 503


async def test_n01_sin_base_academica_el_duenio_igual_lee(monkeypatch) -> None:
    monkeypatch.setattr(deps.settings, "enforce_comision_access", True)
    monkeypatch.setattr(deps.settings, "academic_db_url", "")
    _wire(monkeypatch)
    duenio = uuid4()
    ep = _episode(owner=duenio)
    await _leer(_user(CLERK, uid=duenio), ep)


# ── N05 ────────────────────────────────────────────────────────────────


async def test_n05_opt_out_de_dev_no_bloquea(monkeypatch) -> None:
    monkeypatch.setattr(deps.settings, "enforce_comision_access", False)
    monkeypatch.setattr(deps.settings, "academic_db_url", "")
    _wire(monkeypatch)
    ep = _episode(owner=uuid4())
    await _leer(_user(CLERK), ep)
