# ADR-014 — Docker Compose en dev, Kubernetes en prod

- **Estado**: Aceptado
- **Fecha**: 2026-04
- **Deciders**: Alberto Cortez
- **Tags**: infraestructura, operación

## Contexto y problema

Necesitamos entorno de desarrollo local ligero y rápido de levantar, pero también un entorno productivo escalable capaz de correr con múltiples universidades, con alta disponibilidad, con upgrades sin downtime.

## Opciones consideradas

### Opción A — Docker Compose para todo (dev y prod)
Simple. Funciona para 1-2 universidades. Ops manual para scale-out.

### Opción B — Kubernetes para todo (incluyendo dev)
Paridad total dev/prod. Pesado para la laptop de un dev: 3-4 GB RAM adicionales solo para K8s.

### Opción C — Compose en dev, K8s en prod con Helm
Desarrollo ligero (1-2 GB RAM para toda la infra). Producción escalable.

## Decisión

**Opción C — Compose en dev, Kubernetes + Helm en prod.**

**Desarrollo local**:

- `infrastructure/docker-compose.dev.yml` levanta PostgreSQL, Keycloak, Redis, MinIO, observability stack.
- Los servicios Python corren en host con `uv run uvicorn ... --reload` para hot-reload.
- Los frontends corren con `pnpm dev` (Vite HMR).

**Producción**:

- `infrastructure/helm/platform/` — chart Helm único del monorepo, con subcharts por servicio.
- Cada servicio tiene su `values.yaml` con config específica por ambiente.
- HPA (Horizontal Pod Autoscaler) por servicio según CPU/memoria.
- PostgreSQL con operator (CloudNativePG o similar) para HA con réplicas read-only.
- Redis con Sentinel o cluster-mode.

## Consecuencias

### Positivas
- Dev local ligero (laptop de 16GB RAM opera cómodamente).
- Prod escalable con HA.
- Helm permite diffear entre ambientes antes de aplicar.
- Rollbacks con `helm rollback`.

### Negativas
- Paridad imperfecta: algo puede funcionar en Compose y fallar en K8s (service discovery, DNS, persistencia).
- Doble configuración: valores de env en Compose y en `values.yaml`.
- Equipo necesita conocer K8s para operar producción.

### Neutras
- Si en el futuro se justifica K3s local para paridad total, la migración es viable.

## Referencias

- `infrastructure/docker-compose.dev.yml`
- `infrastructure/helm/platform/`
