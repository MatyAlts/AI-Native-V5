"""Tests de LDAP federation con respx."""

from __future__ import annotations

from uuid import UUID

import pytest
import respx
from httpx import Response
from platform_ops.ldap_federation import (
    LDAPConfig,
    LDAPFederationSpec,
    LDAPFederator,
    LDAPGroupMapping,
)

KC_BASE = "http://kc.test"


async def fake_token() -> str:
    return "fake-admin-token"


@pytest.fixture
def federator() -> LDAPFederator:
    return LDAPFederator(keycloak_base_url=KC_BASE, admin_token_provider=fake_token)


@pytest.fixture
def ldap_spec() -> LDAPFederationSpec:
    return LDAPFederationSpec(
        realm_name="unsl",
        tenant_uuid=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        display_name="LDAP UNSL",
        ldap=LDAPConfig(
            connection_url="ldaps://ldap.unsl.edu.ar:636",
            bind_dn="cn=admin,dc=unsl,dc=edu,dc=ar",
            bind_credential="ldap-pw-from-secret",
            users_dn="ou=people,dc=unsl,dc=edu,dc=ar",
        ),
        group_mappings=[
            LDAPGroupMapping(
                ldap_group_dn="cn=docentes,ou=grupos,dc=unsl,dc=edu,dc=ar",
                realm_role="docente",
            ),
        ],
    )


# ── Creación de provider ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_crea_provider_nuevo(federator, ldap_spec) -> None:
    async with respx.mock(base_url=KC_BASE, assert_all_called=False) as router:
        # GET components (no existe el provider)
        router.get(f"{KC_BASE}/admin/realms/unsl/components").mock(
            side_effect=[
                Response(200, json=[]),  # list providers → vacío
                Response(200, json=[]),  # list mappers del provider nuevo → vacío
                Response(200, json=[]),  # tenant_id check
                Response(200, json=[]),  # group mapping check
            ]
        )
        # POST para crear provider
        provider_create = router.post(f"{KC_BASE}/admin/realms/unsl/components").mock(
            return_value=Response(
                201, headers={"location": f"{KC_BASE}/admin/realms/unsl/components/new-prov-id"}
            ),
        )

        result = await federator.configure(ldap_spec)

    assert provider_create.called
    assert result["provider_id"] == "new-prov-id"
    assert any("creado" in a for a in result["actions"])


@pytest.mark.asyncio
async def test_actualiza_provider_si_ya_existe(federator, ldap_spec) -> None:
    """Idempotencia: si el provider ya existe, se actualiza en lugar de duplicar."""
    async with respx.mock(base_url=KC_BASE, assert_all_called=False) as router:
        # Primer GET: provider ya existe
        router.get(f"{KC_BASE}/admin/realms/unsl/components").mock(
            side_effect=[
                Response(200, json=[{"id": "existing-prov", "name": "LDAP UNSL"}]),
                # Mappers existentes incluye todos los mappers para que no se dupliquen
                Response(
                    200,
                    json=[
                        {"name": "email"},
                        {"name": "first name"},
                        {"name": "last name"},
                    ],
                ),
                # tenant_id mapper ya existe
                Response(200, json=[{"name": "tenant_id_from_ldap_provider"}]),
                # group mapping ya existe
                Response(200, json=[{"name": "group_docente"}]),
            ]
        )
        # PUT para update
        update_put = router.put(f"{KC_BASE}/admin/realms/unsl/components/existing-prov").mock(
            return_value=Response(204)
        )
        # NO debe haber POSTs de creación
        create_posts = router.post(f"{KC_BASE}/admin/realms/unsl/components").mock(
            return_value=Response(500)  # si lo llaman, explota
        )

        result = await federator.configure(ldap_spec)

    assert update_put.called
    assert not create_posts.called
    assert result["provider_id"] == "existing-prov"
    assert any("actualizado" in a for a in result["actions"])


@pytest.mark.asyncio
async def test_config_ldap_pasa_valores_correctos_a_keycloak(federator, ldap_spec) -> None:
    """Keycloak espera config como dict[str, list[str]]. Verificamos
    que connection_url, users_dn, etc se serialicen bien."""
    captured_bodies: list[dict] = []

    async with respx.mock(base_url=KC_BASE, assert_all_called=False) as router:
        router.get(f"{KC_BASE}/admin/realms/unsl/components").mock(
            side_effect=[
                Response(200, json=[]),
                Response(200, json=[]),
                Response(200, json=[]),
                Response(200, json=[]),
            ]
        )

        async def capture(request):
            import json

            captured_bodies.append(json.loads(request.content))
            return Response(
                201, headers={"location": f"{KC_BASE}/admin/realms/unsl/components/xxx"}
            )

        router.post(f"{KC_BASE}/admin/realms/unsl/components").mock(side_effect=capture)

        await federator.configure(ldap_spec)

    # El PRIMER POST es el del provider (todos los siguientes son mappers)
    provider_body = captured_bodies[0]
    assert provider_body["providerId"] == "ldap"
    config = provider_body["config"]
    assert config["connectionUrl"] == ["ldaps://ldap.unsl.edu.ar:636"]
    assert config["usersDn"] == ["ou=people,dc=unsl,dc=edu,dc=ar"]
    assert config["bindDn"] == ["cn=admin,dc=unsl,dc=edu,dc=ar"]
    # CRÍTICO: editMode READ_ONLY (nunca modificamos el LDAP)
    assert config["editMode"] == ["READ_ONLY"]


# ── Mappers ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_crea_mappers_estandar(federator, ldap_spec) -> None:
    mapper_posts: list[dict] = []

    async with respx.mock(base_url=KC_BASE, assert_all_called=False) as router:
        # Provider existe
        router.get(f"{KC_BASE}/admin/realms/unsl/components").mock(
            side_effect=[
                Response(200, json=[{"id": "prov-1", "name": "LDAP UNSL"}]),
                Response(200, json=[]),  # mappers: vacío → crear los 3
                Response(200, json=[]),  # tenant_id check vacío → crear
                Response(200, json=[]),  # group check vacío → crear
            ]
        )
        router.put(f"{KC_BASE}/admin/realms/unsl/components/prov-1").mock(
            return_value=Response(204)
        )

        async def capture_mapper(request):
            import json

            body = json.loads(request.content)
            mapper_posts.append(body)
            return Response(201)

        router.post(f"{KC_BASE}/admin/realms/unsl/components").mock(
            side_effect=capture_mapper,
        )

        await federator.configure(ldap_spec)

    mapper_names = {m.get("name") for m in mapper_posts}
    assert "email" in mapper_names
    assert "first name" in mapper_names
    assert "last name" in mapper_names
    # tenant_id y group_docente
    assert "tenant_id_from_ldap_provider" in mapper_names
    assert "group_docente" in mapper_names


@pytest.mark.asyncio
async def test_tenant_id_mapper_tiene_uuid_correcto(federator, ldap_spec) -> None:
    captured_mappers: list[dict] = []

    async with respx.mock(base_url=KC_BASE, assert_all_called=False) as router:
        router.get(f"{KC_BASE}/admin/realms/unsl/components").mock(
            side_effect=[
                Response(200, json=[{"id": "prov-1", "name": "LDAP UNSL"}]),
                Response(
                    200,
                    json=[
                        {"name": "email"},
                        {"name": "first name"},
                        {"name": "last name"},
                    ],
                ),
                Response(200, json=[]),  # tenant_id mapper no existe → crear
                Response(200, json=[]),
            ]
        )
        router.put(f"{KC_BASE}/admin/realms/unsl/components/prov-1").mock(
            return_value=Response(204)
        )

        async def capture(request):
            import json

            captured_mappers.append(json.loads(request.content))
            return Response(201)

        router.post(f"{KC_BASE}/admin/realms/unsl/components").mock(side_effect=capture)

        await federator.configure(ldap_spec)

    tenant_mapper = next(
        m for m in captured_mappers if m.get("name") == "tenant_id_from_ldap_provider"
    )
    assert tenant_mapper["config"]["attribute.value"] == [str(ldap_spec.tenant_uuid)]
    assert tenant_mapper["config"]["user.model.attribute"] == ["tenant_id"]
