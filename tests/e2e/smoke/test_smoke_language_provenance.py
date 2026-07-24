"""Smoke — procedencia de lenguaje del episodio (multi-language-research-integrity).

Cierra la sección 8 de la change. Valida contra el stack real las dos puntas
de la capability `episode-language-provenance`:

  1. **Escritura** (8.1): abrir un episodio sobre una TP Java deja `language`
     en el payload del evento `episodio_abierto` (seq=0) del CTR.
  2. **Lectura** (8.2): un endpoint de analytics sobre una cohorte MIXTA
     (el episodio Java recién abierto + un episodio legacy del seed, sin
     campo `language`) declara los dos lenguajes.

Por qué smoke y no unit: los unit de la sección 2 mockean el `AcademicClient`
y los de la sección 4 mockean `ctr_store`. Acá se ejercita la cadena real
academic-service → tutor-service → CTR → analytics-service, que es donde vive
el riesgo: que el lenguaje se resuelva bien en memoria pero nunca llegue al
payload persistido, o que analytics lo lea de `TareaPractica.language` (la
fuente equivocada) en vez del evento de apertura.

El caso legacy no es decorativo: el episodio del seed fue escrito ANTES de que
el campo existiera, así que su payload no lo tiene. Que resuelva a `python` por
default es lo que sostiene que los 100+ episodios del piloto-1 sigan siendo
comparables. Si alguien cambia el default o lo hace obligatorio, este test cae.

Requiere:
  - stack completo up (api-gateway :8000, academic :8002, analytics :8005,
    tutor :8006, ctr :8007)
  - **partition workers del ctr-service corriendo** — sin ellos el evento se
    queda en el stream Redis y nunca llega a Postgres. Los tests skipean con
    mensaje explícito en vez de fallar, igual criterio que
    `test_smoke_pedagogico.py` (que directamente no valida persistencia).
  - `CTR_STORE_URL` + `CLASSIFIER_DB_URL` declaradas en el Settings del
    analytics-service; sin eso cae a stub y resuelve todo a `python`.
  - seed con el episodio `80000000-...-0000000f69b4` (fixture
    `seeded_episode_id`).
"""

from __future__ import annotations

import time
from uuid import UUID, uuid4

import httpx
import pytest
from _helpers import COMISION_A_MANANA, DOCENTE_DEMO, TENANT_DEMO

# Mismos hashes del seed que usa `test_smoke_pedagogico.py`. Duplicados a
# proposito: no hay endpoint publico que los exponga y no queremos acoplar
# este modulo al import de otro modulo de test.
SEEDED_CLASSIFIER_CONFIG_HASH = "9dd96894fc88e68390b0d078d19c98acdb1b9810fec9757b0c05d577495c6edd"
SEEDED_CURSO_CONFIG_HASH = "fd7ab31baa147f2c15a52947af98b11aa3b1f1c99e4cba00afa242bb5698832a"

# Ventana de espera para que el partition worker drene el stream Redis a
# Postgres. Es asincrono single-writer; 15s es holgado para un evento suelto.
_CTR_DRAIN_TIMEOUT_SECONDS = 15.0
_CTR_POLL_INTERVAL_SECONDS = 0.5

# State compartido entre tests del modulo (secuenciales, igual patron que
# `test_smoke_java_language.py`).
_state: dict[str, str] = {}


def _docente_headers() -> dict[str, str]:
    return {
        "X-User-Id": DOCENTE_DEMO,
        "X-Tenant-Id": TENANT_DEMO,
        "X-User-Email": "docente@demo-uni.edu",
        "X-User-Roles": "docente",
    }


def _crear_tp_java_publicada(client: httpx.Client) -> str:
    """Ejercicio Java + TP Java compuesta y publicada. Devuelve el id de la TP.

    Es el minimo que `tutor.open_episode()` acepta: la TP tiene que estar
    `published` y tener al menos un ejercicio (sino da 422 por TP vacia).
    """
    headers = _docente_headers()

    ej_resp = client.post(
        "/api/v1/ejercicios",
        json={
            "titulo": f"Smoke provenance Java {uuid4().hex[:8]}",
            "enunciado_md": "Resolver el ejercicio en java.",
            "unidad_tematica": "smoke",
            "language": "java",
            "test_cases": [
                {
                    "id": "tc1",
                    "name": "caso basico",
                    "type": "junit_assert",
                    "code": "assert True",
                    "is_public": True,
                    "weight": 1.0,
                }
            ],
        },
        headers=headers,
    )
    assert ej_resp.status_code in (200, 201), (
        f"create ejercicio java: {ej_resp.status_code} {ej_resp.text[:300]}"
    )

    tp_resp = client.post(
        "/api/v1/tareas-practicas",
        json={
            "comision_id": COMISION_A_MANANA,
            "codigo": f"SMK-LP{uuid4().hex[:4].upper()}",
            "titulo": "Smoke TP java (procedencia de lenguaje)",
            "enunciado": "Trabajo practico de smoke en java.",
            "language": "java",
        },
        headers=headers,
    )
    assert tp_resp.status_code in (200, 201), (
        f"create tp java: {tp_resp.status_code} {tp_resp.text[:300]}"
    )
    tp_id: str = tp_resp.json()["id"]

    add_resp = client.post(
        f"/api/v1/tareas-practicas/{tp_id}/ejercicios",
        json={"ejercicio_id": ej_resp.json()["id"], "orden": 1, "peso_en_tp": "1.0"},
        headers=headers,
    )
    assert add_resp.status_code in (200, 201), (
        f"add ejercicio a la tp: {add_resp.status_code} {add_resp.text[:300]}"
    )

    pub_resp = client.post(f"/api/v1/tareas-practicas/{tp_id}/publish", headers=headers)
    assert pub_resp.status_code in (200, 201), (
        f"publish tp java: {pub_resp.status_code} {pub_resp.text[:300]}"
    )

    return tp_id


def _esperar_evento_de_apertura(client: httpx.Client, episode_id: str) -> dict:
    """Poll al audit alias hasta que el `episodio_abierto` (seq=0) este en DB.

    El evento viaja tutor-service → stream Redis `ctr.pN` → partition worker →
    Postgres. Si el worker no esta corriendo nunca llega, y eso no es un fallo
    de esta capability: skipeamos nombrando la pre-condicion que falta.
    """
    deadline = time.monotonic() + _CTR_DRAIN_TIMEOUT_SECONDS
    ultimo_status = None
    while time.monotonic() < deadline:
        resp = client.get(f"/api/v1/audit/episodes/{episode_id}", headers=_docente_headers())
        ultimo_status = resp.status_code
        if resp.status_code == 200:
            eventos = resp.json().get("events") or []
            apertura = next((e for e in eventos if e.get("seq") == 0), None)
            if apertura is not None:
                return apertura
        time.sleep(_CTR_POLL_INTERVAL_SECONDS)

    pytest.skip(
        f"El evento de apertura del episodio {episode_id} no llego a ctr_store en "
        f"{_CTR_DRAIN_TIMEOUT_SECONDS:.0f}s (ultimo status del audit: {ultimo_status}). "
        "Pre-condicion faltante: los partition workers del ctr-service tienen que "
        "estar drenando los streams `ctr.p0..ctr.p7`. Sin ellos no se puede verificar "
        "la persistencia del lenguaje."
    )


# ── 8.1 — escritura: el lenguaje llega al evento de apertura ───────────


@pytest.mark.smoke
def test_episodio_sobre_tp_java_registra_java_en_el_evento_de_apertura(
    client: httpx.Client, auth_headers, student_id: str, comision_id: str
) -> None:
    """8.1 — abrir un episodio sobre una TP Java deja `language="java"` en seq=0.

    Es la unica fuente de verdad del lenguaje de un episodio: el CTR es
    append-only, asi que lo que quede en el payload de apertura es lo que
    cualquier analisis posterior va a leer, aunque la TP despues cambie.
    """
    tp_java_id = _crear_tp_java_publicada(client)
    _state["tp_java_id"] = tp_java_id

    open_resp = client.post(
        "/api/v1/episodes",
        json={
            "comision_id": comision_id,
            "problema_id": tp_java_id,
            "curso_config_hash": SEEDED_CURSO_CONFIG_HASH,
            "classifier_config_hash": SEEDED_CLASSIFIER_CONFIG_HASH,
        },
        headers=auth_headers("estudiante", user_id=student_id),
    )
    assert open_resp.status_code == 201, (
        f"POST /api/v1/episodes sobre TP java fallo: {open_resp.status_code} {open_resp.text[:400]}"
    )
    episode_id = open_resp.json()["episode_id"]
    UUID(episode_id)
    _state["episodio_java_id"] = episode_id

    apertura = _esperar_evento_de_apertura(client, episode_id)

    assert apertura["event_type"] == "episodio_abierto", (
        f"seq=0 deberia ser el episodio_abierto, es {apertura['event_type']}"
    )
    assert apertura["payload"].get("language") == "java", (
        "el lenguaje no llego al payload de apertura. El tutor-service lo resuelve "
        "en `_resolve_episode_language(contexto_data)` desde la respuesta del "
        "academic-service — si esto falla, revisar que `TareaPracticaOut` siga "
        f"exponiendo `language`. payload={apertura['payload']}"
    )


# ── 8.2 — lectura: analytics declara los lenguajes de una cohorte mixta ─


@pytest.mark.smoke
def test_analytics_sobre_cohorte_mixta_declara_ambos_lenguajes(
    client: httpx.Client, auth_headers, seeded_episode_id: str
) -> None:
    """8.2 — kappa sobre {episodio java nuevo, episodio legacy del seed}.

    Elegimos kappa entre los 6 endpoints con `languages_present` porque es el
    unico donde el conjunto de episodios viaja en el request: nos deja armar
    una cohorte mixta deterministica sin depender de que el classifier haya
    clasificado el episodio nuevo.

    El episodio del seed es legacy — su payload de apertura NO tiene el campo
    `language`. Que resuelva a `python` por default es la garantia de
    comparabilidad con el piloto-1.
    """
    episodio_java = _state.get("episodio_java_id")
    if not episodio_java:
        pytest.skip("depende de test_episodio_sobre_tp_java_... (corre antes en el modulo)")

    resp = client.post(
        "/api/v1/analytics/kappa",
        json={
            "ratings": [
                {
                    "episode_id": episodio_java,
                    "rater_a": "apropiacion_reflexiva",
                    "rater_b": "apropiacion_reflexiva",
                },
                {
                    "episode_id": seeded_episode_id,
                    "rater_a": "delegacion_pasiva",
                    "rater_b": "delegacion_pasiva",
                },
            ]
        },
        headers=auth_headers("docente"),
    )
    assert resp.status_code == 200, f"POST kappa fallo: {resp.status_code} {resp.text[:400]}"

    body = resp.json()
    assert body["languages_present"] == ["java", "python"], (
        "la declaracion de lenguajes de una cohorte mixta esta mal. "
        "Si dice solo ['python'], el analytics-service probablemente esta en modo "
        "stub — verificar que `CTR_STORE_URL` y `CLASSIFIER_DB_URL` esten declaradas "
        f"en su Settings (`_real_data_source_enabled`). body={body}"
    )
    assert body["n_episodes"] == 2, f"sin filtro deberian entrar los 2 ratings: {body}"
    assert body["insufficient_data"] is False


@pytest.mark.smoke
def test_filtro_por_lenguaje_recorta_la_cohorte_mixta(
    client: httpx.Client, auth_headers, seeded_episode_id: str
) -> None:
    """8.2 (contracara) — `?language=java` deja solo el episodio Java.

    Sin este lado, `languages_present` podria estar bien y el filtro no filtrar
    nada. Los dos juntos prueban que el lenguaje resuelto se usa de verdad.
    """
    episodio_java = _state.get("episodio_java_id")
    if not episodio_java:
        pytest.skip("depende de test_episodio_sobre_tp_java_... (corre antes en el modulo)")

    ratings = {
        "ratings": [
            {
                "episode_id": episodio_java,
                "rater_a": "apropiacion_reflexiva",
                "rater_b": "apropiacion_reflexiva",
            },
            {
                "episode_id": seeded_episode_id,
                "rater_a": "delegacion_pasiva",
                "rater_b": "delegacion_pasiva",
            },
        ]
    }

    resp_java = client.post(
        "/api/v1/analytics/kappa",
        params={"language": "java"},
        json=ratings,
        headers=auth_headers("docente"),
    )
    assert resp_java.status_code == 200, f"kappa?language=java: {resp_java.text[:300]}"
    body_java = resp_java.json()
    assert body_java["languages_present"] == ["java"], body_java
    assert body_java["n_episodes"] == 1, (
        f"el filtro java deberia dejar 1 solo rating, dejo {body_java['n_episodes']}"
    )

    # Un lenguaje que no esta en la cohorte → ausencia de datos, NO kappa=0.0
    # (que se leeria como desacuerdo perfecto). Seccion 4.9.
    resp_vacio = client.post(
        "/api/v1/analytics/kappa",
        params={"language": "rust"},
        json=ratings,
        headers=auth_headers("docente"),
    )
    assert resp_vacio.status_code == 200, resp_vacio.text[:300]
    body_vacio = resp_vacio.json()
    assert body_vacio["insufficient_data"] is True, body_vacio
    assert body_vacio["kappa"] is None, (
        f"un filtro sin resultados NO debe fabricar un kappa: {body_vacio}"
    )
