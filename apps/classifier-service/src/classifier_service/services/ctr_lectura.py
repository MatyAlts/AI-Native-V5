"""Lectura de episodios del CTR para el estudio de codificación (design D4).

Cuenta de servicio PROPIA (`ESTUDIO_LECTOR_SERVICE_USER_ID`, no reusa la del
tutor) con rol `classifier_worker`, que está en `READ_ROLES` y en
`CTR_OVERSIGHT_ROLES` del ctr-service: lee cualquier episodio del tenant sin
pasar por el gate de comisión (A0.6). Por eso el endpoint de la traza solo
resuelve `item_id` de la muestra o de las anclas del estudio del caller: esta
cuenta nunca se usa con un `episode_id` que venga del pedido.

No se modifica ctr-service: se mandan los mismos headers que inyecta el
gateway y, si hay `gateway_shared_secret`, la firma HMAC (`sign_headers`).

Errores: 404 -> `EpisodioInexistenteError`; cualquier otro error HTTP o de red
(incluido el timeout de 15 s) -> `CTRNoDisponibleError`, sin el cuerpo de la
respuesta (puede traer datos del episodio). Un 200 cuyo cuerpo no es JSON o no
tiene la forma mínima de `EpisodeWithEvents` que lee el estudio (un proxy que
responde HTML, un contrato cambiado) también es `CTRNoDisponibleError`: el
endpoint responde 502 genérico en vez de un 500 (verify-1, F6).
"""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any
from uuid import UUID

import httpx
from platform_observability import sign_headers

from classifier_service.config import settings

ESTUDIO_LECTOR_SERVICE_USER_ID = UUID("00000000-0000-0000-0000-000000000c0d")
ESTUDIO_LECTOR_EMAIL = "estudio-lector@classifier-service.internal"
ESTUDIO_LECTOR_ROL = "classifier_worker"
TIMEOUT_SEGUNDOS = 15.0


class CTRNoDisponibleError(Exception):
    """El CTR no respondió o devolvió un error distinto de 404."""


class EpisodioInexistenteError(Exception):
    """El CTR no tiene ese episodio en el tenant."""


def _es_entero(valor: Any) -> bool:
    return isinstance(valor, int) and not isinstance(valor, bool)


def _es_numero(valor: Any) -> bool:
    return isinstance(valor, int | float) and not isinstance(valor, bool)


def _es_uuid(valor: Any) -> bool:
    if not isinstance(valor, str):
        return False
    try:
        UUID(valor)
    except ValueError:
        return False
    return True


def _es_instante(valor: Any) -> bool:
    """ISO 8601 con zona, como lo parsea `traza_ciega._instante` (un instante
    sin zona no se puede restar a uno con zona)."""
    if not isinstance(valor, str):
        return False
    try:
        instante = datetime.fromisoformat(valor.replace("Z", "+00:00"))
    except ValueError:
        return False
    return instante.tzinfo is not None


def _payload_con_forma(evento: dict[str, Any]) -> bool:
    payload = evento.get("payload", {})
    if payload is None:
        return True
    if not isinstance(payload, dict):
        return False
    tipo = evento["event_type"]
    if tipo == "episodio_abierto":
        ejercicio = payload.get("ejercicio_id")
        if ejercicio is not None and not _es_uuid(ejercicio):
            return False
    if tipo == "lectura_enunciado":
        duracion = payload.get("duration_seconds")
        if duracion is not None and not _es_numero(duracion):
            return False
    return True


def _evento_con_forma(evento: Any) -> bool:
    return (
        isinstance(evento, dict)
        and _es_entero(evento.get("seq"))
        and isinstance(evento.get("event_type"), str)
        and _es_instante(evento.get("ts"))
        and isinstance(evento.get("chain_hash"), str)
        and _payload_con_forma(evento)
    )


def tiene_forma_de_episodio(datos: Any) -> bool:
    """Forma de `EpisodeWithEvents` (ctr-service `schemas`) en lo que leen la
    traza, la evidencia fija y el criterio de episodio terminado: tipos de cada
    campo, `ts` ISO 8601 con zona, `problema_id` y `ejercicio_id` UUID, y
    `duration_seconds` numérico (se suma al agrupar lecturas). Los demás campos
    del payload se copian tal cual y no se validan (verify-2, N2)."""
    return (
        isinstance(datos, dict)
        and isinstance(datos.get("estado"), str)
        and _es_uuid(datos.get("problema_id"))
        and _es_entero(datos.get("events_count"))
        and isinstance(datos.get("last_chain_hash"), str)
        and isinstance(datos.get("integrity_compromised", False), bool)
        and isinstance(datos.get("events"), list)
        and all(_evento_con_forma(e) for e in datos["events"])
    )


class CTRLector:
    def __init__(
        self,
        base_url: str,
        *,
        secreto: str = "",
        timeout: float = TIMEOUT_SEGUNDOS,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.secreto = secreto
        self.timeout = timeout
        self._transport = transport

    def _headers(self, tenant_id: UUID) -> dict[str, str]:
        headers = {
            "X-User-Id": str(ESTUDIO_LECTOR_SERVICE_USER_ID),
            "X-Tenant-Id": str(tenant_id),
            "X-User-Email": ESTUDIO_LECTOR_EMAIL,
            "X-User-Roles": ESTUDIO_LECTOR_ROL,
        }
        if self.secreto:
            ts = int(time.time())
            headers["X-Gateway-Ts"] = str(ts)
            headers["X-Gateway-Signature"] = sign_headers(
                self.secreto,
                headers["X-User-Id"],
                headers["X-Tenant-Id"],
                headers["X-User-Roles"],
                ts,
            )
        return headers

    async def episodio(self, tenant_id: UUID, episode_id: UUID) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=self.timeout, transport=self._transport) as client:
                r = await client.get(
                    f"{self.base_url}/api/v1/episodes/{episode_id}",
                    headers=self._headers(tenant_id),
                )
        except httpx.HTTPError as exc:
            raise CTRNoDisponibleError(type(exc).__name__) from None
        if r.status_code == 404:
            raise EpisodioInexistenteError(str(episode_id))
        if r.status_code != 200:
            raise CTRNoDisponibleError(f"status {r.status_code}")
        try:
            datos = r.json()
        except ValueError:
            raise CTRNoDisponibleError("cuerpo no JSON") from None
        if not tiene_forma_de_episodio(datos):
            raise CTRNoDisponibleError("forma inesperada")
        episodio: dict[str, Any] = datos
        return episodio


def get_ctr_lector() -> CTRLector:
    """Dependencia FastAPI; los tests la reemplazan con un CTR falso."""
    return CTRLector(settings.ctr_service_url, secreto=settings.gateway_shared_secret)
