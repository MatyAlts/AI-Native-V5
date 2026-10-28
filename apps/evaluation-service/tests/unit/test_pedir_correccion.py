"""Pedir corrección: devolución parcial (change publicar-nota-y-pedir-correccion).

`ordenes_a_corregir` es la única definición del alcance de una devolución
(D3): la usan el submit, el PATCH y el frontend la espeja.
"""

from __future__ import annotations

import uuid
from typing import Any

from evaluation_service.routes.entregas import ordenes_a_corregir
from evaluation_service.schemas.entrega import EjercicioEstadoSchema


def _est(orden: int, *, marca: bool | None = None) -> dict[str, Any]:
    est: dict[str, Any] = {
        "ejercicio_id": str(uuid.uuid4()),
        "orden": orden,
        "episode_id": str(uuid.uuid4()),
        "completado": True,
        "completed_at": "2026-08-20T14:03:00+00:00",
    }
    if marca is not None:
        est["reabierto_por_docente"] = marca
    return est


class TestOrdenesACorregir:
    def test_sin_marcas_son_todos(self) -> None:
        assert ordenes_a_corregir([_est(1), _est(2), _est(3)]) == {1, 2, 3}

    def test_con_marcas_son_solo_los_marcados(self) -> None:
        estados = [
            _est(1, marca=False),
            _est(2, marca=True),
            _est(3, marca=False),
            _est(4, marca=True),
        ]
        assert ordenes_a_corregir(estados) == {2, 4}

    def test_lista_vacia_es_vacio(self) -> None:
        assert ordenes_a_corregir([]) == set()

    def test_todas_las_marcas_en_false_cuentan_como_legacy(self) -> None:
        assert ordenes_a_corregir([_est(1, marca=False), _est(2, marca=False)]) == {1, 2}

    def test_none_es_vacio(self) -> None:
        assert ordenes_a_corregir(None) == set()


class TestEsquema:
    def test_un_dict_legacy_sin_la_clave_deserializa_con_false(self) -> None:
        legacy = _est(1)
        assert "reabierto_por_docente" not in legacy
        assert EjercicioEstadoSchema.model_validate(legacy).reabierto_por_docente is False

    def test_la_marca_se_conserva(self) -> None:
        assert EjercicioEstadoSchema.model_validate(_est(2, marca=True)).reabierto_por_docente


# ── 3. _reabrir_ejercicios con `ordenes` ─────────────────────────────────

import copy
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from evaluation_service.routes import entregas as entregas_mod
from evaluation_service.routes.entregas import _reabrir_ejercicios
from evaluation_service.schemas.entrega import ReturnEntregaBody
from fastapi import HTTPException


class TestReabrirSoloLosPedidos:
    def test_solo_el_pedido_se_reabre_y_se_marca(self) -> None:
        estados = [_est(1), _est(2), _est(3)]
        original = copy.deepcopy(estados)

        out = _reabrir_ejercicios(estados, [2])

        por_orden = {e["orden"]: e for e in out}
        assert por_orden[2]["completado"] is False
        assert por_orden[2]["completed_at"] is None
        assert por_orden[2]["reabierto_por_docente"] is True
        # 1 y 3: intactos salvo la marca explicita en False (D4: la marca se
        # reescribe en TODAS las filas en cada devolucion), episode_id incluido
        assert por_orden[1] == {**original[0], "reabierto_por_docente": False}
        assert por_orden[3] == {**original[2], "reabierto_por_docente": False}
        assert por_orden[2]["episode_id"] == original[1]["episode_id"]

    def test_copia_profunda_no_muta_el_original(self) -> None:
        estados = [_est(1), _est(2)]
        original = copy.deepcopy(estados)
        _reabrir_ejercicios(estados, [1])
        assert estados == original

    def test_dos_ordenes(self) -> None:
        out = _reabrir_ejercicios([_est(i) for i in range(1, 6)], [2, 4])
        assert [e["completado"] for e in out] == [True, False, True, False, True]
        assert [e["reabierto_por_docente"] for e in out] == [False, True, False, True, False]

    def test_una_devolucion_nueva_reescribe_la_marca_de_la_anterior(self) -> None:
        # Triangulacion: la marca persiste entre ciclos, asi que la segunda
        # devolucion ("solo el 3") tiene que apagar la del 2.
        primera = _reabrir_ejercicios([_est(1), _est(2), _est(3)], [2])
        for e in primera:
            e["completado"] = True  # el alumno reentrego
        segunda = _reabrir_ejercicios(primera, [3])
        assert [e["reabierto_por_docente"] for e in segunda] == [False, False, True]

    def test_sin_ordenes_reabre_todos_y_los_marca(self) -> None:
        out = _reabrir_ejercicios([_est(1), _est(2), _est(3)])
        assert [e["completado"] for e in out] == [False, False, False]
        assert all(e["reabierto_por_docente"] is True for e in out)

    def test_ordenes_none_equivale_a_sin_ordenes(self) -> None:
        out = _reabrir_ejercicios([_est(1), _est(2)], None)
        assert all(e["completado"] is False for e in out)


# ── 3.3 el endpoint ──────────────────────────────────────────────────────


class _DbFalsa:
    def __init__(self) -> None:
        self.flushes = 0

    async def flush(self) -> None:
        self.flushes += 1

    async def refresh(self, _obj: Any) -> None:
        return None


def _graded(estados: list[dict[str, Any]]) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        tarea_practica_id=uuid.uuid4(),
        student_pseudonym=uuid.uuid4(),
        comision_id=uuid.uuid4(),
        estado="graded",
        ejercicio_estados=estados,
        submitted_at=None,
        artefacto_sha256=None,
        legacy=False,
        created_at=datetime(2026, 10, 27, 12, 0, tzinfo=UTC),
        deleted_at=None,
    )


async def _devolver(
    monkeypatch: pytest.MonkeyPatch, entrega: SimpleNamespace, body: ReturnEntregaBody | None
) -> Any:
    async def _fake_get(*_a: Any, **_kw: Any) -> SimpleNamespace:
        return entrega

    async def _fake_scope(*_a: Any, **_kw: Any) -> None:
        return None

    monkeypatch.setattr(entregas_mod, "_get_or_404", _fake_get)
    monkeypatch.setattr(entregas_mod, "_assert_comision_visible", _fake_scope)
    return await entregas_mod.return_entrega(
        entrega.id,
        body,
        user=object(),  # type: ignore[arg-type]
        db=_DbFalsa(),  # type: ignore[arg-type]
    )


class TestReturnEndpoint:
    async def test_parcial_reabre_solo_el_pedido(self, monkeypatch: pytest.MonkeyPatch) -> None:
        entrega = _graded([_est(1), _est(2), _est(3)])
        salida = await _devolver(monkeypatch, entrega, ReturnEntregaBody(ordenes=[2]))
        assert salida.estado == "returned"
        assert [e["completado"] for e in salida.ejercicio_estados] == [True, False, True]
        assert [e.get("reabierto_por_docente", False) for e in salida.ejercicio_estados] == [
            False,
            True,
            False,
        ]

    async def test_sin_body_reabre_todos(self, monkeypatch: pytest.MonkeyPatch) -> None:
        entrega = _graded([_est(1), _est(2)])
        salida = await _devolver(monkeypatch, entrega, None)
        assert [e["completado"] for e in salida.ejercicio_estados] == [False, False]

    async def test_body_con_ordenes_none_reabre_todos(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        entrega = _graded([_est(1), _est(2)])
        salida = await _devolver(monkeypatch, entrega, ReturnEntregaBody())
        assert [e["completado"] for e in salida.ejercicio_estados] == [False, False]

    @pytest.mark.parametrize(
        "ordenes",
        [[], [2, 2], [9], [1, 9]],
        ids=["vacia", "duplicados", "orden_inexistente", "uno_valido_uno_inexistente"],
    )
    async def test_lista_invalida_es_422_y_la_entrega_no_cambia(
        self, monkeypatch: pytest.MonkeyPatch, ordenes: list[int]
    ) -> None:
        entrega = _graded([_est(1), _est(2), _est(3)])
        antes = copy.deepcopy(entrega.ejercicio_estados)
        with pytest.raises(HTTPException) as exc:
            await _devolver(monkeypatch, entrega, ReturnEntregaBody(ordenes=ordenes))
        assert exc.value.status_code == 422
        assert entrega.estado == "graded"
        assert entrega.ejercicio_estados == antes

    async def test_no_graded_sigue_siendo_409(self, monkeypatch: pytest.MonkeyPatch) -> None:
        entrega = _graded([_est(1)])
        entrega.estado = "submitted"
        with pytest.raises(HTTPException) as exc:
            await _devolver(monkeypatch, entrega, ReturnEntregaBody(ordenes=[1]))
        assert exc.value.status_code == 409
        assert entrega.ejercicio_estados[0]["completado"] is True

    async def test_audita_con_structlog_parcial(self, monkeypatch: pytest.MonkeyPatch) -> None:
        eventos: list[tuple[str, dict[str, Any]]] = []

        class _Log:
            def info(self, evento: str, **kw: Any) -> None:
                eventos.append((evento, kw))

        monkeypatch.setattr(entregas_mod.structlog, "get_logger", lambda *_a, **_k: _Log())
        entrega = _graded([_est(1), _est(2), _est(3)])
        await _devolver(monkeypatch, entrega, ReturnEntregaBody(ordenes=[3, 1]))
        await _devolver(monkeypatch, _graded([_est(1), _est(2)]), None)

        nombres = [n for n, _ in eventos]
        assert nombres == ["tp_correccion_pedida", "tp_correccion_pedida"]
        assert eventos[0][1]["ordenes"] == [1, 3]
        assert eventos[0][1]["parcial"] is True
        assert eventos[1][1]["ordenes"] == [1, 2]
        assert eventos[1][1]["parcial"] is False
