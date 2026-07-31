"""El runner no lanza mas contenedores de los que el host aguanta.

Compilar Java es CPU-bound. Sin techo, N alumnos apretando "Ejecutar" a la vez
lanzan N contenedores a la vez, se pelean por los cores y mueren por wall-time.
Medido sobre 4 CPUs (el hardware del VPS del piloto):

    sin techo, 40 concurrentes -> 30 de 40 MUEREN por timeout
    techo 8,   40 concurrentes -> 40/40 ok
    techo 8,   87 concurrentes -> 87/87 ok (el piloto entero junto)

El modo de falla es lo que hace que esto importe y no sea "va lento": un
timeout por contencion del host es INDISTINGUIBLE de un bucle infinito del
alumno — los dos dan `timed_out=True` -> `CaseStatus.ERROR` -> cuenta como
fallo -> N3. Bajo carga, alumnos con codigo correcto quedan registrados en el
corpus como que fallaron. Es ruido de infraestructura atribuido al alumno, la
misma familia que `ctr_emitter` evita para el fallo de infra, pero deflactando.

Estos tests no tocan Docker: verifican la propiedad del techo con un doble.
"""

from __future__ import annotations

import asyncio

import pytest
from execution_service.config import settings
from execution_service.services import docker_runner


@pytest.fixture(autouse=True)
def _semaforo_limpio():
    """El semaforo es perezoso y global: se resetea entre tests."""
    original = settings.execution_max_concurrent_runs
    docker_runner._semaforo = None
    yield
    docker_runner._semaforo = None
    settings.execution_max_concurrent_runs = original


async def _correr_con_espia(n_corridas: int, techo: int) -> int:
    """Lanza `n_corridas` a la vez y devuelve el pico real de simultaneidad."""
    settings.execution_max_concurrent_runs = techo
    docker_runner._semaforo = None

    en_vuelo = 0
    pico = 0

    async def falso_run(source_code: str, stdin: str = "") -> docker_runner.DockerRunResult:
        nonlocal en_vuelo, pico
        en_vuelo += 1
        pico = max(pico, en_vuelo)
        # Cede el control para que las demas corutinas puedan entrar si el
        # semaforo las dejara — sin esto el pico seria 1 por construccion y el
        # test pasaria sin probar nada.
        await asyncio.sleep(0.01)
        en_vuelo -= 1
        return docker_runner.DockerRunResult(
            exit_code=0, stdout="ok", stderr="", timed_out=False, compile_failed=False
        )

    original = docker_runner._run_java_sin_techo
    docker_runner._run_java_sin_techo = falso_run
    try:
        await asyncio.gather(*[docker_runner.run_java("x") for _ in range(n_corridas)])
    finally:
        docker_runner._run_java_sin_techo = original
    return pico


@pytest.mark.asyncio
async def test_nunca_se_superan_las_corridas_simultaneas_del_techo() -> None:
    """87 alumnos juntos (el piloto entero) no lanzan 87 contenedores."""
    pico = await _correr_con_espia(n_corridas=87, techo=8)
    assert pico <= 8, (
        f"pico de {pico} corridas simultaneas con techo 8. Sin techo efectivo, "
        "una comision entera satura los cores del host y las corridas mueren por "
        "wall-time — y ese timeout es indistinguible de un bucle infinito del alumno."
    )


@pytest.mark.asyncio
async def test_el_techo_se_usa_entero_no_serializa() -> None:
    """No alcanza con no pasarse: hay que APROVECHAR el techo.

    Un semaforo mal puesto —o un `await` que serialice— daria pico 1 y el test
    anterior pasaria igual, con el sandbox procesando de a uno.
    """
    pico = await _correr_con_espia(n_corridas=40, techo=8)
    assert pico == 8, (
        f"pico {pico} con techo 8: el sandbox no esta usando el paralelismo disponible"
    )


@pytest.mark.asyncio
async def test_todas_las_corridas_terminan_ninguna_se_pierde() -> None:
    """El techo encola, no descarta. Esperar es aceptable; perder la corrida no."""
    settings.execution_max_concurrent_runs = 4
    docker_runner._semaforo = None
    terminadas = 0

    async def falso_run(source_code: str, stdin: str = "") -> docker_runner.DockerRunResult:
        nonlocal terminadas
        await asyncio.sleep(0.01)
        terminadas += 1
        return docker_runner.DockerRunResult(
            exit_code=0, stdout="ok", stderr="", timed_out=False, compile_failed=False
        )

    original = docker_runner._run_java_sin_techo
    docker_runner._run_java_sin_techo = falso_run
    try:
        res = await asyncio.gather(*[docker_runner.run_java("x") for _ in range(30)])
    finally:
        docker_runner._run_java_sin_techo = original

    assert terminadas == 30
    assert all(r.exit_code == 0 for r in res)


@pytest.mark.asyncio
async def test_la_espera_no_consume_el_wall_time_del_alumno() -> None:
    """El cronometro del alumno arranca cuando SU contenedor arranca.

    Es la diferencia entre encolar y fallar: si la espera contara dentro del
    wall-time, el techo no arreglaria nada — solo moveria el timeout de lugar.
    Por eso el semaforo envuelve a `_run_java_sin_techo`, que es donde vive el
    `wait_for`, y no al reves.
    """
    settings.execution_max_concurrent_runs = 1
    docker_runner._semaforo = None
    esperas: list[float] = []

    async def falso_run(source_code: str, stdin: str = "") -> docker_runner.DockerRunResult:
        inicio = asyncio.get_running_loop().time()
        await asyncio.sleep(0.05)
        esperas.append(asyncio.get_running_loop().time() - inicio)
        return docker_runner.DockerRunResult(
            exit_code=0, stdout="", stderr="", timed_out=False, compile_failed=False
        )

    original = docker_runner._run_java_sin_techo
    docker_runner._run_java_sin_techo = falso_run
    try:
        await asyncio.gather(*[docker_runner.run_java("x") for _ in range(5)])
    finally:
        docker_runner._run_java_sin_techo = original

    # Las 5 se serializan por el techo=1, pero NINGUNA "ve" la cola: cada una
    # mide solo su propia ejecucion.
    assert len(esperas) == 5
    assert max(esperas) < 0.2, (
        f"una corrida midio {max(esperas):.3f}s de ejecucion propia con techo 1. "
        "La espera en la cola se esta filtrando dentro del presupuesto del alumno."
    )
