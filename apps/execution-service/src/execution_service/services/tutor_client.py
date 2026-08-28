"""Emision de `tests_ejecutados` al CTR, via tutor-service (tarea 5.1).

Por que existe
--------------
`ctr_emitter` construia el payload desde el dia uno y **nadie lo llamaba**: la
propia tarea 5.1 lo admitia ("Falta cablearlo al POST del tutor-service") y aun
asi estaba marcada como hecha. El efecto era de tesis, no de codigo:

    java    2 episodios   13 codigo_ejecutado    0 tests_ejecutados
    python  156 episodios  11 codigo_ejecutado  113 tests_ejecutados

El labeler v1.2.0 usa `tests_ejecutados` para separar N3 de N4. Sin el evento,
un episodio Java **no puede** tomar ese camino: los episodios Java y Python no
son comparables en el corpus, que es exactamente lo que la change
`multi-language-research-integrity` existia para impedir. Y no se nota — no hay
error en ningun lado, solo un evento que nunca aparece.

La identidad es la del ALUMNO, no la del servicio
-------------------------------------------------
Este cliente reenvia los headers del estudiante que pidio la corrida, NO el
service-account `execution_service` que usa `AcademicClient`. No es un atajo: el
invariante del CTR dice que los eventos de actividad del alumno llevan su
`user_id` (mismo criterio que `codigo_ejecutado`). Un `tests_ejecutados` a
nombre del servicio seria un evento de actividad sin alumno.

Ademas hace que el endpoint del tutor no necesite aceptar un rol nuevo: el
estudiante ya esta en su lista de roles permitidos.

Falla soft
----------
Un fallo emitiendo NO rompe la corrida: el alumno ya vio su resultado y la
cuota ya se consumio. Se loguea fuerte, porque un evento perdido es un episodio
que para el clasificador se ejecuto de menos.
"""

from __future__ import annotations

import logging
from uuid import UUID

import httpx

from execution_service.config import settings
from execution_service.services import metrics
from execution_service.services.ctr_emitter import idempotency_key

logger = logging.getLogger(__name__)


class TutorClient:
    def __init__(self, base_url: str | None = None) -> None:
        self._base_url = (base_url or settings.tutor_service_url).rstrip("/")

    def _headers(self, *, user_id: UUID, tenant_id: UUID, execution_id: UUID) -> dict[str, str]:
        headers = {
            # La accion es del alumno. Ver el docstring del modulo.
            "X-User-Id": str(user_id),
            "X-Tenant-Id": str(tenant_id),
            "X-User-Email": "estudiante@platform.internal",
            "X-User-Roles": "estudiante",
            # Deriva del execution_id (uuid5): un reintento no agrega un segundo
            # evento a la cadena. La corrida ya se pago en computo y cuota.
            "Idempotency-Key": idempotency_key(execution_id),
        }
        if settings.internal_service_token:
            headers["X-Internal-Service-Token"] = settings.internal_service_token
        return headers

    async def emit_tests_ejecutados(
        self,
        *,
        episode_id: UUID,
        execution_id: UUID,
        user_id: UUID,
        tenant_id: UUID,
        payload: dict[str, object],
    ) -> bool:
        """Emite el evento. Devuelve si se acepto. Nunca levanta."""
        # `execution_engine` lo produce `build_payload` pero el contrato del CTR
        # todavia no lo transporta; se saca aca en vez de mandarlo y que el
        # endpoint lo descarte en silencio.
        cuerpo = {k: v for k, v in payload.items() if k != "execution_engine"}
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    f"{self._base_url}/api/v1/episodes/{episode_id}/run-tests",
                    json=cuerpo,
                    headers=self._headers(
                        user_id=user_id, tenant_id=tenant_id, execution_id=execution_id
                    ),
                )
        except (httpx.HTTPError, OSError) as exc:
            metrics.record_ctr_emission_failed(reason="unreachable")
            logger.error(
                "tests_ejecutados_no_emitido episodio=%s ejecucion=%s error=%s "
                "— el episodio queda sin el evento que el labeler usa para N3/N4",
                episode_id,
                execution_id,
                type(exc).__name__,
            )
            return False

        if resp.status_code == 202:
            logger.info(
                "tests_ejecutados_emitido episodio=%s ejecucion=%s", episode_id, execution_id
            )
            return True

        if resp.status_code == 422:
            # Casi siempre es UNA sola causa: `INTERNAL_SERVICE_TOKEN` distinto
            # entre este servicio y el tutor-service. Rebota solo los ejercicios
            # con casos ocultos, que es el modo de falla mas caro — silencioso y
            # justo en los que sostienen el claim del ADR-060.
            metrics.record_ctr_emission_failed(reason="rejected_422")
            logger.error(
                "tests_ejecutados_rechazado_422 episodio=%s ejecucion=%s body=%s "
                "— si menciona tests_hidden, INTERNAL_SERVICE_TOKEN no coincide "
                "con el del tutor-service. El corpus esta perdiendo eventos.",
                episode_id,
                execution_id,
                resp.text[:200],
            )
            return False

        # 409 = episodio cerrado, o sesion ausente que el heal no pudo reponer.
        # "Expirado" YA NO da 409: el `_emitir_con_heal` del tutor-service
        # reconstruye la sesion vencida con `resume_episode` y reintenta, asi
        # que el TTL vencido con episodio vivo termina en 202. Es esperable (el
        # alumno cerro la pestana antes de que terminara la corrida) y no
        # amerita el mismo ruido que un rechazo real.
        #
        # 403 —episodio de otro alumno— sale por la rama `rejected_other`, a
        # proposito: un execution-service pidiendole al tutor que escriba en la
        # cadena de otro estudiante NO es esperable, es un bug de cableo.
        es_esperable = resp.status_code == 409
        metrics.record_ctr_emission_failed(
            reason="rejected_409" if es_esperable else "rejected_other"
        )
        nivel = logger.info if es_esperable else logger.error
        nivel(
            "tests_ejecutados_rechazado episodio=%s ejecucion=%s status=%s body=%s",
            episode_id,
            execution_id,
            resp.status_code,
            resp.text[:200],
        )
        return False
