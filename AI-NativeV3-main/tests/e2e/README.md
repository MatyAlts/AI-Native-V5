# Suite Playwright E2E

Suite top-level que ejecuta 5 journeys browser-driven contra los 3 frontends Vite reales y los 12 servicios Python reales del piloto UNSL. Es el unico lugar del repo con cobertura E2E hoy.

## Pre-requisitos

Antes de correr la suite el entorno tiene que estar completo:

1. **Infra**: `make dev-bootstrap` (postgres, redis, keycloak, minio, grafana, prometheus, jaeger).
2. **Migraciones aplicadas**: `make migrate`.
3. **12 servicios Python + 8 CTR partition workers**: arrancar con `bash scripts/dev-start-all.sh`. El workflow asume `LLM_PROVIDER=mock` (default) — sin ese mock el journey 4 pega al LLM real y consume budget.
4. **3 frontends Vite (`:5173/:5174/:5175`)**: `make dev`. (Vite 6 bindea solo IPv6 por default; usar `localhost`, no `127.0.0.1`.)
5. **Seed `seed-3-comisiones.py` aplicado**: `uv run python scripts/seed-3-comisiones.py` (idempotente — pisa el tenant demo `aaaa...`).
6. **Browser binary**: `pnpm exec playwright install chromium` (one-shot por dev, ~150MB en `~/.cache/ms-playwright/`).

El `globalSetup` falla rapido si alguna pre-condicion falta; el mensaje incluye el comando para arreglarla.

## Comandos

```bash
make test-e2e          # asume warm DB (estado normal del daily loop)
make test-e2e-clean    # re-seedea + corre la suite (DESTRUCTIVO sobre tenant demo)
make test-e2e-headed   # Chromium visible + DevTools + breakpoints (debugging manual)

# Reporte HTML (auto-abre tras un fallo, o manual):
pnpm e2e:report
```

## Warm DB vs Clean DB

| Modo | Cuando usarlo | Side-effects |
|------|---------------|--------------|
| `make test-e2e` (warm) | **Default** del daily loop. Asume seed activo. | Journey 4 cierra 1 episodio nuevo (acceptable). |
| `make test-e2e-clean` | CI manual / sospecha de drift / despues de un cambio en el seed. | Pisa la DB del tenant demo: borra y rehace todo. |

El seed cuesta ~30s. Multiplicado por 5-10 debug loops por sesion = 5+ min perdidos. Por eso warm es el default.

## Estructura

```
tests/e2e/
  playwright.config.ts        # Chromium-only, retries=0, artefactos en .dev-logs/
  global-setup.ts             # 4 checks: services, frontends, redis groups, seed
  fixtures/
    seeded-ids.ts             # source of truth de UUIDs/codes del seed
  helpers/
    select-comision.ts        # helper de page interactions
    wait-for-tutor-stream.ts  # expect.poll para SSE del tutor
  journeys/
    01-admin-auditoria.spec.ts
    02-teacher-tareas-practicas.spec.ts
    03-teacher-progression.spec.ts
    04-student-tutor-flow.spec.ts
    05-cross-frontend-ctr-integrity.spec.ts
```

## Convenciones de selectors

Orden de preferencia (D3 del design):

1. `page.getByRole('button', { name: /Verificar/i })`
2. `page.getByTestId('audit-result')` — agregado al frontend cuando role no alcanza
3. `page.getByText(/Mejorando/)` — para cards/labels visibles

NUNCA usar `.bg-primary`, `#radix-:r0:` o selectores Tailwind. Un cambio de paleta no debe romper la suite.

## Fixture central de UUIDs

`fixtures/seeded-ids.ts` es el unico lugar donde viven los UUIDs del seed. Si alguien cambia `scripts/seed-3-comisiones.py` (UUIDs, codigos de TP, numero de estudiantes), **actualizar este fixture en el mismo PR**. La suite va a romper si hay drift — eso es feature, no bug.

## Troubleshooting

### Falla 1 — "CTR workers no estan consumiendo"

```
[e2e-setup] FAIL: ningun consumer activo en ctr.p0..p7 del grupo `ctr_workers`.
  Sugerencia: arranca `./scripts/dev-start-all.sh` (incluye los 8 partition workers).
```

Los 8 workers materializan eventos Redis Streams a Postgres. Si caen, el journey 5 ve el episodio recien cerrado pero `verify` devuelve 404 (los eventos quedaron en stream sin commit). El globalSetup detecta esto antes de arrancar.

Fix:
```bash
bash scripts/dev-stop-all.sh
bash scripts/dev-start-all.sh
```

### Falla 2 — SSE timeout en journey 4

```
Error: timed out waiting for tutor message
```

El tutor stream tarda >15s o nunca llega. Causas:

- `LLM_PROVIDER` no esta en `mock` -> el ai-gateway intenta pegar a Anthropic real con creds invalidas.
- `ai-gateway:8011` o `tutor-service:8006` caidos a mitad de la suite.
- Budget AI del tenant agotado (chequear `aigw:budget:...:tutor:YYYY-MM` en Redis).

Fix:
```bash
echo $LLM_PROVIDER          # debe imprimir "mock"
tail -f .dev-logs/ai-gateway.log
tail -f .dev-logs/tutor-service.log
```

### Falla 3 — Selector no encontrado / TP-01 no aparece

```
Locator: getByRole('cell', { name: 'TP-01' }) — Expected to be visible.
```

El seed cambio (UUIDs, codigos de TP) o no corrio. Diff del fixture vs `seed-3-comisiones.py`:

```bash
rg "TP-0[0-9]" scripts/seed-3-comisiones.py
rg "TP_CODES" tests/e2e/fixtures/seeded-ids.ts
```

Fix: actualizar `tests/e2e/fixtures/seeded-ids.ts` con los codes/UUIDs nuevos.

## CI integration

**Fuera de scope de este change.** La suite se ejecuta localmente y via `make`. Integrar a `.github/workflows/ci.yml` (con services + DB en runners + headless browser) es un change posterior dedicado — requiere infra de runners y configuracion de Postgres/Redis ephemeral.

## Limitaciones declaradas

- **Solo Chromium**. Firefox/WebKit no son target del piloto. Re-evaluar post-piloto si DI UNSL pide cobertura cruzada.
- **No cubre Bearer JWT flow**. Los frontends en dev mode inyectan headers `X-User-Id`/`X-Tenant-Id` via `vite.config.ts`. Cuando F9 cierre (gap B.2 de CLAUDE.md), agregar journey de login real.
- **Visual regression NO implementado**. Assertions son funcionales (texto presente, modal abierto, fila renderizada) — un cambio de Tailwind no debe romper la suite.
- **Journey 4 crea data nueva** (1 episodio cerrado). Acceptable side-effect declarado en `proposal.md`.
- **Mock de `/api/v1/comisiones/mis` en journey 4** (`page.route(...)`): el endpoint devuelve `[]` para students hasta F9 (gap B.2 de CLAUDE.md). El mock es transversal al flow del piloto — no afecta journeys 1-3.
