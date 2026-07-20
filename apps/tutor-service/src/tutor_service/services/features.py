"""Adaptador del package platform-ops.feature_flags para el tutor-service.

Uso en routers y servicios:

    from tutor_service.services.features import get_flags
    flags = get_flags()
    if flags.is_enabled(user.tenant_id, "enable_claude_opus"):
        model = "claude-opus-4-7"
    else:
        model = "claude-sonnet-4-6"
"""

from __future__ import annotations

from functools import lru_cache

from platform_ops import FeatureFlags

from tutor_service.config import settings


@lru_cache(maxsize=1)
def get_flags() -> FeatureFlags:
    """Singleton. Se carga una vez al primer uso."""
    return FeatureFlags(
        config_path=settings.feature_flags_path,
        reload_interval_seconds=settings.feature_flags_reload_seconds,
    )
