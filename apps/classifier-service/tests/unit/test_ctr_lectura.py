"""Cliente de lectura del CTR con cuenta de servicio propia (tarea 6.3, design D4).

Se prueba contra `httpx.MockTransport` (el repo no usa `respx`): headers de
identidad de la cuenta de servicio, firma del gateway cuando hay secreto,
timeout de 15 s y traducción de errores a excepciones propias, sin reenviar
el cuerpo del error.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import httpx
import pytest
from classifier_service.services.ctr_lectura import (
    ESTUDIO_LECTOR_SERVICE_USER_ID,
    CTRLector,
    CTRNoDisponibleError,
    EpisodioInexistenteError,
)
from platform_observability import verify_gateway_signature

TENANT = UUID("00000000-0000-4000-8000-0000000000aa")


def _lector(handler, secreto: str = "") -> tuple[CTRLector, list[httpx.Request]]:
    pedidos: list[httpx.Request] = []

    def registrar(request: httpx.Request) -> httpx.Response:
        pedidos.append(request)
        return handler(request)

    return CTRLector(
        "http://ctr", secreto=secreto, transport=httpx.MockTransport(registrar)
    ), pedidos


def test_cuenta_de_servicio_propia_y_no_reusada() -> None:
    assert ESTUDIO_LECTOR_SERVICE_USER_ID not in {
        UUID("00000000-0000-0000-0000-000000000010"),  # tutor-service
        UUID("00000000-0000-0000-0000-000000000000"),
        UUID("00000000-0000-0000-0000-000000000001"),
        UUID("00000000-0000-0000-0000-000000000002"),
    }


async def test_pide_el_episodio_con_identidad_de_servicio_y_sin_firma_si_no_hay_secreto() -> None:
    episodio = uuid4()
    datos = {**_episodio_valido(), "id": str(episodio)}
    lector, pedidos = _lector(lambda r: httpx.Response(200, json=datos))
    respuesta = await lector.episodio(TENANT, episodio)
    assert respuesta == datos
    (pedido,) = pedidos
    assert pedido.method == "GET"
    assert str(pedido.url) == f"http://ctr/api/v1/episodes/{episodio}"
    assert pedido.headers["X-User-Id"] == str(ESTUDIO_LECTOR_SERVICE_USER_ID)
    assert pedido.headers["X-Tenant-Id"] == str(TENANT)
    assert pedido.headers["X-User-Roles"] == "classifier_worker"
    assert pedido.headers["X-User-Email"]
    assert "X-Gateway-Signature" not in pedido.headers


async def test_firma_los_headers_cuando_hay_secreto() -> None:
    lector, pedidos = _lector(
        lambda r: httpx.Response(200, json=_episodio_valido()), secreto="s3creto"
    )
    await lector.episodio(TENANT, uuid4())
    assert len(pedidos) == 1
    h = pedidos[0].headers
    assert verify_gateway_signature(
        "s3creto",
        h["X-User-Id"],
        h["X-Tenant-Id"],
        h["X-User-Roles"],
        h["X-Gateway-Ts"],
        h["X-Gateway-Signature"],
    )
    assert not verify_gateway_signature(
        "otro",
        h["X-User-Id"],
        h["X-Tenant-Id"],
        h["X-User-Roles"],
        h["X-Gateway-Ts"],
        h["X-Gateway-Signature"],
    )


async def test_404_es_episodio_inexistente() -> None:
    lector, _ = _lector(lambda r: httpx.Response(404, json={"detail": "no"}))
    with pytest.raises(EpisodioInexistenteError):
        await lector.episodio(TENANT, uuid4())


@pytest.mark.parametrize("status", [403, 500, 503])
async def test_otros_errores_son_ctr_no_disponible_sin_el_cuerpo(status: int) -> None:
    lector, _ = _lector(lambda r: httpx.Response(status, text="traza interna con datos"))
    with pytest.raises(CTRNoDisponibleError) as exc:
        await lector.episodio(TENANT, uuid4())
    assert "traza interna" not in str(exc.value)


async def test_timeout_es_ctr_no_disponible() -> None:
    def lento(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("lento", request=request)

    lector, _ = _lector(lento)
    with pytest.raises(CTRNoDisponibleError):
        await lector.episodio(TENANT, uuid4())


def test_timeout_de_15_segundos() -> None:
    assert CTRLector("http://ctr").timeout == 15.0


# ── 200 con cuerpo no JSON o con forma inesperada (verify-1, F6) ─────────────


def _episodio_valido() -> dict:
    return {
        "id": str(uuid4()),
        "estado": "closed",
        "problema_id": str(uuid4()),
        "events_count": 1,
        "last_chain_hash": "a" * 64,
        "integrity_compromised": False,
        "events": [
            {
                "seq": 0,
                "event_type": "episodio_abierto",
                "ts": "2026-09-01T10:00:00Z",
                "chain_hash": "a" * 64,
                "payload": {"language": "python", "ejercicio_id": None},
            }
        ],
    }


def _sin(clave: str) -> dict:
    datos = _episodio_valido()
    del datos[clave]
    return datos


def _evento_con(**cambios) -> dict:
    datos = _episodio_valido()
    datos["events"][0].update(cambios)
    return datos


async def test_200_con_la_forma_del_contrato_se_devuelve() -> None:
    datos = _episodio_valido()
    lector, _ = _lector(lambda r: httpx.Response(200, json=datos))
    assert await lector.episodio(TENANT, uuid4()) == datos


async def test_200_con_cuerpo_no_json_es_ctr_no_disponible_sin_el_cuerpo() -> None:
    lector, _ = _lector(lambda r: httpx.Response(200, text="<html>proxy con datos</html>"))
    tipo, mensaje = None, ""
    try:
        await lector.episodio(TENANT, uuid4())
    except Exception as exc:  # el tipo es lo que se afirma
        tipo, mensaje = type(exc), str(exc)
    assert tipo is CTRNoDisponibleError
    assert "proxy" not in mensaje


@pytest.mark.parametrize(
    "cuerpo",
    [
        [1, 2],
        "texto",
        None,
        _sin("events"),
        _sin("estado"),
        _sin("events_count"),
        _sin("last_chain_hash"),
        _sin("problema_id"),
        {**_episodio_valido(), "events": {"0": {}}},
        {**_episodio_valido(), "events": ["evento"]},
        _evento_con(seq="0"),
        _evento_con(seq=True),
        _evento_con(event_type=None),
        _evento_con(chain_hash=7),
        _evento_con(payload=["x"]),
    ],
)
async def test_200_con_forma_inesperada_es_ctr_no_disponible(cuerpo) -> None:
    lector, _ = _lector(lambda r: httpx.Response(200, json=cuerpo))
    tipo = None
    try:
        await lector.episodio(TENANT, uuid4())
    except Exception as exc:
        tipo = type(exc)
    assert tipo is CTRNoDisponibleError


# ── Formato de los campos que se parsean (verify-2, N2) ──────────────────────


def _evento_sin(clave: str) -> dict:
    datos = _episodio_valido()
    del datos["events"][0][clave]
    return datos


def _con_lectura(duracion) -> dict:
    datos = _episodio_valido()
    datos["events"].append(
        {
            "seq": 1,
            "event_type": "lectura_enunciado",
            "ts": "2026-09-01T10:00:05+00:00",
            "chain_hash": "b" * 64,
            "payload": {"duration_seconds": duracion},
        }
    )
    return datos


@pytest.mark.parametrize(
    "cuerpo",
    [
        _evento_sin("ts"),
        _evento_con(ts=None),
        _evento_con(ts="ayer"),
        _evento_con(ts=12),
        _evento_con(ts="2026-09-01T10:00:00"),  # sin zona: no se puede restar a uno con zona
        {**_episodio_valido(), "problema_id": "no-uuid"},
        {**_episodio_valido(), "problema_id": 7},
        _evento_con(payload={"ejercicio_id": "zz"}),
        _evento_con(payload={"ejercicio_id": 5}),
        {**_episodio_valido(), "integrity_compromised": "no"},
        _con_lectura("5"),
        _con_lectura(True),
    ],
)
async def test_200_con_campos_que_no_se_pueden_parsear_es_ctr_no_disponible(cuerpo) -> None:
    lector, _ = _lector(lambda r: httpx.Response(200, json=cuerpo))
    tipo = None
    try:
        await lector.episodio(TENANT, uuid4())
    except Exception as exc:
        tipo = type(exc)
    assert tipo is CTRNoDisponibleError


@pytest.mark.parametrize(
    "cuerpo",
    [
        _evento_con(ts="2026-09-01T10:00:00.123456+00:00"),
        _evento_con(payload={"ejercicio_id": str(uuid4()), "language": "python"}),
        _con_lectura(12.5),
        _con_lectura(None),
    ],
)
async def test_200_con_variantes_validas_del_contrato_se_acepta(cuerpo) -> None:
    lector, _ = _lector(lambda r: httpx.Response(200, json=cuerpo))
    assert await lector.episodio(TENANT, uuid4()) == cuerpo
