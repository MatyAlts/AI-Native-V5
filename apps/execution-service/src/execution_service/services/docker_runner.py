"""Ejecucion de Java en un contenedor Docker efimero, sin privilegios (ADR-060).

Motor de ejecucion del servicio. Reemplaza a Judge0, que quedo superado por el
ADR-060 tras medir el spike.

## Por que se cambio

Judge0 resulto tener dos costos que el ADR no anticipo del todo:

  - `isolate` exige **cgroups v1**. Las distros modernas traen v2, asi que no
    levanta ni en la maquina de desarrollo ni en un VPS reciente sin tocar GRUB.
  - Exige **contenedor privilegiado**, que es lo que obliga a sacarlo del VPS de
    produccion (D2 del ADR) y por lo tanto a pagar cloud o un servidor aparte.

Un `docker run` plano no tiene ninguno de los dos problemas: anda con cgroups
v2 y **no necesita privilegios**. El aislamiento pasa a ser el de Docker — el
mismo que la plataforma ya usa para sus 12 servicios — en vez de una superficie
nueva.

## Lo que este modulo NO resuelve

**Quien puede invocar `docker run`.** Si el execution-service monta
`/var/run/docker.sock`, eso equivale a root en el host y seria peor que el
problema original. Las salidas son un socket-proxy que solo permita `run` sobre
una imagen fija, o correr esta pieza fuera de contenedor. Es el gate del ADR-060:
hasta que este resuelto, la ejecucion NO se habilita en produccion.

## Controles aplicados

Todos desde el arranque, no agregados despues:

  --network=none              sin salida de red (control C2 del ADR-059)
  --read-only + tmpfs         sin escritura al filesystem salvo /tmp acotado
  --cap-drop=ALL              sin capabilities
  --security-opt no-new-privileges   no puede escalar via setuid
  --user                      no corre como root dentro del contenedor
  --memory / --cpus / --pids-limit   limites por corrida, explicitos
  timeout externo             `docker run` tambien se puede colgar
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from execution_service.config import settings
from execution_service.services.sandbox_types import SandboxResult, SandboxStatus

logger = logging.getLogger(__name__)

# La imagen sale de config: en produccion se pinea por digest (control C1).

# Usuario sin privilegios dentro del contenedor. 65534 = nobody.
CONTAINER_USER = "65534:65534"

# ── Techo de corridas simultaneas ────────────────────────────────────────────
#
# Sin esto, N alumnos apretando "Ejecutar" a la vez lanzan N contenedores a la
# vez. Compilar Java es CPU-bound, asi que se pelean por los cores del host y
# cada corrida tarda mas — hasta pasarse del wall-time y morir por timeout.
#
# Medido sobre 4 CPUs (el hardware del VPS), con la imagen ya bajada:
#
#     30 concurrentes -> 8,3 s, 30/30 ok   (83% del presupuesto de 10 s)
#     40 concurrentes -> 28 de 40 MUEREN por timeout
#     60 concurrentes -> mueren las 60
#
# No degrada suave: se cae de golpe entre 30 y 40.
#
# Y el modo de falla es peor que "lento". Un timeout por contencion del host es
# INDISTINGUIBLE de un bucle infinito del alumno: los dos devuelven
# `timed_out=True` -> `CaseStatus.ERROR` -> cuenta como fallo -> N3. O sea que
# bajo carga, alumnos que escribieron codigo correcto quedan registrados en el
# corpus como que fallaron, por culpa del servidor. Es el mismo problema que
# `ctr_emitter` evita para el fallo de infraestructura, deflactando en vez de
# inflar — y tampoco se nota, porque el evento se ve igual que uno legitimo.
#
# Con el techo puesto, el excedente ESPERA en vez de morir. Esperar unos
# segundos es honesto; fallar y quedar mal anotado en el corpus, no. El endpoint
# ya es asincrono con consulta de estado (D2), asi que la espera no congela nada
# del lado del alumno.
#
# El techo vive ACA y no en el execution-service a proposito: este modulo corre
# dentro del runner, que es el unico componente con acceso al socket de Docker
# (ADR-060 D3). Es el unico punto por el que pasan todas las corridas — un
# limite en el servicio no se sostendria con mas de una replica.
#
# ⚠️ El semaforo es POR PROCESO. Hoy se sostiene porque el runner corre con un
# solo worker (`Dockerfile.runner` no pasa `--workers`, y uvicorn default es 1).
# El dia que alguien agregue `--workers N`, el techo real pasa a ser 8*N sin que
# nadie toque el 8 — y el sandbox vuelve al precipicio medido. Si hace falta
# escalar el runner, el techo tiene que salir del proceso (Redis) o el numero
# tiene que dividirse por la cantidad de workers. `verificar_configuracion_segura`
# no lo puede detectar: el proceso no sabe cuantos hermanos tiene.
_semaforo: asyncio.Semaphore | None = None


def _obtener_semaforo() -> asyncio.Semaphore:
    """Semaforo perezoso: se crea en el loop que corre, no al importar."""
    global _semaforo
    if _semaforo is None:
        _semaforo = asyncio.Semaphore(settings.execution_max_concurrent_runs)
    return _semaforo


@dataclass(frozen=True)
class DockerRunResult:
    """Resultado crudo de una corrida. Se mapea al formato del sistema aparte."""

    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool
    compile_failed: bool


def _acotar(crudo: bytes) -> str:
    """Corta la salida en `execution_max_output_bytes` y lo AVISA.

    POR QUE EXISTE (reporte de una alumna de Prog 2, 2026-09-01)
    -----------------------------------------------------------
    Nada acotaba la salida. `proc.communicate()` acumula todo lo que el programa
    escriba, y el modo de falla mas comun de quien recien arranca —un bucle que
    imprime— produce cientos de MB en los 10 segundos de wall-time. Esa cadena
    despues viaja entera: a Redis con TTL de 600s, de ahi al navegador, y el
    navegador la mete en el DOM.

    O sea que un `while(true)` de un alumno podia:
      - inflar Redis en el mismo VPS que ya corre al 82,8% en reposo;
      - y colgarle la pestaña al alumno al renderizarla.

    Lo segundo importa para el sintoma reportado: la pestaña colgada se ve
    exactamente como "la plataforma se quedo en un bucle infinito", aunque el
    bucle sea del programa y ya lo hayamos matado.

    La marca NO es decorativa. Una salida cortada en silencio se lee como
    completa, y el alumno buscaria el error en la logica de su programa en vez
    de en la cantidad que imprime.

    LO QUE ESTO **NO** ARREGLA
    --------------------------
    El pico de memoria del proceso HOST durante la corrida sigue sin techo:
    `communicate()` ya leyo todo antes de que esta funcion vea un byte. Acotarlo
    de verdad pide leer el pipe de a pedazos, o cortar adentro del contenedor
    (`| head -c N`), que cambia el codigo de salida que ve `to_sandbox_result` y
    merece su propio cambio, medido contra Docker real. Queda anotado, no
    resuelto: esto acota lo que SALE del servicio, que es lo que llega al alumno
    y a Redis.
    """
    limite = settings.execution_max_output_bytes
    if len(crudo) <= limite:
        return crudo.decode("utf-8", errors="replace")
    # Se corta sobre los BYTES y se decodifica con `replace`: partir a la mitad
    # un caracter multibyte es normal aca, y `replace` lo vuelve un simbolo en
    # vez de una excepcion.
    texto = crudo[:limite].decode("utf-8", errors="replace")
    kb = len(crudo) // 1024
    return (
        f"{texto}\n\n"
        f"[... salida cortada: tu programa imprimio {kb} KB y solo se muestran "
        f"los primeros {limite // 1024} KB. Si no esperabas tanta salida, "
        f"probablemente tengas un bucle que imprime y nunca termina.]"
    )


def _docker_args(source_code: str) -> list[str]:
    return [
        "docker",
        "run",
        "--rm",
        # Sin `-i` el contenedor NO recibe stdin: lo que `communicate()` escribe
        # en el pipe del CLI se pierde, y el programa del alumno arranca con la
        # entrada vacia. El sintoma es un NoSuchElementException de Scanner que
        # se lee como error del alumno y no del sandbox, justo en los ejercicios
        # que leen entrada — o sea la mayoria de los del PID.
        #
        # NO va `-t`: un TTY mezcla stdout con stderr y nos rompe la comparacion
        # contra la salida esperada.
        "-i",
        # C2 del ADR-059: el codigo del alumno NO tiene salida de red.
        "--network=none",
        f"--memory={settings.execution_memory_limit_kb}k",
        # CPUs por contenedor, explicito. NO derivado del limite de tiempo: eso
        # acoplaba dos cosas independientes y hacia que subir el timeout
        # multiplicara el consumo de CPU en silencio, tirando abajo el techo de
        # concurrencia. Ver el comentario en `config.execution_cpu_shares`.
        f"--cpus={settings.execution_cpu_shares:.2f}",
        f"--pids-limit={settings.execution_max_processes}",
        "--read-only",
        # Escribible pero acotado: javac necesita escribir los .class. `mode=1777`
        # es lo que hace falta para que el usuario sin privilegios pueda escribir
        # — el tmpfs se monta como root y sin esto `cp` da "Permission denied".
        "--tmpfs=/work:rw,size=64m,exec,mode=1777",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges",
        f"--user={CONTAINER_USER}",
        # El fuente viaja por ENV, NO por bind mount. Un `-v /tmp/exec-xxx:/src`
        # lo resuelve el DAEMON, y el daemon vive en el host: con el runner
        # adentro de un contenedor esa ruta no existe del otro lado, Docker monta
        # un directorio vacio SIN error, y el `cp` falla con "No such file or
        # directory". En local no se ve, porque ahi el runner no esta
        # containerizado y la ruta si es del host — o sea que la unica topologia
        # que rompe es exactamente la de produccion.
        #
        # Detectado el 2026-08-05 corriendo el spike sobre el despliegue real:
        # 0/30 corridas exitosas, y aun asi el resto del script reportaba OK
        # (el bucle infinito "se cortaba" en 0,32s y la red figuraba bloqueada,
        # porque nunca se ejecuto codigo). Un control sobre algo que no corrio
        # siempre pasa.
        #
        # Por ENV anda igual containerizado o no, que es lo que cierra la
        # asimetria dev/prod de raiz.
        "-e",
        f"SRC={source_code}",
        "-w",
        "/work",
        settings.java_image,
        "sh",
        "-c",
        # Se compila y ejecuta en /work (tmpfs). El exit code 101 se reserva
        # para "no compilo", que es distinto de "el programa fallo".
        'printf %s "$SRC" > Main.java && javac Main.java 2>&1 || exit 101; java Main',
    ]


async def run_java(source_code: str, stdin: str = "") -> DockerRunResult:
    """Compila y ejecuta un archivo Java unico en un contenedor aislado.

    Espera turno si ya hay `execution_max_concurrent_runs` corridas en vuelo.
    La espera NO consume el wall-time del alumno: el cronometro arranca recien
    cuando se lanza el contenedor. Es la diferencia entre encolar y fallar.
    """
    semaforo = _obtener_semaforo()
    if semaforo.locked():
        logger.info(
            "sandbox_saturado techo=%s — la corrida espera turno",
            settings.execution_max_concurrent_runs,
        )
    async with semaforo:
        return await _run_java_sin_techo(source_code, stdin)


async def _run_java_sin_techo(source_code: str, stdin: str = "") -> DockerRunResult:
    """El cuerpo real. Separado para que el wall-time NO cuente la espera."""
    proc = await asyncio.create_subprocess_exec(
        *_docker_args(source_code),
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        out, err = await asyncio.wait_for(
            proc.communicate(stdin.encode()),
            timeout=settings.execution_wall_time_limit_seconds,
        )
    except TimeoutError:
        # `docker run` tambien se puede colgar: el limite del contenedor no
        # cubre el caso de que el daemon no responda.
        proc.kill()
        await proc.wait()
        return DockerRunResult(
            exit_code=-1, stdout="", stderr="", timed_out=True, compile_failed=False
        )

    code = proc.returncode or 0
    return DockerRunResult(
        exit_code=code,
        stdout=_acotar(out),
        stderr=_acotar(err),
        timed_out=False,
        # 101 es el codigo que el comando reserva para fallo de compilacion.
        compile_failed=code == 101,
    )


# ── Comparacion de salidas (JAVA-1) ──────────────────────────────────────────
#
# GEMELO OBLIGADO: `normalizarSalida` / `salidaCoincide` en
# `packages/contracts/src/comparacionSalida.ts`.
#
# Hay DOS implementaciones porque hay dos lenguajes, no dos runtimes: este
# modulo en Python, y el de TypeScript que importan LOS TRES frontends. Ese
# "tres" es la correccion del 2026-08-28: este comentario decia "DOS
# correctores" y habia un tercero sin declarar —el `normalize()` propio de
# `web-teacher/src/lib/pyodideRunner.ts`, el que pinta el verde cuando el
# docente prueba un ejercicio ANTES de asignarlo— que usaba el `\s` de JS y
# recortaba 24 code points en vez de 28. Un `expected_output` pegado con BOM
# le daba verde al docente y WRONG_ANSWER en silencio a toda la cohorte. Por
# eso la copia de TS ahora vive en `packages/contracts` y se importa: una
# implementacion por lenguaje, no una por pantalla.
#
# Si las normalizaciones se separan, el MISMO codigo aprueba en un lenguaje y
# falla en el otro, y los conteos `passed`/`failed` que viajan al CTR dejan de
# ser comparables entre cohortes. Cualquier cambio acá va tambien allá, y al
# reves. El fixture `tests/fixtures/paridad-salida.json` es el que lo ata: lo
# leen las suites de los dos lenguajes.

# Los blancos que se recortan al final de cada linea son los de `str.rstrip()`
# sin argumentos, o sea `str.isspace()`. ESTE LADO ES LA REFERENCIA: el gemelo
# de JavaScript enumera a mano ese mismo set (`CODIGOS_BLANCOS` en
# `packages/contracts/src/comparacionSalida.ts`) porque el `\s` de JS NO es `isspace()` de Python —
# `\s` incluye `﻿`, que Python no considera blanco, y le faltan `\x1c-\x1f`
# y `\x85`, que Python si.
#
# Y es `isspace()` y no un set mas chico porque el corrector viejo era
# `str.strip()` en los dos runners: recortar menos ENDURECE, hace fallar casos
# que pasaban, sobre conteos que ya viajaron al CTR. El caso realista no es
# teorico — el docente pega el `expected_output` desde Word y le entra un
# espacio duro (` `).
#
# Aca vivia una constante `_BLANCOS_FINALES = " \t\f\v"` de un intento anterior
# que quedo MUERTA (cero referencias) cuando la paridad se resolvio al reves:
# alineando el JS a `isspace()` en vez de achicar los dos. Su comentario decia
# "no `str.rstrip()` sin argumentos" justo al lado del `rstrip()` sin argumentos
# de abajo, o sea que prohibia exactamente lo que el codigo hace y lo que hoy es
# correcto. Se borro; si volves a necesitar un set explicito de este lado,
# ordenalo con el gemelo primero.


def normalize_output(text: str) -> str:
    """Normaliza una salida para compararla. Funcion PURA.

    1. Unifica los fines de linea (``\\r\\n`` y ``\\r`` sueltos) a ``\\n``.
    2. Recorta los blancos al final de CADA linea.
    3. Descarta las lineas en blanco del final.

    Lo que NO se toca, a proposito: mayusculas/minusculas, tildes, espacios
    INTERNOS de una linea y lineas en blanco INTERMEDIAS. Eso es contenido que
    el alumno decidio imprimir; tolerarlo seria corregir mal, no corregir menos
    literal.

    Se descartan las lineas en blanco de los DOS extremos, no solo las del
    final. La comparacion anterior (``strip()`` sobre el texto entero) tambien
    perdonaba las iniciales, y quedarse corto endurecia el corrector: un caso
    que pasaba solo por eso empezaba a fallar.

    El error no es simetrico. Endurecer perjudica al alumno; mantener la
    tolerancia vieja no perjudica a nadie. Y hay conteos que YA viajaron al CTR
    con el criterio viejo — cambiar veredictos al re-correr seria reescribir
    evidencia de la tesis.
    """
    lineas = [
        linea.rstrip() for linea in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    ]
    while lineas and lineas[-1] == "":
        lineas.pop()
    while lineas and lineas[0] == "":
        lineas.pop(0)
    if lineas:
        lineas[0] = lineas[0].lstrip()
    return "\n".join(lineas)


def outputs_match(actual: str, expected: str) -> bool:
    """``True`` si la salida obtenida equivale a la esperada. Funcion PURA.

    Solo compara. La decision de si hay algo que comparar (``expected_output``
    ``None`` significa "con terminar bien alcanza", caso ``junit_assert``) se
    toma antes de llamar acá — esa semantica NO se comparte con el navegador,
    donde el mismo nulo significa "no imprime nada". Lo unico compartido, y lo
    unico que tiene que estar en paridad, es la normalizacion.
    """
    return normalize_output(actual) == normalize_output(expected)


def to_sandbox_result(run: DockerRunResult, expected_output: str | None) -> SandboxResult:
    """Traduce la corrida cruda al tipo comun del servicio.

    La comparacion contra `expected_output` se hace acá y no en el contenedor: el
    contenedor solo ejecuta, la evaluacion es nuestra. Judge0 lo hacia adentro;
    hacerlo afuera es mas simple de auditar.
    """
    if run.timed_out:
        return SandboxResult(
            status=SandboxStatus.TIME_LIMIT_EXCEEDED,
            stdout=run.stdout,
            stderr=run.stderr,
            compile_output="",
            time_seconds=settings.execution_wall_time_limit_seconds,
            memory_kb=None,
        )

    if run.compile_failed:
        return SandboxResult(
            status=SandboxStatus.COMPILATION_ERROR,
            stdout="",
            stderr="",
            # javac escribe a stdout por como se arma el comando.
            compile_output=run.stdout or run.stderr,
            time_seconds=None,
            memory_kb=None,
        )

    if run.exit_code != 0:
        # El programa compilo pero termino mal: excepcion, exit() distinto de 0,
        # o lo mato el limite de memoria.
        return SandboxResult(
            status=SandboxStatus.RUNTIME_ERROR_NZEC,
            stdout=run.stdout,
            stderr=run.stderr,
            compile_output="",
            time_seconds=None,
            memory_kb=None,
        )

    # Corrio bien. Si el caso declara salida esperada, se compara con
    # `outputs_match` — mismo criterio, caracter por caracter, que el runner de
    # Pyodide del web-student (ver el comentario de `normalize_output`).
    if expected_output is not None:
        ok = outputs_match(run.stdout, expected_output)
        status = SandboxStatus.ACCEPTED if ok else SandboxStatus.WRONG_ANSWER
    else:
        # Sin `expected` no hay nada que comparar: que haya terminado con exito
        # es el criterio (caso `junit_assert`, donde el assert que falla hace
        # que el programa termine con codigo distinto de cero).
        status = SandboxStatus.ACCEPTED

    return SandboxResult(
        status=status,
        stdout=run.stdout,
        stderr=run.stderr,
        compile_output="",
        time_seconds=None,
        memory_kb=None,
    )
