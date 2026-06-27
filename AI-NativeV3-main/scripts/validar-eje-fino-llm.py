#!/usr/bin/env python3
"""Harness de validación del juez LLM del eje superficial↔reflexiva.

Corre `clasificar_regimen_llm` sobre un conjunto de episodios reales, compara
contra el gold docente y calcula el κ con la MISMA maquinaria que produjo el
κ del clasificador actual (`platform_ops.kappa_analysis`), para comparabilidad
directa. El delta sobre el sub-eje (κ ≈ −0,06 conductual) es la mejora a demostrar.

Uso:
    uv run python scripts/validar-eje-fino-llm.py \
        --input episodios_eje_fino.json \
        --tenant-id <UUID> \
        --model gpt-4o

Formato del JSON de entrada (lista de episodios):
    [
      {
        "episode_id": "01ab7004-...",
        "enunciado": "Crear un archivo productos.txt ...",
        "materia_id": "<UUID o null>",
        "events": [ {seq, event_type, payload}, ... ],   # del CTR
        "gold": "REFLEXIVA" | "SUPERFICIAL"               # consenso docente
      },
      ...
    ]

IMPORTANTE — sin fuga de datos (§6 del diseño):
  - Los episodios usados como few-shot (01ab7004, 23ad4ade por default) NO deben
    estar en el conjunto de evaluación. El script ADVIERTE si los encuentra.
  - Para la validación final, correr en k-fold rotando los few-shot por fold.
    Este harness mide sobre el conjunto dado; el k-fold se orquesta por afuera
    (un input por fold) o como evolución del script.

Requiere el ai-gateway corriendo y una key (BYOK por tenant/materia, o env var).
"""

from __future__ import annotations

import argparse
import asyncio
import json
from collections import Counter
from pathlib import Path
from uuid import UUID

from classifier_service.services.clients import AIGatewayClient
from classifier_service.services.regimen_llm import (
    _FEWSHOT_EPISODE_IDS,  # type: ignore[attr-defined]
    clasificar_regimen_llm,
)
from platform_ops.kappa_analysis import KappaRating, compute_cohen_kappa, format_report

_CATS = ["REFLEXIVA", "SUPERFICIAL"]


def _norm_gold(label: str) -> str:
    """Acepta el gold como 'REFLEXIVA'/'SUPERFICIAL' o como las keys de la BD."""
    s = label.strip().lower()
    if "reflex" in s:
        return "REFLEXIVA"
    if "superf" in s:
        return "SUPERFICIAL"
    raise ValueError(f"Gold no reconocido: {label!r} (esperado reflexiva/superficial)")


async def main() -> int:
    ap = argparse.ArgumentParser(description="Validación del juez LLM del eje fino")
    ap.add_argument("--input", required=True, help="JSON con los episodios")
    ap.add_argument("--tenant-id", required=True, help="UUID del tenant (para BYOK)")
    ap.add_argument("--model", default="gpt-4o", help="modelo del juez")
    ap.add_argument("--ai-gateway-url", default="http://127.0.0.1:8011")
    ap.add_argument("--confianza-min", type=float, default=0.70)
    ap.add_argument("--out", default="", help="JSON opcional para volcar el detalle")
    args = ap.parse_args()

    episodios = json.loads(Path(args.input).read_text(encoding="utf-8"))
    tenant_id = UUID(args.tenant_id)
    client = AIGatewayClient(base_url=args.ai_gateway_url)

    # Aviso de leakage: few-shot dentro del conjunto de evaluación.
    ids = {str(e.get("episode_id", "")) for e in episodios}
    solapados = {fid for fid in _FEWSHOT_EPISODE_IDS if any(i.startswith(fid) for i in ids)}
    if solapados:
        print(f"[ADVERTENCIA] Few-shot dentro del eval (LEAKAGE): {solapados}. "
              f"Excluilos del conjunto o rotá few-shot por fold.\n")

    ratings: list[KappaRating] = []
    estados: Counter[str] = Counter()
    detalle: list[dict] = []

    for ep in episodios:
        eid = str(ep["episode_id"])
        gold = _norm_gold(ep["gold"])
        materia = ep.get("materia_id")
        res = await clasificar_regimen_llm(
            events=ep.get("events", []),
            enunciado=ep.get("enunciado", ""),
            episode_id=eid,
            complete=client.complete,
            model=args.model,
            tenant_id=tenant_id,
            materia_id=UUID(materia) if materia else None,
            confianza_min=args.confianza_min,
        )
        estados[res.estado] += 1
        detalle.append({
            "episode_id": eid, "gold": gold, "estado": res.estado,
            "regimen": res.regimen, "confianza": res.confianza, "razon": res.razon,
        })
        # Solo los "ok" entran al κ; el resto va a revisión humana (se cuenta aparte).
        if res.estado == "ok" and res.regimen is not None:
            ratings.append(KappaRating(episode_id=eid, rater_a=gold, rater_b=res.regimen))
        print(f"  {eid[:8]}  gold={gold:11}  →  {res.estado:14} "
              f"{res.regimen or '—':11} (conf={res.confianza})")

    print("\n" + "=" * 60)
    print(f"Episodios: {len(episodios)} · estados: {dict(estados)}")
    print(f"Entran al κ (estado=ok): {len(ratings)}")

    if len(ratings) >= 2:
        try:
            r = compute_cohen_kappa(ratings, categories=_CATS)
            print("\n" + format_report(r))
            print(f"\n>>> κ del juez LLM = {r.kappa:.3f}  "
                  f"IC95% [{r.kappa_ci_95[0]:.3f}, {r.kappa_ci_95[1]:.3f}]  "
                  f"AC1 = {r.ac1:.3f}  (vs κ ≈ −0,06 conductual)")
        except Exception as exc:
            print(f"\nNo se pudo computar κ: {exc}")
    else:
        print("\nMuy pocos casos 'ok' para computar κ.")

    if args.out:
        Path(args.out).write_text(
            json.dumps(detalle, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"\nDetalle volcado en {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
