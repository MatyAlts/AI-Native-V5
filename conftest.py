"""Conftest global del monorepo Python.

Agrega los paths de src/ de cada servicio y paquete al sys.path para que
pytest resuelva imports correctamente en los tests.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).parent

# Agregar src/ de cada paquete y servicio
for base in (ROOT / "packages", ROOT / "apps"):
    if not base.exists():
        continue
    for subdir in base.iterdir():
        src = subdir / "src"
        if src.is_dir():
            sys.path.insert(0, str(src))
