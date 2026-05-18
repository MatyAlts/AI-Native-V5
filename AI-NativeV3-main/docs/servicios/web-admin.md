# web-admin

## 1. Qué hace (una frase)

Es la consola de gestión académica del tenant: permite a roles `docente_admin` y `superadmin` administrar la jerarquía completa (universidades, facultades, carreras, planes, materias, periodos, comisiones), hacer import masivo desde CSV y revisar clasificaciones N4.

## 2. Rol en la arquitectura

Pertenece a los **frontends**. Sin correspondencia directa con un componente de la arquitectura de la tesis. Existe como UI institucional para operar el plano académico-operacional — es la cara de [academic-service](./academic-service.md) (incluyendo el bulk-import centralizado por [ADR-029](../adr/029-bulk-import-centralized.md), reemplazo del viejo `enrollment-service` deprecado por [ADR-030](../adr/030-deprecate-enrollment-service.md)) para el coordinador académico del tenant (rol `docente_admin`) y el superadmin de la plataforma. Adicionalmente expone gobernanza institucional cross-cohort ([ADR-037](../adr/037-governance-ui.md)), gestión de BYOK keys ([ADR-038](../adr/038-byok-encryption.md)) y verificación de auditoría CTR ([ADR-031](../adr/031-audit-aliases-ctr.md)).

## 3. Responsabilidades

- Renderizar páginas CRUD sobre las entidades del dominio académico (Universidades, Facultades, Carreras, Planes, Materias, Periodos, Comisiones, **Unidades**) + Home + BulkImport + Clasificaciones + Gobernanza + Auditoría + BYOK.
- Ejecutar CRUD completo sobre cada entidad via `/api/v1/*` ruteado por [api-gateway](./api-gateway.md): listar, crear (modal), editar (modal), soft-delete (confirm dialog).
- Soportar la UI del import masivo (`BulkImportPage.tsx`): upload CSV → reporte de dry-run (filas válidas, errores) → botón de commit. **Bulk-import operacional** (gap B.1 cerrado por [ADR-029](../adr/029-bulk-import-centralized.md)): tiene como entidad `inscripciones` (estudiantes en una comisión) — destraba el alta masiva del piloto sin tocar SQL. CSV requiere `comision_id`, `student_pseudonym`, `fecha_inscripcion`. Otras entidades (comisiones, materias, etc.) también soportadas.
- Exponer la vista de Clasificaciones agregadas por comisión (consume `/api/v1/classifications/aggregated` de [classifier-service](./classifier-service.md) via gateway).
- **Página `GovernanceEventsPage.tsx`** ([ADR-037](../adr/037-governance-ui.md)): consume `GET /api/v1/analytics/governance/events` cross-cohort. Filtros cascade facultad → materia → período + CSV export con headers ASCII (cp1252-safe).
- **Página `AuditoriaPage.tsx`** ([ADR-031](../adr/031-audit-aliases-ctr.md), gap D.4): consume `POST /api/v1/audit/episodes/{id}/verify` via api-gateway ROUTE_MAP. Verifica integridad criptográfica SHA-256 de cualquier episodio cerrado en vivo — útil para defensa doctoral (el comité puede ver la verificación en pantalla). NO confundir con las attestations Ed25519 externas (ADR-021) — son dos pruebas independientes complementarias.
- **Página BYOK con `UsagePanel` + stats grid** (epic `ai-native-completion-and-byok`): UI para CRUD de `byok_keys` y visualización de `byok_keys_usage`. **DEFERIDA** al momento del cierre del epic (endpoints CRUD operables vía curl).
- **CRUD de `Unidad`** (epic `unidades-trazabilidad`): página para gestionar unidades por comisión. Permite trazabilidad longitudinal cuando `template_id=NULL`.
- Renderizar el sistema de ayuda in-app uniforme (`HelpButton` en toda page + `helpContent.tsx` con entries) — ver sección "Sistema de ayuda in-app" en CLAUDE.md.
- En dev mode, inyectar headers `X-User-Id`/`X-Tenant-Id`/`X-User-Email`/`X-User-Roles` (plural) en el proxy de Vite (`vite.config.ts`) para que el api-gateway con `dev_trust_headers=True` acepte requests sin JWT real.

## 4. Qué NO hace (anti-responsabilidades)

- **NO interactúa con el CTR como productor**: NO emite episodios ni eventos pedagógicos. SÍ verifica integridad de la cadena CTR via `AuditoriaPage` ([ADR-031](../adr/031-audit-aliases-ctr.md)) — es uso read-only.
- **NO maneja rúbricas ni calificaciones**: es alcance de [evaluation-service](./evaluation-service.md). Acá no hay UI para entregas/correcciones.
- **NO tiene progresión longitudinal ni κ**: esas vistas viven en [web-teacher](./web-teacher.md).
- **NO valida localmente identidad**: se apoya enteramente en el api-gateway (JWT o `dev_trust_headers`). En dev, el header inyectado es `docente_admin,superadmin` hardcoded para no requerir realm Keycloak activo.
- **NO tiene test runner activo**: `package.json` tiene `vitest` declarado y `test: "vitest run --passWithNoTests"`. La suite de tests UI es mínima (los tests del frontend hoy viven en `packages/ui/`).

## 5. Rutas principales

Routing "basado en useState" (no TanStack Router type-safe todavía — previsto F2-F3, ver comentario en `vite.config.ts`). Un `Sidebar` agrupa las rutas por dominio:

| `Route` id | Página | Entidad |
|---|---|---|
| `home` | `HomePage.tsx` | Landing con atajos |
| `universidades` | `UniversidadesPage.tsx` | Universidades |
| `facultades` | `FacultadesPage.tsx` | Facultades |
| `carreras` | `CarrerasPage.tsx` | Carreras |
| `planes` | `PlanesPage.tsx` | Planes de estudios |
| `materias` | `MateriasPage.tsx` | Materias |
| `periodos` | `PeriodosPage.tsx` | Periodos lectivos (+ modal `EditPeriodoModal` migrado al `Modal` del design system) |
| `comisiones` | `ComisionesPage.tsx` | Comisiones — la más grande (637 líneas) |
| `unidades` | `UnidadesPage.tsx` | CRUD de Unidad por comisión (epic `unidades-trazabilidad`) |
| `bulk-import` | `BulkImportPage.tsx` | CSV → dry-run → commit (incluye `inscripciones` por ADR-029) |
| `clasificaciones` | `ClasificacionesPage.tsx` | Distribución N4 por comisión |
| `governance-events` | `GovernanceEventsPage.tsx` | Cross-cohort governance events ([ADR-037](../adr/037-governance-ui.md)) con filtros cascade + CSV export |
| `auditoria` | `AuditoriaPage.tsx` | Verificación SHA-256 en vivo de episodios cerrados ([ADR-031](../adr/031-audit-aliases-ctr.md)) |
| `byok` (DEFERIDA) | `ByokPage.tsx` | CRUD de BYOK keys + `UsagePanel` + stats grid (endpoints operables; UI deferida) |

## 6. Dependencias

**Depende de (servicios):**
- [api-gateway](./api-gateway.md) via proxy `/api` de Vite (default `http://127.0.0.1:8000`).
- Aguas abajo del gateway: [academic-service](./academic-service.md) (la mayoría de las operaciones, incluyendo `BulkImportPage` por ADR-029), [classifier-service](./classifier-service.md) (`ClasificacionesPage`), [analytics-service](./analytics-service.md) (`GovernanceEventsPage` por ADR-037), [ctr-service](./ctr-service.md) (`AuditoriaPage` via aliases `/api/v1/audit/*` por ADR-031), [ai-gateway](./ai-gateway.md) (página BYOK DEFERIDA cuando se implemente).

**Depende de (packages workspace):**
- `@platform/ui` — `Sidebar`, `Modal`, `HelpButton`, `PageContainer`, tokens de CSS.
- `@platform/auth-client` — keycloak-js + `authenticatedFetch` (hoy no invocado activamente en dev porque el proxy inyecta headers directo).
- `@platform/contracts` — schemas TypeScript sincronizados con los Pydantic del backend.

**Dependen de él:** nadie — es consumidor humano.

## 7. Modelo de datos

Frontend — no tiene persistencia propia. Usa los contratos TS de `@platform/contracts` para tipar requests/responses contra los servicios backend.

**State management**: `useState` local + `useEffect` con el patrón "Promise.then()" (no TanStack Query activo, aunque la dependencia está en `package.json`). El patrón del repo exige memoizar `fetchFn` con `useCallback` cuando son deps de `useEffect` — gotcha documentado en CLAUDE.md "Frontends React".

## 8. Archivos clave para entender el servicio

- `apps/web-admin/src/router/Router.tsx` — Routing state-based, `NAV_GROUPS`, switch de render.
- `apps/web-admin/src/App.tsx` — trivial (`<Router />`).
- `apps/web-admin/src/pages/ComisionesPage.tsx` — la página más extensa (637 líneas) — sirve de referencia del patrón CRUD completo con modales.
- `apps/web-admin/src/pages/BulkImportPage.tsx` — flujo dry-run → commit. Maneja `ImportResponse` de enrollment-service.
- `apps/web-admin/src/pages/ClasificacionesPage.tsx` — consume el endpoint `classifications/aggregated`, renderiza distribución + timeseries.
- `apps/web-admin/src/pages/GovernanceEventsPage.tsx` — cross-cohort events ([ADR-037](../adr/037-governance-ui.md)), filtros cascade facultad/materia/período, CSV export con headers ASCII.
- `apps/web-admin/src/pages/AuditoriaPage.tsx` — verificación SHA-256 en vivo via `/api/v1/audit/episodes/{id}/verify` ([ADR-031](../adr/031-audit-aliases-ctr.md)).
- `apps/web-admin/src/pages/UnidadesPage.tsx` — CRUD de Unidad por comisión (epic `unidades-trazabilidad`).
- `apps/web-admin/src/utils/helpContent.tsx` — entries del sistema de ayuda in-app. Español sin tildes (evita cp1252 en Windows). Tokens centralizados en `packages/ui/src/tokens/theme.css`.
- `apps/web-admin/src/lib/` — clientes HTTP tipados.
- `apps/web-admin/vite.config.ts` — proxy `/api` + inyección de headers en dev (user UUID `33333333-...`, roles `docente_admin,superadmin`).

## 9. Configuración y gotchas

**Env vars**:
- `VITE_API_URL` — override del target del proxy (default `http://127.0.0.1:8000`).

**Puerto de desarrollo**: `5173` (default de Vite). Si hay containers ajenos en ese puerto, Vite brinca al siguiente disponible — leer el log de `make dev`.

**Gotchas específicos** (documentados en CLAUDE.md):

- **Headers hardcoded en dev**: `vite.config.ts` inyecta `x-user-id: 33333333-3333-3333-3333-333333333333` + roles `docente_admin,superadmin`. El UUID `33333333-3333-3333-3333-333333333333` (hardcoded en `vite.config.ts:43`) esta declarado como constante `WEB_ADMIN_USER_ID` en `scripts/seed-3-comisiones.py` (cumple el gate `check-vite-seed-sync.py`). En dev_trust_headers mode, el rol elevado se infiere del header `x-user-roles: docente_admin,superadmin` que inyecta el proxy Vite — Casbin enforcement es por rol, no por user_id. Distinto al `11111111-...` de web-teacher.
- **Tailwind v4 + pnpm workspace**: `index.css` debe tener `@source "../../../packages/ui/src/**/*.{ts,tsx}"` — sin eso, Tailwind v4 no escanea las clases usadas en `@platform/ui` (symlink pnpm queda fuera de `node_modules` por default) y los modales se renderizan sin `max-width`. Silencioso en typecheck, visible sólo en browser.
- **Patrón `useCallback` obligatorio para fetchFn en useEffect**: ver CLAUDE.md "Frontends React" — sin `useCallback`, closures inline crean dep nueva en cada render → loop infinito → rate limiter 429. Aplica a todos los patrones "useState + Promise.then()".
- **Seed Casbin desactualiza enforcer en memoria**: si editás policies vía `make seed-casbin` con los backends corriendo, hay que **matar y relanzar** los servicios Python afectados — el enforcer cacheado no refresca con `--reload`.
- **Modal variant mismatch**: los form modals NO deben pasar `variant="dark"` o los labels `text-slate-700` quedan invisibles sobre fondo oscuro. El `Modal` default es `variant="light"`.
- **No usar `localStorage` ni `sessionStorage` para auth**: `@platform/auth-client` maneja tokens en memoria del keycloak-js. En dev el proxy los bypassa totalmente.

## 10. Relación con la tesis doctoral

El web-admin no implementa componentes de la tesis. Es la interfaz operativa del **plano académico-operacional** y habilita al rol institucional (`docente_admin`, `superadmin`) a hacer las operaciones de bootstrap y mantenimiento necesarias para que el piloto corra:

- Dar de alta una universidad, facultad, carrera, plan, materias.
- Crear periodos lectivos (el invariante "no crear comisión en período cerrado" lo valida el backend, la UI lo refleja).
- Crear comisiones con su `curso_config_hash` — el campo que después se propaga a todos los eventos CTR del piloto (ver [ctr-service](./ctr-service.md) Sección 10).
- Importar padrones CSV — hoy el commit no persiste; el workflow real usa `POST /bulk` de academic-service.

La vista de Clasificaciones es un **viewer** de las agregaciones que produce [classifier-service](./classifier-service.md) — no implementa análisis por sí misma. El análisis empírico (κ, progresión, A/B) vive en [web-teacher](./web-teacher.md).

## 11. Estado de madurez

**Tests**: no hay suite activa. Los tests unitarios de componentes UI (`Modal`, `HelpButton`, `PageContainer`) viven en `packages/ui/src/components/*.test.tsx` (25 tests totales de la foundation compartida).

**Known gaps**:
- Routing state-based — migración a TanStack Router type-safe prevista F2-F3 (la dep ya está en `package.json`).
- Sin tests e2e del flujo BulkImport end-to-end.
- Test runner configurado con `--passWithNoTests` — no hay suite real.
- Página BYOK DEFERIDA — endpoints CRUD del ai-gateway operables vía curl o cliente HTTP.
- Tokens visuales centralizados en `packages/ui/src/tokens/theme.css` (paleta "Stack Blue institucional" #185FA5; light backgrounds — rejected dark sidebar). Audit redesign post-skill `impeccable` está en deuda — ver `PRODUCT.md` y `DESIGN.md` en root.

**Fase de consolidación**:
- F1 — scaffold inicial con Sidebar + 10 páginas CRUD (`docs/F1-STATE.md`).
- F5 — integración con keycloak-js (hoy latente, activada con `VITE_KEYCLOAK_URL`).
- 2026-04-29 — `BulkImportPage` con entidad `inscripciones` ([ADR-029](../adr/029-bulk-import-centralized.md)); `AuditoriaPage` ([ADR-031](../adr/031-audit-aliases-ctr.md)).
- 2026-05-04 (epic `ai-native-completion-and-byok`) — `GovernanceEventsPage` ([ADR-037](../adr/037-governance-ui.md)) cross-cohort. Página BYOK DEFERIDA.
- 2026-05-04 — refactor de tokens centralizados en `packages/ui` con paleta "Stack Blue institucional" #185FA5.
- 2026-05-07 (epic `unidades-trazabilidad`) — `UnidadesPage` con CRUD por comisión.
- F8+ — migración a TanStack Router pendiente. Audit UX/UI redesign post-skill `impeccable` (ver `PRODUCT.md` y `DESIGN.md` en root).
