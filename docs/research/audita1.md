# Auditoría AI-Native N4 — Estado de Desarrollo

**Fecha**: 2026-05-10
**Repositorio**: `C:\ana Garis\AI-NativeV3-main (4)\AI-NativeV3-main\`
**Contexto**: Plataforma AI-Native N4, tesis doctoral UNSL (Cortez) — "Modelo AI-Native con Trazabilidad Cognitiva N4 para la Formación en Programación Universitaria"
**Alcance**: inventario de avance, brechas vs spec/tesis, calidad de código y arquitectura, cobertura de tests + CI

> ## ⚠️ Errata — falsos positivos detectados durante ejecución del plan (2026-05-10)
>
> Al ejecutar las acciones del plan derivado de este audit (ver `plan-accion.md`), se descubrió que varios "issues" reportados acá NO son problemas reales. Quedó constancia para que futuras lecturas no persigan fantasmas:
>
> | Item del audit | Realidad | Causa |
> |----------------|----------|-------|
> | "HelpButton ausente en 6/12 views de web-teacher" (sec. 3.3, 3.5, 6) | **Falso**. Las 6 views (EpisodeNLevelView, StudentLongitudinalView, CohortAdversarialView, CorreccionesView, UnidadesView, KappaRatingView) usan `<PageContainer helpContent={...}>` que **embebe HelpButton internamente** (`packages/ui/src/components/PageContainer.tsx:59`). | El audit hizo grep por import directo de `HelpButton` y no detectó el pattern B (PageContainer). CLAUDE.md tenía nota desactualizada que reforzaba el falso positivo. |
> | "MarkdownRenderer duplicado en web-student + web-teacher" (sec. 3.5, 9.3) | **Falso**. Ya está consolidado en `@platform/ui` (`packages/ui/src/components/MarkdownRenderer.tsx`). Los 4 sitios consumidores importan de ahí. | El audit citó CLAUDE.md, que tenía la nota desactualizada. |
> | "integrity-attestation-service 🟡 parcial sin documentación" (sec. 2.1) | Madurez **subestimada**. El servicio tiene 61 tests reales (2 E2E con testcontainers Redis), worker consumer, journal con rotación diaria, failsafe contra dev key en prod, DLQ con retry. Doble path de ingest no documentado: HTTP `POST /api/v1/attestations` + worker Redis Stream. | El audit infirió "parcial" por ausencia de README. README ya existe post-acción A10. |
>
> **Hallazgos reales** (deuda nueva descubierta durante ejecución, no estaba en este audit):
>
> - `apps/api-gateway/src/api_gateway/routes/proxy.py` — `/api/v1/entregas` está declarado dos veces (L43 y L60). Python deduplica al construir el dict, pero es código sucio.
> - **NO hay `superadmin` sembrado en ningún seed del repo**. web-admin loguea como admin fantasma (`33333333-...`) que dev_trust_headers acepta sin validar contra DB. Frágil para el día que se prenda Keycloak validation.
> - `docs/servicios/web-admin.md:95` tiene afirmación falsa: dice que el seed registra el UUID como `docente_admin`, pero Casbin en este repo NO asocia UUIDs a roles — solo rol-a-permission.
> - **40 lint errors pre-existentes** + **9 tests fallando** en frontend (HomeView, StudentLongitudinalView, CorreccionesView, ComisionDelDocenteCard, MaterialesView). No relacionados con cambios recientes.
>
> **Implicación metodológica**: futuras auditorías deben validar afirmaciones leyendo el código vivo, no copiar de CLAUDE.md (que puede quedar desactualizado entre auditorías).

---

---

## Tabla de contenidos

1. [Resumen ejecutivo](#1-resumen-ejecutivo)
2. [Backend — 13 servicios Python](#2-backend--13-servicios-python)
3. [Frontends — 3 apps React 19](#3-frontends--3-apps-react-19)
4. [Packages compartidos + infraestructura + CI](#4-packages-compartidos--infraestructura--ci)
5. [Brechas: especificación vs implementación](#5-brechas-especificación-vs-implementación)
6. [Top 10 riesgos críticos](#6-top-10-riesgos-críticos)
7. [Top 5 fortalezas](#7-top-5-fortalezas)
8. [Riesgos para la tesis doctoral](#8-riesgos-para-la-tesis-doctoral)
9. [Recomendaciones priorizadas](#9-recomendaciones-priorizadas)
10. [Apéndice — mapa de archivos clave](#10-apéndice--mapa-de-archivos-clave)

---

## 1. Resumen ejecutivo

| Dimensión | Estado | Comentario |
|-----------|--------|------------|
| **Backend (13 servicios)** | 🟢 5 maduros / 🟡 6 parciales / ⚫ 2 deprecated | Stack homogéneo (FastAPI 0.100+ / SQLAlchemy 2.0 async / Pydantic v2 / structlog / OTel). Sin Clean Arch — estructura flat por servicio. |
| **Frontends (3 apps)** | 🟢 web-teacher maduro / 🟡 web-admin sólido / 🟡 web-student gappy | React 19 + Vite 6 + TanStack Router file-based (excepto web-admin que usa setState legacy). |
| **Packages (7)** | 🟢 6 con tests / 🟡 1 sin tests (auth-client) | platform-ops + contracts son los más sólidos. |
| **CI/CD** | 🟡 Coverage 60% floor / 🔴 build matrix incompleta (6/11 servicios) | E2E smoke marcado como manual (`workflow_dispatch`), no bloquea PRs. |
| **Spec compliance** | 🟢 ~85-90% | 43 ADRs, casi todos implementados. Capabilities cerradas con feature flags OFF donde aplica. |
| **Riesgos tesis** | 🔴 2 críticos | (1) 106 classifications con hash legacy; (2) validación intercoder bloqueada para socratic_compliance + lexical_anotacion. |

**Veredicto global**: Implementación honra ~85-90% de la spec. Arquitectura **defendible académicamente** (CTR append-only + Ed25519 + k-anonymity + reproducibilidad bit-a-bit). Brechas son operacionalizables pre-defensa, **excepto** los dos riesgos académicos de arriba que requieren acción explícita del equipo (re-clasificación masiva y coordinación con etiquetadores).

---

## 2. Backend — 13 servicios Python

Stack común: FastAPI + SQLAlchemy 2.0 async + Pydantic v2 + Alembic + structlog + OpenTelemetry.

### 2.1 Tabla consolidada

| Servicio | Estado | Endpoints | Modelos | Migraciones | Tests | TODOs | Observación |
|----------|--------|-----------|---------|-------------|-------|-------|-------------|
| **academic-service** | ✅ | 74 | 5 | 11 | 20 | 6 | Más maduro (88 .py, 12 routers). Centro neurálgico académico. |
| **classifier-service** | ✅ | 6 | 1 | 2 | 11 | 1 | Pipeline 5 coherencias (CT, CCD, CII), config_hash determinista. **Core de la tesis.** |
| **content-service** | ✅ | 8 | 3 | 2 | 7 | 0 | RAG + pgvector, chunking + retrieval, hash determinista. |
| **ctr-service** | ✅ | 6 | 3 | 2 | 11 | 0 | **Event sourcing + Redis Streams 8-particiones** (2067 LOC). Append-only SHA-256. |
| **evaluation-service** | ✅ | 11 | 3 | 0 | 5 | 0 | Entregas + calificación. **Sin migrations Alembic** (deuda). |
| **ai-gateway** | 🟡 | 11 | 0 | 0 | 9 | 1 | Sin DB, proxy LLM + budget/cache. |
| **analytics-service** | 🟡 | 16 | 0 | 0 | 9 | 0 | Sin DB. kappa, ab-test-profiles, progression. |
| **api-gateway** | 🟡 | 4 | 0 | 0 | 5 | 0 | Sin DB. Único punto de auth (JWT RS256, headers X-*). ROUTE_MAP de 30 entries. |
| **governance-service** | 🟡 | 6 | 0 | 0 | 5 | 0 | Sin DB. Versionado de prompts. |
| **integrity-attestation-service** | 🟡 | 6 | 0 | 0 | 9 | 0 | Sin DB, **sin README**. Ed25519 (ADR-021). En piloto vive en VPS UNSL. |
| **tutor-service** | 🟡 | 14 | 0 | 0 | 18 | 1 | Orquestador socrático + SSE. 40 archivos. |
| **enrollment-service** | ⚫ | 5 | 0 | 0 | 1 | 2 | **Deprecated** (ADR-030). Bulk-import movido a academic-service. |
| **identity-service** | ⚫ | 3 | 0 | 0 | 1 | 0 | **Deprecated** (ADR-041). Auth desplazada al api-gateway. |

### 2.2 Top 5 más maduros

1. **academic-service** — 88 .py, 74 endpoints, 5 modelos, 11 migraciones, 20 tests. Casbin/RBAC con 170 policies, bulk-import, seeds. Patrón replicable para otros servicios.
2. **tutor-service** — 40 .py, orquestación socrática + SSE + guardrails (ADR-019/043) + overuse detector + workers. Complejidad conceptual máxima.
3. **ctr-service** — Event sourcing puro con `NUM_PARTITIONS=8`, `shard_of(episode_id)` determinístico, single-writer por partición, hash chain SHA-256.
4. **content-service** — RAG + pgvector, embeddings, retrieval, chunking con `chunks_used_hash` determinista.
5. **classifier-service** — 5 coherencias independientes, `classifier_config_hash` SHA-256 canónica (`ensure_ascii=False`, ADR-013), test golden de reproducibilidad.

### 2.3 Top 5 más débiles

1. **identity-service** — Deprecated. Funcionalidad migrada a api-gateway.
2. **enrollment-service** — Deprecated. TODOs irresueltos: "TODO F1-W7: aplicar realmente las inscripciones".
3. **integrity-attestation-service** — Sin README, opaca. Eventos en `attestation.requests` se acumulan sin consumidor en dev.
4. **ai-gateway** — Sin persistencia. TODO cache Redis por materia_id. Budget/fallback opaca.
5. **analytics-service** — 9 tests para 16 endpoints. Confiá ciegamente en headers X-* del api-gateway.

### 2.4 Patrones globales

**Homogeneidad**:
- Estructura estándar `src/{svc_name}/main.py | config.py | routes/ | models/ | services/ | schemas/`.
- Todos con `observability.py` (structlog) y `routes/health.py`.
- Validación JWT delegada al api-gateway; servicios confían en headers.

**Rupturas de convención**:
- 🔴 **NO siguen Clean/Hexagonal Architecture** — no hay layers `domain/`, `application/`, `infrastructure/`. Estructura flat. Documentado pero no implementado.
- Routers + servicios mezclados en mismo módulo (separation of concerns débil).
- Modelos SQLAlchemy y schemas Pydantic separados, sin sincronización automática.

### 2.5 Brechas globales

| Área | Manifestación | Servicios afectados |
|------|---------------|---------------------|
| TODOs sin resolver | "FIXME F1-W7", "TODO F3", "TODO cache Redis" | academic (6), classifier (1), enrollment (2), ai-gateway (1), tutor (1) |
| Migraciones huérfanas | evaluation-service tiene 3 modelos pero sin Alembic | evaluation-service |
| Tests mínimos | < 10 tests por servicio | ai-gateway, analytics, api-gateway, governance |
| Sin documentación | falta README | integrity-attestation-service |
| Event-driven incompleto | solo ctr-service usa Redis Streams | 11/13 servicios |
| Sin tracing cross-service | structlog OK, pero sin correlation IDs en HTTP | todos |
| Sin rate limiting per-svc | solo BYOK budgeting en ai-gateway | todos excepto ai-gateway |

---

## 3. Frontends — 3 apps React 19

Stack común: React 19 + Vite 6 + TanStack Router (file-based) + TanStack Query + Tailwind 4 + Biome + Vitest + Playwright. Compartido `@platform/ui`, `@platform/auth-client`, `@platform/contracts`.

### 3.1 web-admin (puerto 5173)

| Aspecto | Detalle |
|---------|---------|
| **Estado** | 🟡 Sólido — Dashboard CRUD operativo |
| **Rutas** | 13 pages (`src/pages/`) — useState legacy, **NO usa TanStack Router file-based** (deuda de migración) |
| **Pages** | HomePage, UniversidadesPage, FacultadesPage, CarrerasPage, PlanesPage, MateriasPage, PeriodosPage, ComisionesPage, BulkImportPage, AuditoriaPage, ClasificacionesPage, ByokPage, GovernanceEventsPage |
| **Estado/data** | TanStack Query + useMutation. Cascading selectors (Univ → Carrera → Plan → Materia). |
| **Tests unit** | 2 archivos (~250 LOC) |
| **Tests E2E** | 1 journey (`01-admin-auditoria.spec.ts`) |
| **HelpButton** | ✅ 8/9 pages (88% compliance) |
| **Deuda** | 0 console.logs, 0 TODOs, 0 `any`. Migración a TanStack Router file-based diferida. |

### 3.2 web-student (puerto 5175)

| Aspecto | Detalle |
|---------|---------|
| **Estado** | 🟡 Funcional con gaps críticos |
| **Rutas** | 4 file-based: `__root.tsx`, `index.tsx`, `materia.$id.tsx`, `episodio.$id.tsx` |
| **Componentes** | 9 presentacionales (CodeEditor con Monaco + Pyodide, TareaSelector, ExerciseListView, NotesPanel, OpeningStage, ReflectionModal, etc.) |
| **Estado/data** | useState + Promise.then() (**NO TanStack Query**). sessionStorage para episodio recovery. SSE del tutor-service. |
| **Tests unit** | 7 archivos (~500 LOC) |
| **Tests E2E** | 1 journey (`04-student-tutor-flow.spec.ts`) |
| **HelpButton** | ✅ EpisodePage + `__root.tsx` |
| **Deuda** | 3 console.warn, 2 console.debug en EpisodePage. 2 TODOs (auth + ContinuarCard styling). EpisodePage anomalía: vive embebida en `/episodio/$id`, no en root. |
| **Bloqueador 🔴** | `GET /api/v1/comisiones/mis` devuelve `[]` para estudiantes (busca en `usuarios_comision` que es de docentes). Fallback dev hardcoded UUID en `vite.config`. F9-bloqueado por Keycloak claims. |

### 3.3 web-teacher (puerto 5174)

| Aspecto | Detalle |
|---------|---------|
| **Estado** | 🟢 Maduro — frontend más completo |
| **Rutas** | 10 file-based + 12 views: index, templates, tareas-practicas, materiales, kappa, progression, export, episode-n-level, student-longitudinal, cohort-adversarial, correcciones, unidades |
| **Componentes** | 38 archivos. 6 reutilizables (AcademicContextSelector, ComisionSelector, ComisionSelectorRouted, GenerarConIAWizard, ViewModeToggle, ComisionDelDocenteCard) + 12 views |
| **Estado/data** | Mezcla useState + TanStack Query. Drill-down via search params. AcademicContextSelector con `useCallback` (resuelve loop infinito 36req/s del bug 2026-04-23) |
| **Tests unit** | 6 archivos + `helpContent.coverage.test.ts` (anti-regresión) (~800 LOC) |
| **Tests E2E** | 4 journeys (más cobertura E2E del repo) |
| **HelpButton** | 🔴 **6/12 views (50%)** — falta en EpisodeNLevelView, StudentLongitudinalView, CohortAdversarialView, CorreccionesView, UnidadesView, KappaRatingView. **Viola mandato de CLAUDE.md.** |
| **Deuda** | 2× `as any` (ComisionSelector — narrowing tipado fallido). 0 console.logs. `helpContent.coverage` test verifica claves pero NO renderizado. |

### 3.4 Comparación cruzada

| Eje | web-admin | web-student | web-teacher |
|-----|-----------|-------------|-------------|
| Madurez | 🟡 Sólido | 🟡 Gappy | 🟢 Maduro |
| Rutas | 13 (legacy) | 4 (file-based) | 10 (file-based) |
| Tests E2E | 1 | 1 | 4 |
| HelpButton compliance | 88% | n/a (no dashboard) | 50% 🔴 |
| Deuda crítica | 0 | Gap B.2 (comisiones) | 6 views sin HelpButton |

### 3.5 Brechas frontend

| Brecha | Severidad | App | Comentario |
|--------|-----------|-----|------------|
| HelpButton ausente en 6/12 views | 🔴 Mandato violado | web-teacher | Bloqueado post-defensa (skill `impeccable`, G7 ADR-022) |
| `/api/v1/comisiones/mis` vacío | 🔴 Funcional | web-student | Gap B.2 documentado. F9-bloqueado por Keycloak |
| EpisodePage anomalía arquitectónica | 🟡 Deuda | web-student | No es root, vive en `/episodio/$id` |
| MarkdownRenderer duplicado | 🟡 Deuda | student + teacher | No está en `@platform/ui`. Refactor obvio |
| 2× `as any` narrowing | 🟡 Tipado | web-teacher | Fallback `(c as any).nombre` en ComisionSelector |
| Tests unit débiles en lógica episodio | 🟡 Cobertura | web-student | E2E journey 4 lo compensa parcialmente |
| Sin tests A11y | 🟡 Discovery | todos 3 | Sin axe-core, sin WCAG checks |
| `vite.config` UUIDs hardcoded sin CI safeguard | 🟡 Drift | todos 3 | Sincronización seed ↔ frontend manual |
| TanStack Router migración pendiente | 🟡 Consistencia | web-admin | Plugin ya en `package.json`, falta migrar pages |

---

## 4. Packages compartidos + infraestructura + CI

### 4.1 Packages (7)

| Package | Stack | Propósito | Tests | Estado |
|---------|-------|-----------|-------|--------|
| **auth-client** | TS | Cliente Keycloak + React hooks | 0 (lint/typecheck only) | 🟡 |
| **contracts** | TS + Python | Schemas Zod/Pydantic + tipos CTR/academic | 5 (hashing, paridad TS↔Python, self_hash non-ASCII) | ✅ |
| **ctr-client** | TS | Cliente IndexedDB para caché CTR local | 1 suite (Vitest, fake-indexeddb) | ✅ |
| **observability** | Python | OTel + structlog + Sentry | 2 unit | ✅ |
| **platform-ops** | Python | Exports, alertas, crypto, AB testing, auditoría | 11 (crypto, cii-alerts, cii-longitudinal, ab-testing, academic-export, adversarial, audit) | ✅ |
| **test-utils** | Python | Fixtures testcontainers (Postgres, Redis) | 0 (es fixture lib) | ✅ |
| **ui** | TS | Componentes React (Modal, HelpButton, PageContainer) + Tailwind 4 | 3 (Modal, HelpButton, PageContainer) | ✅ |

**Ranking de madurez**: platform-ops > contracts > observability ≈ ui > ctr-client > test-utils > auth-client.

### 4.2 CI/CD — `.github/workflows/`

| Workflow | Trigger | Jobs | Cobertura |
|----------|---------|------|-----------|
| **ci.yml** | PR + push main | 8 secuenciales | Lint (ruff) + typecheck (mypy) + unit tests (pytest, gate 60%) + integration (testcontainers) + RLS isolation + migrations dry-run + Docker build matrix (6 servicios) + Trivy security |
| **e2e-smoke.yml** | PR/push + workflow_dispatch | 1 (skeleton) | Levanta 12 servicios + 11 workers, seed data, 30 smoke tests, artifacts en falla. **No bloquea merges** (manual). |
| **deploy.yml** | (no auditado en detalle) | — | Deploy pipeline |

**Gate de coverage**: 60% (deuda pedagógica conocida — tutor=60%, ctr=63%, classifier=85%, goal global=80% / pedagógico=85%).

**Build matrix Docker** (6/11 servicios cubiertos):
- ✅ api-gateway, identity-service, academic-service, tutor-service, ctr-service, ai-gateway
- ❌ analytics, classifier, content, governance, evaluation, integrity-attestation

### 4.3 Infraestructura

**Docker Compose dev** (`infrastructure/docker-compose.dev.yml`) levanta 11 servicios infra:
- PostgreSQL 16 + pgvector (4 bases lógicas: academic_main, ctr_store, classifier_db, content_db)
- Keycloak 25
- Redis 7 (Streams + cache)
- MinIO (S3)
- OTel Collector + Jaeger
- Prometheus + Grafana + Loki

Los **13 servicios Python NO están en compose** — corren localmente con `uv run uvicorn` para hot-reload.

**Helm** (`infrastructure/helm/platform/`): chart único monolítico (`templates/backend-services.yaml` + 3 value files). Templating per-service no visible.

**Terraform** (`infrastructure/terraform/`): presente, no auditado en detalle.

**Ops** (`ops/`):
- `grafana/` — dashboards
- `k8s/` — manifiestos (rollouts, svc, statefulsets, canary-tutor-service.yaml)
- `prometheus/` — alertas + scrape configs

### 4.4 Scripts (`scripts/`)

21 scripts. Críticos:
- `dev-start-all.sh` / `dev-stop-all.sh` — bootstrap
- `migrate-all.sh` — Alembic para 4 bases
- `seed-3-comisiones.py`, `seed-demo-data.py`, `seed-smoke.py` — fixtures
- `check-rls.py` — verifica policies RLS
- `check-claude-md.py` — valida claims numéricos en CLAUDE.md vs código
- `verify-attestations.py` — verifica attestations Ed25519 bit-exact
- `g8a-sensitivity-analysis.py` — análisis ventanas override `anotacion_creada`

### 4.5 Makefile (39 targets)

Cobertura excelente: bootstrap (`init`, `dev-bootstrap`, `install`), dev (`dev`, `build`, `status`), tests (`test`, `test-fast`, `test-rls`, `test-adversarial`, `test-e2e`, `test-smoke`), ops (`migrate`, `seed-casbin`, `seed-smoke`), analytics (`kappa`, `progression`, `export-academic`, `ab-test-profiles`).

### 4.6 Brechas CI/infra

1. 🔴 **Build matrix incompleta**: 6/11 servicios. Faltan tutor, analytics, classifier, content, governance, evaluation, integrity-attestation.
2. 🔴 **E2E smoke no obligatorio**: solo `workflow_dispatch`. Debería bloquear PRs.
3. 🟡 **Helm monolítico**: sin templating per-service visible.
4. 🟡 **Coverage floor 60%**: deuda pedagógica (tutor 60%, ctr 63% vs goal 85%).
5. 🟡 **RLS tests aislados**: corren en job separado (`test-rls`), no integrados.
6. 🟡 **auth-client + test-utils sin tests propios**.

---

## 5. Brechas: especificación vs implementación

### 5.1 Servicios declarados vs implementados

✅ **Coherencia 100%**. README.md sección "Arquitectura en un vistazo" coincide exactamente con lo implementado. No hay servicios fantasma. 11 activos + 2 deprecated preservados con README de deprecation.

### 5.2 Capabilities (epic `ai-native-completion-and-byok`)

5 capabilities backend, todas implementadas con feature flags OFF donde aplica:
- ADR-035 — reflexión ✅
- ADR-033/034 — sandbox Pyodide (esqueleto, deferido al piloto-2) ✅ esqueleto
- ADR-036 — TP-gen IA (endpoint funcional, UI wizard diferida) ✅ parcial
- ADR-037 — governance UI read-only (endpoint OK, `GovernanceEventsPage.tsx` UI diferida) ✅ parcial
- ADR-038/039/040 — BYOK multi-provider ✅

Restricción crítica del epic: `_EXCLUDED_FROM_FEATURES = {"reflexion_completada", "tp_entregada", "tp_calificada"}` — verificado por test `test_reflexion_completada_no_afecta_clasificacion_ni_features`.

### 5.3 ADRs (43 totales) vs implementación

**Completos** (41/43): 001-014, 016-040, 042-045 implementados y verificables por código + tests.

**Brechas en ADRs**:
- 🟡 **ADR-015 (Blue-green deploy)**: especificado, canary en `ops/k8s/canary-tutor-service.yaml`, **no validado en dev** (vive en VPS UNSL).
- 🟡 **ADR-042 (TareaPracticaTemplate piloto-1)**: comisiones nuevas POST-template **no heredan** TPs automáticamente. Limitación admitida.

### 5.4 Invariantes críticas

| Invariante | Verificación | Estado |
|-----------|-------------|--------|
| CTR append-only (no UPDATE/DELETE) | grep + `is_current=false` + nuevo INSERT | ✅ |
| `LABELER_VERSION=1.2.0` | `classifier-service/config.py:76` | ✅ |
| `MIN_STUDENTS_FOR_QUARTILES=5` | `platform-ops/cii_alerts.py` | ✅ |
| `BYOK_MASTER_KEY` env var | `ai-gateway/services/byok.py` | 🔴 **No está en `.env.example`** |
| `MIN_EPISODES_FOR_LONGITUDINAL=3` | `platform-ops/cii_longitudinal.py` | ✅ |
| Hash canónico no-ASCII (`ensure_ascii=False`) | `contracts/ctr/hashing.py:52-57` | ✅ |
| `GENESIS_HASH="0"*64` | `ctr-service/models/base.py` | ✅ |
| RLS multi-tenant | `make check-rls`, 4 tests reales | ✅ |
| api-gateway único source de identidad | headers X-Tenant-Id, X-User-Id | ✅ |
| `student_pseudonym` vs `student_alias` | 267 referencias separadas | ✅ |

### 5.5 Tesis doctoral

**Trazabilidad Cognitiva N4**:
- ✅ Modelo N4 jerárquico — 5 coherencias en `Classification.coherencies` JSONB
- ✅ Etiquetador N1-N4 (LABELER_VERSION 1.2.0)
- ✅ k-anonymity gate degradable (`insufficient_data: true` si N<5)
- ✅ Auditabilidad — CTR append-only + Ed25519 + aliases `/api/v1/audit/*` + AuditoriaPage
- ✅ Reproducibilidad bit-a-bit — `classifier_config_hash`, `self_hash`, `chain_hash`, test golden

**Brechas académicas**:
1. 🔴 **106 classifications con hash legacy** pre-existentes (antes del bump LABELER_VERSION 1.2.0). Re-clasificación masiva nunca corrió.
2. 🔴 **Validación intercoder bloqueada** — socratic_compliance (ADR-044) y lexical_anotacion (ADR-045) están en esqueleto OFF pendiendo κ ≥ 0.6 sobre 50+ muestras.
3. 🟡 **CII longitudinal limitado a templates** — TPs huérfanas sin `template_id` quedan excluidas del cálculo.

### 5.6 Backlog QA (2026-05-07) — 7 issues abiertos

| Issue | Severidad | Bloqueador v1.0 |
|-------|-----------|-----------------|
| Leak `student_pseudonym` en `GET /comisiones/{id}/inscripciones` | MEDIA | No |
| `POST /classify_episode/{id}` no idempotente (500 duplicate-key) | MEDIA | No |
| Filtro `unidad_id` en `GET /tareas-practicas` no aplica | MEDIA | No |
| `byok_keys_usage` vacía en env_fallback | BAJA | No |
| `tutor_respondio.payload` no persiste tokens (input/output/provider) | MEDIA | No |
| `nota_final` serializado como string Decimal vs number | MEDIA | No |
| 106 classifications con hash legacy | MEDIA | Piloto |

---

## 6. Top 10 riesgos críticos

| # | Riesgo | Severidad | Categoría | Mitigación |
|---|--------|-----------|-----------|------------|
| 1 | **106 classifications con hash legacy** — reproducibilidad histórica comprometida | 🔴 CRÍTICA | Académica | Worker que recompute con LABELER_VERSION 1.2.0 antes de defensa |
| 2 | **Validación intercoder bloqueada** (socratic + lexical) — κ ≥ 0.6 sobre 50+ muestras pendiente | 🔴 CRÍTICA | Académica | Coordinar con etiquetadores UNSL, iterar patrones |
| 3 | **`BYOK_MASTER_KEY` sin default seguro en dev** — bloquea dev local sin setup manual | 🔴 ALTA | Operacional | Agregar a `.env.example` con instrucción `openssl rand -base64 32` |
| 4 | **Comisión selector vacío para estudiantes** — Gap B.2, F9-bloqueado por Keycloak | 🔴 ALTA | UX | Activar claim `comisiones_activas` con DI UNSL semana previa |
| 5 | **HelpButton ausente en 6/12 views de web-teacher** — viola mandato CLAUDE.md | 🟡 ALTA | Compliance | Skill `help-system-content` resuelve cada view en ~30min |
| 6 | **Build matrix Docker incompleta (6/11)** — 5 servicios sin imagen en CI | 🟡 ALTA | DevOps | Expandir matriz en `ci.yml` |
| 7 | **E2E smoke no obligatorio** — `workflow_dispatch` manual | 🟡 ALTA | Calidad | Cambiar trigger a `pull_request` |
| 8 | **CII longitudinal excluye TPs huérfanas** — reduce cobertura del modelo N4 | 🟡 MEDIA | Metodológica | Documentar en defensa como scope piloto-1 |
| 9 | **Leak `student_pseudonym` en `GET /inscripciones`** — handler debería filtrar `WHERE student_pseudonym = user.id` | 🟡 MEDIA | Privacidad | Fix de query |
| 10 | **`tutor_respondio.payload` no persiste tokens** — gap auditoría costos LLM multi-provider (ADR-039) | 🟡 MEDIA | Auditoría | Agregar campos input/output/provider |

---

## 7. Top 5 fortalezas

1. **Arquitectura de dos planos desacoplada** (académico vs pedagógico) — Redis Streams como bus preserva invariantes separadamente. Permite evolucionar classifier sin tocar academic-service. **Decisión de diseño excelente.**
2. **CTR append-only + Ed25519 attestations (defensa dual)** — hashes SHA-256 + firmas externas crean evidencia criptográfica irrefutable. `test_audit_aliases_apunta_al_mismo_handler` verifica coherencia. **Modelo defendible académicamente.**
3. **Feature flags + golden hash tests para esqueletos** (ADRs 044/045) — patrón reutilizable: código sin activar + determinismo verificado. Reduce riesgo de regresiones cuando se prenda. **Innovación operacional sólida.**
4. **Documentación operativa exhaustiva** (CLAUDE.md 247 líneas, 43 ADRs, docs/SESSION-LOG.md, docs/servicios/) — cambios futuros son mecánicos, no creativos. **Excelente knowledge transfer.**
5. **k-anonymity integrada como gate degradable** — no es módulo separado, es check en cada endpoint relevante. Con N<5 → `insufficient_data: true`. **Privacy by design, no bolted-on.**

---

## 8. Riesgos para la tesis doctoral

| Riesgo | Probabilidad | Impacto | Mitigación |
|--------|--------------|---------|------------|
| Comité rechaza modelo N4 por **106 históricos no-reproducibles** | ALTA | CRÍTICO | Re-clasificar masivo antes de defensa |
| **Validación intercoder falla (κ < 0.6)** para socratic/lexical | MEDIA | ALTO | Entrenar etiquetadores, ajustar patrones, iterar |
| Keycloak no onboardeado en UNSL → **selector comisiones vacío en defensa** | MEDIA | ALTO | Activar claim `comisiones_activas` con DI UNSL semana previa |
| **Canary deploy falla en vivo** porque no se validó en dev | MEDIA | MEDIO | Testear ADR-015 en staging K8s antes de prod |
| **CII longitudinal reporta N=0** en una comisión (todas TPs huérfanas) | BAJA | MEDIO | Documentar limitación en defensa como scope piloto-1 |

---

## 9. Recomendaciones priorizadas

### 9.1 Pre-defensa (críticas)

1. **Re-clasificar 106 classifications históricas** con LABELER_VERSION 1.2.0 (worker batch nuevo).
2. **Coordinar validación intercoder** para socratic_compliance + lexical_anotacion (50+ muestras, κ ≥ 0.6).
3. **Activar Keycloak claim `comisiones_activas`** con DI UNSL para desbloquear gap B.2.
4. **Agregar `BYOK_MASTER_KEY` a `.env.example`** con instrucción `openssl rand -base64 32`.

### 9.2 Compliance & calidad (altas)

5. **Agregar HelpButton a las 6 views faltantes** de web-teacher (skill `help-system-content` documenta el patrón).
6. **Expandir build matrix Docker** a los 11 servicios (agregar tutor, analytics, classifier, content, governance, evaluation, integrity-attestation).
7. **Hacer e2e-smoke obligatorio en CI** (cambiar trigger a `pull_request`).
8. **Migración Alembic de evaluation-service** (3 modelos sin migrations).
9. **Documentar integrity-attestation-service** (README con propósito + arquitectura Ed25519).

### 9.3 Deuda técnica (media)

10. **Consolidar MarkdownRenderer** duplicado a `@platform/ui` (web-student + web-teacher).
11. **Migrar web-admin a TanStack Router file-based** (plugin ya en `package.json`).
12. **Agregar tests a `auth-client` package** (actualmente 0).
13. **Ratchet coverage floor** de 60% → 80%/85% (tutor + ctr son los retrasados).
14. **Verificar `ROUTE_MAP` invariants** del api-gateway con smoke test.
15. **Resolver 2× `as any`** en ComisionSelector con narrowing real.
16. **Agregar axe-core** a 1-2 journeys E2E como smoke A11y.
17. **CI gate** que valide UUIDs hardcoded en `vite.config` vs `seed.py`.

### 9.4 Limpieza (baja)

18. **Borrar enrollment-service e identity-service** del workspace (ya están deprecated, solo agregan ruido).
19. **Resolver TODOs antiguos** (academic 6, classifier 1, ai-gateway 1, tutor 1).

---

## 10. Apéndice — mapa de archivos clave

### Documentos canónicos
- `AI-NativeV3-main/CLAUDE.md` — invariantes operativas (247 líneas, recientemente comprimido)
- `AI-NativeV3-main/README.md` — stack + puertos + arquitectura
- `AI-NativeV3-main/PRODUCT.md` — UX/UI source of truth
- `AI-NativeV3-main/DESIGN.md` — tokens Tailwind + paleta
- `AI-NativeV3-main/CONTRIBUTING.md` — convenciones, coverage, commits
- `AI-NativeV3-main/docs/CAPABILITIES.md` — capabilities cerradas (recién creado)
- `AI-NativeV3-main/docs/SESSION-LOG.md` — bitácora narrativa
- `AI-NativeV3-main/docs/adr/` — 43 ADRs
- `AI-NativeV3-main/docs/servicios/` — 1 .md por servicio

### Núcleo criptográfico/reproducibilidad
- `packages/contracts/src/platform_contracts/ctr/hashing.py` — fórmula canónica `ensure_ascii=False`
- `apps/classifier-service/src/classifier_service/services/pipeline.py` — pipeline determinista
- `apps/ctr-service/src/ctr_service/models/base.py` — `GENESIS_HASH`, `chain_hash`
- `apps/classifier-service/tests/unit/test_pipeline_reproducibility.py` — golden hash test

### Operaciones
- `Makefile` — 39 targets
- `infrastructure/docker-compose.dev.yml` — 11 servicios infra
- `infrastructure/helm/platform/` — chart monolítico
- `ops/k8s/canary-tutor-service.yaml` — canary deploy (ADR-015)
- `scripts/dev-start-all.sh`, `scripts/migrate-all.sh`, `scripts/check-claude-md.py`

### Tests E2E (Playwright)
- `tests/e2e/01-admin-auditoria.spec.ts`
- `tests/e2e/02-teacher-tareas-practicas.spec.ts`
- `tests/e2e/03-teacher-progression.spec.ts`
- `tests/e2e/04-student-tutor-flow.spec.ts`
- `tests/e2e/05-cross-frontend-ctr-integrity.spec.ts`
- `tests/e2e/smoke/test_*.py` — 30 smoke tests

### Endpoints más críticos
- `POST /api/v1/episodios` — abre episodio (CTR genesis)
- `POST /api/v1/episodios/{id}/cerrar` — dispara clasificación
- `GET /api/v1/audit/episodes/{id}/verify` — alias auditoría (ADR-031)
- `POST /api/v1/classify_episode/{id}` — clasificación manual (no idempotente — bug)
- `GET /api/v1/comisiones/mis` — selector estudiante (gap B.2 — vacío)
- `POST /api/v1/tareas-practicas/generate` — TP-gen IA (ADR-036)
- Stream Redis `attestation.requests` — Ed25519 (ADR-021)

---

**Conclusión**: el proyecto está en un estado **defendible para piloto-1 + tesis** con dos riesgos académicos críticos (re-clasificación histórica y validación intercoder) que requieren acción del equipo, no fixes técnicos localizados. La implementación honra ~85-90% de la spec, con arquitectura sólida en el plano de invariantes (CTR + reproducibilidad + k-anonymity) y deuda concentrada en compliance UX (HelpButton) y CI (build matrix incompleta, e2e no obligatorio).
