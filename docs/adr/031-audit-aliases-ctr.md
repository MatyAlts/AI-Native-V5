# ADR-031 — Aliases públicos `/api/v1/audit/*` para auditoría CTR desde web-admin

- **Estado**: Aceptado
- **Fecha**: 2026-04-29
- **Deciders**: Alberto Cortez, director de tesis
- **Tags**: backend, api-gateway, ctr, frontend, auditabilidad, defensa-doctoral
- **Cierra**: D.4 de la auditoría de coherencia backend ↔ frontend (2026-04-29).

## Contexto y problema

El `ctr-service` ([`apps/ctr-service/src/ctr_service/routes/events.py`](../../apps/ctr-service/src/ctr_service/routes/events.py)) tiene desde F3 un endpoint `POST /api/v1/episodes/{id}/verify` que recomputa la cadena criptográfica SHA-256 de un episodio y compara `self_hash` y `chain_hash` contra los persistidos. Es el **endpoint que materializa el invariante append-only del CTR** (ADR-010) — si pasa, la cadena está íntegra.

Pre-ADR-031, ese endpoint NO estaba expuesto al frontend:

- El `ROUTE_MAP` del api-gateway ([`proxy.py:40`](../../apps/api-gateway/src/api_gateway/routes/proxy.py#L40)) tiene `"/api/v1/episodes": tutor_service_url` — el prefix `/api/v1/episodes/*` rutea **al tutor-service**, no al ctr-service.
- Verificar la integridad requería SSH al servicio o llamar al ctr-service directo (puerto 8007), saltando el gateway. **No usable desde el web-admin**.

Esto es una **oportunidad fuerte para la defensa doctoral**: una UI que muestre la verificación criptográfica del CTR en vivo es exactamente el tipo de evidencia visual que el comité necesita para validar que el invariante append-only NO es solo declarativo. El propio CLAUDE.md ("Propiedades críticas") incluye este invariante como verificable; faltaba la afordancia UX.

## Drivers de la decisión

- **Materializar la auditabilidad declarada de la tesis**: el ADR-021 (registro Ed25519) cierra el lado de attestation externa; ADR-031 cierra el lado de **verificación interna on-demand** desde la propia plataforma.
- **No romper el ROUTE_MAP existente**: `/api/v1/episodes/*` hacia tutor-service es service-to-service crítico (open/close/abandoned/events). NO se puede mover.
- **Cero duplicación de lógica**: el handler `verify_episode_chain` debe ser **el mismo** que el legacy — alias de routing, no copia de código.
- **Casbin ya cubre los roles**: `READ_ROLES` del ctr-service incluye superadmin/docente_admin/docente. La auditoría es accesible para los roles correctos sin cambios de policy.

## Opciones consideradas

### A — Aliases en `audit_router` con prefix `/api/v1/audit` (ELEGIDA)

Crear un router separado en ctr-service con prefix `/api/v1/audit` que registra los handlers existentes (read + verify) via `add_api_route` apuntando a las mismas funciones. Sumar `/api/v1/audit` al `ROUTE_MAP` del api-gateway → ctr-service.

**LOC efectivo**: ~12 LOC en ctr-service routes/events.py + 1 línea de `app.include_router` en main.py + 1 línea en gateway ROUTE_MAP + UI frontend (~190 LOC) + tests (3) + ADR.

### B — Mover los endpoints de read/verify del CTR a `/api/v1/audit/*` directamente

Renombrar las rutas legacy de `/api/v1/episodes/{id}` y `/api/v1/episodes/{id}/verify` a `/api/v1/audit/episodes/{id}` y `/api/v1/audit/episodes/{id}/verify`.

**Descartada porque**: rompe consumers service-to-service. El tutor-service consume `GET /api/v1/episodes/{id}` del ctr-service para reconstruir state ([`get_episode_state` en tutor routes](../../apps/tutor-service/src/tutor_service/routes/episodes.py)). Renombrar requiere actualizar TODOS los callers + bumpear coordinación interna. La opción A es backwards-compatible.

### C — Resolver el conflicto cambiando el matching del proxy a longest-prefix

Refactorizar `resolve_target` para usar longest-prefix matching en vez de first-match.

**Descartada porque**: cambio sutil del comportamiento del gateway con riesgo de romper rutas que dependen del orden de inserción del dict. Más quirúrgico crear un prefix nuevo (Opción A) que tocar el resolver.

### D — Proxy en tutor-service que llame al ctr-service

Sumar al tutor-service un endpoint `POST /api/v1/episodes/{id}/verify` que internamente llama al ctr-service.

**Descartada porque**: introduce una HTTP hop adicional + responsabilidad cruzada. La auditoría del CTR es responsabilidad del ctr-service, no del tutor.

## Decisión

**Opción A**. Aliases públicos `/api/v1/audit/episodes/{id}` y `/api/v1/audit/episodes/{id}/verify` registrados en el `audit_router` del ctr-service, ruteados desde el api-gateway via prefix `/api/v1/audit` → `ctr_service_url`.

### Cambios concretos

| Archivo | Cambio |
|---|---|
| [`apps/ctr-service/src/ctr_service/routes/events.py`](../../apps/ctr-service/src/ctr_service/routes/events.py) | Nuevo `audit_router = APIRouter(prefix="/api/v1/audit")`. Al final del archivo, dos `audit_router.add_api_route(...)` que registran las funciones existentes `get_episode` y `verify_episode_chain` bajo los paths nuevos. Cero duplicación. |
| [`apps/ctr-service/src/ctr_service/main.py`](../../apps/ctr-service/src/ctr_service/main.py) | Línea `app.include_router(events.audit_router)` agregada después del existente `events.router`. |
| [`apps/api-gateway/src/api_gateway/routes/proxy.py`](../../apps/api-gateway/src/api_gateway/routes/proxy.py) | Entrada `"/api/v1/audit": settings.ctr_service_url` en `ROUTE_MAP`. |
| [`apps/web-admin/src/lib/api.ts`](../../apps/web-admin/src/lib/api.ts) | Tipos `ChainVerificationResult`, `EpisodeWithEvents` + helper `auditApi.verifyEpisode(episodeId)` y `auditApi.getEpisode(episodeId)`. |
| [`apps/web-admin/src/pages/AuditoriaPage.tsx`](../../apps/web-admin/src/pages/AuditoriaPage.tsx) | Nueva. Form con input UUID + botón verify; muestra resultado con colorización OK (verde) / FAIL (rojo) + detalles `events_count`, `failing_seq`, `integrity_compromised`. |
| [`apps/web-admin/src/router/Router.tsx`](../../apps/web-admin/src/router/Router.tsx) | Nueva entrada `auditoria` en `Route` union, sumada al `NAV_GROUPS` bajo grupo "Auditoria" con icono `ShieldCheck`. |
| [`apps/web-admin/src/utils/helpContent.tsx`](../../apps/web-admin/src/utils/helpContent.tsx) | Entrada `auditoria` con explicación de cadena, failing seq, flag persistente, y referencia a ADR-021/ADR-010. |

## Consecuencias

### Positivas

- **Cierra el gap D.4 de la auditoría 2026-04-29** sin tocar contracts ni romper consumers service-to-service.
- **Defensa doctoral**: el director de tesis y el comité pueden verificar en vivo, desde la UI, la integridad criptográfica de cualquier episodio del piloto. Es la materialización empírica del invariante "CTR append-only" (ADR-010).
- **Cero duplicación de lógica**: los handlers son los mismos. Si en el futuro el algoritmo de verificación cambia (por ej. nuevo formato de canonicalización), el cambio aplica a ambos paths automáticamente. Tests `test_audit_aliases.py` cubren esto.
- **Backwards-compatible**: el path legacy `/api/v1/episodes/{id}/verify` sigue funcionando para llamadas service-to-service existentes (no las hay hoy, pero está disponible).
- **Casbin sin cambios**: `READ_ROLES` ya cubre los roles relevantes. La auditoría es accesible para superadmin/docente_admin/docente.

### Negativas / trade-offs

- **Dos paths para la misma función**: `/api/v1/episodes/{id}/verify` (legacy) y `/api/v1/audit/episodes/{id}/verify` (alias). Documentado en docstring de [`events.py`](../../apps/ctr-service/src/ctr_service/routes/events.py). Tests garantizan que apuntan al mismo handler.
- **Surface API más amplia**: el gateway ahora rutea un prefix más. Insignificante en performance pero es una entrada más que mantener en el ROUTE_MAP.
- **Web-admin necesita el episode_id manualmente**: el operador tiene que pegarlo en el input. Mejora futura: agregar drilldown desde `ClasificacionesPage` a `AuditoriaPage` con el episode_id pre-cargado. Diferido — no bloquea la funcionalidad.

### Neutras

- El integrity-attestation-service (ADR-021) sigue como capa externa de auditabilidad complementaria. Combinables: la verificación interna (este ADR) + la attestation Ed25519 firmada institucionalmente forman dos pruebas independientes.
- El `audit_router` queda como pattern aplicable a otros endpoints de auditoría futuros (ej. ver el histórico de attestations en UI sin cambiar el frontend del classifier-service).

## Tests cubriendo el ADR

[`apps/ctr-service/tests/unit/test_audit_aliases.py`](../../apps/ctr-service/tests/unit/test_audit_aliases.py) — 3 tests:

1. `test_audit_get_episode_apunta_al_mismo_handler_que_legacy` — verifica que el GET `/api/v1/audit/episodes/{id}` resuelve a la **misma función** `get_episode` que el legacy `/api/v1/episodes/{id}`.
2. `test_audit_verify_episode_apunta_al_mismo_handler_que_legacy` — análogo para POST `/verify`.
3. `test_audit_router_solo_expone_aliases_de_lectura` — sanity: el `audit_router` NO expone POST `/events` ni nada más; el endpoint legacy sigue exponiendo `/events` para writes service-to-service.

**Resultado**: 3/3 PASS contra el patch del repo (verificado 2026-04-29).

Frontend: TypeScript estricto + biome verde sobre `AuditoriaPage.tsx`, `Router.tsx`, `lib/api.ts`, `helpContent.tsx`.

## Sugerencias para mejoras futuras

- **Drilldown**: desde `ClasificacionesPage` con un click en una fila, navegar a `AuditoriaPage` con el `episode_id` pre-cargado. Reduce fricción para el flow "veo algo raro → verifico".
- **Listar episodios con `integrity_compromised=true`**: endpoint nuevo `GET /api/v1/audit/episodes/compromised` + tabla en `AuditoriaPage`. Útil para el integrity sweep periódico.
- **Combinar con attestations Ed25519 (ADR-021)**: mostrar al lado del resultado de `verify` el JSONL de attestation firmada — si hay match, doble prueba.
- **Export del log de verificación**: `GET /api/v1/audit/episodes/{id}/verify-log` que persista cada verificación on-demand con timestamp + caller. Útil para auditorías externas que requieren trazabilidad de quién verificó qué cuándo.

## Referencias

- Auditoría de coherencia backend ↔ frontend (2026-04-29) — gap D.4.
- ADR-010 — append-only del CTR; el invariante que esta UI verifica.
- ADR-021 — registro externo Ed25519 (auditabilidad complementaria).
- Tesis Sección 7.3 — auditabilidad del CTR como propiedad central.
- CLAUDE.md "Propiedades críticas" — invariantes del sistema verificables.
