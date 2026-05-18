# Grafana legacy — DEPRECADO

Este directorio fue archivado por el change OpenSpec
`grafana-dashboards-provisioned` (epic Día 5-6, 2026-05).

## Estado

Los dashboards aquí son **aspiracionales**: referencian métricas que **nunca
se emitieron** en el piloto:

- `ctr_episodes_opened_total`, `ctr_events_total`, `ctr_episode_duration_seconds`
  → ctr-service no tenía `MeterProvider` configurado (cero métricas custom).
- `http_server_duration_seconds_bucket`, `http_server_requests_total` →
  FastAPIInstrumentor estaba instrumentando trazas pero NO métricas (la
  versión instalada no recibía `meter_provider` argument).
- `ai_gateway_tokens_*`, `classifier_kappa_*` → idem, sin emisión.

Los paneles renderizaban pero todos los queries devolvían `No data`.

## Por qué se archivaron

`grafana-dashboards-provisioned` reemplazó este path por el canónico
**`infrastructure/grafana/provisioning/`** + agregó **instrumentación mínima**
en `packages/observability::setup_metrics()` para que las métricas que sí se
grafican efectivamente se emitan.

## Cómo migrar (si necesitás un dashboard de acá)

1. Identificá el panel del dashboard heredado que querés rescatar.
2. Verificá que la métrica que consume esté en el catálogo de
   `infrastructure/grafana/provisioning/dashboards/README.md` (sección
   "Métricas custom emitidas").
3. Si la métrica está como `pendiente`, hookeá el call site primero (ver
   `apps/<svc>/metrics.py`).
4. Copiá el panel JSON al dashboard nuevo correspondiente bajo el path
   canónico.

## Métricas que esperaban (referencia para futura instrumentación)

```
# CTR
ctr_episodes_opened_total
ctr_events_total
ctr_episode_duration_seconds_bucket
ctr_episodes_integrity_compromised_total

# HTTP (auto)
http_server_duration_seconds_bucket
http_server_requests_total

# AI gateway
ai_gateway_tokens_total
ai_gateway_request_duration_seconds_bucket
ai_gateway_budget_remaining_usd

# Classifier
classifier_kappa_rolling
classifier_classifications_total
classifier_ccd_orphan_ratio
classifier_cii_evolution_slope
```

NO BORRAR este `_archive/` sin coordinación — sirve como trazabilidad
histórica de qué se intentó antes de la instrumentación real.
