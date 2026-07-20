# tutor-service

## 1. Qué hace (una frase)

Orquesta cada interacción socrática estudiante-tutor: carga el prompt vigente, hace retrieval al material de cátedra, invoca al LLM con streaming SSE, y emite la secuencia de eventos del CTR (`episodio_abierto`, `prompt_enviado`, `tutor_respondio`, `codigo_ejecutado`, `edicion_codigo`, `anotacion_creada`, `tests_ejecutados`, `reflexion_completada`, `episodio_cerrado`/`episodio_abandonado`).

## 2. Rol en la arquitectura

Pertenece al **plano pedagógico-evaluativo**. Materializa el componente "Servicio de tutor socrático" descrito en el Capítulo 6 de la tesis (arquitectura C4 del sistema AI-Native), cuyas responsabilidades nominales son: mediar la conversación entre estudiante y LLM bajo un prompt versionado, garantizar que cada turno quede trazado en el CTR con sus hashes de configuración, y propagar al clasificador N4 el contexto necesario (chunks usados, secuencia estricta prompt→respuesta).

Es el **único productor autorizado de eventos al CTR** (con la excepción explícita de `codigo_ejecutado`, `edicion_codigo`, `anotacion_creada` — que usan el `user_id` del estudiante real porque son actividad directa del usuario, no del tutor).

## 3. Responsabilidades

- Exponer `POST /api/v1/episodes` para abrir un episodio tras validar la `TareaPractica` contra [academic-service](./academic-service.md) (6 chequeos: existe, tenant matches, comisión matches, estado=published, dentro de ventana `fecha_inicio`/`fecha_fin`).
- Cargar el prompt activo desde [governance-service](./governance-service.md) y congelar `prompt_system_hash`/`prompt_system_version` en el `SessionState` del episodio.
- Persistir el `SessionState` en Redis (`tutor:session:{episode_id}`, TTL 6h) con los hashes de configuración, mensajes acumulados y próximo `seq` esperado.
- Servir `POST /api/v1/episodes/{id}/message` como SSE: hacer retrieval al [content-service](./content-service.md), emitir `prompt_enviado` con `chunks_used_hash`, streamear la respuesta del LLM vía [ai-gateway](./ai-gateway.md), acumular la respuesta completa, y emitir `tutor_respondio` con el mismo `chunks_used_hash`.
- Recibir eventos de actividad directa del estudiante (`codigo_ejecutado` desde Pyodide, `edicion_codigo` debounced desde el editor, `anotacion_creada` desde el panel de notas) y publicarlos al CTR asignando el `seq` correcto. Usar como `user_id` el del estudiante autenticado — no el service account del tutor.
- **Recibir conteos de tests ejecutados** ([ADR-033](../adr/033-sandbox-pyodide.md), [ADR-034](../adr/034-test-cases-tp.md)): `POST /api/v1/episodes/{id}/run-tests` recibe SOLO conteos (`tests_passed`, `tests_failed`, `tests_total`, `tests_hidden=0`) — no el código. Emite evento CTR `tests_ejecutados`. El classifier labeler v1.2.0 etiqueta N3/N4 sobre este evento.
- **Recibir reflexión metacognitiva post-cierre** ([ADR-035](../adr/035-reflexion-metacognitiva.md)): `POST /api/v1/episodes/{id}/reflection` con 3 textareas (≤500 chars c/u). Emite evento CTR `reflexion_completada`. **Excluido del classifier** vía `_EXCLUDED_FROM_FEATURES = {"reflexion_completada"}` en pipeline (RN-133, preserva `classifier_config_hash` reproducible bit-a-bit).
- Exponer `GET /api/v1/episodes/{id}` que reconstruye el estado del episodio desde los eventos del CTR para recovery del frontend (el `web-student` lo llama al recargar el browser).
- Cerrar episodios con `POST /api/v1/episodes/{id}/close` emitiendo `episodio_cerrado` y eliminando el `SessionState` de Redis.
- **Detectar abandono con doble trigger idempotente** ([ADR-025](../adr/025-episodio-abandonado.md), G10-A): el frontend llama `POST /api/v1/episodes/{id}/abandoned` con `reason="beforeunload"` (`caller_id=student`); en paralelo el `abandonment_worker.py` server-side scanea sesiones inactivas cada 60s y emite con `reason="timeout"` (`caller_id=TUTOR_SERVICE_USER_ID`). Idempotencia por estado de sesión Redis: la primera emisión gana, la segunda llamada encuentra `session=None` y devuelve sin emitir.
- Seleccionar modelo LLM por tenant via feature flags (`enable_claude_opus` → `claude-opus-4-7`, sino `claude-sonnet-4-6`).
- Cachear `materia_id` de la TP en `SessionState` al `open_episode` ([ADR-040](../adr/040-byok-propagation.md)) — alimenta el resolver BYOK del ai-gateway en cada turno (NO se re-resuelve por turno).

## 4. Qué NO hace (anti-responsabilidades)

- **NO persiste nada en una DB propia**: no tiene base lógica. Estado volátil en Redis; estado histórico en `ctr_store` (propiedad de [ctr-service](./ctr-service.md)).
- **NO invoca LLMs directamente**: toda llamada a Claude/OpenAI pasa por [ai-gateway](./ai-gateway.md). RN-101 lo prohíbe explícitamente.
- **NO clasifica en N4**: sólo emite los eventos. La clasificación es asíncrona en [classifier-service](./classifier-service.md) cuando el episodio se cierra.
- **NO hace ingesta ni chunking del material**: pide chunks por tema al [content-service](./content-service.md) con `comision_id` mandatorio.
- **NO es el tenedor del prompt**: lo carga desde governance en cada apertura de episodio, lo congela en el SessionState, y nunca lo modifica ni reemplaza mid-conversation. Si el prompt cambia en governance mientras un episodio está abierto, el episodio sigue con la versión original.
- **NO re-valida JWT**: confía en los headers `X-User-Id`, `X-Tenant-Id`, `X-User-Roles` (plural) inyectados por [api-gateway](./api-gateway.md). Tiene su propio `auth/dependencies.py` que sólo los lee.

## 5. Endpoints HTTP

| Método | Path | Qué hace | Auth |
|---|---|---|---|
| `POST` | `/api/v1/episodes` | Abre episodio; valida TareaPractica; emite `episodio_abierto` (seq=0). | Roles `estudiante`, `docente`, `docente_admin`, `superadmin`. |
| `GET` | `/api/v1/episodes/{id}` | Devuelve estado reconstruído (metadata + último snapshot de código + mensajes + notas). Funciona para episodios cerrados en modo lectura. | Mismos roles. |
| `POST` | `/api/v1/episodes/{id}/message` | SSE con la respuesta del tutor. Emite `prompt_enviado` antes y `tutor_respondio` después. | Mismos roles. |
| `POST` | `/api/v1/episodes/{id}/close` | Emite `episodio_cerrado` y borra el SessionState. 204. | Mismos roles. |
| `POST` | `/api/v1/episodes/{id}/events/codigo_ejecutado` | Emite evento desde Pyodide (`code`, `stdout`, `stderr`, `duration_ms`, `runtime`). 202 con `seq`. | Mismos roles. `user_id` del evento = estudiante real. |
| `POST` | `/api/v1/episodes/{id}/events/edicion_codigo` | Emite snapshot del editor + `diff_chars` + `language` + `origin` opcional (`student_typed` \| `copied_from_tutor` \| `pasted_external`, F6). 202 con `seq`. Crítico para CCD. | Mismos roles. |
| `POST` | `/api/v1/episodes/{id}/events/lectura_enunciado` | Emite tiempo de visibilidad acumulado del panel del enunciado (`duration_seconds`, IntersectionObserver + visibilitychange en el frontend, F5). 202 con `seq`. Señal observable canónica de N1 (Comprensión). | Mismos roles. `user_id` del evento = estudiante real. |
| `POST` | `/api/v1/episodes/{id}/events/anotacion_creada` | Emite `AnotacionCreada` (reflexión explícita del estudiante). Alimenta CCD orphan ratio. 202 con `seq`. | Mismos roles. `user_id` del evento = estudiante real. |
| `POST` | `/api/v1/episodes/{id}/run-tests` | Recibe SOLO conteos (`tests_passed`, `tests_failed`, `tests_total`, `tests_hidden=0`); emite evento CTR `tests_ejecutados` ([ADR-034](../adr/034-test-cases-tp.md), RN-134). El classifier labeler v1.2.0 lo etiqueta como N3/N4. | Mismos roles. `user_id` = estudiante. |
| `POST` | `/api/v1/episodes/{id}/reflection` | Recibe 3 textareas (≤500 chars c/u) post-clasificación; emite evento CTR `reflexion_completada` ([ADR-035](../adr/035-reflexion-metacognitiva.md)). **Excluido del classifier** (RN-133). | Mismos roles. `user_id` = estudiante. |
| `POST` | `/api/v1/episodes/{id}/abandoned` | Trigger explícito desde frontend (`reason="beforeunload"` o `"explicit"`). Idempotente con worker server-side ([ADR-025](../adr/025-episodio-abandonado.md)). 202 con `seq` o no-op si ya emitido. | Mismos roles. `user_id` = estudiante. |
| `GET` | `/health`, `/health/ready` | Health real con `check_redis` + `check_http(governance, content, ai_gateway, ctr, academic)` (epic `real-health-checks`, 2026-05-04). | Ninguna. |

**Ejemplo — abrir episodio**:

Request:
```
POST /api/v1/episodes
Authorization: Bearer <jwt>
Content-Type: application/json

{
  "comision_id": "a1a1a1a1-...",
  "problema_id": "b2b2b2b2-...",
  "curso_config_hash": "c0c0c0c0...64hex",
  "classifier_config_hash": "e5f6a7b8...64hex"
}
```

Response:
```json
{ "episode_id": "7b3e7c8e-1a4f-4a6c-9b2e-3c0d5e6f7a1b" }
```

**Ejemplo — SSE de `POST /episodes/{id}/message`**:

Request body: `{ "content": "¿Por qué mi solución tiene complejidad O(n²)?" }`

Response stream (`text/event-stream`):
```
data: {"type": "chunk", "content": "Bueno, "}

data: {"type": "chunk", "content": "antes "}

data: {"type": "chunk", "content": "de "}

data: {"type": "chunk", "content": "responder, "}

... (múltiples chunks) ...

data: {"type": "done", "chunks_used_hash": "f3a1b2c3...64hex", "seqs": {"prompt": 7, "response": 8}}
```

Durante este stream el tutor-service emite **dos eventos CTR** (antes de empezar el stream emite `prompt_enviado`; al completar acumula `full_response` y emite `tutor_respondio`). Invariante RN-096: entre ambos **no se permiten otros eventos del tutor-service en ese episodio**.

**Ejemplo — `POST /events/codigo_ejecutado`**:

Request:
```json
{
  "code": "def factorial(n):\n    return 1 if n==0 else n*factorial(n-1)",
  "stdout": "120\n",
  "stderr": "",
  "duration_ms": 12.4
}
```

Response `202`:
```json
{ "status": "accepted", "seq": "5" }
```

El evento se publica al CTR con `user_id = user.id` (el estudiante autenticado), **no** con `TUTOR_SERVICE_USER_ID`. Misma regla para `edicion_codigo` y `anotacion_creada` — son actividad directa del estudiante.

## 6. Dependencias

**Depende de (infraestructura):**
- Redis — `tutor:session:{episode_id}` (TTL 6h) para el estado de sesión. DB index 2 por default.

**Depende de (otros servicios):**
- [governance-service](./governance-service.md) — `GET /api/v1/prompts/{name}/{version}` al abrir episodio. Sin governance respondiendo, la apertura falla 500.
- [academic-service](./academic-service.md) — `GET /api/v1/tareas-practicas/{id}` para la validación de 6 chequeos antes del evento `episodio_abierto`. Doble chequeo best-effort (pre y post creación del SessionState) para achicar la ventana de race.
- [content-service](./content-service.md) — `POST /api/v1/retrieve` con `comision_id` obligatorio. Devuelve chunks ordenados + `chunks_used_hash`.
- [ai-gateway](./ai-gateway.md) — `POST /api/v1/stream` con los messages (system + RAG context + historia + user_message) y el modelo seleccionado.
- [ctr-service](./ctr-service.md) — `POST /api/v1/events` para cada evento emitido. Es el único productor en runtime (junto con el estudiante via los endpoints `.../events/...`).
- `packages/platform-ops` — `FeatureFlags` loader para resolver `enable_claude_opus` por tenant.

**Dependen de él:**
- [web-student](./web-student.md) — único consumidor directo. Abre episodios, streamea respuestas, publica eventos de actividad.
- `packages/auth-client` y `packages/ctr-client` — utilizados desde el frontend.

## 7. Modelo de datos

**No tiene DB propia**. El estado de sesión vive en Redis:

- **Key**: `tutor:session:{episode_id}`
- **TTL**: `SESSION_TTL = 6 * 3600` (6h).
- **Contenido** (`SessionState`): `episode_id`, `tenant_id`, `comision_id`, `student_pseudonym`, `seq` (próximo a asignar), `messages` (lista acumulada rol/contenido), `prompt_system_hash`, `prompt_system_version`, `classifier_config_hash`, `curso_config_hash`, `model`.

```python
# apps/tutor-service/src/tutor_service/services/session.py:21
SESSION_TTL = 6 * 3600

@dataclass
class SessionState:
    episode_id: UUID
    tenant_id: UUID
    comision_id: UUID
    student_pseudonym: UUID
    seq: int = 0
    messages: list[dict[str, str]] = field(default_factory=list)
    prompt_system_hash: str = ""
    prompt_system_version: str = ""
    classifier_config_hash: str = ""
    curso_config_hash: str = ""
    model: str = ""   # seleccionado por feature flag en open_episode
    materia_id: UUID | None = None  # cacheado al open_episode (ADR-040 BYOK)
```

El estado histórico vive en `ctr_store` (propiedad de [ctr-service](./ctr-service.md)). El abandono de episodio está **wireado** ([ADR-025](../adr/025-episodio-abandonado.md), epic G10-A): hay dos emisores complementarios:
1. **Frontend** (`web-student/EpisodePage.tsx`): listener `beforeunload` → `POST /episodes/{id}/abandoned` con `reason="beforeunload"`, `caller_id=student`.
2. **Worker server-side** (`apps/tutor-service/src/tutor_service/services/abandonment_worker.py`): scanea sesiones Redis cada `abandonment_check_interval_seconds=60`s; emite `reason="timeout"` con `caller_id=TUTOR_SERVICE_USER_ID` cuando `now - last_activity > episode_idle_timeout_seconds=1800` (30 min).

**Idempotencia por estado de sesión**: la primera emisión borra la sesión Redis; la segunda llamada encuentra `session=None` y devuelve sin emitir. Cualquier reseñalización de `record_episodio_abandonado` debe preservar la propiedad de cancelación atómica del state Redis post-emit.

## 8. Archivos clave para entender el servicio

- `apps/tutor-service/src/tutor_service/services/tutor_core.py` — **el orquestador**. `TutorCore.open_episode()`, `TutorCore.interact()` (el SSE principal), `TutorCore.close_episode()`, y los helpers para los eventos de actividad del estudiante (`emit_codigo_ejecutado`, `record_edicion_codigo`, `record_anotacion_creada`). Define `TUTOR_SERVICE_USER_ID = UUID("00000000-0000-0000-0000-000000000010")` — constante crítica (RN-096, CLAUDE.md "Constantes que NO deben inventarse").
- `apps/tutor-service/src/tutor_service/services/academic_client.py` — valida `TareaPractica` con los 6 chequeos previos al `episodio_abierto` (ver `_validate_tarea_practica` en `tutor_core.py`).
- `apps/tutor-service/src/tutor_service/services/session.py` — `SessionManager` sobre Redis + `SESSION_TTL`. `next_seq()` es atómico (INCR de Redis).
- `apps/tutor-service/src/tutor_service/services/clients.py` — clientes HTTP hacia `governance`, `content`, `ai-gateway`, `ctr`. Todos inyectan los headers `X-Tenant-Id`, `X-User-Id` autoritativamente (el tutor es la fuente del caller_id en las llamadas service-to-service).
- `apps/tutor-service/src/tutor_service/services/features.py` — `FeatureFlags` (pasa por `platform-ops`). Resuelve `enable_claude_opus` por tenant.
- `apps/tutor-service/src/tutor_service/routes/episodes.py` — los endpoints (≥10 ahora con `run-tests`, `reflection`, `abandoned`). `_build_episode_state()` es la proyección CTR→UI que usa `GET /episodes/{id}` para recovery.
- `apps/tutor-service/src/tutor_service/services/abandonment_worker.py` — worker server-side que scanea sesiones Redis cada 60s y emite `episodio_abandonado` con `reason="timeout"` ([ADR-025](../adr/025-episodio-abandonado.md)).
- `apps/tutor-service/src/tutor_service/config.py` — URLs a los 5 servicios dependientes + nombres de modelos LLM. `episode_idle_timeout_seconds=1800`, `abandonment_check_interval_seconds=60`. **`default_prompt_version`** declarado como `v1.0.1` con override de env → eventos persisten `v1.1.0` (drift declarado en CLAUDE.md, test `test_config_prompt_version.py::test_manifest_yaml_existe_y_se_parsea` cubre la consistencia).

**Los 6 chequeos de `_validate_tarea_practica` (pre `episodio_abierto`)**:

```python
# apps/tutor-service/src/tutor_service/services/tutor_core.py:393
tarea = await self.academic.get_tarea_practica(tarea_id=tarea_id, tenant_id=tenant_id, ...)

# 1. Existe
if tarea is None:
    raise HTTPException(404, "Tarea práctica no encontrada")

# 2. Tenant matches (defense in depth — RLS ya debería filtrar)
if tarea.tenant_id != tenant_id:
    raise HTTPException(403, "Tarea práctica de otro tenant")

# 3. Comisión correcta
if tarea.comision_id != comision_id:
    raise HTTPException(400, "Tarea práctica no pertenece a esta comisión")

# 4. Estado published (ni draft, ni archived)
if tarea.estado == "draft":
    raise HTTPException(409, "Tarea práctica en estado borrador, no se puede abrir episodio")
if tarea.estado == "archived":
    raise HTTPException(409, "Tarea práctica archivada, no se aceptan nuevos episodios")

# 5. Ventana temporal — now ≥ fecha_inicio
now = datetime.now(UTC)
if tarea.fecha_inicio is not None and now < tarea.fecha_inicio:
    raise HTTPException(403, "Tarea práctica no ha comenzado todavía")

# 6. Ventana temporal — now ≤ fecha_fin
if tarea.fecha_fin is not None and now > tarea.fecha_fin:
    raise HTTPException(403, "Tarea práctica fuera de plazo (deadline pasado)")
```

La función se llama **dos veces** en `open_episode`: una antes de crear el `SessionState` y otra inmediatamente después (con `is_recheck=True`). El segundo chequeo es best-effort — achica la ventana de race con `academic-service` a <1ms pero no la elimina (no hay transacción distribuida).

**Flujo del `TutorCore.interact()` (el SSE de `POST /message`) — en orden**:

```
1. sessions.get(episode_id) → SessionState (o error si expiró)
2. content.retrieve(query, comision_id, top_k=5) → chunks + chunks_used_hash
3. sessions.next_seq() → prompt_seq  (INCR atómico)
4. ctr.publish_event({event_type: "prompt_enviado", seq: prompt_seq,
                      payload: {content: query, chunks_used_hash, ...}})
5. messages = state.messages + [sys(rag_context), user(query)]
6. async for chunk in ai_gateway.stream(messages, model, tenant_id):
       full_response += chunk
       yield {"type": "chunk", "content": chunk}    # al cliente SSE
7. state.messages += [user(query), assistant(full_response)]
   sessions.set(state)
8. sessions.next_seq() → response_seq   # response_seq == prompt_seq + 1
9. ctr.publish_event({event_type: "tutor_respondio", seq: response_seq,
                      payload: {content: full_response, chunks_used_hash, model}})
10. yield {"type": "done", "chunks_used_hash", "seqs": {"prompt": prompt_seq, "response": response_seq}}
```

El `chunks_used_hash` es **el mismo** en los eventos `prompt_enviado` y `tutor_respondio` del mismo turno — RN-026. Lo calcula content-service una sola vez (paso 2), y el tutor lo reusa en ambos eventos (pasos 4 y 9). Cambiarlo entre evento y evento rompe CCD del classifier.

## 9. Configuración y gotchas

**Env vars críticas** (`apps/tutor-service/src/tutor_service/config.py`):

- `REDIS_URL` — default `redis://127.0.0.1:6379/2` (DB index **2**, separado del bus del CTR que usa DB 0 y del ai-gateway que usa DB 1).
- `GOVERNANCE_SERVICE_URL` — default `http://127.0.0.1:8010`.
- `CONTENT_SERVICE_URL` — default `http://127.0.0.1:8009`.
- `AI_GATEWAY_URL` — default `http://127.0.0.1:8011`.
- `CTR_SERVICE_URL` — default `http://127.0.0.1:8007`.
- `ACADEMIC_SERVICE_URL` — default `http://127.0.0.1:8002`.
- `DEFAULT_PROMPT_VERSION` — default `v1.0.0`. Debe existir en el filesystem del governance-service.
- `DEFAULT_MODEL` — default `claude-sonnet-4-6`. `OPUS_MODEL` — `claude-opus-4-7`.
- `FEATURE_FLAGS_PATH` — default `/etc/platform/feature_flags.yaml`. En dev puede estar vacío.

**Puerto de desarrollo**: `8006`.

**Gotchas específicos**:

- **Invariante de secuencia prompt→respuesta**: en una interacción el tutor debe emitir primero `prompt_enviado` con un seq `N` reservado, luego streamear, y finalmente `tutor_respondio` con seq `N+1`. Entre ambos no se admiten otros eventos del tutor (RN-096). El `SessionManager.next_seq()` es atómico (INCR) — si se parte el flujo, el CTR detecta el hueco al persistir.
- **`chunks_used_hash` debe coincidir entre `prompt_enviado` y `tutor_respondio` del mismo turno** (RN-026): ambos llevan el mismo valor (calculado una sola vez al hacer retrieval). Romper esto invalida CCD (`classifier-service`).
- **`codigo_ejecutado` usa `user.id` del estudiante, NO `TUTOR_SERVICE_USER_ID`**: ver `routes/episodes.py:345`. Misma regla para `edicion_codigo` y `anotacion_creada`. Es la única excepción a "el tutor es el productor" y está documentada como invariante en CLAUDE.md.
- **Doble validación de `TareaPractica`**: `open_episode` llama `_validate_tarea_practica` dos veces (pre y post `SessionState.set`). Es **best-effort** — no hay transacción distribuida contra academic. La ventana de race residual es <1ms pero no es cero. Documentado en CLAUDE.md.
- **Cache del `_tutor` singleton**: `_get_tutor()` crea el `TutorCore` una sola vez con los URLs del settings. Si `governance` o `academic` no están corriendo al primer request, el singleton queda con clientes "malos" pero igual intenta — el error recién aparece en el HTTPX call, no en el arranque.
- **SSE con `X-Accel-Buffering: no`**: el header lo consume el proxy reverso (si hubiera nginx delante); con el api-gateway FastAPI actual no hace diferencia, pero está puesto por si se mete un proxy.
- **Idempotencia mala en los events endpoints**: el frontend NO debe reintentar `POST /events/codigo_ejecutado` (ni los otros) en error de red — cada POST exitoso registra una nueva fila con seq distinto. El cliente debe consultar el episodio si tiene dudas.
- **`tests_ejecutados` con `tests_hidden=0` invariante en endpoint POST run-tests** (RN-134): el endpoint NO recibe el código de los tests, sólo conteos. Si un docente exfiltra los hidden tests por otro vector, el classifier los IGNORA (`is_public=false` no entra al feature extraction).
- **`reflexion_completada` excluida del classifier** (RN-133): post-fix anti-regresión `test_reflexion_completada_no_afecta_clasificacion_ni_features` en `apps/classifier-service/tests/unit/test_pipeline_reproducibility.py`. Si agregás un evento side-channel post-cierre, agregalo al `_EXCLUDED_FROM_FEATURES` set.
- **`materia_id` cacheado en SessionState** ([ADR-040](../adr/040-byok-propagation.md)): se resuelve UNA vez al `open_episode` (lee de la TP) y se cachea. NO se re-resuelve por turno. Sin él, el resolver BYOK del ai-gateway degrada a scope=tenant (`resolved_scope="tenant_fallback_no_materia"`).
- **`tutor_respondio.payload` no persiste `tokens_input/output/provider`** — sólo `model`, `content`, `chunks_used_hash` (deuda QA 2026-05-07).

**Traceback canónico — `POST /episodes` con governance caído**:

```
INFO: 192.168.1.5:54221 - "POST /api/v1/episodes HTTP/1.1" 500 Internal Server Error
ERROR tutor_service.services.tutor_core: Failed to open episode
Traceback (most recent call last):
  File ".../tutor_service/routes/episodes.py", line 157, in open_episode
    episode_id = await tutor.open_episode(...)
  File ".../tutor_service/services/tutor_core.py", line 94, in open_episode
    prompt = await self.governance.get_prompt(
  File ".../tutor_service/services/clients.py", line 54, in get_prompt
    r.raise_for_status()
httpx.HTTPStatusError: Client error '404 Not Found' for url
'http://127.0.0.1:8010/api/v1/prompts/tutor/v1.0.0'
```

Tres causas conocidas en dev: governance no arrancó, `PROMPTS_REPO_PATH` apunta a un path inexistente, o el prompt `tutor/v1.0.0` no está sembrado. Ver [governance-service](./governance-service.md) Sección 9.

**Traceback — emitir evento sobre episodio expirado**:

```
INFO: "POST /api/v1/episodes/.../events/edicion_codigo HTTP/1.1" 409 Conflict
{ "detail": "Episode 7b3e7c8e-... no existe, está cerrado o expiró" }
```

La sesión expira por TTL (6h) aunque el episodio siga "open" en el CTR. El frontend debe manejar el 409: no reintentar automáticamente, ofrecer al estudiante cerrar el episodio en lectura (`GET /episodes/{id}`) o abrir uno nuevo.

## 10. Relación con la tesis doctoral

El tutor-service es el **mediador pedagógico central** descrito en el Capítulo 6 de la tesis. Las dos afirmaciones que materializa son:

1. **Socraticidad trazable**: el Capítulo 4 de la tesis sostiene que la pedagogía socrática basada en LLMs sólo es evaluable si cada intercambio queda registrado con su contexto completo (prompt vigente, material usado, modelo invocado). El tutor lo hace: cada `prompt_enviado`/`tutor_respondio` lleva `prompt_system_hash`, `classifier_config_hash` y `chunks_used_hash`. Eso permite que el analista, meses después, sepa exactamente con qué prompt y qué material se generó cada respuesta.

2. **Separación estudiante-tutor en la autoría**: el `user_id` en el CTR distingue quién generó el evento. Los eventos del tutor (`prompt_enviado`, `tutor_respondio`) llevan `TUTOR_SERVICE_USER_ID`. Los eventos de actividad del estudiante (`codigo_ejecutado`, `edicion_codigo`, `anotacion_creada`) llevan el UUID real del estudiante. Esta distinción es necesaria para el cálculo de CCD (Code-Discourse Coherence) en [classifier-service](./classifier-service.md) — que presupone saber qué acciones son del estudiante.

**Secuencia pedagógica canónica** (Capítulo 7 de la tesis):

```
seq  event_type           emisor              ¿por qué este evento?
────────────────────────────────────────────────────────────────────────────
 0   episodio_abierto     tutor-service       Abre cadena criptográfica
 1   prompt_enviado       tutor-service       Primera pregunta del estudiante
 2   tutor_respondio      tutor-service       Respuesta socrática (stream completo)
 3   edicion_codigo       estudiante real     Empieza a escribir código
 4   edicion_codigo       estudiante real     Debounced: cambió >X chars
 5   codigo_ejecutado     estudiante real     Run → stdout, stderr capturados
 6   anotacion_creada     estudiante real     AnotacionCreada — reflexión explícita
 7   prompt_enviado       tutor-service       Segunda pregunta
 8   tutor_respondio      tutor-service       Segunda respuesta
 ...
 N   episodio_cerrado     tutor-service       Cierra cadena, estado=closed
```

Sobre esta secuencia **el classifier extrae las 5 coherencias**:
- **CT** (temporal): ventanas de trabajo separadas por pausas ≥5min — se infiere de los `ts` de todos los eventos.
- **CCD_mean** y **CCD_orphan_ratio** (código-discurso): correlación entre acciones (`codigo_ejecutado`, `prompt_enviado`) y verbalizaciones (`anotacion_creada`, `prompt_enviado` con `prompt_kind` reflexivo). Nota v1.0.0: `tutor_core.py:201` emite SIEMPRE `prompt_kind="solicitud_directa"` — la clasificación automática de intencionalidad del prompt es agenda confirmatoria (Eje B, G9). Hoy la única fuente activa de verbalización reflexiva en CCD es `anotacion_creada`. El docstring de `apps/classifier-service/src/classifier_service/services/ccd.py` documenta el sesgo.
- **CII_stability** y **CII_evolution** (inter-iteración): overlap léxico entre `prompt_enviado` consecutivos + longitud media a lo largo del episodio.

Sin la distinción `user_id = tutor vs user_id = estudiante`, el cálculo de CCD colapsa — el classifier no podría separar "acción del estudiante + verbalización del estudiante" de "respuesta del tutor que viene con verbalización incluida". Esa distinción está en el wire porque la pone este servicio.

**Por qué dos validaciones de `TareaPractica`**: el ataque hipotético es que un docente archive una TP mientras un estudiante la abre. Con una sola validación, hay una ventana (del orden del RTT `tutor → academic`, ~ms) donde el estudiante puede abrir un episodio contra una TP ya archivada. El segundo chequeo — inmediatamente antes del `ctr.publish_event("episodio_abierto")` — achica esa ventana a <1ms. No la elimina (no hay commit atómico cross-base, ADR-003), pero la hace despreciable para efectos del piloto.

## 11. Estado de madurez

**Tests** (5 archivos unit + health):
- `tests/unit/test_tutor_core.py` — flujo end-to-end de `TutorCore.interact()` con clientes mockeados, verifica secuencia prompt→respuesta y consistencia de `chunks_used_hash`.
- `tests/unit/test_episode_events.py` — `codigo_ejecutado`, `edicion_codigo`, `anotacion_creada` con el `user_id` correcto del estudiante (HU-076).
- `tests/unit/test_open_episode_tarea_practica_validation.py` — los 6 chequeos del validador + race condition (doble check).
- `tests/unit/test_session_manager.py` — serialización/deserialización del SessionState + TTL.
- `tests/unit/test_get_episode_state.py` — `_build_episode_state()` con casos de eventos en desorden, eventos incompletos, episodios cerrados.

**Known gaps**:
- Sin tests de integración contra Redis real (sólo mocks).
- Race window residual en la validación de TareaPractica (documentada).
- Feature flag de modelo LLM es estático (lee archivo YAML); el reload es cada 60s y no hay webhook.
- `tutor_respondio.payload` no persiste `tokens_input/output/provider` — sólo `model`, `content`, `chunks_used_hash` (deuda QA 2026-05-07).
- Drift declarado entre `default_prompt_version` (config) y `manifest.yaml` de governance — responsabilidad operacional en cualquier rotación futura.

**Fase de consolidación**:
- F3 — implementación inicial del `TutorCore` con SSE, retrieval, emisión de eventos (`docs/F3-STATE.md`).
- F4 — hardening, métricas, canary deployment con rollback por `ctr_episodes_integrity_compromised_total`.
- F5 — pseudonimización, feature flags runtime, `anotacion_creada`, Pyodide.
- F6 — feature flags por tenant + modelo opus, validación robusta de TareaPractica.
- 2026-04-29 ([ADR-025](../adr/025-episodio-abandonado.md), G10-A) — `episodio_abandonado` con doble trigger idempotente (frontend `beforeunload` + worker server-side `timeout`).
- 2026-05-04 (epic `ai-native-completion-and-byok`) — `POST /run-tests` ([ADR-034](../adr/034-test-cases-tp.md)), `POST /reflection` ([ADR-035](../adr/035-reflexion-metacognitiva.md)). `materia_id` cacheado en SessionState ([ADR-040](../adr/040-byok-propagation.md)).
- 2026-05-04 (epic `real-health-checks`) — `/health/ready` real con `check_redis + check_http` para los 5 deps.
