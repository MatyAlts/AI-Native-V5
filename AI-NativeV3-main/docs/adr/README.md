# Architecture Decision Records

Decisiones arquitectónicas significativas del proyecto. Formato [MADR](https://adr.github.io/madr/).

Cada ADR es inmutable una vez aceptado. Para revertir o cambiar una decisión, se crea un nuevo ADR que marca el anterior como "Superseded".

## Índice

| ID | Título | Estado | Fecha |
|---|---|---|---|
| [ADR-001](./001-multi-tenancy-rls.md) | Multi-tenancy por Row-Level Security | Aceptado | 2026-04 |
| [ADR-002](./002-keycloak-iam-federado.md) | Keycloak como IAM central con federación | Aceptado | 2026-04 |
| [ADR-003](./003-separacion-bases-logicas.md) | Separación de bases lógicas por plano | Aceptado | 2026-04 |
| [ADR-004](./004-ai-gateway-propio.md) | AI Gateway propio centralizado | Aceptado | 2026-04 |
| [ADR-005](./005-redis-streams-bus.md) | Redis Streams como bus de eventos | Aceptado | 2026-04 |
| [ADR-006](./006-fastapi-sqlalchemy.md) | FastAPI + SQLAlchemy 2.0 en backend | Aceptado | 2026-04 |
| [ADR-007](./007-react-tanstack-frontend.md) | React 19 + TanStack en frontends | Aceptado | 2026-04 |
| [ADR-008](./008-casbin-autorizacion.md) | Casbin para autorización fine-grained | Aceptado | 2026-04 |
| [ADR-009](./009-git-fuente-prompt.md) | Git como fuente de verdad del prompt | Aceptado | 2026-04 |
| [ADR-010](./010-append-only-clasificaciones.md) | Append-only para clasificaciones | Aceptado | 2026-04 |
| [ADR-011](./011-pgvector-rag.md) | pgvector para RAG en MVP | Aceptado | 2026-04 |
| [ADR-012](./012-monorepo-pnpm-uv.md) | Monorepo con pnpm workspaces + uv | Aceptado | 2026-04 |
| [ADR-013](./013-opentelemetry-observabilidad.md) | OpenTelemetry como estándar de observabilidad | Aceptado | 2026-04 |
| [ADR-014](./014-docker-k8s-deployment.md) | Docker Compose en dev, Kubernetes en prod | Aceptado | 2026-04 |
| [ADR-015](./015-blue-green-rolling-deploy.md) | Blue-green para servicios académicos, rolling para workers | Aceptado | 2026-04 |
| [ADR-016](./016-tp-template-instance.md) | TareaPracticaTemplate + instancia por comisión | Aceptado | 2026-04 |
| [ADR-017](./017-ccd-embeddings-semanticos.md) | CCD con embeddings semánticos (DIFERIDO Eje B) | Aceptado (diferido) | 2026-04 |
| [ADR-018](./018-cii-evolution-longitudinal.md) | CII evolution longitudinal por template_id | Aceptado | 2026-04 |
| [ADR-019](./019-guardrails-fase-a.md) | Guardrails Fase A: detección preprocesamiento adversaria | Aceptado | 2026-04 |
| [ADR-020](./020-event-labeler-n-level.md) | Etiquetador N1-N4 derivado en lectura | Aceptado | 2026-04 |
| [ADR-021](./021-external-integrity-attestation.md) | Registro externo Ed25519 para CTR | Aceptado | 2026-04 |
| [ADR-022](./022-tanstack-router-migration.md) | TanStack Router file-based + alertas predictivas + cuartiles | Aceptado | 2026-04 |
| [ADR-023](./023-override-temporal-anotacion-creada.md) | Override temporal de `anotacion_creada` en labeler v1.1.0 (G8a) | Aceptado | 2026-04 |
| [ADR-024](./024-prompt-kind-reflexivo-runtime.md) | `prompt_kind` reflexivo en runtime (DIFERIDO Eje B) | Aceptado (diferido) | 2026-04 |
| [ADR-025](./025-episodio-abandonado-beforeunload-timeout.md) | `EpisodioAbandonado` con beforeunload + worker timeout (G10-A) | Aceptado | 2026-04 |
| [ADR-026](./026-boton-insertar-codigo-tutor.md) | Botón "Insertar código del tutor" en web-student (DIFERIDO post-defensa) | Aceptado (diferido) | 2026-04 |
| [ADR-027](./027-g3-fase-b-postprocesamiento.md) | Guardrails Fase B: postprocesamiento + `socratic_compliance` (DIFERIDO Eje C) | Aceptado (diferido) | 2026-04 |
| [ADR-028](./028-desacoplamiento-instrumento-intervencion.md) | Desacoplamiento instrumento-intervención (DIFERIDO post-piloto-1) | Aceptado (diferido) | 2026-04 |

## Template

Nuevos ADRs usan [`_template.md`](./_template.md).
