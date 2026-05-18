#!/usr/bin/env python3
"""Evalúa el retrieval contra las golden queries.

Uso:
    python scripts/eval-retrieval.py docs/golden-queries/programacion-2.yaml
    python scripts/eval-retrieval.py <archivo.yaml> --api-base http://localhost:8009 --tenant-id <uuid>

Para cada query del YAML:
  1. Hace POST a /api/v1/retrieve
  2. Verifica que al menos un chunk contenga alguno de los `expected_contains_any`
  3. Verifica que el primer chunk tenga score >= min_score
  4. Reporta pass/fail y una métrica agregada (hit rate + latencia P50/P95)

Exit code:
    0 = todas las queries pasan
    1 = al menos una falló
    2 = error de conexión o config
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

DEFAULT_API_BASE = "http://localhost:8009"
DEFAULT_TENANT_ID = "00000000-0000-0000-0000-000000000001"
DEFAULT_USER_ID = "10000000-0000-0000-0000-000000000001"


def load_golden_yaml(path: Path) -> dict:
    """Carga el YAML sin requerir PyYAML (parseo mínimo de la estructura esperada).

    Si PyYAML está instalado lo usa, sino hace un parseo básico para el
    formato específico de nuestros golden files.
    """
    try:
        import yaml  # type: ignore

        return yaml.safe_load(path.read_text())
    except ImportError:
        return _parse_minimal_yaml(path.read_text())


def _parse_minimal_yaml(text: str) -> dict:
    """Parser minimal para nuestro formato específico de golden queries."""
    result: dict = {"queries": []}
    current: dict | None = None
    current_list_key: str | None = None

    for raw_line in text.splitlines():
        # Saltar comentarios y vacías
        stripped = raw_line.split("#", 1)[0].rstrip()
        if not stripped.strip():
            continue

        if stripped.startswith("comision:"):
            result["comision"] = stripped.split(":", 1)[1].strip().strip('"')
            continue

        if stripped.startswith("queries:"):
            continue

        # Item de lista: "  - query: ..."
        if stripped.lstrip().startswith("- query:"):
            if current is not None:
                result["queries"].append(current)
            val = stripped.split("query:", 1)[1].strip().strip('"')
            current = {"query": val, "expected_contains_any": [], "min_score": 0.3}
            current_list_key = None
            continue

        if current is None:
            continue

        # Campos de un item
        if stripped.lstrip().startswith("expected_contains_any:"):
            current_list_key = "expected_contains_any"
            current[current_list_key] = []
            continue
        if stripped.lstrip().startswith("min_score:"):
            current["min_score"] = float(stripped.split(":", 1)[1].strip())
            current_list_key = None
            continue

        # Item de lista anidada: "    - valor"
        if stripped.lstrip().startswith("-") and current_list_key:
            val = stripped.lstrip()[1:].strip().strip('"')
            current[current_list_key].append(val)
            continue

    if current is not None:
        result["queries"].append(current)

    return result


def post_retrieve(
    api_base: str,
    query: str,
    comision_id: str,
    top_k: int,
    headers: dict[str, str],
) -> tuple[dict, float]:
    """POST /api/v1/retrieve. Devuelve (respuesta_json, latencia_ms)."""
    body = json.dumps(
        {
            "query": query,
            "comision_id": comision_id,
            "top_k": top_k,
            "score_threshold": 0.0,  # eval mide el score, no filtra
        }
    ).encode("utf-8")

    req = urllib.request.Request(
        f"{api_base}/api/v1/retrieve",
        data=body,
        method="POST",
    )
    req.add_header("Content-Type", "application/json")
    for k, v in headers.items():
        req.add_header(k, v)

    start = time.perf_counter()
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    latency_ms = (time.perf_counter() - start) * 1000
    return data, latency_ms


def evaluate_query(
    query_spec: dict,
    comision_id: str,
    api_base: str,
    headers: dict[str, str],
) -> tuple[bool, str, float]:
    """Evalúa una query. Devuelve (pass, motivo, latencia_ms)."""
    try:
        resp, latency = post_retrieve(api_base, query_spec["query"], comision_id, 5, headers)
    except urllib.error.URLError as e:
        return False, f"error de red: {e}", 0.0
    except Exception as e:
        return False, f"error: {e}", 0.0

    chunks = resp.get("chunks", [])
    if not chunks:
        return False, "retrieval devolvió 0 chunks", latency

    # Check 1: algún chunk contiene alguno de los substrings esperados
    expected = query_spec.get("expected_contains_any", [])
    if expected:
        all_content = " ".join(c.get("contenido", "").lower() for c in chunks)
        matched = [s for s in expected if s.lower() in all_content]
        if not matched:
            return (
                False,
                f"ningún chunk contiene ninguno de: {expected}",
                latency,
            )

    # Check 2: score mínimo del primer chunk
    min_score = query_spec.get("min_score", 0.0)
    first_score = chunks[0].get("score_rerank") or chunks[0].get("score_vector") or 0
    if first_score < min_score:
        return (
            False,
            f"score del top chunk {first_score:.3f} < {min_score}",
            latency,
        )

    return True, "ok", latency


def main() -> int:
    parser = argparse.ArgumentParser(description="Evalúa retrieval contra golden queries")
    parser.add_argument("golden_file", type=Path)
    parser.add_argument(
        "--api-base",
        default=os.environ.get("CONTENT_API_BASE", DEFAULT_API_BASE),
    )
    parser.add_argument(
        "--tenant-id",
        default=os.environ.get("EVAL_TENANT_ID", DEFAULT_TENANT_ID),
    )
    parser.add_argument(
        "--comision-id",
        default=None,
        help="Override del comision_id (si no se pasa, se usa el del YAML)",
    )
    parser.add_argument(
        "--user-id",
        default=os.environ.get("EVAL_USER_ID", DEFAULT_USER_ID),
    )
    args = parser.parse_args()

    if not args.golden_file.exists():
        print(f"✗ Archivo no existe: {args.golden_file}", file=sys.stderr)
        return 2

    spec = load_golden_yaml(args.golden_file)
    comision_id = args.comision_id or spec.get("comision")
    if not comision_id:
        print("✗ No hay comision_id en el YAML ni en --comision-id", file=sys.stderr)
        return 2

    headers = {
        "X-User-Id": args.user_id,
        "X-Tenant-Id": args.tenant_id,
        "X-User-Email": "eval@platform.ar",
        "X-User-Roles": "docente_admin",
    }

    queries = spec["queries"]
    print(f"Evaluando {len(queries)} queries contra {args.api_base}")
    print(f"Tenant: {args.tenant_id}  Comisión: {comision_id}")
    print()

    passed = 0
    failed: list[tuple[str, str]] = []
    latencies: list[float] = []

    for i, q in enumerate(queries, 1):
        ok, reason, lat = evaluate_query(q, comision_id, args.api_base, headers)
        latencies.append(lat)
        status = "✓" if ok else "✗"
        print(f"  {status} [{i}/{len(queries)}] {q['query'][:60]:<60} ({lat:.0f}ms)")
        if ok:
            passed += 1
        else:
            failed.append((q["query"], reason))
            print(f"      {reason}")

    print()
    print(f"=== Resultado: {passed}/{len(queries)} ({passed * 100 // len(queries)}%)")
    if latencies:
        p50 = statistics.median(latencies)
        sorted_lat = sorted(latencies)
        p95 = sorted_lat[int(len(sorted_lat) * 0.95)] if len(sorted_lat) > 1 else sorted_lat[0]
        print(f"    Latencia P50: {p50:.0f}ms, P95: {p95:.0f}ms")

    if failed:
        print(f"\nFalladas ({len(failed)}):")
        for q, reason in failed:
            print(f"  - {q}")
            print(f"    {reason}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
