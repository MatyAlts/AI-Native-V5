"""unicidad_por_eventos_vistos

Revision ID: 20261126_0008
Revises: 20261104_0007
Create Date: 2026-11-26

HU-050: la clasificación espera la traza completa. Hasta acá la unicidad de
`classifications` era `UNIQUE (episode_id, classifier_config_hash)`: una sola
fila por episodio y configuración. Con eso, si el POST de cierre leía la traza
antes de que la cola del CTR terminara de guardarla, la etiqueta calculada a
medias quedaba congelada (233 de 6.387 episodios en prod).

Desde la HU-050 cada fila de máquina guarda `features['eventos_vistos']` y un
POST que encuentra MÁS eventos recalcula con la misma configuración: fila nueva
vigente, la anterior `is_current=false` (append-only). Eso son dos filas con el
mismo `(episode_id, classifier_config_hash)`, así que la unicidad pasa a ser:

    UNIQUE (episode_id, classifier_config_hash,
            COALESCE(features ->> 'eventos_vistos', ''))

- Las filas anteriores a la HU (sin `eventos_vistos`) caen todas en `''`: para
  ellas la regla es exactamente la vieja, una por `(episodio, hash)`. Por eso el
  `COALESCE` y no la columna JSON a secas (con NULL, Postgres dejaría duplicar).
- Sigue siendo la red de la carrera entre dos POST concurrentes que vieron la
  misma traza: el segundo INSERT choca y el handler recupera la fila ganadora.
- No toca filas ni columnas: crea el índice nuevo (antes de soltar el viejo,
  para que la tabla no quede ni un instante sin unicidad) y suelta la
  constraint. La regla nueva es más ancha que la vieja, así que el índice se
  crea sin conflictos sobre cualquier dato existente.

Como el resto de lo exclusivo de Postgres (ver 20261104_0007), el índice vive
solo acá y no en la metadata del modelo: varios tests hacen `create_all` sobre
SQLite.

Downgrade: vuelve a la constraint vieja. Solo es posible mientras no haya dos
filas con el mismo `(episode_id, classifier_config_hash)`, es decir, antes del
primer recálculo de la HU-050. Si ya las hay, falla con un mensaje explícito y
NO borra nada: decidir qué fila sobra es una decisión de datos, no de esquema.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
from sqlalchemy import text

revision: str = "20261126_0008"
down_revision: str | None = "20261104_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

INDICE = "uq_classifications_episode_config_vistos"
CONSTRAINT_VIEJA = "uq_classifications_episode_config"


def upgrade() -> None:
    op.execute(
        f"CREATE UNIQUE INDEX {INDICE} ON classifications "
        "(episode_id, classifier_config_hash, (COALESCE(features ->> 'eventos_vistos', '')))"
    )
    op.drop_constraint(CONSTRAINT_VIEJA, "classifications", type_="unique")


def downgrade() -> None:
    bind = op.get_bind()
    duplicados = bind.execute(
        text(
            "SELECT count(*) FROM ("
            "  SELECT 1 FROM classifications"
            "  GROUP BY episode_id, classifier_config_hash HAVING count(*) > 1"
            ") d"
        )
    ).scalar_one()
    if duplicados:
        raise RuntimeError(
            f"No se puede volver a UNIQUE (episode_id, classifier_config_hash): "
            f"{duplicados} pares ya tienen mas de una fila (recalculos de la HU-050). "
            "No se borra nada automaticamente; resolver los datos a mano antes."
        )
    op.create_unique_constraint(
        CONSTRAINT_VIEJA, "classifications", ["episode_id", "classifier_config_hash"]
    )
    op.execute(f"DROP INDEX IF EXISTS {INDICE}")
