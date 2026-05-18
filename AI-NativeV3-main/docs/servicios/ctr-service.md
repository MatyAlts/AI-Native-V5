# ctr-service

## 1. Qué hace (una frase)

Persiste los eventos del Cuaderno de Trabajo Reflexivo (CTR) como una cadena criptográfica SHA-256 append-only, con workers particionados que consumen del bus Redis Streams y garantizan orden estricto por episodio.

## 2. Rol en la arquitectura

Pertenece al **plano pedagógico-evaluativo**. Materializa el componente "Servicio del Cuaderno de Trabajo Reflexivo" descrito en el Capítulo 6 de la tesis (arquitectura C4 del sistema AI-Native), cuyas responsabilidades nominales son: persistir la trazabilidad cognitiva de cada episodio, garantizar auditabilidad criptográfica de la cadena de eventos, y servir como fuente de verdad inmutable para análisis posterior (clasificación N4, analytics longitudinal, export académico).

Es el núcleo conceptual de la tesis: sin las garantías que provee (append-only, integridad verificable, reproducibilidad bit-a-bit), la aceptabilidad académica del estudio piloto — y con ella la validez de las mediciones — no se sostiene.

## 3. Responsabilidades

- Exponer `POST /api/v1/events` para recibir eventos desde servicios productores (exclusivamente `tutor-service`, con la salvedad de `codigo_ejecutado`/`edicion_codigo`/`anotacion_creada`/`tests_ejecutados`/`reflexion_completada` cuyo `user_id` proviene del estudiante real).
- Publicar cada evento al stream Redis `ctr.p{N}` correspondiente a su partición, calculada como `SHA-256(episode_id)[:4] mod NUM_PARTITIONS`. **El sharding vive a nivel Redis Streams** (`ctr.p0..ctr.p7`), NO a nivel Postgres — la tabla `events` en `ctr_store` es **única y no particionada físicamente** (verificado 2026-05-04: `pg_inherits` devuelve 0 rows). Single-writer por partición aplica al **bus**: cada worker consumer-group consume una partición.
- Ejecutar un `PartitionWorker` por cada partición (`NUM_PARTITIONS = 8`) que consume del stream, computa `self_hash` y `chain_hash`, valida `seq` consecutivos y persiste el evento en `ctr_store`.
- Garantizar idempotencia por `(tenant_id, event_uuid)` — si un evento llega dos veces al worker (retry del productor, redelivery de Redis), se ignora el duplicado sin romper la cadena.
- Manejar dead-letters: tras 3 intentos fallidos un mensaje se archiva en `dead_letters`, se publica al stream `ctr.dead` y el episodio afectado se marca `integrity_compromised=true`.
- Ejecutar `IntegrityChecker` como CronJob batch que recorre episodios cerrados, recomputa sus cadenas completas y reporta corrupciones nuevas (distinguiendo "ya marcado" de "recién detectado").
- **Disparar attestation Ed25519 externa post-cierre** ([ADR-021](../adr/021-attestation-ed25519.md), RN-128): al persistir un `episodio_cerrado` o `episodio_abandonado`, hace XADD a stream Redis `attestation.requests` con buffer canónico bit-exact. El [integrity-attestation-service](./integrity-attestation-service.md) (puerto 8012) consume el stream con `XREADGROUP`, firma con clave Ed25519 y appendea a `attestations-YYYY-MM-DD.jsonl`. **Eventualmente consistente** (SLO 24h); su ausencia **NO bloquea** el cierre del episodio. Verificado 2026-05-07: stream con 20 entries, 108 episodios cerrados.
- Exponer `GET /api/v1/episodes/{id}` con el episodio completo y sus eventos ordenados por `seq`, y `POST /api/v1/episodes/{id}/verify` para recomputar y validar la cadena on-demand (auditorías manuales). Adicionalmente expone **aliases `/api/v1/audit/episodes/{id}` y `/api/v1/audit/episodes/{id}/verify`** ([ADR-031](../adr/031-audit-aliases-ctr.md)) que apuntan al MISMO handler que el legacy — cero duplicación de lógica. Test anti-regresión `test_audit_aliases.py::test_audit_verify_episode_apunta_al_mismo_handler_que_legacy`. **NO mover los handlers** sin actualizar el `audit_router`.
- Servir como fuente de verdad para lectores del plano académico (`analytics-service` abre sesiones read-only a `ctr_store` con `SET LOCAL app.current_tenant`).

## 4. Qué NO hace (anti-responsabilidades)

- **NO valida autorización en el sentido amplio**: confía en que [api-gateway](./api-gateway.md) ya haya validado el JWT e inyectado los headers `X-Tenant-Id`/`X-User-Id`/`X-User-Roles` (plural). Localmente sólo chequea que `tenant_id` del payload coincida con el del user (salvo `superadmin`) y que el rol esté en `PUBLISH_ROLES`/`READ_ROLES`.
- **NO computa métricas agregadas, κ ni progresión longitudinal**: eso es [analytics-service](./analytics-service.md). Este servicio es sólo persistencia + verificación de integridad.
- **NO clasifica episodios en N4**: emite eventos; la clasificación la hace [classifier-service](./classifier-service.md) leyendo del mismo `ctr_store`.
- **NO aloja el prompt del tutor**: `prompt_system_hash` llega embebido en cada evento desde el productor (que lo obtuvo de [governance-service](./governance-service.md)). El ctr-service nunca contacta governance.
- **NO conoce el contenido del RAG**: `chunks_used_hash` llega pre-computado en el payload del evento `prompt_enviado`. No abre sesiones contra `content_db`.
- **NO implementa un bus de eventos propio**: usa Redis Streams con `XREADGROUP` + consumer group `ctr_workers`. La partición del stream es tanto unidad de paralelismo como invariante de orden.

## 5. Endpoints HTTP

| Método | Path | Qué hace | Auth |
|---|---|---|---|
| `POST` | `/api/v1/events` | Publica un evento al stream Redis de la partición correspondiente (202 Accepted — persistencia asíncrona). | Header `X-User-Id` + rol en `PUBLISH_ROLES`. |
| `GET` | `/api/v1/episodes/{episode_id}` | Devuelve el episodio con todos sus eventos ordenados por `seq`. | Rol en `READ_ROLES`. |
| `POST` | `/api/v1/episodes/{episode_id}/verify` | Recomputa la cadena completa y devuelve `ChainVerificationResult` con `valid`, `failing_seq`, `integrity_compromised`. | Rol en `READ_ROLES`. |
| `GET` | `/api/v1/audit/episodes/{episode_id}` | **Alias** del GET legacy ([ADR-031](../adr/031-audit-aliases-ctr.md), gap D.4). MISMO handler — cero duplicación. Consumido por web-admin `AuditoriaPage`. | Rol en `READ_ROLES`. |
| `POST` | `/api/v1/audit/episodes/{episode_id}/verify` | **Alias** del verify legacy. MISMO handler. Consumido por web-admin `AuditoriaPage` para verificación SHA-256 en vivo (útil para defensa doctoral). | Rol en `READ_ROLES`. |
| `GET` | `/health`, `/health/ready` | Readiness con checks reales contra DB y Redis (responde 503 si alguno falla — patrón propio establecido pre-epic `real-health-checks`, mantenido estable). | Ninguna. |
| `GET` | `/health/live` | Liveness trivial. | Ninguna. |

**Ejemplo de payload para `POST /api/v1/events`** (evento `prompt_enviado` — schema en `apps/ctr-service/src/ctr_service/schemas/__init__.py::EventPublishRequest`):

```json
{
  "event_uuid": "c41c9c00-2f7a-4dcb-9d7a-3e9f8a1b0c00",
  "episode_id": "7b3e7c8e-1a4f-4a6c-9b2e-3c0d5e6f7a1b",
  "tenant_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
  "seq": 3,
  "event_type": "prompt_enviado",
  "ts": "2026-04-24T14:32:11.842Z",
  "payload": {
    "content": "¿Por qué mi solución tiene complejidad O(n²)?",
    "prompt_kind": "solicitud_directa",
    "chunks_used_hash": "f3a1b2c3...64hex"
  },
  "prompt_system_hash": "a1b2c3d4...64hex",
  "prompt_system_version": "v1.0.0",
  "classifier_config_hash": "e5f6a7b8...64hex"
}
```

El response `202 Accepted` devuelve el `message_id` de Redis y la partición destino, **antes** de que el worker haya persistido:

```json
{ "message_id": "1714060331842-0", "partition": 5 }
```

**Response de `GET /api/v1/episodes/{id}`** (`EpisodeWithEvents`):

```json
{
  "id": "7b3e7c8e-...",
  "tenant_id": "aaaaaaaa-...",
  "comision_id": "...",
  "student_pseudonym": "b1b1b1b1-0001-...",
  "problema_id": "...",
  "estado": "open",
  "opened_at": "2026-04-24T14:30:00Z",
  "closed_at": null,
  "events_count": 12,
  "last_chain_hash": "9d1e2f3a...64hex",
  "integrity_compromised": false,
  "prompt_system_hash": "a1b2c3d4...",
  "classifier_config_hash": "e5f6a7b8...",
  "curso_config_hash": "c0c0c0c0...",
  "events": [
    { "event_uuid": "...", "seq": 0, "event_type": "episodio_abierto", "ts": "...", "payload": {...}, "self_hash": "...", "chain_hash": "...", "prev_chain_hash": "0000...00" },
    { "event_uuid": "...", "seq": 1, "event_type": "prompt_enviado",   "ts": "...", "payload": {...}, "self_hash": "...", "chain_hash": "...", "prev_chain_hash": "..." }
  ]
}
```

**Response de `POST /api/v1/episodes/{id}/verify`** (`ChainVerificationResult`):

```json
{
  "episode_id": "7b3e7c8e-...",
  "valid": true,
  "events_count": 12,
  "failing_seq": null,
  "integrity_compromised": false,
  "message": "Cadena íntegra"
}
```

Si la cadena está rota (tampering o corrupción detectada), `valid=false` + `failing_seq=<int>` apunta al primer evento que no verifica, y `message` queda como `"Cadena rota en seq={N}: recomputado no coincide con persistido"`.

## 6. Dependencias

**Depende de (infraestructura):**
- PostgreSQL 16 — base lógica `ctr_store`, usuario dedicado `ctr_user` (ADR-003 exige aislamiento del plano académico).
- Redis 7 — bus de streams (ADR-005), un stream por partición + consumer group compartido.

**Depende de (otros servicios):** ninguno HTTP. El servicio es **hoja**: recibe eventos y los persiste, no consulta a nadie. Los hashes de configuración (`prompt_system_hash`, `classifier_config_hash`, `curso_config_hash`) llegan embebidos en el payload del productor. **Side-channel**: emite XADD a Redis Stream `attestation.requests` post-cierre — el consumer es [integrity-attestation-service](./integrity-attestation-service.md), pero su ausencia no bloquea cierres.

**Dependen de él:**
- [tutor-service](./tutor-service.md) — productor principal, publica casi todos los tipos de eventos (`episodio_abierto`, `prompt_enviado`, `tutor_respondio`, `episodio_cerrado`, `episodio_abandonado`, `tests_ejecutados`, `reflexion_completada`, etc.).
- [classifier-service](./classifier-service.md) — lee el `ctr_store` (conexión read-only separada) para extraer los eventos de un episodio y correr el pipeline N4.
- [analytics-service](./analytics-service.md) — lee read-only `ctr_store` para κ, progresión longitudinal y export académico (HU-088).
- [integrity-attestation-service](./integrity-attestation-service.md) — consume el stream `attestation.requests` con `XREADGROUP`.
- [web-admin](./web-admin.md) — `AuditoriaPage.tsx` consume `/api/v1/audit/episodes/{id}/verify` via api-gateway ROUTE_MAP.
- [`packages/ctr-client`](../../packages/ctr-client/) — cliente TS tipado para consumir el ctr-service desde los frontends (hoy sin consumidores directos; reservado).

## 7. Modelo de datos

Base lógica: **`ctr_store`** (ADR-003), usuario `ctr_user`. Migraciones Alembic en `apps/ctr-service/alembic/versions/`.

**Tablas principales** (`apps/ctr-service/src/ctr_service/models/event.py`):

- **`episodes`** — un registro por episodio de trabajo (estudiante + problema + comisión).
  - Clave primaria: `id` (UUID v4).
  - Columnas críticas: `tenant_id`, `comision_id`, `student_pseudonym`, `problema_id`, `prompt_system_hash`, `prompt_system_version`, `classifier_config_hash`, `curso_config_hash`, `estado` (`open` | `closed` | `expired` | `integrity_compromised`), `events_count`, `last_chain_hash`, `integrity_compromised` (flag).
  - Los cuatro hashes de configuración quedan congelados al abrir el episodio — permiten reproducir bit-a-bit la clasificación posterior.

- **`events`** — append-only, uno por interacción del tutor-estudiante.
  - Claves: `id` (BigInteger autoincrement), `event_uuid` (UUID del emisor para idempotencia).
  - Constraints: `UniqueConstraint(tenant_id, event_uuid)` idempotencia; `UniqueConstraint(tenant_id, episode_id, seq)` orden estricto.
  - Relación: `ForeignKey(episodes.id, ondelete="RESTRICT")` — no se puede borrar un episodio con eventos.
  - Hashes: `self_hash`, `chain_hash`, `prev_chain_hash` (64 chars hex).
  - Hashes de configuración replicados en cada evento (redundancia defensiva: si cambia el episodio, el evento sigue verificable contra la config que estaba vigente).
  - `event_type` en snake_case en runtime (12 tipos efectivamente emitidos al cierre del epic ai-native-completion): `episodio_abierto`, `prompt_enviado`, `codigo_ejecutado`, `tutor_respondio`, `anotacion_creada`, `edicion_codigo`, `episodio_cerrado`, `episodio_abandonado` ([ADR-025](../adr/025-episodio-abandonado.md)), `lectura_enunciado` (instrumentado desde el frontend), `intento_adverso_detectado` ([ADR-019](../adr/019-guardrails-fase-a.md), side-channel del tutor-service para análisis empírico Sección 17.8), `tests_ejecutados` ([ADR-034](../adr/034-test-cases-tp.md), conteos de tests unitarios), `reflexion_completada` ([ADR-035](../adr/035-reflexion-metacognitiva.md), 3 textareas post-cierre, **excluido del classifier** RN-133). El catálogo completo de payloads tipados vive en `packages/contracts/src/platform_contracts/ctr/events.py`.

- **`dead_letters`** — eventos que fallaron 3 veces y fueron archivados.
  - Guarda `raw_payload` JSONB, `error_reason` text, `failed_attempts`, `first_seen_at`, `moved_to_dlq_at`.
  - La inserción aquí dispara un `UPDATE episodes SET integrity_compromised=true, estado='integrity_compromised'` en la misma transacción (`workers/partition_worker.py::_move_to_dlq`).

**Append-only, de verdad**: nunca `UPDATE` ni `DELETE` de eventos (RN-035). Reclasificar no existe en esta DB — vive en [classifier-service](./classifier-service.md) con su propio flag `is_current`. La única excepción autorizada a "modificar" estado es el flag `integrity_compromised` del episodio (no del evento), documentada en `reglas.md` RN-039/RN-040.

**RLS**: todas las tablas tienen `tenant_id` con policy activa (migración `20260721_0002_enable_rls_on_ctr_tables.py`). Cada sesión abre con `SET LOCAL app.current_tenant = ...` vía `tenant_session(tenant_id)` en `db/session.py`. `make check-rls` verifica que no se escape ninguna.

## 8. Archivos clave para entender el servicio

- `apps/ctr-service/src/ctr_service/services/hashing.py` — `canonicalize()`, `compute_self_hash()`, `compute_chain_hash()`, `verify_chain_integrity()`. Es la matemática que sostiene la auditabilidad. `sort_keys=True, separators=(",", ":")`, `ensure_ascii=False` — cualquier cambio rompe reproducibilidad bit-a-bit. **Bug fix cross-package (sesión 2026-05-04)**: `compute_chain_hash` en `packages/contracts/src/platform_contracts/ctr/hashing.py:46` calculaba `sha256(prev || self_hash)` mientras este servicio (y la DB) usan `sha256(self_hash || prev)`. Invertido el orden en contracts package + nuevo test cross-package `packages/contracts/tests/test_chain_hash_canonical_formula.py` con fixtures bit-exact de un episodio real. Sin este fix, un auditor doctoral que use el helper "oficial" para verificar la cadena obtenía falsos failures sobre cadenas íntegras.
- `apps/ctr-service/src/ctr_service/services/producer.py` — `shard_of()` (sharding estable por `SHA-256(episode_id)`) + `EventProducer.publish()` (XADD al stream de la partición).
- `apps/ctr-service/src/ctr_service/workers/partition_worker.py` — consumer single-writer por partición. Aloja la lógica de persistencia transaccional (lock sobre `Episode`, validación de `seq` esperado, cómputo de hashes, `INSERT ... ON CONFLICT DO NOTHING` para idempotencia, retry → DLQ).
- `apps/ctr-service/src/ctr_service/workers/integrity_checker.py` — CronJob batch que recorre episodios cerrados y recomputa cadenas completas.
- `apps/ctr-service/src/ctr_service/models/event.py` — definiciones de `Episode`, `Event`, `DeadLetter` (ORM + constraints).
- `apps/ctr-service/src/ctr_service/models/base.py` — `GENESIS_HASH = "0" * 64`, `TenantMixin`, `NAMING_CONVENTION` para constraints.
- `apps/ctr-service/src/ctr_service/routes/events.py` — endpoints HTTP: publish, get episode, verify chain.
- `apps/ctr-service/src/ctr_service/routes/health.py` — único health real del repo (probes contra DB + Redis con timeout 2s, 503 si alguno falla).
- `apps/ctr-service/alembic/versions/20260721_0002_enable_rls_on_ctr_tables.py` — policies RLS de las tres tablas.

**Canonicalización — el corazón del hashing determinista:**

```python
# apps/ctr-service/src/ctr_service/services/hashing.py:21
def canonicalize(obj: Any) -> bytes:
    return json.dumps(
        obj,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        default=_json_default,   # UUID → str, datetime → ISO-8601 con "Z"
    ).encode("utf-8")


# apps/ctr-service/src/ctr_service/services/hashing.py:41
def compute_self_hash(event: dict[str, Any]) -> str:
    clean = {
        k: v for k, v in event.items()
        if k not in {"self_hash", "chain_hash", "prev_chain_hash",
                     "persisted_at", "id"}
    }
    return hashlib.sha256(canonicalize(clean)).hexdigest()


# apps/ctr-service/src/ctr_service/services/hashing.py:53
def compute_chain_hash(self_hash: str, prev_chain_hash: str | None) -> str:
    prev = prev_chain_hash if prev_chain_hash is not None else GENESIS_HASH
    combined = f"{self_hash}{prev}".encode("utf-8")   # self PRIMERO, prev DESPUÉS
    return hashlib.sha256(combined).hexdigest()
```

**Sharding — reparte episodios entre 8 workers sin coordinación**:

```python
# apps/ctr-service/src/ctr_service/services/producer.py:22
def shard_of(episode_id: UUID, num_partitions: int = NUM_PARTITIONS) -> int:
    h = hashlib.sha256(str(episode_id).encode("utf-8")).digest()
    return int.from_bytes(h[:4], "big") % num_partitions
```

La función es pura y estable: el mismo `episode_id` siempre cae en la misma partición, sin depender del `PYTHONHASHSEED` del proceso. Todos los eventos de un episodio van al mismo worker → orden estricto por `seq` garantizado sin locks distribuidos.

**Flujo transaccional del `_persist_event` (versión resumida)**:

```
BEGIN;
  -- 1. Lock del episodio (SELECT ... FOR UPDATE)
  ep = session.get(Episode, episode_id, with_for_update=True)

  -- 2. Validar seq esperado
  if seq != ep.events_count: raise ValueError

  -- 3. Computar hashes
  self = sha256(canonicalize(event_sin_campos_computados))
  prev = ep.last_chain_hash if seq > 0 else GENESIS_HASH
  chain = sha256(f"{self}{prev}")

  -- 4. INSERT ... ON CONFLICT DO NOTHING
  --    (idempotencia por (tenant_id, event_uuid))
  if rowcount == 0: return   # duplicado → skip silencioso

  -- 5. UPDATE del episodio
  ep.events_count += 1
  ep.last_chain_hash = chain
  if event_type == "episodio_cerrado":
      ep.estado = "closed"
      ep.closed_at = utc_now()
COMMIT;
```

## 9. Configuración y gotchas

**Env vars críticas** (`apps/ctr-service/src/ctr_service/config.py`):

- `CTR_DB_URL` — default `postgresql+asyncpg://ctr_user:ctr_pass@127.0.0.1:5432/ctr_store`. El prefijo `postgresql+asyncpg://` es obligatorio — el servicio usa SQLAlchemy 2.0 async.
- `REDIS_URL` — default `redis://127.0.0.1:6379/0`. Mismo Redis del bus compartido.
- `NUM_PARTITIONS` — default `8`. **Cambiar este valor en caliente rompe la invariante de sharding**: eventos nuevos irían a particiones distintas que los viejos del mismo episodio, y los workers perderían la garantía single-writer. Si se necesita cambiar, coordinar con un re-shard completo.
- `KEYCLOAK_URL`, `KEYCLOAK_REALM` — para que el middleware de auth (heredado via `auth/`) pueda resolver roles del JWT cuando llega. En dev con `dev_trust_headers=true` no se usa.

**Puerto de desarrollo**: `8007`.

**Defaults de dev**: ninguno mock-específico. El servicio funciona con cualquier Postgres + Redis compatibles. Para correrlo sin api-gateway en dev, los frontends lo deberían golpear por el gateway (`:8000`) que le inyecta los headers `X-*`.

**Gotchas específicos**:

- **Sharding inmutable**: `NUM_PARTITIONS = 8` está en tres lugares — `producer.py`, `config.py`, y la replicas del `StatefulSet` de K8s. Cambiar uno sin los otros genera eventos huérfanos. Documentado en CLAUDE.md "Constantes que NO deben inventarse". **Aclaración importante** (verificado 2026-05-04): el sharding vive a nivel **Redis Streams** (`ctr.p0..ctr.p7`), no a nivel Postgres — la tabla `events` es **única y no particionada físicamente**. Single-writer aplica al bus. Cualquier futuro escalamiento que necesite native partitioning de Postgres requiere ADR + migration de `events` a tabla particionada por hash de `episode_id`.
- **Orden del `chain_hash`**: `sha256(f"{self_hash}{prev_chain_hash}")` — **self primero, prev después**. Es contraintuitivo y cualquier invertido invalida toda la cadena. Ver `services/hashing.py:54-60`.
- **Self-hash exclusiones**: `compute_self_hash()` excluye `{self_hash, chain_hash, prev_chain_hash, persisted_at, id}` del payload antes de hashear. Cambiar ese set es BC-breaking: los episodios viejos dejan de verificar.
- **Single-writer por partición**: los 8 workers corren como `StatefulSet` en K8s, cada pod toma la partición que coincide con su ordinal (`ctr-worker-0` → p0, etc.). Si dos pods tomaran la misma partición por un bug de operación, se perderían eventos y/o se duplicarían. El deploy usa estrategia `rolling` (no blue-green) por esto — ver [ADR-015](../adr/015-blue-green-rolling-deploy.md).
- **DLQ implica integrity_compromised**: un sólo evento que falle 3 veces deja todo el episodio marcado como comprometido. Esto está diseñado así — un "hueco" en la cadena invalida criptográficamente todo lo posterior. Para recuperar un episodio comprometido por operación (no por tampering real), el runbook `docs/pilot/runbook.md` incidente I01 tiene el procedimiento.
- **Timestamp con sufijo `Z` obligatorio**: el `_json_default` serializa `datetime` como `iso.replace("+00:00", "Z")`. Un productor que mande `"+00:00"` literal produce un hash distinto — los productores Python usen `datetime.now(UTC).isoformat().replace("+00:00", "Z")`. El schema Pydantic coerce al formato correcto al publicar, pero si se bypasa el schema (push directo al stream), el hash no matchea y el evento termina en DLQ.
- **`persisted_at` NO está en el hash**: es metadata del worker (wall-clock del commit), no del emisor. Su exclusión es intencional — si fuera parte del hash, re-correr el worker sobre el mismo evento produciría hashes distintos.
- **Aliases `/api/v1/audit/*` apuntan al MISMO handler que el legacy** ([ADR-031](../adr/031-audit-aliases-ctr.md)): el `audit_router` registra `get_episode` y `verify_episode_chain` via `add_api_route` apuntando a las funciones legacy. **NO mover los handlers** sin actualizar el audit_router; el test `test_audit_aliases.py::test_audit_verify_episode_apunta_al_mismo_handler_que_legacy` falla si el alias deja de apuntar al mismo objeto.
- **Attestation Ed25519 dispara post-commit** ([ADR-021](../adr/021-attestation-ed25519.md)): el XADD a `attestation.requests` ocurre **después** del commit del cierre. Si el XADD falla (Redis down), se logguea pero no se rollbackea el cierre — la cadena CTR intacta es prioridad sobre la attestation externa. Buffer canónico bit-exact: cualquier desviación (espacios, sufijo `Z` faltante, separadores) ROMPE la verificación. Eventualmente consistente, SLO 24h.

**Traceback canónico del incidente I01** (corrupción detectada por `IntegrityChecker`) — extracto del `runbook.md`:

```
INFO ctr_service.workers.integrity_checker: Episodio 7b3e7c8e-...
  Íntegro: False | Fallo en seq=7
  self_hash persistido  = 9d1e2f3a...
  self_hash recomputado = 3e8c4f1b...
  → posibles causas (en orden de probabilidad):
    1. Tampering del payload (e.g. UPDATE manual vía psql)
    2. Inconsistencia de serialización (cambio en canonicalize/_json_default)
    3. Corrupción de storage (rarísimo en Postgres WAL-protegido)

Acción tomada: Episode.integrity_compromised := true, estado := "integrity_compromised"
Emitir métrica: ctr_episodes_integrity_compromised_total +=1
Notificar al equipo de seguridad (Slack #security-alerts).
```

La métrica `ctr_episodes_integrity_compromised_total` es el **gate del canary de tutor-service** ([ADR-015](../adr/015-blue-green-rolling-deploy.md)): si incrementa durante el rollout, Argo Rollouts hace rollback automático.

## 10. Relación con la tesis doctoral

El ctr-service es la implementación del **mecanismo de trazabilidad cognitiva N4** descrito en la tesis. Materializa dos afirmaciones centrales:

1. **Auditabilidad criptográfica de la interacción estudiante-tutor**: la Sección 7.3 de la tesis (cadena de hashes del CTR) exige que cualquier manipulación posterior de un evento — por error operativo, por tampering malintencionado, por bug de persistencia — sea **detectable** mediante recomputación determinista de `self_hash` y `chain_hash` desde `GENESIS_HASH`. Esto se verifica con `verify_chain_integrity()` y el `IntegrityChecker`.

2. **Reproducibilidad bit-a-bit del estado de configuración**: cada evento viaja con `prompt_system_hash`, `prompt_system_version`, `classifier_config_hash`, y el episodio además guarda `curso_config_hash`. Esto permite, meses después, recargar exactamente el prompt y la config de árbol que estaban vigentes cuando el estudiante interactuó — condición para que la re-clasificación con nuevos profiles sea metodológicamente válida (HU-118, A/B testing de profiles).

La serialización canónica (`canonicalize()`) es la matemática que sostiene las dos propiedades: la misma estructura lógica produce siempre los mismos bytes, y por tanto el mismo hash. La tesis lo trata como supuesto; este servicio es quien garantiza que el supuesto se cumple en la plataforma real.

**Por qué RESTRICT y no CASCADE en el FK `events.episode_id`**: un `ondelete=CASCADE` permitiría que un `DELETE FROM episodes WHERE id=...` borrara todos los eventos asociados. La tesis exige que **los eventos sean indelebles en operación normal** — el único camino legítimo para "anonimizar" un estudiante es `anonymize_student()` en `packages/platform-ops/privacy.py` que **rota el pseudónimo** pero deja los eventos intactos con el nuevo alias (incidente I06 del runbook). `RESTRICT` fuerza esa ruta.

**Histórico — discrepancia PascalCase / snake_case (resuelta en F1-F4, commit `b927dcc`)**: los contracts Pydantic originales declaraban `event_type: Literal["PromptEnviado"]` mientras el tutor-service emitía `"prompt_enviado"`. F1-F4 alineó los contracts al runtime (snake_case) y renombró las clases conflictivas (`RespuestaRecibida` → `TutorRespondio`, `NotaPersonal` → `AnotacionCreada`, `TestsEjecutados` → `CodigoEjecutado`). La regresión está bloqueada por `packages/contracts/tests/test_event_types_match_runtime.py`, que assertea que el conjunto de Literals del contract == strings emitidos por `tutor_core.py`.

**Secuencia canónica de un episodio completo** (ver también la secuencia pedagógica en [tutor-service](./tutor-service.md) Sección 10):

```
seq  event_type           emisor              payload (extracto)
─────────────────────────────────────────────────────────────────────────
 0   episodio_abierto     tutor-service       { student_pseudonym, problema_id, comision_id, curso_config_hash }
 1   prompt_enviado       tutor-service       { content, prompt_kind, chunks_used_hash }
 2   tutor_respondio      tutor-service       { content, chunks_used_hash, model }
 3   edicion_codigo       estudiante real     { snapshot, diff_chars, language }
 4   edicion_codigo       estudiante real     { snapshot, diff_chars, language }
 5   codigo_ejecutado     estudiante real     { code, stdout, stderr, duration_ms, runtime }
 6   anotacion_creada     estudiante real     { content, words }
 7   prompt_enviado       tutor-service       { content, prompt_kind, chunks_used_hash }
 8   tutor_respondio      tutor-service       { content, chunks_used_hash, model }
 ...
 N   episodio_cerrado     tutor-service       { reason, total_events }
```

**Invariante RN-096** (flujo estricto del turno del tutor): entre un `prompt_enviado` con `seq=N` y su `tutor_respondio` con `seq=N+1` no se aceptan otros eventos del tutor-service. La atomicidad la garantiza `SessionManager.next_seq()` con `INCR` de Redis en [tutor-service](./tutor-service.md).

## 11. Estado de madurez

**Tests** (5 archivos):
- `tests/unit/test_hashing_and_sharding.py` — canonicalización, genesis hash, reproducibilidad, sharding estable.
- `tests/unit/test_integrity_checker.py` — detección de tampering, reporte de compromisos nuevos vs. ya marcados.
- `tests/integration/test_ctr_end_to_end.py` — publica eventos al stream real (testcontainer Redis), corre un worker, verifica persistencia y cadena contra Postgres real.
- `tests/integration/conftest.py` — fixtures del testcontainer.
- `tests/test_health.py` — smoke test del endpoint `/health`.

Cubre: hashing determinista (RN-004, RN-007, RN-008), sharding estable (HU-036), idempotencia por `event_uuid` (HU-037), DLQ → integrity_compromised (HU-037), IntegrityChecker CronJob (HU-054), append-only no modificable (HU-119), verify episodio on-demand (HU-116), RLS multi-tenant (HU-104, HU-106).

**Known gaps**:
- Tests RLS reales requieren `CTR_STORE_URL_FOR_RLS_TESTS` apuntando a usuario no-superuser; sin esa env var los 4 tests se skippean silenciosamente. Ver `make test-rls`.
- Coverage objetivo tesis es ≥85% para el plano pedagógico (ver `BUGS-PILOTO.md` GAP-9); el real corriente se mide con `make test --cov`.
- El `EventPublishRequest.event_type` es `str` libre (no `Literal`). Un productor puede enviar `"tipo_desconocido"` y el worker lo persiste igual. La validación tipada sólo ocurre si el productor usa los schemas de `packages/contracts`.

**Fase de consolidación**:
- F3 — implementación inicial del ctr-service con cadena cripto (ver `docs/F3-STATE.md`).
- F4 — hardening: `IntegrityChecker`, métrica `ctr_episodes_integrity_compromised_total` (gate del canary de tutor-service en [ADR-015](../adr/015-blue-green-rolling-deploy.md)).
- F9 — preflight operacional: migraciones RLS, runbook I01 (integridad CTR), procedimiento I06 (borrado via `anonymize_student()` sin tocar el CTR).
- 2026-04-26 ([ADR-021](../adr/021-attestation-ed25519.md)) — registro externo Ed25519 con XADD a `attestation.requests` post-cierre.
- 2026-04-29 ([ADR-031](../adr/031-audit-aliases-ctr.md)) — aliases `/api/v1/audit/*` apuntando al MISMO handler que el legacy (gap D.4).
- 2026-04-29 ([ADR-025](../adr/025-episodio-abandonado.md)) — soporte para `episodio_abandonado` con `reason ∈ {beforeunload, timeout, explicit}`.
- 2026-05-04 (epic `ai-native-completion-and-byok`) — soporte para `tests_ejecutados` y `reflexion_completada`.
- 2026-05-04 (sesión bug-fix cross-package) — `compute_chain_hash` invertido en contracts package; nuevo test cross-package.
