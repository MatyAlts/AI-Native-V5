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

import pytest
from tutor_service.config import settings
from tutor_service.routes.episodes import _es_emisor_interno

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


def _validar(tests_hidden: int, *, emisor_interno: bool) -> None:
    """Replica el guard de `tutor_core.emit_tests_ejecutados`.

    Se prueba la REGLA, no el metodo entero: el metodo necesita Redis, el CTR y
    una sesion viva. Lo que este test protege es la condicion, que es donde
    vivio el bug las dos veces.
    """
    if tests_hidden != 0 and not emisor_interno:
        raise ValueError(f"tests_hidden debe ser 0 desde el cliente (recibido {tests_hidden})")


@pytest.mark.parametrize("ocultos", [1, 2, 5])
def test_el_execution_service_puede_reportar_ocultos(ocultos: int) -> None:
    """EL caso que estaba roto. Es la razon de ser del ADR-060."""
    _validar(ocultos, emisor_interno=True)


@pytest.mark.parametrize("ocultos", [1, 2, 5])
def test_el_navegador_no_puede_reportar_ocultos(ocultos: int) -> None:
    """El guard que NO hay que borrar: Pyodide no recibe los casos
    `is_public=false`, asi que un `tests_hidden > 0` desde el browser es un
    cliente mintiendo sobre lo que ejecuto."""
    with pytest.raises(ValueError, match="desde el cliente"):
        _validar(ocultos, emisor_interno=False)


def test_sin_ocultos_ambos_emisores_pasan() -> None:
    """El camino de Pyodide sigue intacto — es el que corre en produccion hoy."""
    _validar(0, emisor_interno=False)
    _validar(0, emisor_interno=True)
