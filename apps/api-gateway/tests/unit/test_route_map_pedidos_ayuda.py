"""El gateway tiene que exponer `/api/v1/pedidos-ayuda` hacia evaluation-service.

Sin la entrada en `ROUTE_MAP` el endpoint queda inalcanzable desde los
frontends: el servicio responde, pero el gateway devuelve 404 antes de llegar.
"""

from __future__ import annotations

import pytest
from api_gateway.config import settings
from api_gateway.routes.proxy import resolve_target


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/pedidos-ayuda",
        "/api/v1/pedidos-ayuda/mios",
        "/api/v1/pedidos-ayuda/3f2b1c1e-0000-0000-0000-000000000000/resolver",
    ],
)
def test_pedidos_ayuda_rutea_a_evaluation(path: str) -> None:
    assert resolve_target(path) == settings.evaluation_service_url


def test_no_se_come_otros_prefijos_de_evaluation() -> None:
    assert resolve_target("/api/v1/entregas") == settings.evaluation_service_url
