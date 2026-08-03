"""Un caso oculto ejecutado server-side TIENE que poder llegar al CTR.

Este es el test de COSTURA que faltaba. El bug que cierra vivio en el hueco
entre dos capas que nadie cruzaba:

  - `execution-service/ctr_emitter.build_payload` producia el conteo real de
    ocultos, y su unitario lo verificaba.
  - `tutor-service` lo rechazaba, primero en el schema (`le=0`) y despues —tras
    arreglar el schema— en la capa de negocio (`tutor_core`, `tests_hidden != 0`).

Cada lado estaba testeado y en verde. Nadie testeaba que del otro lado lo
aceptaran. Resultado: **todo ejercicio Java con al menos un caso oculto perdia
su `tests_ejecutados`, en silencio**, porque el emisor falla soft.

Por que importa mas que un bug cualquiera: ejecutar un caso oculto SIN
revelarselo al alumno es LA capacidad que justifica el ADR-060. Es lo unico que
Pyodide no podia dar. Justo esa era la que mataba el evento — y sin
`tests_ejecutados` el labeler no puede separar N3 de N4, asi que esos episodios
quedaban fuera de comparacion con los de Python.

La verificacion en navegador tampoco lo agarro: el ejercicio que se probo no
tenia casos ocultos (`tests_hidden: 0` en la evidencia), asi que el camino roto
nunca se ejecuto. De ahi que este test parametrice EL CASO CON OCULTOS.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import fakeredis.aioredis
import pytest
from tutor_service.config import settings
from tutor_service.routes.episodes import _es_emisor_interno
from tutor_service.services.session import SessionManager
from tutor_service.services.tutor_core import TutorCore

from .test_episode_events import (
    FakeAIGatewayClient,
    FakeContentClient,
    FakeGovernanceClient,
)

TOKEN = "secreto-interno-de-32-chars-o-mas-xxxx"


@pytest.fixture(autouse=True)
def _restaurar_token():
    previo = settings.internal_service_token
    yield
    settings.internal_service_token = previo


# ── Quien cuenta como emisor interno ────────────────────────────────────────


def test_el_token_correcto_prueba_procedencia_interna() -> None:
    settings.internal_service_token = TOKEN
    assert _es_emisor_interno(TOKEN)


def test_un_token_forjado_no_alcanza() -> None:
    """El api-gateway NO filtra `X-Internal-Service-Token` — no lo menciona en
    ningun lado. Un navegador puede mandarlo y llega. Lo que prueba procedencia
    es conocer el VALOR, que nunca sale del servidor."""
    settings.internal_service_token = TOKEN
    assert not _es_emisor_interno("me-lo-invente")
    assert not _es_emisor_interno("")
    assert not _es_emisor_interno(None)


def test_un_prefijo_del_token_no_alcanza() -> None:
    """Contra comparacion perezosa: `startswith` o un `==` mal escrito."""
    settings.internal_service_token = TOKEN
    assert not _es_emisor_interno(TOKEN[:-1])
    assert not _es_emisor_interno(TOKEN + "x")


def test_sin_secreto_configurado_nadie_es_interno() -> None:
    """Falla CERRADO. Sin secreto no hay forma de verificar a nadie, y el modo
    permisivo dejaria que un browser reporte ocultos por default."""
    settings.internal_service_token = ""
    assert not _es_emisor_interno(TOKEN)
    assert not _es_emisor_interno("")
    assert not _es_emisor_interno(None)


# ── La regla de negocio ─────────────────────────────────────────────────────


# ── La regla de negocio, contra el METODO REAL ──────────────────────────────
#
# La primera version de estos tests REPLICABA el guard en un helper local. Eso
# los dejaba verdes aunque alguien cambiara `tutor_core`: era el mismo hueco
# entre capas que produjo el bug, con un test adentro. Ahora llaman a
# `emit_tests_ejecutados` de verdad, con dobles para Redis y el CTR — el molde
# es `test_episode_events.py`, que hace lo mismo con el endpoint hermano.


class FakeCTRClient:
    def __init__(self) -> None:
        self.published_events: list[dict] = []

    async def publish_event(self, event: dict, tenant_id: UUID, caller_id: UUID) -> str:
        self.published_events.append(event)
        return f"fake-{len(self.published_events)}"


@pytest.fixture
async def redis_client():
    client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    yield client
    await client.aclose()


@pytest.fixture
def fake_ctr() -> FakeCTRClient:
    return FakeCTRClient()


@pytest.fixture
def tutor(redis_client, fake_ctr) -> TutorCore:
    return TutorCore(
        governance=FakeGovernanceClient(),
        content=FakeContentClient(),
        ai_gateway=FakeAIGatewayClient(),
        ctr=fake_ctr,
        sessions=SessionManager(redis_client),
    )


async def _episodio(tutor: TutorCore) -> UUID:
    return await tutor.open_episode(
        tenant_id=uuid4(),
        comision_id=uuid4(),
        student_pseudonym=uuid4(),
        problema_id=uuid4(),
        curso_config_hash="c" * 64,
        classifier_config_hash="b" * 64,
    )


@pytest.mark.parametrize("ocultos", [1, 2, 5])
async def test_el_execution_service_puede_reportar_ocultos(
    tutor: TutorCore, fake_ctr: FakeCTRClient, ocultos: int
) -> None:
    """EL caso que estaba roto. Es la razon de ser del ADR-060.

    Llega hasta el evento publicado en el CTR: no alcanza con que no explote,
    hay que ver el conteo real de ocultos del otro lado.
    """
    episode_id = await _episodio(tutor)
    seq = await tutor.emit_tests_ejecutados(
        episode_id=episode_id,
        user_id=uuid4(),
        test_count_total=ocultos + 2,
        test_count_passed=2,
        test_count_failed=ocultos,
        tests_publicos=2,
        tests_hidden=ocultos,
        ejecucion_ms=900,
        emisor_interno=True,
    )
    assert seq == 1
    ev = fake_ctr.published_events[-1]
    assert ev["event_type"] == "tests_ejecutados"
    assert ev["payload"]["tests_hidden"] == ocultos


@pytest.mark.parametrize("ocultos", [1, 2, 5])
async def test_el_navegador_no_puede_reportar_ocultos(
    tutor: TutorCore, fake_ctr: FakeCTRClient, ocultos: int
) -> None:
    """El guard que NO hay que borrar: Pyodide no recibe los casos
    `is_public=false`, asi que un `tests_hidden > 0` desde el browser es un
    cliente mintiendo sobre lo que ejecuto."""
    episode_id = await _episodio(tutor)
    with pytest.raises(ValueError, match="desde el cliente"):
        await tutor.emit_tests_ejecutados(
            episode_id=episode_id,
            user_id=uuid4(),
            test_count_total=ocultos + 2,
            test_count_passed=2,
            test_count_failed=ocultos,
            tests_publicos=2,
            tests_hidden=ocultos,
            ejecucion_ms=900,
        )
    # Y no dejo rastro en la cadena: solo esta `episodio_abierto`.
    assert all(e["event_type"] != "tests_ejecutados" for e in fake_ctr.published_events)


async def test_sin_ocultos_el_camino_de_pyodide_sigue_intacto(
    tutor: TutorCore, fake_ctr: FakeCTRClient
) -> None:
    """Es el que corre en produccion hoy. `emisor_interno` default False."""
    episode_id = await _episodio(tutor)
    seq = await tutor.emit_tests_ejecutados(
        episode_id=episode_id,
        user_id=uuid4(),
        test_count_total=2,
        test_count_passed=1,
        test_count_failed=1,
        tests_publicos=2,
        tests_hidden=0,
        ejecucion_ms=500,
    )
    assert seq == 1
    assert fake_ctr.published_events[-1]["payload"]["tests_hidden"] == 0


async def test_el_default_de_emisor_interno_es_cerrado(tutor: TutorCore) -> None:
    """Un caller que no dice nada NO es interno.

    Si el default fuera True, cualquier caller viejo que no conozca el
    parametro podria reportar ocultos sin probar procedencia.
    """
    episode_id = await _episodio(tutor)
    with pytest.raises(ValueError, match="desde el cliente"):
        await tutor.emit_tests_ejecutados(
            episode_id=episode_id,
            user_id=uuid4(),
            test_count_total=3,
            test_count_passed=1,
            test_count_failed=2,
            tests_publicos=2,
            tests_hidden=1,
            ejecucion_ms=900,
            # sin `emisor_interno` a proposito
        )
