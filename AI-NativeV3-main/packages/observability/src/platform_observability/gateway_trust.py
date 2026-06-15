"""Firma HMAC del api-gateway para defensa en profundidad cross-service.

CONTEXTO ARQUITECTÓNICO (invariante del sistema):
    El api-gateway es el ÚNICO source of truth de identidad. Los servicios
    internos confían en los headers ``X-Tenant-Id`` / ``X-User-Id`` /
    ``X-User-Roles`` que inyecta el gateway tras validar el JWT — NO
    re-verifican el JWT aguas abajo (ver CLAUDE.md "Propiedades críticas").

Este módulo NO viola ese invariante: agrega una firma HMAC-SHA256
(``X-Gateway-Signature``) que **prueba** que esos headers fueron emitidos por
el gateway (que comparte un secreto con los servicios), en vez de venir
forjados por un cliente que pega directo a un servicio interno expuesto.

No se re-valida identidad: solo se valida procedencia. Va detrás de un flag
``REQUIRE_GATEWAY_SIGNATURE`` (default OFF) en cada servicio, de modo que con
el flag apagado el comportamiento runtime es idéntico al actual.

Mensaje canónico firmado (orden fijo, separado por ``\\n``):

    f"{user_id}\\n{tenant_id}\\n{roles}\\n{ts}"

donde ``roles`` es exactamente el string que inyecta el gateway (roles
ordenados, unidos por coma) y ``ts`` es el epoch int del momento de la firma
(anti-replay).
"""

from __future__ import annotations

import hashlib
import hmac
import time

__all__ = [
    "sign_headers",
    "verify_gateway_signature",
]


def _canonical_message(user_id: str, tenant_id: str, roles: str, ts: int) -> bytes:
    """Construye el mensaje canónico a firmar.

    El orden y los separadores son parte del contrato: emisor (gateway) y
    verificadores (servicios) DEBEN coincidir bit-a-bit o la firma no valida.
    """
    return f"{user_id}\n{tenant_id}\n{roles}\n{ts}".encode()


def sign_headers(secret: str, user_id: str, tenant_id: str, roles: str, ts: int) -> str:
    """Firma los headers de identidad con HMAC-SHA256.

    Args:
        secret: secreto compartido gateway↔servicios (``GATEWAY_SHARED_SECRET``).
        user_id: valor de ``X-User-Id`` que inyecta el gateway.
        tenant_id: valor de ``X-Tenant-Id``.
        roles: valor de ``X-User-Roles`` (roles ordenados, join por coma).
        ts: epoch int del momento de la firma.

    Returns:
        El hexdigest de la firma HMAC-SHA256.
    """
    message = _canonical_message(user_id, tenant_id, roles, ts)
    return hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()


def verify_gateway_signature(
    secret: str,
    user_id: str,
    tenant_id: str,
    roles: str,
    ts: int,
    signature: str,
    *,
    max_age_seconds: int = 300,
) -> bool:
    """Verifica la firma HMAC de los headers de identidad.

    Recomputa la firma esperada sobre el mensaje canónico y la compara con la
    recibida usando ``hmac.compare_digest`` (constant-time, evita timing
    oracle). Rechaza firmas con ``ts`` más viejo que ``max_age_seconds``
    (anti-replay) o con ``ts`` en el futuro lejano (clock skew defensivo).

    No lanza excepciones: cualquier entrada inválida (firma vacía, ts no
    numérico, tipos raros) devuelve ``False``.

    Args:
        secret: secreto compartido gateway↔servicios.
        user_id: valor de ``X-User-Id`` recibido.
        tenant_id: valor de ``X-Tenant-Id`` recibido.
        roles: valor de ``X-User-Roles`` recibido.
        ts: epoch int recibido en ``X-Gateway-Ts``.
        signature: hexdigest recibido en ``X-Gateway-Signature``.
        max_age_seconds: ventana anti-replay (default 300s = 5 min).

    Returns:
        True si la firma es válida y está dentro de la ventana temporal.
    """
    if not secret or not signature:
        return False

    try:
        ts_int = int(ts)
    except (TypeError, ValueError):
        return False

    now = int(time.time())
    # Anti-replay: rechazar firmas viejas. Tolerar un poco de skew de reloj
    # hacia el futuro (mismo margen que la ventana), no firmas arbitrariamente
    # adelantadas.
    if ts_int < now - max_age_seconds or ts_int > now + max_age_seconds:
        return False

    expected = sign_headers(secret, user_id, tenant_id, roles, ts_int)
    try:
        return hmac.compare_digest(expected, signature)
    except (TypeError, ValueError):
        return False
