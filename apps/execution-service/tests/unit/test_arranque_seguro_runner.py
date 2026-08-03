"""En produccion el runner no arranca sin los controles del ADR-060 (tarea 8.4).

Dos de los tres controles de 8.4 estaban fallando ABIERTOS:

  - Sin `RUNNER_TOKEN`, `_check_token` salia temprano y el runner atendia /run a
    cualquiera que lo alcanzara. Es el UNICO proceso con acceso al socket de
    Docker: permitir `POST /containers/create` es permitir crear un contenedor
    privilegiado con `/` montado (ADR-060 D3).
  - Con la imagen por tag mutable, se ejecutaba lo que hubiera del otro lado del
    tag ese dia. Para un sandbox que corre codigo de terceros, el digest es lo
    que hace reproducible QUE se corrio.

Un control que se cumple solo si alguien se acordo de configurarlo no es un
control. El ADR-059 ya dejo esa leccion: dio por sentado que Judge0 levantaba y
resulto que exige cgroups v1. Ahora fallan CERRADOS, igual que las cuotas.
"""

from __future__ import annotations

import pytest
from execution_service import runner_main
from execution_service.config import settings

DIGEST = "eclipse-temurin@sha256:" + "a" * 64
TOKEN_OK = "x" * 40


@pytest.fixture(autouse=True)
def _restaurar():
    prev = (settings.environment, settings.runner_token, settings.java_image)
    yield
    settings.environment, settings.runner_token, settings.java_image = prev


def _configurar(*, entorno: str, token: str, imagen: str) -> None:
    settings.environment = entorno
    settings.runner_token = token
    settings.java_image = imagen


def test_produccion_sin_token_no_arranca() -> None:
    _configurar(entorno="production", token="", imagen=DIGEST)
    problemas = runner_main.verificar_configuracion_segura()
    assert any("RUNNER_TOKEN" in p for p in problemas), problemas


def test_produccion_con_imagen_por_tag_no_arranca() -> None:
    _configurar(entorno="production", token=TOKEN_OK, imagen="eclipse-temurin:21-jdk")
    problemas = runner_main.verificar_configuracion_segura()
    assert any("digest" in p for p in problemas), problemas


def test_produccion_con_token_corto_se_rechaza() -> None:
    """Un token de 8 chars es adivinable; el control seria decorativo."""
    _configurar(entorno="production", token="corto123", imagen=DIGEST)
    problemas = runner_main.verificar_configuracion_segura()
    assert any("32" in p for p in problemas), problemas


def test_produccion_bien_configurada_arranca() -> None:
    _configurar(entorno="production", token=TOKEN_OK, imagen=DIGEST)
    assert runner_main.verificar_configuracion_segura() == []


def test_desarrollo_tolera_la_configuracion_floja() -> None:
    """Fuera de produccion se avisa, no se bloquea: el dev loop no puede pedir
    un digest y un token para levantar el stack local."""
    _configurar(entorno="development", token="", imagen="eclipse-temurin:21-jdk")
    # Sigue reportando los problemas...
    assert runner_main.verificar_configuracion_segura() != []
    # ...pero no es produccion, asi que el lifespan solo loguea.
    assert not runner_main._es_produccion()


@pytest.mark.parametrize("entorno", ["production", "prod", "staging", "PRODUCTION", "piloto"])
def test_cualquier_entorno_que_no_sea_dev_cuenta_como_produccion(entorno: str) -> None:
    """Fail-closed en la clasificacion tambien: un entorno desconocido se trata
    como produccion. Si alguien escribe `staging` o `piloto`, tiene que exigir
    los controles — no caer al modo permisivo por no estar en una lista."""
    settings.environment = entorno
    assert runner_main._es_produccion()


@pytest.mark.parametrize("entorno", ["development", "dev", "test", "testing", "  DEV  "])
def test_los_entornos_de_desarrollo_se_reconocen(entorno: str) -> None:
    settings.environment = entorno
    assert not runner_main._es_produccion()
