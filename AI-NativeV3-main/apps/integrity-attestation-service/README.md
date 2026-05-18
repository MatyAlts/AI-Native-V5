# integrity-attestation-service

Registro externo auditable del CTR: firma Ed25519 de attestations sobre episodios cerrados (ADR-021, RN-128)

**Puerto**: 8012
**Features**: ed25519-signing, redis-stream-consumer, jsonl-journal

## Proposito

Implementa la propiedad declarada en la Seccion 7.3 de la tesis: el `final_chain_hash` de cada episodio cerrado se firma con clave Ed25519 institucional y se appendea a un journal externo `attestations-YYYY-MM-DD.jsonl`. Esto permite detectar manipulacion del CTR mismo: si alguien con root recalcula la cadena en la DB, queda evidencia en el registro externo que el equipo del piloto no controla.

El worker `attestation_consumer` drena el stream Redis `attestation.requests` (producido por el ctr-service post-commit del cierre), firma cada request, y escribe la linea JSONL del dia.

## Arquitectura

Side-channel **eventually consistent** con SLO 24h:

- El ctr-service hace `XADD attestation.requests` despues del commit del `episodio_cerrado` o `episodio_abandonado`.
- Su ausencia o caida temporal **NO bloquea** el cierre del episodio (RN-128).
- Buffer canonico **bit-exact** sobre `(episode_id, tenant_id, final_chain_hash, total_events, ts_episode_closed, schema_version)`. El campo `ts_episode_closed` debe terminar en sufijo `Z` (no `+00:00`); cualquier desviacion rompe la verificacion externa.
- Verificacion publica via `scripts/verify-attestations.py` con la pubkey servida por `GET /api/v1/attestations/pubkey`.
- El servicio NO esta en `ROUTE_MAP` del api-gateway by-design: el POST es servicio-a-servicio (mTLS o IP allowlist en piloto), los GET son publicos directo.

## Donde corre

- **Piloto UNSL**: VPS institucional separado del cluster del piloto. Director de informatica UNSL custodia la clave Ed25519 privada.
- **Dev local**: NO se levanta. Los eventos se acumulan en `attestation.requests` hasta que el consumer institucional viene online. Verificado 2026-05-07: con 108 episodios cerrados, `XLEN ctr.attestation.requests = 20` (reflejaba cierres pasados por la API real, no seeds).
- **Failsafe**: si la pubkey activa coincide con la dev key Y `environment=production`, el servicio **rechaza arrancar** (proteccion contra deploy accidental con clave de juguete).

## Variables de entorno

Definidas en `src/integrity_attestation_service/config.py`:

| Variable | Default | Notas |
|---|---|---|
| `SERVICE_PORT` | `8012` | Puerto HTTP del servicio. |
| `ENVIRONMENT` | `development` | `production` activa el failsafe contra dev key. |
| `LOG_LEVEL` | `info` | |
| `LOG_FORMAT` | `json` | structlog. |
| `REDIS_URL` | `redis://127.0.0.1:6379/0` | DEBE apuntar a la misma DB que el ctr-service para compartir el stream. |
| `ATTESTATION_PRIVATE_KEY_PATH` | `dev-keys/dev-private.pem` | PEM Ed25519. En piloto, override apuntando al PEM del VPS institucional. |
| `ATTESTATION_PUBLIC_KEY_PATH` | `dev-keys/dev-public.pem` | PEM publico. |
| `ATTESTATION_LOG_DIR` | `./attestations` | Directorio donde se appendean los JSONL diarios. En piloto: filesystem del VPS o mount a MinIO. |
| `OTEL_ENDPOINT` | `http://127.0.0.1:4317` | |
| `SENTRY_DSN` | (vacio) | |

## Endpoints

Definidos en `src/integrity_attestation_service/routes/`:

| Metodo | Path | Proposito |
|---|---|---|
| `GET` | `/` | Status root con metadata (servicio, version, ADR). |
| `GET` | `/health` | Alias de readiness. |
| `GET` | `/health/live` | Liveness (200 si el proceso corre). |
| `GET` | `/health/ready` | Readiness: verifica `attestation_dir_writable` + `private_key_readable`. NO chequea Redis (eventually consistent, D9). |
| `POST` | `/api/v1/attestations` | Recibe `AttestationRequest` del ctr-service, firma y appendea. Servicio-a-servicio (sin JWT). |
| `GET` | `/api/v1/attestations/pubkey` | Pubkey activa en formato PEM. Publico para auditores. Header `X-Signer-Pubkey-Id`. |
| `GET` | `/api/v1/attestations/{day}` | JSONL crudo del dia `YYYY-MM-DD`. Publico, bit-exact. `application/x-ndjson`. |

## Desarrollo local

```bash
# Desde la raiz del monorepo
uv run uvicorn integrity_attestation_service.main:app --reload --port 8012

# Worker consumer del stream (proceso separado)
uv run python -m integrity_attestation_service.workers.attestation_consumer

# Healthcheck
curl http://127.0.0.1:8012/health
```

## Tests

61 tests totales:

- `tests/test_health.py` (5)
- `tests/unit/test_signing.py` (19), `test_journal.py` (13), `test_attestations_endpoint.py` (12), `test_attestation_consumer.py` (10)
- `tests/integration/test_e2e_attestation_flow.py` (2, con testcontainers Redis)

```bash
uv run pytest apps/integrity-attestation-service/
```

## Gotchas piloto

- **Stream se acumula en dev sin consumidor**: `XLEN ctr.attestation.requests` puede crecer si el servicio no se levanta localmente. By-design.
- **Single-consumer requerido**: el journal usa `O_APPEND` sin file lock. El Helm chart fija `replicas: 1`. Escalar horizontal requiere `filelock` o particionar por `episode_id`.
- **At-least-once**: el caller del XADD no garantiza unicidad. Si un mismo `episode_id` se attestiza dos veces, el JSONL queda con dos lineas duplicadas (ambas firmas validan); el verificador externo deduplica.
- **Verificacion post-firma**: `scripts/verify-attestations.py` recompone el buffer canonico y valida cada firma contra la pubkey activa.
- **NO esta en ROUTE_MAP del api-gateway**: el servicio no se accede via gateway. Cualquier intento de exponerlo asi rompe el modelo de aislamiento institucional.

## Referencias

- ADR-021 (`docs/adr/021-external-integrity-attestation.md`): origen y rationale.
- RN-128 (`docs/specs/reglas.md`): regla del buffer canonico bit-exact y formato del `ts`.
- `scripts/smoke-test-attestation.sh`: smoke E2E end-to-end.
- `scripts/verify-attestations.py`: tool de verificacion externa con la pubkey.
