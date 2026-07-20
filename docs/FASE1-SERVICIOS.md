# Fase 1 — Auditoría servicio por servicio

> **Artefacto Fase 1** del [`PLAN-AUDITORIA-RESILIENCIA.md`](PLAN-AUDITORIA-RESILIENCIA.md).
> Auditoría 2026-06-04. Método: 1 deep-dive (`tutor`, `api-gateway`) + barrido transversal
> de los 3 patrones compartidos (HTTP, pool DB, arranque) sobre los 10 servicios.

## Veredicto por servicio

| Servicio | Pool DB | HTTP pool | Arranque | Veredicto | 🚩 principal |
|---|---|---|---|---|---|
| **api-gateway** | n/a | ❌ por-llamada | ✅ | ⚖️ Aceptable | SPOF + backend caído → **500 opaco** (sin 502/retry) |
| **tutor** | n/a (Redis) | ❌ por-llamada (14) | ✅ | ⚖️ Aceptable | HTTP sin pool; `governance` es hard-dep para abrir |
| **academic** | ✅ pool 10 | ❌ por-llamada (4) | ✅ | ✅ Sólido | — (el gate del 403 está bien) |
| **ctr** | ✅ pool 10 | n/a | ✅ | ⚠️ Frágil en *operación* | 534 MB + 81 eventos huérfanos |
| **classifier** | ✅ pool 10 | ❌ (1) | ✅ | ✅ Sólido | — |
| **content** | ✅ pool 10 | ❌ (1) | ✅ | ⚖️ Aceptable | MinIO por URL pública |
| **ai-gateway** | ✅ pool 5 | SDK (no httpx) | ✅ | ⚖️ Aceptable | lee `academic_main` (cruce de planos) |
| **analytics** | ❌❌ **engine por request** | n/a | ✅ | 🔴 **Frágil** | 48 `create_async_engine` / 28 `dispose()` → pool exhaustion |
| **evaluation** | ✅ pool 10 | n/a | ✅ | ✅ Sólido | — |
| **governance** | n/a | n/a | ✅ | ✅ Sólido | nodo hoja, sin deps |

## Los 3 titulares

1. 🔴 **`analytics` es el peor problema de escala.** Crea un engine+pool nuevo a Postgres
   **dentro de cada request** (en los route handlers) y lo destruye. Bajo carga ahoga a
   Postgres. Y lee 3 DBs. Es el flag del plan, confirmado y peor.
2. 🚩 **Nadie poolea HTTP** (0 clientes persistentes en todo el repo). Cada llamada
   inter-servicio abre y tira una conexión. Peor lugar: **api-gateway** (todo el tráfico) y
   **tutor** (14 llamadas). Tolerable con 30 alumnos; problema con 100.
3. 🟢 **Arranque limpio en los 10.** Nadie corre migraciones al boot, ningún startup
   bloquea. → Un reinicio de contenedor arranca limpio (base para el auto-curado).

## Detalle del deep-dive: `tutor-service`

- **Manejo de fallos pensado con criterio:** lo secundario degrada (fail-soft: guardrails,
  overuse, postprocess, datos de ejercicio, BYOK); lo primario explota a propósito (validar
  tarea con academic, prompt de governance, **escribir evento al CTR**). Eligieron
  **integridad sobre disponibilidad** — correcto para una tesis. Precio: un hipo de
  Redis/CTR le corta la acción al alumno.
- **Health bien diseñado:** `/health/ready` → crítico = Redis (503 si cae); downstreams HTTP
  = degraded, no muere.
- 17 archivos de test cubriendo el camino real.

## Hallazgo a verificar en Fase 2

El proxy de `api-gateway` hace `upstream.content` (buffer completo) antes de responder. Si el
**chat socrático SSE** pasa por ahí, podría bufferarse en vez de fluir token a token.

## Prioridad de remediación (escala)

1. `analytics` — sacar la creación de engine de los route handlers; engine único a
   nivel módulo con pool (como el resto de los servicios ya hacen).
2. HTTP pooling — cliente `httpx.AsyncClient` persistente reusado, empezando por
   `api-gateway` y `tutor`.
