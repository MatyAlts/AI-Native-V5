"""El password del docente NO puede volver en una respuesta.

Este archivo existe por un bloqueante encontrado en revision: pydantic v2
incluye el valor que causo el error en cada entrada de `exc.errors()` — para
un error a nivel modelo, ese valor es EL BODY ENTERO. El 422 de
`POST /activeia/credenciales` devolvia la contrasena en claro.

Lo que lo hacia grave no era el 422 en si, sino que **la validacion del body
corre ANTES del cuerpo del endpoint**: apagar el kill switch no lo frenaba, y
el prefijo ya esta en el ROUTE_MAP del gateway.

Los tests van contra la app REAL via TestClient, no contra el schema: lo que
hay que probar es lo que sale por el cable.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from evaluation_service.auth import get_db
from evaluation_service.auth.dependencies import User, get_current_user
from evaluation_service.main import app
from fastapi.testclient import TestClient

SECRETO = "P4ssw0rd-SECRETO-nunca-debe-verse"


@pytest.fixture
def client():
    """Cliente con auth y DB fuera del medio: lo que se prueba es la
    serializacion del error, que ocurre antes de tocar cualquiera de las dos."""

    def _user() -> User:
        return User(
            id=uuid4(),
            tenant_id=uuid4(),
            email="d@utn.edu.ar",
            roles=frozenset({"docente"}),
            realm="utn",
        )

    app.dependency_overrides[get_current_user] = _user
    app.dependency_overrides[get_db] = MagicMock
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


class TestElPasswordNoVuelveEnEl422:
    def test_body_sin_username(self, client: TestClient) -> None:
        """Error a nivel modelo: el `input` de pydantic es el body COMPLETO."""
        r = client.post("/api/v1/activeia/credenciales", json={"password": SECRETO})
        assert r.status_code == 422
        assert SECRETO not in r.text

    def test_password_demasiado_largo(self, client: TestClient) -> None:
        """Error sobre el campo: el `input` de pydantic es el password mismo."""
        r = client.post(
            "/api/v1/activeia/credenciales",
            json={"username": "u", "password": SECRETO + "x" * 300},
        )
        assert r.status_code == 422
        assert SECRETO not in r.text

    def test_password_vacio(self, client: TestClient) -> None:
        r = client.post("/api/v1/activeia/credenciales", json={"username": "u", "password": ""})
        assert r.status_code == 422
        assert "password" in r.text  # el campo se nombra...
        assert '"input"' not in r.text  # ...pero el valor no se devuelve

    def test_tampoco_con_el_kill_switch_apagado(self, client: TestClient) -> None:
        """El caso que volvia esto bloqueante: `_assert_habilitado()` vive en
        el cuerpo del endpoint, y la validacion del body corre antes."""
        with patch("evaluation_service.routes.activeia.settings") as st:
            st.activeia_enabled = False
            r = client.post("/api/v1/activeia/credenciales", json={"password": SECRETO})
        assert r.status_code == 422
        assert SECRETO not in r.text

    def test_el_422_igual_dice_que_campo_esta_mal(self, client: TestClient) -> None:
        """No alcanza con no filtrar: el cliente tiene que poder arreglarlo."""
        r = client.post("/api/v1/activeia/credenciales", json={"password": SECRETO})
        cuerpo = r.json()
        assert any(e["loc"] == ["body", "username"] for e in cuerpo["detail"])
        assert all(e["msg"] for e in cuerpo["detail"])


class TestOtrasSuperficies:
    def test_el_openapi_no_expone_un_ejemplo_con_password(self, client: TestClient) -> None:
        r = client.get("/openapi.json")
        assert SECRETO not in r.text

    def test_el_repr_del_schema_enmascara_el_password(self) -> None:
        """`SecretStr`: si el modelo entra en un traceback o en un log
        estructurado, la contrasena no viaja con el."""
        from evaluation_service.schemas.activeia import CredencialCreate

        modelo = CredencialCreate(username="u", password=SECRETO)
        assert SECRETO not in repr(modelo)
        assert SECRETO not in str(modelo)
        # Pero sigue siendo recuperable donde hace falta.
        assert modelo.password.get_secret_value() == SECRETO
