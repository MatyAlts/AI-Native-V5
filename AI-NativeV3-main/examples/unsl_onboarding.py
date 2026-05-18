"""Ejemplo runnable: onboarding completo del tenant UNSL para el piloto.

Ejecuta los 3 pasos en secuencia para preparar UNSL como tenant de la
plataforma:

  1. Crear realm + client + admin user en Keycloak (tenant_onboarding)
  2. Federar el LDAP institucional de UNSL
  3. Configurar feature flags del piloto

Uso (requiere Keycloak corriendo):

    export KEYCLOAK_ADMIN_PASSWORD=<admin-pw>
    export LDAP_BIND_PASSWORD=<ldap-pw>
    export TENANT_ADMIN_EMAIL=admin@unsl.edu.ar
    python examples/unsl_onboarding.py

En dev local con keycloak en docker-compose:

    export KEYCLOAK_ADMIN_PASSWORD=admin
    export LDAP_BIND_PASSWORD=dev
    python examples/unsl_onboarding.py
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path
from uuid import UUID

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


# Ajustar path para que encuentre el package
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "packages/platform-ops/src"))


# ── Config del tenant UNSL ───────────────────────────────────────────

UNSL_TENANT_UUID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
UNSL_REALM_NAME = "unsl"
KEYCLOAK_URL = os.environ.get("KEYCLOAK_URL", "http://localhost:8180")


async def step1_keycloak_onboarding():
    """Paso 1: Crear realm + client + roles + admin user."""
    from platform_ops import (
        KeycloakClient,
        KeycloakConfig,
        TenantOnboarder,
        TenantSpec,
    )

    logger.info("=== Paso 1: Onboarding Keycloak ===")
    kc_password = os.environ.get("KEYCLOAK_ADMIN_PASSWORD")
    if not kc_password:
        logger.error("KEYCLOAK_ADMIN_PASSWORD no seteado")
        return

    kc = KeycloakClient(
        KeycloakConfig(
            base_url=KEYCLOAK_URL,
            admin_user=os.environ.get("KEYCLOAK_ADMIN_USER", "admin"),
            admin_password=kc_password,
        )
    )

    spec = TenantSpec(
        name="Universidad Nacional de San Luis",
        uuid=UNSL_TENANT_UUID,
        realm_name=UNSL_REALM_NAME,
        admin_email=os.environ.get("TENANT_ADMIN_EMAIL", "admin@unsl.edu.ar"),
        admin_password_temp="ChangeMeAtFirstLogin!",
        allowed_origins=[
            "https://plataforma.unsl.edu.ar",
            "https://plataforma.unsl.edu.ar/admin",
            "https://plataforma.unsl.edu.ar/tutor",
        ],
    )

    onboarder = TenantOnboarder(kc)
    report = await onboarder.onboard(spec)
    logger.info(report.summary())
    return spec


async def step2_ldap_federation(spec):
    """Paso 2: Federar el LDAP institucional."""
    from platform_ops import (
        LDAPConfig,
        LDAPFederationSpec,
        LDAPFederator,
        LDAPGroupMapping,
    )

    logger.info("=== Paso 2: LDAP federation ===")
    ldap_password = os.environ.get("LDAP_BIND_PASSWORD")
    if not ldap_password:
        logger.warning("LDAP_BIND_PASSWORD no seteado — salteando LDAP")
        return

    ldap_spec = LDAPFederationSpec(
        realm_name=spec.realm_name,
        tenant_uuid=spec.uuid,
        display_name="LDAP Institucional UNSL",
        ldap=LDAPConfig(
            connection_url=os.environ.get("LDAP_URL", "ldaps://ldap.unsl.edu.ar:636"),
            bind_dn="cn=admin,dc=unsl,dc=edu,dc=ar",
            bind_credential=ldap_password,
            users_dn="ou=people,dc=unsl,dc=edu,dc=ar",
            use_tls=True,
        ),
        group_mappings=[
            LDAPGroupMapping(
                ldap_group_dn="cn=docentes,ou=grupos,dc=unsl,dc=edu,dc=ar",
                realm_role="docente",
            ),
            LDAPGroupMapping(
                ldap_group_dn="cn=administradores,ou=grupos,dc=unsl,dc=edu,dc=ar",
                realm_role="docente_admin",
            ),
            LDAPGroupMapping(
                ldap_group_dn="cn=estudiantes,ou=grupos,dc=unsl,dc=edu,dc=ar",
                realm_role="estudiante",
            ),
        ],
    )

    # Token provider reutilizando la lógica del KeycloakClient
    import httpx

    async def token_provider() -> str:
        async with httpx.AsyncClient(timeout=10.0) as c:
            r = await c.post(
                f"{KEYCLOAK_URL}/realms/master/protocol/openid-connect/token",
                data={
                    "grant_type": "password",
                    "client_id": "admin-cli",
                    "username": os.environ.get("KEYCLOAK_ADMIN_USER", "admin"),
                    "password": os.environ.get("KEYCLOAK_ADMIN_PASSWORD", ""),
                },
            )
            r.raise_for_status()
            return r.json()["access_token"]

    federator = LDAPFederator(
        keycloak_base_url=KEYCLOAK_URL,
        admin_token_provider=token_provider,
    )
    result = await federator.configure(ldap_spec)
    logger.info("LDAP federation provider_id=%s", result["provider_id"])
    for action in result["actions"]:
        logger.info("  ✓ %s", action)


def step3_feature_flags():
    """Paso 3: Escribir feature flags iniciales del piloto."""
    logger.info("=== Paso 3: Feature flags del piloto ===")

    flags_yaml = """\
# Feature flags del piloto UNSL
# Generado por unsl_onboarding.py

default:
  enable_code_execution: false
  enable_claude_opus: false
  max_episodes_per_day: 50
  welcome_message: Bienvenido a la plataforma
  show_n4_to_students: false

tenants:
  aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa:
    # UNSL piloto — features del piloto activadas
    enable_code_execution: true
    enable_claude_opus: false  # usamos Sonnet para el piloto (costos)
    max_episodes_per_day: 200
    welcome_message: Bienvenido al piloto de la plataforma en UNSL
    show_n4_to_students: true  # el piloto muestra N4 al estudiante
"""

    flags_path = Path(os.environ.get("FEATURE_FLAGS_PATH", "/etc/platform/feature_flags.yaml"))
    try:
        flags_path.parent.mkdir(parents=True, exist_ok=True)
        flags_path.write_text(flags_yaml)
        logger.info("Feature flags escritos en %s", flags_path)
    except PermissionError:
        logger.warning(
            "Sin permisos para escribir en %s. Copiá el siguiente YAML manualmente:\n%s",
            flags_path,
            flags_yaml,
        )


async def main():
    spec = await step1_keycloak_onboarding()
    if spec:
        await step2_ldap_federation(spec)
    step3_feature_flags()
    logger.info("=== Onboarding completado ===")


if __name__ == "__main__":
    asyncio.run(main())
