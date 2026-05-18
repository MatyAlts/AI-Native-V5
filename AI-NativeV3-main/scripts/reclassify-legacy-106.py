"""Script de re-clasificacion batch de classifications con hash legacy (A1 del plan-accion).

Cierra el bloqueador P0-1 del PlanMejora.md: re-clasifica las ~106 classifications
historicas que fueron selladas con un classifier_config_hash anterior al
LABELER_VERSION=1.2.0 vigente, persistiendolas como filas nuevas con el hash
actual (append-only ADR-010 + idempotencia A12).

Estrategia
----------
1. Conecta a CLASSIFIER_DB y calcula el `classifier_config_hash` vigente.
2. Query: classifications con `is_current=true AND classifier_config_hash != :vigente`.
3. Para cada episode_id: POST /api/v1/classify_episode/{episode_id} al
   classifier-service con headers de service-account `classifier_worker`.
4. El endpoint es **idempotente**: si la nueva clasificacion ya existe con
   el hash vigente, devuelve la fila (no duplica). Si existe una vieja con
   hash distinto, marca esa como is_current=false e inserta la nueva.

Precondiciones
--------------
- classifier-service levantado (default: http://127.0.0.1:8008).
- ctr-service levantado y accesible desde classifier-service (para fetch episodes).
- CLASSIFIER_DB_URL apuntando a Postgres con classifications historicas.
- Service account con rol `classifier_worker` (definido en CLASSIFY_ROLES).

Ejecucion
---------
    # Dry-run: NO persiste, solo reporta cuantos episodios serian re-procesados
    python scripts/reclassify-legacy-106.py --dry-run

    # Real: re-clasifica todo
    python scripts/reclassify-legacy-106.py

    # Custom service URL / db url
    CLASSIFIER_SERVICE_URL=http://classifier:8008 \
    CLASSIFIER_DB_URL=postgresql+asyncpg://user:pass@host:5432/classifier_db \
    python scripts/reclassify-legacy-106.py

Idempotencia
------------
Re-correr el script es SEGURO. El endpoint /api/v1/classify_episode/{id}
maneja idempotencia bit-a-bit por (episode_id, classifier_config_hash):
- Si ya existe una fila current con MISMO hash → no-op, devuelve la existente.
- Si existe una con OTRO hash → marca la vieja is_current=false e inserta la nueva.

El script tampoco re-procesa episodios cuyo current ya tiene el hash vigente
(filtra en la query SQL inicial).

Anti-regresion
--------------
- NO toca el CTR (append-only). Solo agrega filas en `classifications`.
- Las filas viejas siguen accesibles via `is_current=false` para auditoria.
- Verificacion post-corrida: contar `is_current=true` antes y despues.
  Esperado: el conteo se mantiene (cada episodio sigue teniendo exactamente
  1 fila current — la nueva en lugar de la vieja).

ADR de respaldo: ADR-010 (append-only), ADR-020 (LABELER_VERSION),
PlanMejora.md P0-1, plan-accion.md A1.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

# Permitir imports del classifier-service para calcular el hash vigente
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "apps" / "classifier-service" / "src"))

from classifier_service.services import (  # noqa: E402
    DEFAULT_REFERENCE_PROFILE,
    compute_classifier_config_hash,
)

# Service-account headers (rol classifier_worker, definido en CLASSIFY_ROLES)
SERVICE_ACCOUNT_USER_ID = "00000000-0000-0000-0000-000000000099"  # placeholder
SERVICE_ACCOUNT_EMAIL = "classifier-worker@service.internal"
SERVICE_ACCOUNT_ROLES = "classifier_worker"


@dataclass(frozen=True)
class LegacyClassification:
    """Una clasificacion con hash legacy que requiere re-procesamiento."""

    episode_id: UUID
    tenant_id: UUID
    comision_id: UUID
    legacy_hash: str


async def list_legacy(
    db_url: str, vigente_hash: str
) -> list[LegacyClassification]:
    """Lista classifications current con hash distinto al vigente."""
    engine = create_async_engine(db_url, echo=False)
    try:
        async with engine.connect() as conn:
            result = await conn.execute(
                text(
                    """
                    SELECT episode_id, tenant_id, comision_id, classifier_config_hash
                    FROM classifications
                    WHERE is_current = true
                      AND classifier_config_hash != :vigente
                    ORDER BY classified_at ASC
                    """
                ),
                {"vigente": vigente_hash},
            )
            return [
                LegacyClassification(
                    episode_id=row.episode_id,
                    tenant_id=row.tenant_id,
                    comision_id=row.comision_id,
                    legacy_hash=row.classifier_config_hash,
                )
                for row in result
            ]
    finally:
        await engine.dispose()


async def reclassify_one(
    client: httpx.AsyncClient,
    service_url: str,
    item: LegacyClassification,
) -> tuple[bool, str]:
    """Re-clasifica un episodio via HTTP. Devuelve (success, message_or_error)."""
    headers = {
        "X-User-Id": SERVICE_ACCOUNT_USER_ID,
        "X-Tenant-Id": str(item.tenant_id),
        "X-User-Email": SERVICE_ACCOUNT_EMAIL,
        "X-User-Roles": SERVICE_ACCOUNT_ROLES,
        "Content-Type": "application/json",
    }
    url = f"{service_url}/api/v1/classify_episode/{item.episode_id}"
    try:
        r = await client.post(url, headers=headers, timeout=60.0)
        if r.status_code == 200:
            data = r.json()
            new_hash = data.get("classifier_config_hash", "?")
            return True, f"OK (new_hash={new_hash[:12]}...)"
        return False, f"HTTP {r.status_code}: {r.text[:200]}"
    except httpx.HTTPError as e:
        return False, f"HTTP error: {e}"


async def main(dry_run: bool, service_url: str, db_url: str) -> int:
    # 1. Calcular el hash vigente local (debe coincidir con el que computa
    # el classifier-service endpoint — ambos usan la misma funcion pura).
    vigente_hash = compute_classifier_config_hash(DEFAULT_REFERENCE_PROFILE, "v1.0.0")
    print(f"Hash vigente: {vigente_hash}")
    print(f"DB: {_redact(db_url)}")
    print(f"Service URL: {service_url}")
    print(f"Mode: {'DRY-RUN (no persist)' if dry_run else 'REAL (persist via HTTP)'}")
    print()

    # 2. Listar legacy
    legacy = await list_legacy(db_url, vigente_hash)
    print(f"Legacy classifications encontradas: {len(legacy)}")
    if not legacy:
        print("Nada que re-procesar. Salida limpia.")
        return 0

    # Resumen por hash legacy (cuantos episodios por cada hash distinto)
    counts: dict[str, int] = {}
    for item in legacy:
        counts[item.legacy_hash] = counts.get(item.legacy_hash, 0) + 1
    print("Distribucion por classifier_config_hash legacy:")
    for legacy_hash, n in sorted(counts.items(), key=lambda kv: -kv[1]):
        print(f"  {legacy_hash[:16]}... → {n} episodios")
    print()

    if dry_run:
        print("DRY-RUN: no se ejecuta nada. Para re-procesar real, correr sin --dry-run.")
        return 0

    # 3. Re-procesar
    n_success = 0
    n_error = 0
    errors: list[tuple[UUID, str]] = []
    async with httpx.AsyncClient() as client:
        for idx, item in enumerate(legacy, start=1):
            success, msg = await reclassify_one(client, service_url, item)
            status_str = "✓" if success else "✗"
            print(f"  [{idx:3d}/{len(legacy)}] {status_str} {item.episode_id} → {msg}")
            if success:
                n_success += 1
            else:
                n_error += 1
                errors.append((item.episode_id, msg))

    print()
    print("=" * 60)
    print(f"Resultado: {n_success}/{len(legacy)} re-clasificadas OK, {n_error} errores")
    if errors:
        print()
        print("Errores detallados:")
        for episode_id, err in errors:
            print(f"  - {episode_id}: {err}")

    # Exit code != 0 si hay errores, para CI
    return 0 if n_error == 0 else 1


def _redact(url: str) -> str:
    """Oculta password del DB URL para logging seguro."""
    if "@" not in url:
        return url
    prefix, rest = url.split("@", 1)
    if "://" in prefix and ":" in prefix.split("://", 1)[1]:
        scheme, userpass = prefix.split("://", 1)
        user = userpass.split(":", 1)[0]
        return f"{scheme}://{user}:***@{rest}"
    return url


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Re-clasificar classifications historicas con LABELER_VERSION vigente (A1)."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="No ejecuta re-clasificacion; solo reporta cuantas estarian afectadas.",
    )
    parser.add_argument(
        "--service-url",
        default=os.environ.get("CLASSIFIER_SERVICE_URL", "http://127.0.0.1:8008"),
        help="URL del classifier-service (default 127.0.0.1:8008).",
    )
    parser.add_argument(
        "--db-url",
        default=os.environ.get(
            "CLASSIFIER_DB_URL",
            "postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/classifier_db",
        ),
        help="DB URL del classifier_db.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    exit_code = asyncio.run(
        main(dry_run=args.dry_run, service_url=args.service_url, db_url=args.db_url)
    )
    sys.exit(exit_code)
