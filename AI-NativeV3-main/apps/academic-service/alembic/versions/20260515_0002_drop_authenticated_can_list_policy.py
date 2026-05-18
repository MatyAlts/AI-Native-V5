"""universidades: drop policy laxa authenticated_can_list

Revision ID: 20260515_0002
Revises: 20260515_0001
Create Date: 2026-05-15

Reemplaza la policy laxa por un endpoint dedicado `GET /api/v1/universidades/mine`
que filtra por rol activo del caller (usuarios_comision o inscripciones).

Antes de aplicar esta migration:
- El endpoint nuevo ya esta vivo en academic-service.
- Los 3 frontends (web-admin/web-teacher/web-student) apuntan a `/universidades/mine`.

Las otras 2 policies vigentes sobre `universidades` se mantienen:
- `tenant_isolation` (filtra por current_setting('app.current_tenant'))
- `superadmin_view_all` (permite ver todas cuando user_roles incluye superadmin)
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "20260515_0002"
down_revision: str | Sequence[str] | None = "20260515_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1) SECURITY DEFINER function: lista IDs de universidades donde el caller
    #    tiene rol activo (docente o estudiante). Corre como dueño (postgres)
    #    y bypassa RLS — legitimo porque filtra explicitamente por user_id.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION universidades_for_user(p_user_id UUID)
        RETURNS TABLE (universidad_id UUID)
        LANGUAGE sql
        SECURITY DEFINER
        STABLE
        SET search_path = public
        AS $$
            SELECT DISTINCT c.universidad_id
            FROM carreras c
            JOIN planes_estudio pe ON pe.carrera_id = c.id
            JOIN materias m ON m.plan_id = pe.id
            JOIN comisiones co ON co.materia_id = m.id
            JOIN usuarios_comision uc ON uc.comision_id = co.id
            WHERE uc.user_id = p_user_id
              AND uc.deleted_at IS NULL
              AND c.deleted_at IS NULL
              AND pe.deleted_at IS NULL
              AND m.deleted_at IS NULL
              AND co.deleted_at IS NULL
            UNION
            SELECT DISTINCT c.universidad_id
            FROM carreras c
            JOIN planes_estudio pe ON pe.carrera_id = c.id
            JOIN materias m ON m.plan_id = pe.id
            JOIN comisiones co ON co.materia_id = m.id
            JOIN inscripciones i ON i.comision_id = co.id
            WHERE i.student_pseudonym = p_user_id
              AND i.estado = 'activa'
              AND i.deleted_at IS NULL
              AND c.deleted_at IS NULL
              AND pe.deleted_at IS NULL
              AND m.deleted_at IS NULL
              AND co.deleted_at IS NULL
        $$;
        """
    )
    # Permiso explicito para el rol no-superuser
    op.execute(
        "GRANT EXECUTE ON FUNCTION universidades_for_user(UUID) TO academic_user"
    )

    # 2) Drop la policy laxa que permitia a cualquier user listar TODAS las unis.
    op.execute("DROP POLICY IF EXISTS authenticated_can_list ON universidades")

    # 3) Nueva policy: usar la funcion SECURITY DEFINER para autorizar SELECT
    #    sobre las universidades del caller. Esta policy reemplaza a la laxa
    #    `authenticated_can_list`. NO se aplica a superadmin (que ya tiene
    #    su propia policy `superadmin_view_all`) ni rompe `tenant_isolation`.
    op.execute(
        """
        CREATE POLICY user_can_view_own_unis ON universidades
        FOR SELECT
        USING (
            current_setting('app.current_user_id', true) IS NOT NULL
            AND current_setting('app.current_user_id', true) <> ''
            AND id IN (
                SELECT universidad_id
                FROM universidades_for_user(
                    current_setting('app.current_user_id', true)::uuid
                )
            )
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS user_can_view_own_unis ON universidades")
    op.execute("DROP FUNCTION IF EXISTS universidades_for_user(UUID)")
    # Re-crea la policy laxa para rollback. NO recomendado en prod sin
    # antes revertir el endpoint `/mine` en los frontends.
    op.execute(
        """
        CREATE POLICY authenticated_can_list ON universidades
        FOR SELECT
        USING (current_setting('app.current_tenant', true) IS NOT NULL
               AND current_setting('app.current_tenant', true) <> '')
        """
    )
