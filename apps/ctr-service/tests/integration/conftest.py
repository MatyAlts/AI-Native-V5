"""Fixtures para tests de integración.

Skip automático si Docker no está disponible. Los tests de este dir se
ejecutan en CI pero no en sandboxes sin Docker.

Las fixtures de Postgres/Redis viven acá y no en un módulo de tests porque
las comparten varios archivos — entre ellos el test de contrato entre
tutor-service y ctr-service.
"""

from __future__ import annotations

import shutil

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


def _docker_available() -> bool:
    """True si podemos correr contenedores."""
    if shutil.which("docker") is None:
        return False
    import subprocess

    try:
        result = subprocess.run(["docker", "info"], capture_output=True, timeout=5)
        return result.returncode == 0
    except Exception:
        return False


requires_docker = pytest.mark.skipif(
    not _docker_available(),
    reason="Docker no disponible (tests de integración se corren en CI)",
)


@pytest.fixture(scope="module")
def pg_container():
    from testcontainers.postgres import PostgresContainer

    with PostgresContainer("postgres:16-alpine") as pg:
        yield pg


@pytest.fixture(scope="module")
def redis_container():
    from testcontainers.redis import RedisContainer

    with RedisContainer("redis:7-alpine") as r:
        yield r


@pytest.fixture(scope="module")
def pg_app_url(pg_container) -> str:
    """Setup one-shot del schema + función RLS + app_user. Devuelve la URL
    asyncpg del `app_user` (NOSUPERUSER NOBYPASSRLS).

    Es **sync** y usa psycopg2 internamente vía SQLAlchemy: así no toca
    el event loop async y no choca con la fixture function-scoped que
    crea el engine asyncpg para cada test.

    El user del testcontainer (`test`) es bootstrap superuser → exempt
    de RLS aun con FORCE. Por eso los tests deben conectar como `app_user`.
    """
    from sqlalchemy import create_engine

    superuser_url = pg_container.get_connection_url()  # postgresql+psycopg2
    su_engine = create_engine(superuser_url, future=True)
    with su_engine.begin() as conn:
        conn.execute(text('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"'))
        conn.execute(
            text("""
            CREATE OR REPLACE FUNCTION apply_tenant_rls(tbl regclass)
            RETURNS void AS $$
            BEGIN
                EXECUTE format('ALTER TABLE %s ENABLE ROW LEVEL SECURITY', tbl);
                EXECUTE format('ALTER TABLE %s FORCE ROW LEVEL SECURITY', tbl);
                EXECUTE format('DROP POLICY IF EXISTS tenant_isolation ON %s', tbl);
                EXECUTE format('
                    CREATE POLICY tenant_isolation ON %s
                    USING (tenant_id = current_setting(''app.current_tenant'')::uuid)
                ', tbl);
            END;
            $$ LANGUAGE plpgsql;
        """)
        )
        conn.execute(
            text("""
            DO $$ BEGIN
                IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_user') THEN
                    CREATE ROLE app_user WITH LOGIN PASSWORD 'app_pass'
                        NOSUPERUSER NOBYPASSRLS;
                END IF;
            END $$;
        """)
        )
        conn.execute(text("GRANT ALL ON SCHEMA public TO app_user"))

    from ctr_service.models import Base

    with su_engine.begin() as conn:
        Base.metadata.create_all(conn)
        for table in ("episodes", "events", "dead_letters"):
            conn.execute(text(f"ALTER TABLE {table} OWNER TO app_user"))
            conn.execute(text(f"SELECT apply_tenant_rls('{table}')"))
        conn.execute(
            text("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO app_user")
        )
        conn.execute(text("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO app_user"))
    su_engine.dispose()

    return superuser_url.replace("postgresql+psycopg2://", "postgresql+asyncpg://").replace(
        "test:test@", "app_user:app_pass@"
    )


@pytest.fixture
async def pg_engine(pg_app_url):
    """Engine asyncpg per-test. Function-scoped para no chocar con el
    event loop closed entre tests.

    También patchea el `get_engine()` / `get_session_factory()` globales
    de `ctr_service.db.session` para que `tenant_session()` (usado por el
    worker) apunte al testcontainer en vez de a `settings.ctr_db_url`.
    """
    engine = create_async_engine(pg_app_url, echo=False)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    from ctr_service.db import session as db_session_module

    prev_engine = db_session_module._engine
    prev_factory = db_session_module._session_factory
    db_session_module._engine = engine
    db_session_module._session_factory = factory

    try:
        yield engine
    finally:
        db_session_module._engine = prev_engine
        db_session_module._session_factory = prev_factory
        await engine.dispose()


@pytest.fixture
async def session_factory(pg_engine):
    return async_sessionmaker(pg_engine, expire_on_commit=False)
