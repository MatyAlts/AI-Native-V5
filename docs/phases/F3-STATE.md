# Estado del repositorio — F3 completado

F3 implementa **el núcleo pedagógico completo** de la plataforma: CTR
criptográfico, tutor socrático con streaming, governance de prompts,
ai-gateway con budget, y clasificador N4 explicable. Esta es la fase
más larga del plan (4 meses) y la que contiene los aportes específicos
de la tesis — todo lo anterior era infraestructura para habilitar esto.

## Entregables F3

### 1. ctr-service — Cuaderno de Trabajo Reflexivo criptográfico

`apps/ctr-service/`:

- **Modelos** (`models/event.py`):
  - `Episode` con `last_chain_hash`, `events_count`, flag `integrity_compromised`
  - `Event` append-only con `event_uuid` (idempotencia), `seq` (orden
    estricto), `self_hash`, `chain_hash`, `prev_chain_hash`
  - `DeadLetter` para eventos que fallaron 3+ veces
- **Hashing criptográfico** (`services/hashing.py`):
  - `canonicalize()` con JSON `sort_keys=True`, `ensure_ascii=False`,
    `separators=(",", ":")` — determinismo total UTF-8
  - `compute_self_hash()` excluyente de campos computados
  - `compute_chain_hash(self, prev)` = SHA256(self || prev) con
    `GENESIS_HASH = "0" * 64`
  - `verify_chain_integrity()` recomputa y detecta manipulación
- **Producer** (`services/producer.py`):
  - `shard_of(episode_id, n)` = SHA256(episode_id) mod n, estable
  - `EventProducer.publish()` con MAXLEN ~1M approximate
- **Worker particionado** (`workers/partition_worker.py`):
  - Consumer group `ctr_workers`, un pod por partición (single-writer
    por shard → no hay race conditions sobre episodios)
  - `XREADGROUP` → persistencia transaccional con RLS → `XACK`
  - Idempotencia por `(tenant_id, event_uuid)` con `ON CONFLICT DO NOTHING`
  - Validación de `seq` esperado (== `events_count` actual)
  - Retry con counter `times_delivered`; al 3° intento → `dead_letters`
    + marca episodio `integrity_compromised=true`
  - Auto-creación del `Episode` al recibir `episodio_abierto`
  - Graceful shutdown vía signal handlers
- **API HTTP** (`routes/events.py`):
  - `POST /api/v1/events` — publish al stream (202 Accepted + message_id)
  - `GET /api/v1/episodes/{id}` — episodio con eventos ordenados por seq
  - `POST /api/v1/episodes/{id}/verify` — recomputa cadena y devuelve
    `failing_seq` si rompe
- **Migración Alembic** inicial con 3 tablas + RLS

### 2. governance-service — Custodia de prompts

`apps/governance-service/`:

- **PromptLoader con fail-loud** (`services/prompt_loader.py`):
  - `load(name, version)` lee `system.md` del repo clonado
  - Si existe `manifest.yaml` con hash declarado, recomputa SHA-256 del
    contenido y **falla si no coincide** (defensa contra manipulación
    post-commit)
  - Cache local para evitar re-lectura en cada request
  - Parser YAML minimal sin deps externas
- **API HTTP** (`routes/prompts.py`):
  - `GET /api/v1/prompts/{name}/{version}` — contenido + hash verificado
  - `POST /api/v1/prompts/{name}/{version}/verify` — re-verificación
  - `GET /api/v1/active_configs` — manifest global de versiones activas
    por tenant

### 3. ai-gateway — Proxy unificado a LLMs

`apps/ai-gateway/`:

- **Providers** (`providers/base.py`):
  - `BaseProvider` abstracto con `complete()` y `stream_complete()`
  - `MockProvider` determinista para tests
  - `AnthropicProvider` con pricing conocido de Sonnet/Haiku/Opus
- **Budget tracking** (`services/budget_and_cache.py`):
  - `BudgetTracker` con contadores mensuales por `(tenant, feature)` en
    Redis con TTL de 35 días
  - Claves: `aigw:budget:{tenant}:{feature}:{YYYY-MM}` con
    `INCRBYFLOAT` atómico
- **Caché** de respuestas idempotentes:
  - `ResponseCache` que solo guarda si `temperature=0` (resultado
    determinista)
  - Clave = SHA-256 del canonical JSON del request
  - Hit sin costo; miss llama al provider
- **Routes** (`routes/complete.py`):
  - `POST /api/v1/complete` — síncrono
  - `POST /api/v1/stream` — SSE con tokens
  - `GET /api/v1/budget` — estado actual del tenant

### 4. tutor-service — Tutor socrático orquestador

`apps/tutor-service/`:

- **Clientes HTTP** hacia servicios dependientes (`services/clients.py`):
  - `GovernanceClient` — carga prompt
  - `ContentClient` — retrieval al content-service (pasa `comision_id`)
  - `AIGatewayClient` — stream SSE de tokens del LLM
  - `CTRClient` — publish de eventos
- **Session manager** (`services/session.py`):
  - `SessionState` en Redis con TTL de 6h
  - Contiene `episode_id`, `seq`, histórico de `messages`, todos los
    hashes de configuración activa
  - `next_seq()` atómico para orden estricto
- **Tutor core** (`services/tutor_core.py`):
  - `open_episode()`: carga prompt → crea session → publica
    `EpisodioAbierto` (seq=0)
  - `interact()` async generator:
    1. Retrieval con `comision_id` del session
    2. Emite `PromptEnviado` con `chunks_used_hash` del retrieval
    3. Stream del LLM con chunks yielded al cliente
    4. Emite `TutorRespondio` con `chunks_used_hash`
  - `close_episode()`: emite `EpisodioCerrado`
  - `TUTOR_SERVICE_USER_ID = UUID("00...0010")` como service-account
    fijo
- **Routes** (`routes/episodes.py`):
  - `POST /api/v1/episodes` — crea episodio
  - `POST /api/v1/episodes/{id}/message` — SSE con respuesta del tutor
  - `POST /api/v1/episodes/{id}/close` — cierra episodio

### 5. classifier-service — Clasificador N4 explicable

`apps/classifier-service/`:

- **Modelos** (`models/__init__.py`):
  - `Classification` append-only con flag `is_current`
  - `classifier_config_hash` en cada fila → reclasificar con distinto
    config produce nueva fila, las anteriores se marcan no-current
  - Preserva las 5 dimensiones (`ct_summary`, `ccd_mean`,
    `ccd_orphan_ratio`, `cii_stability`, `cii_evolution`) sin colapsar
    en un único score
- **Coherencia Temporal** (`services/ct.py`):
  - `compute_windows()` divide el episodio en ventanas separadas por
    pausas >5min
  - `compute_ct_summary()` score [0,1] combinando densidad y balance
    prompt/ejecución
- **Coherencia Código↔Discurso** (`services/ccd.py`):
  - Define "acciones" (prompt solicitud + código ejecutado) y
    "reflexiones" (anotaciones + prompts kind=reflexion)
  - Ventana de correlación 2 min
  - `ccd_mean` = qué tan rápido es el giro cuando se da
  - `ccd_orphan_ratio` = fracción de acciones sin reflexión posterior
- **Coherencia Inter-Iteración** (`services/cii.py`):
  - `cii_stability` = Jaccard promedio entre prompts consecutivos
  - `cii_evolution` = slope normalizada de longitud de prompts
- **Árbol de decisión N4** (`services/tree.py`):
  - 3 ramas: `delegacion_pasiva`, `apropiacion_superficial`,
    `apropiacion_reflexiva`
  - Rama delegación tiene dos gatillos: **extremo**
    (orphan_ratio ≥ 0.8 sin importar CT) o **clásico** (orphan alto +
    CT bajo)
  - `reference_profile` con umbrales configurables por curso
  - Cada clasificación incluye `reason` en prosa con los valores
    concretos que gatillaron la decisión (auditabilidad total)
- **Pipeline determinista** (`services/pipeline.py`):
  - `compute_classifier_config_hash()` canonical JSON → SHA-256 del
    profile + tree_version
  - `classify_episode_from_events()` puro e idempotente (mismos eventos
    + mismo profile = misma clasificación siempre)
  - `persist_classification()` marca `is_current=false` en la vieja
    antes de insertar la nueva (append-only)
- **Routes** (`routes/classify_ep.py`):
  - `POST /api/v1/classify_episode/{id}` — fetcheá el episodio del
    ctr-service y clasificá
  - `GET /api/v1/classifications/{id}` — devuelve la clasificación
    `is_current=true`
- **Migración Alembic** con tabla `classifications` + índice parcial
  sobre `(episode_id, is_current)` para consultas eficientes

### 6. web-student — UI del estudiante

`apps/web-student/`:

- `lib/api.ts` — cliente tipado que habla con el api-gateway:
  - `openEpisode()` / `closeEpisode()`
  - `sendMessage()` async generator que parsea SSE chunks
  - `classifyEpisode()` / `getClassification()`
- `pages/EpisodePage.tsx`:
  - Split view: editor de código (izq) + chat con tutor (der)
  - Estado de streaming con render incremental de chunks
  - Al cerrar episodio: dispara clasificación y muestra
    `ClassificationPanel` con las 3 coherencias + razonamiento del
    árbol, medidores con colores por rango, hash del config del
    clasificador visible para auditoría

### 7. api-gateway actualizado

`apps/api-gateway/`:

- `ROUTE_MAP` con 3 rutas nuevas:
  - `/api/v1/episodes/*` → tutor-service
  - `/api/v1/classify_episode/*` → classifier-service
  - `/api/v1/classifications/*` → classifier-service
- `config.py` con URLs de todos los servicios F3: tutor, ctr,
  classifier, content, governance, ai_gateway

### 8. Makefile actualizado

`make migrate` ahora incluye las 4 bases con sus migraciones:
academic-service, content-service, ctr-service, classifier-service,
identity-service.

## Tests F3 — 81 tests nuevos

```
apps/ctr-service/tests/unit/test_hashing_and_sharding.py .............. 14
  - canonicalización determinista UTF-8
  - self_hash excluye campos computados
  - genesis hash
  - cadena manipulada se detecta
  - chain_hash forjado se detecta
  - sharding estable + property-based testing

apps/governance-service/tests/unit/test_prompt_loader.py .............. 7
  - fail-loud ante hash mismatch
  - cache para evitar re-lectura
  - active_configs multi-tenant

apps/ai-gateway/tests/unit/test_budget_and_cache.py ................... 10
apps/ai-gateway/tests/unit/test_mock_provider.py ...................... 3
  - budget aislado por tenant y por feature
  - caché invariante al orden de keys (canonical JSON)
  - no cachea con temperature > 0

apps/tutor-service/tests/unit/test_session_manager.py ................. 5
apps/tutor-service/tests/unit/test_tutor_core.py ...................... 7
  - chunks_used_hash se propaga del retrieval al evento CTR (CRÍTICO)
  - seqs estrictamente consecutivos en multi-turno (0, 1, 2, 3, 4)
  - historia multi-turno se acumula en session
  - comision_id correcto pasado al content-service

apps/classifier-service/tests/unit/test_ct.py ......................... 6
apps/classifier-service/tests/unit/test_ccd.py ........................ 7
apps/classifier-service/tests/unit/test_cii.py ........................ 7
apps/classifier-service/tests/unit/test_tree.py ........................ 8
apps/classifier-service/tests/unit/test_pipeline_reproducibility.py ... 7
  - clasificación reproducible bit a bit (mismos eventos → mismo resultado)
  - classifier_config_hash invariante al orden de keys
  - escenarios end-to-end:
      * copy-paste extremo → delegacion_pasiva (gracias a rama extrema)
      * trabajo sostenido con reflexión → no delegación pasiva
```

## Suite completa del repo — 145/145 pasan

```
packages/contracts/tests/test_hashing.py ........................... 7
apps/academic-service/tests/unit/test_schemas.py .................. 10
apps/academic-service/tests/integration/test_casbin_matrix.py ..... 23
apps/content-service/tests/unit/*.py .............................. 24
apps/ctr-service/tests/unit/*.py .................................. 14
apps/governance-service/tests/unit/*.py ............................ 7
apps/ai-gateway/tests/unit/*.py ................................... 13
apps/tutor-service/tests/unit/*.py ................................ 12
apps/classifier-service/tests/unit/*.py ........................... 35
──────────────────────────────────────────────────────────────────────
                                                                   145
```

## Propiedades críticas preservadas (requeridos por la tesis)

1. **Trazabilidad criptográfica**: toda interacción con el tutor
   produce eventos en la cadena SHA-256 del CTR. Manipulación se detecta.

2. **Reproducibilidad de clasificaciones**: dado el mismo
   `classifier_config_hash` + los mismos eventos, se produce
   **exactamente el mismo resultado** (verificado con test).

3. **Propagación de `chunks_used_hash`**: el hash del set de chunks
   recuperados del content-service se incluye en el evento `PromptEnviado`
   del CTR. Cualquiera puede reproducir qué material exacto vio el tutor
   al responder (verificado con test).

4. **Filtro doble por `comision_id`**: retrieval aplica RLS por tenant_id
   + WHERE explícito por comision_id (defensa en profundidad contra
   leak cross-comisión).

5. **Append-only de clasificaciones** (ADR-010): reclasificar marca la
   fila vieja como `is_current=false` y crea nueva fila; nunca se
   borran ni modifican clasificaciones existentes.

6. **No colapsar las 3 coherencias**: `Classification` preserva las 5
   dimensiones numéricas (`ct_summary`, `ccd_mean`, `ccd_orphan_ratio`,
   `cii_stability`, `cii_evolution`); la etiqueta N4 es una SÍNTESIS
   explícita y auditable, no un score único opaco.

7. **Fail-loud en manipulación de prompts**: governance-service falla
   ante hash mismatch (verificado con test). El servicio se niega a
   operar si detecta manipulación.

8. **Single-writer por partición del CTR**: sharding estable garantiza
   que un episodio siempre va a la misma partición → no hay race
   conditions sobre `events_count` y `last_chain_hash`.

## Flujo end-to-end validado

```
Estudiante abre episodio via web-student
  → tutor-service crea SessionState + emite EpisodioAbierto (seq=0)
  → ctr-service valida, persiste en cadena

Estudiante envía mensaje
  → tutor-service:
      1. retrieval al content-service con comision_id → chunks + hash
      2. emite PromptEnviado (seq=1) con chunks_used_hash
      3. stream del LLM via ai-gateway
      4. acumula respuesta, envía chunks SSE al navegador
      5. emite TutorRespondio (seq=2) con chunks_used_hash
  → web-student renderiza incrementalmente

Estudiante cierra episodio
  → tutor-service emite EpisodioCerrado (seq=N)
  → web-student llama POST /classify_episode/{id}
  → classifier-service:
      1. fetchea episodio completo del ctr-service
      2. computa CT, CCD, CII
      3. aplica árbol N4 con reference_profile
      4. persiste Classification append-only con classifier_config_hash
  → web-student muestra las 3 coherencias + razón textual
```

## Comandos para validar F3

```bash
# Suite completa sin Docker (Mock de embedder/LLM/storage)
cd /home/claude/platform
EMBEDDER=mock RERANKER=identity STORAGE=mock LLM_PROVIDER=mock \
PYTHONPATH=apps/academic-service/src:apps/content-service/src:apps/ctr-service/src:apps/governance-service/src:apps/ai-gateway/src:apps/tutor-service/src:apps/classifier-service/src:packages/contracts/src:packages/test-utils/src \
  python3 -m pytest \
    apps/academic-service/tests/ \
    apps/content-service/tests/unit/ \
    apps/ctr-service/tests/unit/ \
    apps/governance-service/tests/unit/ \
    apps/ai-gateway/tests/unit/ \
    apps/tutor-service/tests/unit/ \
    apps/classifier-service/tests/unit/ \
    packages/contracts/tests/

# Esperado: 145 passed
```

## Qué queda fuera de F3 (para F4+)

- **Tests de integración end-to-end con Docker real**: hasta ahora todo
  se valida con mocks (redis mock, provider mock, HTTP mock). Tests e2e
  con testcontainers + pgvector + redis + keycloak llegan en F4 como
  parte del hardening.
- **web-student con autenticación Keycloak real**: hoy usa headers X-*
  de dev. F5 agrega el flow OIDC con redirect.
- **Editor Monaco** con ejecución de código: hoy es un textarea plano.
  Agregar Monaco + sandbox de ejecución Python (Pyodide o API backend)
  es parte de F4.
- **Vista docente** de clasificaciones agregadas por comisión: está el
  endpoint `GET /classifications/{id}` pero no hay UI aún.
- **Ingesta asíncrona de materiales**: sigue síncrona como en F2.
- **Validación de integridad periódica del CTR**: el endpoint
  `/episodes/{id}/verify` existe pero no hay cron job que lo corra
  sistemáticamente.

## Próxima fase — F4 (meses 11-13): Hardening + observabilidad

1. Tests integración con testcontainers reales (pgvector + redis + kafka/redis).
2. Observabilidad completa: traces OTel propagándose entre todos los
   servicios, dashboards Grafana con SLOs (latencia P95 del tutor,
   clasificaciones/día, budget consumido por tenant).
3. Canary deployments + rollback automático.
4. Editor Monaco + ejecución segura de código Python.
5. Vista docente de analytics agregados.
6. Validador de integridad periódica del CTR como CronJob.
7. Rate limiting en api-gateway.
