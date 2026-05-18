## ADDED Requirements

### Requirement: Tabla `byok_keys` con encriptación at-rest AES-GCM

El sistema SHALL persistir BYOK keys en una tabla `byok_keys` con columnas: `id` (UUID PK), `tenant_id` (UUID, RLS), `scope_type` (ENUM `tenant|facultad|materia`), `scope_id` (UUID, nullable cuando `scope_type=tenant`), `provider` (ENUM `anthropic|gemini|mistral|openai`), `encrypted_key` (BYTEA — AES-GCM ciphertext), `nonce` (BYTEA, 12 bytes), `auth_tag` (BYTEA, 16 bytes), `key_id` (string, hint público — primeros/últimos chars del plaintext), `created_at`, `created_by`, `revoked_at` (nullable), `last_used_at` (nullable), `monthly_budget_usd` (numeric, nullable). Constraint UNIQUE `(tenant_id, scope_type, scope_id, provider)`.

#### Scenario: RLS aísla keys por tenant

- **WHEN** un usuario con `tenant_id=A` consulta la tabla
- **THEN** SHALL ver solo keys con `tenant_id=A` aunque la tabla contenga keys de tenant B
- **AND** `make check-rls` SHALL pasar incluyendo esta tabla

#### Scenario: Constraint impide duplicados de scope+provider

- **WHEN** un admin intenta crear una segunda key Anthropic para `(tenant=X, facultad=Y)`
- **THEN** la DB SHALL rechazar con violación de UNIQUE
- **AND** el endpoint SHALL retornar `409 Conflict` con mensaje claro

### Requirement: Helper `crypto.py` en `packages/platform-ops` con AES-GCM

El sistema SHALL exponer `packages/platform-ops/src/platform_ops/crypto.py` con funciones puras `encrypt(plaintext: bytes, master_key: bytes) -> tuple[ciphertext, nonce, auth_tag]` y `decrypt(ciphertext, nonce, auth_tag, master_key) -> plaintext`. La master key SHALL leerse del env var `BYOK_MASTER_KEY` (32 bytes base64). El helper SHALL ser usado por TODOS los servicios que tocan BYOK keys — sin duplicar la lógica.

#### Scenario: Encriptación reversible

- **WHEN** se llama `encrypt(b"sk-ant-...", master)` y luego `decrypt(...)` con los mismos parámetros
- **THEN** SHALL recuperarse el plaintext exacto

#### Scenario: Tampering del ciphertext detectado

- **WHEN** el ciphertext o auth_tag se mutan en disco
- **THEN** `decrypt()` SHALL lanzar `InvalidTag` (de la lib `cryptography`)
- **AND** ningún plaintext SHALL retornarse

### Requirement: Resolver jerárquico `materia → facultad → tenant → env fallback`

El `ai-gateway` SHALL resolver la API key para cada llamada en este orden:
1. Si payload incluye `materia_id`: buscar `byok_keys` con `(tenant_id, scope_type=materia, scope_id=materia_id, provider)` no revocada.
2. Si no: derivar `facultad_id` desde `materia_id` (cache Redis `materia:{id}:facultad_id` TTL 1h) y buscar `(tenant_id, scope_type=facultad, scope_id=facultad_id, provider)`.
3. Si no: buscar `(tenant_id, scope_type=tenant, scope_id=NULL, provider)`.
4. Si no: usar env var legacy (ej. `ANTHROPIC_API_KEY`) — fallback compatible.
5. Si tampoco hay env var: retornar `503 No Provider Available` con mensaje claro.

#### Scenario: Materia con key específica

- **WHEN** se llama al gateway con `materia_id=M1` y existe key Anthropic en scope `materia=M1`
- **THEN** SHALL usarse esa key

#### Scenario: Materia sin key, facultad con key

- **WHEN** `materia_id=M2` no tiene key pero su facultad sí (Anthropic)
- **THEN** SHALL usarse la key de la facultad
- **AND** la métrica `byok_key_resolution_total{resolved_scope="facultad"}` SHALL incrementar

#### Scenario: Sin BYOK, fallback a env

- **WHEN** ningún scope tiene key Anthropic pero `ANTHROPIC_API_KEY` env var está seteada
- **THEN** SHALL usarse el env var
- **AND** la métrica `byok_key_resolution_total{resolved_scope="env_fallback"}` SHALL incrementar

### Requirement: Endpoints CRUD + rotate + revoke + test + usage

El sistema SHALL exponer en `ai-gateway` (o nuevo `byok-service` puerto 8013):

- `POST /api/v1/byok/keys` — crear (admin only). Body: `{ scope_type, scope_id, provider, plaintext_key, monthly_budget_usd? }`. SHALL validar la key llamando al provider con un request mínimo antes de persistir. SHALL retornar `key_id` + metadata (sin plaintext).
- `GET /api/v1/byok/keys?scope_type=&scope_id=` — listar (admin only). SHALL retornar metadata sin plaintext ni ciphertext.
- `POST /api/v1/byok/keys/{id}/rotate` — body `{ plaintext_key }`. SHALL re-encriptar y reemplazar `encrypted_key`/`nonce`/`auth_tag`. SHALL preservar `created_at`, `key_id` se refresca al nuevo plaintext.
- `POST /api/v1/byok/keys/{id}/revoke` — soft delete. SHALL setear `revoked_at=now()`. NO borrar la fila (auditoría).
- `POST /api/v1/byok/keys/{id}/test` — re-validar manualmente con request mínimo al provider.
- `GET /api/v1/byok/keys/{id}/usage` — retorna consumo del mes actual: `tokens_input_total`, `tokens_output_total`, `cost_usd`, `requests_count`, `budget_remaining_usd`.

#### Scenario: Crear key inválida es rechazada antes de persistir

- **WHEN** admin pega `POST /api/v1/byok/keys` con plaintext "sk-fake-no-existe"
- **THEN** el endpoint SHALL llamar al provider con un request mínimo
- **AND** ante 401 del provider SHALL retornar `400 Bad Request` con `{"error": "key_invalid", "provider_response": "..."}`
- **AND** la key NO SHALL persistirse

#### Scenario: Revoke preserva auditoría

- **WHEN** admin revoca una key con uso histórico
- **THEN** `revoked_at` SHALL setearse pero la fila persiste
- **AND** queries de usage histórico SHALL seguir funcionando

### Requirement: Budget per-key con enforce hard

Cada `byok_keys` row SHALL poder configurar `monthly_budget_usd` opcional. El gateway SHALL trackear `cost_usd` mensual por key vía métricas Prometheus (`byok_key_cost_usd_total{key_id, provider}`). Cuando `cost_usd >= monthly_budget_usd`, el gateway SHALL retornar `429 Budget Exceeded` para llamadas usando esa key — caller SHALL recibir error claro. El budget SHALL resetearse al primer día del mes (hora UTC).

#### Scenario: Budget cap hit

- **WHEN** una key tiene `monthly_budget_usd=10` y el costo acumulado del mes alcanza $10.05
- **THEN** la próxima llamada SHALL retornar `429`
- **AND** la métrica `byok_budget_exceeded_total{key_id}` SHALL incrementar

#### Scenario: Reset al primer del mes

- **WHEN** comienza un nuevo mes UTC
- **THEN** el contador SHALL resetearse y las llamadas SHALL volver a permitirse hasta el nuevo budget

### Requirement: Adapters Gemini + Mistral en `ai-gateway`

El gateway SHALL incluir adapters para Gemini (`google-generativeai` SDK) y Mistral (`mistralai` SDK), siguiendo la misma interfaz `Provider` que `AnthropicProvider` actual. Los adapters SHALL exponer `complete()`, `stream()`, `count_tokens()`, `embed()` (Gemini soporta nativamente; Mistral usa modelo embed dedicado). Pricing per-model SHALL persistirse en `packages/contracts/src/platform_contracts/ai_gateway/pricing.py` como dict estático con `{provider: {model: {input_per_mtok, output_per_mtok, embed_per_mtok}}}`. Versionado del dict SHALL bumpear con cada cambio de pricing del provider — comentario con fecha de la cotización.

#### Scenario: Llamada a Gemini retorna formato compatible

- **WHEN** se invoca `provider.complete()` con provider resuelto = Gemini
- **THEN** el response SHALL adherir al schema interno `CompletionResponse` (mismo que Anthropic)
- **AND** `tokens_input` y `tokens_output` SHALL extraerse de la response Gemini correctamente

### Requirement: Master key rotation procedimental (runbook, no ADR)

El sistema SHALL documentar la rotación de `BYOK_MASTER_KEY` en `docs/pilot/byok-key-rotation.md` con pasos concretos: generar nueva master key, re-encriptar todas las rows con script `scripts/rotate-byok-master.py` (lee con vieja, escribe con nueva, transactional por row), actualizar env var en infra, restart del gateway. El proceso SHALL preservar `key_id` (hint público) — solo cambia el ciphertext.

#### Scenario: Rotación deja todas las keys descifrables con master nueva

- **WHEN** se ejecuta `scripts/rotate-byok-master.py --old-master ENV_OLD --new-master ENV_NEW`
- **THEN** todas las keys SHALL re-encriptarse con la nueva master
- **AND** un test post-rotación con `decrypt()` usando la nueva master SHALL recuperar los plaintexts correctamente
- **AND** un test con la vieja master SHALL fallar con `InvalidTag`

### Requirement: `materia_id` propaga a todos los callers del ai-gateway

**BREAKING**: Todos los callers internos del `ai-gateway` (tutor-service, classifier-service, content-service) SHALL incluir `materia_id` en el payload. El gateway SHALL aceptarlo opcional inicialmente con warning structlog, luego required en una segunda iteración. La migración SHALL coordinarse en el mismo PR — no admite estado intermedio en producción.

#### Scenario: Caller sin materia_id emite warning

- **WHEN** un caller pega al gateway sin `materia_id` durante el período de transición
- **THEN** el gateway SHALL emitir warning structlog `byok_caller_missing_materia_id` con el caller
- **AND** SHALL fallback a resolución `tenant → env` (sin materia ni facultad)
