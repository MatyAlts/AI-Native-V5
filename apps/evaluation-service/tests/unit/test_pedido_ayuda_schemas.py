"""Schemas de pedidos de ayuda: lo que el cliente puede mandar y lo que no."""

from __future__ import annotations

import uuid

import pytest
from evaluation_service.schemas.pedido_ayuda import PedidoAyudaContexto, PedidoAyudaCreate
from pydantic import ValidationError

TP = uuid.uuid4()


class TestCreate:
    def test_caso_minimo_tp_y_categoria(self) -> None:
        p = PedidoAyudaCreate(tarea_practica_id=TP, categoria="error_plataforma")
        assert p.episode_id is None
        assert p.ejercicio_orden is None
        assert p.mensaje is None
        assert p.contexto.pantalla is None

    def test_caso_completo(self) -> None:
        ep = uuid.uuid4()
        p = PedidoAyudaCreate(
            tarea_practica_id=TP,
            categoria="no_puedo_avanzar",
            mensaje="no entiendo el while",
            ejercicio_orden=2,
            episode_id=ep,
            entrega_id=uuid.uuid4(),
            contexto={"pantalla": "episodio", "error_visible": "x", "user_agent": "UA"},
        )
        assert p.ejercicio_orden == 2
        assert p.episode_id == ep
        assert p.contexto.pantalla == "episodio"

    @pytest.mark.parametrize(
        "cat", ["no_puedo_avanzar", "error_plataforma", "duda_consigna", "otro"]
    )
    def test_las_cuatro_categorias(self, cat: str) -> None:
        assert PedidoAyudaCreate(tarea_practica_id=TP, categoria=cat).categoria == cat

    def test_categoria_fuera_de_las_cuatro(self) -> None:
        with pytest.raises(ValidationError):
            PedidoAyudaCreate(tarea_practica_id=TP, categoria="quiero_la_respuesta")

    def test_mensaje_de_1000_pasa_y_1001_no(self) -> None:
        assert PedidoAyudaCreate(tarea_practica_id=TP, categoria="otro", mensaje="a" * 1000)
        with pytest.raises(ValidationError):
            PedidoAyudaCreate(tarea_practica_id=TP, categoria="otro", mensaje="a" * 1001)

    @pytest.mark.parametrize("orden", [0, -1])
    def test_ejercicio_orden_menor_a_1(self, orden: int) -> None:
        with pytest.raises(ValidationError):
            PedidoAyudaCreate(tarea_practica_id=TP, categoria="otro", ejercicio_orden=orden)

    def test_el_body_no_acepta_comision_ni_estado(self) -> None:
        """La comision la deriva el servidor; el estado nace pendiente."""
        with pytest.raises(ValidationError):
            PedidoAyudaCreate(tarea_practica_id=TP, categoria="otro", comision_id=uuid.uuid4())
        with pytest.raises(ValidationError):
            PedidoAyudaCreate(tarea_practica_id=TP, categoria="otro", estado="resuelto")

    def test_mensaje_en_blanco_se_guarda_como_none(self) -> None:
        p = PedidoAyudaCreate(tarea_practica_id=TP, categoria="otro", mensaje="   ")
        assert p.mensaje is None


class TestContexto:
    def test_clave_no_permitida(self) -> None:
        with pytest.raises(ValidationError):
            PedidoAyudaContexto(codigo="print(1)")

    def test_error_visible_300_pasa_301_no(self) -> None:
        assert PedidoAyudaContexto(error_visible="e" * 300)
        with pytest.raises(ValidationError):
            PedidoAyudaContexto(error_visible="e" * 301)

    def test_pantalla_invalida(self) -> None:
        with pytest.raises(ValidationError):
            PedidoAyudaContexto(pantalla="login")

    def test_user_agent_largo(self) -> None:
        with pytest.raises(ValidationError):
            PedidoAyudaContexto(user_agent="u" * 301)
