# Fase 3 — Resiliencia / caos (versión SEGURA, sin romper prod)

> **Artefacto Fase 3** del [`PLAN-AUDITORIA-RESILIENCIA.md`](PLAN-AUDITORIA-RESILIENCIA.md).
> 2026-06-04. ⚠️ **NO se ejecutó caos real** (matar Redis / reiniciar servicios) porque NO
> hay staging y prod tiene alumnos en vivo. En su lugar: auditoría de la **config de
> reconexión + restart**, que predice el comportamiento sin causar la caída.

## Cómo reacciona a cada caída (predicho del código + config)

| Escenario | ¿Se cura solo? | Evidencia |
|---|---|---|
| **Servicio crashea (proceso muere)** | ✅ Sí | Docker restart policy reinicia + arranque limpio (Fase 1) |
| **Postgres se reinicia** | ✅ Sí | `pool_pre_ping=True` en academic/classifier/content/ctr/evaluation → detecta conexión muerta y la reemplaza |
| **Redis se reinicia / cambia DNS** | ❌ **No** | **Cero config de reconexión** (sin `retry`, `health_check_interval`, reconnect) en todo el repo → la conexión queda rota |
| **Servicio "vivo pero roto"** (ej. Redis caído, sirviendo 503) | ❌ **No** | **No hay healthcheck en EasyPanel** que reinicie por `/health` fallando → queda colgado hasta redeploy manual |

## El hallazgo central

**El incidente del 2026-06-04 no fue mala suerte — es el comportamiento esperado del sistema.**
Dos agujeros de auto-curado se combinan:

1. 🚩 **Redis no se reconecta solo.** Los clientes Redis no tienen `retry_on_timeout` ni
   `health_check_interval`. Tras un restart de Redis (o un cambio de DNS del contenedor), la
   conexión pooleada queda muerta. Por eso el tutor necesitó **redeploy**, no le alcanzó
   *restart*.
2. 🚩 **EasyPanel no reinicia por health.** No hay healthcheck configurado, así que un
   contenedor "vivo pero roto" (proceso arriba, dependencia caída) no se reinicia solo. Docker
   solo reinicia si el proceso **muere**; si sigue corriendo y sirviendo errores, queda así.

**Lo bueno:** Postgres sí se auto-cura (pre_ping), y un crash duro sí reinicia. El agujero es
la combinación "Redis hipa + contenedor no muere".

## Qué arreglar (para el auto-curado que te preocupaba)

1. **Reconexión Redis:** agregar `retry_on_timeout=True` + `health_check_interval=30` +
   `Retry(...)` a los clientes Redis. Esto solo ya hubiera evitado el incidente.
2. **Healthcheck en EasyPanel:** configurar `/health/ready` como healthcheck con reinicio
   automático, así un contenedor roto se reinicia solo a las 3am sin que estés despierto.
3. `pool_pre_ping=True` también en `ai-gateway` (hoy no lo tiene y usa `academic_main`).

## ✅ CAOS REAL EJECUTADO (2026-06-05, ventana sin alumnos) — corrige la predicción

Experimento: **Stop de Redis → observar → Start → ¿recupera solo?**

| Momento | tutor | ctr | classifier |
|---|---|---|---|
| Redis caído | **503 error** | 503 | 503 |
| Redis revivido (a los ~9s) | **200 ready** | 200 ready | 200 ready |

**RESULTADO: todos los servicios se auto-recuperaron solos, sin redeploy, en ~9 segundos.**

⚠️ **Esto CORRIGE la predicción de arriba.** Yo había predicho "zombi, necesita redeploy"
basándome en "no hay config de reconexión". **Estaba equivocado:** `redis-py` reconecta solo
en el siguiente comando (comportamiento default), así que un restart limpio de Redis se cura
solo. <strong>Es justo el valor de romper de verdad en vez de teorizar.</strong>

**Entonces, ¿qué fue el incidente?** No un restart limpio. El `gaierror` es un fallo de
**resolución DNS** — un bicho más feo (probablemente Redis con IP nueva tras un *redeploy*, o
DNS fallando bajo presión de RAM/OOM). Ese modo de fallo NO se reproduce con un Stop/Start
simple. Queda como hipótesis a investigar (redeploy de Redis + presión de memoria).

**Integridad post-caos:** tras el Stop de Redis + el load test de 100 concurrentes, la cadena
CTR quedó **idéntica** (567 eventos, 42 genesis, 0 eslabones rotos). El caos NO corrompió datos.

**Dato extra:** `ai-gateway` reporta `degraded` de forma persistente (antes y después del
test) — su check de Redis falla. Pre-existente, a revisar.

## Veredicto Fase 3 (actualizado)

🟡→🟢 **Más resiliente de lo que el código sugería.** Se auto-cura de: crash, restart de
Postgres **y restart de Redis** (esto último, mejor que lo predicho). El agujero real es más
angosto: el modo `gaierror`/DNS del incidente (no reproducido aún) + la ausencia de healthcheck
que reinicie un contenedor "vivo pero roto". Recomendaciones (healthcheck + retry explícito de
Redis) siguen siendo válidas como cinturón de seguridad, pero la urgencia baja.

## Veredicto Fase 3 (original, predicho — conservado para trazabilidad)

🟠 **Frágil en recuperación.** Se cura de lo simple (crash, Postgres) pero NO de lo que
realmente pasó (Redis + contenedor zombi). Es arreglable con 2 cambios de config acotados, sin
rediseño. **Test de caos real pendiente hasta tener staging.**
