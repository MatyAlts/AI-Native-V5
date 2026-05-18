# integrity-attestation-service

## 1. Qué hace (una frase)

Consume el stream Redis `attestation.requests` que el [ctr-service](./ctr-service.md) emite al cerrar/abandonar episodios, firma cada attestation con clave Ed25519 institucional, y appendea a JSONL append-only `attestations-YYYY-MM-DD.jsonl` — habilita verificación pública e independiente de la cadena criptográfica del CTR sin participación del doctorando.

## 2. Rol en la arquitectura

Pertenece al **plano pedagógico-evaluativo / auditoría transversal**. Materializa el componente "Registro externo Ed25519" descrito en [ADR-021](../adr/021-attestation-ed25519.md) y RN-128, cuyas responsabilidades nominales son: garantizar que la cadena de hashes del CTR puede ser verificada por un auditor externo (comité doctoral, institución externa, lectores académicos del paper publicado) **sin requerir trust en el operador de la plataforma** ni en el doctorando.

En piloto real vive en **VPS UNSL separado del cluster del piloto** (infra institucional de la universidad). En dev local se levanta en el mismo monorepo con dev-keys commiteadas (Ed25519 de juguete). El failsafe arranca el servicio si `pubkey activa == dev-key Y environment == "production"` para evitar deploys accidentales con clave de juguete.

## 3. Responsabilidades

- Consumir el stream Redis `attestation.requests` con `XREADGROUP` (consumer group `attestation_workers`) — los items son emitidos por el [ctr-service](./ctr-service.md) post-commit del cierre de episodios.
- Para cada request: parsear el buffer canónico bit-exact `(episode_id, tenant_id, final_chain_hash, total_events, ts_episode_closed, schema_version)` y firmar con la clave Ed25519 privada activa.
- Appendear el JSONL `{episode_id, tenant_id, final_chain_hash, total_events, ts_episode_closed, ts_attested, signer_pubkey_id, signature, schema_version}` a `attestations-YYYY-MM-DD.jsonl` (un archivo por día UTC, append-only).
- Exponer `POST /api/v1/attestations` para invocación directa service-to-service (en piloto restringido por IP allowlist a nivel red).
- Exponer `GET /api/v1/attestations/pubkey` con la pubkey activa en formato PEM (público por diseño — auditores la usan con `scripts/verify-attestations.py`).
- Exponer `GET /api/v1/attestations/{date}` con el JSONL crudo del día `YYYY-MM-DD` (público por diseño — auditores procesan bit-exact).
- Failsafe en startup: rechazar arrancar si `environment="production"` y la pubkey activa coincide con la dev-key (defensa contra deploy accidental con clave de juguete).
- Operar **eventualmente consistente con SLO 24h**: la ausencia o caída del servicio NO bloquea el cierre de episodios en el ctr-service. Los items se acumulan en el stream Redis hasta que el consumer venga online.

## 4. Qué NO hace (anti-responsabilidades)

- **NO valida ni recomputa la cadena del CTR**: confía en que el `final_chain_hash` que recibe ya pasó por el `IntegrityChecker` o `verify_chain_integrity()` del ctr-service. La función de las attestations es habilitar **verificación posterior por terceros**, no re-verificar el cómputo del hash.
- **NO bloquea el cierre del episodio**: si el XADD del ctr-service falla o el servicio está caído, los episodios cierran igual; las attestations son side-channel.
- **NO emite eventos al CTR**: es read-only respecto al CTR (sólo recibe requests via stream Redis).
- **NO es consumido por frontends ni api-gateway**: es service-to-service via Redis exclusivamente para el POST. Los GETs son públicos para auditores externos pero no atraviesan el api-gateway de la plataforma — quedan expuestos directo en el VPS institucional con su propio nginx + IP allowlist.
- **NO tiene auth**: el POST está restringido por IP allowlist a nivel red (firewall/nginx). Los GETs son públicos por diseño (la auditabilidad pública es la propiedad buscada).
- **NO tiene base de datos**: persistencia es filesystem JSONL append-only.
- **NO conoce el contenido pedagógico**: el buffer canónico es opaco respecto al curriculum/prompt/student. La attestation cubre **integridad criptográfica de la cadena**, no auditabilidad pedagógica (eso es responsabilidad del ctr-service y del classifier).

## 5. Endpoints HTTP

| Método | Path | Qué hace | Auth |
|---|---|---|---|
| `POST` | `/api/v1/attestations` | Recibe `AttestationRequest` `{episode_id, tenant_id, final_chain_hash (64 hex), total_events≥1, ts_episode_closed (ISO-8601 con sufijo Z)}`. Computa buffer canónico, firma con Ed25519 privada, appendea JSONL. Devuelve 201 con `Attestation`. 503 si signing keys no cargadas. | IP allowlist a nivel red (sin JWT). |
| `GET` | `/api/v1/attestations/pubkey` | Devuelve la pubkey activa en formato PEM con header `X-Signer-Pubkey-Id`. **Público por diseño**. | Ninguna. |
| `GET` | `/api/v1/attestations/{date}` | Devuelve el JSONL crudo del día `YYYY-MM-DD` con `Content-Type: application/x-ndjson`. 404 si no existe. **Público por diseño** — sirve los bytes EXACTOS escritos al disco para que auditores procesen bit-exact. | Ninguna. |
| `GET` | `/health`, `/health/ready` | Health real con `check_redis(stream_lag)` + `check_signing_keys` (epic `real-health-checks`). | Ninguna. |

**Buffer canónico bit-exact** (RN-128): cualquier desviación (espacios, sufijo `Z` faltante reemplazado por `+00:00`, separadores) ROMPE la verificación. La función `compute_canonical_buffer` en `services/signing.py` es la fórmula autoritativa. Fórmula del JSON canónico análoga a la del CTR: `sort_keys=True`, `separators=(",", ":")`, `ensure_ascii=False`, default que serializa UUID → str y datetime → ISO-8601 con sufijo `Z`.

**Ejemplo — `POST /api/v1/attestations`**:

```json
{
  "episode_id": "7b3e7c8e-1a4f-4a6c-9b2e-3c0d5e6f7a1b",
  "tenant_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
  "final_chain_hash": "9d1e2f3a...64hex",
  "total_events": 12,
  "ts_episode_closed": "2026-04-24T14:32:11.842Z"
}
```

Response `201`:

```json
{
  "episode_id": "7b3e7c8e-...",
  "tenant_id": "aaaaaaaa-...",
  "final_chain_hash": "9d1e2f3a...",
  "total_events": 12,
  "ts_episode_closed": "2026-04-24T14:32:11.842Z",
  "ts_attested": "2026-04-24T14:32:13.119Z",
  "signer_pubkey_id": "unsl-2026-pri",
  "signature": "base64url-ed25519-signature",
  "schema_version": "v1.0.0"
}
```

## 6. Dependencias

**Depende de (infraestructura):**
- Redis — DB index **0** (compartida con el ctr-service para el stream `attestation.requests`).
- Filesystem — directorio `attestation_log_dir` (default `./attestations/` en dev; en prod, mount a bucket institucional MinIO o filesystem del VPS).
- Clave Ed25519 — `attestation_private_key_path` (default `dev-keys/dev-private.pem` en dev; en prod, override por env apuntando al PEM del VPS institucional generado por el director de informática UNSL).

**Depende de (otros servicios):** ninguno HTTP. Es **hoja**.

**Dependen de él:**
- [ctr-service](./ctr-service.md) — productor único del stream `attestation.requests` post-cierre/abandono de episodio.
- **Auditores externos** (comité doctoral, lectores del paper) — consumen los GET de pubkey + JSONL del día con `scripts/verify-attestations.py` (raíz del repo) para verificar firmas independientemente.

## 7. Modelo de datos

**No tiene DB**. Persistencia en filesystem:

- **Directorio `attestations/`** (configurable):
  ```
  attestations/
  ├── attestations-2026-04-24.jsonl
  ├── attestations-2026-04-25.jsonl
  └── ...
  ```
- Cada línea del JSONL es una `Attestation` serializada con campos canónicos. **Append-only por diseño**: el filesystem JSONL es la fuente de verdad; nunca se reescribe ni se borra una entrada.
- Estado en memoria del proceso:
  - Signing keys cargadas en `app.state.signing` (private_key + public_key + pubkey_id) en el lifespan startup.
  - Consumer offset del stream Redis (gestionado por `XREADGROUP` con consumer group).

**Stream Redis `attestation.requests`** (compartido con ctr-service):
- Productor: ctr-service hace XADD post-commit del cierre.
- Consumer group: `attestation_workers`.
- Verificado 2026-05-07: `XLEN attestation.requests = 20` con 108 episodios cerrados — el path se dispara cuando los cierres pasan por API real (no solo seeds).

## 8. Archivos clave para entender el servicio

- `apps/integrity-attestation-service/src/integrity_attestation_service/routes/attestations.py` — los 3 endpoints HTTP (POST, GET pubkey, GET por día). Path traversal protegido en el GET por día.
- `apps/integrity-attestation-service/src/integrity_attestation_service/workers/attestation_consumer.py` — consumer del stream Redis con `XREADGROUP`. Idempotencia gestionada por el caller (ctr-service usa `event_uuid` como dedup key).
- `apps/integrity-attestation-service/src/integrity_attestation_service/services/signing.py` — `SCHEMA_VERSION`, `compute_canonical_buffer`, `sign_buffer`. La fórmula del buffer canónico bit-exact es la **propiedad crítica** — cualquier cambio rompe verificación.
- `apps/integrity-attestation-service/src/integrity_attestation_service/services/journal.py` — `Attestation` model, `append_attestation`, `now_utc_z`, `raw_jsonl_for_date`.
- `apps/integrity-attestation-service/src/integrity_attestation_service/config.py` — settings + failsafe production vs dev-keys.
- `apps/integrity-attestation-service/dev-keys/` — clave Ed25519 de juguete commiteada al repo (sólo dev). El public key sí se commitea para que tests funcionen sin red; el private SOLO en dev.
- `scripts/verify-attestations.py` (raíz) — herramienta del auditor para verificar firmas bit-exact.
- `scripts/smoke-test-attestation.sh` (raíz) — smoke test end-to-end.
- `docs/pilot/auditabilidad-externa.md` — protocolo de auditoría externa.
- `docs/pilot/attestation-deploy-checklist.md` — checklist operativo de 10 pasos para que el director de informática UNSL deploye el servicio en VPS institucional separado.
- `docs/pilot/attestation-pubkey.pem.PLACEHOLDER` — slot reservado para la pubkey institucional cuando DI UNSL la entregue.

## 9. Configuración y gotchas

**Env vars críticas** (`apps/integrity-attestation-service/src/integrity_attestation_service/config.py`):

- `ENVIRONMENT` — `"development"` (default) o `"production"`. En prod activa el failsafe: si pubkey activa coincide con dev-key, rechaza arrancar.
- `REDIS_URL` — default `redis://127.0.0.1:6379/0` (DB **0** — compartida con ctr-service para el stream).
- `ATTESTATION_PRIVATE_KEY_PATH` — default `dev-keys/dev-private.pem`. En prod, override apuntando al PEM del VPS institucional.
- `ATTESTATION_PUBLIC_KEY_PATH` — default `dev-keys/dev-public.pem`.
- `ATTESTATION_LOG_DIR` — default `./attestations/`. En prod, filesystem del VPS o mount a bucket institucional MinIO.

**Puerto de desarrollo**: `8012`.

**Gotchas específicos**:

- **Buffer canónico bit-exact**: cualquier cambio en la serialización del buffer (orden de campos, separadores, encoding) ROMPE la verificación de auditores externos. La fórmula está congelada en `services/signing.py::compute_canonical_buffer` con `SCHEMA_VERSION = "v1.0.0"`. Cualquier modificación requiere bumpear `SCHEMA_VERSION` y procesar attestations viejas con la fórmula vieja.
- **`ts_episode_closed` con sufijo `Z`**: el formato debe ser ISO-8601 UTC con sufijo `Z` (no `+00:00`). El validador rechaza con 400 si no termina en `Z`. Misma regla que el CTR (`canonicalize()` del ctr-service).
- **Hardware key generation NO requiere doctorando** (D3 del [ADR-021](../adr/021-attestation-ed25519.md)): la generación de la clave Ed25519 institucional es procedimiento del director de informática UNSL en hardware separado. El doctorando NO tiene acceso a la clave privada — sólo recibe la pubkey commiteada al repo como prueba reproducible del período del piloto.
- **Failsafe production + dev-key**: si arranca con `environment=production` y detecta que la pubkey activa coincide con `dev-keys/dev-public.pem`, el servicio falla a startup. Defensa contra deploy accidental.
- **El servicio puede estar caído sin afectar al ctr-service**: los items se acumulan en el stream Redis hasta SLO 24h. Si la backlog crece más allá de eso, alertar — la métrica `attestation_stream_lag` lo mide.
- **`integrity-attestation-service:8012` no está levantado en local en uso normal**: en piloto real vive en VPS UNSL separado. Para tests locales se levanta con `uv run uvicorn integrity_attestation_service.main:app --port 8012 --reload`. Verificado 2026-05-07: el stream `attestation.requests` se está disparando real con `XLEN = 20` cuando los cierres pasan por API.
- **Path traversal protegido**: el GET por día valida formato `YYYY-MM-DD` con regex + checks numéricos antes de buscar el archivo.
- **Auditores usan `scripts/verify-attestations.py`** (raíz del repo): la herramienta toma la pubkey + JSONL + buffer canónico recomputado del CTR original, y verifica firma. Si falla, hay tampering o serialización rota.
- **No hay JWT/Casbin**: por diseño. La auth del POST es por IP allowlist a nivel red; los GETs son públicos para que auditores externos no necesiten credenciales. Cualquier intento de agregar JWT acá rompe la propiedad de auditabilidad pública.

## 10. Relación con la tesis doctoral

El integrity-attestation-service es la implementación operativa del **registro externo auditable** descrito en la Sección 7.3 de la tesis y en [ADR-021](../adr/021-attestation-ed25519.md). La afirmación específica que materializa es:

> "La cadena de hashes del CTR debe ser verificable por un auditor externo sin requerir trust en el operador de la plataforma ni en el doctorando."

La defensa doctoral exige que el comité pueda **independientemente** confirmar que los datos del piloto son íntegros — que ningún evento fue alterado a posteriori para mejorar resultados. Tres propiedades que sostiene:

1. **Auditabilidad criptográfica externa**: con la pubkey + el JSONL del período + el buffer canónico recomputado del CTR, cualquier auditor puede verificar bit-exact que `Ed25519.verify(pubkey, signature, canonical_buffer) == True` para cada attestation.

2. **Hardware key institucional**: la clave privada Ed25519 NO es generada por el doctorando — la genera el director de informática UNSL en hardware separado del cluster del piloto (D3 del ADR). El doctorando recibe la pubkey commiteada al repo como snapshot reproducible del período. Esto cierra la objeción "el doctorando podría haber firmado attestations falsas".

3. **Independencia operativa**: el servicio vive en VPS institucional separado del cluster del piloto (infra UNSL). Si el cluster del piloto fuera comprometido, las attestations Ed25519 ya emitidas siguen siendo verificables — quedan en el filesystem del VPS institucional, fuera del alcance del operador del piloto.

**Por qué eventualmente consistente con SLO 24h**: el ctr-service NO debe bloquear cierres de episodios por la disponibilidad del attestation service. Si una caída de red corta la conectividad VPS↔plataforma por 4h, los items se acumulan en el stream Redis y se procesan al volver online. La SLO de 24h es tolerable porque la verificación sólo importa para episodios cerrados; episodios en progreso no requieren attestation.

**Por qué buffer canónico bit-exact**: cualquier auditor debe poder reproducir exactamente el buffer que se firmó. Si la serialización tiene ambigüedad (orden de campos, espacios, encoding), un auditor puede recibir el mismo input lógico pero generar bytes distintos al firmar/verificar — y la verificación falla. La regla de canonización es idéntica al `canonicalize()` del ctr-service por una razón: las dos cadenas de evidencia (cadena CTR interna + attestation Ed25519 externa) deben ser **complementarias**, no contradictorias.

**Discrepancia declarada**: la generación de clave hardware en VPS institucional es **procedimiento operativo del DI UNSL**, no automatizado. El checklist `docs/pilot/attestation-deploy-checklist.md` documenta los 10 pasos. Si la coordinación con DI UNSL falla, el piloto queda con dev-keys en local (auditable internamente pero NO públicamente — el comité doctoral debe confiar en que no hubo deploy con dev-keys en producción).

## 11. Estado de madurez

**Tests**: smoke test E2E en `scripts/smoke-test-attestation.sh`. Tests unit del buffer canónico y signing en `apps/integrity-attestation-service/tests/`.

**Known gaps**:
- En piloto-1 vive en VPS institucional UNSL separado — el deploy depende de coordinación con DI UNSL (Paso 2 del checklist `attestation-deploy-checklist.md`). Si la coordinación falla, queda en dev-keys.
- Stream lag metric no monitoreada por default — alertar si supera SLO 24h es operacional.
- Sin GUI para visualizar attestations por día — el JSONL crudo es la única interfaz para auditores.
- Recovery de attestations corruptas (filesystem corrupt o JSONL truncado) requiere backup external.
- Rotación de claves Ed25519 no implementada — un solo `signer_pubkey_id` activo por instancia. Para rotación en producción se requiere período de gracia + dual-signing temporal.

**Fase de consolidación**:
- 2026-04-26 ([ADR-021](../adr/021-attestation-ed25519.md)) — implementación inicial con dev-keys + workers + endpoints públicos.
- 2026-04-27 — checklist de deploy institucional documentado en `docs/pilot/attestation-deploy-checklist.md`.
- 2026-05-04 (epic `real-health-checks`) — `/health/ready` real con `check_redis + check_signing_keys`.
- 2026-05-07 (QA pass post-stash recovery) — verificación de que el path documentado SÍ se está disparando en piloto local cuando los cierres pasan por API real (no solo seeds). Bit-exact buffer canónico verificado.

**Operación esperada en piloto real**:

1. DI UNSL despliega el servicio en VPS institucional separado siguiendo `docs/pilot/attestation-deploy-checklist.md`.
2. La pubkey institucional reemplaza al placeholder `docs/pilot/attestation-pubkey.pem.PLACEHOLDER` y se commitea al repo como snapshot reproducible.
3. ctr-service en cluster del piloto apunta su `REDIS_URL` para que el stream `attestation.requests` sea visible al consumer institucional (bridge Redis si los clusters están separados).
4. Auditores externos (comité doctoral) reciben URL canónica del servicio + commit del repo como mirror — ambos deben coincidir bit-a-bit en pubkey y JSONL.
5. Cualquier discrepancia entre URL institucional y mirror del repo es señal de tampering — el procedimiento de verificación falla.
