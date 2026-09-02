"""`correcciones_ia`: con que se corrigio (motor, prompt, modelo)

Cuatro columnas nullable para el corrector propio. Una nota es una decision
sobre una persona, y «por que le puso 6?» tres meses despues solo tiene
respuesta si quedo registrado con que texto exacto y que modelo se produjo.

NULL en las filas de Active-IA, y esa es la respuesta correcta para ellas: el
prompt y el modelo son de ellos y nosotros no los vemos. Por eso son nullable y
no llevan default: un `motor='activeia'` retroactivo diria que sabemos algo del
prompt de ellos que no sabemos.

`rubrica_id` NO se toca: ya identifica contra que rubrica se corrigio. En el
camino nativo lleva `nativa:<sha256[:32]>` de la rubrica local, y como esa
columna entra en `uq_correccion_ia_idempotencia`, editar la rubrica invalida la
correccion anterior por construccion.

Revision ID: 20260902_0001
Revises: 20260827_0002
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260902_0001"
down_revision: str | None = "20260827_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("correcciones_ia", sa.Column("motor", sa.String(length=20), nullable=True))
    op.add_column(
        "correcciones_ia", sa.Column("prompt_version", sa.String(length=100), nullable=True)
    )
    op.add_column("correcciones_ia", sa.Column("prompt_hash", sa.String(length=64), nullable=True))
    op.add_column("correcciones_ia", sa.Column("modelo", sa.String(length=100), nullable=True))


def downgrade() -> None:
    op.drop_column("correcciones_ia", "modelo")
    op.drop_column("correcciones_ia", "prompt_hash")
    op.drop_column("correcciones_ia", "prompt_version")
    op.drop_column("correcciones_ia", "motor")
