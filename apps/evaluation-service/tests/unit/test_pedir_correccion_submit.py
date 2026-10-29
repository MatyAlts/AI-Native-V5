"""Re-entrega y PATCH tras una devolución PARCIAL ("Pedir corrección").

Change publicar-nota-y-pedir-correccion, D4 y D5. Sesión mockeada, sin DB
(mismo estilo que `test_entrega_artefactos.py`): la secuencia de queries que el
endpoint hace es parte de lo que se declara.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from evaluation_service.auth.dependencies import User
from evaluation_service.models.entregas import Entrega, EntregaArtefacto
from evaluation_service.routes.entregas import mark_ejercicio_completado, submit_entrega
from evaluation_service.schemas.entrega import ArtefactoItem, EntregaSubmitBody, MarkEjercicioBody
from fastapi import HTTPException

TENANT = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
COMISION = UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
EJ = {
    1: UUID("11111111-1111-1111-1111-111111111111"),
    2: UUID("22222222-2222-2222-2222-222222222222"),
    3: UUID("33333333-3333-3333-3333-333333333333"),
}
EP = {o: uuid4() for o in (1, 2, 3)}


def _sha(codigo: str) -> str:
    return hashlib.sha256(codigo.encode()).hexdigest()


def _estado(orden: int, *, completado: bool = True, marca: bool | None = None) -> dict[str, Any]:
    est: dict[str, Any] = {
        "ejercicio_id": str(EJ[orden]),
        "orden": orden,
        "episode_id": str(EP[orden]),
        "completado": completado,
        "completed_at": "2026-10-20T14:00:00+00:00" if completado else None,
    }
    if marca is not None:
        est["reabierto_por_docente"] = marca
    return est


def _artefacto(orden: int, codigo: str) -> EntregaArtefacto:
    return EntregaArtefacto(
        id=uuid4(),
        tenant_id=TENANT,
        orden=orden,
        episode_id=EP[orden],
        ejercicio_id=EJ[orden],
        codigo=codigo,
        language="python",
        sha256=_sha(codigo),
    )


def _returned(estados: list[dict[str, Any]], artefactos: list[EntregaArtefacto]) -> Entrega:
    e = Entrega(
        id=uuid4(),
        tenant_id=TENANT,
        tarea_practica_id=uuid4(),
        student_pseudonym=uuid4(),
        comision_id=COMISION,
        estado="returned",
        ejercicio_estados=estados,
    )
    e.artefactos = list(artefactos)
    e.legacy = False
    e.artefacto_sha256 = "viejo"
    e.deleted_at = None
    e.submitted_at = None
    e.created_at = datetime(2026, 10, 1, tzinfo=UTC)
    return e


def _student(entrega: Entrega) -> User:
    return User(
        id=entrega.student_pseudonym,
        tenant_id=TENANT,
        email="a@utn.edu.ar",
        roles=frozenset({"estudiante"}),
        realm="utn",
    )


def _res(entrega: Entrega) -> MagicMock:
    return MagicMock(scalar_one_or_none=MagicMock(return_value=entrega))


def _esperados(ordenes: list[int]) -> MagicMock:
    return MagicMock(all=MagicMock(return_value=[(o, str(EJ[o])) for o in ordenes]))


def _tp_viva() -> MagicMock:
    return MagicMock(first=MagicMock(return_value=(str(COMISION),)))


def _db(*responses: MagicMock) -> MagicMock:
    db = MagicMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    db.execute = AsyncMock(side_effect=list(responses))
    return db


def _previos() -> list[EntregaArtefacto]:
    return [_artefacto(1, "print(1)"), _artefacto(2, "print(2)"), _artefacto(3, "print(3)")]


def _por_orden(entrega: Entrega) -> dict[int, EntregaArtefacto]:
    return {a.orden: a for a in entrega.artefactos}


def _hash_conjunto(entrega: Entrega) -> str:
    canonical = "|".join(f"{a.orden}:{a.sha256}" for a in entrega.artefactos)
    return hashlib.sha256(canonical.encode()).hexdigest()


def _item(orden: int, codigo: str) -> ArtefactoItem:
    return ArtefactoItem(orden=orden, ejercicio_id=EJ[orden], codigo=codigo)


async def _submit(entrega: Entrega, items: list[ArtefactoItem], ordenes: list[int]) -> Any:
    db = _db(_res(entrega), _tp_viva(), _esperados(ordenes))
    body = EntregaSubmitBody(artefactos=items)
    return await submit_entrega(entrega.id, body, _student(entrega), db)


def _parcial_en_el_2() -> Entrega:
    estados = [
        _estado(1, marca=False),
        _estado(2, completado=True, marca=True),  # el alumno ya lo rehizo y cerró
        _estado(3, marca=False),
    ]
    return _returned(estados, _previos())


class TestSubmitDeUnaDevolucionParcial:
    async def test_alcanza_con_mandar_el_codigo_del_reabierto(self) -> None:
        entrega = _parcial_en_el_2()
        previos = {a.orden: (a.codigo, a.sha256, a.episode_id) for a in _previos()}
        # `_previos()` genera ids distintos pero el episode_id sale de EP: comparable.

        await _submit(entrega, [_item(2, "print(22)")], [1, 2, 3])

        assert entrega.estado == "submitted"
        art = _por_orden(entrega)
        assert art[2].codigo == "print(22)"
        for o in (1, 3):
            assert (art[o].codigo, art[o].sha256, art[o].episode_id) == previos[o]
        assert entrega.artefacto_sha256 == _hash_conjunto(entrega)
        assert entrega.artefacto_sha256 != "viejo"

    async def test_las_marcas_sobreviven_al_submit(self) -> None:
        # D4: la lista del docente muestra "Correccion pedida: ej. 2" sobre la
        # re-entrega, asi que el submit NO borra la marca; la reescribe la
        # proxima devolucion.
        entrega = _parcial_en_el_2()
        await _submit(entrega, [_item(2, "print(22)")], [1, 2, 3])
        marcas = {e["orden"]: e.get("reabierto_por_docente") for e in entrega.ejercicio_estados}
        assert marcas == {1: False, 2: True, 3: False}

    async def test_submit_sin_marcas_no_inventa_ninguna(self) -> None:
        # Triangulacion: una entrega legacy (sin la clave) sigue sin ella.
        entrega = _parcial_en_el_2()
        for e in entrega.ejercicio_estados:
            e.pop("reabierto_por_docente", None)
        await _submit(
            entrega, [_item(1, "print(1)"), _item(2, "x"), _item(3, "print(3)")], [1, 2, 3]
        )
        assert not any("reabierto_por_docente" in e for e in entrega.ejercicio_estados)

    async def test_codigo_distinto_para_lo_no_reabierto_se_ignora(self) -> None:
        entrega = _parcial_en_el_2()
        await _submit(
            entrega,
            [_item(1, "HACK"), _item(2, "print(22)"), _item(3, "HACK")],
            [1, 2, 3],
        )
        art = _por_orden(entrega)
        assert (art[1].codigo, art[3].codigo) == ("print(1)", "print(3)")
        assert art[2].codigo == "print(22)"

    async def test_falta_el_codigo_del_reabierto_sigue_siendo_422(self) -> None:
        entrega = _parcial_en_el_2()
        with pytest.raises(HTTPException) as exc:
            await _submit(entrega, [], [1, 2, 3])
        assert exc.value.status_code == 422
        assert "[2]" in str(exc.value.detail)
        assert entrega.estado == "returned"

    async def test_devolucion_legacy_sin_marcas_exige_todos(self) -> None:
        estados = [_estado(1), _estado(2), _estado(3)]  # sin la clave
        entrega = _returned(estados, _previos())
        with pytest.raises(HTTPException) as exc:
            await _submit(entrega, [_item(2, "print(22)")], [1, 2, 3])
        assert exc.value.status_code == 422
        assert "[1, 3]" in str(exc.value.detail)

    async def test_legacy_sin_marcas_con_todos_reemplaza_todo(self) -> None:
        estados = [_estado(1), _estado(2), _estado(3)]
        entrega = _returned(estados, _previos())
        await _submit(entrega, [_item(1, "a"), _item(2, "b"), _item(3, "c")], [1, 2, 3])
        assert [a.codigo for a in entrega.artefactos] == ["a", "b", "c"]

    async def test_sin_artefacto_previo_de_un_no_reabierto_se_le_exige_al_cliente(self) -> None:
        estados = [_estado(1, marca=False), _estado(2, marca=True), _estado(3, marca=False)]
        entrega = _returned(estados, [])
        with pytest.raises(HTTPException) as exc:
            await _submit(entrega, [_item(2, "print(22)")], [1, 2, 3])
        assert exc.value.status_code == 422
        assert "[1, 3]" in str(exc.value.detail)

    async def test_sin_artefacto_previo_pero_el_cliente_lo_manda_se_acepta(self) -> None:
        estados = [_estado(1, marca=False), _estado(2, marca=True), _estado(3, marca=False)]
        entrega = _returned(estados, [])
        await _submit(entrega, [_item(1, "a"), _item(2, "b"), _item(3, "c")], [1, 2, 3])
        assert [a.codigo for a in entrega.artefactos] == ["a", "b", "c"]

    async def test_orden_sobrante_sigue_rechazado(self) -> None:
        entrega = _parcial_en_el_2()
        with pytest.raises(HTTPException) as exc:
            await _submit(entrega, [_item(2, "x"), ArtefactoItem(orden=9, codigo="y")], [1, 2, 3])
        assert exc.value.status_code == 422


# ── PATCH ────────────────────────────────────────────────────────────────


async def _patch(entrega: Entrega, orden: int, completado: bool) -> Any:
    db = _db(_res(entrega), _tp_viva())
    return await mark_ejercicio_completado(
        entrega.id,
        orden,
        MarkEjercicioBody(completado=completado, ejercicio_id=EJ[orden]),
        _student(entrega),
        db,
    )


def _devuelta_parcial_en_el_2() -> Entrega:
    estados = [
        _estado(1, marca=False),
        _estado(2, completado=False, marca=True),
        _estado(3, marca=False),
    ]
    return _returned(estados, _previos())


class TestPatchTrasDevolucionParcial:
    @pytest.mark.parametrize("completado", [False, True], ids=["desmarcar", "marcar"])
    async def test_sobre_un_no_reabierto_es_409_y_no_cambia_nada(self, completado: bool) -> None:
        entrega = _devuelta_parcial_en_el_2()
        antes = [dict(e) for e in entrega.ejercicio_estados]
        with pytest.raises(HTTPException) as exc:
            await _patch(entrega, 1, completado)
        assert exc.value.status_code == 409
        assert entrega.ejercicio_estados == antes

    async def test_sobre_el_reabierto_funciona_como_antes(self) -> None:
        entrega = _devuelta_parcial_en_el_2()
        nuevo_episodio = uuid4()
        db = _db(_res(entrega), _tp_viva())
        salida = await mark_ejercicio_completado(
            entrega.id,
            2,
            MarkEjercicioBody(completado=True, ejercicio_id=EJ[2], episode_id=nuevo_episodio),
            _student(entrega),
            db,
        )
        e2 = next(e for e in salida.ejercicio_estados if e["orden"] == 2)
        assert e2["completado"] is True
        assert e2["episode_id"] == str(nuevo_episodio)

    async def test_en_draft_nada_cambia(self) -> None:
        entrega = _devuelta_parcial_en_el_2()
        entrega.estado = "draft"
        salida = await _patch(entrega, 1, False)
        assert next(e for e in salida.ejercicio_estados if e["orden"] == 1)["completado"] is False

    async def test_devolucion_legacy_sin_marcas_deja_tocar_cualquiera(self) -> None:
        entrega = _returned(
            [_estado(1, completado=False), _estado(2, completado=False)], _previos()
        )
        salida = await _patch(entrega, 1, True)
        assert next(e for e in salida.ejercicio_estados if e["orden"] == 1)["completado"] is True


# ── Ciclo completo (4.5) ─────────────────────────────────────────────────


class TestCicloCompletoConRecalificacion:
    async def test_pedir_reentregar_recalificar_y_pedir_otro(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from evaluation_service.routes import entregas as mod
        from evaluation_service.schemas.entrega import ReturnEntregaBody

        entrega = _returned([_estado(1), _estado(2), _estado(3)], _previos())
        entrega.estado = "graded"

        async def _get(*_a: Any, **_k: Any) -> Entrega:
            return entrega

        async def _scope(*_a: Any, **_k: Any) -> None:
            return None

        monkeypatch.setattr(mod, "_get_or_404", _get)
        monkeypatch.setattr(mod, "_assert_comision_visible", _scope)

        # 1) pedir corrección del 2
        await mod.return_entrega(
            entrega.id,
            ReturnEntregaBody(ordenes=[2]),
            user=object(),
            db=_db(),  # type: ignore[arg-type]
        )
        assert entrega.estado == "returned"
        assert [e["completado"] for e in entrega.ejercicio_estados] == [True, False, True]

        # 2) el alumno rehace el 2 y re-entrega; solo manda el 2
        nuevo_ep = uuid4()
        await mod.mark_ejercicio_completado(
            entrega.id,
            2,
            MarkEjercicioBody(completado=True, ejercicio_id=EJ[2], episode_id=nuevo_ep),
            _student(entrega),
            _db(_tp_viva()),
        )
        await mod.submit_entrega(
            entrega.id,
            EntregaSubmitBody(artefactos=[_item(2, "print(22)")]),
            _student(entrega),
            _db(_tp_viva(), _esperados([1, 2, 3])),
        )
        assert entrega.estado == "submitted"
        assert [a.codigo for a in entrega.artefactos] == ["print(1)", "print(22)", "print(3)"]

        # 3) re-calificación (PR #124 deja la entrega en `graded`) y 4) otro pedido
        entrega.estado = "graded"
        await mod.return_entrega(
            entrega.id,
            ReturnEntregaBody(ordenes=[3]),
            user=object(),
            db=_db(),  # type: ignore[arg-type]
        )
        por_orden = {e["orden"]: e for e in entrega.ejercicio_estados}
        assert [por_orden[o]["completado"] for o in (1, 2, 3)] == [True, True, False]
        assert por_orden[2]["reabierto_por_docente"] is False
        assert por_orden[3]["reabierto_por_docente"] is True
