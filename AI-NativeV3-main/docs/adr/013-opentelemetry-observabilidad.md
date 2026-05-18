# ADR-013 — OpenTelemetry como estándar de observabilidad

- **Estado**: Aceptado
- **Fecha**: 2026-04
- **Deciders**: Alberto Cortez
- **Tags**: observabilidad, operación

## Contexto y problema

La plataforma tiene 12 servicios backend + 3 frontends + varias piezas de infraestructura. Para operarla necesitamos:

- Traces distribuidos (una request del frontend atraviesa 3-5 servicios; visibilidad de dónde se gasta el tiempo).
- Métricas por tenant/carrera/feature (indispensable para budgets de IA y SLOs).
- Logs estructurados correlacionables con traces.
- Alertas sobre degradación de SLO.
- Errores de runtime (con sourcemaps para frontends).

## Opciones consideradas

### Opción A — Stack propietario (Datadog, New Relic, Honeycomb)
Excelentes. Caros. Datos fuera del país. Descartado por costo en pilotaje.

### Opción B — Stack open source con vendor-lock-in (Elastic APM, etc.)
Funciona pero vendor-specific en instrumentación.

### Opción C — OpenTelemetry + Jaeger + Prometheus + Loki + Grafana + Sentry
OTel como estándar vendor-agnostic para instrumentación. Backends open source para storage y visualización.

## Decisión

**Opción C — OpenTelemetry end-to-end.**

Stack:

- **Instrumentación**: OpenTelemetry SDK en cada servicio Python y en los frontends.
- **Collector**: OpenTelemetry Collector como sidecar o DaemonSet.
- **Traces**: Jaeger (retención 7 días full, 90 días sampled).
- **Métricas**: Prometheus (30 días full, 1 año agregado).
- **Logs**: Loki (14 días operacionales, indefinido para logs de auditoría).
- **Unified UI**: Grafana.
- **Errores de runtime**: Sentry con sourcemaps para frontends.

Convenciones:

- Cada span lleva atributos `tenant_id`, `service.name`, `user.id` (pseudonimizado).
- Correlation ID propagado via W3C Trace Context headers.
- Logs en JSON con `trace_id` y `span_id` como campos.
- Métricas custom prefijadas por servicio (`academic_requests_total`, `ctr_events_persisted_total`).

## Consecuencias

### Positivas
- OTel es estándar abierto; migrar de backend es trivial (cambiar OTLP endpoint).
- Trace de un request completo de extremo a extremo (frontend → API gateway → tutor → ai-gateway → Anthropic → back).
- Métricas con labels `tenant_id` permiten slicing fine del uso.
- Grafana dashboards reproducibles vía JSON.

### Negativas
- Overhead operacional: corremos 5 servicios de observabilidad.
- Cada servicio debe inicializar OTel correctamente al arrancar (abstraído en `observability.py` común).
- Sampling en producción requiere configuración cuidadosa para no perder traces importantes pero tampoco saturar.

### Neutras
- Migración futura a DD/Honeycomb es viable manteniendo la instrumentación.

## Referencias

- [OpenTelemetry](https://opentelemetry.io/)
- `apps/*/src/*/observability.py` (bootstrap común)
- `infrastructure/helm/observability/` (stack completo)
