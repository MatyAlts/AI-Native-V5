"""Auth cross-service del integrity-attestation-service (A0.1).

El integrity-attestation-service es infraestructura institucional interna del
piloto (NO está en el ROUTE_MAP del api-gateway — ver CLAUDE.md "completamente
excluidos del ROUTE_MAP by-design"), pero expone endpoints HTTP en la red
interna. Sin auth, cualquiera con acceso de red puede forjar los headers de
identidad `X-User-*` y, vía el POST, hacer que la clave Ed25519 institucional
firme + appendee al journal attestations arbitrarias (episodios fabricados con
firma legítima de la institución).

PATRÓN (espejo de governance-service `auth.py` A0.4 y ai-gateway `auth.py`
A0.1): se reusa el helper compartido ``platform_observability.verify_gateway_signature``
para validar la *procedencia* de los headers de identidad (que fueron emitidos
por el gateway), sin re-verificar el JWT aguas abajo. El invariante del sistema
se respeta: el api-gateway sigue siendo el único source of truth de identidad.

ALCANCE: este dependency SOLO se cablea en el POST /api/v1/attestations (el
único verbo que muta el journal). Los GET (/pubkey, /{date}) quedan ABIERTOS
por diseño (ADR-021): son públicos para que auditores externos verifiquen las
firmas SIN credenciales del gateway. El /health también queda abierto (probes).

  1. El enforcement va TOTALMENTE detrás del flag ``require_gateway_signature``
     (default OFF). Con el flag apagado es un no-op — el runtime es idéntico al
     actual.

  2. Con el flag ON se aceptan DOS caminos de procedencia:
       (a) firma HMAC del gateway (para callers que sí pasan por el gateway); o
       (b) un token de service-account (``X-Internal-Service-Token``) para
           callers internos directos que no pasan por el gateway.
     Ausencia de ambos => 401.
"""

from __future__ import annotations

import hmac

from fastapi import Header, HTTPException, status
from platform_observability import verify_gateway_signature

from integrity_attestation_service.config import settings

# Nombre del header del token de service-account. Los callers internos directos
# deben mandarlo para autenticarse cuando el flag está ON.
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
    """Dependency de auth para el POST de attestations.

    Con ``require_gateway_signature=False`` (default) es un no-op total:
    preserva el comportamiento actual.

    Con el flag ON, exige procedencia probada por firma del gateway O por token
    de service-account. Sin ninguna de las dos => 401.
    """
    if not settings.require_gateway_signature:
        return

    # Camino (b): service-account directo (callers internos que no pasan por el
    # gateway).
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
