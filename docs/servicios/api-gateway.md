# api-gateway

## 1. Qué hace (una frase)

Es la puerta única de la plataforma: valida el JWT de Keycloak (RS256), reescribe autoritativamente los headers `X-User-Id`/`X-Tenant-Id`/`X-User-Email`/`X-User-Roles` (plural) `/X-User-Realm`, aplica rate limiting por principal y rutea a los servicios downstream por prefijo de path. Es **la fuente única de identidad** del sistema — el viejo `identity-service` quedó deprecado por [ADR-041](../adr/041-deprecate-identity-service.md) porque toda esa lógica ya vive acá + Casbin descentralizado.

## 2. Rol en la arquitectura

Pertenece a los **transversales**. Infraestructura transversal del plano, sin correspondencia directa con un componente de la arquitectura de la tesis. Existe porque el modelo de seguridad de la plataforma asume que **hay un único punto donde la identidad se valida** — todos los servicios internos confían ciegamente en los headers `X-*` que el gateway setea. Sin gateway, cada servicio tendría que validar JWTs por separado, multiplicando superficie de ataque y costo de coordinación con Keycloak.

Es el único servicio "externamente expuesto" de la plataforma: los frontends y clientes externos sólo conocen `:8000`.

## 3. Responsabilidades

- Ejecutar el `JWTMiddleware` (`apps/api-gateway/src/api_gateway/middleware/jwt_auth.py`): validar `Authorization: Bearer <JWT>` contra el JWKS de Keycloak (`jwt_issuer` + `jwt_jwks_uri`), extraer claims y reescribir los headers `X-*` autoritativamente — **cualquier header `X-*` que venga del cliente se elimina antes** (defensa contra header injection).
- Soportar **modo dev** (`dev_trust_headers=True`): si no hay `Authorization` pero hay `X-User-Id` + `X-Tenant-Id`, aceptar sin validar JWT. Los `vite.config.ts` de los 3 frontends se apoyan en esto para inyectar los headers en el proxy durante desarrollo local sin realm Keycloak onboardeado.
- Ejecutar el `RateLimitMiddleware` sliding-window sobre Redis (`rate_limit_redis_url`, DB 4). Limits por tier:
  - `/api/v1/episodes/*` — 30 req/min por user (alto costo: LLM + CTR).
  - `/api/v1/retrieve` — 60 req/min.
  - `/api/v1/classify_episode` — 20 req/min.
  - Default — 300 req/min.
- Fail-open sobre Redis caído (`rate_limit_middleware.py:46`): si el limiter no puede chequear, deja pasar el request. Preferir falsa no-disponibilidad de control a bloquear requests legítimos.
- Inyectar `X-Request-Id` (UUID v4 si no venía) para correlación en logs.
- Rutear `/api/v1/{prefix}/...` al servicio correspondiente según `ROUTE_MAP` (14 prefijos → 6 servicios). Passthrough de método, query params, body y response (con filtrado de `content-length`/`transfer-encoding`/`connection`).
- Exentar `/`, `/health`, `/metrics`, `/docs`, `/openapi.json`, `/redoc` de JWT y rate limit.

## 4. Qué NO hace (anti-responsabilidades)

- **NO resuelve permisos fine-grained (RBAC)**: el JWT trae los roles (`X-User-Roles`), el gateway los propaga, y la matriz Casbin ([academic-service](./academic-service.md)) resuelve "este role puede hacer esta acción sobre este recurso en este tenant". Es separación clara: autenticación acá, autorización en los servicios.
- **NO aplica circuit breaker ni retry**: si un servicio downstream falla, el error se propaga tal cual. No hay fallback. `httpx.AsyncClient(timeout=30.0)` es el único control de latencia.
- **NO maneja SSE especialmente**: el endpoint `POST /api/v1/episodes/{id}/message` del [tutor-service](./tutor-service.md) es SSE. El gateway lo rutea como `StreamingResponse` — funciona porque el `upstream.content` se yieldea en un solo chunk. **Posible limitación**: requests muy largas pueden no streamear token-por-token a través del gateway. Verificar con tests end-to-end.
- **NO cachea respuestas**: es un proxy; todo passthrough.
- **NO inspecciona ni modifica bodies**: los bodies viajan opacos — sólo se reescriben headers.
- **NO tiene DB propia**: stateless a nivel persistencia. Estado en Redis sólo para contadores del rate limiter.

## 5. Endpoints HTTP

| Método | Path | Qué hace | Auth |
|---|---|---|---|
| `GET` | `/` | Status trivial. | Exento. |
| `GET` | `/health`, `/health/ready` | Health real con `check_redis(rate_limit_redis)` + `check_keycloak_jwks` (epic `real-health-checks`, 2026-05-04). | Exento. |
| `ALL` | `/api/{full_path:path}` | Proxy a los servicios via `ROUTE_MAP`. | JWT + rate limit. |

Las rutas ruteadas (map interno en `routes/proxy.py`):

| Prefijo | Destino |
|---|---|
| `/api/v1/universidades`, `/facultades`, `/carreras`, `/planes`, `/materias`, `/comisiones`, `/periodos`, `/tareas-practicas`, `/tareas-practicas-templates`, `/unidades`, `/bulk` | [academic-service](./academic-service.md) |
| `/api/v1/entregas` | [evaluation-service](./evaluation-service.md) |
| `/api/v1/materiales`, `/retrieve` | [content-service](./content-service.md) |
| `/api/v1/episodes` | [tutor-service](./tutor-service.md) |
| `/api/v1/classify_episode`, `/classifications` | [classifier-service](./classifier-service.md) |
| `/api/v1/analytics` | [analytics-service](./analytics-service.md) |
| `/api/v1/audit/episodes` | [ctr-service](./ctr-service.md) (aliases `/audit/*` apuntan al MISMO handler que el legacy, [ADR-031](../adr/031-audit-aliases-ctr.md)) |

**Prefijos no ruteados hoy** (no aparecen en `ROUTE_MAP` y `resolve_target()` retorna `None`): endpoints de [governance-service](./governance-service.md), [ai-gateway](./ai-gateway.md) (LLM proxy interno), `/api/v1/ctr/*` (eventos write directo del [ctr-service](./ctr-service.md), service-to-service), `/api/v1/attestations/*` ([integrity-attestation-service](./integrity-attestation-service.md), infra institucional separada). Si se consumen desde el frontend, **no pasan por api-gateway** — o el frontend pega directo al servicio interno (no soportado en prod) o el mapa se amplía.

> **Nota**: los servicios deprecados `enrollment-service` ([ADR-030](../adr/030-deprecate-enrollment-service.md)) y `identity-service` ([ADR-041](../adr/041-deprecate-identity-service.md)) ya NO están en el ROUTE_MAP. Bulk-import de inscripciones se centralizó en `academic-service` ([ADR-029](../adr/029-bulk-import-centralized.md)); auth se resuelve acá + Casbin local.

**Match implícito por `startswith`**: `resolve_target()` matchea con `path.startswith(prefix)`, así que `/api/v1/tareas-practicas-templates` queda routeado a academic-service vía el prefix `/api/v1/tareas-practicas` (sin necesidad de entrada propia). Lo mismo pasa con sub-paths: `/api/v1/episodes/{id}/events/codigo_ejecutado` resuelve por `/api/v1/episodes` → tutor-service. Cuando agregues una entidad nueva, verificá si su prefijo no colisiona con uno existente.

## 6. Dependencias

**Depende de (infraestructura):**
- Redis — DB 4 para el rate limit. Si cae, fail-open.
- Keycloak — JWKS endpoint para validar firmas JWT. Cache TTL de 300s (`jwt_jwks_cache_ttl`).

**Depende de (otros servicios):** los 6 servicios a los que rutea (academic, enrollment, content, tutor, classifier, analytics). No es una dependencia de bootstrap: el gateway arranca igual aunque los downstream no respondan, y devuelve errores por request según quién esté caído.

**Dependen de él:**
- [web-admin](./web-admin.md), [web-teacher](./web-teacher.md), [web-student](./web-student.md) — todos sus requests a `/api/*` pasan por aquí (via el proxy de Vite en dev, via `:8000` en prod).

## 7. Modelo de datos

**No tiene DB propia**. Estado en Redis (DB 4):
- Keys del rate limiter: `aigw:rl:{principal}:{path_prefix}` (nombre exacto en `services/rate_limit.py`) — counters sliding window con TTL igual al `window_seconds` del tier.
- Cache JWKS: en memoria del proceso (no Redis), TTL `jwt_jwks_cache_ttl` (300s default).

## 8. Archivos clave para entender el servicio

- `apps/api-gateway/src/api_gateway/middleware/jwt_auth.py` — **el componente crítico**. Comentario explícito: "este middleware es la única fuente de verdad de la identidad. Los servicios internos confían CIEGAMENTE en los headers X-* que vienen del api-gateway". Elimina `X-*` entrantes antes de setear los propios.
- `apps/api-gateway/src/api_gateway/services/jwt_validator.py` — `JWTValidator` con cache de JWKS, verificación de `iss`/`aud`/`exp`, extracción de claims standard (`sub`, `email`, realm_access.roles). `extract_bearer_token()` parsea el header.
- `apps/api-gateway/src/api_gateway/middleware/rate_limit.py` — delegate a `RateLimiter.check()`, fail-open sobre Redis error.
- `apps/api-gateway/src/api_gateway/services/rate_limit.py` — `PATH_LIMITS` (tiers), `principal_from_request()` (user_id > tenant_id > ip como fallback), `RateLimiter` con sliding window.
- `apps/api-gateway/src/api_gateway/routes/proxy.py` — `ROUTE_MAP` + lógica de passthrough con httpx. `resolve_target()` matchea por `startswith(prefix)`.
- `apps/api-gateway/src/api_gateway/main.py` — ensamblaje: crea validator sólo si hay `jwt_issuer`, instancia middlewares, incluye `health.router` + `proxy.router`.
- `apps/api-gateway/tests/unit/test_jwt_validator.py` — cubre JWTs válidos, expirados, firma inválida, claims faltantes.
- `apps/api-gateway/tests/unit/test_rate_limit.py` — sliding window, principales distintos, fail-open.

## 9. Configuración y gotchas

**Env vars críticas** (`apps/api-gateway/src/api_gateway/config.py`):

- `JWT_ISSUER` — ej. `http://keycloak:8080/realms/demo_uni`. **Default vacío** → cae a modo dev.
- `JWT_AUDIENCE` — default `"platform-backend"`.
- `JWT_JWKS_URI` — ej. `http://keycloak:8080/realms/demo_uni/protocol/openid-connect/certs`.
- `JWT_JWKS_CACHE_TTL` — default `300` segundos.
- `DEV_TRUST_HEADERS` — **default `True`**. En prod tiene que ser `False`.
- `RATE_LIMIT_REDIS_URL` — default `redis://127.0.0.1:6379/4`.
- `{SERVICE}_SERVICE_URL` — URLs de los 10 servicios downstream (todos con default `127.0.0.1:{puerto}` — regla de usar `127.0.0.1` explícito en Windows para evitar dual-stack IPv6, ver CLAUDE.md).

**Puerto de desarrollo**: `8000`.

**Gotchas específicos**:

- **`dev_trust_headers=True` en prod rompe el modelo de seguridad**: si alguien pone ese flag en `values-prod.yaml` pensando que es "tolerante", **cualquier cliente puede inyectar `X-User-Id` y `X-Tenant-Id` y actuar como cualquier user**. Checklist pre-deploy: `dev_trust_headers=False` + `jwt_issuer` seteado.
- **`127.0.0.1` vs `localhost` en service URLs**: documentado en CLAUDE.md "Windows + Docker + IPv6". Usar `127.0.0.1` explícito en `{SERVICE}_SERVICE_URL` para evitar que el gateway en Windows resuelva IPv6 y caiga en un container ajeno.
- **Prefijos no ruteados silenciosos**: los endpoints de governance-service, ai-gateway, identity-service y evaluation-service **no están en `ROUTE_MAP`**. Si un cliente externo los pide, recibe 404. Si un frontend los necesita, hoy no puede — habría que agregarlos al map.
- **SSE passthrough**: `iter_content()` yieldea `upstream.content` de una sola vez (no un async iterator del body). Para SSE real token-por-token podría no transmitir incremental. **Verificar con tests e2e** — si el flujo del tutor funciona en prod, el gateway está transmitiendo ok; si hay buffering, cambiar a `client.stream()`.
- **JWKS sin reload activo**: si Keycloak rota keys, el gateway espera hasta que expire el TTL (300s) para re-fetchear. En esa ventana los tokens nuevos pueden fallar. Aceptable para el piloto.
- **Rate limit por IP como fallback**: si el request no trae `X-User-Id` (ni el gateway logra validarlo), el counter es por `client.host`. Detrás de un load balancer que enmascare la IP (misma IP para todos), el counter colapsa al tenant entero. Nota: sólo aplica cuando el JWT no valida; con JWT válido el principal es `user_id`.
- **30s timeout de httpx**: requests lentas (ingesta de materiales grandes, exports pesados) pueden cortarse por el gateway aunque el downstream siga procesando. El bug es del lado del cliente (no sabe si fue éxito o falla). Revisar si algún endpoint requiere timeout más alto.
- **Header autoritativo `X-User-Roles` (plural), NO `X-Role`**: documentos viejos podían tener la versión incorrecta. El JWT trae `realm_access.roles: ["docente", ...]` y el gateway lo serializa como CSV en `X-User-Roles`. Cualquier servicio downstream debe parsear `request.headers["X-User-Roles"].split(",")`.

## 10. Relación con la tesis doctoral

El api-gateway no implementa componentes de la tesis. Su existencia es una **propiedad del modelo de seguridad** que la plataforma eligió (ADR-002 + ADR-008):

1. **Identidad como header autoritativo** (CLAUDE.md "Propiedades críticas"): el gateway es el único que puede setear `X-User-Id`/`X-Tenant-Id`. Los 10 servicios downstream los leen como verdad — el test `HU-086` verifica que un header `X-User-Id` inyectado por un cliente externo **se descarta** antes del routing, y el valor autoritativo del JWT reemplaza. Sin esa defensa, la matriz Casbin podría ser bypasseada.

2. **Aislamiento multi-tenant via header**: el `X-Tenant-Id` que el gateway inyecta es el valor que cada servicio usa en `SET LOCAL app.current_tenant` para activar RLS. Si el gateway confundiera o mezclara el tenant (por mala implementación de la validación de JWT), toda la defensa RLS se vuelve inútil.

3. **Control de costo operacional del piloto**: el rate limit con tier bajo en `/episodes/*` (30 req/min) protege el budget de LLM del piloto. Un estudiante con bucle infinito o un script accidental no pueden quemar el presupuesto mensual en una tarde.

## 11. Estado de madurez

**Tests** (2 archivos unit):
- `tests/unit/test_jwt_validator.py` — JWT válido, expirado, firma inválida, audience mismatch, claims incompletos.
- `tests/unit/test_rate_limit.py` — sliding window correcto, principales distintos, fail-open en Redis down.

**Known gaps**:
- Los servicios periféricos (governance, ai-gateway, attestation) no están en `ROUTE_MAP` — son service-to-service por diseño. Si algún frontend los necesita, hoy no pueden via gateway.
- `byok` endpoints del ai-gateway no están en `ROUTE_MAP` aún — la UI BYOK del web-admin (DEFERIDA) los necesitará.
- SSE passthrough via `StreamingResponse` en una sola emisión — probable buffering (no verificado e2e).
- Sin circuit breaker ni retry policies.
- `dev_trust_headers=True` como default es riesgoso si se mal-despliega.

**Fase de consolidación**:
- F1 — passthrough inicial con JWT opcional (`docs/F1-STATE.md`).
- F3 — validación real de JWT con JWKS.
- F4 — rate limiting sliding window.
- F5 — modo `dev_trust_headers` + reescritura autoritativa de headers.
- 2026-04-29 ([ADR-029](../adr/029-bulk-import-centralized.md), [ADR-030](../adr/030-deprecate-enrollment-service.md), [ADR-031](../adr/031-audit-aliases-ctr.md)) — `enrollment-service` deprecado y bulk-import centralizado en academic-service; aliases `/api/v1/audit/*` ruteados al ctr-service.
- 2026-05-04 (epic `real-health-checks`) — `/health/ready` real con `check_redis + check_keycloak_jwks`.
- 2026-05-07 ([ADR-041](../adr/041-deprecate-identity-service.md)) — `identity-service` deprecado; auth completamente resuelta acá + Casbin descentralizado en cada servicio.
