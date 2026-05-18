.PHONY: help init install dev dev-bootstrap test test-fast test-rls test-adversarial \
        test-e2e test-e2e-clean test-e2e-headed test-smoke test-smoke-local \
        lint lint-fix typecheck migrate migrate-new setup-dev-perms setup-rls-user clean clean-all \
        check-health check-rls check-claude-md generate-service seed-casbin seed-smoke eval-retrieval backup restore \
        onboard-unsl kappa progression export-academic generate-protocol status build check-tools

SHELL := /bin/bash
.DEFAULT_GOAL := help

# Detect tools
PYTHON := $(shell command -v python3.12 2>/dev/null || command -v python3 2>/dev/null)
UV     := $(shell command -v uv 2>/dev/null)
PNPM   := $(shell command -v pnpm 2>/dev/null)

# Env vars con defaults sensatos para dev
export EMBEDDER     ?= mock
export RERANKER     ?= identity
export STORAGE      ?= mock
export LLM_PROVIDER ?= mock


help: ## Muestra esta ayuda
	@awk 'BEGIN {FS = ":.*##"; printf "\nMonorepo de la plataforma AI-Native N4 - Tesis UNSL\n\nUso: make \033[36m<target>\033[0m\n\n"} \
	/^## / { gsub("^## ", ""); printf "\n\033[1m%s\033[0m\n", $$0 } \
	/^[a-zA-Z_-]+:.*?##/ { printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2 }' $(MAKEFILE_LIST)


## Bootstrap

check-tools: ## Verifica que las herramientas estén instaladas
	@test -n "$(PYTHON)" || (echo "python3.12 no encontrado" && exit 1)
	@test -n "$(UV)"     || (echo "uv no encontrado (pip install uv)" && exit 1)
	@test -n "$(PNPM)"   || (echo "pnpm no encontrado (npm i -g pnpm)" && exit 1)
	@command -v docker   >/dev/null || (echo "docker no encontrado" && exit 1)
	@echo "Todas las herramientas disponibles"

init: check-tools ## [Primera vez] Bootstrap end-to-end: infra + deps + migrate + seed
	@echo "==============================================="
	@echo "  Bootstrap end-to-end de la plataforma"
	@echo "==============================================="
	@$(MAKE) dev-bootstrap
	@$(MAKE) install
	@echo ""
	@echo "Esperando Postgres listo..."
	@until docker exec platform-postgres pg_isready -U postgres >/dev/null 2>&1; do sleep 1; done
	@$(MAKE) migrate
	@$(MAKE) setup-dev-perms
	@$(MAKE) setup-rls-user
	@$(MAKE) seed-casbin || true
	@echo ""
	@echo "==============================================="
	@echo "  Plataforma lista"
	@echo "==============================================="
	@echo ""
	@echo "Proximos pasos:"
	@echo "  - make dev       -> arrancar servicios + frontends"
	@echo "  - make test      -> correr suite completa"
	@echo "  - make status    -> ver estado de servicios"
	@echo ""

install: check-tools ## Instala dependencias Python + Node
	@echo "Python workspace..."
	$(UV) sync --all-packages
	@echo "Node workspace..."
	$(PNPM) install

dev-bootstrap: ## Levanta infraestructura local (postgres, keycloak, redis, grafana)
	docker compose -f infrastructure/docker-compose.dev.yml up -d
	@echo "Esperando servicios..."
	@sleep 8
	@echo "Infra lista"
	@echo "  - PostgreSQL:  localhost:5432"
	@echo "  - Keycloak:    http://localhost:8180  (admin/admin)"
	@echo "  - Redis:       localhost:6379"
	@echo "  - MinIO:       http://localhost:9001  (minioadmin/minioadmin)"
	@echo "  - Grafana:     http://localhost:3000  (admin/admin)"
	@echo "  - Prometheus:  http://localhost:9090"


## Desarrollo diario

dev: ## Arranca servicios + frontends en modo desarrollo
	$(PNPM) turbo dev

build: ## Buildea todos los paquetes
	$(PNPM) turbo build

status: ## Estado de los servicios
	@docker compose -f infrastructure/docker-compose.dev.yml ps 2>/dev/null || echo "Infra no levantada (make dev-bootstrap)"
	@echo ""
	@scripts/check-health.sh 2>/dev/null || echo "Algunos servicios no responden"


## Tests

test: ## Corre la suite completa de tests (Python + TS)
	$(UV) run pytest apps/*/tests/unit/ \
	    apps/academic-service/tests/integration/test_casbin_matrix.py \
	    packages/*/tests/
	$(PNPM) turbo test

test-fast: ## Solo tests Python (sin frontends) - iteracion rapida
	$(UV) run pytest apps/*/tests/unit/ \
	    apps/academic-service/tests/integration/test_casbin_matrix.py \
	    packages/*/tests/ -x

test-rls: ## Tests de aislamiento multi-tenant (requiere Postgres + usuario non-superuser)
	@# Default: app_runtime non-superuser/NOBYPASSRLS creado por `make setup-rls-user`.
	@# CRITICO: NO usar `postgres` aca — superuser bypassa RLS y los tests pasan
	@# en silencio sin verificar nada (CI miente sobre aislamiento multi-tenant).
	@if [ -z "$$CTR_STORE_URL_FOR_RLS_TESTS" ]; then \
	    export CTR_STORE_URL_FOR_RLS_TESTS="postgresql+asyncpg://app_runtime:app_runtime@localhost:5432/ctr_store"; \
	    echo "CTR_STORE_URL_FOR_RLS_TESTS no seteada; usando default app_runtime@localhost"; \
	fi; \
	CTR_STORE_URL_FOR_RLS_TESTS=$${CTR_STORE_URL_FOR_RLS_TESTS:-postgresql+asyncpg://app_runtime:app_runtime@localhost:5432/ctr_store} \
	    $(UV) run pytest packages/platform-ops/tests/test_rls_postgres.py -v

test-adversarial: ## Tests adversariales contra el tutor
	$(UV) run pytest -m "adversarial"

test-e2e: ## Suite Playwright (asume servicios + frontends + seed activos)
	$(PNPM) exec playwright test --config=tests/e2e/playwright.config.ts

test-e2e-clean: ## Re-seedea + corre la suite Playwright (DESTRUCTIVO sobre tenant demo)
	$(UV) run python scripts/seed-3-comisiones.py
	$(PNPM) exec playwright test --config=tests/e2e/playwright.config.ts

test-e2e-headed: ## Suite Playwright en modo headed --debug (inspeccion manual)
	$(PNPM) exec playwright test --config=tests/e2e/playwright.config.ts --headed --debug

test-smoke: ## Smoke E2E API contra stack already-up (12 servicios + DB seedeada)
	$(UV) run pytest tests/e2e/smoke/ -v -m smoke --tb=short --override-ini="testpaths="

test-smoke-local: seed-smoke ## Smoke E2E para piloto local: re-seedea + skipea integrity-attestation-service (:8012)
	SMOKE_SKIP_ATTESTATION_CHECK=1 $(UV) run pytest tests/e2e/smoke/ -v -m smoke --tb=short --override-ini="testpaths="


## Calidad

lint: ## Lint Python + TS
	$(UV) run ruff check .
	$(UV) run ruff format --check .
	$(PNPM) turbo lint

lint-fix: ## Lint con autofix
	$(UV) run ruff check --fix .
	$(UV) run ruff format .
	$(PNPM) turbo lint -- --fix

typecheck: ## Typecheck Python + TS
	$(UV) run mypy .
	$(PNPM) turbo typecheck


## Base de datos

migrate: ## Aplica migraciones pendientes en todas las bases
	@ACADEMIC_DB_URL="postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/academic_main" \
	CTR_DB_URL="postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/ctr_store" \
	CLASSIFIER_DB_URL="postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/classifier_db" \
	CONTENT_DB_URL="postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/content_db" \
	./scripts/migrate-all.sh

migrate-new: ## Nueva migracion. Uso: make migrate-new SERVICE=academic-service NAME=descripcion
	@test -n "$(SERVICE)" || (echo "Usar: make migrate-new SERVICE=<service> NAME=<descripcion>" && exit 1)
	@test -n "$(NAME)"    || (echo "Usar: make migrate-new SERVICE=<service> NAME=<descripcion>" && exit 1)
	cd apps/$(SERVICE) && $(UV) run alembic revision --autogenerate -m "$(NAME)"

setup-dev-perms: ## Otorga permisos a usuarios de servicio y configura GUC app.current_tenant
	@bash ./scripts/setup-dev-permissions.sh

setup-rls-user: ## Crea usuario app_runtime non-superuser/NOBYPASSRLS para tests de RLS
	@bash ./scripts/setup-rls-test-user.sh

seed-casbin: ## Carga la matriz Casbin en la DB
	cd apps/academic-service && $(UV) run python -m academic_service.seeds.casbin_policies

seed-smoke: ## Seed idempotente con UUIDs canónicos para `make test-smoke-local`
	$(UV) run python scripts/seed-smoke.py

backup: ## Backup manual de las 3 bases
	@test -n "$$PG_BACKUP_PASSWORD" || (echo "Setear PG_BACKUP_PASSWORD" && exit 1)
	./scripts/backup.sh

restore: ## Restore desde backup. Uso: make restore DIR=/path/to/backup
	@test -n "$(DIR)" || (echo "Usar: make restore DIR=<path>" && exit 1)
	./scripts/restore.sh $(DIR)


## Onboarding de tenants

onboard-unsl: ## Onboarding UNSL (Keycloak + LDAP + feature flags)
	@test -n "$$KEYCLOAK_ADMIN_PASSWORD" || (echo "Setear KEYCLOAK_ADMIN_PASSWORD" && exit 1)
	$(UV) run python examples/unsl_onboarding.py


## Analisis del piloto

kappa: ## Analisis Kappa via analytics-service. Uso: make kappa FILE=ratings.json
	@test -n "$(FILE)" || (echo "Usar: make kappa FILE=<ratings.json>" && exit 1)
	curl -s -X POST http://localhost:8005/api/v1/analytics/kappa \
	    -H "Authorization: Bearer $${TOKEN:-dev-token}" \
	    -H "Content-Type: application/json" \
	    --data @$(FILE) | $(PYTHON) -m json.tool

progression: ## Progresion longitudinal. Uso: make progression COMISION=<uuid>
	@test -n "$(COMISION)" || (echo "Usar: make progression COMISION=<uuid>" && exit 1)
	curl -s http://localhost:8005/api/v1/analytics/cohort/$(COMISION)/progression \
	    -H "Authorization: Bearer $${TOKEN:-dev-token}" | $(PYTHON) -m json.tool

export-academic: ## Export academico. Uso: make export-academic COMISION=<uuid> SALT=<salt-16+>
	@test -n "$(COMISION)" || (echo "Usar: make export-academic COMISION=<uuid> SALT=<salt>" && exit 1)
	@test -n "$(SALT)"     || (echo "Usar: make export-academic COMISION=<uuid> SALT=<salt>" && exit 1)
	@curl -s -X POST http://localhost:8005/api/v1/analytics/cohort/export \
	    -H "Authorization: Bearer $${TOKEN:-dev-token}" \
	    -H "Content-Type: application/json" \
	    -d '{"comision_id":"$(COMISION)","salt":"$(SALT)","period_days":90}' \
	    | $(PYTHON) -m json.tool

generate-protocol: ## Regenera el DOCX del protocolo del piloto
	@command -v node >/dev/null || (echo "node no encontrado" && exit 1)
	cd docs/pilot && node generate_protocol.js
	@echo "Generado: docs/pilot/protocolo-piloto-unsl.docx"

generate-teacher-guide: ## Regenera el DOCX de la guia de capacitacion docente
	@command -v node >/dev/null || (echo "node no encontrado" && exit 1)
	cd docs/pilot && node generate_teacher_guide.js
	@echo "Generado: docs/pilot/guia-capacitacion-docente.docx"

generate-docs: generate-protocol generate-teacher-guide ## Regenera los DOCX del piloto (protocolo + guia docente)


## Utilidades

eval-retrieval: ## Evalua calidad del retrieval RAG contra golden queries
	$(UV) run python scripts/eval-retrieval.py docs/golden-queries/programacion-2.yaml

check-health: ## Verifica /health de todos los servicios
	@scripts/check-health.sh

check-rls: ## Verifica que toda tabla con tenant_id tenga RLS policy
	$(UV) run python scripts/check-rls.py

check-claude-md: ## Detecta drift numerico entre claims del CLAUDE.md y el codigo
	$(PYTHON) scripts/check-claude-md.py

generate-service: ## Crea nuevo servicio Python. Uso: make generate-service NAME=my-service
	@test -n "$(NAME)" || (echo "Usar: make generate-service NAME=<service-name>" && exit 1)
	scripts/generate-service.sh $(NAME)


## Limpieza

clean: ## Limpia artefactos Python/TS locales
	find . -type d \( -name "__pycache__" -o -name ".ruff_cache" \
	    -o -name ".mypy_cache" -o -name ".pytest_cache" -o -name ".hypothesis" \
	    -o -name "dist" -o -name ".turbo" -o -name ".vite" \) -exec rm -rf {} + 2>/dev/null || true
	@echo "Caches limpios (infra intacta)"

clean-all: ## Limpia TODO incluyendo contenedores y volumenes
	@$(MAKE) clean
	docker compose -f infrastructure/docker-compose.dev.yml down -v
	@echo "Limpieza completa (infra destruida)"
