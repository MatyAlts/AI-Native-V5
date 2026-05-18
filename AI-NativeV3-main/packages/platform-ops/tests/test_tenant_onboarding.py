"""Tests del onboarding de tenant.

Usa respx para interceptar llamadas a Keycloak. Verifica:
  - Creación correcta cuando el tenant no existe
  - Idempotencia: re-correr con tenant existente no duplica
  - Claim mapper tenant_id se configura con el UUID correcto
  - Password temporal con requiredActions=UPDATE_PASSWORD
  - Roles del realm se crean completos
"""

from __future__ import annotations

from uuid import UUID

import pytest
import respx
from httpx import Response
from platform_ops.tenant_onboarding import (
    KeycloakClient,
    KeycloakConfig,
    TenantOnboarder,
    TenantSpec,
)

KC_BASE = "http://kc.test"
ADMIN_TOKEN = "fake-admin-token"


@pytest.fixture
def tenant_spec() -> TenantSpec:
    return TenantSpec(
        name="UNSL",
        uuid=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        realm_name="unsl",
        admin_email="admin@unsl.edu.ar",
        admin_password_temp="TempPass123!",
        allowed_origins=["https://unsl.platform.ar"],
    )


@pytest.fixture
def kc_client() -> KeycloakClient:
    return KeycloakClient(
        KeycloakConfig(
            base_url=KC_BASE,
            admin_user="admin",
            admin_password="secret",
        )
    )


def _mock_admin_login(router: respx.MockRouter) -> None:
    router.post(f"{KC_BASE}/realms/master/protocol/openid-connect/token").mock(
        return_value=Response(200, json={"access_token": ADMIN_TOKEN})
    )


# ── Tenant nuevo (happy path) ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_onboarding_de_tenant_nuevo(kc_client, tenant_spec) -> None:
    async with respx.mock(base_url=KC_BASE, assert_all_called=False) as router:
        _mock_admin_login(router)

        # Realm no existe
        router.get(f"{KC_BASE}/admin/realms/unsl").mock(
            return_value=Response(404),
        )
        # Crear realm
        realm_create = router.post(f"{KC_BASE}/admin/realms").mock(
            return_value=Response(201),
        )

        # GET /clients:
        #   1ra llamada (create_client check): [] → crear
        #   2da llamada (mapper lookup): [{id: internal}] → saltearse creación
        router.get(f"{KC_BASE}/admin/realms/unsl/clients").mock(
            side_effect=[
                Response(200, json=[]),
                Response(200, json=[{"id": "internal-client-id", "clientId": "platform-backend"}]),
            ],
        )
        client_create = router.post(f"{KC_BASE}/admin/realms/unsl/clients").mock(
            return_value=Response(201),
        )

        # Mapper: ninguno existe
        mappers_url = (
            f"{KC_BASE}/admin/realms/unsl/clients/internal-client-id/protocol-mappers/models"
        )
        router.get(mappers_url).mock(return_value=Response(200, json=[]))
        mapper_create = router.post(mappers_url).mock(return_value=Response(201))

        # Roles: ninguno existe → crear los 4. El último GET de docente_admin
        # (para asignarlo al user) sí devuelve 200.
        router.get(f"{KC_BASE}/admin/realms/unsl/roles/estudiante").mock(
            return_value=Response(404),
        )
        router.get(f"{KC_BASE}/admin/realms/unsl/roles/docente").mock(
            return_value=Response(404),
        )
        # docente_admin: primera llamada (check al crear) = 404,
        # segunda llamada (lookup para assign) = 200
        router.get(f"{KC_BASE}/admin/realms/unsl/roles/docente_admin").mock(
            side_effect=[
                Response(404),
                Response(200, json={"id": "role-id", "name": "docente_admin"}),
            ],
        )
        router.get(f"{KC_BASE}/admin/realms/unsl/roles/superadmin").mock(
            return_value=Response(404),
        )
        roles_create = router.post(f"{KC_BASE}/admin/realms/unsl/roles").mock(
            return_value=Response(201),
        )

        # User: no existe → crear
        router.get(
            f"{KC_BASE}/admin/realms/unsl/users",
            params={"email": tenant_spec.admin_email, "exact": "true"},
        ).mock(return_value=Response(200, json=[]))
        user_create = router.post(f"{KC_BASE}/admin/realms/unsl/users").mock(
            return_value=Response(
                201,
                headers={"location": f"{KC_BASE}/admin/realms/unsl/users/new-user-id"},
            ),
        )
        router.post(f"{KC_BASE}/admin/realms/unsl/users/new-user-id/role-mappings/realm").mock(
            return_value=Response(204),
        )

        onboarder = TenantOnboarder(kc_client)
        report = await onboarder.onboard(tenant_spec)

    # Assertions
    assert report.tenant_uuid == tenant_spec.uuid
    assert report.realm_name == "unsl"
    assert report.admin_user_id == "new-user-id"
    assert any("creado" in a.lower() for a in report.actions)
    assert realm_create.called
    assert client_create.called
    assert mapper_create.called
    assert roles_create.call_count == 4  # los 4 roles
    assert user_create.called


@pytest.mark.asyncio
async def test_mapper_injecta_tenant_id_correcto(kc_client, tenant_spec) -> None:
    """CRÍTICO: el mapper debe configurar `claim.value` con el UUID del tenant."""
    async with respx.mock(base_url=KC_BASE, assert_all_called=False) as router:
        _mock_admin_login(router)

        router.get(f"{KC_BASE}/admin/realms/unsl").mock(return_value=Response(200))
        router.get(f"{KC_BASE}/admin/realms/unsl/clients").mock(
            return_value=Response(
                200, json=[{"id": "internal-id", "clientId": "platform-backend"}]
            ),
        )

        mappers_url = f"{KC_BASE}/admin/realms/unsl/clients/internal-id/protocol-mappers/models"
        router.get(mappers_url).mock(return_value=Response(200, json=[]))

        mapper_post = router.post(mappers_url).mock(return_value=Response(201))

        await kc_client.add_tenant_id_mapper(tenant_spec)

    # Verificar que el body del POST tiene el claim value correcto
    assert mapper_post.called
    request = mapper_post.calls[0].request
    body = request.read().decode()
    assert str(tenant_spec.uuid) in body
    assert "tenant_id" in body
    assert "hardcoded-claim-mapper" in body


# ── Idempotencia ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_onboarding_idempotente_no_recrea_realm(kc_client, tenant_spec) -> None:
    """Re-correr el onboarding con tenant existente no crea duplicados."""
    async with respx.mock(base_url=KC_BASE, assert_all_called=False) as router:
        _mock_admin_login(router)

        # Realm ya existe
        router.get(f"{KC_BASE}/admin/realms/unsl").mock(return_value=Response(200))

        realm_create = router.post(f"{KC_BASE}/admin/realms").mock(
            return_value=Response(201),
        )

        # Clients: existe platform-backend
        router.get(f"{KC_BASE}/admin/realms/unsl/clients").mock(
            return_value=Response(
                200, json=[{"id": "existing-id", "clientId": "platform-backend"}]
            ),
        )
        client_create = router.post(f"{KC_BASE}/admin/realms/unsl/clients").mock(
            return_value=Response(201),
        )

        # Mapper ya existe
        mappers_url = f"{KC_BASE}/admin/realms/unsl/clients/existing-id/protocol-mappers/models"
        router.get(mappers_url).mock(
            return_value=Response(200, json=[{"name": "tenant_id"}]),
        )
        mapper_create = router.post(mappers_url).mock(return_value=Response(201))

        # Roles ya existen todos
        for role in ("estudiante", "docente", "docente_admin", "superadmin"):
            router.get(f"{KC_BASE}/admin/realms/unsl/roles/{role}").mock(
                return_value=Response(200, json={"name": role, "id": f"{role}-id"}),
            )
        roles_create = router.post(f"{KC_BASE}/admin/realms/unsl/roles").mock(
            return_value=Response(201),
        )

        # User ya existe
        router.get(
            f"{KC_BASE}/admin/realms/unsl/users",
            params={"email": tenant_spec.admin_email, "exact": "true"},
        ).mock(
            return_value=Response(200, json=[{"id": "existing-user-id"}]),
        )
        user_create = router.post(f"{KC_BASE}/admin/realms/unsl/users").mock(
            return_value=Response(201),
        )

        onboarder = TenantOnboarder(kc_client)
        report = await onboarder.onboard(tenant_spec)

    # No se crearon duplicados
    assert not realm_create.called
    assert not client_create.called
    assert not mapper_create.called
    assert not roles_create.called
    assert not user_create.called
    # Pero el onboarding reportó éxito reutilizando
    assert report.admin_user_id == "existing-user-id"
    assert any("reusando" in a.lower() for a in report.actions)


# ── User admin con password temporal ───────────────────────────────────


@pytest.mark.asyncio
async def test_admin_user_se_crea_con_password_temporal(kc_client, tenant_spec) -> None:
    """El usuario admin debe forzar cambio de password al primer login."""
    async with respx.mock(base_url=KC_BASE, assert_all_called=False) as router:
        _mock_admin_login(router)

        router.get(
            f"{KC_BASE}/admin/realms/unsl/users",
            params={"email": tenant_spec.admin_email, "exact": "true"},
        ).mock(
            return_value=Response(200, json=[]),
        )

        user_create = router.post(f"{KC_BASE}/admin/realms/unsl/users").mock(
            return_value=Response(
                201, headers={"location": f"{KC_BASE}/admin/realms/unsl/users/uid-xyz"}
            ),
        )
        router.get(f"{KC_BASE}/admin/realms/unsl/roles/docente_admin").mock(
            return_value=Response(200, json={"id": "r1", "name": "docente_admin"}),
        )
        router.post(f"{KC_BASE}/admin/realms/unsl/users/uid-xyz/role-mappings/realm").mock(
            return_value=Response(204),
        )

        user_id = await kc_client.create_admin_user(tenant_spec)

    assert user_id == "uid-xyz"
    assert user_create.called
    body = user_create.calls[0].request.read().decode()
    import json

    parsed = json.loads(body)
    assert parsed["email"] == tenant_spec.admin_email
    # Credenciales: password temporal que FORZA cambio
    assert parsed["credentials"][0]["temporary"] is True
    assert "UPDATE_PASSWORD" in parsed["requiredActions"]
