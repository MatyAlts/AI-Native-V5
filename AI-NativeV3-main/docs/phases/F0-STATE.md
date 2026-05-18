# Estado del repositorio — F0 completado

Este documento describe qué está implementado en la versión actual del
repositorio semilla (fase F0 del plan de desarrollo).

## Qué está en verde ✓

### Estructura y tooling

- Monorepo con **pnpm workspaces** + **uv workspaces** + **turborepo**.
- `Makefile` con comandos estandarizados (`make dev`, `make test`, `make migrate`, etc.).
- Lint y format configurados (Ruff, mypy strict, Biome).
- `.editorconfig`, `.gitignore`, `.env.example`, `.vscode/` recomendados.
- `CONTRIBUTING.md` con convenciones + template de PR.

### 15 ADRs completos

Todos los ADRs fundamentales documentados en formato MADR en `docs/adr/`:

1. Multi-tenancy por Row-Level Security
2. Keycloak como IAM central con federación
3. Separación de bases lógicas por plano
4. AI Gateway propio centralizado
5. Redis Streams como bus de eventos
6. FastAPI + SQLAlchemy 2.0 en backend
7. React 19 + TanStack en frontends
8. Casbin para autorización fine-grained
9. Git como fuente de verdad del prompt
10. Append-only para clasificaciones
11. pgvector para RAG en MVP
12. Monorepo con pnpm + uv
13. OpenTelemetry como estándar de observabilidad
14. Docker Compose en dev, Kubernetes en prod
15. Blue-green para servicios HTTP, rolling para workers

### 12 servicios backend Python

Todos con scaffolding completo (`apps/<service>/`):

| Servicio | Puerto | Dependencias específicas |
|---|---|---|
| api-gateway | 8000 | httpx |
| identity-service | 8001 | python-keycloak |
| academic-service | 8002 | alembic, asyncpg |
| enrollment-service | 8003 | pandas |
| evaluation-service | 8004 | jsonschema, weasyprint |
| analytics-service | 8005 | strawberry-graphql |
| tutor-service | 8006 | sse-starlette, anthropic |
| ctr-service | 8007 | alembic, asyncpg |
| classifier-service | 8008 | scikit-learn, sentence-transformers |
| content-service | 8009 | unstructured, tree-sitter, pgvector |
| governance-service | 8010 | gitpython |
| ai-gateway | 8011 | anthropic, openai, tenacity |

Cada uno tiene:
- `pyproject.toml` con dependencias base + específicas
- `Dockerfile` multi-stage con `distroless` como runtime
- `main.py` con FastAPI + lifespan manager
- `config.py` con Pydantic Settings
- `observability.py` con OpenTelemetry + structlog
- `routes/health.py` con `/health/live` y `/health/ready`
- `tests/test_health.py` con 3 tests básicos
- `README.md` propio

### 3 frontends React

- `web-admin` (puerto 5173)
- `web-teacher` (puerto 5174)
- `web-student` (puerto 5175)

Cada uno con React 19 + Vite 6 + TanStack + Tailwind v4 + Biome,
stub que se conecta a `/api/` y muestra el estado.

### 5 packages compartidos

- **`@platform/contracts`** — 12 eventos CTR + 5 eventos académicos,
  esquemas Python (Pydantic) + TypeScript (Zod), helpers SHA-256 con tests.
- **`@platform/ui`** — design system base (Button, Card, Badge, Input, Label).
- **`@platform/auth-client`** — Keycloak integration con hooks React.
- **`@platform/ctr-client`** — captura con debounce + sendBeacon + IndexedDB fallback.
- **`@platform/test-utils`** — fixtures pytest, verificadores RLS, factories.

### Infraestructura

- `docker-compose.dev.yml` con **9 servicios de infraestructura**:
  PostgreSQL 16 (pgvector), Keycloak 25, Redis 7, MinIO, OTel Collector,
  Jaeger, Prometheus, Loki, Grafana.
- Script SQL de inicialización de las **3 bases lógicas** con usuarios separados.
- Helper SQL `apply_tenant_rls()` centralizado (ADR-001).
- Template de realm Keycloak `demo_uni` con 3 usuarios de prueba (admin, docente, estudiante).
- Helm chart base para producción (`infrastructure/helm/platform/`).
- Terraform stub (decisión de cloud provider pospuesta a F5).

### CI/CD

- `.github/workflows/ci.yml` con jobs de lint, typecheck (Python + TS),
  unit tests, integration tests, RLS isolation tests, migrations dry-run,
  build de imágenes Docker con cache, security scan con Trivy.
- `.github/workflows/deploy.yml` con deploy automático a staging y deploy
  manual con approval a producción.
- `.github/dependabot.yml` para updates automáticos.
- PR template que enforza checklist.

### Scripts de soporte

- `scripts/check-health.sh` — verifica los 15 endpoints `/health`.
- `scripts/check-rls.py` — verifica policies RLS en todas las bases.
- `scripts/smoke-tests.sh` — post-deploy validation.
- `scripts/check-staging-stability.sh` — gate pre-producción.
- `scripts/generate-service.sh` — crea nuevo servicio desde template.
- `scripts/generate_python_services.py` — generador usado en F0 (reutilizable).
- `scripts/generate_frontends.py` — generador de frontends.

## Qué está verificado funcionalmente ✓

- ✅ Los schemas Pydantic de eventos CTR se instancian correctamente.
- ✅ El hash SHA-256 es determinista (mismo evento → mismo hash).
- ✅ El genesis hash funciona como prev del primer evento.
- ✅ La cadena de 2+ eventos se verifica como íntegra.
- ✅ La manipulación de un evento es detectada por `verify_chain_integrity`.

## Qué está stub (F1+) ⚠️

- Los 12 servicios responden a `/health` pero no tienen lógica de negocio.
- Las migraciones Alembic están configuradas pero vacías.
- Los frontends muestran el estado del API pero no implementan login ni CRUDs.
- Keycloak realm está definido pero el flujo completo de login desde el
  frontend al backend autenticado se prueba end-to-end en F1.
- Los tests unitarios cubren lo mínimo (`/health`). Coverage significativo
  llega con la lógica de cada fase.

## Cómo validar localmente

```bash
# Instalar requisitos (una sola vez)
# ver docs/onboarding.md

git clone <repo>
cd platform
cp .env.example .env
make dev-bootstrap    # levanta infra
make install          # instala deps Python + Node
make migrate          # no-op en F0
make dev              # arranca los 15 apps

# En otra terminal
make check-health     # debe mostrar todos ✓
make test             # corre tests unitarios
```

## Próximos pasos

El plan completo está en `docs/plan-detallado-fases.md`. Resumen:

- **F1 (meses 3-4)**: dominio académico completo, matriz de permisos con Casbin.
- **F2 (meses 5-6)**: ingesta multi-formato, RAG con pgvector + re-ranker.
- **F3 (meses 7-10)**: motor pedagógico — CTR criptográfico, tutor socrático,
  frontend del estudiante, clasificador N4. La fase más densa.
- **F4 (meses 11-12)**: rúbricas, corrección asistida, dashboards productivos.
- **F5 (meses 13-14)**: federación institucional real, SIS, provisioning.
- **F6 (meses 15-16)**: hardening, validación Kappa, rollout piloto.
