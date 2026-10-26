"""Espera a que Redis responda PING antes de arrancar el ctr-service.

`wait_for_tcp` sólo prueba que el puerto acepte conexiones. Redis puede tenerlo
abierto y aun así contestar `LOADING` mientras carga el dataset en memoria
(BusyLoadingError): paso en prod el 2026-10-16 y el 2026-10-23 tras reiniciar
el stack, y los 8 workers murieron al crear el consumer group. "Listo" es que
`PING` devuelva PONG, autenticado con las credenciales de `REDIS_URL`.

Uso (docker-entrypoint.sh):
    python -m ctr_service.workers.wait_redis --timeout 120 --interval 2

Exit 0 si Redis respondió; 1 si se agotó el tope (con la última causa en stderr).
Los logs son ASCII a propósito: el stdout del contenedor no siempre es UTF-8.
"""

from __future__ import annotations

import argparse
import contextlib
import logging
import sys
import time
from collections.abc import Callable, Sequence
from typing import Any

import redis

from ctr_service.config import settings

logger = logging.getLogger(__name__)


class RedisNoListoError(RuntimeError):
    """Redis no respondió PING dentro del tope; el mensaje trae la última causa."""


def esperar_redis(
    client_factory: Callable[[], Any],
    *,
    timeout: float,
    interval: float,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> int:
    """Hace PING hasta obtener respuesta; devuelve la cantidad de intentos.

    Cualquier `RedisError` u `OSError` (conexión, DNS, auth, LOADING) cuenta
    como "todavía no listo". Al superar `timeout` levanta `RedisNoListoError`.
    """
    inicio = clock()
    intento = 0
    ultima_causa = "sin intentos"
    while True:
        intento += 1
        try:
            cliente = client_factory()
            try:
                if cliente.ping():
                    return intento
                ultima_causa = "PING no devolvio PONG"
            finally:
                with contextlib.suppress(Exception):  # cerrar no debe tapar la causa
                    cliente.close()
        except (redis.RedisError, OSError) as exc:
            ultima_causa = f"{type(exc).__name__}: {exc}"
        logger.info("esperando Redis... intento %d: %s", intento, ultima_causa)
        if clock() - inicio + interval > timeout:
            raise RedisNoListoError(
                f"Redis no respondio PING en {timeout:g}s ({intento} intentos): {ultima_causa}"
            )
        sleep(interval)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Espera a que Redis responda PING")
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--interval", type=float, default=2.0)
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="[ctr-entrypoint] %(message)s")
    try:
        intentos = esperar_redis(
            lambda: redis.from_url(settings.redis_url, socket_connect_timeout=2),
            timeout=args.timeout,
            interval=args.interval,
        )
    except RedisNoListoError as exc:
        print(f"[ctr-entrypoint] ERROR: {exc}", file=sys.stderr)
        return 1
    logger.info("Redis disponible (PING OK) tras %d intento(s)", intentos)
    return 0


if __name__ == "__main__":
    sys.exit(main())
