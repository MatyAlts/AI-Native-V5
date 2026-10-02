"""Tests de `GET /api/v1/analytics/student/me/cii-evolution-longitudinal`.

EL BUG QUE CIERRA (reportado el 2026-10-02 por un alumno del piloto)
----------------------------------------------------------------------
El bloque "tu trayectoria en tareas parecidas" de la pantalla "Mi progreso"
mostraba un error crudo:

    No pudimos cargar esta parte de tu progreso.
    Error: cii-evolution-longitudinal failed: 403

El web-student pegaba a `/student/{id}/cii-evolution-longitudinal` con su
PROPIO uuid y recibia 403.

LA CAUSA, QUE NO ES "AL ALUMNO NO LE CORRESPONDE"
---------------------------------------------------
`clerk_base_roles` reparte `"estudiante,docente"` a TODO usuario logueado
(`api-gateway/config.py`), asi que un alumno real llega con rol `docente`.
`require_student_progress_access` ve un rol de staff, toma la rama de docente, y
exige membresia en `usuarios_comision` — tabla donde los alumnos no estan,
porque viven en `inscripciones`. 403.

POR QUE UN `/me` Y NO TOCAR EL GUARD
--------------------------------------
Sacarle `docente` a la etiqueta base rompe a los docentes reales en este mismo
endpoint: caerian en la rama de alumno, que solo deja ver el propio progreso. Y
aflojar el guard arregla este 403 pero deja intacto el problema de fondo —la
etiqueta miente para todos—, que es una decision de autorizacion con su propia
conversacion.

El `/me` no necesita ninguna de las dos: **el pseudonimo sale del token y no se
acepta por path**, asi que no hay nada que autorizar ni escalacion que impedir.
Es el mismo patron de `/student/me/episodes` y `/student/me/reflections`, y por
eso ESOS bloques de la misma pantalla cargaban bien mientras este fallaba.

LO QUE ESTE ARCHIVO NO CUBRE
------------------------------
Las queries reales (triple cross-DB con RLS) — en modo dev el endpoint devuelve
la estructura vacia, igual que sus hermanos. Eso se cubre en smoke con stack
levantado. Lo que SI se afirma aca es el contrato de identidad, que es la parte
que el bug rompio.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from analytics_service.main import app
from fastapi.testclient import TestClient

_TENANT = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
_USER = "11111111-1111-1111-1111-111111111111"
_COMISION = "22222222-2222-2222-2222-222222222222"
_RUTA = "/api/v1/analytics/student/me/cii-evolution-longitudinal"


@pytest.fixture
def client() -> TestClient:
    with TestClient(app) as c:
        yield c


class TestLaIdentidadSaleDelToken:
    def test_el_pseudonimo_del_response_es_el_del_header(self, client: TestClient) -> None:
        """La garantia central: el alumno no puede pedir el progreso de otro.

        No hay path param que falsear — el uuid sale de `X-User-Id`, que lo
        inyecta autoritativamente el api-gateway.
        """
        r = client.get(
            _RUTA,
            params={"comision_id": _COMISION},
            headers={"X-Tenant-Id": _TENANT, "X-User-Id": _USER},
        )
        assert r.status_code == 200, r.text
        assert r.json()["student_pseudonym"] == _USER

    def test_dos_alumnos_distintos_reciben_su_propio_pseudonimo(self, client: TestClient) -> None:
        """Triangulacion del test anterior.

        Sin esto, un handler que devolviera una constante pasaria el primero.
        """
        otro = str(uuid4())
        r = client.get(
            _RUTA,
            params={"comision_id": _COMISION},
            headers={"X-Tenant-Id": _TENANT, "X-User-Id": otro},
        )
        assert r.status_code == 200, r.text
        assert r.json()["student_pseudonym"] == otro


class TestNoDevuelve403AlAlumno:
    """Estos tests afirman MENOS de lo que su nombre sugiere. Lo declaro.

    QUE NO PUEDEN PROBAR, Y POR QUE
    ---------------------------------
    No pueden distinguir "el guard de docente no esta" de "el guard esta pero no
    corre". Lo descubri por mutacion: reapliqué el guard al handler `/me` —la
    regresion exacta que estos tests existen para prevenir— y los siete
    siguieron en verde.

    El motivo es que `assert_comision_member` arranca con
    `if not settings.enforce_comision_access or not settings.academic_db_url:
    return`. En tests no hay `academic_db_url`, asi que el guard es no-op igual
    que si estuviera apagado — y prender la flag tampoco alcanza, lo probe.

    Tampoco sirve inspeccionar el grafo de dependencias de la ruta: este
    servicio monta sus routers con un wrapper propio (`_IncludedRouter`) y las
    rutas no quedan en `app.routes` ni siquiera dentro del contexto del
    TestClient.

    QUE HACE FALTA PARA PROBARLO DE VERDAD
    ----------------------------------------
    Postgres con `usuarios_comision` poblada y `ACADEMIC_DB_URL` configurada —
    una integracion, no una unidad. El repo ya tiene ese patron en
    `apps/evaluation-service/tests/integration/`. Queda como deuda nombrada, no
    como cobertura que no existe.

    QUE SI PRUEBAN
    ----------------
    Que la ruta existe, responde 200, y que el pseudonimo sale del token. Eso
    es el contrato de identidad, que es la mitad del bug — la otra mitad (que
    el guard no se reaplique) descansa hoy en la lectura del codigo.
    """

    def test_un_alumno_con_rol_docente_heredado_NO_recibe_403(self, client: TestClient) -> None:
        """El caso exacto del reporte.

        `X-User-Roles: estudiante,docente` es lo que recibe CADA alumno real,
        porque `clerk_base_roles` reparte los dos. Contra el endpoint viejo eso
        disparaba la rama de docente y terminaba en 403 por no ser miembro de
        `usuarios_comision`. Contra `/me` no hay rama que disparar.
        """
        r = client.get(
            _RUTA,
            params={"comision_id": _COMISION},
            headers={
                "X-Tenant-Id": _TENANT,
                "X-User-Id": _USER,
                "X-User-Roles": "estudiante,docente",
            },
        )
        assert r.status_code != 403, (
            "el alumno volvio a recibir 403: el `/me` dejo de ser independiente "
            "del guard de docente"
        )
        assert r.status_code == 200, r.text

    def test_sin_rol_ninguno_tampoco(self, client: TestClient) -> None:
        r = client.get(
            _RUTA,
            params={"comision_id": _COMISION},
            headers={"X-Tenant-Id": _TENANT, "X-User-Id": _USER},
        )
        assert r.status_code == 200, r.text


class TestLaRutaMeNoSeConfundeConElPathParam:
    def test_me_no_se_interpreta_como_uuid(self, client: TestClient) -> None:
        """FastAPI matchea por orden de registro.

        Si `/student/me/...` quedara DESPUES de
        `/student/{student_pseudonym}/...`, FastAPI intentaria parsear "me"
        como UUID y devolveria **422**, no 200. Este test falla ruidosamente si
        alguien reordena las rutas — que es un cambio invisible en un diff.
        """
        r = client.get(
            _RUTA,
            params={"comision_id": _COMISION},
            headers={"X-Tenant-Id": _TENANT, "X-User-Id": _USER},
        )
        assert r.status_code != 422, (
            "FastAPI intento parsear 'me' como UUID: la ruta `/me` quedo "
            "registrada DESPUES de la ruta con path param"
        )


class TestGatesDeAutenticacion:
    def test_sin_user_id_devuelve_401(self, client: TestClient) -> None:
        """Sin `X-User-Id` no hay pseudonimo que derivar — es el gate de privacy
        de todo el patron `/me`."""
        r = client.get(
            _RUTA,
            params={"comision_id": _COMISION},
            headers={"X-Tenant-Id": _TENANT},
        )
        assert r.status_code == 401

    def test_sin_comision_id_devuelve_422(self, client: TestClient) -> None:
        """`comision_id` es obligatorio: el calculo esta acotado a una comision
        a proposito (ADR-018), no es un olvido del contrato."""
        r = client.get(
            _RUTA,
            headers={"X-Tenant-Id": _TENANT, "X-User-Id": _USER},
        )
        assert r.status_code == 422
