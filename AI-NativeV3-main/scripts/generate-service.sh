#!/usr/bin/env bash
# Genera un nuevo servicio Python a partir del template.
# Uso: ./scripts/generate-service.sh <nombre-del-servicio>
#
# Lo agrega al uv workspace del pyproject.toml root.

set -euo pipefail

if [ -z "${1:-}" ]; then
    echo "Uso: $0 <nombre-servicio>"
    echo "Ejemplo: $0 notification-service"
    exit 1
fi

NAME="$1"
MODULE="${NAME//-/_}"
PORT=8012  # próximo puerto disponible

if [ -d "apps/$NAME" ]; then
    echo "✗ apps/$NAME ya existe"
    exit 1
fi

python3 - <<PY
import sys
sys.path.insert(0, "scripts")
from generate_python_services import SERVICES, APPS
from pathlib import Path

new_svc = {
    "name": "$NAME",
    "module": "$MODULE",
    "description": "Servicio $NAME",
    "port": $PORT,
    "extra_deps": [],
    "features": [],
}

# Usar las funciones del generator
from generate_python_services import (
    pyproject_content, dockerfile_content, main_py_content,
    config_py_content, observability_py_content, health_py_content,
    routes_init_content, module_init_content, test_health_content,
    service_readme_content,
)

app_dir = APPS / new_svc["name"]
src_dir = app_dir / "src" / new_svc["module"]
routes_dir = src_dir / "routes"
tests_dir = app_dir / "tests"

for d in (src_dir, routes_dir, tests_dir):
    d.mkdir(parents=True, exist_ok=True)

(app_dir / "pyproject.toml").write_text(pyproject_content(new_svc))
(app_dir / "Dockerfile").write_text(dockerfile_content(new_svc))
(app_dir / "README.md").write_text(service_readme_content(new_svc))
(src_dir / "__init__.py").write_text(module_init_content(new_svc))
(src_dir / "main.py").write_text(main_py_content(new_svc))
(src_dir / "config.py").write_text(config_py_content(new_svc))
(src_dir / "observability.py").write_text(observability_py_content(new_svc))
(routes_dir / "__init__.py").write_text(routes_init_content())
(routes_dir / "health.py").write_text(health_py_content(new_svc))
(tests_dir / "__init__.py").write_text("")
(tests_dir / "test_health.py").write_text(test_health_content(new_svc))

print(f"✓ apps/{new_svc['name']} generado")
PY

# Agregar al workspace del pyproject root
python3 - <<PY
from pathlib import Path
import re

root = Path("pyproject.toml")
text = root.read_text()

# Insertar antes del cierre del workspace list
needle = '    "packages/test-utils",\n]'
new_line = '    "apps/$NAME",\n    "packages/test-utils",\n]'
if needle in text:
    text = text.replace(needle, new_line)
    root.write_text(text)
    print("✓ Agregado al uv workspace")
else:
    print("⚠ Agregar manualmente 'apps/$NAME' al workspace en pyproject.toml")
PY

echo ""
echo "Próximos pasos:"
echo "  1. cd apps/$NAME"
echo "  2. uv sync"
echo "  3. uv run uvicorn ${MODULE}.main:app --reload --port $PORT"
