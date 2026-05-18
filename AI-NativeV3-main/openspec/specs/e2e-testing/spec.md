# e2e-testing

## Purpose

Capability that owns the end-to-end test suite — `tests/e2e/` Playwright top-level (no per-frontend) — covering 5 critical user journeys across the 3 frontends (`web-admin`, `web-teacher`, `web-student`) and the 12 backend services. Provides browser-driven regression coverage that traditional unit/integration tests can't reach: Vite proxy header injection, TanStack Router navigation, SSE streaming from the tutor, and the cross-frontend CTR integrity flow that proves the SHA-256 chain works end-to-end.

## Requirements

### Requirement: Suite Playwright top-level con 5 journeys críticos

El monorepo SHALL contener una suite Playwright en `tests/e2e/` (no per-frontend) que ejecute 5 journeys end-to-end contra los 3 frontends Vite (`:5173/:5174/:5175`) y los 12 servicios Python (`:8000-:8012`) reales. Los 5 journeys SHALL cubrir:

1. web-admin — verificación criptográfica de un episodio CTR seedeado.
2. web-teacher — flujo de Trabajos Prácticos (listado + abrir modal nuevo).
3. web-teacher — vista de Progresión (4 cards resumen + filas de estudiantes).
4. web-student — flujo del tutor (selección TP, abrir episodio, mandar turno, ver respuesta SSE, cerrar).
5. cross-frontend — tras (4), verificación de integridad CTR del episodio recién cerrado en web-admin.

La suite SHALL ser ejecutable via `make test-e2e` (asume warm DB), `make test-e2e-clean` (re-seedea), y `make test-e2e-headed` (Chromium visible para debugging).

#### Scenario: Suite ejecuta los 5 journeys verdes

- **WHEN** el desarrollador corre `make test-e2e` con todos los servicios, los 8 CTR workers, los 3 frontends Vite y el seed `seed-3-comisiones.py` activos
- **THEN** Playwright reporta `5 passed` y exitea con código 0
- **AND** se generan los binarios de browsers en `~/.cache/ms-playwright/` (one-shot por dev)

#### Scenario: Fallo genera artefactos navegables

- **WHEN** un journey falla (assertion no se cumple en el timeout)
- **THEN** Playwright genera `playwright-report/index.html` con screenshot del momento del fallo, trace navegable step-by-step y video del journey
- **AND** los artefactos quedan en `.dev-logs/e2e-artifacts/` (gitignored)

#### Scenario: Re-seed antes del run con `test-e2e-clean`

- **WHEN** el desarrollador corre `make test-e2e-clean`
- **THEN** primero se ejecuta `uv run python scripts/seed-3-comisiones.py` (borra y rehace tenant `aaaa...`)
- **AND** luego corre la suite Playwright
- **AND** la suite pasa porque la data está en estado canonico

### Requirement: GlobalSetup falla rápido con mensaje accionable

El `tests/e2e/global-setup.ts` SHALL verificar pre-condiciones del entorno antes de que cualquier journey arranque, y SHALL abortar con mensaje específico si alguna falla. Las pre-condiciones son:

1. 12 servicios HTTP responden `200` en `/health` (timeout 2s c/u).
2. 3 frontends Vite (`:5173/:5174/:5175`) responden `200` en `/` (timeout 2s c/u).
3. Al menos 1 consumer activo en `XINFO GROUPS` de cualquier stream `ctr-events-{0..7}` de Redis (señal de que los CTR workers están consumiendo).
4. La comision `aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa` existe en Postgres `academic_main` con `nombre = 'A-Manana'` (señal de que el seed corrió).

#### Scenario: Servicios caídos abortan setup con mensaje

- **WHEN** el `globalSetup` corre y `tutor-service:8006/health` no responde dentro de 2s
- **THEN** el setup imprime `"Servicio tutor-service:8006 no responde. Arrancá './scripts/dev-start-all.sh' o verificá '.dev-logs/tutor-service.log'."` y aborta con código no-cero
- **AND** ningún journey arranca

#### Scenario: Workers CTR caídos abortan setup

- **WHEN** el `globalSetup` corre y ningún consumer está activo en `ctr-events-0..7`
- **THEN** el setup imprime `"CTR workers no están consumiendo. Arrancá './scripts/dev-start-all.sh' (incluye los 8 partition workers)."` y aborta con código no-cero

#### Scenario: Seed faltante aborta setup

- **WHEN** el `globalSetup` corre y la query a `academic_main` no devuelve la comision `aaaa...` con `nombre='A-Manana'`
- **THEN** el setup imprime `"Seed `seed-3-comisiones.py` no aplicado. Corré 'make test-e2e-clean' o 'uv run python scripts/seed-3-comisiones.py'."` y aborta con código no-cero

### Requirement: Selectors estables — role/testid > clase Tailwind

Los locators usados por la suite SHALL preferir, en orden:

1. ARIA roles con accessible names: `page.getByRole('button', { name: /Nuevo TP/i })`.
2. `data-testid` agregado al frontend cuando role no alcanza: `page.getByTestId('comision-selector')`.
3. Texto visible: `page.getByText(/Mejorando/)`.

Los locators NUNCA SHALL usar:
- Clases Tailwind: `.bg-blue-500.rounded-md`.
- IDs autogenerados (Radix/Headless UI): `#radix-:r0:`.
- Selectores CSS posicionales frágiles: `:nth-child(3)` salvo cuando la posición sea semántica.

#### Scenario: Locator role-first sobrevive cambio de Tailwind

- **WHEN** un componente cambia de `bg-blue-500` a `bg-emerald-500` sin alterar role ni accessible name
- **THEN** los tests que usan `page.getByRole(...)` siguen pasando
- **AND** ningún assertion se rompe

#### Scenario: Locator basado en clase Tailwind es rechazado en code review

- **WHEN** un PR introduce `page.locator('.bg-primary')` en un journey
- **THEN** el reviewer lo bloquea citando este requirement
- **AND** el PR debe migrarse a role/testid antes de merge

### Requirement: `seeded-ids.ts` único source of truth para UUIDs del seed

Los UUIDs y códigos esperados del seed `seed-3-comisiones.py` (tenant ID, comision IDs, student pseudonyms, template IDs, TP codes) SHALL vivir centralizados en `tests/e2e/fixtures/seeded-ids.ts`. Los archivos `*.spec.ts` SHALL importar desde ahí. Ningún spec SHALL hardcodear UUIDs in-line.

#### Scenario: Spec importa IDs desde fixture central

- **WHEN** un spec necesita el `tenant_id` del piloto
- **THEN** importa `import { TENANT_ID } from "../fixtures/seeded-ids"`
- **AND** no escribe `'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'` literal

#### Scenario: Cambio en seed obliga a tocar fixture

- **WHEN** alguien modifica `seed-3-comisiones.py` cambiando el UUID de un template
- **THEN** la suite falla porque el fixture aún tiene el UUID viejo
- **AND** el desarrollador debe actualizar `seeded-ids.ts` para reflejar el nuevo UUID
- **AND** ese cambio queda explícito en el diff del PR (trazabilidad)

### Requirement: SSE polling para journey del tutor

El journey 4 (web-student → tutor flow) SHALL usar `expect.poll()` con timeout >= 10s para esperar la respuesta streameada del tutor. NO SHALL usar `page.waitForTimeout()` con un valor fijo.

#### Scenario: Stream tarda 8s y el assertion pasa

- **WHEN** el journey envía un turno y el tutor stremea su respuesta en 8s
- **THEN** `expect.poll(...).toMatch(/.+/)` reintenta y pasa cuando el contenido aparece
- **AND** el journey continúa con el cierre del episodio

#### Scenario: Stream nunca llega y el assertion falla con timeout

- **WHEN** el journey envía un turno pero el tutor nunca responde (mock LLM caído, ejemplo)
- **THEN** `expect.poll(...)` agota su timeout (15s default)
- **AND** el journey falla con un mensaje claro `"timed out waiting for tutor message"`
- **AND** el screenshot capta el estado del DOM con el mensaje pendiente

### Requirement: Targets `make` documentados

El `Makefile` raíz SHALL exponer 3 targets:

- `make test-e2e` — corre la suite asumiendo servicios + frontends + seed activos (warm DB).
- `make test-e2e-clean` — corre `seed-3-comisiones.py` y luego la suite (clean DB).
- `make test-e2e-headed` — corre la suite con `--headed --debug` para inspección manual paso a paso.

`tests/e2e/README.md` SHALL documentar pre-requisitos (servicios, workers, seed), comandos, política warm-DB vs clean, y troubleshooting de los 3 modos de falla más comunes (workers caídos, seed desincronizado, SSE timeout).

#### Scenario: Dev nuevo arranca la suite siguiendo el README

- **WHEN** un dev nuevo lee `tests/e2e/README.md` y sigue los pasos
- **THEN** consigue correr `make test-e2e` exitosamente sin pedir ayuda
- **AND** entiende qué hacer si un journey falla por workers caídos
