"""Esquema del estudio de codificación ciega (tarea 2.1, design D1).

Contra Postgres real: las tablas existen con RLS habilitado y forzado, y las
unicidades que sostienen la identidad del dato rechazan duplicados. Se inserta
con SQL directo (no con el modelo) para probar lo que la BASE garantiza,
aunque un endpoint futuro se equivoque.

Cada test corre dentro de la transacción de `db_session` (tenant aleatorio,
rollback al final). El ciclo de migración baja y vuelve a subir la base
entera: solo corre con `CLASSIFIER_TEST_MIGRATION_CYCLE=1`, porque borra las
tablas del estudio de la base apuntada.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine

TABLAS_ESTUDIO = (
    "estudio_codificacion",
    "estudio_membresia",
    "estudio_muestra",
    "estudio_enunciado",
    "codebook_version",
    "estudio_ancla",
    "estudio_etiqueta",
    "estudio_etiqueta_historial",
    "entrenamiento_respuesta",
)

SERVICE_DIR = Path(__file__).resolve().parents[2]


async def _tablas_presentes(session) -> set[str]:
    rows = await session.execute(
        text("SELECT tablename FROM pg_tables WHERE schemaname = 'public' AND tablename = ANY(:t)"),
        {"t": list(TABLAS_ESTUDIO)},
    )
    return {r[0] for r in rows}


async def _exigir_tablas(session, *tablas: str) -> None:
    presentes = await _tablas_presentes(session)
    faltan = set(tablas) - presentes
    assert not faltan, f"faltan tablas del estudio: {sorted(faltan)}"


async def _estudio(session, tenant_id, clave: str = "estudio-prueba"):
    estudio_id = uuid4()
    await session.execute(
        text(
            "INSERT INTO estudio_codificacion (id, tenant_id, clave, titulo, traza_version, "
            "created_by) VALUES (:id, :t, :c, 'Estudio', 'traza_v1', :u)"
        ),
        {"id": estudio_id, "t": tenant_id, "c": clave, "u": uuid4()},
    )
    return estudio_id


async def _membresia(session, tenant_id, estudio_id, email: str, *, revocada: bool = False):
    membresia_id = uuid4()
    await session.execute(
        text(
            "INSERT INTO estudio_membresia (id, tenant_id, estudio_id, email, rol, alias, "
            "semilla, created_by, revocada_at) VALUES (:id, :t, :e, :email, 'codificador', "
            ":alias, :semilla, :u, CASE WHEN :rev THEN now() ELSE NULL END)"
        ),
        {
            "id": membresia_id,
            "t": tenant_id,
            "e": estudio_id,
            "email": email,
            "alias": f"C{membresia_id.int % 1000}",
            "semilla": membresia_id.int % (2**62),
            "u": uuid4(),
            "rev": revocada,
        },
    )
    return membresia_id


async def _item(session, tenant_id, estudio_id, episode_id=None):
    item_id = uuid4()
    await session.execute(
        text(
            "INSERT INTO estudio_muestra (item_id, tenant_id, estudio_id, episode_id, seq_tope, "
            "chain_hash_tope, events_count_carga, last_chain_hash_carga, estado_carga, "
            "problema_id, ejercicio_id) VALUES (:i, :t, :e, :ep, 7, :h, 8, :h, 'closed', :p, NULL)"
        ),
        {
            "i": item_id,
            "t": tenant_id,
            "e": estudio_id,
            "ep": episode_id or uuid4(),
            "h": "a" * 64,
            "p": uuid4(),
        },
    )
    return item_id


async def _codebook(session, tenant_id, estudio_id, etiqueta: str = "v0"):
    version_id = uuid4()
    await session.execute(
        text(
            "INSERT INTO codebook_version (id, tenant_id, estudio_id, etiqueta, estado, "
            "contenido_md, created_by) VALUES (:id, :t, :e, :et, 'borrador', '# x', :u)"
        ),
        {"id": version_id, "t": tenant_id, "e": estudio_id, "et": etiqueta, "u": uuid4()},
    )
    return version_id


async def _etiqueta(session, tenant_id, membresia_id, item_id, version_id):
    await session.execute(
        text(
            "INSERT INTO estudio_etiqueta (tenant_id, membresia_id, muestra_item_id, "
            "codebook_version_id, traza_version, respuestas) "
            "VALUES (:t, :m, :i, :v, 'traza_v1', '{}'::jsonb)"
        ),
        {"t": tenant_id, "m": membresia_id, "i": item_id, "v": version_id},
    )


async def test_tablas_del_estudio_existen_con_rls_habilitado_y_forzado(db_session) -> None:
    session, _ = db_session
    await _exigir_tablas(session, *TABLAS_ESTUDIO)
    rows = await session.execute(
        text(
            "SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity, "
            "(SELECT count(*) FROM pg_policies p WHERE p.tablename = c.relname) "
            "FROM pg_class c WHERE c.relname = ANY(:t) AND c.relkind = 'r'"
        ),
        {"t": list(TABLAS_ESTUDIO)},
    )
    estado = {r[0]: (r[1], r[2], r[3]) for r in rows}
    for tabla in TABLAS_ESTUDIO:
        habilitado, forzado, politicas = estado[tabla]
        assert habilitado, f"{tabla}: RLS deshabilitado"
        assert forzado, f"{tabla}: RLS sin forzar"
        assert politicas >= 1, f"{tabla}: sin policy"


async def test_rls_oculta_filas_de_otro_tenant(db_session) -> None:
    session, tenant_id = db_session
    await _exigir_tablas(session, "estudio_codificacion")
    await _estudio(session, tenant_id, "visible-solo-aca")
    await session.execute(
        text("SELECT set_config('app.current_tenant', :t, true)"), {"t": str(uuid4())}
    )
    n = (
        await session.execute(
            text("SELECT count(*) FROM estudio_codificacion WHERE clave = 'visible-solo-aca'")
        )
    ).scalar_one()
    assert n == 0


async def test_clave_de_estudio_unica_por_tenant(db_session) -> None:
    session, tenant_id = db_session
    await _exigir_tablas(session, "estudio_codificacion")
    await _estudio(session, tenant_id, "repetida")
    with pytest.raises(IntegrityError):
        async with session.begin_nested():
            await _estudio(session, tenant_id, "repetida")


async def test_membresia_activa_unica_por_email_sin_distinguir_mayusculas(db_session) -> None:
    session, tenant_id = db_session
    await _exigir_tablas(session, "estudio_codificacion", "estudio_membresia")
    estudio_id = await _estudio(session, tenant_id)
    await _membresia(session, tenant_id, estudio_id, "Ana@Ejemplo.org")
    with pytest.raises(IntegrityError):
        async with session.begin_nested():
            await _membresia(session, tenant_id, estudio_id, "ana@ejemplo.org")


async def test_membresia_revocada_no_impide_una_nueva_activa(db_session) -> None:
    session, tenant_id = db_session
    await _exigir_tablas(session, "estudio_codificacion", "estudio_membresia")
    estudio_id = await _estudio(session, tenant_id)
    await _membresia(session, tenant_id, estudio_id, "ana@ejemplo.org", revocada=True)
    await _membresia(session, tenant_id, estudio_id, "ana@ejemplo.org")
    n = (
        await session.execute(
            text("SELECT count(*) FROM estudio_membresia WHERE estudio_id = :e"),
            {"e": estudio_id},
        )
    ).scalar_one()
    assert n == 2


async def test_muestra_unica_por_estudio_y_episodio(db_session) -> None:
    session, tenant_id = db_session
    await _exigir_tablas(session, "estudio_codificacion", "estudio_muestra")
    estudio_id = await _estudio(session, tenant_id)
    episodio = uuid4()
    await _item(session, tenant_id, estudio_id, episodio)
    with pytest.raises(IntegrityError):
        async with session.begin_nested():
            await _item(session, tenant_id, estudio_id, episodio)


async def test_etiqueta_unica_por_membresia_e_item(db_session) -> None:
    session, tenant_id = db_session
    await _exigir_tablas(session, *TABLAS_ESTUDIO)
    estudio_id = await _estudio(session, tenant_id)
    membresia_id = await _membresia(session, tenant_id, estudio_id, "c1@ejemplo.org")
    item_id = await _item(session, tenant_id, estudio_id)
    version_id = await _codebook(session, tenant_id, estudio_id)
    await _etiqueta(session, tenant_id, membresia_id, item_id, version_id)
    with pytest.raises(IntegrityError):
        async with session.begin_nested():
            await _etiqueta(session, tenant_id, membresia_id, item_id, version_id)


async def test_etiqueta_sin_columnas_de_incoherencia(db_session) -> None:
    """Design D9: no existen `incoherente` ni `disiente_regla`; el desacuerdo
    se deriva de `regimen_propuesto` y `regimen`, ambos persistidos junto con
    `regimen_regla`."""
    session, _ = db_session
    await _exigir_tablas(session, "estudio_etiqueta", "entrenamiento_respuesta")
    for tabla in ("estudio_etiqueta", "entrenamiento_respuesta"):
        rows = await session.execute(
            text("SELECT column_name FROM information_schema.columns WHERE table_name = :t"),
            {"t": tabla},
        )
        columnas = {r[0] for r in rows}
        assert {"regimen", "regimen_regla", "regimen_propuesto", "traza_version"} <= columnas
        assert not columnas & {"incoherente", "disiente_regla", "disiente_de_regla"}


def _alembic(url: str, *args: str) -> subprocess.CompletedProcess:
    # Argumentos fijos del propio test (sin entrada externa).
    return subprocess.run(  # noqa: S603
        ["uv", "run", "alembic", *args],
        cwd=SERVICE_DIR,
        env={**os.environ, "CLASSIFIER_DB_URL": url},
        capture_output=True,
        text=True,
        timeout=120,
    )


async def _tablas_en(url: str) -> set[str]:
    engine = create_async_engine(url)
    try:
        async with engine.connect() as conn:
            rows = await conn.execute(
                text(
                    "SELECT tablename FROM pg_tables WHERE schemaname = 'public' "
                    "AND tablename = ANY(:t)"
                ),
                {"t": list(TABLAS_ESTUDIO)},
            )
            return {r[0] for r in rows}
    finally:
        await engine.dispose()


@pytest.mark.skipif(
    os.environ.get("CLASSIFIER_TEST_MIGRATION_CYCLE") != "1",
    reason="borra las tablas del estudio de la base apuntada; usar solo con base efímera",
)
async def test_migracion_baja_y_vuelve_a_subir_limpia(test_db_url) -> None:
    abajo = _alembic(test_db_url, "downgrade", "20260906_0006")
    assert abajo.returncode == 0, abajo.stderr
    assert await _tablas_en(test_db_url) == set()
    arriba = _alembic(test_db_url, "upgrade", "head")
    assert arriba.returncode == 0, arriba.stderr
    assert await _tablas_en(test_db_url) == set(TABLAS_ESTUDIO)
