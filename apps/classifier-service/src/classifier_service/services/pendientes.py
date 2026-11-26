"""Episodios pendientes de clasificar (HU-051).

Cuando el `POST /classify_episode/{id}` responde 202 porque el CTR todavía no
guardó el `episodio_cerrado` (HU-050), el episodio se anota en
`clasificaciones_pendientes` (migración 20261126_0009) y el barrido
(`services/barrido.py`) lo reintenta solo.

También vive acá la lista de tenants que barre el servicio. `classifier_db`
tiene RLS FORZADO (ADR-001) y el usuario del servicio no ve ninguna fila sin
`app.current_tenant`: no hay forma de preguntarle a la base «qué tenants tienen
pendientes» sin abrir un agujero en el aislamiento. Por eso la lista sale de
dos lugares, sin consultar la base:

- `settings.barrido_tenant_ids` (env `BARRIDO_TENANT_IDS`, JSON), que
  sobrevive a los reinicios. En prod va el tenant del piloto.
- Cada tenant que hace un `POST /classify_episode` en este proceso
  (`registrar_tenant`). Tras un reinicio, los pendientes de un tenant que no
  está en el env se vuelven a barrer en cuanto llega el primer cierre de ese
  tenant.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

TABLA = "clasificaciones_pendientes"

# Lista compartida con el bucle del barrido (`main.lifespan` le pasa este mismo
# objeto): el bucle toma una copia en cada pasada, así que un tenant registrado
# entre pasadas entra en la siguiente.
TENANTS_DEL_BARRIDO: list[UUID] = []


def registrar_tenant(tenant_id: UUID) -> None:
    if tenant_id not in TENANTS_DEL_BARRIDO:
        TENANTS_DEL_BARRIDO.append(tenant_id)


async def anotar_pendiente(
    session: AsyncSession,
    tenant_id: UUID,
    episode_id: UUID,
    comision_id: UUID | None,
) -> None:
    """Anota el episodio como pendiente. Repetirlo no duplica ni lo reabre.

    `ON CONFLICT DO NOTHING`: un 202 repetido no toca la fila, así que
    `creado_at` sigue siendo la primera anotación (de ahí se cuenta el
    vencimiento de N03) y un 'descartado' no vuelve a 'pendiente'.
    """
    await session.execute(
        text(
            f"INSERT INTO {TABLA} (tenant_id, episode_id, comision_id) "
            "VALUES (:t, :ep, :c) ON CONFLICT (tenant_id, episode_id) DO NOTHING"
        ),
        {
            "t": str(tenant_id),
            "ep": str(episode_id),
            "c": str(comision_id) if comision_id else None,
        },
    )


__all__ = ["TABLA", "TENANTS_DEL_BARRIDO", "anotar_pendiente", "registrar_tenant"]
