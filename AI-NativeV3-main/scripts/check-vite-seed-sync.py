"""CI gate: verifica que los UUIDs hardcoded en `apps/web-*/vite.config.ts`
(headers `x-user-id` para dev mode sin Keycloak) existan realmente en el seed
`scripts/seed-3-comisiones.py`.

Motivacion (A24): si alguien corre un seed que no crea esos UUIDs, el frontend
dev queda mudo silenciosamente (TareaSelector vacio, comisiones vacias). Este
gate detecta el drift en CI antes de que llegue al developer.

Politica:
- Si un vite.config.ts NO contiene un UUID hardcoded del patron canonico de 36
  chars, se reporta y se skipea (no es failure — puede haber refactor a env vars).
- Si un UUID aparece en vite.config pero NO en el seed → exit 1.
- Si todos los UUIDs encontrados estan en el seed → exit 0 con OK.

NO modifica archivos. Solo verifica.

Uso:
    uv run python scripts/check-vite-seed-sync.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# Encoding-safe stdout for Windows cp1252 consoles (gotcha del repo).
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

REPO_ROOT = Path(__file__).resolve().parent.parent

VITE_CONFIGS = [
    REPO_ROOT / "apps" / "web-admin" / "vite.config.ts",
    REPO_ROOT / "apps" / "web-teacher" / "vite.config.ts",
    REPO_ROOT / "apps" / "web-student" / "vite.config.ts",
]

SEED_FILE = REPO_ROOT / "scripts" / "seed-3-comisiones.py"

# UUID canonico (8-4-4-4-12 hex) — no apto para validar version pero suficiente
# para detectar el patron hardcoded en vite.config.
UUID_RE = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")

# Buscamos el UUID en lineas que contengan x-user-id (header inyectado al proxy
# del api-gateway). Asi evitamos falsos positivos sobre x-tenant-id u otros.
USER_ID_LINE_RE = re.compile(r"x-user-id", re.IGNORECASE)


def extract_vite_user_id(vite_path: Path) -> tuple[str, int] | None:
    """Lee vite.config.ts y devuelve (uuid, line_no) del x-user-id hardcoded.

    Returns None si el archivo no contiene un UUID hardcoded en el contexto del
    header x-user-id (caso valido — el frontend puede haberse migrado a env var
    o a JWT real).
    """
    if not vite_path.exists():
        return None
    text = vite_path.read_text(encoding="utf-8")
    for idx, line in enumerate(text.splitlines(), start=1):
        if USER_ID_LINE_RE.search(line):
            m = UUID_RE.search(line)
            if m:
                return (m.group(0).lower(), idx)
    return None


def extract_seed_uuids(seed_path: Path) -> set[str]:
    """Devuelve TODOS los UUIDs (lowercase) que aparecen en el seed."""
    if not seed_path.exists():
        return set()
    text = seed_path.read_text(encoding="utf-8")
    return {m.group(0).lower() for m in UUID_RE.finditer(text)}


def main() -> int:
    seed_uuids = extract_seed_uuids(SEED_FILE)
    if not seed_uuids:
        print(f"[FAIL] no se encontro {SEED_FILE} o no contiene UUIDs.")
        return 1

    drift: list[str] = []
    skipped: list[str] = []
    checked: list[str] = []

    for vite_path in VITE_CONFIGS:
        rel = vite_path.relative_to(REPO_ROOT)
        result = extract_vite_user_id(vite_path)
        if result is None:
            skipped.append(f"  {rel}: sin UUID hardcoded en x-user-id (skip)")
            continue
        uuid, line_no = result
        if uuid in seed_uuids:
            checked.append(f"  {rel}:{line_no} -> {uuid} OK")
        else:
            drift.append(
                f"DRIFT: {rel}:{line_no} usa UUID {uuid} que no aparece en "
                f"{SEED_FILE.relative_to(REPO_ROOT)}. Sincronizar manualmente."
            )

    print("[check-vite-seed-sync] verificando UUIDs hardcoded vs seed-3-comisiones.py")
    if checked:
        print("Sincronizados:")
        for line in checked:
            print(line)
    if skipped:
        print("Saltados (sin UUID hardcoded):")
        for line in skipped:
            print(line)
    if drift:
        print("")
        for line in drift:
            print(line)
        print("")
        print("[FAIL] drift detectado entre vite.config.ts y seed-3-comisiones.py.")
        return 1

    print("[OK] vite.config.ts <-> seed-3-comisiones.py sincronizados.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
