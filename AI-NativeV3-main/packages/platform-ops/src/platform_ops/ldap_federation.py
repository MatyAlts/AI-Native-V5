"""Configuración de federación LDAP para tenants con directorio institucional.

Permite que una universidad que ya tiene LDAP/AD (como UNSL) federe los
usuarios a Keycloak sin duplicar la gestión. Los usuarios se autentican
contra el LDAP institucional; Keycloak solo emite el JWT.

Flujo:
  1. El admin de la universidad provee: URL del LDAP, bind DN, password,
     base DN de usuarios y grupos, mapeo de atributos.
  2. Este script crea el User Federation provider en Keycloak.
  3. Configura mappers: username, email, first/last name, groups.
  4. Opcionalmente: mapper de `tenant_id` hardcoded + rol según grupo LDAP
     (ej grupo "docentes-unsl" → rol `docente`).

Decisión arquitectónica: LDAP se configura POR REALM (por tenant), no
global. Cada universidad tiene su propio LDAP y se conecta a su realm
Keycloak independientemente.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from uuid import UUID

import httpx

logger = logging.getLogger(__name__)


@dataclass
class LDAPConfig:
    """Config del LDAP institucional del tenant."""

    connection_url: str  # "ldap://ldap.unsl.edu.ar:389" o "ldaps://..."
    bind_dn: str  # "cn=admin,dc=unsl,dc=edu,dc=ar"
    bind_credential: str  # password del bind DN (viene de secret)
    users_dn: str  # "ou=people,dc=unsl,dc=edu,dc=ar"
    username_attribute: str = "uid"
    email_attribute: str = "mail"
    first_name_attribute: str = "givenName"
    last_name_attribute: str = "sn"
    rdn_attribute: str = "uid"
    uuid_attribute: str = "entryUUID"
    user_object_classes: str = "inetOrgPerson, organizationalPerson"
    # Si true, Keycloak sincroniza usuarios en background cada
    # `sync_period_seconds` minutos. Si false, solo on-demand al login.
    periodic_full_sync: bool = False
    sync_period_seconds: int = 3600  # 1h
    use_tls: bool = True
    connection_timeout_ms: int = 5000
    priority: int = 1  # si hay múltiples providers, menor = más prioritario


@dataclass
class LDAPGroupMapping:
    """Mapea un grupo LDAP a un rol del realm Keycloak.

    Ejemplo típico UNSL:
      LDAPGroupMapping(
          ldap_group_dn="cn=docentes,ou=grupos,dc=unsl,dc=edu,dc=ar",
          realm_role="docente",
      )
    """

    ldap_group_dn: str
    realm_role: str


@dataclass
class LDAPFederationSpec:
    """Spec completo para setup de LDAP en un realm."""

    realm_name: str
    tenant_uuid: UUID
    display_name: str = "LDAP institucional"
    ldap: LDAPConfig = field(default=None)  # type: ignore
    group_mappings: list[LDAPGroupMapping] = field(default_factory=list)
    # Por default, nuevos usuarios LDAP entran con rol "estudiante" salvo
    # que un mapping de grupo les asigne otro.
    default_role: str = "estudiante"


class LDAPFederationError(Exception):
    """Error en el setup de LDAP."""


class LDAPFederator:
    """Configura user federation LDAP en un realm de Keycloak."""

    def __init__(self, keycloak_base_url: str, admin_token_provider) -> None:
        self.keycloak_base_url = keycloak_base_url.rstrip("/")
        self.admin_token_provider = admin_token_provider  # async callable

    async def _headers(self) -> dict[str, str]:
        token = await self.admin_token_provider()
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    async def configure(self, spec: LDAPFederationSpec) -> dict[str, str | list[str]]:
        """Setup completo: provider + mappers básicos + group mappings.

        Idempotente: si el provider ya existe con el mismo nombre, lo
        actualiza; no duplica.

        Returns:
            {"provider_id": "...", "actions": [...]}
        """
        if spec.ldap is None:
            raise LDAPFederationError("LDAPConfig is required")

        actions: list[str] = []
        async with httpx.AsyncClient(timeout=15.0) as client:
            # 1. Provider: check si existe
            provider_id = await self._find_provider(client, spec.realm_name, spec.display_name)
            if provider_id:
                await self._update_provider(client, spec.realm_name, provider_id, spec)
                actions.append(f"LDAP provider '{spec.display_name}' actualizado")
            else:
                provider_id = await self._create_provider(client, spec)
                actions.append(f"LDAP provider '{spec.display_name}' creado")

            # 2. Mappers estándar (username, email, names)
            mappers_added = await self._ensure_standard_mappers(
                client, spec.realm_name, provider_id, spec
            )
            if mappers_added:
                actions.append(f"Mappers estándar: {', '.join(mappers_added)}")

            # 3. Mapper de tenant_id (hardcoded)
            await self._ensure_tenant_id_mapper(client, spec.realm_name, provider_id, spec)
            actions.append("Mapper tenant_id asegurado")

            # 4. Group mappings (grupo LDAP → rol Keycloak)
            for mapping in spec.group_mappings:
                await self._ensure_group_to_role_mapper(
                    client, spec.realm_name, provider_id, mapping
                )
            if spec.group_mappings:
                actions.append(f"Group→Role mappings: {len(spec.group_mappings)} configurados")

        return {"provider_id": provider_id, "actions": actions}

    async def _find_provider(
        self, client: httpx.AsyncClient, realm: str, display_name: str
    ) -> str | None:
        r = await client.get(
            f"{self.keycloak_base_url}/admin/realms/{realm}/components",
            params={"type": "org.keycloak.storage.UserStorageProvider"},
            headers=await self._headers(),
        )
        r.raise_for_status()
        for comp in r.json():
            if comp.get("name") == display_name:
                return comp["id"]
        return None

    async def _create_provider(self, client: httpx.AsyncClient, spec: LDAPFederationSpec) -> str:
        body = {
            "name": spec.display_name,
            "providerId": "ldap",
            "providerType": "org.keycloak.storage.UserStorageProvider",
            "config": self._ldap_config_to_kc_config(spec.ldap),
        }
        r = await client.post(
            f"{self.keycloak_base_url}/admin/realms/{spec.realm_name}/components",
            headers=await self._headers(),
            json=body,
        )
        if r.status_code not in (201, 204):
            raise LDAPFederationError(f"No se pudo crear LDAP provider: {r.status_code} {r.text}")
        location = r.headers.get("location", "")
        return location.rstrip("/").split("/")[-1]

    async def _update_provider(
        self,
        client: httpx.AsyncClient,
        realm: str,
        provider_id: str,
        spec: LDAPFederationSpec,
    ) -> None:
        body = {
            "id": provider_id,
            "name": spec.display_name,
            "providerId": "ldap",
            "providerType": "org.keycloak.storage.UserStorageProvider",
            "config": self._ldap_config_to_kc_config(spec.ldap),
        }
        r = await client.put(
            f"{self.keycloak_base_url}/admin/realms/{realm}/components/{provider_id}",
            headers=await self._headers(),
            json=body,
        )
        if r.status_code not in (200, 204):
            raise LDAPFederationError(
                f"No se pudo actualizar LDAP provider: {r.status_code} {r.text}"
            )

    def _ldap_config_to_kc_config(self, ldap: LDAPConfig) -> dict[str, list[str]]:
        """Keycloak espera cada valor del config como list[str]."""
        return {
            "connectionUrl": [ldap.connection_url],
            "bindDn": [ldap.bind_dn],
            "bindCredential": [ldap.bind_credential],
            "usersDn": [ldap.users_dn],
            "usernameLDAPAttribute": [ldap.username_attribute],
            "rdnLDAPAttribute": [ldap.rdn_attribute],
            "uuidLDAPAttribute": [ldap.uuid_attribute],
            "userObjectClasses": [ldap.user_object_classes],
            "editMode": ["READ_ONLY"],  # la plataforma nunca modifica el LDAP
            "syncRegistrations": ["false"],
            "vendor": ["other"],
            "connectionTimeout": [str(ldap.connection_timeout_ms)],
            "startTls": ["true" if ldap.use_tls else "false"],
            "importEnabled": ["true"],
            "batchSizeForSync": ["1000"],
            "fullSyncPeriod": [str(ldap.sync_period_seconds) if ldap.periodic_full_sync else "-1"],
            "changedSyncPeriod": ["-1"],
            "priority": [str(ldap.priority)],
        }

    async def _ensure_standard_mappers(
        self,
        client: httpx.AsyncClient,
        realm: str,
        provider_id: str,
        spec: LDAPFederationSpec,
    ) -> list[str]:
        """Email, first-name, last-name mappers. Keycloak los crea por
        default al crear el provider, pero los aseguramos."""
        # En la práctica, el mapper de username se crea automáticamente.
        # Verificamos solo que existan email/names con los atributos correctos.
        existing = await self._list_mappers(client, realm, provider_id)
        existing_names = {m["name"] for m in existing}

        created: list[str] = []
        standard_mappers = [
            ("email", "email", spec.ldap.email_attribute),
            ("first name", "firstName", spec.ldap.first_name_attribute),
            ("last name", "lastName", spec.ldap.last_name_attribute),
        ]
        for name, kc_attr, ldap_attr in standard_mappers:
            if name in existing_names:
                continue
            await self._create_mapper(
                client,
                realm,
                provider_id,
                name=name,
                mapper_type="user-attribute-ldap-mapper",
                config={
                    "user.model.attribute": [kc_attr],
                    "ldap.attribute": [ldap_attr],
                    "read.only": ["true"],
                    "always.read.value.from.ldap": ["true"],
                    "is.mandatory.in.ldap": ["false"],
                },
            )
            created.append(name)
        return created

    async def _ensure_tenant_id_mapper(
        self,
        client: httpx.AsyncClient,
        realm: str,
        provider_id: str,
        spec: LDAPFederationSpec,
    ) -> None:
        """Asegura que el LDAP provider también inyecte el claim tenant_id.

        El mapper a nivel de client (del onboarding) ya agrega tenant_id al
        token, pero el mapper a nivel de user-federation garantiza que
        los usuarios LDAP también lo tengan (en caso de que el flow de
        token difiera).
        """
        existing = await self._list_mappers(client, realm, provider_id)
        if any(m.get("name") == "tenant_id_from_ldap_provider" for m in existing):
            return

        # Usa un hardcoded-attribute-mapper: inyecta el UUID del tenant como
        # atributo del usuario. Luego el protocol-mapper a nivel client
        # lee ese atributo y lo pone en el token.
        await self._create_mapper(
            client,
            realm,
            provider_id,
            name="tenant_id_from_ldap_provider",
            mapper_type="hardcoded-attribute-mapper",
            config={
                "user.model.attribute": ["tenant_id"],
                "attribute.value": [str(spec.tenant_uuid)],
            },
        )

    async def _ensure_group_to_role_mapper(
        self,
        client: httpx.AsyncClient,
        realm: str,
        provider_id: str,
        mapping: LDAPGroupMapping,
    ) -> None:
        # Para keep it simple: usamos un hardcoded-ldap-role-mapper por
        # cada grupo. Es más básico que el group-ldap-mapper pero más
        # fácil de auditar: "si el usuario está en este DN → asignarle
        # este role".
        # En producción avanzada se puede migrar a un group-ldap-mapper
        # con sync bidireccional.
        existing = await self._list_mappers(client, realm, provider_id)
        mapper_name = f"group_{mapping.realm_role}"
        if any(m.get("name") == mapper_name for m in existing):
            return

        await self._create_mapper(
            client,
            realm,
            provider_id,
            name=mapper_name,
            mapper_type="role-ldap-mapper",
            config={
                "role.object.classes": ["groupOfNames"],
                "roles.dn": [mapping.ldap_group_dn],
                "role.name.ldap.attribute": ["cn"],
                "membership.ldap.attribute": ["member"],
                "membership.user.ldap.attribute": ["uid"],
                "mode": ["READ_ONLY"],
                "use.realm.roles.mapping": ["true"],
                "realm.role": [mapping.realm_role],
            },
        )

    async def _list_mappers(
        self, client: httpx.AsyncClient, realm: str, provider_id: str
    ) -> list[dict]:
        r = await client.get(
            f"{self.keycloak_base_url}/admin/realms/{realm}/components",
            params={"parent": provider_id},
            headers=await self._headers(),
        )
        r.raise_for_status()
        return r.json()

    async def _create_mapper(
        self,
        client: httpx.AsyncClient,
        realm: str,
        provider_id: str,
        name: str,
        mapper_type: str,
        config: dict[str, list[str]],
    ) -> None:
        body = {
            "name": name,
            "providerId": mapper_type,
            "providerType": "org.keycloak.storage.ldap.mappers.LDAPStorageMapper",
            "parentId": provider_id,
            "config": config,
        }
        r = await client.post(
            f"{self.keycloak_base_url}/admin/realms/{realm}/components",
            headers=await self._headers(),
            json=body,
        )
        if r.status_code not in (201, 204):
            raise LDAPFederationError(f"Mapper '{name}' falló: {r.status_code} {r.text}")


__all__ = [
    "LDAPConfig",
    "LDAPFederationError",
    "LDAPFederationSpec",
    "LDAPFederator",
    "LDAPGroupMapping",
]
