"""El warmup del runner baja la imagen al arrancar y NUNCA tumba el proceso.

El warmup existe porque `docker_runner.py` aplica el wall-time limit (10s) sobre
el `docker run` ENTERO: si la imagen no esta local, esa descarga de ~450MB entra
en el presupuesto de ejecucion del alumno y la corrida muere por timeout.

Lo que estos tests protegen es la otra mitad: que el warmup sea **best-effort de
verdad**. El runner es el unico componente con acceso al socket de Docker; si un
`docker pull` fallado lo tumbara al arrancar, un registry caido o una maquina sin
red dejaria sin ejecucion a todo el piloto — cuando el comportamiento correcto es
degradar a `infrastructure_failure`, que ya esta cubierto y no emite evento CTR.

No se toca Docker real: se sustituye `create_subprocess_exec`. Un test que baje
450MB no es un test unitario.
"""

from __future__ import annotations

import asyncio

import pytest
from execution_service import runner_main
from execution_service.runner_main import _warmup_image


class _ProcFalso:
    """Doble de `asyncio.subprocess.Process` con lo justo que usa el warmup."""

    def __init__(self, returncode: int = 0, stderr: bytes = b"") -> None:
        self.returncode = returncode
        self._stderr = stderr
        self.killed = False

    async def communicate(self, _stdin: bytes | None = None) -> tuple[bytes, bytes]:
        return b"", self._stderr

    def kill(self) -> None:
        self.killed = True

    async def wait(self) -> int:
        return self.returncode


@pytest.mark.asyncio
async def test_el_warmup_pide_pull_de_la_imagen_configurada(monkeypatch) -> None:
    """Tiene que bajar LA imagen del config, no una hardcodeada.

    En produccion la imagen se pinea por digest (control C1 del ADR-060). Si el
    warmup bajara un tag fijo, precalentaria una imagen distinta de la que se
    ejecuta y no serviria para nada.
    """
    visto: list[tuple[str, ...]] = []

    async def _fake(*args: str, **_kwargs: object) -> _ProcFalso:
        visto.append(args)
        return _ProcFalso(returncode=0)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake)
    monkeypatch.setattr(
        runner_main.settings, "java_image", "eclipse-temurin:21-jdk@sha256:deadbeef"
    )

    await _warmup_image()

    assert visto == [("docker", "pull", "eclipse-temurin:21-jdk@sha256:deadbeef")]


@pytest.mark.asyncio
async def test_un_pull_fallado_no_propaga(monkeypatch) -> None:
    """Registry caido, imagen inexistente, sin credenciales: el runner sigue vivo."""

    async def _fake(*_args: str, **_kwargs: object) -> _ProcFalso:
        return _ProcFalso(returncode=1, stderr=b"Error response from daemon: manifest unknown")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake)

    await _warmup_image()  # no debe levantar


@pytest.mark.asyncio
async def test_sin_cliente_de_docker_no_propaga(monkeypatch) -> None:
    """El binario `docker` puede no estar en el PATH. Tampoco es fatal."""

    async def _fake(*_args: str, **_kwargs: object) -> _ProcFalso:
        raise OSError("No such file or directory: 'docker'")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake)

    await _warmup_image()  # no debe levantar


@pytest.mark.asyncio
async def test_un_pull_colgado_se_corta_y_mata_al_proceso(monkeypatch) -> None:
    """Sin el timeout, un registry que acepta la conexion y no responde deja el
    subproceso colgado para siempre dentro del runner."""
    proc = _ProcFalso(returncode=0)

    async def _nunca_termina(_stdin: bytes | None = None) -> tuple[bytes, bytes]:
        await asyncio.sleep(3600)
        raise AssertionError("inalcanzable")

    proc.communicate = _nunca_termina  # type: ignore[method-assign]

    async def _fake(*_args: str, **_kwargs: object) -> _ProcFalso:
        return proc

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake)
    monkeypatch.setattr(runner_main, "_WARMUP_PULL_TIMEOUT_SECONDS", 0.05)

    await _warmup_image()  # no debe levantar ni colgarse

    assert proc.killed, "el subproceso colgado tiene que morir, no quedar huerfano"


@pytest.mark.asyncio
async def test_el_lifespan_no_espera_a_que_termine_el_pull(monkeypatch) -> None:
    """El arranque NO se bloquea: el runner atiende mientras la imagen baja.

    Si el warmup fuera bloqueante, el runner tardaria un minuto en responder
    tras cada deploy y el gate de arranque del smoke (30 reintentos) podria
    darse por vencido antes.
    """
    empezo = asyncio.Event()

    async def _pull_largo() -> None:
        empezo.set()
        await asyncio.sleep(3600)

    monkeypatch.setattr(runner_main, "_warmup_image", _pull_largo)

    async with runner_main.lifespan(runner_main.app):
        # Si el lifespan esperara al pull, nunca llegariamos hasta aca.
        await asyncio.wait_for(empezo.wait(), timeout=1.0)
