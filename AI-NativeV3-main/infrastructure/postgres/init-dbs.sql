-- ADR-003: bases lógicas con usuarios separados.
-- Corre al primer arranque del contenedor Postgres (docker-entrypoint-initdb.d).
--
-- Bases:
--   academic_main   → users, comisiones, episodes meta, Casbin policies
--   ctr_store       → events + dead_letters (CTR criptográfico append-only)
--   classifier_db   → classifications (con is_current + hash)
--   content_db      → materials + chunks (pgvector para RAG)
--
-- identity_store removed in session 2026-04-21 (BUG-25, Option A).
-- Pseudonymization is implemented in packages/platform-ops/privacy.py
-- rotating student_pseudonym in academic_main.episodes (see ADR-003 update).
-- identity-service itself was deprecated in ADR-041 (auth moved to api-gateway).
-- If F8+ requires persistent audit log of pseudonym rotations, restore this DB
-- via a fresh service (the original apps/identity-service/ no longer exists).

-- ── Usuarios ─────────────────────────────────────────────────────────

CREATE USER academic_user   WITH PASSWORD 'academic_pass';
CREATE USER ctr_user        WITH PASSWORD 'ctr_pass';
CREATE USER classifier_user WITH PASSWORD 'classifier_pass';
CREATE USER content_user    WITH PASSWORD 'content_pass';
-- identity_user role removed alongside identity_store (BUG-25, Option A,
-- session 2026-04-21). Restore here if F8+ reintroduces the identity DB.

-- ── Bases + ownership ────────────────────────────────────────────────

CREATE DATABASE academic_main  OWNER academic_user;
CREATE DATABASE ctr_store      OWNER ctr_user;
CREATE DATABASE classifier_db  OWNER classifier_user;
CREATE DATABASE content_db     OWNER content_user;

-- ── Helper RLS reutilizable (ADR-001) ────────────────────────────────
-- Cada migration que cree tabla con tenant_id llama:
--   SELECT apply_tenant_rls('nombre_tabla');

-- ── academic_main ────────────────────────────────────────────────────

\c academic_main
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
CREATE EXTENSION IF NOT EXISTS btree_gin;

CREATE OR REPLACE FUNCTION apply_tenant_rls(table_name text)
RETURNS void AS $$
BEGIN
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', table_name);
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', table_name);
    EXECUTE format(
        'CREATE POLICY tenant_isolation ON %I USING (tenant_id = current_setting(''app.current_tenant'', true)::uuid)',
        table_name
    );
END;
$$ LANGUAGE plpgsql;

-- ── content_db (RAG con pgvector, ADR-011) ──────────────────────────

\c content_db
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;

CREATE OR REPLACE FUNCTION apply_tenant_rls(table_name text)
RETURNS void AS $$
BEGIN
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', table_name);
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', table_name);
    EXECUTE format(
        'CREATE POLICY tenant_isolation ON %I USING (tenant_id = current_setting(''app.current_tenant'', true)::uuid)',
        table_name
    );
END;
$$ LANGUAGE plpgsql;

-- ── ctr_store (cadena criptográfica append-only) ────────────────────

\c ctr_store
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE OR REPLACE FUNCTION apply_tenant_rls(table_name text)
RETURNS void AS $$
BEGIN
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', table_name);
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', table_name);
    EXECUTE format(
        'CREATE POLICY tenant_isolation ON %I USING (tenant_id = current_setting(''app.current_tenant'', true)::uuid)',
        table_name
    );
END;
$$ LANGUAGE plpgsql;

-- ── classifier_db ────────────────────────────────────────────────────

\c classifier_db
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE OR REPLACE FUNCTION apply_tenant_rls(table_name text)
RETURNS void AS $$
BEGIN
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', table_name);
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', table_name);
    EXECUTE format(
        'CREATE POLICY tenant_isolation ON %I USING (tenant_id = current_setting(''app.current_tenant'', true)::uuid)',
        table_name
    );
END;
$$ LANGUAGE plpgsql;

-- ── identity_store removed in session 2026-04-21 (BUG-25, Option A) ──
-- The identity_store DB and its extensions block were removed because the
-- schema was never implemented; pseudonymization lives in
-- packages/platform-ops/privacy.py and rotates student_pseudonym in
-- academic_main.episodes. See ADR-003 update for the rationale.
