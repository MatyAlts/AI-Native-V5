# ADR-040 — `materia_id` propagation cross-service en payload del ai-gateway

- **Estado**: Aceptado
- **Fecha**: 2026-05
- **Deciders**: Alberto Cortez
- **Tags**: cross-service, ai-gateway, byok, materia
- **Epic**: ai-native-completion-and-byok / Sec 6
- **Tipo**: BREAKING para callers internos (NO afecta contrato externo del gateway)

## Contexto y problema

ADR-039 definio el resolver jerarquico: para que la BYOK pueda elegir
una key con scope=materia, el ai-gateway necesita recibir `materia_id`
en el payload. Hoy los callers (`tutor-service`, `classifier-service`,
`content-service`) no lo mandan — solo `feature` + tenant_id (header).

Como propagar `materia_id` cross-service sin romper invariantes
existentes ni perder backward compatibility?

## Drivers de la decisión

- **No-breaking del contrato externo**: el `ai-gateway` no expone APIs
  publicas a frontends — los frontends pegan al api-gateway que rutea a
  tutor-service / classifier-service / etc. No hay que preocuparse de
  rompe-clientes externos. Solo callers internos.
- **Atomic rollout**: si todos los callers se actualizan en un PR atomico,
  no hay ventana donde el gateway recibe payloads sin `materia_id` en
  produccion. Pero los tests legacy y los staging environments pueden
  tardar en migrar.
- **Trazabilidad de fallback**: cuando un caller manda payload sin
  `materia_id`, el resolver cae al scope=tenant. Necesitamos saber
  cuantos requests caen ahi para detectar callers no-migrados.

## Decisión

1. **`materia_id` opcional en el schema del ai-gateway**:
   `CompleteRequest.materia_id: UUID | None = Field(default=None)`. Si esta
   presente, el resolver lo usa para scope=materia. Si esta ausente, el
   resolver salta directo a scope=tenant (no se rompe el flow).

2. **Propagar `materia_id` desde callers**:
   - `tutor-service` (`tutor_core.py::interact`): resolver `materia_id`
     desde `episode.problema_id → tarea_practica.comision_id →
     comision.materia_id`. Cache local del SessionState para evitar
     re-resolver por turno.
   - `classifier-service` (`pipeline.py`): si el classifier llama al LLM
     (no hoy, pero el spec lo declara), pasa `materia_id` resolviendo
     desde `Episode.comision_id`.
   - `content-service` (`embedding.py`): si genera embeddings via
     ai-gateway, pasa `materia_id` resolviendo desde el material que se
     esta indexando.
   - `academic-service` (`tarea_practica_service.py::generate`): pasa
     `materia_id` directo (es input del endpoint TP-gen).

3. **Metrica `byok_key_resolution_total{resolved_scope="tenant_fallback_no_materia"}`**:
   se incrementa cuando el resolver cae a tenant porque el caller NO
   mando `materia_id`. Permite detectar callers no-migrados en runtime.

## Consecuencias

### Positivas

- Backward compat: callers viejos siguen funcionando (cae a tenant scope).
- Forward compat: el dia que un caller empieza a mandar `materia_id`,
  el resolver elige la key con scope mas especifico automaticamente.
- Trazabilidad: la metrica detecta callers que no migraron.

### Negativas / trade-offs

- **Tests existentes pueden romper si mockean el ai-gateway con assertions
  estrictos sobre el payload**. Mitigacion: el campo es OPTIONAL — assertions
  estrictos sobre keys ausentes no fallan. Si fallan, agregar `materia_id`
  al fixture es trivial.
- **PR atomico requiere coordinacion**: en una sola release, los 4 callers
  + el schema del gateway. Aceptado — el scope de la epic ya es atomico.

### Neutras

- El `materia_id` opcional en el gateway permite hacer rollout incremental
  servicio-por-servicio. Solo el primer servicio que lo manda empieza a
  beneficiarse del scope=materia; los demas siguen funcionando con scope=tenant.

## Estado en piloto-1

**Implementado en piloto-1**:
- Schema del ai-gateway acepta `materia_id` opcional (`routes/complete.py`).
- `academic-service` (TP-gen) pasa `materia_id` (es input del endpoint).
- `AIGatewayClient` de `academic-service` (`services/ai_clients.py`) acepta
  el parametro.

**Diferido a follow-up**:
- `tutor-service`: requiere resolver `materia_id` desde `episode → tarea →
  comision → materia` y cachearlo en `SessionState`. Bug fix: el episodio
  ya tiene `comision_id`, basta agregar lookup cross-DB.
- `classifier-service` y `content-service`: no llaman al ai-gateway hoy
  con el patron de `complete` — el dia que lo hagan, agregan `materia_id`.

## Referencias

- Schema: `apps/ai-gateway/src/ai_gateway/routes/complete.py::CompleteRequest`
- Cliente academic: `apps/academic-service/.../services/ai_clients.py::AIGatewayClient`
- ADR-039 — Resolver jerarquico (consumidor de `materia_id`).
