"""Cliente del academic-service: trae la definicion COMPLETA del ejercicio.

Con los casos OCULTOS incluidos — que es el punto entero de ejecutar
server-side. La ejecucion en el navegador no podia dar esta propiedad: para
correr un caso oculto habria que mandarselo al alumno, y ahi deja de ser oculto.

**Va DIRECTO al academic-service, no via gateway.** El gateway inyecta la
identidad del caller original (el alumno), y con esa identidad el academic-service
aplica `sanitize_ejercicio_for_student` y devuelve solo los casos publicos. Este
servicio se presenta con su propio rol de service-account `execution_service`,
que esta en `FULL_CONTENT_ROLES` por la misma razon que `tutor_service`.

Contrapartida de ese privilegio: **nada de lo que se lee acá sale en la
respuesta al cliente**. Lo garantiza `to_client_payload` en `executor.py`, con
un test dedicado (tarea 3.5).
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

import httpx

from execution_service.config import settings

# Service-account propio. NO se reusa el del tutor: si mañana hay que revocarle
# el acceso a uno de los dos, tienen que ser revocables por separado.
EXECUTION_SERVICE_USER_ID = "00000000-0000-0000-0000-000000000013"


@dataclass(frozen=True)
class TestCase:
    # pytest colecta por convencion cualquier clase que empiece con `Test`.
    # Esto es un dataclass del dominio, no una suite.
    __test__ = False

    id: str
    name: str
    type: str
    code: str
    expected: str | None
    is_public: bool
    weight: float


@dataclass(frozen=True)
class Ejercicio:
    id: UUID
    language: str
    inicial_codigo: str | None
    test_cases: list[TestCase]

    @property
    def public_cases(self) -> list[TestCase]:
        return [tc for tc in self.test_cases if tc.is_public]

    @property
    def hidden_cases(self) -> list[TestCase]:
        return [tc for tc in self.test_cases if not tc.is_public]


class AcademicUnavailableError(RuntimeError):
    """No se pudo leer la definicion del ejercicio.

    Es fallo de infraestructura, no del alumno: se traduce a
    `RunOutcome.INFRASTRUCTURE_FAILURE`, nunca a casos fallidos.
    """


class AcademicClient:
    def __init__(self, base_url: str | None = None) -> None:
        self._base_url = (base_url or settings.academic_service_url).rstrip("/")

    def _headers(self, tenant_id: UUID) -> dict[str, str]:
        headers = {
            "X-User-Id": EXECUTION_SERVICE_USER_ID,
            "X-Tenant-Id": str(tenant_id),
            "X-User-Email": "execution-service@platform.internal",
            "X-User-Roles": "execution_service",
        }
        if settings.internal_service_token:
            headers["X-Internal-Service-Token"] = settings.internal_service_token
        return headers

    async def get_ejercicio(self, ejercicio_id: UUID, tenant_id: UUID) -> Ejercicio:
        """Definicion completa del ejercicio, con los casos ocultos.

        Raises:
            AcademicUnavailableError: no respondio, o el ejercicio no existe.
        """
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    f"{self._base_url}/api/v1/ejercicios/{ejercicio_id}",
                    headers=self._headers(tenant_id),
                )
        except (httpx.HTTPError, OSError) as exc:
            raise AcademicUnavailableError(
                f"academic-service no alcanzable: {type(exc).__name__}"
            ) from exc

        if resp.status_code == 404:
            raise AcademicUnavailableError(f"ejercicio {ejercicio_id} no encontrado")
        if resp.status_code >= 400:
            raise AcademicUnavailableError(f"academic-service respondio {resp.status_code}")

        body = resp.json()
        return Ejercicio(
            id=UUID(body["id"]),
            language=body.get("language") or "python",
            inicial_codigo=body.get("inicial_codigo"),
            test_cases=[
                TestCase(
                    id=str(tc.get("id") or f"tc{i}"),
                    name=tc.get("name") or f"caso {i + 1}",
                    type=tc.get("type") or "stdin_stdout",
                    code=tc.get("code") or "",
                    expected=tc.get("expected"),
                    # Sin `is_public` explicito se asume OCULTO. El default
                    # seguro es no mostrarlo: equivocarse para el otro lado
                    # filtra la solucion.
                    is_public=bool(tc.get("is_public", False)),
                    weight=float(tc.get("weight") or 1.0),
                )
                for i, tc in enumerate(body.get("test_cases") or [])
            ],
        )
