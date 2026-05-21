"""Verificacion continua del deploy del integrity-attestation-service (A3 del plan-accion).

Cierra parcialmente P0-3 del PlanMejora.md (la parte que SI es codigo: el
checklist de deploy ya existe en docs/pilot/attestation-deploy-checklist.md
para que DI UTN lo ejecute). Este script corre desde la maquina del doctorando
contra el VPS UTN y verifica que el servicio sigue procesando attestations
correctamente.

Chequeos
--------
1. HTTP health (GET /health/ready, GET /).
2. Pubkey servida (GET /api/v1/attestations/pubkey) coincide con la PEM
   distribuida al doctorando (Paso 2 del checklist).
3. Si CTR_REDIS_URL esta disponible: XLEN del stream attestation.requests
   (consumer lag). Esperado: 0 o creciendo lentamente. Si crece sin drenar,
   el consumer del VPS no esta procesando.
4. Si se pasa --day YYYY-MM-DD: descarga el JSONL del dia y verifica
   cada attestation con la pubkey publica (sin enviar nada al VPS — solo lee).

Uso
---
    # Healthcheck basico
    python scripts/verify-attestation-deployment.py --service-url https://attestation.utn.edu.ar

    # Healthcheck + verificacion bit-exacta de un dia
    python scripts/verify-attestation-deployment.py \\
        --service-url https://attestation.utn.edu.ar \\
        --day 2026-05-15 \\
        --expected-pubkey-path /path/to/attestation-pubkey.pem

    # Con check de consumer lag (requiere acceso al Redis del piloto)
    CTR_REDIS_URL=redis://localhost:6379/0 \\
        python scripts/verify-attestation-deployment.py \\
        --service-url https://attestation.utn.edu.ar

Exit codes
----------
- 0: todos los chequeos OK.
- 1: al menos un chequeo critico fallo.
- 2: chequeo de pubkey mismatch (CRITICO — alguien rotó la clave sin avisar).
- 3: verificacion bit-exacta fallo (CRITICO — el journal del dia esta corrupto).

Cuando correrlo
---------------
- Semanal durante el piloto (script de cron del doctorando).
- Despues de cada cierre de batch del piloto (~30 episodios cerrados).
- Antes de la defensa doctoral para confirmar el estado del piloto.
- En cualquier momento que `audi2.md §3.2` o `plan-accion.md A3` se discutan.

ADR de respaldo: ADR-021 (external integrity attestation), RN-128 (SLO 24h),
PlanMejora.md P0-3, docs/pilot/attestation-deploy-checklist.md (deploy manual).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from base64 import b64decode
from dataclasses import dataclass
from pathlib import Path

import httpx

try:
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PublicKey,
    )
except ImportError:
    print(
        "ERROR: necesita `cryptography` instalado. Correr: pip install cryptography",
        file=sys.stderr,
    )
    sys.exit(1)


@dataclass(frozen=True)
class CheckResult:
    name: str
    ok: bool
    detail: str


async def check_http_health(client: httpx.AsyncClient, base_url: str) -> CheckResult:
    """GET /health/ready, GET /."""
    try:
        r = await client.get(f"{base_url}/health/ready", timeout=10.0)
        if r.status_code != 200:
            return CheckResult("HTTP health", False, f"/health/ready HTTP {r.status_code}")
        ready = r.json()
        if not ready.get("ready", False):
            return CheckResult("HTTP health", False, f"/health/ready: {ready}")
        return CheckResult("HTTP health", True, f"OK ({ready})")
    except httpx.HTTPError as e:
        return CheckResult("HTTP health", False, f"HTTP error: {e}")


async def check_pubkey(
    client: httpx.AsyncClient,
    base_url: str,
    expected_pubkey_path: str | None,
) -> tuple[CheckResult, bytes | None]:
    """GET /api/v1/attestations/pubkey y compara con la PEM esperada."""
    try:
        r = await client.get(f"{base_url}/api/v1/attestations/pubkey", timeout=10.0)
        if r.status_code != 200:
            return CheckResult("Pubkey", False, f"HTTP {r.status_code}"), None
        served_pem = r.content
        signer_id = r.headers.get("X-Signer-Pubkey-Id", "?")
        if expected_pubkey_path:
            expected_path = Path(expected_pubkey_path)
            if not expected_path.exists():
                return (
                    CheckResult("Pubkey", False, f"expected pubkey path no existe: {expected_path}"),
                    served_pem,
                )
            expected_pem = expected_path.read_bytes().strip()
            if served_pem.strip() != expected_pem:
                return (
                    CheckResult(
                        "Pubkey",
                        False,
                        f"MISMATCH! El VPS sirve una pubkey distinta a la esperada. "
                        f"signer_id={signer_id}. Esto es CRITICO: alguien rotó la clave "
                        "sin redistribuir. Verificar con DI UTN.",
                    ),
                    served_pem,
                )
            return (
                CheckResult("Pubkey", True, f"OK match con {expected_path} (signer={signer_id})"),
                served_pem,
            )
        return (
            CheckResult(
                "Pubkey", True, f"servida OK (sin verificacion vs expected, signer={signer_id})"
            ),
            served_pem,
        )
    except httpx.HTTPError as e:
        return CheckResult("Pubkey", False, f"HTTP error: {e}"), None


async def check_consumer_lag(redis_url: str) -> CheckResult:
    """XLEN del stream `attestation.requests`.

    Esperado: 0 (consumer al dia) o crecimiento lento. Si XLEN crece sin drenar,
    el consumer del VPS no esta procesando (D9 SLO 24h violada).
    """
    try:
        import redis.asyncio as aioredis  # type: ignore[import-not-found]
    except ImportError:
        return CheckResult(
            "Consumer lag",
            False,
            "redis package no instalado. pip install redis para este chequeo.",
        )
    try:
        client = aioredis.from_url(redis_url, decode_responses=True)
        try:
            xlen = await client.xlen("attestation.requests")
            # Si el stream no existe, xlen devuelve 0 — no es error
            msg = f"XLEN attestation.requests = {xlen}"
            # Threshold: >50 sin drenar = warning, >200 = critico
            if xlen > 200:
                return CheckResult(
                    "Consumer lag",
                    False,
                    f"{msg} (CRITICO: consumer no esta drenando — verificar VPS)",
                )
            if xlen > 50:
                return CheckResult(
                    "Consumer lag",
                    True,
                    f"{msg} (WARNING: lag creciente, monitorear)",
                )
            return CheckResult("Consumer lag", True, msg)
        finally:
            await client.aclose()
    except Exception as e:
        return CheckResult("Consumer lag", False, f"Redis error: {e}")


def _build_canonical_buffer(att: dict) -> bytes:
    """Reconstruye el buffer canonico bit-exact de una attestation.

    Pattern: README del servicio dice "Buffer canonico bit-exact sobre
    (episode_id, tenant_id, final_chain_hash, total_events, ts_episode_closed,
    schema_version). El campo ts_episode_closed debe terminar en sufijo Z."
    """
    canonical = {
        "episode_id": att["episode_id"],
        "tenant_id": att["tenant_id"],
        "final_chain_hash": att["final_chain_hash"],
        "total_events": att["total_events"],
        "ts_episode_closed": att["ts_episode_closed"],
        "schema_version": att.get("schema_version", "1.0.0"),
    }
    # JSON canonico: sort_keys, separators sin whitespace, ensure_ascii=True
    return json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode(
        "utf-8"
    )


async def check_day_journal(
    client: httpx.AsyncClient,
    base_url: str,
    day: str,
    served_pubkey_pem: bytes,
) -> CheckResult:
    """Descarga el JSONL del dia y verifica firma de cada attestation."""
    try:
        r = await client.get(f"{base_url}/api/v1/attestations/{day}", timeout=60.0)
        if r.status_code == 404:
            return CheckResult("Day journal", True, f"sin attestations el {day} (404 OK)")
        if r.status_code != 200:
            return CheckResult("Day journal", False, f"HTTP {r.status_code}")
        lines = [line for line in r.text.splitlines() if line.strip()]
        if not lines:
            return CheckResult("Day journal", True, f"journal del {day} vacio")

        pubkey = serialization.load_pem_public_key(served_pubkey_pem)
        if not isinstance(pubkey, Ed25519PublicKey):
            return CheckResult(
                "Day journal", False, "pubkey servida no es Ed25519 (no se puede verificar)"
            )

        n_total = len(lines)
        n_verified = 0
        n_failed = 0
        errors: list[str] = []
        for idx, line in enumerate(lines):
            try:
                att = json.loads(line)
                buffer = _build_canonical_buffer(att)
                signature = b64decode(att["signature_b64"])
                pubkey.verify(signature, buffer)
                n_verified += 1
            except InvalidSignature:
                n_failed += 1
                errors.append(f"  linea {idx + 1}: firma invalida (ep={att.get('episode_id')})")
            except (KeyError, ValueError) as e:
                n_failed += 1
                errors.append(f"  linea {idx + 1}: formato invalido ({e})")
        if n_failed > 0:
            detail = (
                f"{n_verified}/{n_total} OK, {n_failed} fallos:\n" + "\n".join(errors[:5])
            )
            if len(errors) > 5:
                detail += f"\n  ... y {len(errors) - 5} mas."
            return CheckResult("Day journal", False, detail)
        return CheckResult(
            "Day journal", True, f"verificadas {n_verified}/{n_total} attestations del {day}"
        )
    except httpx.HTTPError as e:
        return CheckResult("Day journal", False, f"HTTP error: {e}")


async def main(
    service_url: str,
    expected_pubkey_path: str | None,
    redis_url: str | None,
    day: str | None,
) -> int:
    print(f"=== Verify attestation deployment ===")
    print(f"Service URL: {service_url}")
    print(f"Expected pubkey: {expected_pubkey_path or '(no verificacion vs PEM local)'}")
    print(f"Redis URL: {redis_url or '(skip consumer lag)'}")
    print(f"Day to verify: {day or '(skip)'}")
    print()

    results: list[CheckResult] = []
    async with httpx.AsyncClient() as client:
        # 1. HTTP health
        results.append(await check_http_health(client, service_url))

        # 2. Pubkey
        pubkey_result, served_pem = await check_pubkey(
            client, service_url, expected_pubkey_path
        )
        results.append(pubkey_result)

        # 3. Consumer lag (opcional)
        if redis_url:
            results.append(await check_consumer_lag(redis_url))

        # 4. Day journal (opcional)
        if day and served_pem:
            results.append(await check_day_journal(client, service_url, day, served_pem))

    # Reporte
    print("\n=== Resultados ===")
    for r in results:
        marker = "✓" if r.ok else "✗"
        print(f"  {marker} {r.name}: {r.detail}")

    n_failed = sum(1 for r in results if not r.ok)
    pubkey_failed = next((r for r in results if r.name == "Pubkey" and not r.ok), None)
    journal_failed = next((r for r in results if r.name == "Day journal" and not r.ok), None)

    print()
    if n_failed == 0:
        print(f"OK: todos los chequeos pasaron ({len(results)}/{len(results)}).")
        return 0
    print(f"FAIL: {n_failed}/{len(results)} chequeos fallaron.")
    # Pubkey mismatch o journal corrupto son CRITICOS — exit code distintivo
    if pubkey_failed and "MISMATCH" in pubkey_failed.detail:
        return 2
    if journal_failed:
        return 3
    return 1


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Verificar deploy del integrity-attestation-service en VPS UTN (A3)."
    )
    p.add_argument(
        "--service-url",
        default=os.environ.get(
            "ATTESTATION_SERVICE_URL", "http://127.0.0.1:8012"
        ),
        help="URL del servicio attestation (default 127.0.0.1:8012).",
    )
    p.add_argument(
        "--expected-pubkey-path",
        default=os.environ.get("ATTESTATION_EXPECTED_PUBKEY_PATH"),
        help="Path a la PEM publica que el doctorando recibio del DI UTN (Paso 2 del checklist).",
    )
    p.add_argument(
        "--redis-url",
        default=os.environ.get("CTR_REDIS_URL"),
        help="URL del Redis del CTR para chequear consumer lag (opcional).",
    )
    p.add_argument(
        "--day",
        default=None,
        help="Dia YYYY-MM-DD para verificacion bit-exacta del journal (opcional).",
    )
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    exit_code = asyncio.run(
        main(
            service_url=args.service_url,
            expected_pubkey_path=args.expected_pubkey_path,
            redis_url=args.redis_url,
            day=args.day,
        )
    )
    sys.exit(exit_code)
