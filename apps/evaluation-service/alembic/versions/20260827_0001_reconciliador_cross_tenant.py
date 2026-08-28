"""El reconciliador necesita poder ver los tenants con correcciones colgadas

`tenants_con_running()` era la unica query del servicio que tiene que CRUZAR
tenants: corre sin request, o sea sin `app.current_tenant`, para descubrir
sobre que tenants hay que reconciliar. Su docstring afirmaba que "corre como
owner para poder ver todos los tenants".

**Era falso, y el fallo era silencioso.** Las migraciones corren como
`postgres` (ver `scripts/migrate-all.sh`), asi que `postgres` es el owner de la
tabla; el runtime conecta como `academic_user`, que NO es owner y se creo con
un `CREATE USER` pelado — sin `SUPERUSER` y sin `BYPASSRLS`
(`infrastructure/postgres/init-dbs.sql`). La policy de `correcciones_ia` exige
`tenant_id = current_setting('app.current_tenant', true)::uuid`, y sin ese
setting `current_setting(..., true)` devuelve NULL: la comparacion da NULL y la
fila se filtra. **Cero filas, sin error.**

Consecuencia: la pasada de arranque y el loop periodico iteraban sobre una
lista vacia para siempre. Las correcciones huerfanas de un deploy quedaban
girando en el panel del docente, y como `consumidas_hoy` cuenta `pending` y
`running`, le comian la cuota diaria sin liberarse nunca. El design D9 se apoya
en el reconciliador para justificar `BackgroundTasks` sin cola durable: el
sosten no existia.

**Por que una policy y no `SECURITY DEFINER`**: la tabla tiene `FORCE ROW LEVEL
SECURITY`, que somete al owner a sus propias policies. Una funcion
`SECURITY DEFINER` correria como `postgres` — el owner — y quedaria filtrada
igual. `FORCE` esta puesto a proposito y no se toca.

**Por que `FOR SELECT` y no una policy general**: aunque el flag se filtre a una
transaccion que no deberia tenerlo, lo unico que habilita es LEER. Las
escrituras del reconciliador siguen yendo por `tenant_session(tenant_id)`, una
por tenant, bajo la policy de siempre. Y el unico codigo que prende el flag
(`tenants_con_running`) selecciona `tenant_id` y nada mas: nunca contenido.

Revision ID: 20260827_0001
Revises: 20260818_0004
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260827_0001"
down_revision: str | None = "20260818_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_POLICY = "correcciones_ia_reconciliador_lectura"


def upgrade() -> None:
    op.execute(f"DROP POLICY IF EXISTS {_POLICY} ON correcciones_ia")
    # `app.reconciliador` lo prende `tenants_con_running()` con SET LOCAL, asi
    # que vive lo que dura esa transaccion y nada mas.
    op.execute(
        f"CREATE POLICY {_POLICY} ON correcciones_ia "
        "FOR SELECT "
        "USING (current_setting('app.reconciliador', true) = 'on')"
    )


def downgrade() -> None:
    op.execute(f"DROP POLICY IF EXISTS {_POLICY} ON correcciones_ia")
