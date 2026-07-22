"""Métricas custom de analytics-service emitidas via OTel SDK.

Las métricas de κ rolling viven acá (no en classifier-service) porque el
analytics-service es quien orquesta el procedimiento intercoder de Cohen's
kappa (`/api/v1/analytics/kappa`) y conoce los timestamps de cómputo. El
classifier-service emite las métricas de cada clasificación per-episode.
"""

from __future__ import annotations

from platform_observability import get_meter

_meter = get_meter("analytics-service")

# κ rolling 7d por cohorte. Push-style: cada vez que un kappa se computa para
# una cohorte (via `/kappa` endpoint o el refresh nightly), el gauge se setea
# al valor nuevo. UpDownCounter para que pueda subir y bajar en updates.
classifier_kappa_rolling = _meter.create_up_down_counter(
    "classifier_kappa_rolling",
    description="Coeficiente Cohen's kappa por cohorte (window 7d). Actualizado por el endpoint /kappa.",
    unit="1",
)

# Timestamp del último update del gauge κ por cohorte. Permite a Grafana
# computar `time() - last_update_unix_seconds` para mostrar "frescura del dato"
# y alertar si el dato quedó stale.
classifier_kappa_rolling_last_update_unix_seconds = _meter.create_up_down_counter(
    "classifier_kappa_rolling_last_update_unix_seconds",
    description="Unix timestamp del último cómputo del kappa rolling por cohorte.",
    unit="s",
)


__all__ = [
    "classifier_kappa_rolling",
    "classifier_kappa_rolling_last_update_unix_seconds",
]
