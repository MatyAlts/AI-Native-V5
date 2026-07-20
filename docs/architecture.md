# Arquitectura de la plataforma

La arquitectura completa está documentada en el documento formal
`plataforma-arquitectura.pdf` (o `.docx` / `.md`) generado junto con el
paquete de documentación del proyecto.

Este archivo es un pointer + resumen navegable dentro del repositorio.

## Resumen en un minuto

La plataforma se organiza en **dos planos desacoplados vía bus de eventos**
Redis Streams:

1. **Plano académico-operacional** — gestión tradicional de la universidad:
   identidad (Keycloak), dominio académico, evaluación con rúbricas,
   dashboards analíticos. Tecnologías maduras, patrones consolidados.

2. **Plano pedagógico-evaluativo** — núcleo de la tesis: tutor socrático con
   prompt versionado, CTR criptográficamente auditable (cadena SHA-256),
   clasificador N4 con tres dimensiones de coherencia. Propiedades
   auditables como condición de aceptabilidad académica.

## Multi-tenancy

Una instancia de la plataforma aloja múltiples universidades. Cada
universidad es un tenant aislado mediante **Row-Level Security de
PostgreSQL** ([ADR-001](./adr/001-multi-tenancy-rls.md)).

## Tres bases lógicas

Cuatro bases separadas con roles distintos ([ADR-003](./adr/003-separacion-bases-logicas.md), ver addendum 2026-04-21):

- `academic_main` — dominio académico, inscripciones, audit log, casbin policies
- `ctr_store` — eventos del CTR (append-only, criptográfico)
- `classifier_db` — classifications N4 (con `is_current` para reclasificaciones)
- `content_db` — materiales y chunks pgvector para RAG

Nota: ADR-003 original mencionaba `identity_store` (cinco bases) pero quedó sin uso. La pseudonimización vive en `packages/platform-ops/privacy.py` rotando `student_pseudonym` en `academic_main.episodes`. Resuelto en sesión 2026-04-21 (BUG-25 Option A).

## Identidad federada

Keycloak como IAM central con federación SAML/OIDC/LDAP al IdP
institucional de cada universidad ([ADR-002](./adr/002-keycloak-iam-federado.md)).

## Invocación de IA centralizada

Todas las llamadas a LLMs y embeddings pasan por `ai-gateway`
([ADR-004](./adr/004-ai-gateway-propio.md)) que provee budget por tenant,
observabilidad por feature, fallback entre proveedores y caché.

## Eventos y auditabilidad

- Bus de eventos: Redis Streams particionado ([ADR-005](./adr/005-redis-streams-bus.md))
- Clasificaciones: append-only con versionado ([ADR-010](./adr/010-append-only-clasificaciones.md))
- Prompt versionado: Git separado con GPG signing ([ADR-009](./adr/009-git-fuente-prompt.md))

## Servicios

12 servicios backend en Python (FastAPI + SQLAlchemy 2.0), 3 frontends
React, agrupados así:

**Plano académico**
- `identity-service` — wrapper Keycloak
- `academic-service` — CRUDs del dominio
- `enrollment-service` — integraciones con SIS institucional
- `evaluation-service` — rúbricas + corrección
- `analytics-service` — dashboards + agregados

**Plano pedagógico (núcleo de la tesis)**
- `tutor-service` — tutor socrático con streaming SSE
- `ctr-service` — persistencia del CTR con workers particionados
- `classifier-service` — N4 + tres coherencias
- `content-service` — ingesta + RAG
- `governance-service` — custodia del prompt versionado

**Transversales**
- `api-gateway` — auth + proxy
- `ai-gateway` — routing a LLMs con budget

**Frontends**
- `web-admin` — gestión institucional
- `web-teacher` — autoría y seguimiento
- `web-student` — resolución con tutor socrático

## Para profundizar

- [Plan detallado de 16 meses](./plan-detallado-fases.md)
- [ADRs completos](./adr/)
- Documento formal `plataforma-arquitectura.pdf` (con diagramas)
- Documento técnico `ai-native-n4-guia.pdf` (núcleo de la tesis)
