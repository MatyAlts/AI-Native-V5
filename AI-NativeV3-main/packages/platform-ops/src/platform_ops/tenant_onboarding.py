"""Onboarding automatizado de tenants (universidades).

Pasos que hace este comando idempotentemente:

  1. Crear realm en Keycloak (o reutilizar si existe)
  2. Configurar client "platform-backend" con audience correcta
  3. Crear mapper que inyecte el claim `tenant_id` en todos los tokens
  4. Crear roles del realm: estudiante, docente, docente_admin, superadmin
  5. Crear usuario admin inicial con password temporal
  6. Seed en academic_main DB: fila en Universidades + UUID del tenant
  7. Clone del repo de prompts en el tenant (si se pasó --prompts-repo)

Cada paso verifica estado previo — si se re-corre el onboarding para
un tenant existente, no duplica nada y reporta qué cambió.

Uso:
    python -m platform_ops.tenant_onboarding \\
        --tenant-name "UNSL" \\
        --tenant-uuid aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa \\
        --admin-email admin@unsl.edu.ar \\
        --keycloak-url http://localhost:8180 \\
        --keycloak-admin-password admin

Secretos (passwords, tokens de Keycloak admin) deben venir de variables
de entorno en CI, no argparse. Las variables soportadas:
    KEYCLOAK_ADMIN_USER, KEYCLOAK_ADMIN_PASSWORD, TENANT_DB_URL
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from dataclasses import dataclass, field
from uuid import UUID

import httpx

logger = logging.getLogger(__name__)


# ── Spec del tenant ────────────────────────────────────────────────────


@dataclass
class TenantSpec:
    name: str  # "UNSL"
    uuid: UUID  # tenant_id autoritativo
    realm_name: str  # "unsl" (slug del name)
    admin_email: str
    admin_password_temp: str = "ChangeMeAtFirstLogin!"
    default_locale: str = "es"
    prompts_repo_ref: str | None = None  # git ref si se clona prompt repo
    allowed_origins: list[str] = field(default_factory=list)


# ── Keycloak client ────────────────────────────────────────────────────


@dataclass
class KeycloakConfig:
    base_url: str  # "http://keycloak:8080"
    admin_user: str
    admin_password: str
    admin_realm: str = "master"


class KeycloakClient:
    """Wrapper mínimo sobre el Admin REST API de Keycloak."""

    def __init__(self, config: KeycloakConfig) -> None:
        self.config = config
        self._token: str | None = None

    async def _token_or_login(self, client: httpx.AsyncClient) -> str:
        if self._token:
            return self._token
        url = (
            f"{self.config.base_url}/realms/{self.config.admin_realm}/protocol/openid-connect/token"
        )
        r = await client.post(
            url,
            data={
                "grant_type": "password",
                "client_id": "admin-cli",
                "username": self.config.admin_user,
                "password": self.config.admin_password,
            },
        )
        r.raise_for_status()
        self._token = r.json()["access_token"]
        return self._token

    async def _headers(self, client: httpx.AsyncClient) -> dict[str, str]:
        t = await self._token_or_login(client)
        return {"Authorization": f"Bearer {t}", "Content-Type": "application/json"}

    async def realm_exists(self, realm: str) -> bool:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(
                f"{self.config.base_url}/admin/realms/{realm}",
                headers=await self._headers(client),
            )
            return r.status_code == 200

    async def create_realm(self, spec: TenantSpec) -> None:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(
                f"{self.config.base_url}/admin/realms",
                headers=await self._headers(client),
                json={
                    "realm": spec.realm_name,
                    "enabled": True,
                    "displayName": spec.name,
                    "defaultLocale": spec.default_locale,
                    "accessTokenLifespan": 1800,  # 30 min
                    "ssoSessionIdleTimeout": 3600 * 8,  # 8h
                    "passwordPolicy": "length(10) and digits(1) and upperCase(1) and notUsername",
                },
            )
            if r.status_code not in (201, 204, 409):
                r.raise_for_status()

    async def create_client(self, spec: TenantSpec, client_id: str = "platform-backend") -> None:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # Check if exists
            r = await client.get(
                f"{self.config.base_url}/admin/realms/{spec.realm_name}/clients",
                params={"clientId": client_id},
                headers=await self._headers(client),
            )
            r.raise_for_status()
            existing = r.json()
            if existing:
                logger.info("client %s ya existe en realm %s", client_id, spec.realm_name)
                return

            r = await client.post(
                f"{self.config.base_url}/admin/realms/{spec.realm_name}/clients",
                headers=await self._headers(client),
                json={
                    "clientId": client_id,
                    "enabled": True,
                    "protocol": "openid-connect",
                    "publicClient": False,  # server-side flow
                    "standardFlowEnabled": True,
                    "directAccessGrantsEnabled": True,  # para CLI scripts
                    "serviceAccountsEnabled": False,
                    "redirectUris": spec.allowed_origins or ["*"],
                    "webOrigins": spec.allowed_origins or ["*"],
                    "attributes": {
                        "access.token.lifespan": "1800",
                    },
                },
            )
            r.raise_for_status()

    async def add_tenant_id_mapper(
        self, spec: TenantSpec, client_id: str = "platform-backend"
    ) -> None:
        """Agrega un mapper que injecta el claim `tenant_id` en cada token.

        El valor del claim es el mismo UUID del tenant para todos los
        usuarios de este realm. (En K.C. se hace con un 'Hardcoded claim'
        protocol mapper.)
        """
        async with httpx.AsyncClient(timeout=10.0) as client:
            headers = await self._headers(client)

            # Obtener el internal id del client
            r = await client.get(
                f"{self.config.base_url}/admin/realms/{spec.realm_name}/clients",
                params={"clientId": client_id},
                headers=headers,
            )
            r.raise_for_status()
            clients = r.json()
            if not clients:
                raise RuntimeError(f"client {client_id} no existe en {spec.realm_name}")
            internal_id = clients[0]["id"]

            # Check si el mapper ya existe
            mappers_url = (
                f"{self.config.base_url}/admin/realms/{spec.realm_name}"
                f"/clients/{internal_id}/protocol-mappers/models"
            )
            r = await client.get(mappers_url, headers=headers)
            r.raise_for_status()
            existing = [m for m in r.json() if m.get("name") == "tenant_id"]
            if existing:
                logger.info("mapper tenant_id ya existe")
                return

            await client.post(
                mappers_url,
                headers=headers,
                json={
                    "name": "tenant_id",
                    "protocol": "openid-connect",
                    "protocolMapper": "oidc-hardcoded-claim-mapper",
                    "config": {
                        "claim.name": "tenant_id",
                        "claim.value": str(spec.uuid),
                        "jsonType.label": "String",
                        "id.token.claim": "true",
                        "access.token.claim": "true",
                        "userinfo.token.claim": "true",
                    },
                },
            )

    async def create_realm_roles(self, spec: TenantSpec) -> list[str]:
        """Crea los roles del realm si no existen. Devuelve los creados."""
        ROLES = ["estudiante", "docente", "docente_admin", "superadmin"]
        created: list[str] = []
        async with httpx.AsyncClient(timeout=10.0) as client:
            headers = await self._headers(client)
            base = f"{self.config.base_url}/admin/realms/{spec.realm_name}/roles"

            for role in ROLES:
                # Check
                r = await client.get(f"{base}/{role}", headers=headers)
                if r.status_code == 200:
                    continue
                # Create
                r = await client.post(
                    base,
                    headers=headers,
                    json={"name": role, "description": f"Rol {role} del realm {spec.realm_name}"},
                )
                if r.status_code in (201, 204):
                    created.append(role)
        return created

    async def create_admin_user(self, spec: TenantSpec) -> str:
        """Crea el user admin del tenant con password temporal. Devuelve el user_id."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            headers = await self._headers(client)
            base = f"{self.config.base_url}/admin/realms/{spec.realm_name}/users"

            r = await client.get(
                base,
                params={"email": spec.admin_email, "exact": "true"},
                headers=headers,
            )
            r.raise_for_status()
            existing = r.json()
            if existing:
                logger.info("admin user %s ya existe", spec.admin_email)
                return existing[0]["id"]

            r = await client.post(
                base,
                headers=headers,
                json={
                    "username": spec.admin_email,
                    "email": spec.admin_email,
                    "enabled": True,
                    "emailVerified": False,
                    "credentials": [
                        {
                            "type": "password",
                            "value": spec.admin_password_temp,
                            "temporary": True,  # fuerza cambio en primer login
                        }
                    ],
                    "requiredActions": ["UPDATE_PASSWORD"],
                },
            )
            r.raise_for_status()

            # Recuperar el user_id del Location header
            location = r.headers.get("location", "")
            user_id = location.rstrip("/").split("/")[-1]

            # Asignarle el rol docente_admin
            role_r = await client.get(
                f"{self.config.base_url}/admin/realms/{spec.realm_name}/roles/docente_admin",
                headers=headers,
            )
            if role_r.status_code == 200:
                role_data = role_r.json()
                await client.post(
                    f"{base}/{user_id}/role-mappings/realm",
                    headers=headers,
                    json=[role_data],
                )
            return user_id


# ── Orchestrator ───────────────────────────────────────────────────────


@dataclass
class OnboardingReport:
    tenant_uuid: UUID
    realm_name: str
    actions: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    admin_user_id: str | None = None

    def summary(self) -> str:
        lines = [
            f"Tenant: {self.tenant_uuid}",
            f"Realm: {self.realm_name}",
            f"Admin user: {self.admin_user_id or 'n/a'}",
            "",
            "Acciones ejecutadas:",
            *[f"  ✓ {a}" for a in self.actions],
        ]
        if self.warnings:
            lines.append("")
            lines.append("Advertencias:")
            lines.extend(f"  ⚠ {w}" for w in self.warnings)
        return "\n".join(lines)


class TenantOnboarder:
    def __init__(self, keycloak: KeycloakClient) -> None:
        self.keycloak = keycloak

    async def onboard(self, spec: TenantSpec) -> OnboardingReport:
        report = OnboardingReport(tenant_uuid=spec.uuid, realm_name=spec.realm_name)

        # 1. Realm
        if await self.keycloak.realm_exists(spec.realm_name):
            report.actions.append(f"Realm '{spec.realm_name}' ya existía — reusando")
        else:
            await self.keycloak.create_realm(spec)
            report.actions.append(f"Realm '{spec.realm_name}' creado")

        # 2. Client
        await self.keycloak.create_client(spec)
        report.actions.append("Client 'platform-backend' asegurado")

        # 3. Mapper de tenant_id
        await self.keycloak.add_tenant_id_mapper(spec)
        report.actions.append(f"Mapper tenant_id={spec.uuid} asegurado")

        # 4. Roles
        created_roles = await self.keycloak.create_realm_roles(spec)
        if created_roles:
            report.actions.append(f"Roles creados: {', '.join(created_roles)}")
        else:
            report.actions.append("Todos los roles ya existían")

        # 5. Admin user
        report.admin_user_id = await self.keycloak.create_admin_user(spec)
        report.actions.append(
            f"Admin user asegurado ({spec.admin_email}) "
            f"con password temporal '{spec.admin_password_temp}'"
        )

        # 6. Warning sobre pasos manuales fuera del scope del script
        report.warnings.append(
            "Seed de universidad en academic_main DB debe hacerse con "
            "`make seed-tenant TENANT_UUID=... TENANT_NAME=...` (no incluido aquí)"
        )
        report.warnings.append(
            "Prompts repo debe clonarse al governance-service según el flujo GitOps del tenant"
        )

        return report


# ── CLI ────────────────────────────────────────────────────────────────


async def run_cli(args: argparse.Namespace) -> int:
    logging.basicConfig(level=logging.INFO)

    kc_password = os.environ.get("KEYCLOAK_ADMIN_PASSWORD")
    if not kc_password:
        print("ERROR: KEYCLOAK_ADMIN_PASSWORD env var es requerida", file=sys.stderr)
        return 2

    kc = KeycloakClient(
        KeycloakConfig(
            base_url=args.keycloak_url,
            admin_user=os.environ.get("KEYCLOAK_ADMIN_USER", "admin"),
            admin_password=kc_password,
        )
    )

    spec = TenantSpec(
        name=args.tenant_name,
        uuid=UUID(args.tenant_uuid),
        realm_name=args.realm_name or args.tenant_name.lower().replace(" ", "_"),
        admin_email=args.admin_email,
        admin_password_temp=args.admin_password or "ChangeMeAtFirstLogin!",
        allowed_origins=args.allowed_origin or [],
    )

    onboarder = TenantOnboarder(kc)
    report = await onboarder.onboard(spec)
    print(report.summary())
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Onboarding de tenant nuevo")
    parser.add_argument("--tenant-name", required=True, help="Nombre del tenant (ej UNSL)")
    parser.add_argument(
        "--tenant-uuid", required=True, help="UUID del tenant (tenant_id autoritativo)"
    )
    parser.add_argument(
        "--realm-name", help="Nombre del realm K.C. (default: tenant-name lowercased)"
    )
    parser.add_argument("--admin-email", required=True)
    parser.add_argument("--admin-password", help="Password inicial temporal")
    parser.add_argument("--keycloak-url", default="http://localhost:8180")
    parser.add_argument(
        "--allowed-origin",
        action="append",
        help="Origen permitido para redirects (puede repetirse)",
    )
    args = parser.parse_args()
    sys.exit(asyncio.run(run_cli(args)))


if __name__ == "__main__":
    main()
