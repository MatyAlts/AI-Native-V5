# ADR-015 — Blue-green para servicios académicos, rolling para workers del CTR

- **Estado**: Aceptado
- **Fecha**: 2026-04
- **Deciders**: Alberto Cortez
- **Tags**: deployment, operación, ctr

## Contexto y problema

Los servicios de la plataforma tienen dos perfiles de deployment con necesidades distintas:

1. **Servicios HTTP del plano académico** (academic-service, evaluation-service, analytics-service, frontends): requests stateless con sesiones en cliente. Un deploy debe ser **atómico** y **reversible** rápidamente ante errores.

2. **Workers del CTR** (ctr-service): consumidores single-writer por partición del stream. Cambiar versión requiere handoff cuidadoso para no perder eventos ni romper la invariante de single-writer.

Ambos perfiles necesitan estrategia distinta.

## Opciones consideradas

### Opción A — Rolling update para todo (default K8s)
Los pods se reemplazan uno por uno. Simple pero:
- Durante el deploy conviven versiones N y N+1 sirviendo tráfico. Si hay cambio de contrato (improbable pero posible), puede haber errores transitorios.
- En workers del CTR, rolling es exactamente lo que queremos.

### Opción B — Blue-green para todo
Dos ambientes completos, switch atómico. Seguro pero caro (2x recursos durante el switch) y complejo para workers con conexiones persistentes.

### Opción C — Blue-green para servicios HTTP, rolling para workers
Mezcla pragmática.

## Decisión

**Opción C — Blue-green para servicios HTTP, rolling para workers del CTR.**

**Blue-green para servicios del plano académico**:

- Dos deployments etiquetados `version: blue` y `version: green`.
- Traefik (o el Service de K8s) rutea a uno.
- Deploy: se despliega la nueva versión al que está inactivo, se ejecutan smoke tests, se cambia el selector del Service atómicamente.
- Rollback: cambio de selector vuelve al estado anterior en segundos.

**Rolling update para workers del CTR**:

- 8 pods (uno por partición del stream).
- Cada uno se reinicia uno a la vez: el nuevo pod espera hasta que el anterior libere el lease (30s de grace period).
- `XCLAIM` transfiere mensajes pendientes sin procesar del pod anterior al nuevo.
- Invariante de single-writer por partición se preserva.

**Frontends**: archivos estáticos en CDN con atomic flip (upload a carpeta versionada + update de pointer).

## Consecuencias

### Positivas
- Rollback HTTP servicios en <30s (atomic selector flip).
- Workers del CTR sin pérdida de eventos ni violación de single-writer.
- Deploys a producción sin downtime percibido.

### Negativas
- Blue-green requiere 2x recursos durante el switch.
- Operacional: el equipo debe conocer la diferencia.
- Migraciones de DB deben ser backward-compatible: blue y green conviven brevemente y ambas versiones deben funcionar con el schema post-migración.

### Neutras
- Canary releases (una fracción de tráfico a la nueva versión) pueden agregarse después si se justifica.

## Referencias

- `infrastructure/helm/platform/templates/` (deployments con ambas estrategias)
- `.github/workflows/deploy.yml`
- ADR-005 (workers single-writer por partición)
