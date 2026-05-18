# Plan operativo B.2 — JWT con `comisiones_activas` claim

**Estado**: PAUSADO. Requiere Keycloak operacional + coordinación institucional UNSL.

**Origen**: gap B.2 de la auditoría de coherencia backend ↔ frontend (2026-04-29). Documentado como CRÍTICO bloqueante para uso real con SSO institucional.

**Por qué este documento existe**: las recomendaciones priorizadas de la auditoría incluían B.2, pero NO es ejecutable sin Keycloak corriendo (que requiere coordinación con DI UNSL — los 5 puntos pendientes documentados en ADR-021 / `docs/RESUMEN-EJECUTIVO-2026-04-27.md`). Este plan deja la implementación lista para que, cuando se desbloquee la infra, alguien la ejecute mecánicamente sin tener que re-investigar el problema.

---

## Síntoma actual (verificado contra el código, 2026-04-29)

`GET /api/v1/comisiones/mis` ([apps/academic-service/src/academic_service/routes/comisiones.py:107](../apps/academic-service/src/academic_service/routes/comisiones.py#L107)) JOINea contra la tabla `usuarios_comision` — esa tabla solo trae **docentes / JTP / auxiliares**, NO estudiantes (que viven en `inscripciones` con `student_pseudonym`).

Consecuencia operativa hoy:
- Si un estudiante real loguea con SSO Keycloak → el `ComisionSelector` del web-student queda **vacío** → app inutilizable.
- En dev mode el web-student cae al fallback de `vite.config.ts` (UUID hardcoded `b1b1b1b1-0001-0001-0001-000000000001` que existe sólo en `seed-3-comisiones.py`). En producción ese UUID **no existe** → el endpoint igualmente devuelve vacío.

CLAUDE.md ya documenta esto como gap conocido pendiente F9.

## Por qué este plan NO se ejecutó en la sesión 2026-04-29

Tres dependencias externas sin las cuales el cambio no es testeable ni desplegable:

1. **Keycloak con realm UNSL configurado** — el cambio toca claims del JWT. Sin Keycloak corriendo no se puede testear.
2. **Federación LDAP completa** — las inscripciones se cargan via bulk-import (ADR-029) con `student_pseudonym` derivado de la federación. Si el flow LDAP→pseudonym→inscripción no está cerrado, el claim `comisiones_activas` apunta a inscripciones huérfanas.
3. **Coordinación con DI UNSL** — los 5 puntos pendientes del piloto (ADR-021 / RESUMEN-EJECUTIVO) están sin resolver. Avanzar B.2 sin esa coordinación es prematuro.

## Diseño propuesto

### Cambios en Keycloak

1. **Custom protocol mapper** (Java SPI o JavaScript mapper) que para cada login del estudiante:
   - Resuelve el `student_pseudonym` a partir del `sub` (subject) del JWT base — vía función de pseudonimización determinista (compatible con `packages/platform-ops/privacy.py`).
   - Lee la lista de `inscripciones` activas para ese pseudonym desde la base `academic_main`.
   - Inyecta un claim `comisiones_activas: list[str]` (UUIDs de comisiones) en el access token.
2. **Mapeo del claim al token type**: el claim debe estar disponible en `access_token` (no solo `id_token`) porque el api-gateway valida el access token para autorizar requests.

**Alternativa (sin Java SPI)**: usar un **groups-mapper** estándar de Keycloak donde cada comisión es un grupo Keycloak. La membership del usuario al grupo se sincroniza vía bulk-import. Más simple operacionalmente, pero requiere mantener consistencia entre `inscripciones` (Postgres) y `groups` (Keycloak) — dos sources of truth.

**Recomendación**: empezar con groups-mapper para piloto-1 y migrar a SPI custom en piloto-2 si se necesita lógica más rica.

### Cambios en api-gateway

[apps/api-gateway/src/api_gateway/auth/jwt.py](../apps/api-gateway/src/api_gateway/auth/jwt.py) (o el módulo equivalente que valida JWT y extrae claims):

1. Leer claim `comisiones_activas` del access token (o `groups` filtrado por prefix `comision:` si va por groups-mapper).
2. Inyectar como header autoritativo `X-Comisiones-Activas` en formato CSV o JSON-array al servicio downstream.
3. Si el claim NO existe en el token (estudiante sin inscripciones, error de federación), responder 403 con mensaje claro: *"No hay comisiones activas asociadas a tu cuenta. Contactá al docente."*

### Cambios en academic-service

[apps/academic-service/src/academic_service/routes/comisiones.py:107](../apps/academic-service/src/academic_service/routes/comisiones.py#L107):

1. Modificar `GET /api/v1/comisiones/mis` para que:
   - Si el caller tiene rol `estudiante`: devolver las comisiones cuyos UUIDs están en el header `X-Comisiones-Activas` (cross-checked contra `inscripciones` en la base por defensa en profundidad — el header es autoritativo pero debe ser consistente).
   - Si el caller tiene rol `docente`/`docente_admin`/`superadmin`: comportamiento actual (JOIN con `usuarios_comision`).
2. **Defensa en profundidad**: el handler valida que cada comision en el header pertenezca al `tenant_id` del caller (RLS doble-check). Si una no, log warning + skip.

### Cambios en frontends

- `apps/web-student/vite.config.ts`: el header `X-User-Id` hardcoded del dev mode debe acompañarse de un fallback `X-Comisiones-Activas` con los UUIDs del seed activo. Documentar en el comment que esto es DEV ONLY.
- En producción con SSO real, los frontends NO inyectan headers — el api-gateway valida el JWT y los inyecta downstream.

### Tests requeridos

1. **Unit en academic-service**: `test_comisiones_mis_lee_header_para_estudiante` — mockea User con role `estudiante`, header `X-Comisiones-Activas` con 2 UUIDs, verifica que devuelve sólo esos.
2. **Unit en academic-service**: `test_comisiones_mis_filtra_por_tenant_aunque_header_traiga_otro_tenant` — defensa en profundidad.
3. **Integration con Keycloak**: requiere Keycloak corriendo con groups-mapper configurado. Login de estudiante de prueba, decode del JWT, assertion de `comisiones_activas` claim.
4. **E2E web-student**: el `ComisionSelector` muestra las comisiones del claim post-login. **Requiere Keycloak en CI** — bloqueante hasta que la infra esté.

## Coordinación institucional necesaria

Antes de implementar, resolver con DI UNSL:

1. ¿Keycloak realm UNSL ya tiene configurada la federación LDAP completa?
2. ¿Hay un mecanismo de sincronización `inscripciones ↔ groups` o se hace por bulk import periódico?
3. ¿La pseudonimización del estudiante se hace en Keycloak (custom mapper) o en api-gateway al recibir el sub?
4. ¿Qué pasa si un estudiante se inscribe mid-cuatrimestre — su token activo no tiene la nueva comisión hasta el próximo refresh?

Estas son **decisiones académicas + arquitectónicas**, no técnicas puras.

## Estimación de trabajo (post-desbloqueo de infra)

| Fase | LOC efectivo | Dependencias |
|---|---|---|
| Custom groups-mapper en Keycloak | ~50 (config XML/JSON) | Keycloak corriendo |
| api-gateway: inyectar X-Comisiones-Activas | ~30 LOC | tests con Keycloak |
| academic-service: modificar `/comisiones/mis` | ~40 LOC + 3 tests | DB de pruebas con inscripciones |
| frontends: ajustar fallback dev | ~10 LOC | — |
| Tests E2E con Keycloak | ~80 LOC | docker-compose con Keycloak para CI |
| **Total** | **~210 LOC** | **Keycloak + LDAP + DI UNSL** |

## Recomendación de timing

Implementar B.2 en la **misma ventana** en que se cierre la coordinación institucional para el deploy del `integrity-attestation-service` (ADR-021) — son las dos tareas que dependen de DI UNSL y conviene encararlas juntas para no fragmentar la conversación institucional.

## Cuando esté listo para ejecutar

Re-abrir esta tarea como una nueva entrada en `SESSION-LOG.md` con la fecha del momento de implementación. Marcar B.2 de la auditoría como `RESUELTO con commit XYZ` y agregar el ADR correspondiente (probablemente ADR-032).

## Referencias

- Auditoría de coherencia backend ↔ frontend (2026-04-29) — gap B.2.
- ADR-021 — Ed25519 attestation; los 5 puntos institucionales pendientes con DI UNSL.
- `docs/RESUMEN-EJECUTIVO-2026-04-27.md` — coordinación institucional documentada.
- `docs/pilot/attestation-deploy-checklist.md` — checklist operativo del piloto que comparte la misma ventana institucional.
- CLAUDE.md "Brechas conocidas" — declaración del gap pre-iter-2.
