"""Tests del endpoint de salud."""

from unittest.mock import AsyncMock, patch

import pytest
from ctr_service.main import app
from httpx import ASGITransport, AsyncClient, Response


@pytest.fixture
async def client() -> AsyncClient:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def test_health_ready_ok_when_deps_up(client: AsyncClient) -> None:
    with (
        patch("ctr_service.routes.health._check_db", new=AsyncMock(return_value="ok")),
        patch("ctr_service.routes.health._check_redis", new=AsyncMock(return_value="ok")),
        patch("ctr_service.routes.health._check_workers", new=AsyncMock(return_value="ok")),
    ):
        response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "ctr-service"
    assert data["status"] == "ready"
    assert data["checks"] == {"db": "ok", "redis": "ok", "workers": "ok"}


async def test_health_ready_degraded_when_db_down(client: AsyncClient) -> None:
    with (
        patch(
            "ctr_service.routes.health._check_db",
            new=AsyncMock(return_value="fail: ConnectionRefusedError"),
        ),
        patch("ctr_service.routes.health._check_redis", new=AsyncMock(return_value="ok")),
        patch("ctr_service.routes.health._check_workers", new=AsyncMock(return_value="ok")),
    ):
        response = await client.get("/health/ready")
    assert response.status_code == 503
    data = response.json()
    assert data["status"] == "degraded"
    assert data["checks"]["db"].startswith("fail")
    assert data["checks"]["redis"] == "ok"


async def test_health_ready_degraded_when_redis_down(client: AsyncClient) -> None:
    with (
        patch("ctr_service.routes.health._check_db", new=AsyncMock(return_value="ok")),
        patch(
            "ctr_service.routes.health._check_redis",
            new=AsyncMock(return_value="fail: TimeoutError"),
        ),
        patch("ctr_service.routes.health._check_workers", new=AsyncMock(return_value="ok")),
    ):
        response = await client.get("/health/ready")
    assert response.status_code == 503
    data = response.json()
    assert data["status"] == "degraded"
    assert data["checks"]["redis"].startswith("fail")


async def test_health_live(client: AsyncClient) -> None:
    response = await client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "alive"}


async def test_root(client: AsyncClient) -> None:
    response = await client.get("/")
    assert response.status_code == 200
    assert response.json()["service"] == "ctr-service"


# ── check `workers`: heartbeat por partición ──────────────────────────────
# Incidente 2026-10-16 / 2026-10-23: HTTP vivo (202) con los 8 workers muertos y
# nada que lo dijera. Readiness lee `ctr:worker:heartbeat:{p}` de las 8 particiones.

HB = "ctr:worker:heartbeat:"


def _redis_con_heartbeats(vivas: set[int] | None = None, *, extra: dict[str, str] | None = None):
    """Cliente Redis fake cuyo MGET responde según qué keys 'existen'."""
    store = {f"{HB}{p}": "2026-10-24T00:00:00 worker" for p in (vivas or set())}
    store.update(extra or {})

    class _Fake:
        async def mget(self, keys: list[str]) -> list[str | None]:
            return [store.get(k) for k in keys]

        async def aclose(self) -> None:
            pass

    return _Fake()


async def _ready_con_redis_fake(client: AsyncClient, fake) -> Response:
    with (
        patch("ctr_service.routes.health._check_db", new=AsyncMock(return_value="ok")),
        patch("ctr_service.routes.health._check_redis", new=AsyncMock(return_value="ok")),
        patch("ctr_service.routes.health.redis.from_url", return_value=fake),
    ):
        return await client.get("/health/ready")


async def test_workers_ok_con_los_8_heartbeats(client: AsyncClient) -> None:
    response = await _ready_con_redis_fake(client, _redis_con_heartbeats(set(range(8))))

    assert response.status_code == 200
    assert response.json()["checks"]["workers"] == "ok"


async def test_workers_ninguno_vivo_da_503_nombrando_las_8_particiones(
    client: AsyncClient,
) -> None:
    response = await _ready_con_redis_fake(client, _redis_con_heartbeats(set()))

    assert response.status_code == 503
    data = response.json()
    assert data["status"] == "degraded"
    detalle = data["checks"]["workers"]
    assert detalle == "fail: sin heartbeat p0,p1,p2,p3,p4,p5,p6,p7"


async def test_workers_falta_solo_p5_da_503_nombrando_p5(client: AsyncClient) -> None:
    response = await _ready_con_redis_fake(client, _redis_con_heartbeats(set(range(8)) - {5}))

    assert response.status_code == 503
    assert response.json()["checks"]["workers"] == "fail: sin heartbeat p5"


async def test_live_sigue_200_con_workers_caidos(client: AsyncClient) -> None:
    with patch(
        "ctr_service.routes.health._check_workers",
        new=AsyncMock(return_value="fail: sin heartbeat p0,p1,p2,p3,p4,p5,p6,p7"),
    ):
        response = await client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "alive"}


async def test_workers_keys_con_otro_prefijo_o_particion_fuera_de_rango_no_cuentan(
    client: AsyncClient,
) -> None:
    ajenas = {
        "tutor:worker:heartbeat:0": "x",  # otro prefijo
        f"{HB}8": "x",  # fuera de rango (NUM_PARTITIONS=8 => 0..7)
        f"{HB}99": "x",
    }
    response = await _ready_con_redis_fake(client, _redis_con_heartbeats({1, 2}, extra=ajenas))

    assert response.status_code == 503
    assert response.json()["checks"]["workers"] == "fail: sin heartbeat p0,p3,p4,p5,p6,p7"


async def test_workers_error_de_redis_devuelve_fail_tipo_sin_excepcion(
    client: AsyncClient,
) -> None:
    import redis as redis_lib

    class _Roto:
        async def mget(self, keys: list[str]) -> list[str | None]:
            raise redis_lib.ConnectionError("down")

        async def aclose(self) -> None:
            pass

    response = await _ready_con_redis_fake(client, _Roto())

    assert response.status_code == 503
    assert response.json()["checks"]["workers"] == "fail: ConnectionError"
