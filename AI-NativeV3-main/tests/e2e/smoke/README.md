# Smoke E2E API — `tests/e2e/smoke/`

Suite Python de smoke E2E que pega al api-gateway real (`:8000`) + ai-gateway
(`:8011`) + governance (`:8010`) + ctr-service (`:8007`) + Postgres real, con
el stack already-up. Cubre la clase de bugs que **escapan a los tests unit
porque mockean DB**.

Origen: auditoría del 2026-05-04 detectó que 446 tests unit pasaban en verde
mientras la API CRUD de BYOK estaba completamente rota en runtime (bug del
`SET LOCAL app.current_tenant = :tid` con bind params, que Postgres rechaza)
y 2 migrations alembic estaban sin aplicar (`test_cases JSONB` + `byok_keys`).
Esta suite es la red para que esa clase de bug no vuelva a pasar.

NO confundir con la suite Playwright en `tests/e2e/journeys/` — esa maneja
browser y los 3 frontends. Esta es API-only y rapidísima (~2s).

## Cómo correrlo local

Pre-requisito: stack up. Si no lo está:

```bash
make dev-bootstrap                          # postgres, redis, keycloak, minio, ...
make migrate                                # las 4 bases al head
uv run python scripts/seed-3-comisiones.py  # seed con 3 comisiones / 18 students / 94 episodios cerrados
bash scripts/dev-start-all.sh               # arranca los 12 servicios Python (logs en /tmp/piloto-logs/)
```

Luego:

```bash
make test-smoke                # corre la suite (~2s, 33 tests)
```

Override del DSN de Postgres:

```bash
SMOKE_PG_DSN=postgresql://user:pass@host:5432 make test-smoke
```

Override del api-gateway URL:

```bash
SMOKE_API_BASE_URL=http://staging-gateway:8000 make test-smoke
```

## Cómo se autentica el client (descubrimiento I.1)

El api-gateway en dev mode tiene `dev_trust_headers=True` (config default).
El middleware de auth (`apps/api-gateway/src/api_gateway/middleware/jwt_auth.py`)
hace este flujo:

1. Si la request trae `Authorization: Bearer ...`, intenta validarlo (con un
   JWTValidator si está configurado).
2. Si NO trae Authorization Y trae `X-User-Id` + `X-Tenant-Id`, **pasa sin
   validar JWT** y propaga los headers tal cual aguas abajo.
3. Caso contrario: 401.

Los `vite.config.ts` de los 3 frontends del repo (`apps/web-{admin,teacher,student}`)
hacen exactamente eso en su `configure` hook del proxy `/api`: **eliminan el
Authorization header y setean los X-* hardcoded** (UUIDs del seed). Replicamos
ese patrón en `conftest.py::_headers_for_role`.

Header crítico: `X-User-Roles` (PLURAL). Si mandás `X-Role` o `X-Roles`, el
gateway los ignora y los servicios downstream no autorizan.

Cuando el JWT validator real entre en producción (Keycloak con realm UNSL
operacional), esta suite va a fallar con 401 — habría que generar un Bearer
firmado con la clave del realm. Para piloto-1 dev, headers X-* es suficiente.

## Estructura

```
tests/e2e/smoke/
├── README.md                       (este archivo)
├── conftest.py                     fixtures session-scoped (auth, http client, ids)
├── _helpers.py                     helpers no-fixture (fetch_pg, tail_log, constantes)
├── test_smoke_health.py            13 tests (12 health endpoints + ROUTE_MAP)
├── test_smoke_pedagogico.py         3 tests (open episode + abandoned)
├── test_smoke_byok.py               4 tests (CRUD BYOK + 403 path)
├── test_smoke_analytics.py          5 tests (kappa + cii-longitudinal + cuartiles + alerts)
├── test_smoke_audit.py              3 tests (alias ADR-031 + legacy + episode read)
├── test_smoke_chain_e2e.py          1 test (recompute SHA-256 chain bit-exact)
└── test_smoke_governance.py         4 tests (active_configs + prompts + ai-gateway mock)
```

Todos los tests están marcados `@pytest.mark.smoke`.

## Bugs específicos que la suite atrapa

| Bug histórico | Test que lo atrapa |
|---|---|
| BYOK SET LOCAL con bind params (Postgres rechaza) | `test_smoke_byok.test_get_keys_no_500_with_superadmin` |
| Migration faltante `test_cases`/`created_via_ai` | `test_smoke_pedagogico.test_open_episode_returns_uuid` (cascada academic→tutor) |
| Tabla `byok_keys` no creada | `test_smoke_byok.test_get_keys_no_500_with_superadmin` |
| Casbin policies de `byok_key:CRUD` faltantes | `test_smoke_byok.test_get_keys_403_for_non_admin` |
| Alias `/api/v1/audit/*` desconectado del legacy (ADR-031) | `test_smoke_audit.test_audit_verify_alias_matches_legacy` |
| Chain hash con orden invertido en concatenación | `test_smoke_chain_e2e.test_recompute_chain_of_seeded_episode` |
| `chunks_used_hash` cambio de fórmula | (cubierto indirectamente por chain_e2e) |
| Privacy gate cuartiles bajado a <5 | `test_smoke_analytics.test_cii_quartiles_respects_privacy_gate` |
| Manifest yaml roto / governance sin prompt | `test_smoke_governance.test_active_configs_returns_versions` |
| Mock provider del ai-gateway tirado | `test_smoke_governance.test_ai_gateway_complete_with_mock_provider` |

## Cómo agregar un nuevo smoke test

1. Decidir bajo qué archivo va (por flujo: health / pedagogico / byok / analytics / audit / chain / governance).
2. Marcar `@pytest.mark.smoke`.
3. Usar las fixtures: `client`, `auth_headers`, `tenant_id`, `student_id`, `comision_id`, `tarea_practica_id`, `seeded_episode_id`.
4. Mantenerlo rápido (<5s). Si tarda más, comentar por qué.
5. Si el test crea recursos (un episodio nuevo), usar `unique_uuid` o
   `unique_suffix` para no colisionar entre runs.
6. Verificar que el test atrapa un bug: comentarlo en docstring con el ADR
   o el hallazgo del audit que lo motivó.

## Convenciones

- Test fails deben tener mensajes accionables. Para errores complejos, incluir
  las últimas 20 líneas del log del servicio relevante via `tail_log("svc-name")`.
- NO modificar state en la DB. Para reads side-channel: `fetch_pg(dbname, sql, params)`.
- Si un test crea recursos (BYOK key, episodio, etc), no hard-deletear —
  el patrón del piloto es soft-delete para preservar historial. Cleanup a
  través del endpoint correspondiente (ej. `revoke`).
- NO mockear nada. Si necesitás mock, no es un smoke E2E.

## Limitaciones declaradas

- **No verifica persistencia de events del CTR** post-`open_episode`. Los
  partition workers son async single-writer y pueden no estar corriendo en
  el ambiente de smoke. Lo que sí validamos es que los endpoints HTTP
  responden correctamente (201, 204, etc).
- **No verifica firmas Ed25519 attestation**. Eso requiere el
  `integrity-attestation-service` con clave Ed25519 cargada y al menos un
  episodio reciente cerrado en disco — overhead no justificado para smoke.
  La suite Playwright cubre el journey completo.
- **No verifica eventos LLM reales**. El `LLM_PROVIDER=mock` en defaults
  del Makefile devuelve respuestas determinísticas. Si en piloto el LLM
  real falla, los smoke siguen pasando con mock — habría que agregar un
  smoke en CI nightly que use credenciales BYOK reales.

## CI

`.github/workflows/e2e-smoke.yml` corre la suite en cada PR. Es un skeleton
mínimo que asume servicios up (mismo patrón que `make dev-bootstrap`).
