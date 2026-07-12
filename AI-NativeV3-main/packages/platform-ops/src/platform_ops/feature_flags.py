"""Feature flags por tenant para rollout gradual.

Resuelve si una feature está activa para un tenant específico. Es la
palanca de F10: prender una feature primero en el tenant piloto, después en
más tenants, y por último en el `default` global (rollout progresivo por
tenant). La fuente de verdad es un YAML (misma infra que los prompts):

    # /etc/platform/feature_flags.yaml   (env var FEATURE_FLAGS_PATH)
    default:
      enable_code_execution: false
      enable_claude_opus: false
      max_episodes_per_day: 50

    tenants:
      aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa:  # UTN (pilot tenant)
        enable_code_execution: true
        enable_claude_opus: true
        max_episodes_per_day: 200
      bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb:
        enable_code_execution: true

Consulta:
    FeatureFlags.is_enabled(tenant_id, "enable_code_execution") → bool
    FeatureFlags.get_value(tenant_id, "max_episodes_per_day") → int

    # Default seguro sin YAML ni try/except (recomendado en el hot-path):
    FeatureFlags.is_enabled(tenant_id, "enable_x", default=False) → bool

Cómo se DEFINE / ACTIVA un flag
-------------------------------
1. Declararlo SIEMPRE en `default:` (valor seguro/apagado). Así nunca hay
   una feature "no declarada" silenciosa: o está en default, o el caller da
   `default=`, o se levanta `FeatureNotDeclaredError` explícito.
2. Activarlo por tenant: agregar la clave bajo `tenants: <uuid>:` con el
   valor deseado (rollout gradual: un tenant a la vez).
3. Override de ops por env var (kill-switch / force global, sin editar el
   YAML ni redeployar): `PLATFORM_FF_<FLAG_EN_MAYÚSCULAS>`. Ej.:
       PLATFORM_FF_ENABLE_CODE_EXECUTION=true
   Aplica a TODOS los tenants y tiene la precedencia más alta.

Resolución (mayor → menor precedencia):
    env var PLATFORM_FF_<FLAG>  →  override del tenant  →  default (YAML)
    →  parámetro `default=`  →  raise FeatureNotDeclaredError
"""

from __future__ import annotations

import hashlib
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import UUID

logger = logging.getLogger(__name__)

# Prefijo de env var para el override global de ops (kill-switch / force).
ENV_PREFIX = "PLATFORM_FF_"

# Sentinela: distingue "no se pasó default" de "default=None" legítimo.
_UNSET: Any = object()


class FeatureNotDeclaredError(Exception):
    """La feature consultada no está declarada ni en default ni en tenant."""


@dataclass
class FlagsSnapshot:
    """Snapshot inmutable cargado desde disco."""

    defaults: dict[str, Any] = field(default_factory=dict)
    per_tenant: dict[str, dict[str, Any]] = field(default_factory=dict)
    loaded_at: float = 0.0
    source_hash: str = ""


class FeatureFlags:
    """Flags con reload periódico desde archivo.

    Se cachean `reload_interval_seconds` antes de re-leer. La re-lectura
    es transparente: si el archivo no cambió (hash), no se rebuilt.
    """

    def __init__(
        self,
        config_path: str | Path,
        reload_interval_seconds: int = 60,
    ) -> None:
        self.config_path = Path(config_path)
        self.reload_interval_seconds = reload_interval_seconds
        self._snapshot: FlagsSnapshot = FlagsSnapshot()

    def _maybe_reload(self) -> None:
        now = time.time()
        if (
            now - self._snapshot.loaded_at
        ) < self.reload_interval_seconds and self._snapshot.loaded_at > 0:
            return

        if not self.config_path.exists():
            # Archivo ausente → flags vacíos (todos los queries caerán al default del caller)
            logger.warning("feature_flags file missing: %s", self.config_path)
            self._snapshot = FlagsSnapshot(loaded_at=now)
            return

        raw = self.config_path.read_text()
        source_hash = hashlib.sha256(raw.encode()).hexdigest()

        if source_hash == self._snapshot.source_hash:
            self._snapshot = FlagsSnapshot(
                defaults=self._snapshot.defaults,
                per_tenant=self._snapshot.per_tenant,
                loaded_at=now,
                source_hash=source_hash,
            )
            return

        # Parse minimal YAML (evita dependencia de PyYAML).
        parsed = _parse_minimal_yaml(raw)
        defaults = parsed.get("default", {})
        tenants = parsed.get("tenants", {})

        logger.info(
            "feature_flags reloaded: defaults=%d tenants=%d",
            len(defaults),
            len(tenants),
        )
        self._snapshot = FlagsSnapshot(
            defaults=defaults,
            per_tenant=tenants,
            loaded_at=now,
            source_hash=source_hash,
        )

    def is_enabled(self, tenant_id: UUID, feature: str, default: Any = _UNSET) -> bool:
        """Atajo para flags booleanas.

        Si `default` se provee y la feature no está declarada (ni en env,
        ni override, ni YAML), devuelve `default` en vez de levantar. Es el
        patrón recomendado para el hot-path: `is_enabled(t, "x", default=False)`.
        """
        val = self.get_value(tenant_id, feature, default=default)
        if not isinstance(val, bool):
            raise TypeError(f"Feature '{feature}' no es booleana (tipo={type(val).__name__})")
        return val

    def get_value(self, tenant_id: UUID, feature: str, default: Any = _UNSET) -> Any:
        """Devuelve el valor de la feature resolviendo por precedencia.

        env var PLATFORM_FF_<FLAG> → override del tenant → default (YAML)
        → parámetro `default=` → raise FeatureNotDeclaredError.
        """
        # 1. Override de ops por env var (kill-switch / force global).
        env_val = os.environ.get(ENV_PREFIX + feature.upper())
        if env_val is not None:
            return _parse_value(env_val)

        self._maybe_reload()

        # 2. Override del tenant.
        tenant_overrides = self._snapshot.per_tenant.get(str(tenant_id), {})
        if feature in tenant_overrides:
            return tenant_overrides[feature]

        # 3. Default del YAML.
        if feature in self._snapshot.defaults:
            return self._snapshot.defaults[feature]

        # 4. Default seguro provisto por el caller.
        if default is not _UNSET:
            return default

        raise FeatureNotDeclaredError(
            f"Feature '{feature}' no declarada en defaults ni override "
            f"para tenant {tenant_id}. Declararla en feature_flags.yaml, "
            f"pasar default=, o setear {ENV_PREFIX}{feature.upper()}."
        )

    def get_all_for_tenant(self, tenant_id: UUID) -> dict[str, Any]:
        """Devuelve todos los flags resueltos para el tenant (útil para debug/UI)."""
        self._maybe_reload()
        resolved: dict[str, Any] = dict(self._snapshot.defaults)
        resolved.update(self._snapshot.per_tenant.get(str(tenant_id), {}))
        return resolved


# ── Parser YAML minimal ────────────────────────────────────────────────


def _parse_minimal_yaml(text: str) -> dict[str, Any]:
    """Parser minimal para el formato específico de feature_flags.yaml.

    Soporta:
      - Claves top-level: `default:`, `tenants:`
      - Sub-claves con indentación de 2 espacios
      - Valores: true/false, enteros, strings (sin comillas)
      - Ignora comentarios (líneas que empiezan con `#`)
    """
    result: dict[str, Any] = {"default": {}, "tenants": {}}
    current_section: str | None = None
    current_tenant: str | None = None

    for raw_line in text.splitlines():
        stripped = raw_line.split("#", 1)[0].rstrip()
        if not stripped.strip():
            continue

        indent = len(stripped) - len(stripped.lstrip(" "))
        content = stripped.strip()

        if indent == 0:
            if content == "default:":
                current_section = "default"
                current_tenant = None
            elif content == "tenants:":
                current_section = "tenants"
                current_tenant = None
            else:
                current_section = None
                current_tenant = None
        elif indent == 2 and current_section == "default":
            if ":" in content:
                k, v = content.split(":", 1)
                result["default"][k.strip()] = _parse_value(v.strip())
        elif indent == 2 and current_section == "tenants":
            # "aaaaaaaa-...: " indica un tenant
            if content.endswith(":"):
                current_tenant = content.rstrip(":").strip()
                result["tenants"].setdefault(current_tenant, {})
        elif indent == 4 and current_section == "tenants" and current_tenant:
            if ":" in content:
                k, v = content.split(":", 1)
                result["tenants"][current_tenant][k.strip()] = _parse_value(v.strip())

    return result


def _parse_value(s: str) -> Any:
    s = s.strip()
    if s == "true":
        return True
    if s == "false":
        return False
    if s in {"null", ""}:
        return None
    # int
    try:
        return int(s)
    except ValueError:
        pass
    # float
    try:
        return float(s)
    except ValueError:
        pass
    # string (sin comillas)
    return s.strip('"').strip("'")
