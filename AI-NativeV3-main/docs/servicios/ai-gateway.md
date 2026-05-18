# ai-gateway

## 1. Qué hace (una frase)

Actúa como proxy único hacia proveedores de LLM (Anthropic, OpenAI, **Mistral**, mock), aplicando budget mensual por tenant-feature, caché de respuestas deterministas, **resolver BYOK jerárquico (materia → tenant → env_fallback)** ([ADR-038](../adr/038-byok-encryption.md), [ADR-039](../adr/039-byok-resolver.md), [ADR-040](../adr/040-byok-propagation.md)), y una interfaz uniforme `POST /complete` / `POST /stream` — ningún otro servicio de la plataforma puede llamar directo a un proveedor de LLM.

## 2. Rol en la arquitectura

Pertenece al **plano pedagógico-evaluativo** en sentido funcional (soporta tutor-service y classifier-service), pero arquitectónicamente es **transversal**: infraestructura de IA compartida sin correspondencia directa con un componente nominal de la tesis. Existe porque el Capítulo 6 de la tesis — y la práctica operativa del piloto — exige tres propiedades que el modelo AI-Native no puede dejar libradas a cada servicio: control de costos por tenant, caché auditable de respuestas, y un único punto donde las credenciales de LLM viven (no dispersas en 12 servicios). [ADR-004](../adr/004-ai-gateway-propio.md) lo justifica formalmente.

## 3. Responsabilidades

- Exponer `POST /api/v1/complete` (síncrono, JSON) y `POST /api/v1/stream` (SSE) como **única puerta autorizada** a cualquier LLM (RN-101).
- Aceptar `messages + model + feature + temperature + max_tokens + materia_id?` y rutear a un provider concreto (`MockProvider`, `AnthropicProvider`, `OpenAIProvider`, `MistralProvider`) mediante `get_provider()` (factory con lru_cache).
- **Resolver la API key vía BYOK jerárquico** ([ADR-039](../adr/039-byok-resolver.md), RN-132): orden **materia → tenant → env_fallback** según `feature` + `tenant_id` + `materia_id?`. Scope `facultad` declarado pero **no implementado en piloto-1** (requiere lookup cross-DB; cache Redis es follow-up).
- **Encriptar y persistir API keys de cliente** ([ADR-038](../adr/038-byok-encryption.md)): tablas `byok_keys` y `byok_keys_usage` con RLS forzada. Encriptación AES-256-GCM via `packages/platform-ops/src/platform_ops/crypto.py::encrypt/decrypt` con master key en env `BYOK_MASTER_KEY` (32 bytes base64). Endpoints CRUD: `POST /keys`, `GET /keys`, `POST /keys/{id}/rotate`, `POST /keys/{id}/revoke`, `GET /keys/{id}/usage`.
- Contabilizar gasto mensual por `(tenant_id, feature)` en Redis bajo la key `aigw:budget:{tenant_id}:{feature}:{YYYY-MM}`. Rechazar con 429 si el budget se excede. Adicionalmente **incrementar `byok_keys_usage` con UPSERT** (yyyymm + key_id) post-`tracker.charge` en `routes/complete.py` cuando el resolver elige una BYOK key.
- Cachear respuestas idempotentes (`temperature=0`) bajo `hash(input + model + params)`. El docstring cita ~40% de ahorro en clasificación.
- Registrar cada invocación con `input_tokens`, `output_tokens`, `cost_usd`, `cache_hit`, `provider` para observabilidad (Grafana + Loki via structlog + OTel).
- Emitir métricas OTLP específicas BYOK: `byok_key_usage_total`, `byok_key_resolution_total{resolved_scope}`, `byok_key_resolution_duration_seconds` (SLO p99 < 50ms). Health check `byok_resolver_healthy` no-critical degrada cuando master key falta.
- Exponer `GET /api/v1/budget?feature=...` para que otros servicios (o la UI docente) consulten el estado del budget mensual.
- Traducir el esquema interno uniforme (`CompletionRequest`/`CompletionResponse`) al formato nativo de cada provider y de regreso — el caller no ve la heterogeneidad.

## 4. Qué NO hace (anti-responsabilidades)

- **NO tiene usuarios finales para los endpoints LLM**: sus clientes son **otros servicios** de la plataforma (tutor-service, classifier-service, academic-service vía TP-gen, content-service si usa embeddings remotos). Se autentica con headers `X-Tenant-Id` + `X-Caller` inyectados por el caller, no con JWT de usuario. En F5+ está previsto migrar a mTLS o JWT de cliente. **Excepción**: los endpoints CRUD de BYOK (`/keys/*`) sí son consumidos por web-admin como UI humana (con Casbin `byok_key:CRUD` para superadmin/docente_admin).
- **NO decide qué modelo usar**: el caller manda `model` explícito en cada request. La selección `sonnet` vs `opus` por tenant la hace [tutor-service](./tutor-service.md) con sus feature flags antes de llamar.
- **NO persiste estado de LLM en DB propia**: estado volátil en Redis (budget counters + caché con TTL). **Sí tiene `alembic/` para BYOK**: tablas `byok_keys` y `byok_keys_usage` viven en `academic_main` (compartido — coordinación con academic-service).
- **NO hace rate limiting por IP/user**: eso es [api-gateway](./api-gateway.md). Acá el único control cuantitativo es budget mensual en USD.
- **NO valida permisos RBAC para los endpoints LLM**: los callers son servicios internos confiables. El gateway externo ya filtró al usuario; el ai-gateway sólo ve la invocación del servicio. **Sí valida Casbin para BYOK**: `byok_key:CRUD` sólo para `superadmin` y `docente_admin`.
- **NO streamea el CTR directamente**: quien emite los eventos `prompt_enviado`/`tutor_respondio` al CTR es [tutor-service](./tutor-service.md). El ai-gateway sólo ve el streaming de tokens, no los metadatos pedagógicos.

## 5. Endpoints HTTP

| Método | Path | Qué hace | Auth |
|---|---|---|---|
| `POST` | `/api/v1/complete` | Completion síncrona (JSON). Resuelve BYOK key (materia → tenant → env_fallback). Chequea budget, check caché, invoca provider, cachea, carga el gasto, incrementa `byok_keys_usage`. Devuelve `content + model + provider + tokens + cost_usd + cache_hit + budget_status`. 429 si budget excedido, 502 si provider falla. Acepta `materia_id?` opcional ([ADR-040](../adr/040-byok-propagation.md)). | Headers `X-Tenant-Id` + `X-Caller`. |
| `POST` | `/api/v1/stream` | SSE streaming. Misma validación de budget + BYOK pre-stream. Yielda `{"type": "token", "content": "..."}` y cierra con `{"type": "done", "estimated_cost_usd": ...}`. El costo es estimado por longitud de output porque algunos providers no exponen tokens finales en streaming. | Mismos headers. |
| `GET` | `/api/v1/budget?feature=...` | Estado del budget mensual: `used_usd`, `limit_usd`, `remaining_usd`, `exceeded`. | Mismos headers. |
| `POST` | `/api/v1/byok/keys` | Crear BYOK key. Body: `provider, scope (materia\|tenant), scope_id?, plaintext_value, label?, expires_at?`. Encripta con AES-256-GCM y persiste. | Casbin `byok_key:create`. |
| `GET` | `/api/v1/byok/keys` | Listar BYOK keys del tenant. Devuelve metadata sin plaintext (sólo prefix/suffix opcional). | Casbin `byok_key:read`. |
| `POST` | `/api/v1/byok/keys/{id}/rotate` | Rotar key (preserva metadata, re-encripta nuevo plaintext). | Casbin `byok_key:update`. |
| `POST` | `/api/v1/byok/keys/{id}/revoke` | Marcar `revoked_at = now()`. La key deja de ser elegible por el resolver. | Casbin `byok_key:update`. |
| `GET` | `/api/v1/byok/keys/{id}/usage` | Lista usage por mes (`yyyymm`, requests, tokens_in, tokens_out, cost_usd). | Casbin `byok_key:read`. |
| `GET` | `/health`, `/health/ready` | Health real con `check_postgres` + `check_redis` + `byok_resolver_healthy` (no-critical degrada con master key faltante). Status `ready/degraded/error` → 200/200/503 (epic `real-health-checks`, 2026-05-04). | Ninguna. |

**Ejemplo — request `POST /api/v1/complete`**:

```
POST /api/v1/complete
X-Tenant-Id: aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa
X-Caller: tutor-service
Content-Type: application/json

{
  "messages": [
    {"role": "system", "content": "Sos un tutor socrático..."},
    {"role": "user", "content": "¿Por qué O(n²)?"}
  ],
  "model": "claude-sonnet-4-6",
  "feature": "tutor",
  "temperature": 0.7,
  "max_tokens": 2048
}
```

Response:

```json
{
  "content": "Antes de responder directamente, pensemos juntos...",
  "model": "claude-sonnet-4-6",
  "provider": "anthropic",
  "feature": "tutor",
  "input_tokens": 324,
  "output_tokens": 187,
  "cost_usd": 0.00377,
  "cache_hit": false,
  "budget_status": {
    "used_usd": 12.47,
    "limit_usd": 100.0,
    "remaining_usd": 87.53
  }
}
```

**Ejemplo — `POST /api/v1/stream`** (SSE):

```
data: {"type": "token", "content": "Bueno, "}

data: {"type": "token", "content": "antes "}

...

data: {"type": "done", "estimated_cost_usd": 0.0023}
```

Nota: `estimated_cost_usd` es aproximado (ver gotcha en Sección 9). Para costo exacto, usar `POST /complete` (sync).

**Ejemplo — `GET /api/v1/budget?feature=tutor`**:

```json
{
  "tenant_id": "aaaaaaaa-...",
  "feature": "tutor",
  "month": "2026-04",
  "used_usd": 12.47,
  "limit_usd": 100.0,
  "remaining_usd": 87.53,
  "exceeded": false
}
```

**Error response — budget excedido**:

```
HTTP/1.1 429 Too Many Requests
{
  "detail": "Budget excedido para aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa/tutor: gastado $100.23 de $100.00"
}
```

## 6. Dependencias

**Depende de (infraestructura):**
- Redis — DB index **1** (separada del CTR que usa 0 y del tutor que usa 2). Keys `aigw:budget:*` y `aigw:cache:*`.
- PostgreSQL — base lógica `academic_main` (compartida con academic-service vía engine independiente). Tablas: `byok_keys`, `byok_keys_usage`. RLS forzada por `tenant_id`.
- Env vars: `BYOK_MASTER_KEY` (32 bytes base64 — generar con `openssl rand -base64 32`); `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `MISTRAL_API_KEY` como fallback genérico cuando el resolver no encuentra BYOK key (scope `env_fallback`).

**Depende de (otros servicios):** ninguno. Es **hoja**.

**Dependen de él (según RN-101, TODOS los que necesitan LLM/embedding):**
- [tutor-service](./tutor-service.md) — consumidor principal. `POST /stream` por cada turno del tutor. Propaga `materia_id` cacheado en `SessionState` desde `open_episode` (ADR-040).
- [academic-service](./academic-service.md) — `POST /complete` con `feature="tp_generator"` + `materia_id` en el endpoint TP-gen IA ([ADR-036](../adr/036-tp-gen-ia.md)).
- [classifier-service](./classifier-service.md) — previsto para clasificación semántica (hoy usa lógica léxica; la ruta semántica quedaría como HU futura).
- [content-service](./content-service.md) — cuando el embedder esté configurado como provider externo (Voyage, OpenAI).
- [web-admin](./web-admin.md) — UI de gestión de BYOK keys (página BYOK con `UsagePanel` + stats grid).

## 7. Modelo de datos

**Estado volátil en Redis (DB 1)**:

- **`aigw:budget:{tenant_id}:{feature}:{YYYY-MM}`** — float acumulado del gasto mensual.
  - Actualización atómica con `INCRBYFLOAT` — resistente a múltiples writers concurrentes.
  - TTL 35 días (expira pasado el mes).
  - Una key por tenant-feature-mes.

- **`aigw:cache:{sha256(canonical_request)}`** — `CompletionResponse` serializado.
  - Sólo se popula cuando `temperature == 0.0 and not stream`.
  - TTL default `7 * 24 * 3600` (7 días). Configurable por el caller (`ResponseCache.__init__`).
  - El `cache_hit` no se guarda en el blob — se setea al leer.

**Estado persistente en PostgreSQL `academic_main`** ([ADR-038](../adr/038-byok-encryption.md)):

- **`byok_keys`** — keys encriptadas BYOK.
  - PK: `id` UUID.
  - `tenant_id` con RLS forzada (POLICY `tenant_isolation` + FORCE).
  - `scope` (`materia | tenant | facultad`), `scope_id?` (UUID; null si scope=tenant).
  - `provider` (`anthropic | openai | mistral`).
  - `feature?` (string libre, ej. `"tutor"`, `"tp_generator"`).
  - `encrypted_value` (bytes — AES-256-GCM con master key).
  - `label?`, `expires_at?`, `revoked_at?`, `created_by`, `created_at`.
- **`byok_keys_usage`** — usage tracking por mes (UPSERT).
  - PK: `(key_id, yyyymm)`.
  - `requests INTEGER`, `tokens_in BIGINT`, `tokens_out BIGINT`, `cost_usd NUMERIC`.
  - Llamado post-`tracker.charge` en `routes/complete.py` cuando el resolver elige una BYOK key. **Vacío hoy cuando el resolver cae a `env_fallback`** — gap declarado para auditoría doctoral de costos (deuda QA 2026-05-07).

El gasto histórico (no per-key) queda en structlog/Loki como antes.

## 8. Archivos clave para entender el servicio

- `apps/ai-gateway/src/ai_gateway/routes/complete.py` — `/complete` y `/stream`. La función `complete()` tiene el flujo canónico: BYOK resolve → budget check → cache check → provider call → cache set → budget charge → `increment_usage()` (UPSERT sobre `byok_keys_usage`).
- `apps/ai-gateway/src/ai_gateway/routes/byok.py` — los 5 endpoints CRUD de BYOK keys.
- `apps/ai-gateway/src/ai_gateway/services/byok.py` — `resolve_byok_key()` (jerarquía materia → tenant → env_fallback, RN-132), `create_byok_key()`, `rotate()`, `revoke()`, `increment_usage()`.
- `apps/ai-gateway/src/ai_gateway/providers/base.py` — `BaseProvider` + `CompletionRequest`/`CompletionResponse` (esquema interno uniforme) + `MockProvider` + `AnthropicProvider` + **`MistralProvider`** (recovery del stash 2026-05-07 commit 7ecabf7; usa `mistralai>=1.0` SDK oficial; soporta `complete()` + `stream_complete()`; pricing per-modelo `mistral-small/medium/large/codestral`; verificado end-to-end con API real). `get_provider()` es el factory basado en env var. **Adapter Gemini sigue diferido** (no hay caso de uso piloto-1).
- `apps/ai-gateway/src/ai_gateway/services/budget_and_cache.py` — `BudgetTracker` (contabilidad atómica con `INCRBYFLOAT` de Redis) y `ResponseCache` (condicional a `temperature=0`).
- `apps/ai-gateway/src/ai_gateway/schemas/complete.py` — `CompleteRequest` con campo opcional `materia_id: UUID | None` ([ADR-040](../adr/040-byok-propagation.md)).
- `apps/ai-gateway/src/ai_gateway/config.py` — settings. `default_monthly_budget_usd = 100.0`. Secrets de provider (env_fallback). `BYOK_MASTER_KEY`.
- `packages/platform-ops/src/platform_ops/crypto.py` — helper compartido `encrypt(plaintext, master_key) → bytes` y `decrypt(ciphertext, master_key) → str` (AES-256-GCM).
- `apps/ai-gateway/tests/unit/test_budget_and_cache.py` — cubre budget exceeded, cache hit/miss, charge/check concurrencia.
- `apps/ai-gateway/tests/unit/test_byok.py` — resolver jerárquico, encrypt/decrypt roundtrip, usage tracking.
- `apps/ai-gateway/tests/unit/test_mock_provider.py` — contratos del esquema interno con el provider mock.

**Flujo del `POST /complete` — paso a paso** (`routes/complete.py:99`):

```
1. tracker = BudgetTracker(redis)
   cache   = ResponseCache(redis)

2. status = tracker.check(tenant_id, feature, limit)
   if status.exceeded:
       raise HTTPException(429, "Budget excedido...")

3. internal_req = CompletionRequest(messages, model, temperature, max_tokens)

4. cached = cache.get(internal_req)        ← solo hit si temperature=0
   if cached:
       return CompleteResponse(..., cache_hit=True, cost_usd=0.0)

5. provider = get_provider()               ← MockProvider | AnthropicProvider
   try:
       response = await provider.complete(internal_req)
   except Exception as e:
       raise HTTPException(502, f"LLM provider error: {e}")

6. cache.set(internal_req, response)       ← solo guarda si temperature=0
7. new_total = await tracker.charge(tenant_id, feature, response.cost_usd)

8. return CompleteResponse(
       content=response.content,
       input_tokens=...,
       output_tokens=...,
       cost_usd=response.cost_usd,
       cache_hit=False,
       budget_status={ "used_usd": new_total, ... }
   )
```

Los pasos 2 y 7 **no son atómicos entre sí** — entre el check y el charge puede haber otro request del mismo tenant consumiendo budget. El exceso puede ser de algunos USD. Gotcha conocido (Sección 9).

**Pricing table — `AnthropicProvider.PRICING`** (`providers/base.py:80`):

```python
PRICING = {
    "claude-sonnet-4-6": {"input": 3.0,  "output": 15.0},   # USD por 1M tokens
    "claude-haiku-4-5":  {"input": 0.8,  "output": 4.0},
    "claude-opus-4-7":   {"input": 15.0, "output": 75.0},
}
```

Fórmula de costo:

```python
cost = (input_tokens * pricing["input"] + output_tokens * pricing["output"]) / 1_000_000
```

Modelos fuera de la tabla caen a fallback `{"input": 1.0, "output": 5.0}` — defensivo pero inexacto; si aparece un modelo nuevo, actualizar la tabla.

**Canonicalización para la key del cache** (`services/budget_and_cache.py:83`):

```python
def _key(self, request: CompletionRequest) -> str:
    canonical = json.dumps(
        {
            "messages": request.messages,
            "model": request.model,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        },
        sort_keys=True,          # ← determinismo
        ensure_ascii=False,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"aigw:cache:{digest}"
```

La fórmula comparte la canonicalización de hashes del resto del repo (mismo `sort_keys`, `separators`, `ensure_ascii=False`). **Diferencia clave con el CTR**: acá el hash cubre **la request al LLM**, no un evento — es interno del gateway, no viaja al wire ni al CTR. Cambiar la canonicalización no rompe auditabilidad (sólo invalida el cache).

## 9. Configuración y gotchas

**Env vars críticas** (`apps/ai-gateway/src/ai_gateway/config.py`):

- `REDIS_URL` — default `redis://127.0.0.1:6379/1` (DB index 1, separada del CTR).
- `DEFAULT_MONTHLY_BUDGET_USD` — default `100.0`. En F4+ se prevé consultar [academic-service](./academic-service.md) por el límite específico del tenant/feature; hoy es único para todos.
- `ANTHROPIC_API_KEY`, `OPENAI_API_KEY` — por default vacías. Con providers reales activos y key vacía, el provider falla y el gateway devuelve 502.
- Factory selection por variable de entorno (`LLM_PROVIDER=mock` el default en dev) — asegura que el test suite no consume API keys reales.

**Puerto de desarrollo**: `8011`.

**Gotchas específicos**:

- **Regla cero: nadie llama directo a Anthropic/OpenAI**: RN-101 prohíbe `import anthropic` fuera de este servicio. Cualquier PR que lo introduzca en otro servicio debe rechazarse. Verificación: grep `import anthropic` por el repo, único match aceptable es `apps/ai-gateway/`.
- **Caché sólo con `temperature=0`**: con temperaturas >0 cada invocación puede diferir; cachear sería correctness-incorrect. La regla está codificada en `ResponseCache._is_cacheable()`. El tutor corre con `temperature=0.7` (`tutor_core.py:199`) — **no hay cache hit** para tutoría, deliberadamente.
- **Budget check no es atómico con el charge**: `check()` lee, `charge()` escribe; entre ambos otra request podría haber consumido. Es "soft" — el exceso puede ser de algunos USD. Para el piloto es tolerable; para prod multi-tenant a escala, considerar `INCR` atómico con rollback si el LLM call falla.
- **Costo estimado en streaming**: `event_stream()` calcula `est_cost = total_chars / 4 / 1_000_000 * 5.0` (~$5 por M output tokens). Es una aproximación grosera — el provider real (Anthropic) devuelve tokens exactos en el `usage` final del stream, pero esos no se capturan hoy. Si se quiere exactitud, el streaming tiene que exponer el `usage` al `event_stream` antes del `yield "done"`.
- **`feature` es string libre**: el request lleva `feature: str` ("tutor", "classifier", etc.) sin enum validado. Si un caller escribe `"Tutor"` vs `"tutor"`, son dos budgets distintos. Convención: minúsculas, snake_case. Verificable con `GET /budget` si algo huele mal.
- **Provider failures → 502**: si el provider crashea, el gateway no falla silencioso — devuelve 502 con el mensaje del provider. El caller (tutor) tiene que decidir qué hacer (retry, fallback, emitir evento de error al CTR). Hoy el tutor-service propaga el error al SSE como `{"type": "error"}`.
- **`INCRBYFLOAT` precision**: Redis devuelve el total como string decimal; el parseo a `float` puede perder precisión en el orden $10⁻⁹. Para USD es imperceptible; no es bug pero tampoco uses esto para cálculos contables con precisión exacta.
- **Pricing desactualizada**: la tabla en `providers/base.py` tiene precios de abril 2026. Si Anthropic actualiza precios, hay que editar el código y redesplegar — no hay config externa. PR separado cuando suba.
- **`BYOK_MASTER_KEY` rotation es ritual**: si la perdés, **TODAS** las keys BYOK quedan inservibles. Procedimiento de rotación de master key requiere re-encriptar el catálogo entero (5 pasos en ADR-038). En dev podés tener una local; en prod usar Vault/KMS. **NUNCA** la commitees ni la loguees.
- **`SET LOCAL ... :tid` no funciona en Postgres** (bug fixed en c8a4685): `apps/ai-gateway/src/ai_gateway/services/byok.py:121-124` usaba `text("SET LOCAL ... :tid")` con bind param — Postgres no acepta parametrizar `SET LOCAL`. Reemplazado por `text("SELECT set_config('app.current_tenant', :tid, true)")` que sí acepta bind. Smoke real confirmado: `GET /api/v1/byok/keys` → 200 (antes 500 silencioso porque tests mockeaban DB). Lección: **nunca** hagas `text("SET LOCAL ... :param")` con bind params.
- **`set_config(..., is_local=true)` muere con el commit**: bug latente fixed en c8a4685. `create_byok_key`, `rotate`, `revoke` hacían `commit() → refresh()` post-RLS. La RLS es transaction-scoped (`is_local=true`), entonces `refresh()` corría con tenant vacío y RLS bloqueaba con `invalid input syntax for type uuid: ""`. Fix: re-aplicar `_set_tenant_rls` antes de cada `refresh` post-commit en los 3 métodos. Cualquier futuro método que necesite `refresh()` post-commit con RLS debe replicar el patrón.
- **Resolver scope `facultad` declarado pero no implementado en piloto-1**: requiere lookup cross-DB (`materia_id` → `materia.carrera.facultad`), incompatible con sesiones por-base de ADR-003. Cache Redis del resolver es follow-up. Hoy el orden efectivo es **materia → tenant → env_fallback**; con `materia_id=None` (RN-040 dependiente del caller) → `resolved_scope="tenant_fallback_no_materia"`.
- **`byok_keys_usage` queda vacía cuando resolver cae a `env_fallback`**: gap declarado para auditoría doctoral de costos (deuda QA 2026-05-07).
- **UI BYOK page DEFERIDA en web-admin para v1.0** — endpoints CRUD están operables vía curl o cliente HTTP.

**Traceback — provider con API key vacía**:

```
ERROR ai_gateway.providers.base: provider_error
Traceback (most recent call last):
  File ".../ai_gateway/routes/complete.py", line 157, in complete
    response = await provider.complete(internal_req)
  File ".../ai_gateway/providers/base.py", line 95, in complete
    result = await client.messages.create(...)
anthropic.AuthenticationError: Error code: 401 - {'type': 'error', 'error': {'type': 'authentication_error', 'message': 'invalid x-api-key'}}

INFO: "POST /api/v1/complete HTTP/1.1" 502 Bad Gateway
{ "detail": "LLM provider error: Error code: 401 - ..." }
```

**Traceback — budget excedido**:

```
INFO: "POST /api/v1/stream HTTP/1.1" 429 Too Many Requests
{ "detail": "Budget excedido" }
```

El 429 corta **antes** de llamar al provider — el check del budget es el primer paso. No hay llamada fallida a Anthropic ni costo incurrido.

**Traceback — cache hit exitoso**:

El gateway no emite log distinto en cache hit (sólo `INFO cache_hit tenant=... feature=... model=...`). En Grafana se ve porque `cost_usd=0.0` y `cache_hit=true`. La ventana típica de hit rate en clasificación (temperature=0) es ~40% según el docstring.

## 10. Relación con la tesis doctoral

El ai-gateway no es un componente que la tesis describa en sus propios términos — no aparece en el Capítulo 6 como "servicio de X". Existe porque la tesis, y la operatividad del piloto, imponen tres restricciones que a nivel sistema sólo se cumplen con un proxy centralizado:

1. **Auditabilidad del provider** (Capítulo 7 de la tesis): cada evento `prompt_enviado`/`tutor_respondio` queda con su `prompt_system_hash` y los mensajes exactos — pero la identidad del proveedor (`"anthropic"` vs `"openai"` vs `"mock"`) y la versión del modelo sólo son trazables si hay un punto único que los registre. El ai-gateway lo hace: `CompletionResponse.provider` queda en logs estructurados + Grafana.

2. **Control de costos del piloto**: el protocolo UNSL tiene un presupuesto acotado. Si un bug en el tutor genera un loop infinito de prompts, el budget tracker detiene el sangrado a nivel tenant antes de que la factura se dispare. Es una condición operativa del convenio.

3. **Fallback y reproducibilidad**: [ADR-004](../adr/004-ai-gateway-propio.md) prevé que si un provider cae (ej. Anthropic outage), el gateway pueda rutear al otro. Para tests y análisis retrospectivo, el `MockProvider` determinista permite re-correr pipelines sin gastar en LLM real.

**Por qué `MockProvider` es determinista**: el test de la tesis debe poder re-correrse mil veces con la misma secuencia de eventos generada — sin pagar Anthropic por cada corrida. El mock toma la última `user message` y devuelve `"[mock respuesta para: {last[:50]}]"` — reproducible bit-a-bit. Esto permite que el `ctr-service` valide que sus hashes son deterministas sin acoplar los tests al mundo real.

**Por qué el budget es por `(tenant_id, feature)` y no sólo por `tenant_id`**: un universidad puede querer un presupuesto grande para `tutor` (uso masivo de estudiantes) y uno chico para `classifier` (batch job ocasional). Si se consolida en un solo budget, un experimento de clasificación mal configurado puede comerse el presupuesto del tutor y dejar a los estudiantes sin poder trabajar. La granularidad por feature es defensa operativa del uso académico.

**Por qué `temperature=0` es cacheable**: con `temperature=0`, el LLM devuelve la respuesta de máxima verosimilitud — estrictamente determinista para la misma input (con los modelos actuales; antes de `temperature=0` real había drift por sampling). Para el `classifier-service` (si migra a clasificación semántica), todas las llamadas serían `temperature=0` y el hit rate esperado sobre un dataset repetitivo sería alto. Para el tutor (`temperature=0.7`), cada llamada genera variación natural — cachear sería servir una respuesta "no socrática" repetida al mismo estudiante.

**Discrepancia declarada**: [ADR-004](../adr/004-ai-gateway-propio.md) menciona "fallback entre providers" como feature. Está arquitecturalmente previsto (el factory podría rotarse) pero no implementado hoy — `get_provider()` devuelve un único provider configurado, sin rollover automático en failure. La justificación para el piloto: Anthropic no ha tenido outages en el tiempo de desarrollo, y el fallback a OpenAI cambiaría el comportamiento del tutor (prompt optimizado para Claude). Pendiente de decisión operativa si el piloto lo exige.

## 11. Estado de madurez

**Tests** (2 archivos unit):
- `tests/unit/test_mock_provider.py` — contratos del esquema interno, roundtrip request/response, streaming.
- `tests/unit/test_budget_and_cache.py` — budget check/charge, TTL de 35 días, cache hit con `temperature=0`, miss con `temperature>0`.

**Known gaps**:
- Sin tests de integración con provider real (AnthropicProvider) — coverage del path prod es por smoke manual.
- Budget check-then-charge no es atómico (gotcha documentado).
- Costo en streaming estimado por longitud (no preciso). El `usage` real del provider en streaming está disponible pero no se captura.
- Fallback entre providers no implementado.
- Selection de modelo por feature flag vive en el caller (tutor), no acá. Coupling con el caller que podría reducirse si el gateway tuviera su propia config de defaults por tenant-feature.
- Pricing table hardcoded en código — actualización requiere deploy.
- `feature` sin enum validado — typos silenciosos dividen budgets.
- BYOK scope `facultad` declarado pero no implementado en piloto-1 (cache Redis follow-up).
- `byok_keys_usage` queda vacía con `env_fallback` (gap auditoría doctoral).
- UI BYOK page en web-admin DEFERIDA — endpoints operables vía curl o cliente HTTP.
- Adapter Gemini diferido (no hay caso de uso piloto-1).

**Fase de consolidación**:
- F3 — implementación inicial con mock provider (`docs/F3-STATE.md`).
- F4 — budget tracking + caché.
- F5+ — mTLS entre servicios internos (caller auth robusta), fallback entre providers (ADR-004), previstos no implementados.
- 2026-05-04 (epic `ai-native-completion-and-byok`) — BYOK multi-provider ([ADR-038](../adr/038-byok-encryption.md), [ADR-039](../adr/039-byok-resolver.md), [ADR-040](../adr/040-byok-propagation.md)), 5 endpoints CRUD, métricas OTLP. Mistral provider implementado.
- 2026-05-04 (epic `real-health-checks`) — `/health/ready` real con `check_postgres + check_redis + byok_resolver_healthy`.
- 2026-05-07 (post-stash recovery) — bug fix `SET LOCAL ... :tid` (commit c8a4685) y `set_config()` post-commit refresh.

**Recomendaciones operativas del piloto** (no documentadas formalmente):

1. Monitorear `GET /api/v1/budget?feature=tutor` en Grafana — alerta cuando `used_usd / limit_usd > 0.8`.
2. Correr el piloto con `LLM_PROVIDER=anthropic` + `DEFAULT_MONTHLY_BUDGET_USD` ajustado al presupuesto del convenio UNSL.
3. Para análisis retrospectivos (re-correr clasificación sobre episodios viejos), usar `LLM_PROVIDER=mock` salvo que la clasificación semántica se active — el mock es free y determinista.
4. Si Anthropic sube precios, actualizar `PRICING` en `providers/base.py` y deployar — el costo histórico queda con los precios del momento de la invocación (structlog persiste el valor, no una referencia).
