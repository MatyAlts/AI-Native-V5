"""Re-clasifica TODOS los episodios con la versión vigente del classifier.

Tras deployar el classifier (v4.0.0), correr DENTRO del contenedor
`tutor-socratico-classifier-service`:

    python -m classifier_service.reclassify_all <TENANT_ID>

Recorre los `episode_id` de la tabla `classifications` (is_current) y dispara
`POST /api/v1/classify_episode/{id}` contra el propio servicio (localhost). El
endpoint recomputa con el `classifier_config_hash` vigente e inserta la nueva
clasificación (append-only, ADR-010). Las etiquetas previas NO se borran —
quedan para comparar.

**Corregido (ronda de revisión 2026-09-27, gobernanza humana B3+B5): la vieja
NO siempre queda `is_current=false`.** Si el episodio tiene una anulación
humana vigente (`features['revision_humana']` en la fila `is_current=true`,
ver `services/review.py`), `persist_classification` (`pipeline.py`) NO la
degrada — la excluye explícitamente del `UPDATE` — y la fila nueva que este
backfill dispara entra con `is_current=false`: se registra (queda para
comparar, igual que siempre) pero NO gobierna. La anulación humana sigue
mandando hasta que otro humano la cambie. Antes de este fix, correr este
script sobre un episodio con anulación humana pisaba la decisión del docente
sin aviso — exactamente el bug que motivó el fix.

**Corregido (ronda de auditoría 2026-09-27, ronda 5, punto 3): el conteo SÍ
distingue las dos cosas ahora.** `ClassificationOut.is_current`
(`routes/classify_ep.py:69`) ya viaja en la respuesta HTTP — no hizo falta
tocar el contrato del endpoint, solo leer un campo que ya estaba. Un 201 con
`is_current=false` significa "se registró, pero una anulación humana previa
sigue gobernando la etiqueta oficial" — se cuenta aparte
(`nuevos_no_vigentes`) de un 201 que sí cambió la etiqueta vigente
(`nuevos_vigentes`). Importa en particular para el bloque 6: la
reclasificación masiva que sigue al bump de `tree_version` es exactamente el
escenario donde alguien va a leer "nuevos(201)=N" como "N etiquetas
cambiaron", y antes de este fix ese número podía incluir episodios donde la
etiqueta oficial no se movió.

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


def _classify_response(status_code: int, body: dict) -> str:
    """Bucket del conteo final para una respuesta de `POST /classify_episode/{id}`.

    Función pura (sin HTTP) para que el conteo sea testeable sin mockear
    `httpx.AsyncClient` — ver `tests/unit/test_reclassify_all.py`.
    """
    if status_code == 201:
        return "nuevos_vigentes" if body.get("is_current") else "nuevos_no_vigentes"
    if status_code == 200:
        return "sin_cambio"
    return "error"


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
    nuevos_vigentes = nuevos_no_vigentes = sin_cambio = errores = 0

    async with httpx.AsyncClient(timeout=30.0) as client:
        for i, eid in enumerate(episode_ids, 1):
            try:
                r = await client.post(f"{base}/api/v1/classify_episode/{eid}", headers=headers)
                bucket = _classify_response(r.status_code, r.json() if r.status_code < 400 else {})
                if bucket == "nuevos_vigentes":
                    nuevos_vigentes += 1
                elif bucket == "nuevos_no_vigentes":
                    nuevos_no_vigentes += 1
                    print(
                        f"  [{i}] {eid} -> 201 pero NO gobierna (anulación "
                        f"humana vigente en este episodio)"
                    )
                elif bucket == "sin_cambio":
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
        f"\nListo. total={total} | nuevos_vigentes(201)={nuevos_vigentes} | "
        f"nuevos_no_vigentes(201, no gobierna)={nuevos_no_vigentes} | "
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
