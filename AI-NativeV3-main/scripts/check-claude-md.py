#!/usr/bin/env python3
"""Detecta drift numerico entre claims del CLAUDE.md y el codigo real.

Usar:
    uv run python scripts/check-claude-md.py
    uv run python scripts/check-claude-md.py --verbose
    uv run python scripts/check-claude-md.py --explain

Exit code:
    0 = todos los claims numericos del CLAUDE.md matchean el codigo
    1 = al menos un claim no matchea (drift detectado, lista cada uno)
    2 = no se pudo leer CLAUDE.md o pyproject.toml

Pensado como gate post-trim del CLAUDE.md y como CI guard liviano (sin DB,
sin red, sub-segundo). Para extender: agregar un dict a CHECKS con `pattern`,
`count_fn`, `where`. El pattern matchea contra CLAUDE.md y captura el numero
en el grupo 1; count_fn devuelve el numero real desde el codigo.

Output en ASCII (cp1252-safe, gotcha conocido de Windows stdout).
"""

from __future__ import annotations

import argparse
import re
import sys
import tomllib
from collections.abc import Callable
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CLAUDE_MD = REPO_ROOT / "CLAUDE.md"
PYPROJECT = REPO_ROOT / "pyproject.toml"


def count_uv_workspace_services() -> int:
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    members = data.get("tool", {}).get("uv", {}).get("workspace", {}).get("members", [])
    return sum(1 for m in members if m.startswith("apps/"))


def count_casbin_policies() -> int:
    seed = REPO_ROOT / "apps/academic-service/src/academic_service/seeds/casbin_policies.py"
    text = seed.read_text(encoding="utf-8")
    return sum(1 for line in text.splitlines() if line.startswith("    ("))


def count_smoke_tests() -> int:
    smoke_dir = REPO_ROOT / "tests/e2e/smoke"
    if not smoke_dir.exists():
        return 0
    pattern = re.compile(r"^def test_", re.MULTILINE)
    return sum(
        len(pattern.findall(f.read_text(encoding="utf-8")))
        for f in smoke_dir.glob("test_*.py")
    )


def count_alembic_migrations() -> int:
    return len(list(REPO_ROOT.glob("apps/*/alembic/versions/*.py")))


def count_adrs() -> int:
    adr_dir = REPO_ROOT / "docs/adr"
    if not adr_dir.exists():
        return 0
    return sum(1 for f in adr_dir.glob("[0-9]*.md"))


Check = dict[str, object]

CHECKS: list[Check] = [
    {
        "label": "uv workspace services (apps/*)",
        "pattern": re.compile(r"\*\*(\d+) servicios Python activos\*\*"),
        "count_fn": count_uv_workspace_services,
        "where": "pyproject.toml [tool.uv.workspace].members con prefijo apps/",
    },
    {
        "label": "Casbin policies en seed",
        "pattern": re.compile(r"\*\*(\d+) policies\*\*"),
        "count_fn": count_casbin_policies,
        "where": "apps/academic-service/.../seeds/casbin_policies.py - lineas que arrancan con cuatro espacios + parentesis",
    },
    {
        "label": "Smoke tests E2E",
        "pattern": re.compile(r"con (\d+) tests \(verificado"),
        "count_fn": count_smoke_tests,
        "where": "tests/e2e/smoke/test_*.py - matches de '^def test_'",
    },
    {
        "label": "Migraciones Alembic",
        "pattern": re.compile(r"(\d+) migraciones Alembic", re.IGNORECASE),
        "count_fn": count_alembic_migrations,
        "where": "apps/*/alembic/versions/*.py",
    },
    {
        "label": "ADRs numerados",
        "pattern": re.compile(r"\b(\d+) ADRs\b"),
        "count_fn": count_adrs,
        "where": "docs/adr/[0-9]*.md",
    },
]


def run_checks(verbose: bool) -> int:
    if not CLAUDE_MD.exists():
        print(f"[FAIL] CLAUDE.md no encontrado en {CLAUDE_MD}")
        return 2
    if not PYPROJECT.exists():
        print(f"[FAIL] pyproject.toml no encontrado en {PYPROJECT}")
        return 2

    text = CLAUDE_MD.read_text(encoding="utf-8")
    failures: list[str] = []
    skipped = 0
    passed = 0

    for check in CHECKS:
        label = check["label"]
        pattern: re.Pattern[str] = check["pattern"]  # type: ignore[assignment]
        count_fn: Callable[[], int] = check["count_fn"]  # type: ignore[assignment]
        actual = count_fn()
        match = pattern.search(text)
        if match is None:
            skipped += 1
            if verbose:
                print(f"[SKIP] {label}: claim no encontrado en CLAUDE.md (real = {actual})")
            continue
        claimed = int(match.group(1))
        if claimed == actual:
            passed += 1
            if verbose:
                print(f"[OK]   {label}: {claimed}")
        else:
            failures.append(
                f"[FAIL] {label}: CLAUDE.md dice {claimed}, codigo tiene {actual}\n"
                f"       fuente: {check['where']}"
            )

    if failures:
        for f in failures:
            print(f)
        print()
        print(f"[FAIL] {len(failures)} drifts detectados ({passed} OK, {skipped} skip)")
        return 1

    print(f"[OK] {passed} claims verificados, {skipped} skip, sin drift")
    return 0


def explain() -> int:
    for c in CHECKS:
        print(f"  {c['label']}")
        print(f"    pattern: {c['pattern'].pattern}")  # type: ignore[union-attr]
        print(f"    fuente : {c['where']}")
        print()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Detecta drift numerico entre CLAUDE.md y el codigo"
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="muestra los OK tambien")
    parser.add_argument("--explain", action="store_true", help="muestra patrones y fuentes")
    args = parser.parse_args()

    if args.explain:
        return explain()
    return run_checks(args.verbose)


if __name__ == "__main__":
    sys.exit(main())
