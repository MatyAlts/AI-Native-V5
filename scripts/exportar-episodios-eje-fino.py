#!/usr/bin/env python3
"""Exporta los episodios del eje superficial↔reflexiva a un JSON para validar el juez LLM.

Junta, desde las bases de producción:
  - el GOLD docente (interrater_ratings, classifier_db): episodios doble-codificados
    donde ambos codificadores coinciden y la etiqueta es superficial o reflexiva;
  - el SUBGRUPO de la máquina (classifications, classifier_db): para saber cuáles caen
    en la zona gris de colaboradores (los que el juez debe clasificar);
  - los EVENTS del episodio (events, ctr_store): la conversación cruda que lee el juez.

Produce el JSON que consume `validar-eje-fino-llm.py`:
    [ {episode_id, gold, materia_id, events:[...], enunciado}, ... ]

Uso:
    uv run python scripts/exportar-episodios-eje-fino.py \
        --classifier-db "$CLASSIFIER_DB_URL" \
        --ctr-db "$CTR_STORE_URL" \
        --out episodios_eje_fino.json \
        [--solo-zona-gris]   # exporta solo colaborador_* (lo que pasa por el juez)

Los rater_id por default son los dos codificadores del piloto; override con --raters.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path

import asyncpg

RATER_A_DEFAULT = "59218f74-a2ca-517c-a8cc-a4ac089c33b3"
RATER_B_DEFAULT = "cf6bd3bb-98f1-5e4a-982d-34858d199a1f"
EJE_FINO_LABELS = ("apropiacion_superficial", "apropiacion_reflexiva")
ZONA_GRIS = ("colaborador_reflexivo", "colaborador_funcional")


# El driver del proyecto es 'postgresql+asyncpg://...'; asyncpg quiere 'postgresql://...'.
def _dsn(url: str) -> str:
    return url.replace("postgresql+asyncpg://", "postgresql://").replace("+asyncpg", "")


GOLD_SQL = """
WITH humans AS (
  SELECT episode_id,
         max(label) FILTER (WHERE rater_id = $1) AS h1,
         max(label) FILTER (WHERE rater_id = $2) AS h2
  FROM interrater_ratings WHERE protocol = 'ejes' GROUP BY episode_id
),
gold AS (
  SELECT episode_id, h1 AS gold FROM humans
  WHERE h1 IS NOT NULL AND h1 = h2 AND h1 = ANY($3::text[])
)
SELECT g.episode_id::text AS episode_id, g.gold,
       c.comision_id::text AS comision_id,
       c.features->'subgrupo'->>'key' AS subgrupo
FROM gold g
JOIN classifications c ON c.episode_id = g.episode_id AND c.is_current = true
"""

EVENTS_SQL = """
SELECT seq, event_type, payload
FROM events WHERE episode_id = $1 ORDER BY seq
"""


async def main() -> int:
    ap = argparse.ArgumentParser(description="Export episodios eje fino → JSON")
    ap.add_argument("--classifier-db", default=os.environ.get("CLASSIFIER_DB_URL", ""))
    ap.add_argument(
        "--ctr-db", default=os.environ.get("CTR_STORE_URL", os.environ.get("CTR_DB_URL", ""))
    )
    ap.add_argument("--out", default="episodios_eje_fino.json")
    ap.add_argument("--raters", nargs=2, default=[RATER_A_DEFAULT, RATER_B_DEFAULT])
    ap.add_argument(
        "--solo-zona-gris",
        action="store_true",
        help="exporta solo colaborador_* (lo que el juez realmente clasifica)",
    )
    args = ap.parse_args()

    if not args.classifier_db or not args.ctr_db:
        print("Faltan --classifier-db / --ctr-db (o las env CLASSIFIER_DB_URL / CTR_STORE_URL).")
        return 2

    cls_conn = await asyncpg.connect(_dsn(args.classifier_db))
    ctr_conn = await asyncpg.connect(_dsn(args.ctr_db))
    try:
        gold_rows = await cls_conn.fetch(
            GOLD_SQL, args.raters[0], args.raters[1], list(EJE_FINO_LABELS)
        )
        print(f"Episodios gold del eje fino: {len(gold_rows)}")

        salida: list[dict] = []
        for row in gold_rows:
            subgrupo = row["subgrupo"]
            if args.solo_zona_gris and subgrupo not in ZONA_GRIS:
                continue
            ev_rows = await ctr_conn.fetch(EVENTS_SQL, row["episode_id"])
            events = []
            for ev in ev_rows:
                payload = ev["payload"]
                if isinstance(payload, str):
                    try:
                        payload = json.loads(payload)
                    except json.JSONDecodeError:
                        payload = {}
                events.append(
                    {
                        "seq": ev["seq"],
                        "event_type": ev["event_type"],
                        "payload": payload or {},
                    }
                )
            salida.append(
                {
                    "episode_id": row["episode_id"],
                    "gold": row["gold"],
                    "materia_id": None,  # classifications no expone materia_id; BYOK cae a tenant
                    "subgrupo": subgrupo,
                    "enunciado": "",  # opcional; enriquecer desde academic_main si hace falta
                    "events": events,
                }
            )
    finally:
        await cls_conn.close()
        await ctr_conn.close()

    Path(args.out).write_text(json.dumps(salida, ensure_ascii=False, indent=2), encoding="utf-8")
    zona = sum(1 for e in salida if e["subgrupo"] in ZONA_GRIS)
    print(f"Exportados {len(salida)} episodios ({zona} en zona gris de colaboradores) → {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
