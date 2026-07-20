# ADR-004 — AI Gateway propio centralizado

- **Estado**: Aceptado
- **Fecha**: 2026-04
- **Deciders**: Alberto Cortez, director de tesis
- **Tags**: ai, costos, observabilidad

## Contexto y problema

La plataforma invoca LLMs y embeddings desde al menos cuatro servicios distintos (tutor, classifier, content para embeddings, evaluation para sugerencia de notas), con distintos modelos y distintas restricciones.

Hay tres riesgos sin un gateway centralizado:

1. **Costos descontrolados**: un bug o un uso abusivo puede quemar miles de USD en horas. Sin observabilidad por tenant, detectarlo lleva días.
2. **Credenciales esparcidas**: API keys en múltiples servicios = más superficie de leak.
3. **Falta de fallback**: si Anthropic tiene degradación, los servicios deberían poder rutear a OpenAI o a un modelo local, pero esa lógica duplicada es un desastre.

## Drivers de la decisión

- Observabilidad: saber exactamente cuánto gasta cada universidad en IA, por feature.
- Kill-switch: poder frenar un tenant que excede budget sin cambiar código de aplicación.
- Fallback entre proveedores: Anthropic → OpenAI → local si hay outage.
- Caché de respuestas idempotentes (clasificación con T=0).
- Credenciales centralizadas.

## Opciones consideradas

### Opción A — Cada servicio llama directo al proveedor
Simple, pero todos los problemas mencionados arriba.

### Opción B — Gateway propio (servicio `ai-gateway`)
Un servicio FastAPI que expone `POST /complete`, `POST /embed`, `POST /rerank`. Los servicios nunca hablan con Anthropic directamente.

### Opción C — Usar LiteLLM como proxy
LiteLLM es un proyecto open source que hace exactamente esto. Costo: adoptar sus convenciones y rezar que sigan manteniéndolo.

## Decisión

**Opción B — Gateway propio.**

El `ai-gateway` expone una API unificada para LLM completion, embeddings y re-ranking. Todos los demás servicios invocan al gateway.

Responsabilidades del gateway:

1. **Auth + extracción de tenant**: valida JWT, extrae `tenant_id` para imputar costos.
2. **Budget check**: consulta `ai_budgets` y rechaza si ya se excedió el mensual.
3. **Rate limiting**: token bucket por usuario y por tenant.
4. **Routing**: selecciona modelo (Sonnet/Haiku/GPT-4/etc.) por feature.
5. **Circuit breaker + retry**: si proveedor degradado, falla rápido o rutea a fallback.
6. **Caché**: respuestas idempotentes (`temperature=0`) se cachean por `hash(input+modelo)`.
7. **Logging**: cada invocación registra tokens in/out, latencia, tenant, feature, modelo.

## Consecuencias

### Positivas
- Observabilidad centralizada por tenant/carrera/feature/modelo.
- Credenciales de proveedor en un solo lugar.
- Fallback entre proveedores sin replicar código.
- Caché ahorra ~40% de invocaciones de clasificación (valor medido en pilotaje pyloto).
- Cambiar modelo por feature no requiere redeploys de los servicios consumidores.

### Negativas
- Punto central que requiere alta disponibilidad (SPOF si cae).
- Latencia adicional de 10-30 ms por request.
- Otro servicio a mantener (aunque es chico).

### Neutras
- LiteLLM puede adoptarse internamente si conviene en el futuro; la interfaz que exponemos a otros servicios la controlamos nosotros.

## Referencias

- `apps/ai-gateway/`
- `docs/plan-detallado-fases.md` → F3.2 (invocación desde tutor), F5.7 (budget enforcement)
