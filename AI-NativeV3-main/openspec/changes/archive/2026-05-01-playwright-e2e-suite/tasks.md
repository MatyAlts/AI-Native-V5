## 1. Setup base de la suite

- [x] 1.1 Agregar `@playwright/test` a `devDependencies` del `package.json` raíz (mismo rango de version que `playwright` ya instalado: `^1.59.1`).
- [x] 1.2 Crear `tests/e2e/playwright.config.ts` con: `testDir: './journeys'`, `fullyParallel: false` (cross-frontend acoples), `retries: 0` (no enmascarar flakiness en MVP), `reporter: [['html', { open: 'on-failure' }], ['list']]`, `use: { headless: true, baseURL: 'http://localhost:5173', trace: 'retain-on-failure', screenshot: 'only-on-failure', video: 'retain-on-failure' }`, `outputDir: '.dev-logs/e2e-artifacts/'`, `globalSetup: './global-setup.ts'`. Projects: 1 solo proyecto Chromium (`devices['Desktop Chrome']`).
- [x] 1.3 Crear `tests/e2e/fixtures/seeded-ids.ts` exportando: `TENANT_ID`, `COMISION_A_ID`/`COMISION_B_ID`/`COMISION_C_ID`, `STUDENT_A1_ID..A6_ID` (de A-Manana), `STUDENT_B1_ID..B6_ID`, `STUDENT_C1_ID..C6_ID`, `TEMPLATE_1_ID`/`TEMPLATE_2_ID`, `DOCENTE_USER_ID`, `TP_CODES` (lista de codigos de TP publicadas que el seed crea, e.g. `["TP-01", "TP-02"]`). Fuente: leer `scripts/seed-3-comisiones.py` y extraer literales.
- [x] 1.4 Crear `tests/e2e/global-setup.ts` que implemente las 4 pre-condiciones del spec (servicios, frontends, Redis groups, seed). Usa `node:fetch` para HTTP, `ioredis` para Redis (ya está en deps via web-student? si no, usar `redis` cliente simple), `pg` para Postgres (ya en deps de testcontainers? si no, fallback: hacer query via api-gateway endpoint). En cada falla imprimir mensaje accionable y `process.exit(1)`.
- [x] 1.5 Agregar a `.gitignore`: `tests/e2e/playwright-report/`, `tests/e2e/test-results/`, `.dev-logs/e2e-artifacts/`.

## 2. Targets Makefile + scripts npm

- [x] 2.1 Agregar al `Makefile` el target `test-e2e`: `pnpm exec playwright test --config=tests/e2e/playwright.config.ts`.
- [x] 2.2 Agregar `test-e2e-clean`: corre `uv run python scripts/seed-3-comisiones.py` antes y luego `pnpm exec playwright test ...`.
- [x] 2.3 Agregar `test-e2e-headed`: `pnpm exec playwright test --config=tests/e2e/playwright.config.ts --headed --debug`.
- [x] 2.4 Agregar a `package.json` raíz scripts: `"e2e": "playwright test --config=tests/e2e/playwright.config.ts"`, `"e2e:headed": "playwright test --config=tests/e2e/playwright.config.ts --headed"`, `"e2e:report": "playwright show-report tests/e2e/playwright-report"`.

## 3. Helper de page interactions

- [x] 3.1 Crear `tests/e2e/helpers/select-comision.ts` con función `selectComision(page, comisionName: 'A-Manana' | 'B-Tarde' | 'C-Noche')` que abre el `ComisionSelector` y hace click. Reusable en journeys 2, 3, 4.
- [x] 3.2 Crear `tests/e2e/helpers/wait-for-tutor-stream.ts` con función `waitForTutorReply(page, timeoutMs = 15000)` que usa `expect.poll(() => page.getByTestId('tutor-message-last').textContent()).toMatch(/.+/)`.

## 4. Journey 1 — web-admin Auditoría CTR

- [x] 4.1 Crear `tests/e2e/journeys/01-admin-auditoria.spec.ts`. Setup: `page.goto('http://localhost:5173/auditoria')`. Test: pegar un `episode_id` del seed (importar de fixture; el seed produce episodios cerrados — extraer 1 de la lista de student A1).
- [x] 4.2 Click en botón "Verificar" (locator: `page.getByRole('button', { name: /verificar/i })`). Assert: aparece el resultado con `valid: true`. Locator: `page.getByText(/valid.*true/i)` o un `data-testid` agregado al componente de resultado.
- [x] 4.3 Si la página no expone `data-testid` para el área de resultado, agregarlo en `apps/web-admin/src/pages/AuditoriaPage.tsx` (`<div data-testid="audit-result">...`). Cambio mínimo, no semántico.

## 5. Journey 2 — web-teacher Trabajos Prácticos

- [x] 5.1 Crear `tests/e2e/journeys/02-teacher-tareas-practicas.spec.ts`. Setup: `page.goto('http://localhost:5174/tareas-practicas')`. La comisión debería auto-seleccionarse (default del frontend); si no, usar helper `selectComision(page, 'A-Manana')`.
- [x] 5.2 Assert: la tabla muestra al menos 2 TPs. Locator: `expect(page.getByRole('row')).toHaveCount({ atLeast: 2 })` o contar filas en `<tbody>`.
- [x] 5.3 Click en "+ Nuevo TP" (locator: `page.getByRole('button', { name: /nuevo.*tp/i })`). Assert: modal abre. Locator: `page.getByRole('dialog')` o `data-testid="tp-create-modal"`.
- [x] 5.4 Click en "Cancelar" o ESC. Assert: modal cierra.

## 6. Journey 3 — web-teacher Progresión

- [x] 6.1 Crear `tests/e2e/journeys/03-teacher-progression.spec.ts`. Setup: `page.goto('http://localhost:5174/progression')`. Seleccionar comisión B-Tarde con `selectComision` (cohorte balanceada, mejor para vista poblada).
- [x] 6.2 Assert: 4 cards resumen renderizan: "Mejorando", "Estable", "Empeorando", "Datos insuficientes". Locator: `page.getByText(/Mejorando|Estable|Empeorando|Datos insuficientes/i)` con `count: 4` (o assertion individual por card).
- [x] 6.3 Assert: al menos 1 fila de estudiante con barras de progresión visibles. Locator: `page.getByTestId('student-row')` con `count >= 1`. Agregar `data-testid` en `apps/web-teacher/src/views/ProgressionView.tsx` si no existe.

## 7. Journey 4 — web-student Tutor flow

- [x] 7.1 Crear `tests/e2e/journeys/04-student-tutor-flow.spec.ts`. Setup: `page.goto('http://localhost:5175/')` (web-student auto-loguea como student `b1b1b1b1-0001-...`).
- [x] 7.2 Assert: comisión A-Manana auto-seleccionada (header del frontend), 2 TP cards visibles.
- [x] 7.3 Click en "Empezar a trabajar" en la primera TP card. Assert: navegación a `/episode/<uuid>` con `episode_id` real.
- [x] 7.4 Locate input del tutor: `page.getByRole('textbox', { name: /pregunta|mensaje/i })` o `data-testid="tutor-input"`. Escribir "¿qué es una variable?" y enviar (ENTER o botón "Enviar").
- [x] 7.5 Esperar respuesta SSE con helper `waitForTutorReply(page)`. Assert: aparece contenido en `[data-testid=tutor-message-last]`.
- [x] 7.6 Cerrar episodio: click en "Finalizar episodio" o equivalente. Locator: `page.getByRole('button', { name: /finalizar|cerrar/i })`. Assert: confirmación modal aparece, click "Sí".
- [x] 7.7 Assert: redirige a la lista de TPs o muestra mensaje "Episodio cerrado".
- [x] 7.8 Capturar el `episode_id` de la URL durante este journey y exportarlo via `test.info().attach()` o un fixture compartido para que journey 5 lo reuse.
- [x] 7.9 Si los `data-testid` `tutor-input`, `tutor-message-last`, `tp-card` no existen en `apps/web-student/src/`, agregarlos en los componentes correspondientes (cambios mínimos, sin alterar markup ni clases).

## 8. Journey 5 — Cross-frontend CTR integrity

- [x] 8.1 Crear `tests/e2e/journeys/05-cross-frontend-ctr-integrity.spec.ts`. Marcar como `test.describe.configure({ mode: 'serial' })` y declarar dependencia de journey 4 (correr DESPUÉS).
- [x] 8.2 Recuperar el `episode_id` cerrado en journey 4 (via fixture compartido o storage state). Si Playwright no puede pasar data trivialmente entre specs, leer el ultimo episodio cerrado del student `b1b1b1b1-0001-...` via SQL en `globalSetup` previo (no), o via un fetch al api-gateway dentro del test (preferido).
- [x] 8.3 `page.goto('http://localhost:5173/auditoria')`. Pegar el `episode_id` del paso anterior.
- [x] 8.4 Click "Verificar". Assert: `valid: true` AND `events_count >= 4` (los 4 eventos que el journey 4 generó: `episodio_abierto`, `prompt_enviado`, `tutor_respondio`, `episodio_cerrado`).
- [x] 8.5 Documentar en el spec un comentario: "Este journey valida que el CTR escribió la cadena criptográfica correctamente — depende de los 8 partition workers consumiendo Redis Streams."

## 9. README de la suite

- [x] 9.1 Crear `tests/e2e/README.md` con secciones: (a) Pre-requisitos (12 servicios via `dev-start-all.sh`, 3 frontends via `make dev`, seed via `seed-3-comisiones.py`), (b) Comandos (`make test-e2e`, `make test-e2e-clean`, `make test-e2e-headed`), (c) Warm DB vs Clean DB explicación, (d) Troubleshooting con 3 fallas típicas: "Workers no consumen → corré dev-start-all.sh", "SSE timeout → verificá ai-gateway log", "Selector no encontrado → seed cambió, actualizá seeded-ids.ts".

## 10. Verificación E2E ✅ — **5/5 verde en 6.2s**

- [x] 10.1 Chromium binary instalado en `~/.cache/ms-playwright/chromium-1217/`.
- [x] 10.2 `make test-e2e` corrió **5/5 verde en 6.2s** (2 corridas consecutivas estables).
- [ ] 10.3 Test de globalSetup forzando fallo — diferido (no bloqueante para defensa; el `globalSetup` ya corrió con 4/4 chequeos OK).
- [ ] 10.4 Test de artefacto de fallo — durante el debug de la sesión Playwright generó traces/screenshots/videos correctamente al fallar (confirmado en `tests/e2e/.dev-logs/e2e-artifacts/`).
- [ ] 10.5 `make test-e2e-clean` — diferido (re-seedeo destructivo, no se prueba en esta sesion para no pisar la data activa que journeys 4+5 cerraron).

## 11. Quality gates

- [x] 11.1 `pnpm exec biome check tests/e2e/` pasa (formato + lint TypeScript).
- [x] 11.2 `pnpm exec tsc --noEmit -p tests/e2e/tsconfig.json` (crear `tsconfig.json` mínimo si no hay) — typecheck limpio.
- [x] 11.3 Tests Python no afectados por la epic — la epic solo crea `tests/e2e/`, edita `Makefile`/`package.json`/`.gitignore` y agrega 4 `data-testid` en componentes frontend (cambios JSX-only sin lógica).
- [x] 11.4 `make check-rls` pasa: `[OK] Todas las tablas con tenant_id tienen policy RLS + FORCE`.
- [x] 11.5 `git status` confirma cambios aditivos para esta epic: `tests/e2e/` (nuevo), edits a `Makefile`/`package.json`/`.gitignore`, y `data-testid` props en `AuditoriaPage.tsx`/`ProgressionView.tsx`/`TareaSelector.tsx`/`EpisodePage.tsx`. Otros archivos modificados en working tree son del minimalist UI pase preexistente, no de esta epic.
