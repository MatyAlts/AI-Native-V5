## Why

Hoy el repo tiene **cero cobertura E2E**. Vitest + RTL cubre componentes (mockeando `fetch`), `pytest` cubre los 12 servicios Python, `make check-health` y los smoke-tests por curl validan endpoints — pero **ningún test conduce un browser real por el journey de usuario**. La consecuencia operativa es que cualquier regresión visual o de integración (proxy Vite, header injection, SSE del tutor, navegación entre rutas TanStack, drift seed↔frontend) **es invisible hasta que un humano la encuentra en vivo**.

Con la defensa doctoral en el horizonte cercano y la pasada minimalist UI ya mergeada sin red de seguridad, este es el gap de mayor leverage para cerrar antes de exponer la plataforma al comité y al piloto. La meta cuantitativa es concreta: pasar de **0 a 5 journeys cubiertos** que ejecuten sobre los frontends reales (`:5173/:5174/:5175`) y los servicios reales (`:8000-:8012`) — lo más cercano posible al uso del piloto sin ser piloto.

`playwright@^1.59.1` ya está en `devDependencies` raíz (instalado en sesión previa), así que la inversión incremental es escribir specs + glue de bootstrap, no traer una toolchain nueva.

## What Changes

- Suite Playwright top-level en `tests/e2e/` (NO per-frontend) que cubre 5 journeys end-to-end:
  1. **web-admin → Auditoría CTR**: navegar a "Integridad CTR", pegar un `episode_id` seedeado conocido, assert `valid:true` visible.
  2. **web-teacher → Trabajos Prácticos**: comisión auto-seleccionada, tabla con ≥2 TPs publicadas, click "+ Nuevo TP" → modal abre, cancelar sin guardar.
  3. **web-teacher → Progresión**: 4 cards resumen (Mejorando/Estable/Empeorando/Datos insuficientes) con datos, ≥1 fila de estudiante con barras de progresión.
  4. **web-student → Tutor flow**: comisión auto-seleccionada, ver 2 TP cards, click "Empezar a trabajar" en TP-01, episodio abre, mandar turno ("¿qué es una variable?"), ver respuesta streameada (SSE), cerrar episodio.
  5. **CTR chain integrity (cross-frontend)**: tras (4), volver a web-admin Auditoría y verificar el episodio recién cerrado (`valid:true`, `events_count >= 4`).
- Configuración Playwright (`playwright.config.ts` en `tests/e2e/`): Chromium-only, headless en CI, `--headed` opt-in local, `screenshot: 'only-on-failure'`, `trace: 'retain-on-failure'`, `video: 'retain-on-failure'`, artefactos a `.dev-logs/e2e-artifacts/` (ya `.gitignore`-d).
- `globalSetup` que verifica que los 12 servicios respondan `/health` y los 3 frontends Vite estén bindeados antes de arrancar la suite (falla rápido con mensaje claro en vez de 5 timeouts crípticos).
- Estrategia de auth: **reusar el header injection del proxy Vite** (`vite.config.ts` ya inyecta `x-user-id`, `x-tenant-id`, `x-user-roles` en dev mode). Cero infra de auth nueva. Los UUIDs hardcodeados de cada frontend siguen siendo el contrato.
- Estrategia de data: **warm DB asumida** + target separado `make test-e2e-clean` que ejecuta `uv run python scripts/seed-3-comisiones.py` antes de la suite. Razón: re-seedear cuesta ~30s, multiplicado por debug loops es prohibitivo. La suite asume que el dev tiene seed activo (lo que ya pide el daily loop).
- Nuevo target en `Makefile`:
  - `make test-e2e` — corre la suite asumiendo servicios + frontends + seed activos.
  - `make test-e2e-clean` — re-seedea y corre la suite (para CI manual / debugging desde estado limpio).
  - `make test-e2e-headed` — arranca con `--headed --debug` para inspección manual.
- `package.json` raíz: agregar `@playwright/test` (peer del runner; `playwright` ya está) y scripts npm `e2e`, `e2e:headed`, `e2e:report`.
- `.gitignore`: agregar `.dev-logs/e2e-artifacts/`, `playwright-report/`, `test-results/`.

## Capabilities

### New Capabilities

- `e2e-testing`: Cobertura E2E browser-driven de los 3 frontends + flujo del tutor con verificación cruzada CTR. Incluye los 5 journeys, el contrato del `globalSetup` (servicios sanos + frontends bindeados), la estrategia warm-DB vs reseed, la convención de selectores estables (preferir `data-testid` o roles ARIA — NO clases Tailwind), y el contrato de artefactos de fallo (screenshot + trace + video).

### Modified Capabilities

Ninguna. Esta capability nace nueva — no toca specs existentes (no hay specs E2E previas en `openspec/specs/`). El header injection del proxy Vite y los seeds ya viven en código y no se modifican; sólo se consumen.

## Impact

- **Código nuevo**: `tests/e2e/{playwright.config.ts,global-setup.ts,journeys/*.spec.ts,fixtures/seeded-ids.ts}`. Sin cambios a `apps/*` o `packages/*` — es un layer aditivo.
- **`Makefile`**: 3 targets nuevos (`test-e2e`, `test-e2e-clean`, `test-e2e-headed`).
- **`package.json` raíz**: agregar `@playwright/test`, scripts npm.
- **`.gitignore`**: artefactos de Playwright.
- **Browsers**: `pnpm exec playwright install chromium` (one-shot por dev — documentado en README de `tests/e2e/`).
- **CI**: **explicitamente fuera de scope de este change**. La integración a `.github/workflows/ci.yml` (con servicios + DB en runners + headless browser) es un change separado posterior. Este proposal entrega la suite ejecutable localmente y vía `make`.
- **Tiempo estimado**: 1.5 días (Día 2-3 del epic).
- **Servicios requeridos para que la suite pase**:
  - 12 servicios Python en `:8000-:8012` (los 3 frontends Vite en `:5173-:5175`).
  - 8 CTR partition workers corriendo (sin ellos el journey 5 falla — los eventos Redis quedan en stream sin materializar a Postgres; ver hallazgo en engram `smoke-test/pedagogical-plane`).
  - `LLM_PROVIDER=mock` activo (evita pegar a Anthropic real; ver mismo hallazgo).
  - Seed `seed-3-comisiones.py` ejecutado.

## Non-goals

- **Cross-browser**: solo Chromium en MVP. Firefox/WebKit no son target del piloto y multiplican el costo de mantenimiento sin valor para la defensa.
- **Visual regression**: los assertions son funcionales (texto presente, modal abierto, fila renderizada), NO pixel-perfect snapshots. Un cambio de Tailwind no debe romper la suite.
- **Load testing**: ni stress, ni concurrencia, ni performance budgets. Otra herramienta (k6) y otro change.
- **Mocking del LLM dentro del test**: el test usa `LLM_PROVIDER=mock` del ai-gateway tal cual está hoy. No reemplaza ai-gateway con un mock Playwright.
- **Cobertura exhaustiva**: 5 journeys = los caminos críticos de la tesis. CRUDs secundarios (carreras, facultades, materiales) no entran al MVP.
- **CI integration**: como se aclaró arriba, separado.

## Risks

- **Flakiness por SSE del tutor**: el journey 4 espera el stream del tutor. Con timing racy puede fallar intermitentemente. Mitigación: usar `expect.poll()` con timeout generoso (15s) sobre el contenido del último mensaje, no sleeps fijos. Selectors estables vía `data-testid` en `EpisodePage.tsx` — agregar si no existen es tarea menor del apply phase.
- **Workers CTR no corriendo**: el journey 5 depende de los 8 CTR partition workers que materializan Redis Streams a Postgres. Hoy se arrancan a mano (`scripts/dev-start-all.sh`). Si están caídos, `audit verify` del episodio recién cerrado devuelve 404 (ver hallazgo engram `smoke-test/pedagogical-plane`). Mitigación: el `globalSetup` chequea explicitamente `XINFO GROUPS` en al menos una partición Redis y aborta con mensaje `"CTR workers no están consumiendo. Arrancá ./scripts/dev-start-all.sh"` antes de arrancar.
- **Drift seed ↔ test data**: si alguien cambia `seed-3-comisiones.py` (UUIDs, número de TPs, etc.), los selectors quiebran silenciosamente. Mitigación: `tests/e2e/fixtures/seeded-ids.ts` centraliza los IDs/codes esperados (TP-01, comision A `aaaaaaaa-...`, student `b1b1b1b1-0001-...`) — un cambio al seed obliga a tocar el fixture, lo que da trazabilidad.
- **Re-seedear es destructivo**: `make test-e2e-clean` pisa la DB del dev. Documentado en el target Makefile y en el README de `tests/e2e/`. La suite por default (warm DB) es no-destructiva.
- **Header injection sólo aplica a tráfico que pasa por proxy Vite**: si el test hace `request.post(...)` directo (no via página), no inyecta. Mitigación: convención — todos los API calls del test van via `page.goto()` y UI, no via `APIRequestContext`. Excepción: el `globalSetup` que sí pega directo a `:8000/health` (no necesita auth).

## Acceptance criteria

- [ ] `make test-e2e` corre la suite asumiendo servicios + frontends + seed activos y exitea 0 con los **5 journeys verdes**.
- [ ] `make test-e2e-clean` re-seedea + corre + exitea 0.
- [ ] Ante cualquier fallo, Playwright genera `playwright-report/index.html` con screenshot, trace navegable y video del journey roto.
- [ ] `tests/e2e/README.md` documenta: prereqs (servicios, workers, seed), comandos, política warm-DB vs clean, troubleshooting de los 3 modos de falla más comunes (workers caídos, seed desincronizado, SSE timeout).
- [ ] Selectors estables: cero acoplamiento a clases Tailwind o IDs autogenerados. Todo lo testeado expone `data-testid` o role ARIA.
- [ ] `tests/e2e/fixtures/seeded-ids.ts` único punto de verdad para IDs del seed; ningún `.spec.ts` hardcodea UUIDs.
- [ ] CI integration **NO entregable acá** (declarado explícitamente en este proposal y en el README de la suite).
