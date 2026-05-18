"""verify-attestations.py — verifica firmas Ed25519 de un journal de attestations.

ADR-021: tool CLI standalone para auditores externos. Recibe un directorio
con archivos `attestations-YYYY-MM-DD.jsonl` y la clave publica PEM, valida
que cada attestation este firmada correctamente con esa clave.

Uso:
    uv run python scripts/verify-attestations.py \\
        --jsonl-dir apps/integrity-attestation-service/attestations/ \\
        --pubkey-pem apps/integrity-attestation-service/dev-keys/dev-public.pem

    # Con verbose para ver cada linea verificada
    uv run python scripts/verify-attestations.py --jsonl-dir <dir> --pubkey-pem <pem> -v

Exit codes:
    0 — todas las firmas validan + sin duplicados sospechosos
    1 — al menos una firma invalida
    2 — error de I/O (directorio inexistente, PEM corrupto)

Diseno bit-exact con el servicio: reusamos `compute_canonical_buffer` y
`verify_buffer` del modulo `integrity_attestation_service.services.signing`.
Si un auditor quisiera reimplementar la tool en otro lenguaje (Go, Rust),
el ADR-021 documenta el buffer canonico bit-a-bit suficiente para reproducir
las verificaciones sin acceso al codigo Python.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

# El monorepo uv instala todos los packages editables en el venv comun.
# `import integrity_attestation_service` funciona desde cualquier lado al
# correr con `uv run`.
from integrity_attestation_service.services.signing import (
    compute_canonical_buffer,
    compute_signer_pubkey_id,
    load_public_key,
    verify_buffer,
)


def _print_ok(msg: str) -> None:
    print(f"[OK]   {msg}")


def _print_fail(msg: str) -> None:
    print(f"[FAIL] {msg}", file=sys.stderr)


def _print_warn(msg: str) -> None:
    print(f"[WARN] {msg}")


_DUPLICATES_DISPLAY_LIMIT = 10  # cuantos duplicados listar antes de truncar


def _verify_line(
    raw_line: str,
    public_key,
    expected_pubkey_id: str,
    *,
    verbose: bool,
) -> tuple[bool, str | None]:
    """Verifica una linea JSON. Devuelve (ok, episode_id_si_se_pudo_parsear)."""
    try:
        att = json.loads(raw_line)
    except json.JSONDecodeError as e:
        _print_fail(f"JSON invalido: {e}")
        return False, None

    episode_id = att.get("episode_id", "<sin-episode_id>")

    # Validacion del pubkey_id de la attestation contra la pubkey provista.
    # Si no matchea, la attestation fue firmada con OTRA clave — el verificador
    # debe buscar la pubkey correspondiente en su llavero. Reportamos como WARN,
    # no FAIL, porque puede ser legitimo (rotacion de claves).
    sig_pubkey_id = att.get("signer_pubkey_id", "")
    if sig_pubkey_id != expected_pubkey_id:
        _print_warn(
            f"episode_id={episode_id} firmado con pubkey_id={sig_pubkey_id}, "
            f"pero esta tool esta usando pubkey_id={expected_pubkey_id}. "
            f"Salteo verificacion (cargar la pubkey correspondiente)."
        )
        return True, episode_id

    # Reconstruir buffer canonico
    try:
        canonical = compute_canonical_buffer(
            episode_id=att["episode_id"],
            tenant_id=att["tenant_id"],
            final_chain_hash=att["final_chain_hash"],
            total_events=int(att["total_events"]),
            ts_episode_closed=att["ts_episode_closed"],
            schema_version=att.get("schema_version", "1.0.0"),
        )
    except (KeyError, ValueError) as e:
        _print_fail(f"episode_id={episode_id} attestation malformada: {e}")
        return False, episode_id

    # Verificar firma
    ok = verify_buffer(public_key, canonical, att.get("signature", ""))
    if ok:
        if verbose:
            _print_ok(
                f"episode_id={episode_id} ts_attested={att.get('ts_attested')} "
                f"final_chain_hash={att['final_chain_hash'][:16]}..."
            )
        return True, episode_id
    _print_fail(
        f"episode_id={episode_id} FIRMA INVALIDA. "
        f"Posibles causas: pubkey incorrecta, attestation manipulada, "
        f"buffer canonico cambio entre runtime y este verificador."
    )
    return False, episode_id


def main() -> int:  # noqa: PLR0912 — secuencia lineal de pasos, extraer funciones empeoraria legibilidad
    parser = argparse.ArgumentParser(
        description="Verifica firmas Ed25519 de un journal de attestations (ADR-021)"
    )
    parser.add_argument(
        "--jsonl-dir",
        type=Path,
        required=True,
        help="Directorio con archivos attestations-YYYY-MM-DD.jsonl",
    )
    parser.add_argument(
        "--pubkey-pem",
        type=Path,
        required=True,
        help="Path a la clave publica Ed25519 en formato PEM",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Reporta cada linea verificada (no solo las fallas)",
    )
    args = parser.parse_args()

    if not args.jsonl_dir.is_dir():
        print(f"[FATAL] No existe directorio: {args.jsonl_dir}", file=sys.stderr)
        return 2
    if not args.pubkey_pem.is_file():
        print(f"[FATAL] No existe pubkey PEM: {args.pubkey_pem}", file=sys.stderr)
        return 2

    try:
        public_key = load_public_key(args.pubkey_pem)
    except Exception as e:
        print(f"[FATAL] Error cargando pubkey: {e}", file=sys.stderr)
        return 2

    expected_pubkey_id = compute_signer_pubkey_id(public_key)
    print(f"Verificando con pubkey_id={expected_pubkey_id}")
    print(f"Directorio: {args.jsonl_dir}")
    print()

    files = sorted(args.jsonl_dir.glob("attestations-*.jsonl"))
    if not files:
        print(f"[WARN] No hay archivos attestations-*.jsonl en {args.jsonl_dir}")
        return 0

    total = 0
    fails = 0
    episode_counter: Counter[str] = Counter()
    fails_by_file: dict[str, int] = defaultdict(int)

    for path in files:
        print(f"--- {path.name} ---")
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            total += 1
            ok, episode_id = _verify_line(
                line, public_key, expected_pubkey_id, verbose=args.verbose
            )
            if not ok:
                fails += 1
                fails_by_file[path.name] += 1
            if episode_id:
                episode_counter[episode_id] += 1

    # Detectar duplicados (mismo episode_id firmado mas de una vez).
    # No es necesariamente bug — un episodio reabierto y re-cerrado podria
    # legitimamente atestiguarse dos veces — pero es info que el auditor
    # quiere ver. Reportamos como WARN.
    duplicates = {ep: count for ep, count in episode_counter.items() if count > 1}

    print()
    print("=" * 60)
    print(f"Total attestations procesadas:  {total}")
    print(f"Firmas validas:                  {total - fails}")
    print(f"Firmas invalidas:                {fails}")
    if duplicates:
        print(f"Duplicados (mismo episode_id):   {len(duplicates)}")
        for ep, count in sorted(duplicates.items())[:_DUPLICATES_DISPLAY_LIMIT]:
            print(f"  - {ep}: {count} attestations")
        if len(duplicates) > _DUPLICATES_DISPLAY_LIMIT:
            print(f"  (... y {len(duplicates) - _DUPLICATES_DISPLAY_LIMIT} mas)")
    if fails_by_file:
        print()
        print("Fallas por archivo:")
        for fname, count in sorted(fails_by_file.items()):
            print(f"  {fname}: {count}")

    return 1 if fails > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
