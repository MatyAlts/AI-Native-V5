# ADR-039 — BYOK: resolver jerárquico materia → facultad → tenant → env

- **Estado**: Aceptado
- **Fecha**: 2026-05
- **Deciders**: Alberto Cortez
- **Tags**: byok, scoping, fallback
- **Epic**: ai-native-completion-and-byok / Sec 5

## Contexto y problema

Una vez que las keys estan encriptadas en `byok_keys` (ADR-038), el
ai-gateway necesita decidir **que key usar** dado un request con
`(tenant_id, materia_id?, provider, feature)`. Hay multiples scopes
posibles: tenant-wide, facultad-wide, materia-specific. Y el caller puede
no pasar `materia_id` (legacy callers pre-migracion).

## Drivers de la decisión

- **Specificity wins**: si una materia tiene una key configurada, debe
  ganar sobre la facultad o el tenant.
- **Multi-provider simultaneo**: una facultad puede tener Anthropic Y
  Gemini activas a la vez (diferentes features usan diferentes providers).
  UNIQUE constraint debe ser `(tenant, scope, scope_id, provider)` —
  NO `(tenant, scope, scope_id)`.
- **Compatibilidad legacy**: callers que NO pasan `materia_id` deben
  seguir funcionando (fallback a tenant scope).
- **Fallback a env var**: si nada matchea, env legacy (`ANTHROPIC_API_KEY`)
  permite que dev y entornos sin BYOK configurado sigan funcionando.

## Decisión

Resolver jerarquico con 4 niveles:

```
Request: (tenant_id, materia_id?, provider, feature)
  ↓
1. byok_keys WHERE scope=materia, scope_id=materia_id, provider=X, revoked_at IS NULL
   ├─ HIT → desencriptar con BYOK_MASTER_KEY → usar
   └─ MISS ↓
2. byok_keys WHERE scope=facultad, scope_id=facultad_id, provider=X
   (facultad_id derivado de materia_id via cache Redis materia:{id}:facultad_id TTL 1h)
   ├─ HIT → usar
   └─ MISS ↓     ⚠️ DIFERIDO en piloto-1 (requiere lookup cross-DB Materia.facultad_id;
                    cache Redis es follow-up).
3. byok_keys WHERE scope=tenant, scope_id=NULL, provider=X
   ├─ HIT → usar
   └─ MISS ↓
4. Env var legacy (ANTHROPIC_API_KEY, GEMINI_API_KEY, etc.)
   ├─ HIT → usar (modo dev / fallback)
   └─ MISS → None (caller decide 503 "no provider available")
```

UNIQUE parcial: `(tenant_id, scope_type, scope_id, provider)` WHERE
`revoked_at IS NULL`. Permite multi-provider simultaneo por scope.

## Consecuencias

### Positivas

- Specificity wins: configuracion granular cuando se necesita.
- Multi-provider simultaneo: features distintas pueden usar providers
  distintos sin friction.
- Backward compat: callers sin `materia_id` siguen funcionando (fallback
  a tenant + env).
- Env fallback permite dev sin configurar BYOK.

### Negativas / trade-offs

- **Latency adicional ~5-20ms por request** (lookup DB). Mitigacion:
  cache Redis `resolved:{tenant}:{materia}:{provider}` TTL 5min — diferida
  a follow-up del piloto-1. Si la latencia degrada SSE del tutor,
  prioritizar la implementacion del cache.
- **Lookup de facultad_id desde materia_id requiere join cross-DB**
  (materia vive en academic_main, byok_keys tambien — pero el ai-gateway
  necesita mapping). Cache Redis `materia:{id}:facultad_id` TTL 1h
  resuelve esto — DIFERIDO en piloto-1, el resolver actual SALTA del
  scope=materia directo a scope=tenant.

### Neutras

- `BYOK_ENABLED=false` salta directo al env fallback (modo legacy).
- Si `BYOK_MASTER_KEY` no esta configurada, fallback a env (no podemos
  desencriptar lo que no tenemos master key para).

## Métricas (follow-up)

`byok_key_resolution_total{resolved_scope}` con valores `materia`,
`facultad`, `tenant`, `env_fallback`, `none`. Permite ver:
- Cuantos requests usan keys per-scope.
- Cuantos caen a env (callers legacy o setup incompleto).
- Cuantos resultan en 503 (configuracion ausente y env tampoco esta).

`byok_key_resolution_duration_seconds` (histogram) con SLO p99 < 50ms.

## Referencias

- Resolver: `apps/ai-gateway/src/ai_gateway/services/byok.py::resolve_byok_key`
- Endpoints CRUD: `apps/ai-gateway/src/ai_gateway/routes/byok.py`
- ADR-038 — Encriptacion at-rest.
- ADR-040 — `materia_id` propagation cross-service (input del resolver).
