"""Auth de procedencia cross-service del classifier-service (A0.1).

El api-gateway es el ÚNICO source of truth de identidad: valida el JWT e
inyecta ``X-Tenant-Id`` / ``X-User-Id`` / ``X-User-Roles`` a los servicios
internos, que confían en esos headers sin re-verificar el JWT aguas abajo
(ver CLAUDE.md "Propiedades críticas"). El classifier ya consume esos headers
(``classifier_service.auth.get_current_user``) para autorizar por rol y scopear
el tenant — pero HOY no prueba que hayan sido emitidos por el gateway. Si el
puerto interno queda expuesto, cualquiera los forja (bug A0.1).

Este dependency NO viola el invariante: reusa el helper compartido
``platform_observability.verify_gateway_signature`` para validar la
*procedencia* de los headers (firma HMAC del gateway), sin re-verificar el JWT.
Es defensa en profundidad, TOTALMENTE detrás del flag
``require_gateway_signature`` (default OFF).

DIFERENCIA con el flujo del gateway: hay callers legítimos que llegan DIRECTO,
sin pasar por el gateway y por lo tanto sin firma:

  - ``reclassify_all.py`` corre dentro del contenedor y pega a ``localhost``
    (backfill de re-clasificación) con ``X-User-Roles=classifier_worker``.
  - ``academic-service`` pega directo a ``GET /api/v1/classifier/config-hash``
    al resolver ``GET /comisiones/{id}/nes``.

Por eso, igual que governance (A0.4):

  1. Con el flag OFF (default) es un no-op — el runtime es idéntico al actual y
     ningún caller directo se rompe.
  2. Con el flag ON se aceptan DOS caminos de procedencia:
       (a) firma HMAC del gateway (para callers que pasan por el gateway); o
       (b) un token de service-account (``X-Internal-Service-Token``) para los
           callers internos directos.
     Ausencia de ambos => 401.
"""

from __future__ import annotations

import hmac

from fastapi import Header, HTTPException, status
from platform_observability import verify_gateway_signature

from classifier_service.config import settings

# Nombre del header del token de service-account. Los callers internos directos
# (reclassify_all, academic-service) deben mandarlo para autenticarse con el
# flag ON.
INTERNAL_SERVICE_TOKEN_HEADER = "X-Internal-Service-Token"


def _valid_service_token(token: str | None) -> bool:
    """True si ``token`` coincide con el service-account configurado.

    Comparación constant-time (evita timing oracle). Si no hay token
    configurado, este camino queda deshabilitado (siempre False) para no abrir
    un bypass con string vacío.
    """
    if not settings.internal_service_token or not token:
        return False
    return hmac.compare_digest(settings.internal_service_token, token)


async def require_gateway_auth(
    x_tenant_id: str | None = Header(default=None),
    x_user_id: str | None = Header(default=None),
    x_user_roles: str | None = Header(default=None),
    x_gateway_signature: str | None = Header(default=None),
    x_gateway_ts: str | None = Header(default=None),
    x_internal_service_token: str | None = Header(default=None),
) -> None:
    """Dependency de procedencia para los routers de datos/metadata del classifier.

    Con ``require_gateway_signature=False`` (default) es un no-op total:
    preserva el comportamiento actual y NO rompe a los callers directos
    (reclassify_all + academic-service).

    Con el flag ON, exige procedencia probada por firma del gateway O por token
    de service-account. Sin ninguna de las dos => 401.
    """
    if not settings.require_gateway_signature:
        return

    # Camino (b): service-account directo (reclassify_all + academic-service,
    # que no pasan por el gateway).
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
