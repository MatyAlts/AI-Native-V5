# Plataforma AI-Native con Trazabilidad Cognitiva N4

Monorepo integrado para la tesis doctoral de **Alberto Alejandro Cortez**
(UNSL) — _"Modelo AI-Native con Trazabilidad Cognitiva N4 para la
Formación en Programación Universitaria"_.

Este repositorio contiene **la plataforma completa** que ejecuta el
estudio piloto en UNSL: servicios backend, frontends, observabilidad,
análisis empírico, privacidad, y toda la operación.

## Estado

**Listo para piloto**. Fases F0–F9 integradas + epics post-piloto cerrados (`ai-native-completion-and-byok`, `real-health-checks`, `unidades-trazabilidad`, `tp-entregas-correccion`).

| Métrica | Valor |
|---|---|
| Apps activas | 14 (11 servicios Python + 3 frontends) |
| Servicios deprecated preservados | 2 (`identity-service` ADR-041, `enrollment-service` ADR-030) |
| Packages compartidos | 7 |
| Migraciones Alembic | 17 |
| ADRs | 43 |

## Arquitectura en un vistazo

```
┌─────────────────┐   ┌─────────────────┐   ┌─────────────────┐
│  web-student    │   │  web-teacher    │   │  web-admin      │
│  (Vite + React) │   │  (3 vistas F7)  │   │                 │
└────────┬────────┘   └────────┬────────┘   └────────┬────────┘
         │                     │                     │
         └──────────────┬──────┴──────────┬──────────┘
                        ▼                 ▼
                ┌───────────────┐  ┌──────────────┐
                │  api-gateway  │  │   Keycloak   │
                │  (JWT + RLS)  │◄─┤   (+ LDAP)   │
                └───────┬───────┘  └──────────────┘
                        │
      ┌─────────────────┼─────────────────┬─────────────────┐
      ▼                 ▼                 ▼                 ▼
 ┌─────────┐      ┌─────────┐       ┌───────────┐    ┌──────────┐
 │ tutor-  │      │  ctr-   │       │classifier-│    │analytics-│
 │ service │─────▶│ service │◄─────│  service  │───▶│ service  │
 │  (RAG)  │      │ (chain) │       │  (N4)    │    │(F7 + F8) │
 └────┬────┘      └────┬────┘       └──────────┘    └──────────┘
      │                │                    │
      ▼                ▼                    ▼
 ┌──────────────────────────────────────────────┐
 │  Postgres (4 bases lógicas + RLS + FORCE)    │
 │  Redis (sessions + streams)                  │
 │  MinIO (artifacts + backups)                 │
 │  Prometheus + Grafana + Loki                 │
 └──────────────────────────────────────────────┘
```

Ver detalles en [`docs/architecture.md`](docs/architecture.md).

## Decisiones arquitectónicas recientes

Catálogo completo en [`docs/adr/`](docs/adr/) (43 ADRs numerados). Las mayores cerradas en epics post-piloto:

- **ADR-016** — `TareaPracticaTemplate`: cada cátedra (materia+período) define un template canónico que auto-instancia una `TareaPractica` por cada comisión. `problema_id` del CTR apunta a la instancia (no al template), preservando cadena criptográfica.
- **ADR-018** + **ADR-022/RN-131** — CII evolution longitudinal por `template_id` + alertas predictivas con z-score vs cohorte (privacy gate `MIN_STUDENTS_FOR_QUARTILES=5`).
- **ADR-021/RN-128** — Attestation Ed25519 externa post-cierre de episodio (eventually consistent, SLO 24h, NO bloquea).
- **ADR-023/G8a** — Override temporal de `anotacion_creada` en `LABELER_VERSION=1.1.0` (ventana posicional 120s/60s sobre `event_ts`).
- **ADR-025/G10-A** — `EpisodioAbandonado` con doble trigger idempotente (frontend `beforeunload` + worker server-side scan cada 60s).
- **ADR-029** — Bulk-import de inscripciones centralizado en academic-service.
- **ADR-030, ADR-041** — Deprecación de `enrollment-service` e `identity-service` (preservados en disco con README de deprecation).
- **ADR-033 / ADR-034 / ADR-035 / ADR-036** — Sandbox client-side (Pyodide) + `test_cases` JSONB + reflexión metacognitiva post-cierre + TP-gen IA (todo del epic `ai-native-completion-and-byok`). `LABELER_VERSION` bumpeada a 1.2.0 con regla N3/N4 sobre `tests_ejecutados`.
- **ADR-037 / ADR-038 / ADR-039 / ADR-040** — BYOK multi-provider con AES-256-GCM, resolver jerárquico materia → tenant → env_fallback, helper compartido `packages/platform-ops/.../crypto.py`. Mistral adapter implementado (Gemini diferido).
- **Unidades de trazabilidad** (epic SDD post-piloto) — entidad `Unidad` scoped a `comision_id`, FK nullable `tareas_practicas.unidad_id`, función `compute_evolution_per_unidad()` para trazabilidad longitudinal cuando `template_id=NULL`.

Documentación por servicio en [`docs/servicios/`](docs/servicios/). Verdades operativas y constantes que NO deben cambiarse en [`CLAUDE.md`](CLAUDE.md).

## Empezar

Requisitos: **Python 3.12**, **uv**, **pnpm**, **Docker** (compose v2), **Node 20+**, **make**.

> En Windows: `winget install ezwinports.make` y reiniciar Git Bash. Usar Git Bash o WSL.

### Paso 1 — Bootstrap (primera vez)

```bash
git clone <repo>
cd jr-3-main
make init     # infra Docker + deps + migraciones + seed Casbin
```

### Paso 2 — Levantar infraestructura

Si ya hiciste `make init` antes, solo necesitas levantar los containers:

```bash
make dev-bootstrap
```

Servicios de infraestructura:

| Servicio    | URL                          | Credenciales        |
|-------------|------------------------------|---------------------|
| PostgreSQL  | `localhost:5432`             | postgres/postgres   |
| Keycloak    | `http://localhost:8180`      | admin/admin         |
| Redis       | `localhost:6379`             | —                   |
| MinIO       | `http://localhost:9001`      | minioadmin/minioadmin |
| Grafana     | `http://localhost:3000`      | admin/admin         |
| Prometheus  | `http://localhost:9090`      | —                   |

### Paso 3 — Levantar frontends

```bash
make dev
```

> **Importante**: `make dev` **SÓLO levanta los 3 frontends Vite** (hot-reload via `pnpm turbo dev`). **NO levanta los 12 servicios Python** — para eso, ver el Paso 4. Los frontends van a renderizarse, pero cualquier interacción con la API va a fallar hasta que arranques los backends a mano.

| Frontend      | URL                      |
|---------------|--------------------------|
| web-admin     | `http://localhost:5173`   |
| web-teacher   | `http://localhost:5174`   |
| web-student   | `http://localhost:5175`   |

> Si los puertos estan ocupados, Vite asigna el siguiente disponible. Revisar el log de `make dev`.

### Paso 4 — Levantar servicios backend

Los 11 servicios Python activos se arrancan **cada uno en su propia terminal**, **desde la raíz del repo** (no desde `apps/<svc>/` — `pydantic_settings` busca `.env` relativo al CWD):

```bash
# api-gateway (OBLIGATORIO — única puerta externa de los frontends)
uv run uvicorn api_gateway.main:app --port 8000 --reload

# academic-service
uv run uvicorn academic_service.main:app --port 8002 --reload

# evaluation-service (TP entregas + correcciones — epic tp-entregas-correccion)
uv run uvicorn evaluation_service.main:app --port 8004 --reload

# analytics-service
uv run uvicorn analytics_service.main:app --port 8005 --reload

# tutor-service
uv run uvicorn tutor_service.main:app --port 8006 --reload

# ctr-service
uv run uvicorn ctr_service.main:app --port 8007 --reload

# classifier-service
uv run uvicorn classifier_service.main:app --port 8008 --reload

# content-service
uv run uvicorn content_service.main:app --port 8009 --reload

# governance-service (ver "Prompts del tutor" abajo)
# El repo incluye ai-native-prompts/ con el prompt N4 minimo sembrado;
# en Windows usar ruta absoluta:
PROMPTS_REPO_PATH="$(pwd)/ai-native-prompts" uv run uvicorn governance_service.main:app --port 8010 --reload

# ai-gateway (incluye BYOK resolver — ADRs 038/039/040)
uv run uvicorn ai_gateway.main:app --port 8011 --reload

# integrity-attestation-service (ADR-021 — en piloto vive en VPS UNSL separado;
# en local es opcional, los eventos se acumulan en el stream Redis hasta drenarse)
uv run uvicorn integrity_attestation_service.main:app --port 8012 --reload
```

Para el flujo mínimo (estudiante abre TP y chatea con el tutor) necesitás al menos:
**api-gateway** + **academic-service** + **tutor-service** + **ctr-service** + **governance-service** + **ai-gateway**.

> **Servicios deprecated**: `identity-service` (ADR-041, 2026-05-07) e `enrollment-service` (ADR-030, 2026-04-29) están preservados en disco con README de deprecation pero **fuera del workspace `uv` y del `ROUTE_MAP` del api-gateway**. Auth se resuelve hoy en api-gateway via headers X-* + Casbin descentralizado; bulk-import de inscripciones vive en `academic-service` (ADR-029).

### Paso 5 — Prompts del tutor (governance-service)

El governance-service sirve prompts versionados desde un repo en filesystem (ADR-009). **El repo ya incluye `ai-native-prompts/prompts/tutor/v1.0.0/system.md`** con un prompt N4 mínimo sembrado en sesión 2026-04-23. **No hace falta crearlo** — sólo asegurate de arrancar el governance-service con la env var correcta (ver Paso 4).

Si querés personalizar el prompt, editá `ai-native-prompts/prompts/tutor/v1.0.0/system.md` y reiniciá el governance-service. El hash se recomputa automáticamente y viaja en cada evento CTR como `prompt_system_hash`.

### Paso 6 — Datos demo (opcional, recomendado)

Hay dos seeds complementarios — usar el nuevo para demos de comparación de cohortes:

```bash
# Opción A — Seed básico: 1 comisión, 6 estudiantes, 30 episodios
uv run python scripts/seed-demo-data.py

# Opción B — Seed extendido (RECOMENDADO): 3 comisiones (A-Manana, B-Tarde, C-Noche)
# con 18 estudiantes + 94 episodios + 2 plantillas de TP auto-instanciadas en las 3
# comisiones (demostración completa del ADR-016).
uv run python scripts/seed-3-comisiones.py
```

Ambos son **idempotentes** — se pueden correr repetidas veces. El seed extendido pisa lo que haya dejado el básico si se corre después. Cohortes del seed B están deliberadamente diferenciadas (A=balanceada, B=cohorte fuerte, C=cohorte con dificultades) para que el dashboard de progresión del `web-teacher` muestre patrones distintos.

### Paso 7 — Verificar

```bash
make status        # Estado de containers + health checks
make check-health  # Solo health checks de los 12 servicios
```

### Resumen de URLs

| Servicio | URL | Notas |
|---|---|---|
| web-admin | http://localhost:5173 | Gestion academica |
| web-teacher | http://localhost:5174 | TPs, materiales, progresion |
| web-student | http://localhost:5175 | IDE + tutor socratico |
| API Gateway | http://localhost:8000 | Entrada unica para APIs |
| Grafana | http://localhost:3000 | admin/admin |
| Keycloak | http://localhost:8180 | admin/admin |

### Modo dev sin Keycloak

En desarrollo, el api-gateway corre con `dev_trust_headers=True`. Los frontends inyectan headers
`X-User-Id`, `X-Tenant-Id`, `X-User-Email`, `X-User-Roles` automaticamente via el proxy de Vite.
No necesitas onboardear Keycloak para desarrollo local.

### Gotchas en Windows

- Usar **Git Bash** o **WSL** — el Makefile requiere bash.
- Despues de `winget install ezwinports.make`, **reiniciar Git Bash**.
- Si hay containers Docker de otros proyectos, usar `127.0.0.1` en vez de `localhost` en URLs de servicio (IPv6 dual-stack).
- Si Vite cambia de puerto por colision, revisar el log de `make dev`.

## Ejecutar la suite de tests

```bash
make test              # Python 320 + frontends
make test-fast         # Solo Python, termina en ~25s
make test-rls          # Solo multi-tenant contra Postgres real (requiere CTR_STORE_URL_FOR_RLS_TESTS)
```

## Estructura del repo

```
platform/
├── apps/                              # 11 servicios activos + 3 frontends + 2 deprecated
│   ├── api-gateway/                   # JWT RS256 + headers X-* + ROUTE_MAP
│   ├── academic-service/              # Universidad→Comisión + TPs + Casbin (131 policies)
│   ├── analytics-service/             # Kappa, progresión, longitudinal, alertas, governance UI
│   ├── tutor-service/                 # Orquestador socrático (SSE) + reflexión + abandonment worker
│   ├── ctr-service/                   # CTR append-only SHA-256 + alias /audit/* (ADR-031)
│   ├── classifier-service/            # Árbol N4 + 5 coherencias + labeler v1.2.0
│   ├── content-service/               # Materiales + RAG (pgvector + chunker estratificado)
│   ├── governance-service/            # Prompts versionados (FS Git) + tp_generator/v1.0.0
│   ├── ai-gateway/                    # LLM proxy + BYOK multi-provider (ADRs 038-040) + Mistral
│   ├── evaluation-service/            # Entregas + calificación (epic tp-entregas-correccion)
│   ├── integrity-attestation-service/ # Attestation Ed25519 externa (ADR-021)
│   ├── identity-service/              # DEPRECATED (ADR-041) — preservado en disco
│   ├── enrollment-service/            # DEPRECATED (ADR-030) — preservado en disco
│   ├── web-admin/                     # Gestión institucional + Auditoría + BYOK + Governance UI
│   ├── web-teacher/                   # TanStack Router + 3 vistas G7 (ADR-022) + drill-down
│   └── web-student/                   # React + Monaco + Pyodide + 3-cols + reflexión modal
│
├── packages/
│   ├── contracts/                     # Schemas + hashing canónico (cross-package fix 2026-05-04)
│   ├── observability/                 # OTel + structlog + helper de health checks reales
│   ├── platform-ops/                  # Privacy, Kappa, longitudinal, alertas, crypto AES-GCM
│   ├── ctr-client/                    # Cliente tipado del ctr-service
│   ├── auth-client/                   # keycloak-js + authenticated fetch
│   ├── ui/                            # Componentes React compartidos + tokens "Stack Blue"
│   └── test-utils/                    # Helpers de testing
│
├── infrastructure/                    # docker-compose.dev.yml + observability configs
├── ops/
│   ├── k8s/                           # Manifests K8s + canary Argo Rollouts
│   └── grafana/                       # Dashboards + provisioning
│
├── docs/
│   ├── architecture.md                # Diseño general
│   ├── adr/                           # 43 ADRs numerados (incluyendo 9 diferidos para piloto-2)
│   ├── servicios/                     # 1 .md por servicio activo + integrity-attestation
│   ├── specs/                         # historias.md, reglas.md, bulk-import-csv-format.md
│   ├── research/                      # audi1/2.md, BUGS-PILOTO.md, CHANGELOGs, plan-b2-jwt-...
│   ├── phases/                        # F0–F9 STATE.md (log incremental de fases)
│   ├── pilot/                         # Protocolo UNSL (DOCX), runbook, analysis-template.ipynb
│   ├── golden-queries/                # Queries de evaluación RAG
│   ├── onboarding.md                  # Guía para nuevos devs
│   └── SESSION-LOG.md                 # Bitácora narrativa cross-sesión
│
├── ai-native-prompts/                 # Prompts versionados (consumidos por governance-service)
├── examples/                          # Scripts runnable de bootstrap UNSL
├── scripts/                           # bash + python (migrate-all, backup, eval-retrieval, etc.)
├── tests/                             # Smoke E2E (epic tests-smoke)
├── CLAUDE.md                          # Verdades operativas + invariantes (source of truth)
├── PRODUCT.md / DESIGN.md             # Identidad + tokens visuales (post-impeccable)
├── Makefile                           # Orquestación (defaults dev: EMBEDDER=mock, etc.)
└── README.md                          # (este archivo)
```

## Workflows comunes

### Crear un tenant nuevo (ej. UNSL)

```bash
export KEYCLOAK_ADMIN_PASSWORD=admin
export LDAP_BIND_PASSWORD=secret
export TENANT_ADMIN_EMAIL=admin@unsl.edu.ar
make onboard-unsl
```

### Análisis empírico del piloto

```bash
# Progresión longitudinal de una cohorte
make progression COMISION=aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa

# Kappa inter-rater (requiere archivo con ratings)
make kappa FILE=ratings.json

# Export académico anonymizado
make export-academic COMISION=<uuid> SALT=mi-salt-de-investigacion-2026
```

O desde el frontend docente en http://localhost:5176.

### Backup y restore

```bash
PG_BACKUP_PASSWORD=xxx make backup
make restore DIR=/var/backups/platform/2026-04-20
```

### Regenerar el protocolo del piloto

```bash
make generate-protocol
# → docs/pilot/protocolo-piloto-unsl.docx
```

### Correr un análisis estadístico sobre los datos del piloto

```bash
jupyter notebook docs/pilot/analysis-template.ipynb
# Editar DATASET_PATH y correr todas las celdas
```

## Documentación por rol

### Si sos **docente participante** del piloto UNSL

1. Leer [`docs/pilot/README.md`](docs/pilot/README.md) — operativa diaria
2. Entrar a http://localhost:5174 — panel docente
3. Ante un incidente: [`docs/pilot/runbook.md`](docs/pilot/runbook.md)

### Si sos **desarrollador nuevo** contribuyendo al código

1. Leer [`docs/onboarding.md`](docs/onboarding.md)
2. Ejecutar `make init` para entorno local
3. Revisar [`docs/servicios/`](docs/servicios/) para entender cada microservicio
4. Revisar [`docs/adr/`](docs/adr/) para decisiones arquitectónicas clave (43 ADRs)
5. Leer [`CLAUDE.md`](CLAUDE.md) para invariantes y constantes que NO deben cambiarse
6. [`CONTRIBUTING.md`](CONTRIBUTING.md) para el workflow de contribución

### Si sos **investigador** analizando los datos

1. Leer [`docs/pilot/protocolo-piloto-unsl.docx`](docs/pilot/protocolo-piloto-unsl.docx)
2. Descargar dataset: `make export-academic` o desde la UI docente
3. Usar [`docs/pilot/analysis-template.ipynb`](docs/pilot/analysis-template.ipynb)

### Si sos **ops** desplegando la plataforma

1. Configurar secrets (`.env` desde `.env.example`)
2. Aplicar migraciones: `make migrate` (ver [`scripts/migrate-all.sh`](scripts/migrate-all.sh))
3. Verificar RLS: `make check-rls`
4. Montar dashboards Grafana: ya auto-provisiona desde
   [`ops/grafana/provisioning/`](ops/grafana/provisioning/)
5. Configurar canary: [`ops/k8s/canary-tutor-service.yaml`](ops/k8s/canary-tutor-service.yaml)

## Propiedades críticas preservadas

Este repo encarna decisiones arquitectónicas específicas, verificadas
por tests automatizados. **Al modificar código, respetar**:

- **CTR append-only** — nunca UPDATE/DELETE de eventos. Reclasificar =
  marcar viejo con `is_current=false` + INSERT nuevo.
- **RLS multi-tenant** — toda tabla con `tenant_id` debe tener policy
  activa. `make check-rls` lo verifica.
- **api-gateway como único source of truth de identidad** — los
  servicios internos confían en los headers X-* del gateway.
- **Hash determinista del classifier_config_hash** — reproducibilidad
  bit a bit verificada con test de integración.
- **Preservar las 5 coherencias separadas** (CT, CCD_mean,
  CCD_orphan_ratio, CII_stability, CII_evolution) — nunca colapsar en
  un score único.
- **Write-only al CTR desde tutor-service**, excepto `codigo_ejecutado`
  que usa el `user_id` del estudiante autenticado.
- **Salt mínimo 16 chars** en export académico, `include_prompts=False`
  por default.
- **LDAP federation READ_ONLY** — la plataforma nunca modifica el
  directorio institucional.

## Fases del desarrollo

El monorepo se construyó incrementalmente en 10 fases (F0–F9) más epics post-piloto. Cada fase tiene su doc de estado en [`docs/phases/`](docs/phases/).

| Fase | Alcance |
|---|---|
| F0 | Monorepo semilla (servicios + frontends + CI + docs) |
| F1 | academic-service + enrollment-service (RLS + Casbin) — enrollment luego deprecado |
| F2 | content-service con RAG (pgvector + chunker estratificado) |
| F3 | ctr-service (cadena cripto) + classifier + tutor + ai-gateway |
| F4 | Hardening: SLOs, rate limiting, integrity checker |
| F5 | Multi-tenant producción: JWT, onboarding, privacy, Pyodide |
| F6 | Piloto UNSL: feature flags runtime, Kappa, audit, LDAP, canary |
| F7 | Empírico: longitudinal, A/B profiles, export worker |
| F8 | Adaptadores DB reales + frontend docente + Grafana + protocolo DOCX |
| F9 | Preflight operacional: RLS migrations, runbook, notebook |

### Epics post-F9 cerrados

| Epic | Alcance |
|---|---|
| `tp-entregas-correccion` | evaluation-service implementado: 8 endpoints REST, audit log, RLS forzada |
| `ai-native-completion-and-byok` | Reflexión post-cierre + sandbox client-side + test_cases JSONB + TP-gen IA + BYOK multi-provider (ADRs 033-040) |
| `real-health-checks` | Health checks reales en los 11 servicios via helper compartido en `packages/observability` |
| `unidades-trazabilidad` | Entidad `Unidad` para trazabilidad longitudinal cuando `template_id=NULL` |
| `tests-smoke` | Suite E2E de 32 smoke tests contra stack real en `tests/e2e/smoke/` (red de seguridad) |

## Licencia

Ver [`LICENSE`](LICENSE).

## Contacto

- **Investigador principal**: Alberto Alejandro Cortez · UNSL
- **Dudas del código**: issues del repo
- **Comité de ética UNSL**: cei@unsl.edu.ar
