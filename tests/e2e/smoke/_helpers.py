"""Helpers no-fixture importables desde los modulos de test.

Mantenemos las fixtures en `conftest.py` (auto-discoverable por pytest) y
los helpers no-fixture aca para que los tests puedan importarlos via path
absoluto. Cualquier constante o funcion que no necesite ser fixture vive
aca.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

import psycopg2

# Mismas constantes que conftest.py — duplicadas para no acoplar import path.
TENANT_DEMO = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
COMISION_A_MANANA = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
DOCENTE_DEMO = "11111111-1111-1111-1111-111111111111"
SUPERADMIN_DEMO = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
STUDENT_A1 = "b1b1b1b1-0001-0001-0001-000000000001"

# identity-service (:8001) deprecated por ADR-041 — auth movida a api-gateway.
# enrollment-service (:8003) deprecated por ADR-030 — bulk-import en academic-service.
SERVICES_HEALTH = [
    (8000, "api-gateway"),
    (8002, "academic-service"),
    (8004, "evaluation-service"),
    (8005, "analytics-service"),
    (8006, "tutor-service"),
    (8007, "ctr-service"),
    (8008, "classifier-service"),
    (8009, "content-service"),
    (8010, "governance-service"),
    (8011, "ai-gateway"),
    (8012, "integrity-attestation-service"),
]

PG_CONN_STR = os.environ.get("SMOKE_PG_DSN", "postgresql://postgres:postgres@127.0.0.1:5432")

# Donde escriben los servicios DE VERDAD: `scripts/dev-start-all.sh` hace
# `mkdir -p .dev-logs` y manda cada servicio a `.dev-logs/<name>.log`,
# relativo al root del repo.
#
# Hasta el 2026-08-28 esto apuntaba a `/tmp/piloto-logs`, un directorio que
# NADIE escribe: el workflow de smoke lo creaba con `mkdir -p` y ahi terminaba
# su historia. Consecuencia: cada `tail_log()` de un test que fallaba imprimia
# `(no log file at /tmp/piloto-logs/<svc>.log)` en vez del log, o sea que todo
# el diagnostico in-test estaba muerto justo cuando hacia falta.
#
# `SMOKE_LOGS_DIR` permite apuntarlo a otro lado sin tocar codigo.
_REPO_ROOT = Path(__file__).resolve().parents[3]
PILOTO_LOGS_DIR = Path(os.environ.get("SMOKE_LOGS_DIR") or (_REPO_ROOT / ".dev-logs"))


def fetch_pg(dbname: str, sql: str, params: tuple[Any, ...] = ()) -> list[tuple[Any, ...]]:
    """Read-only helper. NO modifica state."""
    conn = psycopg2.connect(f"{PG_CONN_STR}/{dbname}")
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()
    finally:
        conn.close()


def tail_log(service: str, lines: int = 20) -> str:
    """Devuelve las últimas N líneas del log del servicio."""
    log_path = PILOTO_LOGS_DIR / f"{service}.log"
    if not log_path.exists():
        return f"(no log file at {log_path})"
    try:
        content = log_path.read_text(errors="replace")
    except Exception as exc:
        return f"(error reading log: {exc})"
    return "\n".join(content.splitlines()[-lines:])


# Exportar al sys.path para que los tests sean simples
_THIS_DIR = Path(__file__).parent
if str(_THIS_DIR) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR))
