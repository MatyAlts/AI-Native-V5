# ADR-056 — Tenant fijo en el piloto mono-institucion (RLS forzado, ejercitado en single-tenant)

- **Estado**: Aceptado
- **Fecha**: 2026-06
- **Deciders**: Alberto Cortez, director de tesis
- **Tags**: seguridad, multi-tenancy, rls, auth
- **QA**: hallazgo #13 (QA-seguridad 2026-06-15)

## Contexto y problema

La invariante de plataforma es **multi-tenancy por Row-Level Security forzado
en Postgres** (ADR-001): toda tabla con `tenant_id` tiene policy RLS activa y
el driver entra con `SET LOCAL app.current_tenant = ...` por request. El
diseno contempla derivar el `tenant_id` por request — el path Keycloak lo
toma de un claim del token y el aislamiento entre instituciones se ejercita en
vivo.

Pero el piloto actual es **mono-institucion (UTN)**. El `ClerkJWTValidator`
usa un `fixed_tenant_id` (param del constructor, `jwt_validator.py:232`;
docstring "tenant_id es fijo, no viene del token" en `:216`) — cableado en
prod al tenant del piloto via config — en vez de derivar el tenant de un
claim del token Clerk. Por contraste, el path Keycloak SI exige el claim
(`jwt_validator.py:193-195`: token sin `tenant_id` → rechazado). Consecuencia
operativa:

- El header `X-Tenant-Id` que el api-gateway inyecta a los servicios internos
  es **constante** en prod (siempre el tenant del piloto).
- La aislacion cross-tenant via RLS **nunca se ejercita** con datos reales: no
  hay un segundo tenant contra el cual demostrar que el RLS bloquea fugas.

No hay leak hoy — con un solo tenant no hay frontera que cruzar. Pero la
invariante "RLS multi-tenant forzado" queda **no demostrable en vivo**: el
mecanismo esta forzado en Postgres y verificado por `make check-rls` (toda
tabla con `tenant_id` tiene policy), pero se ejercita degradado a
single-tenant. La auditoria #13 lo marca como deuda de demostrabilidad, no
como vulnerabilidad activa.

## Drivers de la decisión

- **El piloto es mono-institucion por alcance**: UTN es la unica institucion.
  Derivar tenant del token no aporta valor hoy y agrega superficie (mapeo
  claim→tenant, manejo de tokens sin el claim, etc.).
- **No reescribir el path de auth a ultimo momento**: el `fixed_tenant_id` es
  simple, auditable y suficiente para el piloto. Cambiarlo introduce riesgo de
  regresion en el unico flujo de auth productivo.
- **La invariante de seguridad NO se relaja**: el RLS sigue FORZADO en
  Postgres. La degradacion es del *ejercicio* de la invariante (single-tenant),
  no de su *enforcement* (que sigue activo y verificado en CI).
- **El path multi-tenant real ya existe** (Keycloak deriva tenant de claim) —
  la decision es no activarlo en el piloto, no inventarlo desde cero a futuro.

## Decisión

1. **En el piloto, el `tenant_id` es FIJO por diseno** — viene de
   `fixed_tenant_id` en config, NO se deriva del token Clerk. Es una decision
   consciente alineada al alcance mono-institucion del piloto, no un descuido.
2. **El RLS queda FORZADO en Postgres** (sin cambios respecto a ADR-001) pero
   **ejercitado en single-tenant**: `make check-rls` sigue garantizando que
   toda tabla con `tenant_id` tiene policy, y el `SET LOCAL app.current_tenant`
   sigue corriendo por request. Lo que NO se ejercita en vivo es el cruce
   entre dos tenants distintos.
3. **Para multi-institucion futura** (piloto-2 / produccion multi-tenant):
   - Derivar `tenant_id` de un claim del token (como ya hace el path Keycloak),
     eliminando el `fixed_tenant_id` en ese deployment.
   - Agregar un **smoke-test cross-tenant**: dos tenants, request del tenant A
     no puede leer/escribir filas del tenant B — demostrando el RLS en vivo, no
     solo su presencia estructural.

## Consecuencias

### Positivas

- Auth del piloto simple, auditable y estable. Cero riesgo de regresion por
  reescribir el path productivo a ultimo momento.
- La invariante de seguridad core (RLS forzado) se mantiene intacta y
  verificada por CI — la degradacion es de ejercicio, no de enforcement.
- El camino a multi-tenant real esta documentado y ya tiene un path de
  referencia funcional (Keycloak), no requiere diseno nuevo.

### Negativas / trade-offs

- La invariante "RLS multi-tenant forzado" **no es demostrable en vivo** en el
  piloto: se confia en `make check-rls` (estructural) + tests, no en un cruce
  cross-tenant productivo. Aceptado mientras el alcance sea mono-institucion.
- Si el piloto sumara una segunda institucion sin antes derivar el tenant del
  token, todos los datos caerian bajo el mismo `fixed_tenant_id` — fuga
  silenciosa. **Mitigacion**: la transicion a multi-institucion DEBE ejecutar
  los dos pasos de la decision (derivar del claim + smoke-test cross-tenant)
  ANTES de onboardear el segundo tenant.

### Neutras

- No hay cambio de codigo en este ADR — documenta una decision by-design ya
  vigente y fija el contrato para la evolucion futura. El `fixed_tenant_id`
  permanece como esta.

## Referencias

- ADR-001 — Multi-tenancy via Row-Level Security forzado.
- ADR-002 — Federacion IAM Keycloak (path que deriva tenant de claim).
- `apps/api-gateway/src/api_gateway/services/jwt_validator.py:216,232` —
  `ClerkJWTValidator(fixed_tenant_id=...)`; vs `:193-195` (Keycloak exige el
  claim `tenant_id`).
- QA-seguridad 2026-06-15, hallazgo #13.
- `make check-rls` (`scripts/check-rls.py`) — verificacion estructural de
  policies RLS en CI.
