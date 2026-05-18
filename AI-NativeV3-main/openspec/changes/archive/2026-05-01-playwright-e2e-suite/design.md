## Context

Hoy la torre de tests del repo es: `vitest + RTL` para componentes (con `fetch` mockeado), `pytest` para 12 servicios Python, smoke por `curl` (`make check-health`), y `make eval-retrieval` para el RAG. **Ningún test conduce un browser real**. El piloto UNSL para defensa doctoral expone 3 frontends + 12 servicios y la pasada minimalist UI mergeó sin red de seguridad — cualquier regresión visual o de integración (Vite proxy, header injection del dev mode, SSE del tutor, navegación TanStack, drift seed↔frontend) queda invisible hasta que un humano la pisa.

**Contexto operativo**: Playwright 1.59.1 ya está en `devDependencies` raíz (instalado en sesión previa), `@platform/ui` ya tiene componentes con tests vitest, los 3 frontends ya inyectan headers `X-User-Id`/`X-Tenant-Id`/`X-User-Roles` via `vite.config.ts` en dev mode (sin Bearer JWT — `dev_trust_headers=True` default). Los 12 servicios + 8 CTR workers corren en background via `scripts/dev-start-all.sh`. Seeds del piloto (`seed-3-comisiones.py`) son idempotentes y producen UUIDs estables.

**Stakeholders**: doctorando (defensa); director de tesis (puede ver la suite verde como evidencia de calidad operativa); DI UNSL (recibe el repo y debe poder correr `make test-e2e` sin instalar 12 cosas más).

**Constraints duros**:
- NO romper invariantes doctorales (CTR append-only, RLS, hashing determinista). La suite es read-only sobre el sistema; el único side-effect es escribir un episodio nuevo en el journey 4.
- NO traer toolchain nueva más allá de `@playwright/test` (ya hay `playwright`). Cero deps que el comité tenga que justificar.
- NO modificar `apps/*` ni `packages/*` salvo agregar `data-testid` selectors estables donde haga falta — y eso solo si los locators por role/text no alcanzan.
- CI integration es scope separado (declarado en proposal).

## Goals / Non-Goals

**Goals:**
- 5 journeys E2E verdes contra los 3 frontends + servicios reales, con artefactos de fallo (screenshot + trace + video) que un humano pueda abrir en `playwright-report/index.html`.
- `globalSetup` que falla rápido y claro si el entorno no está listo (servicios down, workers down, seed faltante).
- Selectors estables: 0 acoplamiento a clases Tailwind ni IDs autogenerados.
- `tests/e2e/fixtures/seeded-ids.ts` como único source of truth para los UUIDs del seed.
- Targets `make test-e2e`, `make test-e2e-clean`, `make test-e2e-headed` para cubrir warm DB, clean DB, debugging.

**Non-Goals:**
- Cross-browser (solo Chromium MVP — Firefox/WebKit duplican mantenimiento sin valor para defensa).
- Visual regression (snapshot pixel-perfect). Assertions son funcionales (texto presente, modal abierto, fila renderizada).
- Load/stress testing (otra herramienta, otra epic).
- Reemplazar `ai-gateway` con mock Playwright — `LLM_PROVIDER=mock` ya cubre eso a nivel infra.
- Cobertura exhaustiva de CRUDs secundarios (carreras, facultades, materiales) — solo los 5 journeys críticos para la tesis.
- CI integration en `.github/workflows/ci.yml` — change posterior.

## Decisions

### D1: Top-level `tests/e2e/`, NO per-frontend

**Decision**: la suite vive en `tests/e2e/` en la raíz del monorepo, NO en `apps/web-{admin,teacher,student}/tests/e2e/`. Un solo `playwright.config.ts`, un solo `globalSetup`, journeys cross-frontend en `tests/e2e/journeys/*.spec.ts`.

**Rationale**:
- El journey 5 ("CTR chain integrity") cruza web-student → web-admin — splitting por frontend lo rompe.
- Compartir `seeded-ids.ts` y helpers de auth entre journeys requiere ubicación única.
- `pnpm` workspace resuelve `@playwright/test` desde root sin configuración extra.

**Alternativa rechazada**: per-frontend. Habría 3 configs casi idénticos, 3 globalSetup, y los journeys cross-frontend romperían el modelo.

### D2: Warm DB asumida + target `make test-e2e-clean` para CI manual

**Decision**: `make test-e2e` asume que el dev tiene seed activo (estado normal del daily loop). `make test-e2e-clean` re-ejecuta `seed-3-comisiones.py` antes de la suite — usar para CI manual o cuando se sospecha drift de data.

**Rationale**:
- Re-seedear cuesta ~30s. Multiplicado por 5-10 debug loops por sesión = 5+ min perdidos en cada iteración.
- El seed es idempotente (borra y rehace tenant `aaaa...`) — re-seedear durante un test que escribió data nueva (journey 4 cierra un episodio) borraría esa data.
- La default no-destructiva refleja el modelo dev real.

**Alternativa rechazada**: re-seedear siempre. Demasiado costoso. La opción más conservadora ("re-seedear si la fixture detecta drift") es over-engineered para 5 journeys.

### D3: Selectors estables — preferencia role > testid > text > nada

**Decision**: orden de preferencia para locators:
1. `page.getByRole('button', { name: /nuevo TP/i })` — robusto, accesible.
2. `page.getByTestId('comision-selector')` — agregar `data-testid` solo donde role/text no alcancen.
3. `page.getByText(/Mejorando/)` — para cards/labels visibles.
4. NUNCA `page.locator('.bg-blue-500.rounded-md')` — clase Tailwind acopla a estilo.
5. NUNCA `page.locator('#radix-:r0:')` — IDs autogenerados Radix/Tailwind cambian entre builds.

**Rationale**:
- ARIA roles + accessible names sobreviven refactors visuales y mejoran a11y como side-effect.
- Tests que rompen ante cambio de Tailwind son ruido.

**Alternativa rechazada**: solo `data-testid` sin role-first. Más rápido de escribir pero deja la suite divorciada de la a11y real.

### D4: Reuso de header injection del proxy Vite — cero auth nueva

**Decision**: la suite navega via `page.goto('http://localhost:5174/...')` y deja que Vite inyecte los headers en el proxy `/api/*`. NO hay setup de Bearer JWT, NO hay mock Keycloak.

**Rationale**:
- Los 3 frontends ya tienen `vite.config.ts` con `configure` hook que inyecta `X-User-Id`/`X-Tenant-Id`/`X-User-Email`/`X-User-Roles`. Los UUIDs hardcodeados son el contrato del dev mode (CLAUDE.md "vite.config.ts hardcodea x-user-id").
- Cualquier auth setup adicional duplica esa lógica y crea drift.

**Trade-off explícito**: el test no cubre el flow de Bearer JWT (Keycloak realm). Eso es invariante diferida (gap B.2 de CLAUDE.md, F9). Cuando F9 cierre, este test puede agregar un journey de login real — fuera de scope hoy.

### D5: `globalSetup` con failover claro

**Decision**: `globalSetup` chequea, en orden:
1. Los 12 servicios responden `200` en `/health` (timeout 2s c/u).
2. Los 3 frontends Vite responden `200` en `/` (timeout 2s c/u).
3. Redis stream `XINFO GROUPS ctr-events-{0..7}` muestra al menos 1 consumer activo (workers CTR consumen).
4. Postgres `academic_main` tiene la comision `aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa` con `nombre='A-Manana'` (smoke test del seed).

Si cualquier check falla, el setup imprime un mensaje accionable con el `make` o script para arreglarlo y aborta antes de que arranque cualquier journey.

**Rationale**:
- Los 5 timeouts crípticos de fallar a mitad de un journey son la peor UX posible para debugging.
- Un fail-fast con "Workers CTR caídos. Corré `bash scripts/dev-start-all.sh`" es lo que un dev necesita.

**Alternativa considerada**: arrancar los servicios desde el setup. Rechazado: `dev-start-all.sh` ya existe y maneja PID tracking en `.dev-logs/pids.txt` — duplicar lógica es deuda silenciosa.

### D6: Estrategia anti-flakiness para SSE del tutor (journey 4)

**Decision**: el journey 4 espera la respuesta del tutor con `expect.poll(async () => await page.locator('[data-testid=tutor-message-last]').textContent(), { timeout: 15_000 }).toMatch(/.+/)`. NO usa `await page.waitForTimeout(5000)`.

**Rationale**:
- SSE chunks llegan al frontend en intervalos imprevisibles. `waitForTimeout` falla si la red está lenta (CI) o pasa antes de que el stream termine en local.
- `expect.poll` reintenta el assertion hasta el timeout, fallando solo si el contenido nunca aparece.

**Trade-off**: 15s de timeout es generoso pero no infinito. Si el LLM mock devuelve >15s, el test es legítimamente raro y vale la pena fallar.

## Risks / Trade-offs

- **[Riesgo] CTR workers caídos rompen journey 5** -> Mitigation: D5 (globalSetup chequea Redis groups). Si los workers caen mid-suite, el journey 5 falla con assertion clara, no con timeout.
- **[Riesgo] Drift seed↔fixture** -> Mitigation: `seeded-ids.ts` centralizado + comentario en `seed-3-comisiones.py` advirtiendo que cualquier cambio de UUIDs requiere actualizar el fixture (será una task explicita).
- **[Riesgo] Selectors frágiles ante refactor visual** -> Mitigation: D3 (role-first), code review de cualquier locator nuevo.
- **[Riesgo] Re-seedear borra data en vivo del dev** -> Mitigation: target `test-e2e-clean` separado (no es default), advertencia en docstring + README.
- **[Trade-off] Solo Chromium** -> Acepto: defensa doctoral no usa Firefox/WebKit. Re-evaluar post-piloto si DI UNSL pide cobertura cruzada.
- **[Trade-off] No cubre Bearer JWT flow** -> Acepto: F9 lo destrabará. El test cubre la realidad operativa del piloto (dev_trust_headers=True).
- **[Trade-off] No CI integration en este change** -> Acepto: requiere infra de runners con Postgres + Redis + browsers; merece un change dedicado.

## Migration Plan

1. **Setup local del dev** (one-shot por colaborador):
   - `pnpm install` (trae `@playwright/test` nuevo).
   - `pnpm exec playwright install chromium` (browser binary, ~150MB).
   - Documentado en `tests/e2e/README.md`.
2. **Ejecución**:
   - Daily loop: `make dev-bootstrap` + `bash scripts/dev-start-all.sh` + `make dev` + (si falta seed) `uv run python scripts/seed-3-comisiones.py` + `make test-e2e`.
   - Debug: `make test-e2e-headed` abre Chromium visible con DevTools y pausa antes de cada step para inspección.
3. **Cuando un journey falla**: `playwright-report/index.html` (auto-abierto si `--reporter=html`) muestra screenshot + trace + video del fallo. Trace permite navegación step-by-step de la página.
4. **Rollback**: `tests/e2e/` es aditivo — borrar el directorio + 3 targets del Makefile + entry de package.json revierte completo. Sin migrations DB.

## Open Questions

Ninguna abierta. Las 6 decisiones (D1-D6) son cerradas; los riesgos están mitigados con tareas concretas que el apply phase ejecuta.
