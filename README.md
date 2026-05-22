# AI-Native N4

**Plataforma de tutoría socrática con trazabilidad cognitiva criptográfica** para la enseñanza de programación universitaria.

Tesis doctoral de **Alberto Alejandro Cortez** (UTN) — *"Modelo AI-Native con Trazabilidad Cognitiva N4 para la Formación en Programación Universitaria"*.

> No es un producto comercial. Es un **piloto académico** cuya aceptabilidad doctoral depende de invariantes criptográficas y reproducibilidad bit-a-bit.

---

## TL;DR

```bash
cd AI-NativeV3-main
cp .env.example .env                          # editar BYOK_MASTER_KEY
docker compose -f infrastructure/docker-compose.dev.yml up -d
uv sync --all-packages && pnpm install
ACADEMIC_DB_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/academic_main \
CTR_DB_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/ctr_store \
CTR_STORE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/ctr_store \
CLASSIFIER_DB_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/classifier_db \
CONTENT_DB_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/content_db \
bash scripts/migrate-all.sh
uv run python -m academic_service.seeds.casbin_policies
uv run python scripts/seed-3-comisiones.py
uv run python scripts/seed-ejercicios-piloto.py
bash scripts/dev-start-all.sh &
make dev
```

Después abrís `http://localhost:5175` y ya estás dentro como alumno.

---

## Tabla de contenidos

1. [Qué hace esta plataforma](#1-qué-hace-esta-plataforma)
2. [Arquitectura en un vistazo](#2-arquitectura-en-un-vistazo)
3. [Pre-requisitos](#3-pre-requisitos)
4. [Bootstrap (primera vez)](#4-bootstrap-primera-vez)
5. [Levantar el stack día a día](#5-levantar-el-stack-día-a-día)
6. [URLs y roles](#6-urls-y-roles)
7. [Flujo pedagógico](#7-flujo-pedagógico)
8. [Cómo cargar contenido](#8-cómo-cargar-contenido)
9. [Las invariantes académicas](#9-las-invariantes-académicas)
10. [Troubleshooting](#10-troubleshooting)
11. [Reset entre sesiones](#11-reset-entre-sesiones)
12. [Recursos para profundizar](#12-recursos-para-profundizar)

---

## 1. Qué hace esta plataforma

Un alumno de programación I entra a su materia, elige una unidad temática, abre un trabajo práctico y empieza a resolver ejercicios. Mientras escribe código:

- **Pyodide** ejecuta su Python en el browser (sin servidor).
- Un **tutor socrático con LLM real** (Mistral / OpenAI / Anthropic / Gemini via BYOK) lo guía con preguntas — **NO le da la respuesta**.
- Cada evento (lectura, edición, ejecución, pregunta al tutor, respuesta del tutor) se persiste en una **cadena criptográfica append-only SHA-256** (Cognitive Traceability Record, CTR).
- Al cerrar, un **clasificador determinista** evalúa **3 coherencias separadas** (Temporal, Código-Discurso, Inter-Iteración) operacionalizadas en 5 métricas internas (CT, CCD_mean, CCD_orphan_ratio, CII_stability, CII_evolution) y emite un diagnóstico cognitivo N4.

El docente ve dashboards con la **progresión de la cohorte** (con k-anonymity N≥5 sobre cuartiles), puede armar TPs vinculando ejercicios del banco, generar ejercicios nuevos con IA, y verificar la integridad criptográfica de cada episodio.

El admin gestiona universidades, planes, comisiones, importa CSVs de inscripciones, y carga las API keys BYOK por tenant.

---

## 2. Arquitectura en un vistazo

```
┌──────────────────┐   ┌──────────────────┐   ┌──────────────────┐
│  web-student     │   │  web-teacher     │   │  web-admin       │
│  :5175           │   │  :5174           │   │  :5173           │
│  Monaco+Pyodide  │   │  TanStack Router │   │  React 19        │
└────────┬─────────┘   └────────┬─────────┘   └────────┬─────────┘
         │                      │                       │
         └──────────────┬───────┴──────────────┬────────┘
                        ▼                      ▼
                ┌───────────────┐      ┌──────────────┐
                │  api-gateway  │      │   Keycloak   │
                │  :8000        │◄─────┤   :8180      │
                │  JWT + RLS    │      │   (+ LDAP)   │
                └───────┬───────┘      └──────────────┘
                        │
   ┌────────────────────┼────────────────────┬───────────────────┐
   ▼                    ▼                    ▼                   ▼
┌────────────┐    ┌──────────┐         ┌──────────────┐   ┌──────────────┐
│ academic   │    │ tutor    │         │ ctr-service  │   │ classifier   │
│ -service   │    │ -service │  XADD   │ + 8 workers  │   │ -service     │
│ :8002      │    │ :8006    │────────▶│ Redis Streams│   │ :8008        │
│ (CRUDs)    │    │ (SSE)    │         │ partitioned  │   │ (N4 + hash)  │
└────────────┘    └────┬─────┘         └──────┬───────┘   └──────────────┘
                       │                      │
                       ▼                      ▼
                 ┌──────────┐           ┌────────────┐
                 │ ai-gw    │           │ governance │
                 │ :8011    │           │ :8010      │
                 │ BYOK+    │           │ Prompts    │
                 │ cache    │           │ versionados│
                 └──────────┘           └────────────┘

                    Postgres (4 bases lógicas + RLS forced)
                    Redis (sessions + 8 streams CTR particionados)
                    MinIO (artifacts + backups)
                    Prometheus + Grafana + Loki + Jaeger
```

**Dos planos desacoplados** por bus Redis Streams:

- **Académico-operacional**: `academic-service`, `evaluation-service`, `analytics-service`. CRUDs tradicionales.
- **Pedagógico-evaluativo**: `tutor-service`, `ctr-service`, `classifier-service`, `content-service`, `governance-service`. Núcleo de la tesis.

**4 bases lógicas separadas**: `academic_main`, `ctr_store`, `classifier_db`, `content_db` — sin joins cross-base.

**Multi-tenancy = Row-Level Security de Postgres** (ADR-001). Toda tabla con `tenant_id` tiene policy RLS forzada.

---

## 3. Pre-requisitos

| Herramienta | Para qué | Instalación |
|---|---|---|
| **Docker Desktop** | Postgres, Redis, Keycloak, MinIO, observabilidad | https://docker.com |
| **uv** | Manejador de Python (instala todo el backend) | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| **pnpm** | Manejador de Node (frontends) | `npm i -g pnpm` |
| **make** | Orquestador | system package manager |
| **Node 20+** y **Python 3.12+** | Lo demás lo manejan uv/pnpm | nvm + pyenv |
| **Git Bash o WSL** (solo Windows) | El `Makefile` asume bash | Git for Windows + `winget install ezwinports.make` |

**Verificar:** `docker --version && uv --version && pnpm --version && make --version`

Stack RAM ≈ **4 GB**. Si la máquina es chica, comentá la stack de observabilidad en `infrastructure/docker-compose.dev.yml`.

---

## 4. Bootstrap (primera vez)

```bash
# Entrar al monorepo real (no al wrapper)
cd AI-NativeV3-main

# 1. Variables de entorno
cp .env.example .env
# Editá .env y reemplazá BYOK_MASTER_KEY por el output de:
openssl rand -base64 32

# 2. Infraestructura Docker (Postgres, Redis, Keycloak, MinIO, Grafana...)
docker compose -f infrastructure/docker-compose.dev.yml up -d

# 3. Deps backend (~3-5 min la primera vez)
uv sync --all-packages

# 4. Deps frontends
pnpm install

# 5. Migraciones en las 4 bases
ACADEMIC_DB_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/academic_main \
CTR_DB_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/ctr_store \
CTR_STORE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/ctr_store \
CLASSIFIER_DB_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/classifier_db \
CONTENT_DB_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/content_db \
bash scripts/migrate-all.sh

# 6. Seeds: Casbin (permisos) + datos demo
uv run python -m academic_service.seeds.casbin_policies
uv run python scripts/seed-3-comisiones.py       # 5 comisiones + docentes + alumnos
uv run python scripts/seed-ejercicios-piloto.py  # 25 ejercicios del banco
```

Una sola vez. La próxima vez salteás esto y vas directo a "Día a día".

---

## 5. Levantar el stack día a día

**Dos terminales** (o usá `tmux` / `zellij`):

```bash
# Terminal 1: 11 servicios HTTP + 8 workers CTR
bash scripts/dev-start-all.sh

# Terminal 2: 3 frontends Vite (5173/5174/5175)
make dev
```

Verificación rápida:

```bash
bash scripts/check-health.sh
```

Deberías ver 10/11 servicios OK. El `integrity-attestation-service:8012` queda en `503 by design` en dev local — vive en VPS UTN en piloto real, no es bloqueante.

**Apagar todo:**

```bash
bash scripts/dev-stop-all.sh    # backend
# Ctrl+C en el shell de `make dev`
```

---

## ⚙️ Modelo de tenancy (2026-05-14)

**Invariante: 1 universidad = 1 tenant aislado** (migration `20260514_0004`).

- Cada `Universidad` tiene su propio `tenant_id` (`universidad.id == tenant_id` por convención enforzada en `UniversidadService.create()`).
- Toda la jerarquía debajo (facultades, carreras, planes, materias, comisiones, usuarios, inscripciones, **ejercicios**) está aislada por `tenant_id` con **RLS forced**.
- Una universidad nueva arranca con **0 ejercicios** — no hereda nada de otras.
- El admin web (5173) tiene un **selector dinámico de universidad** en la barra superior. Cambiar de universidad cambia el `tenant_id` activo (vía `localStorage` + header `x-selected-tenant` + monkey-patch de `window.fetch` en `main.tsx`).
- El rol `superadmin` puede listar TODAS las universidades a través del policy `superadmin_view_all` (necesario para que el selector funcione).

## 6. URLs y roles

| URL | Frontend | Usuario logueado | Roles |
|---|---|---|---|
| http://localhost:5173 | **Admin** | `33333333-...` admin@demo-uni.edu | `docente_admin,superadmin` |
| http://localhost:5174 | **Docente** | `c8a54501-...` docente01 (titular Comisión 1) | `docente` |
| http://localhost:5175 | **Alumno** | `e19354fb-...` alumno01 (inscripto Comisión 1) | `estudiante` |

**No hay login en dev** — los headers `X-User-Id`, `X-Tenant-Id`, `X-User-Roles` los inyecta el proxy de Vite directamente. En producción los firma Keycloak.

**Para entrar como otro usuario** editá el `vite.config.ts` correspondiente. Los 5 docentes y 5 alumnos del seed están listados en [`docs/users.md`](AI-NativeV3-main/docs/users.md).

Otras URLs útiles:

| URL | Servicio |
|---|---|
| http://localhost:8000 | api-gateway (entrada externa) |
| http://localhost:3000 | Grafana (métricas) |
| http://localhost:16686 | Jaeger (traces) |
| http://localhost:8180 | Keycloak admin |
| http://localhost:9090 | Prometheus |

---

## 7. Flujo pedagógico

```
DOCENTE (5174)                              ALUMNO (5175)
══════════════                              ═════════════

1. Crea Unidades temáticas                  1. Entra a su materia
   (TP1: Secuenciales, TP2: Condicionales)     │
       │                                       ▼
       ▼                                    2. Elige una Unidad
2. Crea Ejercicios en el banco                 │
   - Manual                                    ▼
   - Con IA (Mistral genera todo)           3. Elige un TP de esa Unidad
       │                                       │
       ▼                                       ▼
3. Crea Trabajos Prácticos                  4. Hace los ejercicios secuencialmente:
   - Asigna a una Unidad                       │
   - Vincula ejercicios del banco              ├─ Lee la consigna     (evento N1)
       │                                       ├─ Escribe código      (evento N3)
       ▼                                       ├─ Ejecuta con Pyodide (evento N3/N4)
4. Ve dashboards de progresión              │   ├─ Charla con el tutor  (eventos N4)
   - K-anonymity N≥5 sobre cuartiles        │   └─ Cierra el episodio
   - Alertas predictivas por estudiante     │       │
       │                                    │       ▼
       ▼                                    5. Recibe diagnóstico N4:
5. Audita la cadena CTR de cualquier            CT / CCD / CII separados
   episodio (verify chain SHA-256)              + appropriation (3 categorías,
                                                  paper §4.4 / tree.py):
                                                  · apropiacion_reflexiva
                                                    (label UI: "Autonomo")
                                                  · apropiacion_superficial
                                                  · delegacion_pasiva
                                                    (sub_branch: extreme | classic)
```

**Concepto clave de la tesis**: las 3 coherencias (en sus 5 métricas internas) NUNCA se colapsan en un score único — el análisis es multidimensional.

---

## 8. Cómo cargar contenido

### Los 25 ejercicios canónicos

Vienen de 3 `.docx` reales del PID UTN (cátedras de programación de UTN-FRM × UTN-FRSN). Cada uno fue extraído a un YAML estructurado con todos los campos pedagógicos (consigna markdown, test_cases ejecutables, rúbrica, misconceptions, banco socrático, anti-patrones, tutor_rules).

```
scripts/data/ejercicios-piloto.yaml  ← 4.176 líneas, 25 ejercicios
                ↓
       seed-ejercicios-piloto.py     ← script idempotente
                ↓
       tabla `ejercicios`             ← banco standalone (ADR-047/048)
```

### Cómo agregar ejercicios NUEVOS

| Forma | Comando / camino | Cuándo |
|---|---|---|
| **A. Editar YAML + re-correr seed** | Agregás bloque a `ejercicios-piloto.yaml`, corrés `seed-ejercicios-piloto.py` | Cuando tenés fuente formal y querés versionado en git |
| **B. Manual desde la UI** | Web-teacher → Banco → "Crear manual" | Cuando el docente quiere agregar uno puntual |
| **C. Generar con IA** | Web-teacher → "Crear con IA" | Para exploración rápida. Marca `created_via_ai=true` |

Los tres caminos terminan en la misma tabla `ejercicios`. El campo `created_via_ai` queda como trazabilidad académica para distinguir piloto canónico de extensiones.

### Vincular ejercicios a un TP

Una vez creado el TP en el web-teacher, lo abrís y vinculás N ejercicios del banco vía la tabla intermedia `tp_ejercicios`. Los alumnos los van a hacer **en orden secuencial** (el siguiente queda bloqueado hasta completar el anterior).

---

## 9. Las invariantes académicas

Estas NO son sugerencias — están verificadas por tests y fundamentan la aceptabilidad doctoral del piloto:

| Invariante | Cómo se verifica | ADR |
|---|---|---|
| **CTR append-only** (`UPDATE`/`DELETE` prohibidos) | Test smoke + verify chain SHA-256 | ADR-010 |
| **`classifier_config_hash` determinista** | `test_pipeline_reproducibility.py` re-clasifica y compara hash | ADR-020 |
| **Las 3 coherencias SEPARADAS (en 5 métricas)** | `Classification` schema con 5 columnas (CT, CCD_mean, CCD_orphan_ratio, CII_stability, CII_evolution), nunca un score único | ADR-018 |
| **k-anonymity N≥5 sobre cuartiles** | `MIN_STUDENTS_FOR_QUARTILES=5` en `cii_alerts.py` | ADR-022/RN-131 |
| **Multi-tenant RLS forzado** | `make check-rls` en CI | ADR-001 |
| **Attestation Ed25519 post-cierre** | `integrity-attestation-service` firma con SLO 24h | ADR-021/RN-128 |
| **`EpisodioAbandonado` idempotente** | Doble trigger (frontend `beforeunload` + worker 60s) | ADR-025 |
| **Write-only al CTR desde tutor-service** | Excepto `codigo_ejecutado` que usa user del estudiante | ADR-010 |
| **Eventos excluidos del classifier** | `reflexion_completada`, `tp_entregada`, `tp_calificada` | ADR-027/044 |
| **Export académico anonimizado** | `salt ≥ 16 chars`, `include_prompts=False` default | RN-090 |

Romper cualquiera invalida la tesis. Las constantes (hashes, versiones, UUIDs de service-accounts, ventanas temporales) están en [`AI-NativeV3-main/CLAUDE.md`](AI-NativeV3-main/CLAUDE.md) bajo la sección "Constantes que NO deben inventarse ni cambiarse".

---

## 10. Troubleshooting

| Síntoma | Causa probable | Fix |
|---|---|---|
| Frontends salen en 5176/5177 en vez de 5173/5174/5175 | Containers Docker de otros proyectos en esos puertos | `docker ps -a --format '{{.Names}} {{.Ports}}' \| grep :5173` y matá los rivales |
| `make migrate` falla con permission denied | `alembic/env.py` apunta hardcoded a `academic_user` | Override: `ACADEMIC_DB_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/academic_main uv run alembic -c apps/academic-service/alembic.ini upgrade head` |
| `POST /api/v1/episodes` da 201 pero `GET` siguiente da 404 | Race condition: worker CTR no terminó de persistir | Ya parcheado en frontend con retry exponential. Si persiste, `pgrep -af partition_worker` debe mostrar 8 procesos vivos |
| Wizard IA devuelve `LLM devolvió JSON inválido` (502) | No hay BYOK cargada en el tenant | Entrar al admin (5173) → Configuración BYOK → cargar API key |
| `make dev` no levanta uno de los 3 frontends | Tailwind v4 + symlink pnpm: falta `@source` directive | Verificar que `apps/web-*/src/index.css` tenga `@source "../../../packages/ui/src/**/*.{ts,tsx}"` |
| Edición de schema en `packages/contracts/` no se ve en runtime | `uv run uvicorn --reload` no watchea `packages/` | Matar el PID del servicio (`pkill -9 -f academic_service.main:app`) y relanzar |
| `make check-rls` skippea los 4 tests reales | Falta `CTR_STORE_URL_FOR_RLS_TESTS` | Exportar la var apuntando a una base con usuario non-superuser |
| Vite + `localhost` en Windows enruta mal | `localhost` resuelve IPv6 primero, hay containers en `0.0.0.0` | Usar `127.0.0.1` en config service-a-service. Para frontends usar `localhost` |

Más detalles operativos en [`AI-NativeV3-main/CLAUDE.md`](AI-NativeV3-main/CLAUDE.md) sección "Gotchas de entorno".

---

## 11. Reset entre sesiones

Si querés volver al estado "recién clonado + seeds" sin re-correr migraciones:

```bash
bash AI-NativeV3-main/scripts/reset-to-seed.sh
```

Borra TPs, unidades, episodios, clasificaciones y ejercicios IA. **Preserva**: comisiones, docentes, alumnos, los 25 ejercicios canónicos, policies Casbin, y BYOK keys.

Útil antes de demos o entre iteraciones de testing.

---

## 12. Recursos para profundizar

### Documentación interna

| Documento | Para qué |
|---|---|
| [`AI-NativeV3-main/README.md`](AI-NativeV3-main/README.md) | README técnico completo (426 líneas, orientado a devs) |
| [`AI-NativeV3-main/CLAUDE.md`](AI-NativeV3-main/CLAUDE.md) | Invariantes, constantes hash, gotchas operacionales |
| [`AI-NativeV3-main/docs/adr/`](AI-NativeV3-main/docs/adr/) | 43 ADRs (decisiones arquitectónicas permanentes) |
| [`AI-NativeV3-main/docs/SESSION-LOG.md`](AI-NativeV3-main/docs/SESSION-LOG.md) | Changelog narrativo de cambios |
| [`AI-NativeV3-main/docs/CAPABILITIES.md`](AI-NativeV3-main/docs/CAPABILITIES.md) | Estado por capability funcional |
| [`AI-NativeV3-main/PRODUCT.md`](AI-NativeV3-main/PRODUCT.md) | UX/UI source of truth |
| [`AI-NativeV3-main/DESIGN.md`](AI-NativeV3-main/DESIGN.md) | Tokens Tailwind / paleta |

### Documentación de gobierno (en este wrapper)

| Documento | Para qué |
|---|---|
| [`audita1.md`](audita1.md) | Auditoría inicial (inventario, brechas, riesgos) |
| [`plan-accion.md`](plan-accion.md) | Plan derivado con 26 acciones + DAG + estado |
| [`audi2.md`](audi2.md) | Auditoría de completitud (20 capabilities × 4 criterios) |
| [`ppconarev.md`](ppconarev.md) | Revisión paper vs implementación |
| [`paper-draft.md`](paper-draft.md) | Draft consolidado del paper académico |

### Stack técnico

**Backend (Python)**: FastAPI 0.100+ · SQLAlchemy 2.0 async · Alembic · structlog · OpenTelemetry · Casbin · pgvector

**Frontends (TypeScript)**: React 19 · Vite 6 · TanStack Router · TanStack Query · Tailwind 4 · Monaco · Pyodide · Keycloak-js

**Workspace**: uv (Python) + pnpm + turbo (TS)

**Infraestructura**: Postgres 16 + RLS · Redis 7 Streams · Keycloak 25 · MinIO · Prometheus + Grafana + Loki + Jaeger

---

## Estado actual del piloto

| Métrica | Valor |
|---|---|
| Apps activas | 14 (11 servicios Python + 3 frontends) |
| Capabilities funcionales al 100% | 11 / 20 (núcleo doctoral defendible) |
| Packages compartidos | 7 |
| Migraciones Alembic | 17 |
| ADRs | 43 |
| Tests smoke E2E | 30 (corren en <2s) |
| Acciones cerradas | 23 / 26 del plan-accion.md |

**Lo que aún falta** son externos al código (coordinación humana):

- **A1**: re-clasificar 106 classifications históricas con DB del piloto real.
- **A2**: validación intercoder κ ≥ 0.70 con 2 docentes UTN (cuello de botella académico).
- **A3**: claim `comisiones_activas` en JWT de Keycloak (con DI UTN).
- **A5**: defensa doctoral.

---

## Licencia

Ver [`AI-NativeV3-main/LICENSE`](AI-NativeV3-main/LICENSE).

---

**Autor**: Alberto Alejandro Cortez · Doctorado UTN
**Co-directora**: Daniela Carbonari
**Repositorio del piloto**: este monorepo
