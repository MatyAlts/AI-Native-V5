"""El alumno ve sus entregas aunque llegue con el rol `docente` heredado.

EL BUG (2026-10-02, en produccion)
------------------------------------
Un alumno abria "Mis notas" y leia *"todavia no entregaste nada"* teniendo una
entrega corregida con nota 5, feedback del docente y criterios cargados.

`GET /api/v1/entregas?comision_id=...` devolvia `{"data": []}`. **Sin error**:
el frontend no tenia nada que mostrar distinto de un vacio legitimo, asi que
le dijo al alumno que no habia entregado. Una mentira tranquila, que es peor
que un error — un error se reporta.

LA CAUSA
----------
`clerk_base_roles` reparte `"estudiante,docente"` a TODO usuario logueado
(`api-gateway/config.py:112`). Un alumno real llega entonces con rol `docente`,
`list_entregas` lo tomaba por staff, buscaba las comisiones donde es profe en
`usuarios_comision` —tabla donde los alumnos no estan, porque viven en
`inscripciones`—, no encontraba ninguna, y hacia un `return` temprano con la
lista vacia. Nunca llegaba al filtro `student_pseudonym == user.id`.

POR QUE NINGUN TEST LO VIO
----------------------------
Porque los tests del alumno usan `alumno_de(key)`, que arma los headers con el
rol `"estudiante"` **solo**. Esa identidad no existe en este deploy: ningun
alumno real llega asi.

El repo ya habia aprendido esta leccion para el docente —la fixture expone
`docente_prod` con los dos roles, y `tests/unit/test_scope_con_roles_de_produccion.py`
dice textual que "un test de autorizacion con un usuario de UN solo rol no
prueba nada en este deploy"— pero la contraparte del alumno quedo sin cubrir.

Este archivo la cubre.

LO QUE NO ARREGLA
-------------------
La raiz. El rol sigue mintiendo para todos, y el mismo defecto produjo hoy un
403 en `cii-evolution-longitudinal` y, segun
`docs/RUNBOOK-DEPLOY-2026-08-28.md`, abre de mas en
`GET /api/v1/audit/episodes/{id}`. Arreglarlo de verdad pide que el gateway
derive el rol de las tablas, y el api-gateway hoy **no se conecta a ninguna
base**: es un cambio de arquitectura, no un parche.
"""

from __future__ import annotations

from evaluation_service.main import app
from httpx import ASGITransport, AsyncClient

ROLES_DE_PRODUCCION = "estudiante,docente"


def _headers_de_produccion(scope_setup: dict, key: str) -> dict[str, str]:
    """Los headers del dueño de `key`, con los roles que el gateway emite.

    `alumno_de(key)` arma `"estudiante"` a secas — una identidad que no existe
    en este deploy. Se reusa su `X-User-Id` y se reconstruyen los headers con
    los dos roles.
    """
    uid = scope_setup["alumno_de"](key)["X-User-Id"]
    return scope_setup["headers"](uid, ROLES_DE_PRODUCCION)


async def _listar(headers: dict[str, str], **params: str) -> dict:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/api/v1/entregas", headers=headers, params=params)
    assert r.status_code == 200, r.text
    return r.json()


class TestElAlumnoVeLoSuyo:
    async def test_ve_su_entrega_corregida(self, scope_setup: dict) -> None:
        """El caso exacto del reporte: entrega con nota, y la pantalla vacia."""
        body = await _listar(
            _headers_de_produccion(scope_setup, "propia_returned"),
            comision_id=str(scope_setup["comision_propia"]),
        )
        ids = {e["id"] for e in body["data"]}
        assert str(scope_setup["propia_returned"]) in ids, (
            "el alumno no ve su propia entrega corregida: el rol `docente` "
            "heredado lo volvio a mandar por la rama de staff"
        )

    async def test_con_el_rol_de_un_solo_valor_tambien(self, scope_setup: dict) -> None:
        """Triangulacion con la identidad vieja.

        Si este pasa y el de arriba falla, el problema es exclusivamente el rol
        heredado. Si fallan los dos, el bug es otro y este archivo esta mirando
        el lugar equivocado.
        """
        body = await _listar(
            scope_setup["alumno_de"]("propia_returned"),
            comision_id=str(scope_setup["comision_propia"]),
        )
        ids = {e["id"] for e in body["data"]}
        assert str(scope_setup["propia_returned"]) in ids

    async def test_ve_su_propio_draft(self, scope_setup: dict) -> None:
        """La rama del alumno muestra su borrador; la de docente lo oculta.

        Importa para el arreglo elegido: se degrada `is_docente` ANTES de la
        bifurcacion, asi el caller entra por la rama del alumno COMPLETA. Un
        parche dentro de la rama de staff habria arreglado la lista y dejado al
        alumno sin ver su propio trabajo en curso.
        """
        body = await _listar(
            _headers_de_produccion(scope_setup, "propia_draft"),
            comision_id=str(scope_setup["comision_propia"]),
        )
        ids = {e["id"] for e in body["data"]}
        assert str(scope_setup["propia_draft"]) in ids, (
            "el alumno no ve su propio draft: se degrado el rol DENTRO de la "
            "rama de staff en vez de antes, y heredo su semantica"
        )

    async def test_sin_filtro_de_comision_tambien(self, scope_setup: dict) -> None:
        """`comision_id` es opcional: sin el, ve todas las suyas."""
        body = await _listar(_headers_de_produccion(scope_setup, "propia_returned"))
        ids = {e["id"] for e in body["data"]}
        assert str(scope_setup["propia_returned"]) in ids


class TestNoVeLoAjeno:
    """La mitad que hace que el arreglo sea un arreglo y no un agujero."""

    async def test_no_ve_entregas_de_otro_alumno(self, scope_setup: dict) -> None:
        """El dueño de `propia_returned` no ve las entregas de la comision ajena.

        Son de otro alumno. Si el fix hubiera ampliado el scope en vez de
        acotarlo, apareceria aca.
        """
        body = await _listar(_headers_de_produccion(scope_setup, "propia_returned"))
        ids = {e["id"] for e in body["data"]}
        for ajena in ("ajena_submitted", "ajena_returned", "ajena_graded"):
            assert str(scope_setup[ajena]) not in ids, (
                f"el alumno ve {ajena}, que es de otro alumno y de otra comision"
            )

    async def test_el_parametro_student_pseudonym_no_le_sirve_para_espiar(
        self, scope_setup: dict
    ) -> None:
        """Pedir las entregas de otro no devuelve las de otro.

        `list_entregas` acepta `student_pseudonym` como filtro —lo usa el
        docente—, asi que el camino de ataque obvio para un alumno con el rol
        heredado es pasarlo apuntando a un companero.
        """
        otro = scope_setup["alumno_de"]("ajena_graded")["X-User-Id"]
        body = await _listar(
            _headers_de_produccion(scope_setup, "propia_returned"),
            student_pseudonym=otro,
        )
        ids = {e["id"] for e in body["data"]}
        assert str(scope_setup["ajena_graded"]) not in ids, (
            "FUGA: un alumno leyo la entrega de otro pasando su pseudonimo"
        )


class TestElDocenteRealNoSeRompe:
    async def test_sigue_viendo_su_comision(self, scope_setup: dict) -> None:
        """Con comisiones asignadas, el rol `docente` sigue siendo efectivo.

        Es la otra mitad del riesgo: degradar el rol de mas dejaria a los
        docentes reales sin su cola de correccion.
        """
        body = await _listar(
            scope_setup["docente_prod"],
            comision_id=str(scope_setup["comision_propia"]),
        )
        ids = {e["id"] for e in body["data"]}
        assert str(scope_setup["propia_returned"]) in ids, (
            "el docente real perdio su cola de correccion"
        )

    async def test_sigue_sin_ver_la_comision_ajena(self, scope_setup: dict) -> None:
        body = await _listar(scope_setup["docente_prod"])
        ids = {e["id"] for e in body["data"]}
        assert str(scope_setup["ajena_graded"]) not in ids, (
            "el aislamiento por comision del docente se rompio"
        )
