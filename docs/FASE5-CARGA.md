# Fase 5 — Carga y escala (versión SEGURA: modelo de capacidad)

> **Artefacto Fase 5** del [`PLAN-AUDITORIA-RESILIENCIA.md`](PLAN-AUDITORIA-RESILIENCIA.md).
> 2026-06-04. ⚠️ **NO se corrió un load test real** (100 alumnos concurrentes) contra prod:
> sobre un VPS al 82% de RAM con el bug de pool de `analytics`, hacerlo podía OOMear la caja y
> voltear prod con alumnos en vivo. En su lugar: **modelo de capacidad** con los números reales
> medidos read-only.

## El número que manda: `max_connections = 100`

Medido en Postgres prod: **`max_connections = 100`** (el default, bajo). Uso actual en idle:
**8 conexiones**. Ese 100 es el techo **compartido por TODO el sistema** (1 solo Postgres, 4
DBs lógicas).

## La cuenta de saturación

| Fuente | Conexiones que consume |
|---|---|
| 7 servicios con pool sano (`pool_size=10` + `max_overflow=5`) | hasta **15 c/u** bajo carga → ~105 si todos saturan |
| **`analytics` (engine POR REQUEST)** | cada request abre un engine nuevo (pool 2–5) **×3 DBs**, sin compartir pool → **se acumula con la concurrencia** |

**El cuello no son los 100 alumnos — es Postgres a las ~100 conexiones.** Y el acelerador es
`analytics`: bajo carga, ~15–30 requests concurrentes de analytics pueden **solos** acercarse
al techo, además de los pools de los otros servicios.

## El punto de quiebre (predicho)

1. La concurrencia sube → `analytics` abre engines/pools por request → conexiones a Postgres
   trepan rápido.
2. Postgres llega a **100 conexiones** → rechaza nuevas (`FATAL: too many connections`).
3. Como **todos comparten ese Postgres**, el fallo NO es solo de analytics: **cae el sistema
   entero** (academic, ctr, classifier… todos sin conexión).
4. En paralelo, cada conexión cuesta RAM → con el host ya al 82%, sube el riesgo de **OOM**
   (que mata contenedores → reaparecen los bugs de Redis de la Fase 3). Doble penalización.

**Hipótesis de quiebre:** muy por **debajo** de 100 alumnos concurrentes si una fracción
dispara dashboards de analytics. El recurso que rompe primero: **conexiones de Postgres**
(seguido de RAM). CPU NO es el cuello.

## Qué arreglar antes de escalar

1. 🥇 **`analytics`: engine único a nivel módulo** (como ya hacen los otros 6 servicios). Mata
   la fuente principal de la tormenta de conexiones. Es EL fix de escala #1.
2. **Pooler de conexiones (PgBouncer)** delante de Postgres → desacopla "requests" de
   "conexiones físicas". Headroom real.
3. **Subir `max_connections`** con cuidado (cada una cuesta RAM; sin más RAM, PgBouncer es
   mejor que subir el número).
4. **HTTP pooling** (Fase 1) → reduce churn de conexiones en el plano HTTP también.

## ✅ RESULTADOS REALES (load test ejecutado 2026-06-05, ventana sin alumnos)

Target: `GET /api/v1/analytics/cohort/{id}/progression` (el endpoint que crea engine por
request y lee 3 DBs). Identidad de docente real. Carga desde httpx async.

| Concurrencia | Latencia p50 | Throughput | Conexiones PG | Errores |
|---|---|---|---|---|
| 1 (baseline) | **260 ms** | — | 8 / 100 | 0% |
| 20 | **2.5 s** (10×) | 8 req/s | ~16 | 0% |
| 50 | **6 s** | 8 req/s | **87 / 100** | 0% |
| **100** | **9 s** (max 18s) | 10 req/s | **96–98 / 100** | **🔴 49% (500)** |

**El punto de quiebre es real y está PROBADO:** a **~100 usuarios concurrentes** sobre un
solo endpoint de analytics, **la mitad de las requests fallan con 500** y la otra mitad espera
9–18 segundos. La causa: Postgres llega a su techo de **100 conexiones** (medido subiendo de
8 → 87 → 98 con la concurrencia), y el motor de `analytics` (engine por request) es lo que las
quema.

**Hallazgos extra:**
- **Throughput clavado en ~8 req/s** sin importar la concurrencia → hay un punto de
  serialización (CPU del cálculo de progression + crear/destruir engines). Sumar usuarios solo
  apila latencia, no procesa más rápido.
- **Recuperación:** al parar la carga, el sistema volvió solo a 260 ms / 200 OK. La
  degradación fue transitoria (no rompió nada permanente).
- **Está MUY por debajo de los "100 alumnos"** del objetivo: un solo dashboard de docente
  basta para tumbarlo. Con varios docentes mirando analytics a la vez, ya cruje.

## Veredicto Fase 5

🟠 **Frágil a escala, con causa raíz clara y acotada.** No es un problema difuso de "el
sistema es lento": es **un servicio (`analytics`) quemando conexiones** contra un techo bajo
(`max_connections=100`) en una DB compartida. Arreglado eso + un pooler, el salto a "100
alumnos" es realista. **Load test real pendiente para confirmar el número exacto (necesita
staging o ventana sin alumnos).**
