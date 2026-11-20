"""`_aplicar_juez_eje_fino` con el juez v2: casos de borde que la aceptación no fija."""

from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID

from classifier_service.config import settings
from classifier_service.routes import classify_ep
from classifier_service.services.regimen_llm import normalizar_regimen_llm_persistido

TENANT = UUID("00000000-0000-0000-0000-0000000000aa")


def _resultado(subgrupo: str, appropriation: str):
    return SimpleNamespace(
        appropriation=appropriation, reason="proxy", features={"subgrupo": {"key": subgrupo}}
    )


def _v2_que_falla(monkeypatch):
    async def _explota(**kw):
        raise RuntimeError("gateway caído")

    monkeypatch.setattr(settings, "eje_fino_llm_enabled", True)
    monkeypatch.setattr(settings, "eje_fino_juez_version", "v2")
    monkeypatch.setattr(classify_ep, "clasificar_regimen_v2", _explota)
    monkeypatch.setattr(classify_ep, "AIGatewayClient", lambda **kw: SimpleNamespace(complete=None))


async def test_gateway_caido_con_ex_pasiva_queda_sin_clasificar(monkeypatch):
    _v2_que_falla(monkeypatch)
    res = _resultado("dependiente_sobreuso", "delegacion_pasiva")
    await classify_ep._aplicar_juez_eje_fino(res, [], UUID(int=1), {}, TENANT)
    assert res.appropriation == "sin_clasificar"
    assert res.features["needs_review"] is True
    assert "regimen_llm" not in res.features


async def test_gateway_caido_con_colaborador_conserva_el_proxy(monkeypatch):
    _v2_que_falla(monkeypatch)
    res = _resultado("desenganchado", "apropiacion_superficial")
    await classify_ep._aplicar_juez_eje_fino(res, [], UUID(int=1), {}, TENANT)
    assert res.appropriation == "apropiacion_superficial"
    assert res.features["needs_review"] is True


async def test_flag_apagado_no_corre_ningun_juez(monkeypatch):
    _v2_que_falla(monkeypatch)
    monkeypatch.setattr(settings, "eje_fino_llm_enabled", False)
    res = _resultado("dependiente_sobreuso", "delegacion_pasiva")
    await classify_ep._aplicar_juez_eje_fino(res, [], UUID(int=1), {}, TENANT)
    assert res.appropriation == "delegacion_pasiva"
    assert "needs_review" not in res.features


def test_normalizar_registro_v2_corrupto_devuelve_el_dato_tal_cual():
    corrupto = {"juez_version": "v2", "estado": "no_existe"}
    assert normalizar_regimen_llm_persistido(corrupto) == corrupto
