"""Auth cross-service del analytics-service (A0.1).

analytics-service YA valida la PRESENCIA de los headers de identidad
(``X-Tenant-Id`` / ``X-User-Id``): sin ellos los endpoints devuelven 401/403
(ver ``routes/analytics.py::get_tenant_id`` / ``get_user_id``). Pero esa
validación NO prueba la PROCEDENCIA de los headers — cualquiera con acceso de
red al servicio interno puede forjarlos y leer análisis de otra comisión/tenant
(A0.1).

PATRÓN (espejo del governance-service `auth.py`, A0.4): se reusa el helper
compartido ``platform_observability.verify_gateway_signature`` para validar que
los headers fueron emitidos por el gateway (firma HMAC), sin re-verificar el JWT
aguas abajo. El invariante del sistema se respeta: el api-gateway sigue siendo
el único source of truth de identidad.

Esta dependency corre ADEMÁS de la validación de headers existente — NO la
reemplaza. Con el flag OFF (default) es un no-op total: el runtime es idéntico
al actual y los comandos ``make kappa/progression/export-academic`` (que pegan
por curl directo con ``TOKEN=dev-token``, sin firma) siguen funcionando.

Con el flag ON se aceptan DOS caminos de procedencia:
  (a) firma HMAC del gateway (para callers que pasan por el gateway); o
  (b) un token de service-account (``X-Internal-Service-Token``) para callers
      internos directos — ej. los comandos make en prod, que no pasan por el
      gateway y por lo tanto no firman.
Ausencia de ambos => 401.
"""

from __future__ import annotations

import hmac

from fastapi import Header, HTTPException, status
from platform_observability import verify_gateway_signature

from analytics_service import config

# Nombre del header del token de service-account. Los callers internos directos
# (ej. curls de los comandos make en prod) deben mandarlo cuando el flag está ON.
INTERNAL_SERVICE_TOKEN_HEADER = "X-Internal-Service-Token"


def _valid_service_token(token: str | None) -> bool:
    """True si ``token`` coincide con el service-account configurado.

    Comparación constant-time (evita timing oracle). Si no hay token
    configurado, este camino queda deshabilitado (siempre False) para no abrir
    un bypass con string vacío.
    """
    secret = config.settings.internal_service_token
    if not secret or not token:
        return False
    return hmac.compare_digest(secret, token)


async def require_gateway_auth(
    x_tenant_id: str | None = Header(default=None),
    x_user_id: str | None = Header(default=None),
    x_user_roles: str | None = Header(default=None),
    x_gateway_signature: str | None = Header(default=None),
    x_gateway_ts: str | None = Header(default=None),
    x_internal_service_token: str | None = Header(default=None),
) -> None:
    """Dependency de auth para los routers analíticos.

    Con ``require_gateway_signature=False`` (default) es un no-op total:
    preserva el comportamiento actual (incluida la validación de headers, que
    vive en otras dependencies) y NO rompe los comandos make.

    Con el flag ON, exige procedencia probada por firma del gateway O por token
    de service-account. Sin ninguna de las dos => 401. La validación de
    presencia de headers (get_tenant_id / get_user_id) sigue corriendo aparte.
    """
    settings = config.settings
    if not settings.require_gateway_signature:
        return

    # Camino (b): service-account directo (callers internos que no pasan por el
    # gateway, ej. los comandos make en prod).
    if _valid_service_token(x_internal_service_token):
        return

    # Camino (a): firma HMAC del gateway sobre los headers de identidad.
    ok = verify_gateway_signature(
        settings.gateway_shared_secret,
        x_user_id or "",
        x_tenant_id or "",
        x_user_roles or "",
        x_gateway_ts,  # type: ignore[arg-type]
        x_gateway_signature or "",
    )
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Firma del gateway ausente o invalida y token de servicio ausente o invalido",
        )
