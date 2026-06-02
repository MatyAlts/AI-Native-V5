"""Config de pytest para analytics-service.

Desactiva el enforcement de membresía por comisión (`enforce_comision_access`)
en los tests unit: estos prueban la mecánica de los endpoints en modo
stub/dev y NO simulan al api-gateway (no mandan X-User-Id) ni siembran
filas `usuarios_comision`. El guard se cubre con su propio test dedicado
(`test_comision_access_guard.py`). En prod el flag queda en True (default).
"""

from __future__ import annotations

import os

os.environ["ENFORCE_COMISION_ACCESS"] = "false"

# Rebind defensivo: si analytics_service.config ya fue importado (cacheado
# con el default True), forzamos una instancia fresca con el flag en False.
from analytics_service import config as _config

_config.get_settings.cache_clear()
_config.settings = _config.get_settings()
