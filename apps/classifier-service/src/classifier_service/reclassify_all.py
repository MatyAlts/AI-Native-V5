"""Re-clasifica TODOS los episodios con la versión vigente del classifier.

Tras deployar el classifier (v4.0.0), correr DENTRO del contenedor
`tutor-socratico-classifier-service`:

    python -m classifier_service.reclassify_all <TENANT_ID>

Recorre los `episode_id` de la tabla `classifications` (is_current) y dispara
`POST /api/v1/classify_episode/{id}` contra el propio servicio (localhost). El
endpoint recomputa con el `classifier_config_hash` vigente, marca la
clasificación vieja `is_current=false` e inserta la nueva (append-only,
ADR-010). Las etiquetas previas NO se borran — quedan para comparar.

OJO v4.0.0: el juez LLM gobierna la etiqueta de los con-tutor no-delegación,
así que este backfill llama al ai-gateway (OpenRouter, google/gemini-2.5-flash)
por cada episodio con-tutor — implica costo/latencia y dependencia del gateway.

Idempotente: re-correrlo no duplica. Si un episodio ya está en la versión nueva
devuelve 200 (no-op); si recomputa con hash nuevo devuelve 201.

El TENANT_ID se saca con:
    psql -U postgres -d classifier_db -tA -c \\
      "SELECT DISTINCT tenant_id FROM classifications LIMIT 1;"
"""

from __future__ import annotations

import asyncio
import sys
from uuid import UUID

import httpx
from sqlalchemy import text

from classifier_service.config import settings
from classifier_service.db import tenant_session


async def _run(tenant_id: UUID) -> int:
    base = f"http://127.0.0.1:{settings.service_port}"
    headers = {
        "X-User-Id": "00000000-0000-0000-0000-0000000000aa",
        "X-Tenant-Id": str(tenant_id),
        "X-User-Email": "reclassify@platform.internal",
        "X-User-Roles": "classifier_worker",
        "content-type": "application/json",
    }

    async with tenant_session(tenant_id) as session:
        rows = await session.execute(
            text("SELECT DISTINCT episode_id FROM classifications WHERE is_current = true")
        )
        episode_ids = [str(r[0]) for r in rows.all()]

    total = len(episode_ids)
    print(f"Episodios a re-clasificar: {total}")
    nuevos = sin_cambio = errores = 0

    async with httpx.AsyncClient(timeout=30.0) as client:
        for i, eid in enumerate(episode_ids, 1):
            try:
                r = await client.post(f"{base}/api/v1/classify_episode/{eid}", headers=headers)
                if r.status_code == 201:
                    nuevos += 1
                elif r.status_code == 200:
                    sin_cambio += 1
                else:
                    errores += 1
                    print(f"  [{i}] {eid} -> HTTP {r.status_code}: {r.text[:140]}")
            except Exception as e:
                errores += 1
                print(f"  [{i}] {eid} -> ERROR {e}")
            if i % 25 == 0:
                print(f"  ... {i}/{total}")

    print(
        f"\nListo. total={total} | re-clasificados(201)={nuevos} | "
        f"sin_cambio(200)={sin_cambio} | errores={errores}"
    )
    return 1 if errores else 0


def main() -> None:
    if len(sys.argv) != 2:
        print("Uso: python -m classifier_service.reclassify_all <TENANT_ID>")
        raise SystemExit(2)
    raise SystemExit(asyncio.run(_run(UUID(sys.argv[1]))))


if __name__ == "__main__":
    main()
