"""Carga de la muestra y orden por codificador (tareas 7.1 y 7.2, design D4b, D6, D7).

App real + Postgres real + CTR falso. Los CSV son sintéticos, generados acá
(nunca la muestra real del paper).
"""

from __future__ import annotations

import hashlib
import time
from uuid import UUID, uuid4

import pytest


def _sd(r) -> tuple[int, object]:
    """Status y `detail` sin romper si la respuesta no es JSON o no trae detail:
    así un 200 o un 500 inesperado falla por aserción y no por KeyError."""
    try:
        cuerpo = r.json()
    except ValueError:
        cuerpo = None
    return r.status_code, cuerpo.get("detail") if isinstance(cuerpo, dict) else cuerpo


def _sha(texto: str) -> str:
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


async def _contar_items(estudio) -> int:
    return (await estudio.sql("SELECT count(*) AS n FROM estudio_muestra"))[0]["n"]


def _cinco(estudio) -> list[UUID]:
    ctr = estudio.ctr
    return [
        ctr.agregar(),
        ctr.agregar(ejercicio_id=uuid4()),
        ctr.agregar(estado="paused", cierre="episodio_abandonado"),
        ctr.agregar(),
        ctr.agregar(ejercicio_id=uuid4()),
    ]


async def test_carga_valida_guarda_solo_episode_id_y_evidencia_fija(estudio_http) -> None:
    episodios = _cinco(estudio_http)
    csv = estudio_http.csv_muestra(episodios)
    r = await estudio_http.cargar_muestra(episodios, sha256_esperado=_sha(csv))
    assert r.status_code == 200, r.text
    assert r.json() == {"items": 5, "sha256": _sha(csv)}

    filas = await estudio_http.sql(
        "SELECT episode_id, seq_tope, chain_hash_tope, events_count_carga, last_chain_hash_carga, "
        "estado_carga, problema_id, ejercicio_id FROM estudio_muestra"
    )
    por_episodio = {f["episode_id"]: f for f in filas}
    assert set(por_episodio) == set(episodios)
    for ep in episodios:
        datos = estudio_http.ctr.episodios[ep]
        ejercicio = datos["events"][0]["payload"]["ejercicio_id"]
        assert dict(por_episodio[ep]) == {
            "episode_id": ep,
            "seq_tope": datos["events"][-1]["seq"],
            "chain_hash_tope": datos["events"][-1]["chain_hash"],
            "events_count_carga": datos["events_count"],
            "last_chain_hash_carga": datos["last_chain_hash"],
            "estado_carga": datos["estado"],
            "problema_id": UUID(datos["problema_id"]),
            "ejercicio_id": UUID(ejercicio) if ejercicio else None,
        }
    assert sum(1 for f in filas if f["ejercicio_id"] is None) == 3

    estudio_fila = await estudio_http.sql(
        "SELECT muestra_sha256, muestra_cargada_at FROM estudio_codificacion"
    )
    assert estudio_fila[0]["muestra_sha256"] == _sha(csv)
    assert estudio_fila[0]["muestra_cargada_at"] is not None

    tablas = [
        "estudio_codificacion",
        "estudio_membresia",
        "estudio_muestra",
        "estudio_enunciado",
        "codebook_version",
        "estudio_ancla",
        "estudio_etiqueta",
        "estudio_etiqueta_historial",
        "entrenamiento_respuesta",
    ]
    partes: list[str] = []
    for t in tablas:
        partes += [
            str(f["fila"])
            for f in await estudio_http.sql(f"SELECT row_to_json(x)::text AS fila FROM {t} x")
        ]
    volcado = " ".join(partes)
    assert "episode_id" in volcado
    for valor in ("origen-0", "origen-4", "TP-0", "TP-1", "E0", "E2", "estrato"):
        assert valor not in volcado, valor


@pytest.mark.parametrize(
    ("csv", "fragmento"),
    [
        ("estrato,origen\nE1,x\n", "episode_id"),
        ("episode_id\nno-es-uuid\n", "fila 2"),
        ("episode_id\n", "vacía"),
    ],
)
async def test_csv_invalido_da_422_y_no_carga_nada(estudio_http, csv, fragmento) -> None:
    r = await estudio_http.client.post(
        estudio_http.ruta("/muestra"),
        content=csv.encode(),
        headers={**estudio_http.investigador.headers(), "Content-Type": "text/csv"},
    )
    assert r.status_code == 422
    assert fragmento in r.text
    assert await _contar_items(estudio_http) == 0


async def test_duplicado_da_422_con_la_fila(estudio_http) -> None:
    ep = estudio_http.ctr.agregar()
    r = await estudio_http.cargar_muestra([ep, estudio_http.ctr.agregar(), ep])
    assert r.status_code == 422
    assert "fila 4" in r.text
    assert await _contar_items(estudio_http) == 0


async def test_hash_distinto_da_422(estudio_http) -> None:
    episodios = [estudio_http.ctr.agregar()]
    r = await estudio_http.cargar_muestra(episodios, sha256_esperado="0" * 64)
    assert _sd(r) == (422, {"codigo": "sha256_distinto"})
    assert await _contar_items(estudio_http) == 0


@pytest.mark.parametrize("caso", ["inexistente", "open", "paused_sin_abandono", "integridad"])
async def test_episodio_invalido_da_422_y_no_carga_nada(estudio_http, caso) -> None:
    ctr = estudio_http.ctr
    malo = {
        "inexistente": uuid4,
        "open": lambda: ctr.agregar(estado="open", cierre=None),
        "paused_sin_abandono": lambda: ctr.agregar(estado="paused", cierre=None),
        "integridad": lambda: ctr.agregar(integrity_compromised=True),
    }[caso]()
    r = await estudio_http.cargar_muestra([ctr.agregar(), malo])
    assert r.status_code == 422
    assert "episodios_invalidos" in r.text
    assert "fila 3" in r.text
    assert str(malo) not in r.text
    assert await _contar_items(estudio_http) == 0


async def test_abandonado_y_reanudado_despues_no_cambia_la_traza(estudio_http) -> None:
    ep = estudio_http.ctr.agregar(estado="paused", cierre="episodio_abandonado")
    assert (await estudio_http.cargar_muestra([ep])).status_code == 200
    problema = UUID(estudio_http.ctr.episodios[ep]["problema_id"])
    await estudio_http.insertar_enunciado_sql("tp", problema, "Consigna")
    item_id = (await estudio_http.sql("SELECT item_id FROM estudio_muestra"))[0]["item_id"]
    antes = await estudio_http.pedir("GET", f"/items/{item_id}/traza", estudio_http.c1)
    assert antes.status_code == 200, antes.text
    estudio_http.ctr.evento(ep, "prompt_enviado", {"content": "retome"}, estado="open")
    estudio_http.ctr.evento(ep, "edicion_codigo", {"snapshot": "x = 1", "language": "python"})
    despues = await estudio_http.pedir("GET", f"/items/{item_id}/traza", estudio_http.c1)
    assert despues.json() == antes.json()
    assert antes.json()["elementos"][-1]["tipo"] == "fin_abandonado"


async def test_episodio_que_es_ancla_da_409(estudio_http) -> None:
    await estudio_http.pedir(
        "POST", "/codebook", estudio_http.investigador, json={"etiqueta": "v0"}
    )
    ep = estudio_http.ctr.agregar()
    await estudio_http.insertar_item_sql(ep, ancla_de="v0")
    r = await estudio_http.cargar_muestra([estudio_http.ctr.agregar(), ep])
    assert _sd(r) == (409, "episodio_es_ancla")
    assert await _contar_items(estudio_http) == 0


async def test_reemplazo_sin_etiquetas_se_acepta(estudio_http) -> None:
    primera = [estudio_http.ctr.agregar(), estudio_http.ctr.agregar()]
    assert (await estudio_http.cargar_muestra(primera)).status_code == 200
    segunda = [estudio_http.ctr.agregar()]
    r = await estudio_http.cargar_muestra(segunda)
    assert r.status_code == 200, r.text
    filas = await estudio_http.sql("SELECT episode_id FROM estudio_muestra")
    assert [f["episode_id"] for f in filas] == segunda


async def test_reemplazo_con_etiquetas_da_409_y_no_cambia(estudio_http) -> None:
    primera = [estudio_http.ctr.agregar()]
    assert (await estudio_http.cargar_muestra(primera)).status_code == 200
    await estudio_http.pedir(
        "POST", "/codebook", estudio_http.investigador, json={"etiqueta": "v0"}
    )
    await estudio_http.sql(
        "INSERT INTO estudio_etiqueta (tenant_id, membresia_id, muestra_item_id, codebook_version_id, "
        "traza_version) SELECT :t, m.id, i.item_id, v.id, 'traza_v1' FROM estudio_membresia m, "
        "estudio_muestra i, codebook_version v WHERE m.rol = 'codificador' LIMIT 1",
        {"t": estudio_http.tenant_id},
        commit=True,
    )
    r = await estudio_http.cargar_muestra([estudio_http.ctr.agregar()])
    assert _sd(r) == (409, "muestra_con_etiquetas")
    filas = await estudio_http.sql("SELECT episode_id FROM estudio_muestra")
    assert [f["episode_id"] for f in filas] == primera


@pytest.mark.parametrize("quien", ["c1", "ajeno", "admin"])
async def test_solo_el_investigador_carga(estudio_http, quien) -> None:
    r = await estudio_http.cargar_muestra(
        [estudio_http.ctr.agregar()], persona=getattr(estudio_http, quien)
    )
    assert r.status_code == 403
    assert estudio_http.ctr.llamadas == []


async def test_ctr_caido_da_502_y_no_carga(estudio_http) -> None:
    episodios = [estudio_http.ctr.agregar()]
    estudio_http.ctr.modo = "caido"
    r = await estudio_http.cargar_muestra(episodios)
    assert r.status_code == 502
    assert await _contar_items(estudio_http) == 0


async def test_carga_simulada_de_150_items(estudio_http) -> None:
    episodios = [estudio_http.ctr.agregar() for _ in range(150)]
    inicio = time.perf_counter()
    r = await estudio_http.cargar_muestra(episodios)
    duracion = time.perf_counter() - inicio
    assert r.status_code == 200, r.text
    assert r.json()["items"] == 150
    print(f"carga simulada de 150 items: {duracion:.2f} s")
    assert duracion < 120


# ── 7.2 orden por codificador ─────────────────────────────────────────────


async def test_items_en_orden_estable_mismo_conjunto_y_semillas_distintas(estudio_http) -> None:
    episodios = [estudio_http.ctr.agregar() for _ in range(6)]
    assert (await estudio_http.cargar_muestra(episodios)).status_code == 200
    a1 = await estudio_http.items(estudio_http.c1)
    a2 = await estudio_http.items(estudio_http.c1)
    b = await estudio_http.items(estudio_http.c2)
    assert a1 == a2
    assert {i["item_id"] for i in a1} == {i["item_id"] for i in b}
    assert [i["posicion"] for i in a1] == list(range(1, 7))
    assert all(set(i) == {"item_id", "posicion", "estado"} for i in a1 + b)
    assert all(i["estado"] == "sin_empezar" for i in a1)
    assert not {str(e) for e in episodios} & {i["item_id"] for i in a1}

    semillas = await estudio_http.sql(
        "SELECT email, semilla FROM estudio_membresia WHERE rol = 'codificador'"
    )
    por_email = {f["email"]: f["semilla"] for f in semillas}
    assert por_email["c1@ejemplo.org"] != por_email["c2@ejemplo.org"]
    recomputado = sorted(
        a1,
        key=lambda i: hashlib.sha256(
            f"{por_email['c1@ejemplo.org']}:{i['item_id']}".encode()
        ).hexdigest(),
    )
    assert [i["item_id"] for i in recomputado] == [i["item_id"] for i in a1]


async def test_items_solo_para_codificadores(estudio_http) -> None:
    assert (await estudio_http.pedir("GET", "/items", estudio_http.ajeno)).status_code == 403


async def test_ctr_con_problema_id_que_no_es_uuid_da_502_y_no_carga_nada(estudio_http) -> None:
    """verify-2, N2: un 200 del CTR con `problema_id` que no es UUID daba 500
    en `evidencia_fija`; es una falla del registro -> 502 genérico."""
    import copy

    import httpx
    from classifier_service.main import app
    from classifier_service.services.ctr_lectura import CTRLector, get_ctr_lector

    ep = estudio_http.ctr.agregar()
    datos = copy.deepcopy(estudio_http.ctr.episodios[ep])
    datos["problema_id"] = "no-uuid-secreto"
    transporte = httpx.MockTransport(lambda r: httpx.Response(200, json=datos))
    app.dependency_overrides[get_ctr_lector] = lambda: CTRLector("http://ctr", transport=transporte)
    r = await estudio_http.cargar_muestra([ep])
    assert r.status_code == 502
    assert "secreto" not in r.text
    assert await _contar_items(estudio_http) == 0
