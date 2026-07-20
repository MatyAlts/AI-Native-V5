# ops/k8s — manifiestos Kubernetes NO wireados

**Estado: diseño de referencia, no desplegado por nada.**

Estos 3 manifiestos no los referencia ningún pipeline: no están en el chart
Helm (`infrastructure/helm/platform/`, que solo tiene `backend-services.yaml`),
ni en `docker-compose.prod.yml`, ni en los workflows de CI. El deploy real del
piloto corre sobre EasyPanel con `docker-compose.prod.yml`.

Se conservan a propósito: describen operaciones que **no están cubiertas en
ningún otro lado del repo**. Borrarlos perdería el diseño, no duplicación.

| Archivo | Qué describe | Equivalente hoy |
|---|---|---|
| `ctr-integrity-checker.yaml` | CronJob que recorre la cadena CTR y marca `Episode.integrity_compromised=true` ante tampering (ADR-010, RN-039/RN-040) | Ninguno automatizado. La verificación existe on-demand vía `POST /api/v1/audit/episodes/{id}/verify` (ADR-031) desde el web-admin. |
| `backup-cronjob.yaml` | CronJob de backup de las 4 bases | `scripts/backup.sh` + `infrastructure/systemd/` (unit + timer). En EasyPanel hay que correrlo en un sidecar — ver `docs/VPS-DEPLOY.md`. |
| `canary-tutor-service.yaml` | Despliegue canary del tutor-service con Argo Rollouts (10% → análisis de métricas → promoción) | Ninguno. EasyPanel hace deploy directo sin canary. |

## Antes de usarlos

No están probados contra un cluster real. Si el piloto migra de EasyPanel a
Kubernetes, hay que revisarlos: los nombres de imagen, los secrets y los
namespaces asumen convenciones que pueden haber cambiado.

## Lo que se borró de `ops/`

En la limpieza de 2026-07-20 se eliminaron dos subcarpetas que **sí** estaban
duplicadas, con el reemplazo documentado en el propio código:

- `ops/grafana/_archive/` → reemplazado por `infrastructure/grafana/provisioning/`
  (ver comentario en `infrastructure/docker-compose.dev.yml:184-185`).
- `ops/prometheus/slo-rules.yaml` → portado a
  `infrastructure/observability/alerts/platform-critical.yml`
  (ver comentario en la línea 3 de ese archivo).

Se recuperan del historial si hicieran falta:

```bash
git log --oneline --diff-filter=D -- ops/grafana ops/prometheus
git checkout <commit-anterior> -- ops/grafana ops/prometheus
```
