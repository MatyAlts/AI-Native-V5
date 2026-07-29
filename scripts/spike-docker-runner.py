"""Spike de carga: mide el runner Docker contra la concurrencia real.

El escenario es el del design: una comision entera ejecutando en la misma
ventana. NO un caso comodo.
"""

import asyncio
import statistics
import sys
import time

sys.path.insert(0, "apps/execution-service/src")

from execution_service.services.docker_runner import run_java

OK = 'public class Main { public static void main(String[] a){ System.out.println("Hola"); } }'
MAL = 'public class Main { public static void main(String[] a){ System.out.println("x") } }'
LOOP = "public class Main { public static void main(String[] a){ while(true){} } }"


async def cronometrar(src: str):
    t0 = time.perf_counter()
    r = await run_java(src)
    return time.perf_counter() - t0, r


async def main():
    print("=== 1. Correctitud ===")
    for nombre, src in [("compila y corre", OK), ("no compila", MAL)]:
        dt, r = await cronometrar(src)
        estado = "COMPILE_ERROR" if r.compile_failed else f"exit={r.exit_code}"
        salida = r.stdout.strip()[:40] or r.stderr.strip()[:60]
        print(f"  {nombre:18} {dt:5.2f}s  {estado:15} {salida!r}")

    print("\n=== 2. El bucle infinito se corta ===")
    dt, r = await cronometrar(LOOP)
    print(f"  bucle infinito     {dt:5.2f}s  timed_out={r.timed_out}")

    print("\n=== 3. Sin red (control C2) ===")
    NET = (
        "import java.net.*; public class Main { public static void main(String[] a) "
        'throws Exception { System.out.println(new URL("http://example.com").openStream() '
        "!= null); } }"
    )
    dt, r = await cronometrar(NET)
    bloqueado = r.exit_code != 0 or "Exception" in r.stderr or "Exception" in r.stdout
    print(f"  salida a internet  {dt:5.2f}s  bloqueada={bloqueado}")
    if not bloqueado:
        print(f"    !! FUGA: {r.stdout[:120]}")

    print("\n=== 4. Carga: una comision entera ejecutando junta ===")
    for n in (10, 30):
        t0 = time.perf_counter()
        tiempos = await asyncio.gather(*[cronometrar(OK) for _ in range(n)])
        total = time.perf_counter() - t0
        dts = [d for d, _ in tiempos]
        ok = sum(1 for _, r in tiempos if r.exit_code == 0)
        print(
            f"  {n:2} concurrentes: total {total:5.2f}s | "
            f"p50 {statistics.median(dts):4.2f}s | max {max(dts):5.2f}s | ok {ok}/{n}"
        )


asyncio.run(main())
