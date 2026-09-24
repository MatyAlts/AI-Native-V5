"""Tests de integración de `find_closed_episode` (GET /episodes/closed-match).

REAPERTURA · Mejora 2 (fix-pdf-auditoria-qa, 2026-09-23): cuando el alumno
reabre un ejercicio cerrado, este endpoint es el ÚNICO guardián de que el
episodio nuevo herede el código del ÚLTIMO episodio CERRADO del MISMO alumno
— y no el de otro alumno que cerró el mismo ejercicio. Sin un test contra DB
real con RLS activa, un bug en el filtro de `student_pseudonym` o de
`tenant_id` filtraría código de un alumno a otro sin que nada lo detecte.

Requiere Docker (testcontainers Postgres real + `app_user` NOSUPERUSER
NOBYPASSRLS). Skip automático si Docker no está disponible.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text

from ctr_service.auth import User
from ctr_service.models import Episode
from ctr_service.routes.events import find_closed_episode

from .conftest import requires_docker

pytestmark = [pytest.mark.integration, requires_docker]


def _user(tenant_id: UUID) -> User:
    return User(
        id=uuid4(),
        tenant_id=tenant_id,
        email="docente@test.local",
        roles=frozenset({"docente"}),
        realm=str(tenant_id),
    )


async def _crear_episodio_cerrado(
    session_factory,
    *,
    tenant_id: UUID,
    student_pseudonym: UUID,
    problema_id: UUID,
    ejercicio_id: UUID | None,
    closed_at: datetime,
    estado: str = "closed",
) -> Episode:
    """Inserta un episodio con RLS activo (SET LOCAL app.current_tenant)."""
    ep = Episode(
        id=uuid4(),
        tenant_id=tenant_id,
        comision_id=uuid4(),
        student_pseudonym=student_pseudonym,
        problema_id=problema_id,
        prompt_system_hash="a" * 64,
        prompt_system_version="v1",
        classifier_config_hash="b" * 64,
        curso_config_hash="c" * 64,
        estado=estado,
        closed_at=closed_at,
        meta={"ejercicio_id": str(ejercicio_id)} if ejercicio_id is not None else {},
    )
    async with session_factory() as s:
        await s.execute(
            text("SELECT set_config('app.current_tenant', :t, true)"),
            {"t": str(tenant_id)},
        )
        s.add(ep)
        await s.commit()
    return ep


async def _buscar(session_factory, *, tenant_id, student_pseudonym, problema_id, ejercicio_id):
    """Llama la función de ruta directamente, con la sesión con RLS seteado."""
    async with session_factory() as s:
        await s.execute(
            text("SELECT set_config('app.current_tenant', :t, true)"),
            {"t": str(tenant_id)},
        )
        return await find_closed_episode(
            student_pseudonym=student_pseudonym,
            problema_id=problema_id,
            ejercicio_id=ejercicio_id,
            user=_user(tenant_id),
            db=s,
        )


# ── 1. OWNERSHIP (crítico) ──────────────────────────────────────────────


async def test_ownership_no_devuelve_el_episodio_cerrado_de_otro_alumno(
    pg_engine, session_factory
) -> None:
    """Dos episodios cerrados del MISMO (tenant, problema, ejercicio) pero de
    DISTINTO alumno: pedir el de A nunca debe devolver el de B, y viceversa.

    Este es el guardián de la fuga cross-alumno en la reapertura: si el
    filtro por `student_pseudonym` se rompiera (o se borrara), este test es
    el que lo detecta.
    """
    tenant = uuid4()
    problema = uuid4()
    ejercicio = uuid4()
    alumno_a = uuid4()
    alumno_b = uuid4()

    ep_a = await _crear_episodio_cerrado(
        session_factory,
        tenant_id=tenant,
        student_pseudonym=alumno_a,
        problema_id=problema,
        ejercicio_id=ejercicio,
        closed_at=datetime.now(UTC),
    )
    ep_b = await _crear_episodio_cerrado(
        session_factory,
        tenant_id=tenant,
        student_pseudonym=alumno_b,
        problema_id=problema,
        ejercicio_id=ejercicio,
        closed_at=datetime.now(UTC),
    )

    match_a = await _buscar(
        session_factory,
        tenant_id=tenant,
        student_pseudonym=alumno_a,
        problema_id=problema,
        ejercicio_id=ejercicio,
    )
    match_b = await _buscar(
        session_factory,
        tenant_id=tenant,
        student_pseudonym=alumno_b,
        problema_id=problema,
        ejercicio_id=ejercicio,
    )

    assert match_a is not None
    assert match_a.episode_id == ep_a.id
    assert match_a.episode_id != ep_b.id

    assert match_b is not None
    assert match_b.episode_id == ep_b.id
    assert match_b.episode_id != ep_a.id


# ── 2. Más reciente por closed_at DESC ──────────────────────────────────


async def test_devuelve_el_cierre_mas_reciente_del_mismo_alumno(
    pg_engine, session_factory
) -> None:
    tenant = uuid4()
    problema = uuid4()
    ejercicio = uuid4()
    alumno = uuid4()
    ahora = datetime.now(UTC)

    ep_viejo = await _crear_episodio_cerrado(
        session_factory,
        tenant_id=tenant,
        student_pseudonym=alumno,
        problema_id=problema,
        ejercicio_id=ejercicio,
        closed_at=ahora - timedelta(hours=2),
    )
    ep_reciente = await _crear_episodio_cerrado(
        session_factory,
        tenant_id=tenant,
        student_pseudonym=alumno,
        problema_id=problema,
        ejercicio_id=ejercicio,
        closed_at=ahora - timedelta(minutes=5),
    )

    match = await _buscar(
        session_factory,
        tenant_id=tenant,
        student_pseudonym=alumno,
        problema_id=problema,
        ejercicio_id=ejercicio,
    )

    assert match is not None
    assert match.episode_id == ep_reciente.id
    assert match.episode_id != ep_viejo.id


# ── 3. NO devuelve open/paused ───────────────────────────────────────────


async def test_no_devuelve_episodios_open_o_paused(pg_engine, session_factory) -> None:
    tenant = uuid4()
    problema = uuid4()
    ejercicio = uuid4()
    alumno = uuid4()

    await _crear_episodio_cerrado(
        session_factory,
        tenant_id=tenant,
        student_pseudonym=alumno,
        problema_id=problema,
        ejercicio_id=ejercicio,
        closed_at=datetime.now(UTC),
        estado="open",
    )
    await _crear_episodio_cerrado(
        session_factory,
        tenant_id=tenant,
        student_pseudonym=alumno,
        problema_id=problema,
        ejercicio_id=ejercicio,
        closed_at=datetime.now(UTC),
        estado="paused",
    )

    match = await _buscar(
        session_factory,
        tenant_id=tenant,
        student_pseudonym=alumno,
        problema_id=problema,
        ejercicio_id=ejercicio,
    )

    assert match is None


# ── 4. Matcheo correcto de ejercicio_id dentro de la misma tarea ────────


async def test_no_cruza_ejercicios_distintos_de_la_misma_tarea(
    pg_engine, session_factory
) -> None:
    tenant = uuid4()
    problema = uuid4()
    alumno = uuid4()
    ejercicio_1 = uuid4()
    ejercicio_2 = uuid4()

    ep_1 = await _crear_episodio_cerrado(
        session_factory,
        tenant_id=tenant,
        student_pseudonym=alumno,
        problema_id=problema,
        ejercicio_id=ejercicio_1,
        closed_at=datetime.now(UTC),
    )
    await _crear_episodio_cerrado(
        session_factory,
        tenant_id=tenant,
        student_pseudonym=alumno,
        problema_id=problema,
        ejercicio_id=ejercicio_2,
        closed_at=datetime.now(UTC),
    )

    match = await _buscar(
        session_factory,
        tenant_id=tenant,
        student_pseudonym=alumno,
        problema_id=problema,
        ejercicio_id=ejercicio_1,
    )

    assert match is not None
    assert match.episode_id == ep_1.id
    assert match.ejercicio_id == ejercicio_1


# ── 5. Sin match → None ──────────────────────────────────────────────────


async def test_sin_match_devuelve_none(pg_engine, session_factory) -> None:
    match = await _buscar(
        session_factory,
        tenant_id=uuid4(),
        student_pseudonym=uuid4(),
        problema_id=uuid4(),
        ejercicio_id=uuid4(),
    )
    assert match is None


# ── 6. RLS por tenant también aísla ──────────────────────────────────────


async def test_rls_no_deja_ver_un_episodio_cerrado_de_otro_tenant(
    pg_engine, session_factory
) -> None:
    """Defensa en profundidad: aunque el `user.tenant_id` pasado a la función
    coincidiera con el tenant dueño del episodio, si la sesión de DB quedó
    con `app.current_tenant` seteado a OTRO tenant, RLS bloquea la fila —
    la política FORCE ROW LEVEL SECURITY corta antes de que el filtro de la
    query en Python tenga oportunidad de aplicar.
    """
    tenant_dueno = uuid4()
    tenant_ajeno = uuid4()
    problema = uuid4()
    ejercicio = uuid4()
    alumno = uuid4()

    ep = await _crear_episodio_cerrado(
        session_factory,
        tenant_id=tenant_dueno,
        student_pseudonym=alumno,
        problema_id=problema,
        ejercicio_id=ejercicio,
        closed_at=datetime.now(UTC),
    )

    # La sesión de DB queda con RLS seteado al tenant AJENO, mientras que el
    # `user` que se pasa a la función dice ser del tenant DUEÑO — exactamente
    # el escenario que RLS debe cortar aunque el filtro de la query lo deje
    # pasar.
    async with session_factory() as s:
        await s.execute(
            text("SELECT set_config('app.current_tenant', :t, true)"),
            {"t": str(tenant_ajeno)},
        )
        match = await find_closed_episode(
            student_pseudonym=alumno,
            problema_id=problema,
            ejercicio_id=ejercicio,
            user=_user(tenant_dueno),
            db=s,
        )

    assert match is None, "RLS debe ocultar el episodio de un tenant distinto al de la sesión"

    # Confirmación positiva: con la sesión en el tenant correcto, el mismo
    # episodio sí aparece.
    match_ok = await _buscar(
        session_factory,
        tenant_id=tenant_dueno,
        student_pseudonym=alumno,
        problema_id=problema,
        ejercicio_id=ejercicio,
    )
    assert match_ok is not None
    assert match_ok.episode_id == ep.id
