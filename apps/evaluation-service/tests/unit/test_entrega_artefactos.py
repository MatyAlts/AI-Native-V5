"""Tests del artefacto de la entrega (Epic 1 de `correccion-activeia`).

Cubren lo que hace corregible a una entrega: que el codigo entregado quede
persistido, que la validacion mire los ejercicios ESPERADOS y no los
presentes, que el hash guardado no se recalcule al leer, y que un docente de
otra comision reciba 404 y no 403.

Mismo estilo que el resto del repo: sesion mockeada, sin DB real (ver
`academic-service/tests/integration/test_soft_delete.py`).
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from evaluation_service.auth.dependencies import User
from evaluation_service.models.entregas import Entrega, EntregaArtefacto
from evaluation_service.routes.entregas import (
    _persistir_artefactos,
    _reconciliar_estados,
    get_entrega_artefacto,
    submit_entrega,
)
from evaluation_service.schemas.entrega import ArtefactoItem, EntregaSubmitBody
from fastapi import HTTPException

TENANT = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
COMISION = UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
EJ1 = UUID("11111111-1111-1111-1111-111111111111")
EJ2 = UUID("22222222-2222-2222-2222-222222222222")


def _estado(orden: int, ejercicio_id: UUID | None, completado: bool) -> dict:
    return {
        "ejercicio_id": str(ejercicio_id) if ejercicio_id else None,
        "orden": orden,
        "episode_id": None,
        "completado": completado,
        "completed_at": None,
    }


def _entrega(student_id: UUID, estados: list[dict]) -> Entrega:
    e = Entrega(
        id=uuid4(),
        tenant_id=TENANT,
        tarea_practica_id=uuid4(),
        student_pseudonym=student_id,
        comision_id=COMISION,
        estado="draft",
        ejercicio_estados=estados,
    )
    e.artefactos = []
    e.legacy = False
    e.artefacto_sha256 = None
    e.deleted_at = None
    e.submitted_at = None
    # `created_at` lo pone el server default; sin DB real hay que darselo o
    # `EntregaOut` rechaza el None.
    e.created_at = datetime(2026, 8, 18, tzinfo=UTC)
    return e


def _student(sid: UUID) -> User:
    return User(
        id=sid, tenant_id=TENANT, email="a@utn.edu.ar", roles=frozenset({"estudiante"}), realm="utn"
    )


def _docente(did: UUID) -> User:
    return User(
        id=did, tenant_id=TENANT, email="d@utn.edu.ar", roles=frozenset({"docente"}), realm="utn"
    )


def _res_entrega(entrega: Entrega | None) -> MagicMock:
    return MagicMock(scalar_one_or_none=MagicMock(return_value=entrega))


def _res_esperados(esperados: list[dict]) -> MagicMock:
    return MagicMock(
        all=MagicMock(return_value=[(e["orden"], e["ejercicio_id"]) for e in esperados])
    )


def _res_comision(asignado: bool) -> MagicMock:
    return MagicMock(first=MagicMock(return_value=(1,) if asignado else None))


def _res_tp_viva(viva: bool = True) -> MagicMock:
    """Respuesta de `_comision_de_la_tp`, el gate de TP borrada del submit.

    `_get_or_404(..., para_escritura=True)` lo consulta ANTES de
    `_ejercicios_esperados`: una entrega cuya TP fue borrada no puede seguir
    avanzando el ciclo (409). Devuelve la comisión de la TP, o `None` si la TP
    está borrada o no existe.
    """
    return MagicMock(first=MagicMock(return_value=(str(COMISION),) if viva else None))


def _res_artefactos(artefactos: list) -> MagicMock:
    return MagicMock(
        scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=artefactos)))
    )


def _mock_db(*responses: MagicMock):
    """Sesion que devuelve `responses` en orden, uno por `db.execute`.

    Explicita a proposito: cada test declara la secuencia exacta de queries
    que espera del endpoint, asi un cambio en el orden rompe el test en vez
    de pasar leyendo la respuesta equivocada.
    """
    db = MagicMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    db.execute = AsyncMock(side_effect=list(responses))
    return db


# ── _reconciliar_estados ──────────────────────────────────────────────────


class TestReconciliarEstados:
    def test_agrega_el_ejercicio_que_la_tp_sumo_despues(self) -> None:
        estados = [_estado(1, EJ1, completado=True)]
        esperados = [
            {"orden": 1, "ejercicio_id": str(EJ1)},
            {"orden": 2, "ejercicio_id": str(EJ2)},
        ]
        out = _reconciliar_estados(estados, esperados)
        assert len(out) == 2
        assert out[1]["orden"] == 2
        assert out[1]["completado"] is False

    def test_no_borra_un_ejercicio_que_la_tp_ya_no_declara(self) -> None:
        estados = [_estado(1, EJ1, completado=True), _estado(2, EJ2, completado=True)]
        out = _reconciliar_estados(estados, [{"orden": 1, "ejercicio_id": str(EJ1)}])
        assert len(out) == 2

    def test_sin_esperados_devuelve_los_estados_tal_cual(self) -> None:
        estados = [_estado(1, None, completado=True)]
        assert _reconciliar_estados(estados, []) == estados

    def test_no_duplica_cuando_el_estado_guardado_no_tiene_uuid(self) -> None:
        """El estado sin `ejercicio_id` es lo que escribe el PATCH cuando el
        cliente no lo manda. Buscando SOLO por UUID no se lo encontraba y se
        agregaba un SEGUNDO estado con el mismo `orden`, incompleto. Y no se
        destrababa: el PATCH siguiente matchea el primero, y el submit exige
        el segundo para siempre — la entrega quedaba inentregable.
        """
        estados = [_estado(1, None, completado=True)]
        out = _reconciliar_estados(estados, [{"orden": 1, "ejercicio_id": str(EJ1)}])
        assert len(out) == 1, f"duplico el ejercicio 1: {out}"
        assert out[0]["completado"] is True

    def test_mezcla_de_estados_con_y_sin_uuid(self) -> None:
        """Uno con UUID, uno sin, y un tercero que la TP suma ahora."""
        estados = [_estado(1, EJ1, completado=True), _estado(2, None, completado=True)]
        esperados = [
            {"orden": 1, "ejercicio_id": str(EJ1)},
            {"orden": 2, "ejercicio_id": str(EJ2)},
            {"orden": 3, "ejercicio_id": None},
        ]
        out = _reconciliar_estados(estados, esperados)
        assert sorted(e["orden"] for e in out) == [1, 2, 3]

    def test_devuelve_una_copia_propia(self) -> None:
        """El caller reasigna el resultado a la columna JSONB. Si compartiera
        los dicts con el valor cargado, SQLAlchemy no veria diferencia."""
        estados = [_estado(1, EJ1, completado=False)]
        out = _reconciliar_estados(estados, [{"orden": 1, "ejercicio_id": str(EJ1)}])
        out[0]["completado"] = True
        assert estados[0]["completado"] is False


# ── Persistencia del artefacto ────────────────────────────────────────────


class TestPersistirArtefactos:
    """Ojo: estos corren con listas Python, NO con una sesion.

    La persistencia real (que el UPDATE se emita, que el `delete-orphan` no
    choque el UNIQUE) vive en `tests/integration/test_entrega_artefactos_db.py`,
    contra Postgres. Un mock no puede ver esa clase de bug.
    """

    async def test_una_fila_por_ejercicio_con_su_sha256(self) -> None:
        entrega = _entrega(uuid4(), [_estado(1, EJ1, True), _estado(2, EJ2, True)])
        items = [
            ArtefactoItem(orden=1, ejercicio_id=EJ1, codigo="class A {}", language="java"),
            ArtefactoItem(orden=2, ejercicio_id=EJ2, codigo="class B {}", language="java"),
        ]
        await _persistir_artefactos(_mock_db(), entrega, items, entrega.ejercicio_estados, TENANT)

        assert len(entrega.artefactos) == 2
        assert entrega.artefactos[0].sha256 == hashlib.sha256(b"class A {}").hexdigest()
        assert entrega.artefactos[1].sha256 == hashlib.sha256(b"class B {}").hexdigest()
        assert entrega.artefacto_sha256 is not None

    async def test_el_hash_del_conjunto_no_depende_del_orden_de_llegada(self) -> None:
        estados = [_estado(1, EJ1, True), _estado(2, EJ2, True)]
        a = _entrega(uuid4(), estados)
        b = _entrega(uuid4(), estados)
        i1 = ArtefactoItem(orden=1, ejercicio_id=EJ1, codigo="uno")
        i2 = ArtefactoItem(orden=2, ejercicio_id=EJ2, codigo="dos")

        await _persistir_artefactos(_mock_db(), a, [i1, i2], estados, TENANT)
        await _persistir_artefactos(_mock_db(), b, [i2, i1], estados, TENANT)
        assert a.artefacto_sha256 == b.artefacto_sha256

    async def test_hereda_el_episode_id_del_estado_cuando_el_cliente_no_lo_manda(self) -> None:
        ep = uuid4()
        estados = [_estado(1, EJ1, True)]
        estados[0]["episode_id"] = str(ep)
        entrega = _entrega(uuid4(), estados)

        await _persistir_artefactos(
            _mock_db(),
            entrega,
            [ArtefactoItem(orden=1, ejercicio_id=EJ1, codigo="x")],
            estados,
            TENANT,
        )
        assert entrega.artefactos[0].episode_id == ep

    async def test_un_resubmit_reemplaza_y_no_apila(self) -> None:
        estados = [_estado(1, EJ1, True)]
        entrega = _entrega(uuid4(), estados)
        await _persistir_artefactos(
            _mock_db(),
            entrega,
            [ArtefactoItem(orden=1, ejercicio_id=EJ1, codigo="v1")],
            estados,
            TENANT,
        )
        primer_hash = entrega.artefacto_sha256

        await _persistir_artefactos(
            _mock_db(),
            entrega,
            [ArtefactoItem(orden=1, ejercicio_id=EJ1, codigo="v2")],
            estados,
            TENANT,
        )
        assert len(entrega.artefactos) == 1
        assert entrega.artefactos[0].codigo == "v2"
        assert entrega.artefacto_sha256 != primer_hash


# ── Submit ────────────────────────────────────────────────────────────────


class TestSubmit:
    async def test_persiste_una_fila_por_ejercicio(self) -> None:
        sid = uuid4()
        estados = [_estado(1, EJ1, True), _estado(2, EJ2, True)]
        entrega = _entrega(sid, estados)
        esperados = [
            {"orden": 1, "ejercicio_id": str(EJ1)},
            {"orden": 2, "ejercicio_id": str(EJ2)},
        ]
        db = _mock_db(_res_entrega(entrega), _res_tp_viva(), _res_esperados(esperados))
        body = EntregaSubmitBody(
            artefactos=[
                ArtefactoItem(orden=1, ejercicio_id=EJ1, codigo="a", language="java"),
                ArtefactoItem(orden=2, ejercicio_id=EJ2, codigo="b", language="java"),
            ]
        )

        await submit_entrega(entrega.id, body, _student(sid), db)

        assert entrega.estado == "submitted"
        assert len(entrega.artefactos) == 2

    async def test_falta_un_ejercicio_esperado_da_422(self) -> None:
        """La entrega tiene el 1 completo, pero la TP espera dos.

        Antes esto pasaba: el submit validaba `if estados:` sobre la lista
        guardada, asi que un ejercicio que no figuraba no se exigia.
        """
        sid = uuid4()
        entrega = _entrega(sid, [_estado(1, EJ1, True)])
        esperados = [
            {"orden": 1, "ejercicio_id": str(EJ1)},
            {"orden": 2, "ejercicio_id": str(EJ2)},
        ]
        db = _mock_db(_res_entrega(entrega), _res_tp_viva(), _res_esperados(esperados))

        with pytest.raises(HTTPException) as exc:
            await submit_entrega(entrega.id, EntregaSubmitBody(), _student(sid), db)
        assert exc.value.status_code == 422
        assert "[2]" in str(exc.value.detail)
        assert entrega.estado == "draft"

    async def test_falta_el_codigo_de_un_ejercicio_da_422(self) -> None:
        """Los dos ejercicios estan completos, pero el cliente solo manda el
        codigo del 1. Aceptarlo dejaria una entrega `submitted` de la que no
        se sabe que se entrego."""
        sid = uuid4()
        entrega = _entrega(sid, [_estado(1, EJ1, True), _estado(2, EJ2, True)])
        esperados = [
            {"orden": 1, "ejercicio_id": str(EJ1)},
            {"orden": 2, "ejercicio_id": str(EJ2)},
        ]
        db = _mock_db(_res_entrega(entrega), _res_tp_viva(), _res_esperados(esperados))
        body = EntregaSubmitBody(artefactos=[ArtefactoItem(orden=1, ejercicio_id=EJ1, codigo="a")])

        with pytest.raises(HTTPException) as exc:
            await submit_entrega(entrega.id, body, _student(sid), db)
        assert exc.value.status_code == 422
        assert "[2]" in str(exc.value.detail)
        assert entrega.estado == "draft"

    async def test_submit_sin_body_de_un_cliente_viejo_da_422(self) -> None:
        sid = uuid4()
        entrega = _entrega(sid, [_estado(1, EJ1, True)])
        db = _mock_db(
            _res_entrega(entrega),
            _res_tp_viva(),
            _res_esperados([{"orden": 1, "ejercicio_id": str(EJ1)}]),
        )

        with pytest.raises(HTTPException) as exc:
            await submit_entrega(entrega.id, None, _student(sid), db)
        assert exc.value.status_code == 422
        assert entrega.estado == "draft"

    async def test_tp_monolitica_entrega_sin_lista_esperada(self) -> None:
        """Sin `tp_ejercicios` no hay lista contra la cual exigir. Exigir
        sobre una lista vacia bloquearia toda entrega monolitica."""
        sid = uuid4()
        entrega = _entrega(sid, [])
        db = _mock_db(_res_entrega(entrega), _res_tp_viva(), _res_esperados([]))

        await submit_entrega(entrega.id, EntregaSubmitBody(), _student(sid), db)
        assert entrega.estado == "submitted"
        assert entrega.legacy is False

    async def test_tp_borrada_da_409_antes_de_leer_los_esperados(self) -> None:
        """El gate corta ANTES de `_ejercicios_esperados`, y por eso el
        `_mock_db` no declara esa respuesta: si el orden se invirtiera, el
        endpoint pediría una respuesta que no está y el test rompe.

        El caso real es el alumno que tenía la entrega abierta cuando el
        docente borró la TP. Sin el gate el submit pasaba y la entrega
        aparecía en la cola de corrección (`list_entregas` filtra
        `estado != "draft"`) de un trabajo práctico que ya no existe.
        """
        sid = uuid4()
        entrega = _entrega(sid, [_estado(1, EJ1, True)])
        db = _mock_db(_res_entrega(entrega), _res_tp_viva(viva=False))

        with pytest.raises(HTTPException) as exc:
            await submit_entrega(entrega.id, EntregaSubmitBody(), _student(sid), db)
        assert exc.value.status_code == 409
        assert entrega.estado == "draft"


# ── Lectura del artefacto ─────────────────────────────────────────────────


class TestGetArtefacto:
    async def test_docente_de_otra_comision_recibe_404(self) -> None:
        entrega = _entrega(uuid4(), [_estado(1, EJ1, True)])
        # `usuarios_comision` no devuelve fila → el docente no esta asignado.
        db = _mock_db(_res_entrega(entrega), _res_comision(asignado=False))

        with pytest.raises(HTTPException) as exc:
            await get_entrega_artefacto(entrega.id, _docente(uuid4()), db)
        assert exc.value.status_code == 404

    async def test_docente_de_la_comision_si_lo_lee(self) -> None:
        """El 404 de arriba tiene que ser por la comision, no porque el
        endpoint devuelva 404 siempre. Este es el control positivo."""
        entrega = _entrega(uuid4(), [_estado(1, EJ1, True)])
        db = _mock_db(_res_entrega(entrega), _res_comision(asignado=True), _res_artefactos([]))

        out = await get_entrega_artefacto(entrega.id, _docente(uuid4()), db)
        assert out.entrega_id == entrega.id

    async def test_devuelve_el_hash_guardado_sin_recalcularlo(self) -> None:
        """El hash guardado prueba que el contenido no cambio. Si se
        recalculara al leer, un cambio silencioso pasaria desapercibido y el
        hash dejaria de probar nada."""
        sid = uuid4()
        entrega = _entrega(sid, [_estado(1, EJ1, True)])
        entrega.artefacto_sha256 = "d" * 64
        entrega.artefactos = [
            EntregaArtefacto(
                id=uuid4(),
                tenant_id=TENANT,
                entrega_id=entrega.id,
                orden=1,
                episode_id=None,
                ejercicio_id=EJ1,
                codigo="lo que sea",
                language="java",
                sha256="e" * 64,
                created_at=datetime(2026, 8, 18, tzinfo=UTC),
            )
        ]
        # El owner no pasa por el gate de comision: entrega y artefactos, nada mas.
        db = _mock_db(_res_entrega(entrega), _res_artefactos(entrega.artefactos))

        out = await get_entrega_artefacto(entrega.id, _student(sid), db)
        assert out.artefacto_sha256 == "d" * 64
        assert out.artefactos[0].sha256 == "e" * 64
