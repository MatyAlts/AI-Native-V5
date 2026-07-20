"""Auth cross-service del governance-service (A0.4).

governance-service es interno by-design (NO está en el ROUTE_MAP del
api-gateway — ver CLAUDE.md "governance-service NO expuesto en ROUTE_MAP"),
pero vive en la misma red que los demás servicios. Sin auth, cualquiera con
acceso de red lee todos los prompts y configs.

PATRÓN (espejo del evaluation-service `auth/dependencies.py`): se reusa el
helper compartido ``platform_observability.verify_gateway_signature`` para
validar la *procedencia* de los headers de identidad (que fueron emitidos por
el gateway), sin re-verificar el JWT aguas abajo. El invariante del sistema se
respeta: el api-gateway sigue siendo el único source of truth de identidad.

DIFERENCIA CLAVE con evaluation-service: governance NO se alcanza vía gateway.
El consumidor legítimo principal — ``tutor-service`` — llama a governance
DIRECTO (``GET /api/v1/prompts/tutor/vX``) al abrir cada episodio, sin pasar
por el gateway y por lo tanto sin firma. Por eso:

  1. El enforcement va TOTALMENTE detrás del flag ``require_gateway_signature``
     (default OFF). Con el flag apagado es un no-op — el runtime es idéntico al
     actual y el tutor sigue funcionando. (evaluation exige headers X-User-*
     siempre; acá no, porque el tutor no los manda y romperíamos episodios.)

  2. Con el flag ON se aceptan DOS caminos de procedencia:
       (a) firma HMAC del gateway (para callers que sí pasan por el gateway); o
       (b) un token de service-account (``X-Internal-Service-Token``) para el
           tutor-service y otros callers internos directos.
     Ausencia de ambos => 401.
"""

from __future__ import annotations

import hmac

from fastapi import Header, HTTPException, status
from platform_observability import verify_gateway_signature

from governance_service.config import settings

# Nombre del header del token de service-account. El caller interno
# (tutor-service) debe mandarlo para autenticarse cuando el flag está ON.
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
    """Dependency de auth para los endpoints de prompts/configs.

    Con ``require_gateway_signature=False`` (default) es un no-op total:
    preserva el comportamiento actual y NO rompe el llamado directo del
    tutor-service.

    Con el flag ON, exige procedencia probada por firma del gateway O por token
    de service-account. Sin ninguna de las dos => 401.
    """
    if not settings.require_gateway_signature:
        return

    # Camino (b): service-account directo (tutor-service y otros callers
    # internos que no pasan por el gateway).
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
