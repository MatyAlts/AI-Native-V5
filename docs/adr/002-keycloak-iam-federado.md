# ADR-002 — Keycloak como IAM central con federación

- **Estado**: Aceptado
- **Fecha**: 2026-04
- **Deciders**: Alberto Cortez, director de tesis
- **Tags**: seguridad, identidad, federación

## Contexto y problema

Cada universidad del sistema ya tiene su propio IdP institucional (típicamente Shibboleth SAML en universidades nacionales argentinas, algunas con Google Workspace/OIDC o Active Directory). La plataforma necesita:

- Autenticación federada que respete el IdP institucional.
- Gestión centralizada de roles (superadmin, docente_admin, docente, estudiante).
- Autorización fine-grained a nivel de comisión específica.
- Tokens JWT con claims custom (`tenant_id`, `comisiones_activas`, `roles`).

## Drivers de la decisión

- Las universidades no aceptan que los usuarios tengan "otra contraseña" para la plataforma.
- Privacidad: las credenciales institucionales nunca deben llegar a nuestra plataforma.
- Operabilidad: el equipo no puede construir un IAM desde cero ni mantener uno custom.
- Estándares: SAML 2.0 y OIDC son los protocolos de federación aceptados.

## Opciones consideradas

### Opción A — Keycloak 25
Producto open source maduro (Red Hat). Soporta SAML, OIDC, LDAP, SCIM. Admin UI completa. Realm por tenant. Custom claims vía mappers.

### Opción B — Authentik
Alternativa moderna, más simple. Menor adopción institucional. Funcionalmente comparable pero con menos ecosistema.

### Opción C — Construcción propia sobre OAuth2 libraries
Full control, pero 3-6 meses de trabajo solo en IAM.

### Opción D — Auth0 / Okta
Servicios hosted. Buenos, pero costo recurrente alto (~USD 200-500/mes a nuestra escala) y datos de identidad educacional en proveedor externo — fricción con normativas de protección de datos.

## Decisión

**Opción A — Keycloak 25.**

Un **realm por universidad**, cada uno federado con el IdP institucional correspondiente. Tokens emitidos por Keycloak con claims custom. Roles base (`superadmin`, `docente_admin`, `docente`, `estudiante`) como realm-roles. Autorización fine-grained (acceso a comisión específica) se resuelve en capa de aplicación con Casbin (ver ADR-008).

Para operación local y tests: tres realms preconfigurados (`platform`, `demo_uni`, `test_tenant`) en `infrastructure/keycloak/realm-templates/`.

## Consecuencias

### Positivas
- Federación SAML/OIDC/LDAP funciona out of the box.
- Ecosistema grande: documentación, mappers probados, Helm charts oficiales.
- Admin REST API permite automatizar provisioning de realms (ver ADR-009 y F5).
- Tokens JWT autocontenidos: servicios validan sin round-trip a Keycloak.

### Negativas
- Complejidad: Keycloak es laberíntico (realms, clients, roles, groups, mappers, auth flows). Curva de aprendizaje alta.
- Dependencia crítica: si Keycloak está caído, toda la plataforma está caída. Requiere HA en producción.
- Consumo de RAM significativo (1-2 GB por pod con carga baja).
- Los tokens JWT pueden hacerse grandes si hay muchos roles/atributos.

### Neutras
- Si en el futuro se migra a Authentik u otra solución, el patrón (IdP central + realm por tenant + JWT con custom claims) sigue siendo aplicable.

## Referencias

- [Keycloak docs](https://www.keycloak.org/documentation)
- `infrastructure/keycloak/realm-templates/`
- ADR-008 (Casbin para fine-grained)
