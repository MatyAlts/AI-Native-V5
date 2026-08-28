"""`correcciones_ia.artefacto_sha256` nullable, para que el olvido no reviente

El derecho al olvido vacia ese campo porque es el MISMO hash que se acaba de
borrar de `entregas`, con el `orden` del ejercicio al lado para saber cual era
el enunciado: el hash de un archivo chico es reversible por fuerza bruta si
alguien tiene la consigna. Borrar la fila del artefacto y dejar su hash aca es
hacer la mitad del trabajo por el que se borro.

Lo vaciaba con `""`. **Y el UNIQUE de idempotencia incluye esa columna**
(`uq_correccion_ia_idempotencia` = tenant + entrega + orden + rubrica + sha).

Un alumno que reentrego despues de un `returned` tiene DOS correcciones sobre
la misma entrega, el mismo orden y la misma rubrica, con sha distinto — porque
`_persistir_artefactos` reemplaza el artefacto y el codigo nuevo hashea
distinto. Al olvidarlo, las dos filas iban a `""`, chocaban contra el UNIQUE
(que no es deferrable) y **la anonimizacion entera se caia con IntegrityError**.

Justo para los alumnos que mas interactuaron con la plataforma, y en el camino
que existe para cumplir un compromiso del consentimiento firmado.

`NULL` en vez de `""` porque en Postgres dos NULL no colisionan en un UNIQUE —
y porque es lo que el dato realmente es: no hay hash, se borro. El test que
cubria el olvido creaba UNA sola correccion, asi que nunca vio el choque.

La columna nace `NOT NULL` en `20260818_0003` y esa sigue siendo la regla para
una correccion viva: `_cerrar_con_resultado` y el INSERT de la ruta siempre lo
escriben. Lo que esta migracion habilita es el estado terminal de una fila
anonimizada.

Revision ID: 20260827_0002
Revises: 20260827_0001
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260827_0002"
down_revision: str | None = "20260827_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "correcciones_ia",
        "artefacto_sha256",
        existing_type=sa.String(length=64),
        nullable=True,
    )


def downgrade() -> None:
    # Las filas anonimizadas tienen NULL y no hay forma de reconstruir el hash
    # (ese es el punto). Se las lleva a "" para poder volver a NOT NULL; el
    # choque contra el UNIQUE que eso puede producir es exactamente el bug que
    # esta migracion arregla, asi que bajar no es una operacion segura si ya
    # hubo olvidos con reentregas.
    op.execute("UPDATE correcciones_ia SET artefacto_sha256 = '' WHERE artefacto_sha256 IS NULL")
    op.alter_column(
        "correcciones_ia",
        "artefacto_sha256",
        existing_type=sa.String(length=64),
        nullable=False,
    )
