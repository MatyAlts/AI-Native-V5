"""Tests de `wait_redis`: el arranque espera PING OK, no "puerto abierto".

Incidente 2026-10-16 y 2026-10-23: Redis tenia el puerto abierto pero
respondia `LOADING` (BusyLoadingError); `wait_for_tcp` lo dio por listo y los 8
workers murieron. Aca no hay Redis real: un fake client, sleep y clock
inyectados para no esperar.
"""

from __future__ import annotations

import logging

import pytest
import redis
from ctr_service.workers import wait_redis
from ctr_service.workers.wait_redis import RedisNoListoError, esperar_redis


class _FakeClock:
    """Reloj que avanza sólo cuando se duerme (sleep inyectado)."""

    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


class _FakeRedis:
    """Cliente cuyo `ping` consume una lista de resultados (excepción o valor)."""

    def __init__(self, resultados: list[object]) -> None:
        self._resultados = list(resultados)
        self.pings = 0

    def ping(self) -> bool:
        self.pings += 1
        r = self._resultados.pop(0) if len(self._resultados) > 1 else self._resultados[0]
        if isinstance(r, BaseException):
            raise r
        return bool(r)

    def close(self) -> None:
        pass


def test_pong_al_primer_intento_es_exito() -> None:
    clock = _FakeClock()
    cliente = _FakeRedis([True])

    intentos = esperar_redis(
        lambda: cliente, timeout=120, interval=2, sleep=clock.sleep, clock=clock
    )

    assert intentos == 1
    assert cliente.pings == 1
    assert clock.sleeps == []


def test_loading_dos_veces_y_luego_pong_reintenta_y_loguea(
    caplog: pytest.LogCaptureFixture,
) -> None:
    clock = _FakeClock()
    loading = redis.BusyLoadingError("Redis is loading the dataset in memory")
    cliente = _FakeRedis([loading, loading, True])

    with caplog.at_level(logging.INFO, logger="ctr_service.workers.wait_redis"):
        intentos = esperar_redis(
            lambda: cliente, timeout=120, interval=2, sleep=clock.sleep, clock=clock
        )

    assert intentos == 3
    assert clock.sleeps == [2, 2]
    reintentos = [r.getMessage() for r in caplog.records if "BusyLoadingError" in r.getMessage()]
    assert len(reintentos) == 2
    assert "intento 1" in reintentos[0]
    assert "intento 2" in reintentos[1]


def test_connection_error_siempre_falla_al_agotar_tope_con_la_causa() -> None:
    clock = _FakeClock()
    cliente = _FakeRedis([redis.ConnectionError("Connection refused")])

    with pytest.raises(RedisNoListoError) as exc:
        esperar_redis(lambda: cliente, timeout=10, interval=2, sleep=clock.sleep, clock=clock)

    msg = str(exc.value)
    assert "Redis" in msg
    assert "ConnectionError" in msg
    assert "Connection refused" in msg
    assert cliente.pings >= 2  # reintentó, no se rindió al primero


def test_authentication_error_no_es_listo_y_la_causa_queda_en_el_mensaje() -> None:
    clock = _FakeClock()
    cliente = _FakeRedis([redis.AuthenticationError("invalid password")])

    with pytest.raises(RedisNoListoError) as exc:
        esperar_redis(lambda: cliente, timeout=6, interval=2, sleep=clock.sleep, clock=clock)

    assert "AuthenticationError" in str(exc.value)
    assert "invalid password" in str(exc.value)


def test_error_al_construir_el_cliente_tambien_cuenta_como_no_listo() -> None:
    """DNS roto (gaierror es OSError) al crear/conectar: se reintenta."""
    clock = _FakeClock()
    llamadas = {"n": 0}

    def factory() -> _FakeRedis:
        llamadas["n"] += 1
        if llamadas["n"] < 3:
            raise OSError("Name or service not known")
        return _FakeRedis([True])

    intentos = esperar_redis(factory, timeout=120, interval=2, sleep=clock.sleep, clock=clock)

    assert intentos == 3


# ── main(): exit codes ────────────────────────────────────────────────────


def test_main_exit_0_cuando_redis_responde(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(wait_redis, "esperar_redis", lambda *a, **k: 1)

    assert wait_redis.main(["--timeout", "5", "--interval", "1"]) == 0


def test_main_exit_1_con_tope_agotado_y_mensaje_a_stderr(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def _agotado(*a: object, **k: object) -> int:
        raise RedisNoListoError("Redis no respondio PING en 5s: ConnectionError: boom")

    monkeypatch.setattr(wait_redis, "esperar_redis", _agotado)

    assert wait_redis.main(["--timeout", "5", "--interval", "1"]) == 1
    assert "ConnectionError: boom" in capsys.readouterr().err


def test_main_pasa_timeout_e_interval_a_esperar_redis(monkeypatch: pytest.MonkeyPatch) -> None:
    capturado: dict[str, float] = {}

    def _espiar(factory: object, *, timeout: float, interval: float, **k: object) -> int:
        capturado.update(timeout=timeout, interval=interval)
        return 1

    monkeypatch.setattr(wait_redis, "esperar_redis", _espiar)
    wait_redis.main(["--timeout", "33", "--interval", "7"])

    assert capturado == {"timeout": 33, "interval": 7}
