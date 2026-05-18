"""Cliente HTTP del academic-service para validar TareaPractica.

Se usa al abrir un episodio para verificar que el `problema_id` apunta a
una TP existente, publicada, en plazo y de la comisión correcta.

Mirror del patrón `ContentClient`: usa headers de service-account
(`X-User-Id` con el UUID fijo del tutor, `X-Tenant-Id`, `X-User-Roles`).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

import httpx

logger = logging.getLogger(__name__)


@dataclass
class TareaPracticaResponse:
    """Subset de campos de TareaPractica que el tutor-service necesita."""

    id: UUID
    tenant_id: UUID
    comision_id: UUID
    estado: str
    fecha_inicio: datetime | None
    fecha_fin: datetime | None


@dataclass
class ComisionResponse:
    """Subset de campos de Comision que el tutor-service necesita.

    ADR-040: el tutor consume `materia_id` para propagarlo al ai-gateway en cada
    turno (resolver BYOK con scope=materia primero, fallback a scope=tenant).
    """

    id: UUID
    tenant_id: UUID
    materia_id: UUID
    periodo_id: UUID


class AcademicClient:
    """Cliente del academic-service.

    Propaga headers `X-*` del tutor-service como service-account para que
    el academic-service autorice la llamada (rol `tutor_service`).
    """

    def __init__(self, base_url: str, timeout: float = 10.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    async def get_tarea_practica(
        self,
        tarea_id: UUID,
        tenant_id: UUID,
        caller_id: UUID,
    ) -> TareaPracticaResponse | None:
        """Obtiene una TareaPractica por id.

        Returns:
            TareaPracticaResponse si existe (HTTP 200).
            None si la TP no existe (HTTP 404).

        Raises:
            httpx.HTTPStatusError: en caso de 5xx u otros errores HTTP no
                manejados (el caller decide cómo escalarlo).
        """
        headers = {
            "X-User-Id": str(caller_id),
            "X-Tenant-Id": str(tenant_id),
            "X-User-Email": "tutor-service@platform.internal",
            "X-User-Roles": "tutor_service",
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.get(
                f"{self.base_url}/api/v1/tareas-practicas/{tarea_id}",
                headers=headers,
            )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        data = resp.json()
        return TareaPracticaResponse(
            id=UUID(data["id"]),
            tenant_id=UUID(data["tenant_id"]),
            comision_id=UUID(data["comision_id"]),
            estado=data["estado"],
            fecha_inicio=_parse_datetime(data.get("fecha_inicio")),
            fecha_fin=_parse_datetime(data.get("fecha_fin")),
        )

    async def get_comision(
        self,
        comision_id: UUID,
        tenant_id: UUID,
        caller_id: UUID,
    ) -> ComisionResponse | None:
        """Obtiene una Comision por id.

        ADR-040 (Sec 6.2): se invoca al abrir un episodio para resolver
        `materia_id` y cachearlo en `SessionState`. Si la comision no existe
        (404) o el caller no tiene permiso (4xx), devuelve None — el caller
        degrada a `materia_id=None` (BYOK fallback a scope=tenant).

        Returns:
            ComisionResponse si existe (HTTP 200).
            None si la comision no existe (HTTP 404).

        Raises:
            httpx.HTTPStatusError: en caso de 5xx.
        """
        headers = {
            "X-User-Id": str(caller_id),
            "X-Tenant-Id": str(tenant_id),
            "X-User-Email": "tutor-service@platform.internal",
            "X-User-Roles": "tutor_service",
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.get(
                f"{self.base_url}/api/v1/comisiones/{comision_id}",
                headers=headers,
            )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        data = resp.json()
        return ComisionResponse(
            id=UUID(data["id"]),
            tenant_id=UUID(data["tenant_id"]),
            materia_id=UUID(data["materia_id"]),
            periodo_id=UUID(data["periodo_id"]),
        )


    async def get_tarea_practica_full(
        self,
        tarea_id: UUID,
        tenant_id: UUID,
        caller_id: UUID,
    ) -> dict | None:
        """Obtiene la TP completa incluyendo rubrica y ejercicios.

        tutor-context-rag-rubrica: se usa al abrir el episodio para resolver
        la rubrica de la TP (o del ejercicio especifico si ejercicio_orden!=None)
        y cachearla en SessionState. Best-effort: si falla, el caller ignora y
        el episodio se abre sin contexto de rubrica.

        Returns:
            Dict con todos los campos del response del academic-service
            (incluye rubrica JSONB y ejercicios JSONB array), o None si 404.
        """
        headers = {
            "X-User-Id": str(caller_id),
            "X-Tenant-Id": str(tenant_id),
            "X-User-Email": "tutor-service@platform.internal",
            "X-User-Roles": "tutor_service",
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.get(
                f"{self.base_url}/api/v1/tareas-practicas/{tarea_id}",
                headers=headers,
            )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()

    async def get_ejercicio_by_id(
        self,
        ejercicio_id: UUID,
        tenant_id: UUID,
        caller_id: UUID,
    ) -> dict | None:
        """Obtiene un Ejercicio del banco standalone por UUID (ADR-047).

        Consume `GET /api/v1/ejercicios/{id}` y devuelve el dict completo
        con todos los campos pedagógicos (banco_preguntas, misconceptions,
        respuesta_pista, heuristica_cierre, anti_patrones, tutor_rules,
        rubrica, prerequisitos, etc.).

        Returns:
            Dict con todos los campos del Ejercicio o None si 404.
        """
        headers = {
            "X-User-Id": str(caller_id),
            "X-Tenant-Id": str(tenant_id),
            "X-User-Email": "tutor-service@platform.internal",
            "X-User-Roles": "tutor_service",
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.get(
                f"{self.base_url}/api/v1/ejercicios/{ejercicio_id}",
                headers=headers,
            )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()

    async def get_tp_ejercicios(
        self,
        tarea_id: UUID,
        tenant_id: UUID,
        caller_id: UUID,
    ) -> list[dict]:
        """Lista los ejercicios asociados a una TP via tp_ejercicios (ADR-047).

        Consume `GET /api/v1/tareas-practicas/{tarea_id}/ejercicios` que
        devuelve list[TpEjercicioRead] ordenado por `orden`. Cada item
        tiene `{id, tarea_practica_id, ejercicio_id, orden, peso_en_tp,
        ejercicio: EjercicioRead}`.

        Returns:
            Lista de pairs (puede ser vacía si la TP no tiene ejercicios).
            Lista vacía también si la TP no existe (HTTP 404 raises).

        Raises:
            httpx.HTTPStatusError: en caso de 4xx/5xx no manejados.
        """
        headers = {
            "X-User-Id": str(caller_id),
            "X-Tenant-Id": str(tenant_id),
            "X-User-Email": "tutor-service@platform.internal",
            "X-User-Roles": "tutor_service",
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.get(
                f"{self.base_url}/api/v1/tareas-practicas/{tarea_id}/ejercicios",
                headers=headers,
            )
        resp.raise_for_status()
        data = resp.json()
        # El endpoint devuelve directamente la lista (no envuelta en ListResponse).
        return data if isinstance(data, list) else []

    async def resolve_ejercicio_orden_in_tp(
        self,
        tarea_id: UUID,
        ejercicio_id: UUID,
        tenant_id: UUID,
        caller_id: UUID,
    ) -> int | None:
        """Resuelve el `orden` denormalizado de un Ejercicio dentro de una TP.

        Necesario porque:
        - El CTR todavía emite `ejercicio_orden` (ADR-049 lo cambiará al
          sumar `ejercicio_id` al payload — Batch 6).
        - La validación de secuencialidad opera por orden.

        Returns:
            El `orden` del par (tarea_id, ejercicio_id) en tp_ejercicios,
            o None si el ejercicio no está asociado a esta TP.
        """
        pairs = await self.get_tp_ejercicios(
            tarea_id=tarea_id,
            tenant_id=tenant_id,
            caller_id=caller_id,
        )
        for pair in pairs:
            if str(pair.get("ejercicio_id")) == str(ejercicio_id):
                return pair.get("orden")
        return None


def _parse_datetime(value: str | None) -> datetime | None:
    """Parsea ISO-8601 que puede venir con sufijo Z o con offset."""
    if value is None:
        return None
    # fromisoformat acepta `+00:00` pero no `Z` en Python <3.11; lo
    # normalizamos para mantener compatibilidad.
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return datetime.fromisoformat(value)
