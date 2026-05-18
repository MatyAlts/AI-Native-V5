"""Feature flags por tenant.

Resuelve si una feature está activa para un tenant específico. La fuente
de verdad es un YAML en el governance-service (misma infra que prompts):

    # /etc/platform/feature_flags.yaml
    default:
      enable_code_execution: false
      enable_claude_opus: false
      max_episodes_per_day: 50

    tenants:
      aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa:  # UNSL (pilot tenant)
        enable_code_execution: true
        enable_claude_opus: true
        max_episodes_per_day: 200
      bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb:
        enable_code_execution: true

Consulta:
    FeatureFlags.is_enabled(tenant_id, "enable_code_execution") → bool
    FeatureFlags.get_value(tenant_id, "max_episodes_per_day") → int

Resolución: tenant override → default → raise si la feature no existe.
El objetivo es tener todas las features declaradas en `default` para que
nunca haya "feature no declarada" silenciosamente.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import UUID

logger = logging.getLogger(__name__)


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
        import hashlib

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

    def is_enabled(self, tenant_id: UUID, feature: str) -> bool:
        """Atajo para flags booleanas."""
        val = self.get_value(tenant_id, feature)
        if not isinstance(val, bool):
            raise TypeError(f"Feature '{feature}' no es booleana (tipo={type(val).__name__})")
        return val

    def get_value(self, tenant_id: UUID, feature: str) -> Any:
        """Devuelve el valor de la feature; levanta si no está declarada."""
        self._maybe_reload()

        tenant_overrides = self._snapshot.per_tenant.get(str(tenant_id), {})
        if feature in tenant_overrides:
            return tenant_overrides[feature]

        if feature in self._snapshot.defaults:
            return self._snapshot.defaults[feature]

        raise FeatureNotDeclaredError(
            f"Feature '{feature}' no declarada en defaults ni override "
            f"para tenant {tenant_id}. Declarar en feature_flags.yaml."
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
