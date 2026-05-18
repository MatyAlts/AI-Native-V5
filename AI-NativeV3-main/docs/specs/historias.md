# Historias de Usuario — Plataforma AI-Native N4 (Piloto UNSL)

**Autor**: Alberto Alejandro Cortez
**Contexto**: Tesis doctoral UNSL — "Modelo AI-Native con Trazabilidad Cognitiva N4 para la Formación en Programación Universitaria"
**Versión del documento**: 1.0
**Fecha**: 2026-04-20

---

## Resumen de cobertura

- **Total de historias de usuario**: 124
- **Distribución por fase**:
  - F0 (Fundaciones e Infraestructura): 10
  - F1 (Dominio Académico): 12
  - F2 (RAG + Contenido): 11
  - F3 (Motor Pedagógico): 18
  - F4 (Hardening + SLOs): 10
  - F5 (Producción Multi-tenant + Privacy + Pyodide): 12
  - F6 (Integración UNSL + LDAP + Canary): 12
  - F7 (Empírico): 8
  - F8 (DB Reales + Frontend Docente + Grafana + Protocolo): 10
  - F9 (Preflight): 8
  - Transversales por actor: 7
  - Invariantes críticos: 6
- **Distribución por actor principal**:
  - Estudiante: 18
  - Docente: 19
  - Docente Admin: 6
  - Superadmin / Admin UNSL: 11
  - Investigador / Tesista: 11
  - Operador (Ops): 17
  - Auditor Académico: 9
  - Sistema (service-accounts): 20
  - Plataforma (transversal): 13

---

## Índice

- [Actores del sistema](#actores-del-sistema)
- [Convenciones](#convenciones)
- [Fase F0 — Fundaciones e Infraestructura](#fase-f0--fundaciones-e-infraestructura)
- [Fase F1 — Dominio Académico](#fase-f1--dominio-académico)
- [Fase F2 — RAG + Contenido](#fase-f2--rag--contenido)
- [Fase F3 — Motor Pedagógico](#fase-f3--motor-pedagógico)
- [Fase F4 — Hardening + SLOs](#fase-f4--hardening--slos)
- [Fase F5 — Producción Multi-tenant + Privacy + Pyodide](#fase-f5--producción-multi-tenant--privacy--pyodide)
- [Fase F6 — Integración UNSL + LDAP + Canary](#fase-f6--integración-unsl--ldap--canary)
- [Fase F7 — Empírico](#fase-f7--empírico)
- [Fase F8 — DB Reales + Frontend Docente + Grafana + Protocolo](#fase-f8--db-reales--frontend-docente--grafana--protocolo)
- [Fase F9 — Preflight](#fase-f9--preflight)
- [Historias transversales por actor](#historias-transversales-por-actor)
- [Historias de invariantes críticos](#historias-de-invariantes-críticos)
- [Trazabilidad](#trazabilidad)

---

## Actores del sistema

| Rol | Descripción |
|-----|-------------|
| Estudiante | Usuario final del piloto UNSL. Resuelve consignas con tutor socrático, ejecuta código Python en Pyodide dentro del navegador, visualiza su clasificación N4. |
| Docente | Responsable de cátedra de Programación. Observa progresión de la cohorte, etiqueta episodios para cálculo de Kappa, configura A/B testing de perfiles de referencia, exporta datasets. |
| Docente Admin | Responsable de gestión académica de la universidad. Administra comisiones, inscripciones por CSV, correlatividades y períodos. |
| Superadmin | Administrador global de la plataforma. Gestiona universidades, realms Keycloak, policies Casbin y configuración de tenants. |
| Admin UNSL | Administrador institucional del piloto. Ejecuta onboarding del tenant UNSL, configura federación LDAP y activa feature flags pedagógicos. |
| Investigador / Tesista | Usa datasets anonimizados para análisis cuantitativos (κ de Cohen, progresión longitudinal, correlaciones) y contrasta hipótesis de la tesis. |
| Operador (Ops) | Responsable de infraestructura y confiabilidad. Opera Helm, monitoriza Grafana, ejecuta runbook de incidentes, administra backups. |
| Auditor Académico | Verifica integridad de la cadena CTR, monitorea Kappa y detecta anomalías de seguridad o de manipulación. |
| Tutor-Service (service-account) | Emite eventos CTR, consulta contenido, invoca ai-gateway para LLM. |
| Classifier-Worker (service-account) | Consume episodios, calcula las cinco coherencias y genera clasificación N4. |
| Sistema / Plataforma | Conjunto de invariantes transversales que la propia plataforma debe mantener sin intervención humana. |

---

## Convenciones

- **Numeración**: HU-XXX, secuencial, sin saltos.
- **Prioridades**:
  - **Crítica**: protege invariantes del sistema (CTR append-only, RLS, identidad, reproducibilidad) o ejes éticos (consentimiento, privacidad, LDAP read-only).
  - **Alta**: capacidad funcional principal del piloto (tutor socrático, clasificador N4, export académico, RAG).
  - **Media**: dashboards, análisis longitudinal y operaciones corrientes.
  - **Baja**: mejoras de experiencia del desarrollador y observabilidad fina.
- **Criterios de aceptación**: redactados como enunciados verificables por test automatizado o inspección directa. Cada historia incluye entre tres y seis criterios.
- **Invariantes afectados**: se listan cuando la historia toca alguno de los doce invariantes críticos del sistema. La matriz completa figura en la sección final.
- **Referencias a ADRs**: cuando la historia deriva de una decisión arquitectónica formal, se cita el ADR correspondiente.

---

## Fase F0 — Fundaciones e Infraestructura

### HU-001 — Inicialización del monorepo híbrido Python + TypeScript
**Actor**: Operador (Ops)
**Fase**: F0
**Servicio(s)**: repositorio raíz, packages compartidos
**Prioridad**: Crítica

**Historia**:
Como operador, quiero inicializar el monorepo con `make init` en una máquina limpia, para obtener un entorno de desarrollo funcional sin configuración manual adicional.

**Criterios de aceptación**:
- `make init` ejecuta docker compose up, uv sync, pnpm install, migraciones y seed de Casbin sin errores.
- La primera sincronización `uv sync --all-packages` completa en un tiempo razonable y deja los doce servicios Python instalables.
- `pnpm install` resuelve los tres frontends y los cinco packages TypeScript compartidos.
- Al finalizar, `make status` muestra los doce servicios y la infraestructura en estado saludable.

**Invariantes afectados**: ninguno directo (habilita el resto).

---

### HU-002 — Scaffolding de los doce servicios FastAPI
**Actor**: Sistema
**Fase**: F0
**Servicio(s)**: todos los apps/* Python
**Prioridad**: Alta

**Historia**:
Como plataforma, quiero que los doce servicios Python compartan una estructura homogénea (`src/<svc>/{routes,services,auth}`, `tests/{unit,integration}`, `pyproject.toml` con hatchling), para que cualquier agente o desarrollador nuevo pueda navegar cualquier servicio con el mismo modelo mental.

**Criterios de aceptación**:
- Cada servicio expone un endpoint `/health` que responde 200.
- Cada servicio declara `structlog` y `OpenTelemetry` como dependencias base.
- El layout de directorios coincide entre los doce servicios y es verificable por script de auditoría.
- `conftest.py` raíz agrega automáticamente los `src/` de cada servicio al `sys.path`.

---

### HU-003 — Paquetes TypeScript compartidos
**Actor**: Sistema
**Fase**: F0
**Servicio(s)**: packages/ui, auth-client, ctr-client, observability, platform-ops
**Prioridad**: Alta

**Historia**:
Como plataforma, quiero contar con cinco packages TypeScript compartidos, para evitar duplicación entre los tres frontends y garantizar consistencia de componentes, autenticación y clientes CTR.

**Criterios de aceptación**:
- Cada package expone su API mediante `package.json` con `exports` tipado.
- Los tres frontends (`web-student`, `web-teacher`, `web-admin`) consumen los packages sin relative imports cruzados.
- `turbo build` reconstruye incrementalmente solo los packages cambiados.
- Biome lint pasa en los cinco packages sin warnings bloqueantes.

---

### HU-004 — Levantamiento de infraestructura local por docker compose
**Actor**: Operador (Ops)
**Fase**: F0
**Servicio(s)**: infrastructure/docker-compose.dev.yml
**Prioridad**: Crítica

**Historia**:
Como operador, quiero un stack local completo (Postgres+pgvector, Keycloak, Redis, MinIO, OTel Collector, Jaeger, Prometheus, Loki, Grafana), para desarrollar y depurar sin depender de recursos cloud.

**Criterios de aceptación**:
- `make dev-bootstrap` deja toda la infraestructura saludable en menos de tres minutos.
- Los puertos de cada servicio están documentados y no colisionan con los de la plataforma.
- Grafana arranca con datasources preprovisionados contra Prometheus y Loki.
- El stack completo consume aproximadamente 4 GB de RAM, documentado en el CLAUDE.md.

---

### HU-005 — Aislamiento multi-tenant por Row-Level Security base
**Actor**: Sistema
**Fase**: F0
**Servicio(s)**: infrastructure/postgres, migrations
**Prioridad**: Crítica

**Historia**:
Como plataforma, quiero que toda tabla con columna `tenant_id` declare `ROW LEVEL SECURITY` activo desde la primera migración, para cumplir el invariante de aislamiento multi-tenant (ADR-001).

**Criterios de aceptación**:
- `make check-rls` falla si alguna tabla con `tenant_id` carece de policy RLS.
- El gate corre en CI y bloquea merge en caso de violación.
- Las políticas utilizan `current_setting('app.current_tenant')` como predicado.
- Toda nueva migración que introduzca `tenant_id` obliga a test RLS en el mismo PR.

**Invariantes afectados**: RLS multi-tenant FORCE.

---

### HU-006 — Contratos Pydantic + Zod para los veinte eventos base
**Actor**: Sistema
**Fase**: F0
**Servicio(s)**: packages/contracts
**Prioridad**: Alta

**Historia**:
Como plataforma, quiero que los quince eventos CTR y los cinco eventos académicos estén definidos en Pydantic (Python) y Zod (TypeScript) dentro de `packages/contracts`, para garantizar serialización canónica idéntica entre productores y consumidores.

**Criterios de aceptación**:
- Cada evento tiene schema Pydantic v2 y schema Zod equivalente.
- Existe test de serialización que valida igualdad de JSON canónico entre ambas implementaciones.
- Cambios de contrato obligan a actualizar ambas implementaciones en el mismo PR.
- El contrato se publica como dependencia para los doce servicios Python y los tres frontends.

---

### HU-007 — Hash SHA-256 sobre JSON canonicalizado
**Actor**: Sistema
**Fase**: F0
**Servicio(s)**: packages/contracts
**Prioridad**: Crítica

**Historia**:
Como plataforma, quiero una función de hashing canónico SHA-256 sobre JSON con ordenamiento determinista de claves, para que la cadena CTR y el `classifier_config_hash` sean reproducibles bit-a-bit.

**Criterios de aceptación**:
- La función ordena claves recursivamente y normaliza tipos numéricos.
- El hash de un evento idéntico produce siempre el mismo dígest en Python y en TypeScript.
- Existe test que cruza la implementación Python con la TypeScript sobre los mismos inputs.
- La implementación documenta explícitamente el tratamiento de `null`, booleanos y floats.

**Invariantes afectados**: CTR append-only; reproducibilidad bit-a-bit.

---

### HU-008 — Health checks y readiness por servicio
**Actor**: Operador (Ops)
**Fase**: F0
**Servicio(s)**: todos los servicios
**Prioridad**: Alta

**Historia**:
Como operador, quiero un endpoint `/health` por servicio que verifique dependencias críticas (DB, Redis, bus), para diagnosticar rápido el estado real del stack.

**Criterios de aceptación**:
- `/health` responde 200 solo cuando las dependencias declaradas responden.
- `make check-health` recorre los doce servicios y reporta estado consolidado.
- En caso de dependencia caída, el servicio retorna 503 con detalle del subsistema afectado.
- Kubernetes readiness y liveness probes consumen el mismo endpoint.

---

### HU-009 — Pipeline de CI con gates duros
**Actor**: Operador (Ops)
**Fase**: F0
**Servicio(s)**: .github/workflows/ci.yml
**Prioridad**: Crítica

**Historia**:
Como operador, quiero que cada PR pase por `ruff`, `mypy --strict`, `tsc`, `pytest` (unit + integration), `make check-rls`, dry-run de migraciones y reporte a Codecov, para impedir merges que rompan invariantes o reduzcan cobertura.

**Criterios de aceptación**:
- El workflow falla ante cualquiera de los siete gates.
- Coverage debe superar 80% global y 85% en el plano pedagógico.
- El reporte de CI identifica claramente qué gate falló.
- El job se ejecuta en menos de quince minutos en promedio.

---

### HU-010 — Seguridad de imágenes con Trivy
**Actor**: Operador (Ops)
**Fase**: F0
**Servicio(s)**: .github/workflows/ci.yml
**Prioridad**: Alta

**Historia**:
Como operador, quiero que cada imagen Docker se escanee con Trivy en CI, para detectar vulnerabilidades de alta severidad antes de promover a staging.

**Criterios de aceptación**:
- El job Trivy bloquea el merge ante CVEs HIGH o CRITICAL no ignoradas explícitamente.
- Las excepciones quedan documentadas en un archivo de ignore versionado.
- El reporte se adjunta como artifact del PR.
- La base de datos de vulnerabilidades se actualiza en cada corrida.

---

## Fase F1 — Dominio Académico

### HU-011 — Modelado de las once entidades académicas
**Actor**: Sistema
**Fase**: F1
**Servicio(s)**: academic-service
**Prioridad**: Crítica

**Historia**:
Como plataforma, quiero modelar Universidad, Facultad, Carrera, PlanEstudios, Materia, Período, Comisión, Inscripción, UsuarioComisión, AuditLog y CasbinRule, para sostener el dominio académico del piloto UNSL.

**Criterios de aceptación**:
- Cada entidad tiene tabla SQLAlchemy 2.0 con `tenant_id` y policy RLS.
- Las relaciones (Carrera→PlanEstudios→Materia, Período→Comisión→Inscripción) están declaradas con FKs y cascadas explícitas.
- La migración Alembic inicial genera las once tablas más sus policies en una sola revisión reversible.
- Existen tests que validan constraints de unicidad y de integridad referencial.

**Invariantes afectados**: RLS multi-tenant.

---

### HU-012 — Seed de policies Casbin RBAC-con-dominios
**Actor**: Superadmin
**Fase**: F1
**Servicio(s)**: academic-service, identity-service
**Prioridad**: Crítica

**Historia**:
Como superadmin, quiero cargar las policies Casbin iniciales que cubran los cuatro roles (estudiante, docente, docente_admin, superadmin) por todos los recursos definidos en el seed, para que la autorización quede completamente declarada antes del primer login. El count exacto evoluciona con nuevas entidades — ver RN-018 actualizada.

**Criterios de aceptación**:
- `make seed-casbin` deja todas las filas de la lista `POLICIES` (`apps/academic-service/src/academic_service/seeds/casbin_policies.py`) en `casbin_rule` sin duplicados; la fuente de verdad del count es el código del seed.
- Cada combinación `rol × recurso × acción` está cubierta o explícitamente denegada.
- Las policies se cargan bajo el modelo `rbac_with_domains` con `tenant_id` como dominio.
- El comando es idempotente: correrlo dos veces no duplica filas.

---

### HU-013 — Context manager `tenant_session` con SET LOCAL
**Actor**: Sistema
**Fase**: F1
**Servicio(s)**: packages/test-utils, academic-service
**Prioridad**: Crítica

**Historia**:
Como plataforma, quiero un context manager `tenant_session()` que ejecute `SET LOCAL app.current_tenant = :tid` por request, para que todas las queries respeten RLS sin intervención manual del desarrollador.

**Criterios de aceptación**:
- Al entrar al context, `SET LOCAL` se emite en la misma transacción que el SELECT/INSERT.
- Al salir, la sesión vuelve a estado sin tenant configurado.
- Un request sin `tenant_id` falla por default en lugar de abrir un canal sin filtro.
- Existe test que verifica aislamiento entre dos tenants en transacciones concurrentes.

**Invariantes afectados**: RLS multi-tenant FORCE.

---

### HU-014 — BaseRepository genérico para el dominio
**Actor**: Sistema
**Fase**: F1
**Servicio(s)**: academic-service
**Prioridad**: Media

**Historia**:
Como plataforma, quiero un `BaseRepository[T]` genérico con CRUD tipado, para reducir duplicación y uniformar acceso a datos en los servicios académicos.

**Criterios de aceptación**:
- El repositorio expone `get`, `list`, `create`, `update`, `delete` tipados.
- Todas las operaciones se ejecutan dentro de `tenant_session()`.
- Los tests unitarios cubren el caso de `tenant_id` cruzado (debe retornar vacío).
- `mypy --strict` pasa sobre el módulo.

---

### HU-015 — Validación de dominio: período abierto y correlatividades
**Actor**: Docente Admin
**Fase**: F1
**Servicio(s)**: academic-service
**Prioridad**: Alta

**Historia**:
Como docente admin, quiero que las inscripciones se rechacen si el período está cerrado o si faltan correlatividades, para mantener la integridad académica del plan de estudios.

**Criterios de aceptación**:
- El servicio valida `Periodo.estado == abierto` antes de crear `Inscripcion`.
- El servicio valida que todas las correlatividades `aprobadas` estén registradas.
- Errores retornan 422 con mensaje descriptivo y código interno.
- Existen tests que cubren ambos caminos negativos y el camino feliz.

---

### HU-016 — Decorador `require_permission` basado en Casbin
**Actor**: Sistema
**Fase**: F1
**Servicio(s)**: academic-service, identity-service
**Prioridad**: Crítica

**Historia**:
Como plataforma, quiero un decorador `@require_permission(recurso, acción)` para proteger endpoints, de modo que la autorización quede declarada junto al handler.

**Criterios de aceptación**:
- El decorador consulta Casbin con `tenant_id`, `user_id`, `recurso` y `acción`.
- Una denegación retorna 403 sin exponer la razón interna.
- Las consultas a Casbin usan cache con invalidación explícita ante cambios de policy.
- Existe test matriz (`test_casbin_matrix.py`, 23/23) que cubre los roles definidos en el seed; el count exacto evoluciona con nuevas entidades — ver RN-018 actualizada.

---

### HU-017 — AuditLog transaccional por cambio de dominio
**Actor**: Auditor Académico
**Fase**: F1
**Servicio(s)**: academic-service
**Prioridad**: Alta

**Historia**:
Como auditor, quiero que toda operación de escritura sobre el dominio académico genere un `AuditLog` dentro de la misma transacción, para tener trazabilidad fiable de cambios administrativos.

**Criterios de aceptación**:
- El `AuditLog` registra `user_id`, `tenant_id`, `entidad`, `entidad_id`, `acción`, `diff` y timestamp.
- Si la transacción hace rollback, el `AuditLog` también se revierte (consistencia).
- El diff persiste las columnas que cambiaron, no el snapshot completo.
- Existe test que valida escritura consistente bajo fallo simulado.

---

### HU-018 — Migración Alembic inicial autogenerada y revisada
**Actor**: Operador (Ops)
**Fase**: F1
**Servicio(s)**: academic-service
**Prioridad**: Alta

**Historia**:
Como operador, quiero una única migración Alembic inicial que cree las diez tablas de dominio más policies RLS, para que cualquier ambiente parta del mismo estado base.

**Criterios de aceptación**:
- La revisión se ejecuta en limpio sin errores.
- La revisión es reversible (downgrade vuelve a estado vacío).
- `make migrate` aplica la revisión a las tres bases según corresponda.
- La revisión está anotada con descripción humana del cambio.

---

### HU-019 — Importación de inscripciones por CSV con dry-run y commit
**Actor**: Docente Admin
**Fase**: F1
**Servicio(s)**: academic-service
**Prioridad**: Alta

**Historia**:
Como docente admin, quiero subir un CSV de inscripciones a una comisión y ejecutar primero un `dry-run`, para ver conflictos antes de confirmar los cambios reales.

**Criterios de aceptación**:
- El endpoint acepta `mode=dry_run` y `mode=commit` explícitos.
- El dry-run reporta filas válidas, filas con error (con motivo) y resumen de conteo.
- El commit aplica solo las filas válidas y genera `AuditLog` por cada inserción.
- Un CSV con UTF-8 BOM o delimitadores no estándar es rechazado con error claro.

---

### HU-020 — Crear y administrar comisiones universitarias
**Actor**: Docente Admin
**Fase**: F1
**Servicio(s)**: academic-service
**Prioridad**: Alta

**Historia**:
Como docente admin, quiero crear, editar y cerrar comisiones asociadas a una materia y un período, para operar las cátedras durante el piloto.

**Criterios de aceptación**:
- Una comisión se asocia a exactamente una materia y un período.
- No se puede editar una comisión en período cerrado.
- Cerrar una comisión impide nuevas inscripciones pero mantiene datos históricos.
- Los cambios quedan registrados en `AuditLog`.

---

### HU-021 — Suite de 40 tests de dominio académico
**Actor**: Sistema
**Fase**: F1
**Servicio(s)**: academic-service
**Prioridad**: Media

**Historia**:
Como plataforma, quiero al menos cuarenta tests que cubran las reglas de dominio académico, para dar evidencia de correctitud antes de abrir el dominio al resto de los servicios.

**Criterios de aceptación**:
- Se cubren validaciones de dominio, aislamiento RLS, Casbin y AuditLog.
- La suite corre en menos de un minuto en la pipeline.
- Coverage del servicio supera 85%.
- Cada test tiene nombre descriptivo en español neutro.

---

### HU-022 — Consultar inscripciones y constancias desde el frontend de docente admin
**Actor**: Docente Admin
**Fase**: F1
**Servicio(s)**: academic-service, web-admin
**Prioridad**: Media

**Historia**:
Como docente admin, quiero consultar inscripciones y emitir constancias simples, para dar soporte a consultas de estudiantes durante el piloto.

**Criterios de aceptación**:
- La búsqueda filtra por DNI, legajo o comisión.
- Los resultados respetan RLS (solo la universidad del docente admin).
- La constancia se descarga como PDF con hash de verificación.
- Las consultas quedan en `AuditLog`.

---

## Fase F2 — RAG + Contenido

### HU-023 — Ingesta de materiales por tipo (Markdown, PDF, ZIP de código, texto)
**Actor**: Docente
**Fase**: F2
**Servicio(s)**: content-service
**Prioridad**: Alta

**Historia**:
Como docente, quiero subir materiales de cátedra en formatos Markdown, PDF, ZIP con código y texto plano, para alimentar la base RAG del tutor.

**Criterios de aceptación**:
- El servicio acepta los cuatro tipos y rechaza otros con 415.
- El ZIP de código soporta trece lenguajes (al menos Python, JS, TS, Java, C, C++, Go, Rust, Ruby, PHP, Kotlin, Swift, Scala).
- Cada material genera su registro en la tabla `Material` con metadatos.
- La subida queda asociada a una comisión específica.

---

### HU-024 — Extracción de `heading_path` en Markdown
**Actor**: Sistema
**Fase**: F2
**Servicio(s)**: content-service
**Prioridad**: Alta

**Historia**:
Como plataforma, quiero extraer la jerarquía de encabezados (`heading_path`) al procesar Markdown, para que cada chunk conserve contexto semántico.

**Criterios de aceptación**:
- Un encabezado `# A > ## B > ### C` queda como `["A","B","C"]` en los chunks que le siguen.
- La extracción respeta saltos a niveles superiores.
- El test cubre tres niveles de anidamiento y encabezados malformados.
- El `heading_path` se persiste como JSONB en la tabla `Chunk`.

---

### HU-025 — Chunking estratificado: código por función, prosa por ventana
**Actor**: Sistema
**Fase**: F2
**Servicio(s)**: content-service
**Prioridad**: Alta

**Historia**:
Como plataforma, quiero que el chunker trate el código fuente a nivel de función (aproximadamente 1500 tokens) y la prosa con ventana deslizante de 512 tokens con overlap de 50, para preservar granularidad apropiada a cada tipo de contenido.

**Criterios de aceptación**:
- Un archivo Python con cinco funciones produce cinco chunks de función.
- Un texto largo produce chunks de 512 tokens con solapamiento de 50.
- Los tokens se cuentan con el tokenizador del embedder configurado.
- Existe test para archivos de código sin funciones (fallback a ventana).

---

### HU-026 — Embedders intercambiables (Mock y SentenceTransformer)
**Actor**: Sistema
**Fase**: F2
**Servicio(s)**: content-service
**Prioridad**: Alta

**Historia**:
Como plataforma, quiero dos implementaciones intercambiables del embedder (MockEmbedder basado en SHA-512 y SentenceTransformer `multilingual-e5-large`), para correr tests deterministas sin GPU y producción con embeddings reales.

**Criterios de aceptación**:
- El default de test es `EMBEDDER=mock` y no requiere red.
- El MockEmbedder produce vectores de 1024 dimensiones derivados de SHA-512.
- El SentenceTransformer respeta la convención `passage:` / `query:` de e5.
- Un switch por variable de entorno determina qué implementación se usa.

---

### HU-027 — Rerankers intercambiables (Identity y CrossEncoder)
**Actor**: Sistema
**Fase**: F2
**Servicio(s)**: content-service
**Prioridad**: Media

**Historia**:
Como plataforma, quiero rerankers intercambiables (`IdentityReranker` para tests y `CrossEncoderReranker` con `bge-reranker-base`), para ajustar calidad de retrieval sin modificar el código cliente.

**Criterios de aceptación**:
- `RERANKER=identity` preserva el orden original.
- `RERANKER=crossencoder` recalcula scores contra el query.
- La interfaz `rerank(query, docs) -> list[doc]` es común a ambas.
- Existe test comparativo sobre un set fijo.

---

### HU-028 — Almacenamiento de archivos pluggable (Mock y S3)
**Actor**: Sistema
**Fase**: F2
**Servicio(s)**: content-service
**Prioridad**: Media

**Historia**:
Como plataforma, quiero un backend de storage abstracto con implementaciones Mock (filesystem local) y S3 (MinIO en dev, S3 en prod), para desacoplar la ingesta de la infraestructura concreta.

**Criterios de aceptación**:
- La interfaz expone `put`, `get`, `delete` y `presign`.
- `STORAGE=mock` escribe en `/tmp` y no requiere servicios externos.
- `STORAGE=s3` respeta credenciales desde variables de entorno.
- Existe test de contrato compartido entre ambas implementaciones.

---

### HU-029 — Retrieval con doble filtro RLS + comisión explícita
**Actor**: Sistema
**Fase**: F2
**Servicio(s)**: content-service
**Prioridad**: Crítica

**Historia**:
Como plataforma, quiero que toda query de retrieval aplique simultáneamente RLS por `tenant_id` y `WHERE comision_id = :cid`, para evitar filtración cross-comisión aún si una policy RLS fuera mal configurada.

**Criterios de aceptación**:
- El repositorio nunca emite una query sin `WHERE comision_id`.
- Existe test que verifica que omitir el filtro explícito falla.
- Test de aislamiento cross-tenant contra Postgres real pasa.
- La defensa en profundidad está documentada en el código.

**Invariantes afectados**: doble filtro retrieval (RLS + WHERE comision_id); RLS multi-tenant.

---

### HU-030 — pgvector con IVFFlat y cosine similarity
**Actor**: Sistema
**Fase**: F2
**Servicio(s)**: content-service
**Prioridad**: Alta

**Historia**:
Como plataforma, quiero que la columna `embedding vector(1024)` tenga índice IVFFlat con `lists=100` y operador `<=>`, para que la búsqueda de similitud escale con la cohorte UNSL.

**Criterios de aceptación**:
- La migración crea el índice IVFFlat tras insertar datos suficientes.
- El operador `<=>` se usa consistentemente.
- La query top-20 responde en menos de 200 ms para un corpus del piloto.
- El ADR-011 cita esta decisión y queda referenciado.

---

### HU-031 — Pipeline top-20 → rerank → top-5 con `chunks_used_hash`
**Actor**: Sistema
**Fase**: F2
**Servicio(s)**: content-service, tutor-service
**Prioridad**: Crítica

**Historia**:
Como plataforma, quiero que retrieval traiga top-20 candidatos, los rerankee y devuelva top-5 junto con un `chunks_used_hash = SHA-256(sorted(chunk_ids))`, para cerrar el círculo de reproducibilidad con la cadena CTR.

**Criterios de aceptación**:
- El servicio retorna siempre exactamente los top-5 tras rerank.
- El hash se calcula sobre IDs ordenados lexicográficamente.
- El hash viaja en el evento CTR `TutorRespondio` del tutor.
- Misma query + mismo corpus + mismo config → mismo hash (test).

**Invariantes afectados**: `chunks_used_hash` propagation; reproducibilidad bit-a-bit.

---

### HU-032 — Set de quince golden queries de Programación 2
**Actor**: Investigador / Tesista
**Fase**: F2
**Servicio(s)**: content-service
**Prioridad**: Media

**Historia**:
Como investigador, quiero un set curado de quince queries doradas con respuestas esperadas, para evaluar regresión de calidad del retrieval entre versiones.

**Criterios de aceptación**:
- Las queries cubren temas nucleares de Programación 2 (recursión, TAD, complejidad, etc.).
- `make eval-retrieval` ejecuta el set y reporta precision@5 y recall@5.
- Una regresión de más de cinco puntos porcentuales rompe CI.
- Las golden queries viven en `docs/golden-queries/` versionadas.

---

### HU-033 — Endpoint POST /retrieve y gestión de materiales
**Actor**: Docente
**Fase**: F2
**Servicio(s)**: content-service, api-gateway
**Prioridad**: Alta

**Historia**:
Como docente, quiero un endpoint para subir materiales y otro para probar queries de retrieval, para validar la calidad del RAG de mi comisión.

**Criterios de aceptación**:
- POST `/materiales` acepta multipart file + comision_id.
- POST `/retrieve` acepta query + comision_id y retorna top-5 con scores.
- El api-gateway enruta ambos endpoints con autenticación.
- Los errores preservan el comision_id mal autorizado sin filtrar otros datos.

---

## Fase F3 — Motor Pedagógico

### HU-034 — Modelo Episode y Event append-only
**Actor**: Sistema
**Fase**: F3
**Servicio(s)**: ctr-service
**Prioridad**: Crítica

**Historia**:
Como plataforma, quiero persistir episodios y eventos como estructuras estrictamente append-only, para garantizar que la cadena CTR sea auditable y criptográficamente verificable.

**Criterios de aceptación**:
- La tabla `Event` no expone `UPDATE` ni `DELETE` en el ORM.
- El tipo de evento, el `seq`, el `self_hash`, el `chain_hash` y el `event_uuid` son campos no nulos.
- Un intento de `UPDATE` a nivel SQL lanza excepción por trigger/policy documentada.
- Existe test que verifica que el ORM solo expone `INSERT`.

**Invariantes afectados**: CTR append-only.

---

### HU-035 — Hashing encadenado con GENESIS_HASH
**Actor**: Sistema
**Fase**: F3
**Servicio(s)**: ctr-service
**Prioridad**: Crítica

**Historia**:
Como plataforma, quiero que cada evento calcule `self_hash = SHA-256(canonicalize(payload))` y `chain_hash = SHA-256(prev_chain_hash || self_hash)`, iniciando desde `GENESIS_HASH = 0x00...00` (64 hex), para formar una cadena inmutable por episodio.

**Criterios de aceptación**:
- El primer evento de un episodio usa `GENESIS_HASH` como predecesor.
- La canonicalización excluye `self_hash` y `chain_hash` del propio payload hasheado.
- Un test recorre una cadena de cien eventos y verifica consistencia.
- Un cambio de un solo byte del payload rompe la verificación aguas abajo.

**Invariantes afectados**: CTR append-only; hash determinista.

---

### HU-036 — Sharding estable por episodio
**Actor**: Sistema
**Fase**: F3
**Servicio(s)**: ctr-service
**Prioridad**: Crítica

**Historia**:
Como plataforma, quiero que los eventos de un mismo episodio caigan siempre en la misma partición Redis Streams, mediante `hash(episode_id) mod n`, para preservar la invariante de single-writer por partición.

**Criterios de aceptación**:
- La función de sharding es determinista y documentada.
- Existe test que simula 10.000 episodios y verifica distribución aproximadamente uniforme.
- Cambiar el número de particiones requiere un ADR y migración específica.
- Dos eventos del mismo episodio nunca caen en particiones distintas.

**Invariantes afectados**: single-writer por partición CTR.

---

### HU-037 — Worker CTR particionado con idempotencia y DLQ
**Actor**: Sistema
**Fase**: F3
**Servicio(s)**: ctr-service
**Prioridad**: Crítica

**Historia**:
Como plataforma, quiero un worker por partición que consuma vía `XREADGROUP`, garantice idempotencia por `event_uuid`, valide `seq` monótono, reintente hasta tres veces y derive a DLQ marcando `integrity_compromised=true` en caso de falla persistente, para manejar fallos transitorios sin romper la cadena.

**Criterios de aceptación**:
- El consumer group se crea automáticamente si no existe.
- Un evento repetido (mismo `event_uuid`) no se procesa dos veces.
- Un `seq` fuera de orden se rechaza y no se escribe en la cadena.
- Tras tres reintentos, el evento entra a DLQ y el episodio queda marcado.
- Existe test que cubre reintento, idempotencia y DLQ.

**Invariantes afectados**: CTR append-only; single-writer por partición.

---

### HU-038 — Governance-service con PromptLoader fail-loud
**Actor**: Sistema
**Fase**: F3
**Servicio(s)**: governance-service
**Prioridad**: Crítica

**Historia**:
Como plataforma, quiero que el `PromptLoader` compare el hash del prompt cargado contra el manifest firmado y falle ruidosamente ante discrepancia, para detectar manipulación del corpus pedagógico (ADR-009).

**Criterios de aceptación**:
- El loader calcula SHA-256 del prompt y lo compara contra el manifest.
- Un mismatch lanza excepción y devuelve 503 al consumidor.
- El resultado exitoso se cachea en memoria con TTL.
- Existen endpoints `/prompts`, `/verify` y `/active_configs`.

**Invariantes afectados**: governance fail-loud.

---

### HU-039 — ai-gateway BaseProvider con pricing Anthropic
**Actor**: Sistema
**Fase**: F3
**Servicio(s)**: ai-gateway
**Prioridad**: Alta

**Historia**:
Como plataforma, quiero un `BaseProvider` abstracto con implementaciones Mock y Anthropic (Sonnet, Haiku, Opus) que conozcan el pricing vigente, para centralizar la facturación de tokens (ADR-004).

**Criterios de aceptación**:
- El provider Mock devuelve respuestas determinísticas sin red.
- El provider Anthropic mapea modelo a tarifa por millón de tokens input/output.
- Cada invocación reporta tokens consumidos y costo estimado.
- Ningún servicio llama directo al proveedor; todo pasa por ai-gateway.

---

### HU-040 — BudgetTracker por tenant en Redis con TTL 35 días
**Actor**: Admin UNSL
**Fase**: F3
**Servicio(s)**: ai-gateway
**Prioridad**: Crítica

**Historia**:
Como admin UNSL, quiero que el presupuesto de tokens por tenant viva en Redis con TTL de 35 días y se incremente atómicamente con `INCRBYFLOAT`, para imponer un techo mensual por universidad.

**Criterios de aceptación**:
- La clave `budget:{tenant}:{yyyymm}` caduca a los 35 días.
- Al superar el techo, el gateway devuelve 402 con detalle del remanente.
- El endpoint `/budget` expone consumo acumulado y techo configurado.
- Existe test con Redis testcontainers que simula concurrencia alta.

---

### HU-041 — ResponseCache solo para temperatura 0
**Actor**: Sistema
**Fase**: F3
**Servicio(s)**: ai-gateway
**Prioridad**: Media

**Historia**:
Como plataforma, quiero cachear respuestas del LLM solo cuando `temperature=0` y el prompt es idéntico, para ahorrar costos sin degradar la variabilidad esperada en generación creativa.

**Criterios de aceptación**:
- La cache usa hash del par `(prompt, model, params canónicos)`.
- Invocaciones con `temperature>0` ignoran la cache.
- Hit-rate y miss-rate se exponen como métricas Prometheus.
- El TTL por entrada es configurable por variable de entorno.

---

### HU-042 — Endpoints complete y stream SSE en ai-gateway
**Actor**: Sistema
**Fase**: F3
**Servicio(s)**: ai-gateway
**Prioridad**: Alta

**Historia**:
Como plataforma, quiero dos endpoints — `/complete` síncrono y `/stream` con SSE — en ai-gateway, para soportar tanto llamadas puntuales como respuestas incrementales del tutor.

**Criterios de aceptación**:
- `/stream` emite eventos SSE con `event: token` y cierre `event: end`.
- Ambos endpoints aceptan `model`, `temperature`, `max_tokens`.
- Errores de budget se traducen a códigos SSE específicos.
- El cliente puede cancelar el stream sin dejar la conexión colgada.

---

### HU-043 — SessionState del tutor en Redis con TTL 6h
**Actor**: Sistema
**Fase**: F3
**Servicio(s)**: tutor-service
**Prioridad**: Alta

**Historia**:
Como plataforma, quiero mantener el estado conversacional del tutor en Redis con TTL de seis horas, para cubrir sesiones largas sin desbordar memoria y recuperar ante reinicio.

**Criterios de aceptación**:
- Cada `SessionState` tiene clave `session:{episode_id}` con TTL 6h.
- La restauración tras reinicio respeta `seq` actual y chunks previos.
- Un TTL expirado cierra el episodio automáticamente en el próximo ping.
- El estado incluye `model` elegido por feature flag.

---

### HU-044 — TutorCore: apertura, interacción y cierre de episodio
**Actor**: Estudiante
**Fase**: F3
**Servicio(s)**: tutor-service
**Prioridad**: Crítica

**Historia**:
Como estudiante, quiero abrir un episodio, interactuar con el tutor vía streaming y cerrar el episodio al terminar, para tener una sesión pedagógica con trazabilidad completa.

**Criterios de aceptación**:
- `open_episode` emite `EpisodioAbierto` con `seq=0`.
- `interact` genera async: retrieval, emite `PromptEnviado` (`seq+1`), streamea LLM y emite `TutorRespondio` (`seq+2`) con `chunks_used_hash`.
- `close_episode` emite `EpisodioCerrado`.
- La secuencia completa queda validada por test end-to-end con Mock.

**Invariantes afectados**: CTR append-only; chunks_used_hash propagation.

---

### HU-045 — Service-account del tutor con UUID fijo
**Actor**: Tutor-Service (service-account)
**Fase**: F3
**Servicio(s)**: tutor-service, identity-service
**Prioridad**: Crítica

**Historia**:
Como tutor-service, quiero un UUID fijo de service-account para firmar mis eventos CTR, de modo que sea trivial distinguir eventos emitidos por el tutor de aquellos emitidos por el estudiante.

**Criterios de aceptación**:
- El UUID del tutor está en configuración y nunca rota sin ADR.
- Todos los eventos del tutor (excepto `codigo_ejecutado`) llevan ese `user_id`.
- El event `codigo_ejecutado` lleva el `user_id` del estudiante.
- Un evento con `user_id` mezclado falla en validación de capas superiores.

**Invariantes afectados**: CTR append-only; api-gateway identidad autoritativa.

---

### HU-046 — Classification append-only con is_current
**Actor**: Sistema
**Fase**: F3
**Servicio(s)**: classifier-service
**Prioridad**: Crítica

**Historia**:
Como plataforma, quiero que las clasificaciones se registren como inserts append-only con flag `is_current`, marcando la anterior como `is_current=false` al reclasificar, para preservar historia y reproducibilidad (ADR-010).

**Criterios de aceptación**:
- Reclasificar no hace `UPDATE` del registro previo salvo el flag `is_current`.
- Un test verifica que la historia queda disponible para auditoría.
- El `classifier_config_hash` es parte del insert.
- Una misma combinación `(episode_id, classifier_config_hash)` puede coexistir solo si `is_current=false` en las demás.

**Invariantes afectados**: CTR append-only; reproducibilidad bit-a-bit.

---

### HU-047 — Cálculo de las cinco coherencias separadas
**Actor**: Sistema
**Fase**: F3
**Servicio(s)**: classifier-service
**Prioridad**: Crítica

**Historia**:
Como plataforma, quiero calcular las cinco coherencias (CT, CCD_mean, CCD_orphan_ratio, CII_stability, CII_evolution) y mantenerlas SEPARADAS, para no colapsar el análisis multidimensional que fundamenta la tesis.

**Criterios de aceptación**:
- CT se calcula por ventanas con pausas mayores a cinco minutos.
- CCD considera ventanas de dos minutos entre acciones y reflexiones.
- CII_stability usa Jaccard sobre prompts consecutivos.
- CII_evolution usa la pendiente de la longitud de respuesta.
- Un test asegura que las cinco se exponen como campos independientes.

**Invariantes afectados**: cinco coherencias separadas; reproducibilidad.

---

### HU-048 — Árbol de clasificación N4 con gatillos extremo y clásico
**Actor**: Sistema
**Fase**: F3
**Servicio(s)**: classifier-service
**Prioridad**: Crítica

**Historia**:
Como plataforma, quiero un árbol de decisión que mapee las cinco coherencias al triplete N4 (`delegacion_pasiva`, `apropiacion_superficial`, `apropiacion_reflexiva`) aplicando gatillos de caso extremo y caso clásico, para producir la etiqueta pedagógica de la tesis.

**Criterios de aceptación**:
- Los umbrales de los gatillos están parametrizados en `reference_profile`.
- Cambiar el perfil de referencia produce `classifier_config_hash` distinto.
- La razón prosa explicita qué rama del árbol disparó.
- Existe test con casos extremos y clásicos pre-computados.

**Invariantes afectados**: cinco coherencias separadas; reproducibilidad bit-a-bit.

---

### HU-049 — Reproducibilidad bit-a-bit de la clasificación
**Actor**: Investigador / Tesista
**Fase**: F3
**Servicio(s)**: classifier-service
**Prioridad**: Crítica

**Historia**:
Como investigador, quiero que un mismo `(events, classifier_config_hash)` produzca siempre la misma `Classification`, para sostener auditabilidad académica del piloto.

**Criterios de aceptación**:
- El test de integración corre la clasificación dos veces y compara bit-a-bit.
- El `classifier_config_hash` se deriva del serializado canónico del perfil.
- Toda nueva regla cambia el hash y queda registrada.
- El endpoint `/active_configs` expone el hash vigente.

**Invariantes afectados**: reproducibilidad bit-a-bit; cinco coherencias separadas.

---

### HU-050 — EpisodePage con Monaco split y chat en web-student
**Actor**: Estudiante
**Fase**: F3
**Servicio(s)**: web-student
**Prioridad**: Alta

**Historia**:
Como estudiante, quiero una pantalla con editor Monaco a la izquierda y chat con el tutor a la derecha, para resolver consignas sin cambiar de aplicación.

**Criterios de aceptación**:
- El editor Monaco soporta Python con resaltado y autocompletar básico.
- El chat muestra mensajes en streaming SSE.
- Botón de ejecución ejecuta el código en Pyodide (F5).
- El layout se adapta a pantallas de 1366×768 o mayores.

---

### HU-051 — ClassificationPanel con tres coherencias y árbol N4
**Actor**: Estudiante
**Fase**: F3
**Servicio(s)**: web-student
**Prioridad**: Alta

**Historia**:
Como estudiante, quiero ver un panel con mis tres coherencias más relevantes y la clasificación N4 actual, para tomar conciencia de mi estilo de aprendizaje.

**Criterios de aceptación**:
- El panel se actualiza al recibir una nueva clasificación.
- Los valores muestran tendencia respecto a la clasificación previa.
- La etiqueta N4 tiene color distintivo por categoría.
- El panel es accesible con lectores de pantalla.

---

## Fase F4 — Hardening + SLOs

### HU-052 — platform-observability con OpenTelemetry OTLP gRPC
**Actor**: Operador (Ops)
**Fase**: F4
**Servicio(s)**: packages/observability, todos
**Prioridad**: Alta

**Historia**:
Como operador, quiero un package `platform-observability` con OTel tracing vía OTLP gRPC, auto-instrumentación de FastAPI, httpx, SQLAlchemy y Redis, y structlog con `trace_id` y `span_id`, para tener trazas unificadas en Jaeger.

**Criterios de aceptación**:
- Cada servicio configura tracing con cuatro líneas de código.
- W3C trace context se propaga cross-service.
- Sentry queda conectado como exporter secundario.
- Un `NoopTracer` permite correr tests sin colector.

---

### HU-053 — Rate limiting sliding window en api-gateway
**Actor**: Operador (Ops)
**Fase**: F4
**Servicio(s)**: api-gateway
**Prioridad**: Alta

**Historia**:
Como operador, quiero rate limiting por principal (estudiante, tenant, service-account) con ventanas deslizantes en Redis, para proteger la plataforma de abuso y garantizar SLOs.

**Criterios de aceptación**:
- Los límites por endpoint son: 30/min episodes, 60/min retrieve, 20/min classify, 300/min default.
- Al excederse, se devuelve 429 con `Retry-After` y headers `X-RateLimit-*`.
- El sistema es fail-open ante caída de Redis.
- La inferencia de principal considera JWT, headers X-* y IP como fallback documentado.

---

### HU-054 — IntegrityChecker CronJob que verifica CTR cada 6h
**Actor**: Auditor Académico
**Fase**: F4
**Servicio(s)**: ctr-service
**Prioridad**: Crítica

**Historia**:
Como auditor, quiero un CronJob que cada seis horas recorra los episodios cerrados en las últimas 24 horas, recomputa la cadena y marque `integrity_compromised=true` ante discrepancia, para detectar manipulación no autorizada de la cadena.

**Criterios de aceptación**:
- El CronJob corre en K8s cada seis horas.
- Ante discrepancia, emite alerta Prometheus y marca el episodio.
- El log incluye `episode_id`, `event_uuid` conflictivo y detalle del mismatch.
- Existe test de integración con cadena adulterada manualmente.

**Invariantes afectados**: CTR append-only.

---

### HU-055 — Tests de integración con testcontainers (Postgres + Redis)
**Actor**: Sistema
**Fase**: F4
**Servicio(s)**: todos los servicios backend
**Prioridad**: Media

**Historia**:
Como plataforma, quiero una suite de integración que levante Postgres con pgvector y Redis con testcontainers, para probar código contra dependencias reales sin montar stack completo.

**Criterios de aceptación**:
- Los tests marcados `integration` corren vía testcontainers automáticamente.
- Las imágenes se cachean entre corridas locales.
- Los tests aíslan su esquema por base creada ad-hoc.
- El fixture cierra los containers al terminar.

---

### HU-056 — Agregación classifier `by_comision` con timeseries
**Actor**: Docente
**Fase**: F4
**Servicio(s)**: classifier-service
**Prioridad**: Media

**Historia**:
Como docente, quiero consultar clasificaciones agregadas por comisión y como serie temporal, para observar evolución de la cohorte.

**Criterios de aceptación**:
- El endpoint expone `GROUP BY comision_id, categoria_n4` y contadores.
- Un query parameter `window=day|week` cambia la granularidad temporal.
- La respuesta incluye total de episodios considerados.
- El resultado respeta RLS por `tenant_id`.

---

### HU-057 — ClasificacionesPage en web-admin
**Actor**: Docente Admin
**Fase**: F4
**Servicio(s)**: web-admin
**Prioridad**: Media

**Historia**:
Como docente admin, quiero una página que muestre las clasificaciones agregadas por comisión, para tener vista global del comportamiento de las cohortes.

**Criterios de aceptación**:
- La página filtra por período, materia y comisión.
- Se muestran conteos y porcentajes por categoría N4.
- Los datos se cargan vía TanStack Query con cache.
- Las rutas están protegidas por Casbin.

---

### HU-058 — Dashboard Grafana platform-slos.json
**Actor**: Operador (Ops)
**Fase**: F4
**Servicio(s)**: infrastructure/grafana
**Prioridad**: Alta

**Historia**:
Como operador, quiero un dashboard Grafana con paneles de tutor latency (P50/P95/P99), ai-gateway tokens y cache, CTR eventos, integrity y DLQ, N4 pie y tendencia, API 429s y error rate, para tener una vista central de los SLOs.

**Criterios de aceptación**:
- El dashboard se provisiona automáticamente vía carpeta.
- Cada panel referencia alerta Prometheus asociada.
- Las unidades son correctas (ms, %, req/s).
- Hay sección de métricas de negocio separada de técnicas.

---

### HU-059 — PrometheusRules con alertas críticas
**Actor**: Operador (Ops)
**Fase**: F4
**Servicio(s)**: infrastructure/prometheus
**Prioridad**: Crítica

**Historia**:
Como operador, quiero reglas Prometheus que alerten por TutorFirstTokenLatencyP95/99, CTRIntegrity, CTRDLQ, BudgetExhaust, ClassifierBacklog y ServiceError5xx, para actuar antes de degradación visible al estudiante.

**Criterios de aceptación**:
- Cada regla tiene severidad, runbook URL y label de servicio.
- CTRIntegrity es severidad critical y pagea inmediatamente.
- Las alertas se enrutan a Alertmanager con agrupación por servicio.
- Test unitario valida sintaxis de las rules.

---

### HU-060 — Métrica `ctr_episodes_integrity_compromised_total`
**Actor**: Auditor Académico
**Fase**: F4
**Servicio(s)**: ctr-service
**Prioridad**: Crítica

**Historia**:
Como auditor, quiero un contador Prometheus `ctr_episodes_integrity_compromised_total`, para cuantificar incidentes de integridad y disparar alertas automáticas.

**Criterios de aceptación**:
- La métrica incrementa solo cuando IntegrityChecker marca el flag.
- Tiene label por `tenant_id`.
- La alerta asociada tiene severidad critical.
- El canary rollback del tutor se dispara si este contador incrementa.

**Invariantes afectados**: CTR append-only.

---

### HU-061 — Coverage tutor/ctr/classifier ≥ 85%
**Actor**: Sistema
**Fase**: F4
**Servicio(s)**: tutor-service, ctr-service, classifier-service
**Prioridad**: Alta

**Historia**:
Como plataforma, quiero que el plano pedagógico mantenga coverage mínimo de 85%, para reducir riesgo de regresión en el núcleo de la tesis.

**Criterios de aceptación**:
- CI falla si coverage cae por debajo de 85% en esos tres servicios.
- El reporte distingue coverage de `src/` vs `tests/`.
- Los archivos `__init__.py` están excluidos del cálculo.
- Codecov muestra gráfico de evolución.

---

## Fase F5 — Producción Multi-tenant + Privacy + Pyodide

### HU-062 — JWT RS256 obligatorio en api-gateway
**Actor**: Sistema
**Fase**: F5
**Servicio(s)**: api-gateway
**Prioridad**: Crítica

**Historia**:
Como plataforma, quiero que api-gateway valide JWTs RS256 con JWKS cacheada (con force-refresh) y verifique claims `iss`, `aud`, `exp`, `sub` y `tenant_id`, para que la identidad entre a la plataforma por un único punto de control.

**Criterios de aceptación**:
- Un token sin `tenant_id` válido se rechaza con 401.
- La JWKS se refresca ante `kid` desconocido.
- Los headers X-* se reescriben autoritativos (no se confía en los entrantes).
- Existe modo `dev_trust_headers` solo para desarrollo local.
- `X-Request-Id` se genera si falta.

**Invariantes afectados**: api-gateway único source identidad.

---

### HU-063 — Onboarding de tenant UNSL idempotente
**Actor**: Superadmin
**Fase**: F5
**Servicio(s)**: platform-ops, identity-service
**Prioridad**: Crítica

**Historia**:
Como superadmin, quiero un script `tenant_onboarding` que cree realm Keycloak, client `platform-backend`, mapper `tenant_id`, cuatro roles y admin con `UPDATE_PASSWORD`, reportando cada paso y siendo idempotente, para onboardear nuevas universidades sin riesgo.

**Criterios de aceptación**:
- Correr el script dos veces deja el mismo estado.
- Cada paso reporta éxito o reutilización.
- Un error en un paso no deja estado inconsistente.
- El admin arranca con acción obligatoria `UPDATE_PASSWORD`.

---

### HU-064 — TenantSecretResolver con fallback ordenado
**Actor**: Sistema
**Fase**: F5
**Servicio(s)**: platform-ops
**Prioridad**: Alta

**Historia**:
Como plataforma, quiero un resolver de secretos que busque primero archivos K8s, luego env per-tenant, luego env global y finalmente falle si no encuentra, para manejar secretos por tenant sin hardcoding.

**Criterios de aceptación**:
- El orden de fallback está documentado y testeado.
- Un secreto faltante lanza `SecretNotFoundError` con nombre claro.
- Los secretos nunca se logean.
- El resolver cachea el resultado en memoria por request.

---

### HU-065 — Feature flags declarativos con YAML
**Actor**: Admin UNSL
**Fase**: F5
**Servicio(s)**: platform-ops
**Prioridad**: Crítica

**Historia**:
Como admin UNSL, quiero un archivo YAML con feature flags declarados (default + overrides por tenant), con API `is_enabled`, `get_value`, `get_all_for_tenant` y reload basado en hash, para activar capacidades por universidad sin deploys.

**Criterios de aceptación**:
- Una flag no declarada lanza `FeatureNotDeclaredError` (nunca silent false).
- El reload detecta cambios por hash del archivo.
- El override por tenant toma precedencia sobre default.
- Existe test que cubre flags booleanas y de valor string.

**Invariantes afectados**: feature flags declarativos.

---

### HU-066 — Exportación de datos de un estudiante firmada
**Actor**: Estudiante
**Fase**: F5
**Servicio(s)**: platform-ops, privacy
**Prioridad**: Crítica

**Historia**:
Como estudiante, quiero ejercer mi derecho a exportar mis datos (episodios, CTR, clasificaciones, materiales consultados) con firma SHA-256, para cumplir la dimensión ética del piloto.

**Criterios de aceptación**:
- El export incluye los cuatro bloques declarados.
- El archivo tiene firma SHA-256 adjunta.
- La solicitud queda registrada en `AuditLog`.
- El archivo se entrega por enlace firmado con expiración.

---

### HU-067 — Anonimización de estudiante preservando CTR
**Actor**: Admin UNSL
**Fase**: F5
**Servicio(s)**: platform-ops, privacy
**Prioridad**: Crítica

**Historia**:
Como admin UNSL, quiero anonimizar un estudiante rotando su pseudónimo sin tocar la cadena CTR, para cumplir el derecho a retirarse del piloto preservando auditoría académica.

**Criterios de aceptación**:
- La operación rota el pseudónimo en `identity_store`.
- Los registros CTR permanecen intactos (no se modifican).
- La operación queda en `AuditLog` del módulo privacy.
- Un test verifica que el `chain_hash` se mantiene válido post anonimización.

**Invariantes afectados**: CTR append-only; privacy.

---

### HU-068 — Scripts backup.sh y restore.sh con manifest firmado
**Actor**: Operador (Ops)
**Fase**: F5
**Servicio(s)**: scripts
**Prioridad**: Crítica

**Historia**:
Como operador, quiero scripts de backup y restore que usen `pg_dump --format=custom -Z 9`, generen un manifest SHA-256, exijan `CONFIRM=yes` para restore y verifiquen checksums, para preservar el estado del piloto.

**Criterios de aceptación**:
- El backup corre vía CronJob diario a las 03:00 UTC.
- Se mantienen siete días de retención en PVC de 50 Gi.
- El restore sin `CONFIRM=yes` aborta con mensaje explícito.
- Un checksum inválido detiene el restore antes de tocar la DB.

---

### HU-069 — CodeEditor con Monaco + Pyodide 0.26
**Actor**: Estudiante
**Fase**: F5
**Servicio(s)**: web-student
**Prioridad**: Alta

**Historia**:
Como estudiante, quiero ejecutar código Python 100% en el navegador vía Pyodide, para resolver consignas sin enviar mi código al servidor.

**Criterios de aceptación**:
- Pyodide 0.26 se carga desde CDN (~6 MB).
- stdout y stderr se muestran al estudiante.
- No hay acceso a red desde el sandbox.
- La stdlib completa y `micropip` están disponibles.
- La ejecución emite un callback al tutor con métricas básicas.

---

### HU-070 — Tests de suite F5 (44 nuevos)
**Actor**: Sistema
**Fase**: F5
**Servicio(s)**: platform-ops, api-gateway, privacy
**Prioridad**: Media

**Historia**:
Como plataforma, quiero al menos 44 tests nuevos que cubran JWT RS256, onboarding, secretos, feature flags, privacy y Pyodide, para fijar el comportamiento de producción.

**Criterios de aceptación**:
- Los 44 tests pasan en CI.
- La cobertura de `platform-ops` supera 85%.
- Hay tests por cada rama de fallo declarada en los módulos.
- El tiempo de ejecución no excede dos minutos.

---

### HU-071 — RLS con FORCE ROW LEVEL SECURITY en bases productivas
**Actor**: Sistema
**Fase**: F5
**Servicio(s)**: infrastructure/postgres
**Prioridad**: Crítica

**Historia**:
Como plataforma, quiero aplicar `FORCE ROW LEVEL SECURITY` en todas las tablas multi-tenant, para que incluso el owner del esquema respete las policies (ADR-001).

**Criterios de aceptación**:
- `make check-rls` verifica FORCE y no solo ENABLE.
- Migración documentada y reversible.
- Tests RLS contra Postgres real pasan con el FORCE activo.
- Ningún rol salvo `postgres` (superuser) puede bypassear policies.

**Invariantes afectados**: RLS multi-tenant FORCE.

---

### HU-072 — Separación de usuarios DB por plano
**Actor**: Sistema
**Fase**: F5
**Servicio(s)**: infrastructure/postgres
**Prioridad**: Crítica

**Historia**:
Como plataforma, quiero usuarios DB separados por plano (`academic_user`, `ctr_user`, `identity_user`) con permisos mínimos, para cumplir ADR-003 y aislar blast radius.

**Criterios de aceptación**:
- Cada usuario solo tiene acceso a las tablas de su plano.
- `.env.example` documenta la separación.
- Un servicio conectado con usuario incorrecto falla al primer query.
- Auditoría de permisos corre en CI.

---

### HU-073 — Validación de salt ≥ 16 caracteres en exports
**Actor**: Sistema
**Fase**: F5
**Servicio(s)**: analytics-service
**Prioridad**: Crítica

**Historia**:
Como plataforma, quiero rechazar exports cuyo `salt` tenga menos de 16 caracteres, para garantizar fortaleza del pseudónimo y cumplir la condición ética declarada en el protocolo.

**Criterios de aceptación**:
- El endpoint valida longitud antes de cualquier operación.
- La validación se repite en frontend docente y backend.
- Un salt menor lanza 422 con mensaje claro.
- El `include_prompts=False` es el default.

**Invariantes afectados**: privacy.

---

## Fase F6 — Integración UNSL + LDAP + Canary

### HU-074 — Observabilidad unificada con wrappers
**Actor**: Sistema
**Fase**: F6
**Servicio(s)**: todos los servicios backend
**Prioridad**: Media

**Historia**:
Como plataforma, quiero reducir los doce `observability.py` locales a wrappers de ~20 LOC que delegan a `platform-observability`, para eliminar drift entre servicios.

**Criterios de aceptación**:
- Cada `observability.py` local no excede 20 LOC.
- Un cambio en el package se refleja automáticamente en los doce servicios.
- No queda duplicación de lógica de instrumentación.
- Tests existentes siguen pasando.

---

### HU-075 — useAuthenticatedFetch con refresh automático en 401
**Actor**: Estudiante
**Fase**: F6
**Servicio(s)**: web-student, auth-client
**Prioridad**: Alta

**Historia**:
Como estudiante, quiero que las llamadas al API inyecten automáticamente el Bearer y hagan refresh ante 401, para no ver errores espurios cuando el token expira durante una sesión larga.

**Criterios de aceptación**:
- El hook reintenta una vez ante 401.
- Un refresh fallido redirige al login.
- El `authenticatedSSE` soporta custom headers (incluido el Bearer).
- `emitCodeExecuted` viaja con el token correcto.

---

### HU-076 — Evento `codigo_ejecutado` con user_id del estudiante
**Actor**: Estudiante
**Fase**: F6
**Servicio(s)**: tutor-service, ctr-service
**Prioridad**: Crítica

**Historia**:
Como plataforma, quiero que el evento `codigo_ejecutado` lleve el `user_id` del estudiante autenticado y no el del tutor, para que la cadena CTR refleje correctamente quién ejecutó el código.

**Criterios de aceptación**:
- POST `/episodes/{id}/events/codigo_ejecutado` acepta `code`, `stdout`, `stderr`, `duration_ms`.
- `TutorCore.emit_codigo_ejecutado` hace el seq+1 de forma atómica.
- El `user_id` del evento es el del estudiante (no el service-account del tutor).
- Existe test que falla si se cambia por error al tutor.

**Invariantes afectados**: CTR append-only; api-gateway identidad autoritativa.

---

### HU-077 — Feature flag `enable_claude_opus` en runtime
**Actor**: Admin UNSL
**Fase**: F6
**Servicio(s)**: tutor-service, platform-ops
**Prioridad**: Alta

**Historia**:
Como admin UNSL, quiero activar `enable_claude_opus` por tenant y que el tutor elija `claude-opus-4-7` o `sonnet-4-6` en consecuencia, persistiendo el modelo elegido en `SessionState` y en el evento `EpisodioAbierto`, para habilitar A/B pedagógico sin redeploy.

**Criterios de aceptación**:
- La flag se consulta al abrir cada episodio.
- El modelo elegido queda en `SessionState`.
- El evento `EpisodioAbierto` registra `model`.
- Cambiar la flag afecta solo episodios nuevos (no rompe sesiones en curso).

**Invariantes afectados**: feature flags declarativos.

---

### HU-078 — AcademicExporter con pseudónimos deterministas
**Actor**: Investigador / Tesista
**Fase**: F6
**Servicio(s)**: analytics-service
**Prioridad**: Crítica

**Historia**:
Como investigador, quiero exportar una cohorte completa con pseudónimos derivados de `hash(UUID + salt)` deterministas, incluyendo las cinco coherencias N4 y contadores de eventos, con `include_prompts=False` por default y `salt_hash` en el manifest, para correr análisis reproducibles preservando la identidad.

**Criterios de aceptación**:
- Mismo `(dataset, salt)` produce pseudónimos iguales entre corridas.
- `salt_hash` viaja en el manifest (no el salt crudo).
- `include_prompts=True` requiere flag explícito y queda en AuditLog.
- Salt menor a 16 caracteres se rechaza.

**Invariantes afectados**: privacy; reproducibilidad bit-a-bit.

---

### HU-079 — Cálculo de κ de Cohen con interpretación Landis & Koch
**Actor**: Docente
**Fase**: F6
**Servicio(s)**: analytics-service
**Prioridad**: Alta

**Historia**:
Como docente, quiero obtener κ de Cohen con observed/expected agreement, per-class agreement y matriz de confusión, más interpretación de Landis & Koch, para validar calidad de etiquetado con el tutor.

**Criterios de aceptación**:
- POST `/analytics/kappa` valida enum de categorías con `Literal` pydantic.
- La respuesta incluye las cuatro métricas.
- La interpretación retorna una de las cinco bandas.
- Existe test con casos pre-computados manualmente.

---

### HU-080 — AuditEngine con tres reglas SIEM
**Actor**: Auditor Académico
**Fase**: F6
**Servicio(s)**: identity-service
**Prioridad**: Alta

**Historia**:
Como auditor, quiero un motor con reglas BruteForceRule (5 fallos en 5 min), CrossTenantAccessRule y RepeatedAuthFailures (10 errores 401 en 10 min), que emita findings ordenados por severidad en JSON SIEM, para detectar intentos de ataque o mal uso.

**Criterios de aceptación**:
- Cada regla se puede habilitar o deshabilitar por tenant.
- Los findings se serializan a formato SIEM estándar.
- Un finding incluye ventana temporal y evidencia.
- Existe test con eventos sintéticos por cada regla.

---

### HU-081 — Federación LDAP READ-ONLY
**Actor**: Admin UNSL
**Fase**: F6
**Servicio(s)**: identity-service
**Prioridad**: Crítica

**Historia**:
Como admin UNSL, quiero configurar la federación LDAP con `editMode: READ_ONLY`, mappers de email, first_name, last_name, mapper hardcoded de `tenant_id` y mapeo de grupo LDAP a rol, para cumplir la condición del convenio de no modificar el directorio institucional.

**Criterios de aceptación**:
- `LDAPFederator.configure` es idempotente.
- `editMode` queda verificado post-configuración.
- Un intento de escritura desde la plataforma retorna error.
- El mapper de `tenant_id` es hardcoded por script (no dinámico).

**Invariantes afectados**: LDAP READ-ONLY.

---

### HU-082 — Canary tutor-service con Argo Rollouts
**Actor**: Operador (Ops)
**Fase**: F6
**Servicio(s)**: tutor-service, infrastructure/helm
**Prioridad**: Crítica

**Historia**:
Como operador, quiero un rollout canary 10% → 2 min → 50% → 5 min → 100% que analice métricas Prometheus (latency P95<3s, error 5xx<1%) y haga rollback inmediato si `ctr_episodes_integrity_compromised_total` incrementa, para desplegar el núcleo pedagógico con seguridad.

**Criterios de aceptación**:
- Argo Rollout se aplica vía Helm.
- El análisis se evalúa en cada step.
- Un incremento del contador de integridad dispara rollback automático.
- El runbook I01 menciona este canary.

**Invariantes afectados**: CTR append-only.

---

### HU-083 — Endpoint POST /analytics/cohort/export
**Actor**: Investigador / Tesista
**Fase**: F6
**Servicio(s)**: analytics-service, api-gateway
**Prioridad**: Alta

**Historia**:
Como investigador, quiero un endpoint para exportar una cohorte con salt y flags configurables, para disparar exports desde frontend o CLI.

**Criterios de aceptación**:
- El endpoint valida salt ≥ 16 caracteres.
- La respuesta incluye `job_id` y URL de polling.
- El exporter corre async (F7).
- La llamada queda en `AuditLog`.

---

### HU-084 — Endpoint POST /analytics/kappa
**Actor**: Docente
**Fase**: F6
**Servicio(s)**: analytics-service, api-gateway
**Prioridad**: Alta

**Historia**:
Como docente, quiero un endpoint para calcular κ sobre un conjunto de etiquetas, para obtener medidas de acuerdo entre humano y tutor.

**Criterios de aceptación**:
- El endpoint acepta listas de pares `(labeler_a, labeler_b)`.
- Valida enum de categorías con `Literal`.
- Retorna el objeto completo de κ y sus métricas auxiliares.
- Un payload con categorías inválidas retorna 422.

---

### HU-085 — Suite de 50 tests de F6
**Actor**: Sistema
**Fase**: F6
**Servicio(s)**: todos los impactados
**Prioridad**: Media

**Historia**:
Como plataforma, quiero 50 tests nuevos que cubran OIDC real, evento `codigo_ejecutado`, feature flag de modelo, exportador, κ, AuditEngine, LDAP y canary, para consolidar F6 antes de F7.

**Criterios de aceptación**:
- Todos los 50 tests pasan en CI.
- Cada módulo nuevo tiene al menos cinco tests.
- Se añade test de regresión para el `user_id` de `codigo_ejecutado`.
- Coverage del plano pedagógico sigue ≥ 85%.

---

## Fase F7 — Empírico

### HU-086 — StudentTrajectory con progression_label
**Actor**: Investigador / Tesista
**Fase**: F7
**Servicio(s)**: analytics-service
**Prioridad**: Alta

**Historia**:
Como investigador, quiero calcular `progression_label` por estudiante comparando el primer tercio y el último tercio de sus episodios, en escala `delegacion=0 < superficial=1 < reflexiva=2`, con tolerancia 0.25 para producir `mejorando`, `empeorando`, `estable` o `insuficiente`, para analizar longitudinalmente el piloto.

**Criterios de aceptación**:
- El algoritmo requiere mínimo de episodios (umbral `insuficiente`).
- La tolerancia 0.25 está parametrizada.
- El endpoint GET `/analytics/cohort/{id}/progression` retorna la serie.
- Existen tests para cada una de las cuatro etiquetas.

---

### HU-087 — CohortProgression.net_progression_ratio
**Actor**: Investigador / Tesista
**Fase**: F7
**Servicio(s)**: analytics-service
**Prioridad**: Alta

**Historia**:
Como investigador, quiero calcular `(mejorando - empeorando) / total` como `net_progression_ratio`, para tener una métrica compacta del efecto del tutor sobre la cohorte.

**Criterios de aceptación**:
- La fórmula excluye `insuficiente` del denominador.
- El valor está siempre en `[-1, 1]`.
- Se expone junto a los tres contadores base.
- Existe test con mezclas prepactadas.

---

### HU-088 — A/B testing de reference_profiles
**Actor**: Investigador / Tesista
**Fase**: F7
**Servicio(s)**: analytics-service, classifier-service
**Prioridad**: Alta

**Historia**:
Como investigador, quiero comparar un perfil gold standard contra candidatos usando `compare_profiles(gold_standard, candidatos, classify_fn, compute_hash_fn)`, obteniendo κ por perfil, para seleccionar el perfil óptimo de clasificación.

**Criterios de aceptación**:
- La función devuelve κ y hash por candidato.
- El test de integración verifica reproducibilidad determinista.
- Endpoint POST `/analytics/ab-test-profiles` expone la comparación.
- Los resultados quedan en `AuditLog`.

**Invariantes afectados**: reproducibilidad bit-a-bit.

---

### HU-089 — ExportWorker async con estados PENDING → RUNNING → SUCCEEDED|FAILED
**Actor**: Investigador / Tesista
**Fase**: F7
**Servicio(s)**: analytics-service
**Prioridad**: Alta

**Historia**:
Como investigador, quiero que los exports corran en worker async con estados claros (PENDING, RUNNING, SUCCEEDED, FAILED) y cleanup de jobs antiguos, para disparar exports largos sin bloquear el cliente.

**Criterios de aceptación**:
- `ExportJobStore` usa `asyncio.Lock` para mutaciones.
- `run_forever` procesa cola FIFO.
- El endpoint `/status` retorna estado y progreso.
- `/download` rechaza jobs no SUCCEEDED.
- El lifespan de la app arranca y detiene el worker de forma grácil.

---

### HU-090 — data_source_factory desacoplado para exporter
**Actor**: Sistema
**Fase**: F7
**Servicio(s)**: analytics-service
**Prioridad**: Media

**Historia**:
Como plataforma, quiero que el exporter reciba su `data_source` por factory, para intercambiar mock y source real sin cambiar el worker.

**Criterios de aceptación**:
- La factory se configura vía env var.
- El mock data source se usa por default en test.
- El real se activa en dev/prod con credenciales.
- Un error en la factory falla al startup (fail-fast).

---

### HU-091 — unsl_onboarding.py runnable end-to-end
**Actor**: Admin UNSL
**Fase**: F7
**Servicio(s)**: platform-ops, scripts
**Prioridad**: Alta

**Historia**:
Como admin UNSL, quiero un script único que encadene Keycloak + LDAP + feature flags, para dejar listo el tenant UNSL en una sola corrida.

**Criterios de aceptación**:
- El script es idempotente end-to-end.
- Reporta cada paso con prefix `[onboarding]`.
- Falla fast ante credenciales inválidas.
- Corresponde al `make onboard-unsl` del Makefile.

---

### HU-092 — Consulta de progresión de cohorte desde frontend docente
**Actor**: Docente
**Fase**: F7
**Servicio(s)**: web-teacher, analytics-service
**Prioridad**: Media

**Historia**:
Como docente, quiero consultar la progresión de mi cohorte y ver el ratio neto, para observar el efecto longitudinal del tutor en tiempo real.

**Criterios de aceptación**:
- La vista muestra el ratio con signo y color semántico.
- Incluye conteos absolutos de cada categoría.
- Filtro por período y materia.
- Consulta cacheada con TanStack Query.

---

### HU-093 — Suite 44 tests F7
**Actor**: Sistema
**Fase**: F7
**Servicio(s)**: analytics-service
**Prioridad**: Media

**Historia**:
Como plataforma, quiero 44 tests nuevos que cubran progresión longitudinal, A/B de perfiles, export worker async y onboarding, para consolidar la capa empírica.

**Criterios de aceptación**:
- 44 tests pasan en CI.
- Coverage de `analytics-service` supera 85%.
- Los tests de determinismo corren dos veces y comparan.
- Los tests del worker usan asyncio.

---

## Fase F8 — DB Reales + Frontend Docente + Grafana + Protocolo

### HU-094 — RealCohortDataSource con sesiones DB separadas
**Actor**: Sistema
**Fase**: F8
**Servicio(s)**: analytics-service
**Prioridad**: Crítica

**Historia**:
Como plataforma, quiero un `RealCohortDataSource` que use sesiones separadas a `ctr_store` y `classifier_db`, aplique `SET LOCAL app.current_tenant` y doble filtro `WHERE + RLS`, para garantizar aislamiento real contra DB productiva.

**Criterios de aceptación**:
- La sesión a `ctr_store` no comparte conexión con `classifier_db`.
- `set_tenant_rls` emite `SET LOCAL` al comienzo de cada sesión.
- Mismo binario corre en dev (mock) y prod (real) por env var.
- Existe test que lee de ambas bases y verifica resultado.

**Invariantes afectados**: RLS multi-tenant; doble filtro retrieval.

---

### HU-095 — RealLongitudinalDataSource wire por env vars
**Actor**: Sistema
**Fase**: F8
**Servicio(s)**: analytics-service
**Prioridad**: Alta

**Historia**:
Como plataforma, quiero una `RealLongitudinalDataSource` complementaria para el análisis longitudinal, seleccionada por env var en la factory, para no duplicar código entre exporter y análisis.

**Criterios de aceptación**:
- La factory detecta `REAL_DATA_SOURCE=1` o similar.
- Ambos data sources comparten interfaz abstracta.
- Mock y real se pueden mezclar en tests con monkeypatch.
- No hay credenciales hardcoded.

---

### HU-096 — ProgressionView en web-teacher
**Actor**: Docente
**Fase**: F8
**Servicio(s)**: web-teacher, analytics-service
**Prioridad**: Alta

**Historia**:
Como docente, quiero una vista con cards, barra de `net_progression` y timeline individual coloreado por N4, para interpretar la evolución de la cohorte sin leer JSON.

**Criterios de aceptación**:
- Las cards muestran mejorando/empeorando/estable/insuficiente.
- La barra tiene umbrales visuales (por ejemplo −0.2 rojo).
- El timeline individual usa los tres colores N4.
- Accesibilidad: contraste AA mínimo.

---

### HU-097 — KappaRatingView en web-teacher
**Actor**: Docente
**Fase**: F8
**Servicio(s)**: web-teacher, analytics-service
**Prioridad**: Alta

**Historia**:
Como docente, quiero una vista para etiquetar episodios con botones reflexiva/superficial/delegación y ver κ con interpretación Landis & Koch y matriz de confusión, para auditar calidad del clasificador.

**Criterios de aceptación**:
- Cada episodio muestra transcript y botones de etiqueta.
- Al finalizar, se invoca POST `/analytics/kappa`.
- La matriz de confusión se renderiza visualmente.
- Las etiquetas se guardan localmente mientras no se envían.

---

### HU-098 — ExportView con validación de salt y descarga JSON
**Actor**: Investigador / Tesista
**Fase**: F8
**Servicio(s)**: web-teacher, analytics-service
**Prioridad**: Alta

**Historia**:
Como investigador, quiero una vista con validación de salt ≥ 16 del lado cliente, polling de estado cada 2 s, barra de progreso y descarga JSON al finalizar, para ejecutar el export sin recurrir a CLI.

**Criterios de aceptación**:
- El botón de enviar se habilita solo con salt válido.
- El polling se detiene al llegar a SUCCEEDED o FAILED.
- La descarga preserva el nombre de archivo con timestamp.
- Errores se muestran con mensaje amigable.

---

### HU-099 — App web-teacher tabbed con tres vistas
**Actor**: Docente
**Fase**: F8
**Servicio(s)**: web-teacher
**Prioridad**: Media

**Historia**:
Como docente, quiero una aplicación con tabs para Progresión, Kappa y Export, para navegar las tres vistas sin recargar.

**Criterios de aceptación**:
- Los tabs se navegan por teclado.
- La URL refleja el tab activo (deep-linking).
- Cada tab carga lazy con React.lazy.
- La cabecera muestra usuario autenticado y logout.

---

### HU-100 — Dashboard Grafana unsl-pilot.json
**Actor**: Operador (Ops)
**Fase**: F8
**Servicio(s)**: infrastructure/grafana
**Prioridad**: Alta

**Historia**:
Como operador, quiero un dashboard con doce paneles (stats diarios, N4 pie + timeseries, progression con thresholds, Kappa gauge, backlog, reclasificaciones 30d, exports, budget fraction) y template vars por comisión P1/P2/TSU-IA + tenant, provisioned automáticamente, para monitorear el piloto completo.

**Criterios de aceptación**:
- El dashboard se carga automáticamente por provisioning.
- Los template vars filtran todos los paneles relevantes.
- Los thresholds de progression coinciden con el protocolo.
- Cada panel enlaza al runbook correspondiente.

---

### HU-101 — Protocolo piloto-unsl.docx
**Actor**: Investigador / Tesista
**Fase**: F8
**Servicio(s)**: docs/pilot
**Prioridad**: Alta

**Historia**:
Como investigador, quiero un protocolo DOCX de ~23 KB con ocho secciones y dos anexos (resumen ejecutivo, objetivos, diseño metodológico, métricas y stopping rules, análisis, ética, cronograma, productos, consentimiento y glosario), para soportar la revisión del comité de tesis.

**Criterios de aceptación**:
- `make generate-protocol` regenera el DOCX.
- El documento cubre 180 estudiantes en 16 semanas.
- Incluye 1 OG + 5 OE + 3 H.
- Anexo A tiene los cuatro derechos del estudiante.
- Anexo B define trece términos del glosario.

---

### HU-102 — Suite 10 tests F8
**Actor**: Sistema
**Fase**: F8
**Servicio(s)**: analytics-service
**Prioridad**: Baja

**Historia**:
Como plataforma, quiero diez tests que cubran data sources reales y vistas de frontend docente, para dar evidencia de correctitud de F8.

**Criterios de aceptación**:
- Diez tests pasan en CI.
- Tres son de frontend (web-teacher) con Vitest.
- Siete son de backend (analytics-service).
- Coverage no baja.

---

### HU-103 — Monitoreo de reclasificaciones últimos 30 días
**Actor**: Auditor Académico
**Fase**: F8
**Servicio(s)**: classifier-service, infrastructure/grafana
**Prioridad**: Media

**Historia**:
Como auditor, quiero un panel Grafana con cantidad de reclasificaciones por día en los últimos 30 días, para detectar inestabilidad del clasificador o cambios de perfil.

**Criterios de aceptación**:
- El panel cuenta filas con `is_current=false` por día.
- Un pico inusual dispara alerta warning.
- El panel filtra por tenant.
- Hay link a runbook I04 (Kappa bajo).

**Invariantes afectados**: CTR append-only.

---

## Fase F9 — Preflight

### HU-104 — Migraciones RLS específicas para CTR y Classifier
**Actor**: Operador (Ops)
**Fase**: F9
**Servicio(s)**: ctr-service, classifier-service
**Prioridad**: Crítica

**Historia**:
Como operador, quiero migraciones explícitas (`enable_rls_on_ctr_tables.py`, `enable_rls_on_classifier_tables.py`) que apliquen `ENABLE ROW LEVEL SECURITY FORCE`, creen policy con `current_setting('app.current_tenant')` y default vacío fail-safe, para cerrar el aislamiento antes de producción.

**Criterios de aceptación**:
- Ambas migraciones son reversibles.
- Un rol sin `SET LOCAL` no ve filas.
- Las migraciones corren en orden con el resto.
- Tests de integración validan post-migración.

**Invariantes afectados**: RLS multi-tenant FORCE.

---

### HU-105 — migrate-all.sh con dry-run y alembic current
**Actor**: Operador (Ops)
**Fase**: F9
**Servicio(s)**: scripts
**Prioridad**: Crítica

**Historia**:
Como operador, quiero un script `migrate-all.sh` que aplique `alembic upgrade head` a las cuatro bases en orden, imprima `alembic current` antes y después, falle fast y soporte `--dry-run`, para migrar producción con confianza.

**Criterios de aceptación**:
- Lee `CTR_STORE_URL`, `ACADEMIC_DB_URL`, `CLASSIFIER_DB_URL`, `CONTENT_DB_URL`.
- `--dry-run` muestra el plan sin ejecutar.
- Ante error, aborta y deja el estado reportado.
- El output queda apto para anexar al change log.

---

### HU-106 — Tests RLS contra Postgres real
**Actor**: Sistema
**Fase**: F9
**Servicio(s)**: test-utils, ctr-service
**Prioridad**: Crítica

**Historia**:
Como plataforma, quiero cuatro tests RLS contra Postgres real (saltados si falta `CTR_STORE_URL_FOR_RLS_TESTS`) que verifiquen: sin SET LOCAL → vacío, tenant_a → solo a, INSERT con tenant mismatch falla, SET LOCAL se resetea post-commit, para dar evidencia de aislamiento real.

**Criterios de aceptación**:
- `make test-rls` corre los cuatro tests.
- Los tests se skipean si la env var falta.
- Cada test aísla sus datos y limpia al final.
- El reporte incluye tiempo por test.

**Invariantes afectados**: RLS multi-tenant.

---

### HU-107 — Runbook de diez incidentes codificados
**Actor**: Operador (Ops)
**Fase**: F9
**Servicio(s)**: docs/pilot
**Prioridad**: Crítica

**Historia**:
Como operador, quiero un runbook con diez incidentes codificados (I01 a I10) que cubran integridad CTR, timeouts tutor, backlog classifier, Kappa bajo, net progression negativo, solicitud de borrado, falla de export, LDAP caído, budget agotado y backup fallido, para actuar ante incidentes con procedimiento escrito.

**Criterios de aceptación**:
- Cada incidente tiene severidad, síntoma, diagnóstico y resolución.
- I01 (Integridad CTR) es crítico y tiene protocolo de congelamiento del tenant.
- I06 invoca `anonymize_student` sin tocar CTR.
- El runbook está enlazado desde las alertas Prometheus.

**Invariantes afectados**: CTR append-only; privacy.

---

### HU-108 — Notebook analysis-template.ipynb
**Actor**: Investigador / Tesista
**Fase**: F9
**Servicio(s)**: docs/pilot
**Prioridad**: Alta

**Historia**:
Como investigador, quiero un notebook Jupyter que cargue el JSON exportado, verifique `salt_hash`, haga descriptivos a nivel episodio con boxplots, replique `progression_label` con heatmap, calcule correlaciones Pearson con significancia `p<0.05` y pre-post con McNemar (binaria reflexiva vs resto), para tener el andamiaje del capítulo empírico de la tesis.

**Criterios de aceptación**:
- El notebook corre end-to-end con un export sintético.
- Verifica `salt_hash` y aborta ante mismatch.
- Genera figuras reproducibles con seed fijo.
- Incluye sección final con resumen apto para el capítulo.

---

### HU-109 — Default vacío fail-safe en policies RLS
**Actor**: Sistema
**Fase**: F9
**Servicio(s)**: infrastructure/postgres
**Prioridad**: Crítica

**Historia**:
Como plataforma, quiero que toda policy RLS tenga default vacío fail-safe, para que la ausencia de `SET LOCAL` nunca derive en fuga de datos.

**Criterios de aceptación**:
- `current_setting('app.current_tenant', true)` retorna cadena vacía sin error.
- La policy `USING (tenant_id::text = current_setting('app.current_tenant', true))` filtra todo si está vacío.
- Existe test que lo verifica contra real.
- Cambios a la policy requieren ADR.

**Invariantes afectados**: RLS multi-tenant FORCE.

---

### HU-110 — Incidente I06: solicitud de borrado con CTR preservado
**Actor**: Admin UNSL
**Fase**: F9
**Servicio(s)**: privacy, ctr-service
**Prioridad**: Crítica

**Historia**:
Como admin UNSL, quiero que la solicitud de borrado siga el protocolo I06 (ejecutar `anonymize_student`, no tocar CTR, registrar AuditLog), para respetar el derecho del estudiante sin romper auditoría académica.

**Criterios de aceptación**:
- El protocolo I06 invoca `anonymize_student` únicamente.
- La cadena CTR queda validable después.
- La solicitud original se conserva firmada digitalmente.
- Un test simula el incidente y verifica post-condición.

**Invariantes afectados**: CTR append-only; privacy.

---

### HU-111 — Pre-flight checks antes de abrir el piloto
**Actor**: Operador (Ops)
**Fase**: F9
**Servicio(s)**: scripts
**Prioridad**: Crítica

**Historia**:
Como operador, quiero una checklist automática pre-flight (migraciones aplicadas, RLS activas, LDAP conectado, budget configurado, feature flags cargadas, backups verdes, canary del tutor OK), para dar luz verde al inicio del piloto.

**Criterios de aceptación**:
- El script retorna 0 solo si todos los checks pasan.
- Cada falla reporta el ítem y el runbook asociado.
- La corrida queda en AuditLog.
- Se ejecuta como job previo al deploy a producción.

---

## Historias transversales por actor

### HU-112 — Estudiante: revisar historia de clasificaciones propias
**Actor**: Estudiante
**Fase**: transversal
**Servicio(s)**: classifier-service, web-student
**Prioridad**: Media

**Historia**:
Como estudiante, quiero revisar mi historial de clasificaciones con razones prosa, para entender cómo fue evolucionando mi estilo de resolución.

**Criterios de aceptación**:
- Se muestran clasificaciones actuales e históricas (`is_current=false`).
- Cada entrada tiene fecha, categoría N4 y razón prosa.
- No se muestran clasificaciones de otros estudiantes.
- La vista es responsive.

**Invariantes afectados**: CTR append-only; RLS multi-tenant.

---

### HU-113 — Docente: revisar episodios etiquetados y re-etiquetar
**Actor**: Docente
**Fase**: transversal
**Servicio(s)**: analytics-service, web-teacher
**Prioridad**: Media

**Historia**:
Como docente, quiero revisar mis etiquetados previos y poder re-etiquetar un episodio corrigiéndome, para mantener calidad de Kappa.

**Criterios de aceptación**:
- El historial muestra etiqueta previa y fecha.
- Re-etiquetar registra `AuditLog` con la versión anterior.
- Kappa se recalcula al re-etiquetar.
- Solo puede re-etiquetar sus propios labels.

---

### HU-114 — Superadmin: alta de nueva universidad
**Actor**: Superadmin
**Fase**: transversal
**Servicio(s)**: platform-ops, identity-service, academic-service
**Prioridad**: Crítica

**Historia**:
Como superadmin, quiero registrar una nueva universidad emitiendo su realm, usuarios iniciales y policies Casbin, para expandir la plataforma más allá del piloto UNSL.

**Criterios de aceptación**:
- El proceso es idempotente y reproducible.
- Un intento de alta duplicada reutiliza el estado previo.
- Se generan seeds de policy automáticamente.
- Ningún paso deja credenciales en logs.

---

### HU-115 — Operador: ejecutar restore en ambiente staging
**Actor**: Operador (Ops)
**Fase**: transversal
**Servicio(s)**: scripts, infrastructure
**Prioridad**: Alta

**Historia**:
Como operador, quiero restaurar un backup en staging con `restore.sh` contra un snapshot anterior, para practicar el drill de recuperación ante desastre.

**Criterios de aceptación**:
- Drill documentado con pasos, inputs y outputs.
- `CONFIRM=yes` obligatorio.
- Checksum verificado antes del restore.
- Tiempo total del drill medido y reportado.

---

### HU-116 — Auditor: verificar cadena CTR de un episodio puntual
**Actor**: Auditor Académico
**Fase**: transversal
**Servicio(s)**: ctr-service
**Prioridad**: Crítica

**Historia**:
Como auditor, quiero verificar la cadena CTR de un episodio específico y obtener reporte con `integrity_ok=true|false`, para responder a requerimientos puntuales del comité.

**Criterios de aceptación**:
- Endpoint `/episodes/{id}/verify` retorna el flag y un detalle por evento.
- Un episodio con flag comprometido identifica el primer `event_uuid` fuera de cadena.
- La verificación se registra en `AuditLog`.
- Solo auditores pueden invocar el endpoint (Casbin).

**Invariantes afectados**: CTR append-only.

---

### HU-117 — Sistema (service-account): emitir evento con idempotencia
**Actor**: Sistema
**Fase**: transversal
**Servicio(s)**: ctr-service, tutor-service
**Prioridad**: Crítica

**Historia**:
Como service-account emisor, quiero emitir un evento CTR con `event_uuid` autogenerado y ser idempotente ante reintentos de red, para no romper la cadena por duplicados espurios.

**Criterios de aceptación**:
- El evento con mismo `event_uuid` se ignora en segundo intento.
- El worker marca duplicado explícitamente en métrica.
- El `seq` no avanza en duplicado.
- Existe test que lo prueba con Redis Streams real.

**Invariantes afectados**: CTR append-only; single-writer.

---

### HU-118 — Plataforma: emitir versión y build_sha en /health
**Actor**: Operador (Ops)
**Fase**: transversal
**Servicio(s)**: todos
**Prioridad**: Baja

**Historia**:
Como operador, quiero que `/health` incluya versión semántica y `build_sha`, para correlacionar incidentes con commits.

**Criterios de aceptación**:
- El `build_sha` es el hash corto del commit.
- La versión semántica se inyecta en build time.
- El endpoint devuelve ambos en JSON.
- Test valida presencia de los campos.

---

## Historias de invariantes críticos

### HU-119 — Invariante: bloqueo de UPDATE/DELETE en tablas CTR
**Actor**: Sistema
**Fase**: F3/F9
**Servicio(s)**: ctr-service
**Prioridad**: Crítica

**Historia**:
Como plataforma, quiero que las tablas CTR rechacen cualquier `UPDATE` y `DELETE` por trigger o policy, para proteger la invariante append-only incluso ante bugs futuros.

**Criterios de aceptación**:
- Un intento directo de `UPDATE` emite excepción.
- Un intento directo de `DELETE` emite excepción.
- Test de integración verifica ambos casos.
- El único flag mutable permitido es `is_current` en `Classification` (no en `Event`).

**Invariantes afectados**: CTR append-only.

---

### HU-120 — Invariante: identidad autoritativa reescrita por api-gateway
**Actor**: Sistema
**Fase**: F5
**Servicio(s)**: api-gateway, todos los backend
**Prioridad**: Crítica

**Historia**:
Como plataforma, quiero que los servicios internos confíen únicamente en los headers X-Tenant-Id, X-User-Id y X-Role reescritos por api-gateway, sin re-verificar JWT aguas abajo, para centralizar la identidad y evitar inconsistencias.

**Criterios de aceptación**:
- Un request directo a un servicio interno sin pasar por gateway es rechazado en red.
- Los servicios leen X-* y no validan JWT.
- `dev_trust_headers` existe solo para desarrollo local.
- Un test muestra que cambiar X-* en el cliente no tiene efecto si gateway los reescribe.

**Invariantes afectados**: api-gateway único source identidad.

---

### HU-121 — Invariante: chunks_used_hash propaga a CTR
**Actor**: Sistema
**Fase**: F2/F3
**Servicio(s)**: content-service, tutor-service, ctr-service
**Prioridad**: Crítica

**Historia**:
Como plataforma, quiero que el `chunks_used_hash` calculado en retrieval viaje al evento `TutorRespondio`, para que auditoría posterior pueda reproducir qué chunks fundamentaron cada respuesta.

**Criterios de aceptación**:
- El hash viaja en el payload del evento.
- Un test verifica que hash desde retrieval == hash en CTR.
- Un cambio del chunk set cambia el hash.
- La auditoría puede reconstruir los chunks dado el hash y el corpus versionado.

**Invariantes afectados**: chunks_used_hash propagation; reproducibilidad.

---

### HU-122 — Invariante: las cinco coherencias no colapsan en un score
**Actor**: Sistema
**Fase**: F3
**Servicio(s)**: classifier-service
**Prioridad**: Crítica

**Historia**:
Como plataforma, quiero que las cinco coherencias (CT, CCD_mean, CCD_orphan_ratio, CII_stability, CII_evolution) se expongan y persistan separadas, sin colapsarlas en un score único, para preservar el análisis multidimensional base de la tesis.

**Criterios de aceptación**:
- El modelo `Classification` tiene cinco columnas distintas.
- El endpoint las retorna separadas.
- Un test regresivo falla si se introduce un campo compuesto.
- El protocolo documenta que el colapso está prohibido.

**Invariantes afectados**: cinco coherencias separadas.

---

### HU-123 — Invariante: feature flags no declaradas fallan ruidosamente
**Actor**: Sistema
**Fase**: F5
**Servicio(s)**: platform-ops
**Prioridad**: Crítica

**Historia**:
Como plataforma, quiero que una consulta a una flag no declarada lance `FeatureNotDeclaredError`, para evitar silent false y drift de configuración.

**Criterios de aceptación**:
- Un nombre de flag no presente en el YAML lanza excepción nombrada.
- El error incluye el nombre buscado y universo declarado.
- Existe test que cubre el error.
- La documentación para devs cita este comportamiento.

**Invariantes afectados**: feature flags declarativos.

---

### HU-124 — Invariante: LDAP editMode READ_ONLY post-configuración
**Actor**: Sistema
**Fase**: F6
**Servicio(s)**: identity-service, platform-ops
**Prioridad**: Crítica

**Historia**:
Como plataforma, quiero que `LDAPFederator.configure` deje `editMode=READ_ONLY` y el proceso verifique el estado final, para no violar la condición del convenio UNSL.

**Criterios de aceptación**:
- Tras configurar, el campo `editMode` vuelve a leerse y se compara.
- Un desvío aborta la configuración con error.
- El test se corre contra Keycloak real en integration.
- La documentación del convenio enlaza esta HU.

**Invariantes afectados**: LDAP READ-ONLY.

---

## Trazabilidad

Tabla de referencia HU → Fase → Servicio(s) → Tests o artefactos asociados mencionados en el contexto de fases.

| HU | Fase | Servicio(s) | Tests o artefactos relacionados |
|----|------|-------------|----------------------------------|
| HU-001 | F0 | raíz | Makefile `init`, `make status` |
| HU-002 | F0 | apps/* | `/health` smoke tests |
| HU-003 | F0 | packages/* | biome lint, turbo build |
| HU-004 | F0 | docker-compose.dev.yml | `make dev-bootstrap` |
| HU-005 | F0 | migrations | `make check-rls` |
| HU-006 | F0 | packages/contracts | test serialización Py↔TS |
| HU-007 | F0 | packages/contracts | test canonicalización SHA-256 |
| HU-008 | F0 | todos | `make check-health` |
| HU-009 | F0 | .github/workflows/ci.yml | siete gates duros |
| HU-010 | F0 | .github/workflows/ci.yml | Trivy scan |
| HU-011 | F1 | academic-service | migration Alembic 10 tablas |
| HU-012 | F1 | academic-service | `make seed-casbin` |
| HU-013 | F1 | test-utils | test RLS |
| HU-014 | F1 | academic-service | tests unit BaseRepository |
| HU-015 | F1 | academic-service | tests validación dominio |
| HU-016 | F1 | academic-service | test matriz Casbin (23/23, count via seed — ver RN-018) |
| HU-017 | F1 | academic-service | test transaccional |
| HU-018 | F1 | academic-service | migration reversible |
| HU-019 | F1 | academic-service | tests dry-run/commit CSV |
| HU-020 | F1 | academic-service | tests CRUD comisión |
| HU-021 | F1 | academic-service | 40 tests suite |
| HU-022 | F1 | web-admin | tests Vitest |
| HU-023 | F2 | content-service | tests ingest 4 tipos |
| HU-024 | F2 | content-service | tests heading_path |
| HU-025 | F2 | content-service | tests chunking |
| HU-026 | F2 | content-service | `EMBEDDER=mock` default |
| HU-027 | F2 | content-service | `RERANKER=identity` default |
| HU-028 | F2 | content-service | `STORAGE=mock` default |
| HU-029 | F2 | content-service | test cross-comisión |
| HU-030 | F2 | content-service | índice IVFFlat migration |
| HU-031 | F2 | content-service + tutor-service | test chunks_used_hash |
| HU-032 | F2 | content-service | `make eval-retrieval` |
| HU-033 | F2 | content-service + api-gateway | tests routes |
| HU-034 | F3 | ctr-service | test Event append-only |
| HU-035 | F3 | ctr-service | test cadena 100 eventos |
| HU-036 | F3 | ctr-service | test sharding 10k episodios |
| HU-037 | F3 | ctr-service | test idempotencia + DLQ |
| HU-038 | F3 | governance-service | test fail-loud manifest |
| HU-039 | F3 | ai-gateway | test providers Mock/Anthropic |
| HU-040 | F3 | ai-gateway | test Redis testcontainers |
| HU-041 | F3 | ai-gateway | test temperature cache |
| HU-042 | F3 | ai-gateway | test SSE stream |
| HU-043 | F3 | tutor-service | test SessionState TTL 6h |
| HU-044 | F3 | tutor-service | test e2e TutorCore |
| HU-045 | F3 | tutor-service + identity-service | test service-account UUID |
| HU-046 | F3 | classifier-service | test is_current append-only |
| HU-047 | F3 | classifier-service | test 5 coherencias separadas |
| HU-048 | F3 | classifier-service | test gatillos extremo/clásico |
| HU-049 | F3 | classifier-service | test reproducibilidad bit-a-bit |
| HU-050 | F3 | web-student | EpisodePage Vitest |
| HU-051 | F3 | web-student | ClassificationPanel Vitest |
| HU-052 | F4 | packages/observability | test OTLP + Noop |
| HU-053 | F4 | api-gateway | test sliding window Redis |
| HU-054 | F4 | ctr-service | test IntegrityChecker CronJob |
| HU-055 | F4 | todos | testcontainers Postgres+Redis |
| HU-056 | F4 | classifier-service | test agregación by_comision |
| HU-057 | F4 | web-admin | ClasificacionesPage Vitest |
| HU-058 | F4 | infrastructure/grafana | dashboard platform-slos.json |
| HU-059 | F4 | infrastructure/prometheus | test PrometheusRules |
| HU-060 | F4 | ctr-service | test métrica integrity_compromised |
| HU-061 | F4 | tutor/ctr/classifier | coverage ≥ 85% CI |
| HU-062 | F5 | api-gateway | test JWT RS256 JWKS |
| HU-063 | F5 | platform-ops + identity-service | test onboarding idempotente |
| HU-064 | F5 | platform-ops | test TenantSecretResolver fallback |
| HU-065 | F5 | platform-ops | test FeatureNotDeclaredError |
| HU-066 | F5 | platform-ops + privacy | test export firmado |
| HU-067 | F5 | platform-ops + privacy | test anonymize CTR preservado |
| HU-068 | F5 | scripts | backup.sh/restore.sh tests |
| HU-069 | F5 | web-student | CodeEditor Pyodide tests |
| HU-070 | F5 | platform-ops | 44 tests F5 |
| HU-071 | F5 | infrastructure/postgres | test FORCE RLS |
| HU-072 | F5 | infrastructure/postgres | `.env.example` roles |
| HU-073 | F5 | analytics-service | test salt ≥ 16 |
| HU-074 | F6 | todos | wrappers observability ~20 LOC |
| HU-075 | F6 | web-student + auth-client | test refresh 401 |
| HU-076 | F6 | tutor-service + ctr-service | test user_id estudiante |
| HU-077 | F6 | tutor-service + platform-ops | test feature flag runtime |
| HU-078 | F6 | analytics-service | test AcademicExporter |
| HU-079 | F6 | analytics-service | test compute_cohen_kappa |
| HU-080 | F6 | identity-service | test AuditEngine 3 reglas |
| HU-081 | F6 | identity-service | test LDAPFederator READ_ONLY |
| HU-082 | F6 | tutor-service + helm | canary Argo Rollouts |
| HU-083 | F6 | analytics-service + api-gateway | test endpoint export |
| HU-084 | F6 | analytics-service + api-gateway | test endpoint kappa |
| HU-085 | F6 | todos los impactados | 50 tests F6 |
| HU-086 | F7 | analytics-service | test progression_label |
| HU-087 | F7 | analytics-service | test net_progression_ratio |
| HU-088 | F7 | analytics-service + classifier-service | test compare_profiles |
| HU-089 | F7 | analytics-service | test ExportWorker estados |
| HU-090 | F7 | analytics-service | test data_source_factory |
| HU-091 | F7 | platform-ops + scripts | test unsl_onboarding.py |
| HU-092 | F7 | web-teacher + analytics-service | test progression frontend |
| HU-093 | F7 | analytics-service | 44 tests F7 |
| HU-094 | F8 | analytics-service | test RealCohortDataSource |
| HU-095 | F8 | analytics-service | test RealLongitudinalDataSource |
| HU-096 | F8 | web-teacher + analytics-service | ProgressionView Vitest |
| HU-097 | F8 | web-teacher + analytics-service | KappaRatingView Vitest |
| HU-098 | F8 | web-teacher + analytics-service | ExportView Vitest |
| HU-099 | F8 | web-teacher | App tabbed tests |
| HU-100 | F8 | infrastructure/grafana | dashboard unsl-pilot.json |
| HU-101 | F8 | docs/pilot | `make generate-protocol` |
| HU-102 | F8 | analytics-service | 10 tests F8 |
| HU-103 | F8 | classifier-service + grafana | panel reclasificaciones |
| HU-104 | F9 | ctr-service + classifier-service | migrations RLS |
| HU-105 | F9 | scripts | migrate-all.sh dry-run |
| HU-106 | F9 | test-utils + ctr-service | `make test-rls` |
| HU-107 | F9 | docs/pilot | runbook 10 incidentes |
| HU-108 | F9 | docs/pilot | analysis-template.ipynb |
| HU-109 | F9 | infrastructure/postgres | test default fail-safe |
| HU-110 | F9 | privacy + ctr-service | test incidente I06 |
| HU-111 | F9 | scripts | preflight checks |
| HU-112 | trans | classifier-service + web-student | test historial clasificaciones |
| HU-113 | trans | analytics-service + web-teacher | test re-etiquetado |
| HU-114 | trans | platform-ops + identity + academic | test alta universidad |
| HU-115 | trans | scripts + infra | drill restore staging |
| HU-116 | trans | ctr-service | test verify episodio |
| HU-117 | trans | ctr-service + tutor-service | test idempotencia Redis Streams |
| HU-118 | trans | todos | tests /health versión + build_sha |
| HU-119 | invar | ctr-service | test bloqueo UPDATE/DELETE |
| HU-120 | invar | api-gateway + backend | test identidad autoritativa |
| HU-121 | invar | content + tutor + ctr | test chunks_used_hash propagación |
| HU-122 | invar | classifier-service | test 5 coherencias separadas |
| HU-123 | invar | platform-ops | test FeatureNotDeclaredError |
| HU-124 | invar | identity-service + platform-ops | test LDAP READ_ONLY |
| HU-125 | epic ai-native-completion | ai-gateway + web-admin | gestión BYOK keys (CRUD + rotate + revoke + usage) — backend OK, UI DEFERIDA |
| HU-126 | epic ai-native-completion | tutor-service + web-student | sandbox tests Pyodide client-side — backend OK (`POST /run-tests` + evento CTR), Pyodide UI DEFERIDO |
| HU-127 | epic ai-native-completion | tutor-service + web-student | reflexión metacognitiva post-cierre — modal opcional + evento `reflexion_completada` excluido del classifier |
| HU-128 | epic ai-native-completion | academic-service + ai-gateway | TP-gen IA — endpoint `/generate` con audit log structlog, wizard UI DEFERIDO |
| HU-129 | epic ai-native-completion | analytics-service + web-admin | governance UI con filtros cross-cohort + CSV export ASCII |

---

**Fin del documento**
