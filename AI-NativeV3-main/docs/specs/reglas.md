# Reglas de Negocio — Plataforma AI-Native N4 (Piloto UNSL)

> Este documento captura las reglas de negocio del sistema: restricciones, invariantes, cálculos, políticas y umbrales que el sistema DEBE cumplir. Complementa `historias.md` (que captura capacidades desde la perspectiva del actor). Las reglas acá son verificables por tests automáticos o revisión operacional.

## Índice

- [Convenciones](#convenciones)
- [Resumen ejecutivo](#resumen-ejecutivo)
- [F0 — Fundaciones](#f0--fundaciones)
- [F1 — Dominio Académico](#f1--dominio-académico)
- [F2 — Contenido y RAG](#f2--contenido-y-rag)
- [F3 — Motor Pedagógico (CTR, tutor, governance, ai-gateway, clasificador)](#f3--motor-pedagógico-ctr-tutor-governance-ai-gateway-clasificador)
- [F4 — Hardening y Observabilidad](#f4--hardening-y-observabilidad)
- [F5 — Multi-tenant, JWT, privacidad](#f5--multi-tenant-jwt-privacidad)
- [F6 — Piloto UNSL (LDAP, código ejecutado, Kappa, canary)](#f6--piloto-unsl-ldap-código-ejecutado-kappa-canary)
- [F7 — Pipeline empírico (longitudinal, A/B, export async)](#f7--pipeline-empírico-longitudinal-ab-export-async)
- [F8 — Integración DB real y protocolo](#f8--integración-db-real-y-protocolo)
- [F9 — Preflight operacional](#f9--preflight-operacional)
- [Reglas transversales](#reglas-transversales)
- [Catálogo de severidades](#catálogo-de-severidades)
- [Trazabilidad RN → Fase → Verificación](#trazabilidad-rn--fase--verificación)
- [Reglas con verificación pendiente](#reglas-con-verificación-pendiente)

---

## Convenciones

### Cómo leer una regla

Cada regla se enuncia en imperativo ("DEBE", "NUNCA", "TIENE QUE") y es verificable por un test automatizado, una aserción de arranque, o una inspección documentada. La violación de una regla es un bug, no una variación aceptable.

### Categorías

- **Invariante**: propiedad que jamás debe violarse en runtime (ej. `seq` estrictamente incremental).
- **Cálculo**: fórmula exacta que reproduce un valor (ej. `chain_hash = SHA-256(self_hash || prev_chain_hash)`).
- **Validación**: restricción sobre inputs o estados (ej. `salt` ≥ 16 caracteres).
- **Autorización**: regla sobre quién puede ejecutar qué acción.
- **Persistencia**: cómo se escribe/actualiza/borra data (ej. append-only).
- **Privacidad**: tratamiento de datos personales (GDPR/Ley 25.326).
- **Operación**: políticas de deploy, backup, rollout, retention.
- **Auditoría**: trazabilidad, firma y evidencia que DEBE quedar.
- **Seguridad**: autenticación, rate limiting, hardening.

### Severidades

- **Crítica**: rompe auditabilidad, seguridad o la cadena criptográfica. Gate de merge.
- **Alta**: corrompe comportamiento pedagógico o multi-tenant, pero no criptografía.
- **Media**: degrada UX, performance o analítica pero no invalida el piloto.
- **Baja**: convención de código, coverage, estilo.

### Relación con invariantes críticos

Las reglas marcadas como Críticas corresponden a las siete "Propiedades críticas del sistema" enumeradas en `CLAUDE.md` y en los ADRs. Si una PR viola una regla Crítica, no se mergea por más verde que esté el resto de CI.

---

## Resumen ejecutivo

- **Total de reglas**: 139
- **Distribución por fase**: F0 (9) · F1 (13) · F2 (11) · F3 (28) · F4 (9) · F5 (15) · F6 (13) · F7 (10) · F8 (7) · F9 (7) · Transversales agrupadas (17 referencias cruzadas).
- **Distribución por severidad**: Críticas 38 · Altas 57 · Medias 34 · Bajas 10.
- **Distribución por categoría**: Invariante 24 · Cálculo 19 · Validación 17 · Autorización 9 · Persistencia 12 · Privacidad 9 · Operación 18 · Auditoría 14 · Seguridad 18.

---

## F0 — Fundaciones

### RN-001 — Toda tabla con `tenant_id` DEBE tener RLS activo
**Categoría**: Invariante
**Fase origen**: F0
**Servicio(s)**: todos los servicios con DB (academic, ctr, classifier, content, identity)
**Severidad**: Crítica

**Regla**: Toda tabla del dominio que incluya la columna `tenant_id UUID NOT NULL` DEBE tener aplicada la función `apply_tenant_rls('<tabla>')` antes de recibir datos productivos, lo cual habilita `ENABLE ROW LEVEL SECURITY` + política `tenant_iso` que filtra por `current_setting('app.current_tenant')::uuid`.

**Justificación**: Aislamiento multi-tenant a nivel de motor de BD (ADR-001). Un bug de código no puede filtrar datos cross-tenant si la policy está activa.

**Verificación**: `scripts/check-rls.py` + `make check-rls` (corre en CI). Falla si encuentra una tabla con columna `tenant_id` sin policy RLS.

**ADR/Doc**: ADR-001.

### RN-002 — GENESIS_HASH del CTR es exactamente 64 ceros
**Categoría**: Cálculo
**Fase origen**: F0
**Servicio(s)**: ctr-service, packages/contracts
**Severidad**: Crítica

**Regla**: El valor constante `GENESIS_HASH` DEBE ser literalmente la cadena `"0" * 64` (64 caracteres "0" ASCII). Se usa como `prev_chain_hash` del primer evento (`seq = 0`) de cada episodio y como valor default de `Episode.last_chain_hash` al crear un episodio.

**Justificación**: La cadena criptográfica arranca desde un valor fijo conocido. Cualquier otro valor (incluso "0"*63 + "A") rompe la reproducibilidad.

**Verificación**: `apps/ctr-service/tests/unit/test_hashing_and_sharding.py::test_genesis_hash` y chequeo en `apps/ctr-service/src/ctr_service/models/base.py` línea `GENESIS_HASH = "0" * 64`.

**ADR/Doc**: ADR-010.

### RN-003 — Las tres bases lógicas DEBEN permanecer aisladas (no joins cross-DB)
**Categoría**: Persistencia
**Fase origen**: F0
**Servicio(s)**: academic-service, ctr-service, identity-service (y luego classifier/content)
**Severidad**: Alta

**Regla**: Las bases `academic_main`, `ctr_store` e `identity_realms` (F8 agrega `classifier_db`, `content_db`) son independientes. Ningún servicio PUEDE ejecutar JOINs cross-base. Si un servicio necesita información de otra base, la obtiene por HTTP al servicio dueño o por evento del bus.

**Justificación**: ADR-003. Permite "graduar" un tenant a cluster dedicado y minimiza blast radius de un incidente.

**Verificación**: Revisión de PR + usuarios DB separados por plano (`academic_user`, `ctr_user`, `identity_user`) declarados en `.env.example`.

**ADR/Doc**: ADR-003.

### RN-004 — Canonicalización JSON del CTR usa parámetros exactos
**Categoría**: Cálculo
**Fase origen**: F0
**Servicio(s)**: ctr-service, packages/contracts
**Severidad**: Crítica

**Regla**: La función `canonicalize(obj)` DEBE serializar con `json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))` y encodear el resultado con UTF-8. Los UUID se serializan como `str(uuid)` y los `datetime` como ISO-8601 reemplazando `+00:00` por `Z`.

**Justificación**: Determinismo bit-a-bit de `self_hash`. Cualquier variación (espacios, comillas simples, escape de non-ASCII) produce distintos bytes → distinto hash → cadena rota.

**Verificación**: `apps/ctr-service/src/ctr_service/services/hashing.py::canonicalize` + test `test_canonicalizacion_determinista_utf8`.

**ADR/Doc**: código en `hashing.py`.

### RN-005 — `self_hash` EXCLUYE los campos computados y de metadata
**Categoría**: Cálculo
**Fase origen**: F0
**Servicio(s)**: ctr-service
**Severidad**: Crítica

**Regla**: `compute_self_hash(event)` DEBE excluir las claves `{"self_hash", "chain_hash", "prev_chain_hash", "persisted_at", "id"}` antes de canonicalizar y hashear con SHA-256.

**Justificación**: Si se incluyeran los propios hashes, la fórmula sería circular; `persisted_at` e `id` son metadata del persistidor, no del evento lógico.

**Verificación**: `apps/ctr-service/src/ctr_service/services/hashing.py::compute_self_hash` (conjunto exacto de exclusiones).

### RN-006 — `chain_hash` se calcula como SHA-256 de la concatenación de `self_hash` + `prev_chain_hash`
**Categoría**: Cálculo
**Fase origen**: F0
**Servicio(s)**: ctr-service
**Severidad**: Crítica

**Regla**: `chain_hash = SHA256( (self_hash || prev_chain_hash).encode("utf-8") ).hexdigest()`, donde `||` es concatenación de strings hex. Si `prev_chain_hash` es None (primer evento), se usa `GENESIS_HASH`.

**Justificación**: Esta es la primitiva que liga cada evento con el anterior. Cambiar el orden de concatenación o el encoding invalida toda la cadena.

**Verificación**: `apps/ctr-service/src/ctr_service/services/hashing.py::compute_chain_hash`.

### RN-007 — Los 12 servicios backend DEBEN exponer `/health/live` y `/health/ready`
**Categoría**: Operación
**Fase origen**: F0
**Servicio(s)**: los 12 servicios Python
**Severidad**: Media

**Regla**: Todo servicio FastAPI del monorepo DEBE exponer los endpoints `/health/live` (sondaje de liveness, siempre 200 si el proceso vive) y `/health/ready` (readiness, 200 sólo cuando las dependencias locales están OK).

**Justificación**: Kubernetes usa ambos probes con semántica distinta (liveness → restart; readiness → remover del load balancer). CronJobs de smoke tests dependen de readiness.

**Verificación**: `scripts/check-health.sh` + `make check-health`; cada servicio incluye `tests/test_health.py` con 3 tests básicos.

### RN-008 — Defaults de env para tests deterministas
**Categoría**: Operación
**Fase origen**: F0
**Servicio(s)**: todos
**Severidad**: Media

**Regla**: La suite de tests DEBE correr sin API keys reales ni red externa. Los defaults exigidos son `EMBEDDER=mock`, `RERANKER=identity`, `STORAGE=mock`, `LLM_PROVIDER=mock`. El `Makefile` los exporta automáticamente; sobreescribirlos rompe el contrato de determinismo.

**Justificación**: Reproducibilidad de CI + onboarding local sin cuenta Anthropic/AWS. Mencionado explícitamente en `CLAUDE.md` como gotcha.

**Verificación**: `Makefile` targets `test`, `test-fast` exportan los defaults; tests asumen los mocks.

### RN-009 — Naming convention SQL es obligatoria
**Categoría**: Persistencia
**Fase origen**: F0
**Servicio(s)**: todos los servicios con DB
**Severidad**: Baja

**Regla**: Las bases usan el `NAMING_CONVENTION` definido en `ctr_service/models/base.py` (y homólogos por servicio): `ix_`, `uq_`, `ck_`, `fk_`, `pk_` como prefijos. Ningún DDL directo puede introducir nombres que se desvíen, porque Alembic autogen asume esta convención al diffear.

**Justificación**: Migraciones Alembic sin falsos positivos; rollback reproducible.

**Verificación**: revisión de `alembic/versions/*.py` en PRs.

---

## F1 — Dominio Académico

### RN-010 — `Universidad` es el tenant raíz y NO tiene RLS
**Categoría**: Persistencia
**Fase origen**: F1
**Servicio(s)**: academic-service
**Severidad**: Alta

**Regla**: La tabla `universidades` NO lleva columna `tenant_id` ni policy RLS — porque es la tabla que define el propio tenant. Sólo el rol `superadmin` PUEDE escribirla.

**Justificación**: El tenant no puede filtrarse por sí mismo. Si `universidades` tuviese RLS, nadie podría crear el primer tenant.

**Verificación**: `apps/academic-service/alembic/versions/20260420_0001_initial_schema_with_rls.py` no llama `apply_tenant_rls` sobre `universidades`.

### RN-011 — `casbin_rules` es tabla global (sin RLS)
**Categoría**: Persistencia
**Fase origen**: F1
**Servicio(s)**: academic-service
**Severidad**: Alta

**Regla**: La tabla `casbin_rules` es compartida entre todos los tenants porque el modelo RBAC-con-dominios ya incluye el dominio (tenant) como parte de la policy. No lleva `tenant_id` ni RLS.

**Justificación**: Casbin necesita cargar todas las reglas en memoria para evaluar; filtrar por tenant rompería el modelo. El aislamiento viene de que las policies declaran el dominio explícitamente.

**Verificación**: Schema de `casbin_rules` en migración inicial.

### RN-012 — Soft-delete con `deleted_at` (nunca DELETE físico)
**Categoría**: Persistencia
**Fase origen**: F1
**Servicio(s)**: academic-service, content-service
**Severidad**: Alta

**Regla**: Las entidades de dominio que usan `TimestampMixin` DEBEN ser eliminadas con soft-delete (`UPDATE SET deleted_at = now()`). Las queries de lectura DEBEN filtrar `WHERE deleted_at IS NULL` explícitamente. Ningún servicio PUEDE ejecutar `DELETE` físico sobre entidades de dominio salvo en tareas de retention administrativa explícita.

**Justificación**: Auditabilidad académica + recuperación ante borrado accidental (ej. cátedra borra material equivocado).

**Verificación**: `BaseRepository.soft_delete()` en `repositories/base.py`; retrieval filtra por `m.deleted_at IS NULL`.

### RN-013 — Comisión sólo se crea si el Período está abierto
**Categoría**: Validación
**Fase origen**: F1
**Servicio(s)**: academic-service
**Severidad**: Alta

**Regla**: `ComisionService.crear()` DEBE verificar que `Periodo.estado == "abierto"` antes de persistir. Si el período está `cerrado` o `planificado`, la creación falla con un error de dominio.

**Justificación**: Regla académica: las comisiones se abren sólo dentro del período activo.

**Verificación**: `apps/academic-service/tests/integration/test_comision_periodo_cerrado.py`.

### RN-013bis — Plantillas de TP como fuente canónica
**Categoría**: Invariante
**Fase origen**: F1
**Servicio(s)**: academic-service
**Severidad**: Media

**Regla**: Cuando existe un `TareaPracticaTemplate` para una `(materia_id, periodo_id)`, las `TareaPractica` creadas por auto-instanciación comparten el `template_id` apuntando al template. La edición directa de una instancia (PATCH sobre la `TareaPractica` sin pasar por el template) setea `has_drift=true` pero **no** modifica la cadena CTR — el `Episode.problema_id` de los episodios sigue apuntando al UUID de la instancia. Una instancia con `has_drift=true` queda excluida del re-sync automático cuando el template se versiona.

**Justificación**: ADR-016. Separa la **fuente canónica editable por la cátedra** (template a nivel materia+periodo) de la **instancia estable por comisión** (`problema_id` inmutable que referencia la cadena CTR). Preserva la invariancia de `tutor_core._validate_tarea_practica` (las 6 condiciones siguen aplicando a la instancia) y de `curso_config_hash` per-Comisión (RN-046). El flag `has_drift` hace explícita la divergencia manual, evitando que un re-sync automático sobreescriba trabajo del docente.

**Verificación**: `apps/academic-service/tests/integration/test_tareas_practicas_templates_crud.py` (+ tests de drift y matriz Casbin `tarea_practica_template:CRUD`).

### RN-014 — Correlatividad DEBE existir como materia válida
**Categoría**: Validación
**Fase origen**: F1
**Servicio(s)**: academic-service
**Severidad**: Alta

**Regla**: `MateriaService.crear()` valida que todas las UUIDs en `correlativas` correspondan a materias existentes del mismo `plan_estudios_id`. Si alguna no existe, la creación falla.

**Justificación**: Integridad referencial semántica (no bastan FKs si se permite apuntar a materias de otro plan).

**Verificación**: tests unit de `MateriaService`.

### RN-015 — Cursor pagination obligatoria en listados
**Categoría**: Operación
**Fase origen**: F1
**Servicio(s)**: academic-service
**Severidad**: Media

**Regla**: Los endpoints `GET` que devuelven colecciones DEBEN usar cursor pagination (`after`/`limit`), nunca `offset`. El cursor es un UUID u otro ordenable monotónico.

**Justificación**: `OFFSET` escala mal con volumen; cursor es O(log n) con índice.

**Verificación**: `BaseRepository.list()` usa cursor; revisión de rutas nuevas.

### RN-016 — Cada operación de dominio DEBE escribir `AuditLog` en la misma transacción
**Categoría**: Auditoría
**Fase origen**: F1
**Servicio(s)**: academic-service
**Severidad**: Alta

**Regla**: Todos los services (`UniversidadService`, `CarreraService`, `MateriaService`, `ComisionService`, `PeriodoService`) DEBEN insertar una fila en `audit_logs` dentro de la misma transacción que la mutación. Si la mutación se rollbackea, el audit log también.

**Justificación**: Auditabilidad bit-a-bit del plano académico. Audit log orphan (mutación sin log) o log orphan (log sin mutación) son bugs.

**Verificación**: revisión de services; pattern `session.add(audit) + commit` dentro del mismo `async with`.

### RN-017 — Validación Pydantic de ranges y patterns en schemas
**Categoría**: Validación
**Fase origen**: F1
**Servicio(s)**: academic-service
**Severidad**: Media

**Regla**: Los schemas Pydantic v2 DEBEN incluir:
- Rangos numéricos explícitos (ej. `carga_horaria >= 1`).
- Patterns para códigos (ej. regex para `codigo_materia`).
- `model_validator` para reglas cruzadas (ej. `fecha_fin > fecha_inicio` en `Periodo`).

**Justificación**: Errores visibles en la capa de input, no cuando Postgres rechaza por constraint.

**Verificación**: `apps/academic-service/tests/unit/test_schemas.py` — 10 tests de validación.

### RN-018 — Casbin debe cargar todas las policies del seed sin duplicados

**Categoría**: Autorización
**Fase origen**: F1
**Servicio(s)**: academic-service
**Severidad**: Alta

**Regla**: El seed `seed-casbin` (`apps/academic-service/src/academic_service/seeds/casbin_policies.py`) carga la lista `POLICIES` completa en la tabla `casbin_rules` de forma idempotente (`DELETE + INSERT` en una sola transacción). El número exacto de policies evoluciona conforme se agregan recursos al sistema (universidad, facultad, carrera, plan, materia, periodo, comision, inscripcion, usuario_comision, tarea_practica, tarea_practica_template, audit, etc.) — el código fuente es la única fuente de verdad. El test de matriz `test_casbin_matrix.py` debe pasar cubriendo los 4 roles principales (estudiante, docente, docente_admin, superadmin) sobre los recursos definidos.

**Histórico**: en F1 (2026-04-20 inicial) la matriz cubría 4 roles × 17 recursos ≈ 65 policies. Conforme se agregaron entidades (`facultad:delete` y `plan:delete` durante Camino 3 = 79 policies; `tarea_practica:CRUD` durante Opción C = 93 policies; `tarea_practica_template:CRUD` durante ADR-016 = 107 policies), el número creció. Las HUs y reglas que dependen de un count específico están deprecadas.

**Verificación**:
- `make seed-casbin` debe correr exit 0
- Query: `SELECT COUNT(*) FROM casbin_rules WHERE ptype = 'p'` debe matchear `len(POLICIES)` del seed
- `pytest test_casbin_matrix.py` debe pasar

**ADR/Doc**: ADR-008.

### RN-019 — `@require_permission(resource, action)` en toda ruta de dominio
**Categoría**: Autorización
**Fase origen**: F1
**Servicio(s)**: academic-service
**Severidad**: Crítica

**Regla**: Todo endpoint que muta o lee entidades de dominio DEBE decorarse con `require_permission(resource, action)`. No está permitido validar roles manualmente dentro del handler — la validación es centralizada por Casbin.

**Justificación**: Autorización consistente y auditable; evita que un handler olvide un check.

**Verificación**: code review; ausencia del decorator en rutas de dominio es un bug.

### RN-020 — Superadmin es el único que PUEDE crear universidades
**Categoría**: Autorización
**Fase origen**: F1
**Servicio(s)**: academic-service
**Severidad**: Alta

**Regla**: La creación de `Universidad` requiere rol `superadmin`. Ni `docente_admin` ni ningún otro rol PUEDEN ejecutar `POST /api/v1/universidades`.

**Justificación**: El onboarding de universidades es un evento controlado (incluye creación de realm Keycloak, seed inicial).

**Verificación**: Policy Casbin específica para el recurso `universidad` y acción `crear`.

### RN-021 — Import CSV de inscripciones es dry-run obligatorio antes de commit
**Categoría**: Validación
**Fase origen**: F1
**Servicio(s)**: enrollment-service
**Severidad**: Alta

**Regla**: El flow de importación masiva DEBE pasar por `POST /api/v1/imports` (dry-run que valida columnas, tipos, enums y devuelve errores por fila) ANTES de `POST /api/v1/imports/{id}/commit` (aplicación transaccional). Si el dry-run no se ejecutó previamente con éxito, el commit falla.

**Justificación**: Volcar datos masivos sin preview genera corrupción difícil de revertir.

**Verificación**: `apps/enrollment-service/tests/*`; endpoint commit lee estado del dry-run.

### RN-022 — UUIDs fijos de desarrollo documentados en seeds
**Categoría**: Operación
**Fase origen**: F1
**Servicio(s)**: academic-service
**Severidad**: Baja

**Regla**: Los UUIDs usados en el realm `demo_uni` (superadmin, docente, estudiante, universidad demo) están fijados como constantes y documentados en el realm template Keycloak + seeds. No se auto-generan en dev para permitir comandos curl determinísticos.

**Justificación**: Onboarding + smoke tests reproducibles.

**Verificación**: `infrastructure/keycloak/*` + ejemplos en `docs/F1-STATE.md` (ver bloques `curl`).

---

## F2 — Contenido y RAG

### RN-023 — `RetrievalRequest.comision_id` es MANDATORIO
**Categoría**: Validación
**Fase origen**: F2
**Servicio(s)**: content-service
**Severidad**: Crítica

**Regla**: El schema Pydantic `RetrievalRequest` DEBE tener `comision_id: UUID` marcado como no-opcional. La ausencia genera error 422 antes de llegar al service.

**Justificación**: Sin `comision_id` el tutor podría recibir chunks de otras cátedras del mismo tenant — violaría aislamiento pedagógico.

**Verificación**: `apps/content-service/src/content_service/schemas/__init__.py`.

### RN-024 — Retrieval aplica filtro doble (RLS + `comision_id` en WHERE)
**Categoría**: Invariante
**Fase origen**: F2
**Servicio(s)**: content-service
**Severidad**: Crítica

**Regla**: La query SQL de retrieval DEBE incluir tanto la política RLS implícita (`current_setting('app.current_tenant')`) como un `WHERE c.comision_id = :comision_id` explícito. No está permitido depender de una sola capa.

**Justificación**: Defensa en profundidad. Un bug en la policy RLS o en el setter de `app.current_tenant` no debe causar leak cross-comisión.

**Verificación**: `apps/content-service/src/content_service/services/retrieval.py` — query SQL incluye ambos filtros.

### RN-025 — Pipeline de retrieval: top-20 vector → threshold → rerank → top-k
**Categoría**: Cálculo
**Fase origen**: F2
**Servicio(s)**: content-service
**Severidad**: Alta

**Regla**: `RetrievalService.retrieve()` DEBE ejecutar: (1) vector search con cosine distance, LIMIT 20 (`VECTOR_TOP_N = 20`), (2) filtro por `score_threshold`, (3) re-ranking cross-encoder sobre los restantes, (4) top-k final ordenado por `score_rerank`. El default de top-k es 5 para el uso del tutor.

**Justificación**: Balance calidad/latencia documentado por golden queries. Saltar re-ranking degrada hit rate; traer más de 20 antes del rerank cuesta latencia sin mejora significativa.

**Verificación**: `apps/content-service/src/content_service/services/retrieval.py::VECTOR_TOP_N = 20`; `default top_k=5` en `tutor_core.interact()`.

### RN-026 — `chunks_used_hash` = SHA-256 de IDs ordenados alfabéticamente y unidos por "|"
**Categoría**: Cálculo
**Fase origen**: F2
**Servicio(s)**: content-service, tutor-service
**Severidad**: Crítica

**Regla**: `chunks_used_hash = SHA256( "|".join(sorted(str(id) for id in chunk_ids)).encode("utf-8") ).hexdigest()`. Lista vacía produce el hash del string vacío.

**Justificación**: Reproducibilidad del RAG. El tutor puede reordenar internamente los chunks; lo que importa para auditoría es el conjunto usado, por eso el ordenamiento previo al hash es determinista.

**Verificación**: `apps/content-service/src/content_service/services/retrieval.py::_hash_chunk_ids`.

### RN-027 — Chunking de código: 1 sección = 1 chunk hasta `MAX_CODE_TOKENS = 1500`
**Categoría**: Cálculo
**Fase origen**: F2
**Servicio(s)**: content-service
**Severidad**: Media

**Regla**: Una sección de tipo `code_function` / `code_class` / `code_header` / `code_file` se persiste como un único chunk, salvo que exceda 1500 tokens (aproximación: 1 token = 4 caracteres, `CHARS_PER_TOKEN = 4`). En ese caso se subdivide por bloques lógicos separados por doble salto de línea.

**Justificación**: Semántica del código: funciones se entienden como unidad. Sólo cuando una sola función es desmesurada se divide.

**Verificación**: `apps/content-service/src/content_service/services/chunker.py::MAX_CODE_TOKENS = 1500`, `CHARS_PER_TOKEN = 4`.

### RN-028 — Chunking de prosa: ventana `target=512` tokens, overlap `50` tokens
**Categoría**: Cálculo
**Fase origen**: F2
**Servicio(s)**: content-service
**Severidad**: Media

**Regla**: Prosa usa ventana deslizante con `DEFAULT_TARGET_TOKENS = 512` y `DEFAULT_OVERLAP_TOKENS = 50`. La división respeta límites de oraciones (split heurístico por `.`, `!`, `?` seguido de espacio + mayúscula). El overlap conserva las últimas oraciones que acumulan ~overlap_chars caracteres.

**Justificación**: Ventana estándar en RAG para balance contexto/ruido; overlap evita perder conceptos que crucen el corte.

**Verificación**: `apps/content-service/src/content_service/services/chunker.py::DEFAULT_TARGET_TOKENS`, `DEFAULT_OVERLAP_TOKENS`.

### RN-029 — Tabla se persiste como 1 chunk atómico
**Categoría**: Cálculo
**Fase origen**: F2
**Servicio(s)**: content-service
**Severidad**: Media

**Regla**: Las secciones `section_type == "table"` se persisten como un único chunk independientemente de su tamaño. Nunca se dividen.

**Justificación**: La tabla es la unidad semántica mínima; partirla destruye la relación fila-columna.

**Verificación**: `chunker.py::_as_single_chunk` rama `table`.

### RN-030 — Hash SHA-256 de contenido por chunk para idempotencia
**Categoría**: Persistencia
**Fase origen**: F2
**Servicio(s)**: content-service
**Severidad**: Alta

**Regla**: Cada `FinalChunk` lleva `contenido_hash = SHA256(contenido.encode("utf-8")).hexdigest()`. Re-ingestar un material idéntico produce los mismos hashes → la operación es idempotente (el pipeline hace `DELETE old + INSERT new` dentro de la misma transacción; los hashes garantizan que nada cambie si el contenido no cambió).

**Justificación**: Re-ingesta sin duplicados; verificable offline.

**Verificación**: `chunker.py::_hash_text`.

### RN-031 — Embeddings con convención e5 (`passage:` / `query:`)
**Categoría**: Cálculo
**Fase origen**: F2
**Servicio(s)**: content-service
**Severidad**: Alta

**Regla**: El `SentenceTransformerEmbedder` que envuelve `intfloat/multilingual-e5-large` DEBE prefijar documentos con `"passage: "` al indexar y queries con `"query: "` al recuperar. El `MockEmbedder` produce 1024 dims normalizadas determinísticamente a partir de SHA-512 — mismo texto produce el mismo vector.

**Justificación**: La convención e5 es requisito del modelo para que los embeddings de passage/query caigan en el mismo espacio.

**Verificación**: `apps/content-service/src/content_service/embedding/` (implementaciones); tests de determinismo del mock.

### RN-032 — Índice pgvector IVFFlat con `lists=100` y `vector_cosine_ops`
**Categoría**: Operación
**Fase origen**: F2
**Servicio(s)**: content-service
**Severidad**: Media

**Regla**: La tabla `chunks` tiene índice IVFFlat con `lists = 100` sobre la columna `embedding` usando el operator class `vector_cosine_ops`. El MVP acepta recall ~95% compensado por re-ranking posterior.

**Justificación**: Balance recall/latencia en pgvector (ADR-011). Cambiar a HNSW requiere ADR nuevo.

**Verificación**: `apps/content-service/alembic/versions/20260521_0001_content_schema_with_rls.py`.

**ADR/Doc**: ADR-011.

### RN-033 — Upload de materiales limitado a 50 MB
**Categoría**: Validación
**Fase origen**: F2
**Servicio(s)**: content-service
**Severidad**: Media

**Regla**: `POST /api/v1/materiales` DEBE rechazar uploads con `Content-Length > 50 MB` retornando 413. El límite aplica al archivo completo previo a extracción.

**Justificación**: Presupuesto de memoria y tiempo de pipeline síncrono (F2). Archivos > 50 MB requieren ingesta async que llega post-MVP.

**Verificación**: `apps/content-service/src/content_service/routes/materiales.py`.

---

## F3 — Motor Pedagógico (CTR, tutor, governance, ai-gateway, clasificador)

### RN-034 — El CTR es append-only: NUNCA UPDATE ni DELETE de eventos
**Categoría**: Invariante
**Fase origen**: F3
**Servicio(s)**: ctr-service
**Severidad**: Crítica

**Regla**: La tabla `events` sólo admite `INSERT`. Ningún proceso PUEDE ejecutar `UPDATE` ni `DELETE` sobre filas de `events`. Cualquier corrección pedagógica se hace emitiendo un evento nuevo (ej. `anotacion_creada`), no mutando el viejo.

**Justificación**: Romper esto invalida la cadena criptográfica — base de la auditabilidad de la tesis.

**Verificación**: Code review + ausencia de `update(Event)` / `delete(Event)` en `apps/ctr-service/**`; tests de integridad detectan manipulación.

**ADR/Doc**: ADR-010, `CLAUDE.md` invariante #1.

### RN-035 — Primer evento de un episodio tiene `seq = 0` y `prev_chain_hash = GENESIS_HASH`
**Categoría**: Invariante
**Fase origen**: F3
**Servicio(s)**: ctr-service, tutor-service
**Severidad**: Crítica

**Regla**: El evento `episodio_abierto` de cualquier episodio DEBE tener `seq = 0`. El worker computa su `chain_hash` usando `prev_chain_hash = GENESIS_HASH` (64 ceros). El `events_count` inicial del `Episode` es 0 y `last_chain_hash` default es `"0"*64`.

**Justificación**: Arranque determinista de la cadena.

**Verificación**: `apps/ctr-service/src/ctr_service/workers/partition_worker.py` línea `prev_chain = ep.last_chain_hash if seq > 0 else GENESIS_HASH`.

### RN-036 — `seq` es estrictamente incremental sin gaps por episodio
**Categoría**: Invariante
**Fase origen**: F3
**Servicio(s)**: ctr-service
**Severidad**: Crítica

**Regla**: Dentro de un episodio, los `seq` de sus eventos DEBEN ser 0, 1, 2, ..., N sin gaps ni duplicados. El worker valida `seq == events_count` antes de insertar; si no coincide (y el evento no es duplicado idempotente), rechaza con `ValueError`.

**Justificación**: La cadena depende del orden; un gap rompe la reproducción.

**Verificación**: `partition_worker.py::_persist_event` — verifica `seq != expected_seq`; test `test_tutor_core.py::test_seqs_consecutivos`.

### RN-037 — Idempotencia por `(tenant_id, event_uuid)` con ON CONFLICT DO NOTHING
**Categoría**: Persistencia
**Fase origen**: F3
**Servicio(s)**: ctr-service
**Severidad**: Alta

**Regla**: El INSERT a `events` usa `ON CONFLICT (tenant_id, event_uuid) DO NOTHING`. Publicar el mismo `event_uuid` dos veces produce una única fila persistida.

**Justificación**: Garantiza semántica at-least-once del stream sin doble-procesamiento.

**Verificación**: `partition_worker.py::_persist_event` — statement `insert(...).on_conflict_do_nothing(...)`; test `test_ctr_end_to_end.py::idempotencia`.

### RN-038 — Sharding: `shard = int.from_bytes(SHA256(episode_id)[:4], "big") % N`
**Categoría**: Cálculo
**Fase origen**: F3
**Servicio(s)**: ctr-service
**Severidad**: Crítica

**Regla**: La partición a la que va un episodio se calcula con `shard_of(episode_id, num_partitions=NUM_PARTITIONS)` donde `NUM_PARTITIONS = 8` y el hash se toma de los primeros 4 bytes del SHA-256 del `str(episode_id)`. El resultado es estable entre deploys y no depende del seed de Python.

**Justificación**: Single-writer por partición — un episodio siempre va al mismo worker, eliminando race conditions sobre `events_count` y `last_chain_hash`.

**Verificación**: `apps/ctr-service/src/ctr_service/services/producer.py::shard_of` + test property-based.

### RN-039 — 3 reintentos máximo → DLQ + `integrity_compromised = true`
**Categoría**: Invariante
**Fase origen**: F3
**Servicio(s)**: ctr-service
**Severidad**: Crítica

**Regla**: Si un mensaje del stream falla al procesarse, el worker lo deja sin ACK (vuelve a entregarse). Al tercer intento (`MAX_ATTEMPTS = 3`), se mueve a stream DLQ `ctr.dead` + se inserta fila en `dead_letters` + se marca el episodio afectado como `integrity_compromised=true` y `estado='integrity_compromised'`.

**Justificación**: Backpressure bounded. Un evento roto no puede bloquear el stream ni ocultar su ruptura.

**Verificación**: `partition_worker.py::MAX_ATTEMPTS = 3`; `_move_to_dlq` ejecuta UPDATE sobre `Episode`. Nota: este `UPDATE` sobre `Episode` (no sobre `Event`) es una excepción explícita a RN-034 y es el ÚNICO UPDATE permitido en el ctr-service (flag `integrity_compromised` + transición `estado`).

### RN-040 — Integrity checker corre cada 6 horas
**Categoría**: Operación
**Fase origen**: F4 (seed conceptual F3)
**Servicio(s)**: ctr-service
**Severidad**: Alta

**Regla**: El `CronJob` `ctr-integrity-checker` corre cada 6 horas con `concurrencyPolicy: Forbid`. Recorre episodios cerrados de las últimas 24 h por default, recomputa la cadena desde `GENESIS_HASH` y marca `integrity_compromised=true` a los que no reconcilien. Exit code 1 si detecta nuevas violaciones → alerta Prometheus `CTRIntegrityViolationsDetected` (severity critical).

**Justificación**: Detección activa de manipulación, independiente de que alguien abra la UI.

**Verificación**: `ops/k8s/ctr-integrity-checker.yaml`, `ops/prometheus/slo-rules.yaml`.

### RN-041 — TUTOR_SERVICE_USER_ID es UUID fijo `00000000-0000-0000-0000-000000000010`
**Categoría**: Invariante
**Fase origen**: F3
**Servicio(s)**: tutor-service
**Severidad**: Alta

**Regla**: El service-account del tutor usa el UUID literal `00000000-0000-0000-0000-000000000010`. Este UUID NO cambia entre tenants, entornos ni deploys. Se usa como `caller_id` en los eventos del CTR emitidos por el tutor (excepto `codigo_ejecutado`, ver RN-042).

**Justificación**: Identificación reproducible del emisor "tutor" en toda la plataforma; permite trazabilidad.

**Verificación**: `apps/tutor-service/src/tutor_service/services/tutor_core.py::TUTOR_SERVICE_USER_ID`.

### RN-042 — `codigo_ejecutado` usa el `user_id` del ESTUDIANTE, no el del tutor
**Categoría**: Invariante
**Fase origen**: F6 (cierre del loop, seed en F3)
**Servicio(s)**: tutor-service, ctr-service
**Severidad**: Crítica

**Regla**: El evento `codigo_ejecutado` emitido por `TutorCore.emit_codigo_ejecutado(episode_id, user_id, payload)` DEBE llevar como `caller_id` el `user_id` del estudiante autenticado (obtenido del JWT, nunca del service-account del tutor). Cualquier otro evento del tutor (`episodio_abierto`, `prompt_enviado`, `tutor_respondio`, `episodio_cerrado`) lleva `TUTOR_SERVICE_USER_ID`.

**Justificación**: El estudiante es el autor real del código; registrarlo como tutor falsea la evidencia. Propiedad explícita en `CLAUDE.md`.

**Verificación**: `tutor_core.py::emit_codigo_ejecutado` pasa `user_id` (no `TUTOR_SERVICE_USER_ID`); test `test_tutor_core.py::caller_id_correcto`.

### RN-043 — Orden estricto dentro de un turno: PromptEnviado (seq N) → TutorRespondio (seq N+1)
**Categoría**: Invariante
**Fase origen**: F3
**Servicio(s)**: tutor-service
**Severidad**: Alta

**Regla**: En una interacción, el tutor DEBE emitir primero `prompt_enviado` con un `seq N` reservado por `sessions.next_seq()`, luego streamear la respuesta del LLM, y finalmente emitir `tutor_respondio` con `seq N+1`. Entre ambos no se permiten otros eventos del tutor-service.

**Justificación**: Semántica de turno atómico; el `chunks_used_hash` de ambos coincide (mismo retrieval).

**Verificación**: `tutor_core.py::interact`; test `test_tutor_core.py::seqs_consecutivos_multiturno`.

### RN-044 — `chunks_used_hash` se propaga de retrieval a eventos del CTR
**Categoría**: Invariante
**Fase origen**: F3
**Servicio(s)**: tutor-service, content-service, ctr-service
**Severidad**: Crítica

**Regla**: El `chunks_used_hash` devuelto por `content-service` en la respuesta de retrieval DEBE incluirse en el payload de los eventos `prompt_enviado` y `tutor_respondio` del CTR correspondientes al turno. Es el mismo hash en ambos eventos del turno.

**Justificación**: Reproducibilidad externa — cualquiera puede reconstruir exactamente qué material vio el tutor al responder.

**Verificación**: `tutor_core.py::interact` — `chunks_used_hash=retrieval.chunks_used_hash` en ambos eventos; test `test_tutor_core.py::chunks_used_hash_se_propaga` (marcado CRÍTICO).

### RN-045 — `SessionState` del tutor vive en Redis con TTL de 6 horas
**Categoría**: Persistencia
**Fase origen**: F3
**Servicio(s)**: tutor-service
**Severidad**: Media

**Regla**: `SessionManager.set()` guarda con `setex(key, SESSION_TTL, ...)` donde `SESSION_TTL = 6 * 3600` segundos (6 horas). Al cerrar episodio o expirar, el state se borra; la fuente de verdad histórica es el CTR en Postgres.

**Justificación**: Sesiones típicas duran < 1 h; TTL de 6 h absorbe pausas largas. Más allá, el estudiante abre episodio nuevo.

**Verificación**: `apps/tutor-service/src/tutor_service/services/session.py::SESSION_TTL`.

### RN-046 — `curso_config_hash` y `classifier_config_hash` son strings hex de 64 chars
**Categoría**: Validación
**Fase origen**: F3
**Servicio(s)**: tutor-service, ctr-service, classifier-service
**Severidad**: Alta

**Regla**: Los campos `curso_config_hash`, `classifier_config_hash`, `prompt_system_hash` almacenados en `Episode` y eventos son exactamente 64 caracteres hex (SHA-256). Los schemas Pydantic declaran `Field(min_length=64, max_length=64)`.

**Justificación**: Detecta mal armado de eventos antes de llegar al worker. Garantiza almacenamiento `CHAR(64)` en Postgres.

**Verificación**: `apps/tutor-service/src/tutor_service/routes/episodes.py::OpenEpisodeRequest`.

### RN-047 — Governance: PromptLoader falla LOUD ante hash mismatch
**Categoría**: Seguridad
**Fase origen**: F3
**Servicio(s)**: governance-service
**Severidad**: Crítica

**Regla**: `PromptLoader.load(name, version)` DEBE recomputar el SHA-256 del contenido de `system.md` y compararlo contra el hash declarado en `manifest.yaml` si éste existe. Si no coinciden, levanta `ValueError("Hash mismatch...")`. El servicio se niega a servir el prompt manipulado.

**Justificación**: Defensa ante manipulación post-commit del repo de prompts. Romper esto expondría estudiantes a prompts modificados sin firma.

**Verificación**: `apps/governance-service/src/governance_service/services/prompt_loader.py::load`; test `test_prompt_loader.py::fail_loud_ante_hash_mismatch`.

**ADR/Doc**: ADR-009.

### RN-048 — Hash de contenido = SHA-256 del UTF-8 exacto del archivo
**Categoría**: Cálculo
**Fase origen**: F3
**Servicio(s)**: governance-service
**Severidad**: Crítica

**Regla**: `compute_content_hash(content: str) = SHA256(content.encode("utf-8")).hexdigest()`. Sin normalización (sin strip, sin re-encoding, sin reemplazo de line endings). Cualquier edición cambia el hash.

**Justificación**: Evidencia inmutable de qué prompt se usó en cada episodio.

**Verificación**: `prompt_loader.py::compute_content_hash`.

### RN-049 — Classifier_config_hash usa canonical JSON con ensure_ascii=False
**Categoría**: Cálculo
**Fase origen**: F3
**Servicio(s)**: classifier-service
**Severidad**: Crítica

**Regla**: `compute_classifier_config_hash(reference_profile, tree_version="v1.0.0")` serializa `{"tree_version": ..., "profile": reference_profile}` con `json.dumps(sort_keys=True, ensure_ascii=False, separators=(",", ":"))` y hashea con SHA-256. No depende del orden de keys en el profile.

**Justificación**: Reproducibilidad del clasificador — mismo profile + mismo tree_version = mismo hash = misma clasificación determinista.

**Verificación**: `apps/classifier-service/src/classifier_service/services/pipeline.py::compute_classifier_config_hash`; test `test_pipeline_reproducibility.py::config_hash_invariante_al_orden_de_keys`.

### RN-050 — Clasificación append-only: marcar vieja `is_current=false` e INSERT nueva
**Categoría**: Persistencia
**Fase origen**: F3
**Servicio(s)**: classifier-service
**Severidad**: Crítica

**Regla**: `persist_classification()` DEBE primero ejecutar `UPDATE classifications SET is_current=false WHERE episode_id=? AND is_current=true`, luego INSERT de la nueva fila con `is_current=true`. Nunca se hace UPDATE sobre campos de la clasificación existente. Nunca se hace DELETE.

**Justificación**: ADR-010. Preserva histórico de qué clasificación vio el docente en cada momento.

**Verificación**: `classifier-service/src/classifier_service/services/pipeline.py::persist_classification`.

**ADR/Doc**: ADR-010.

### RN-051 — Las 5 coherencias se persisten SEPARADAS (no colapsar en score único)
**Categoría**: Invariante
**Fase origen**: F3
**Servicio(s)**: classifier-service
**Severidad**: Crítica

**Regla**: La tabla `classifications` almacena las 5 dimensiones numéricas como columnas separadas: `ct_summary`, `ccd_mean`, `ccd_orphan_ratio`, `cii_stability`, `cii_evolution`. NUNCA se reducen a un único score. La etiqueta N4 es una síntesis explícita del árbol de decisión, no un promedio opaco.

**Justificación**: Análisis multidimensional es el aporte de la tesis. Colapsar destruye la explicabilidad.

**Verificación**: schema de `Classification` en migración + `CLAUDE.md` invariante #4.

### RN-052 — Coherencia Temporal: ventanas por pausas > 5 minutos
**Categoría**: Cálculo
**Fase origen**: F3
**Servicio(s)**: classifier-service
**Severidad**: Alta

**Regla**: `compute_windows(events)` divide el episodio en ventanas de trabajo separadas por pausas mayores a `PAUSE_THRESHOLD = timedelta(minutes=5)` entre eventos consecutivos. Mínimo 3 eventos (`MIN_EVENTS_FOR_SCORE = 3`) para evaluar CT; si hay menos, CT se reporta como 0.5 con flag `insufficient_data=True`.

**Justificación**: Umbral empírico: una pausa de >5 min indica interrupción del flujo de trabajo (ir al baño, distracción).

**Verificación**: `apps/classifier-service/src/classifier_service/services/ct.py::PAUSE_THRESHOLD`, `MIN_EVENTS_FOR_SCORE`.

### RN-053 — Coherencia Código-Discurso: ventana de correlación = 2 minutos
**Categoría**: Cálculo
**Fase origen**: F3
**Servicio(s)**: classifier-service
**Severidad**: Alta

**Regla**: Una acción (prompt con `prompt_kind != "reflexion"` o `codigo_ejecutado`) se considera correlacionada con una reflexión (anotación o prompt con `prompt_kind="reflexion"`) si la reflexión ocurre dentro de `CORRELATION_WINDOW = timedelta(minutes=2)` POSTERIOR a la acción. `ccd_mean` normaliza el gap promedio a [0,1] (gap 0s → 1.0, gap 120s → 0.0). `ccd_orphan_ratio = orphans / total_actions`.

**Justificación**: Ventana empírica: una verbalización reflexiva tardía (>2 min) no está ya correlacionada con la acción.

**Verificación**: `apps/classifier-service/src/classifier_service/services/ccd.py::CORRELATION_WINDOW`.

### RN-054 — CII stability = Jaccard de tokens entre prompts consecutivos
**Categoría**: Cálculo
**Fase origen**: F3
**Servicio(s)**: classifier-service
**Severidad**: Alta

**Regla**: `cii_stability` = promedio de similitud Jaccard (intersección / unión de palabras lowercased de `payload.content`) entre pares de prompts consecutivos. Mínimo 2 prompts para calcular; con menos, se reporta 0.5 con `insufficient_data=True`.

**Justificación**: Proxy simple de "estabilidad del foco del estudiante"; alto = profundiza, bajo = salta de tema.

**Verificación**: `apps/classifier-service/src/classifier_service/services/cii.py::compute_cii`, `_jaccard_tokens`.

### RN-055 — CII evolution = slope normalizada de longitud de prompts
**Categoría**: Cálculo
**Fase origen**: F3
**Servicio(s)**: classifier-service
**Severidad**: Alta

**Regla**: `cii_evolution` se calcula con regresión lineal simple sobre la longitud (en palabras) de los prompts ordenados por seq. La slope se normaliza como `clamp(0.5 + slope / 4.0, 0, 1)` (slope 0 → 0.5 neutral, slope +2 palabras/iter → 1.0).

**Justificación**: Proxy de "evolución de elaboración del pensamiento" sin tokenización costosa.

**Verificación**: `cii.py::compute_cii` — bloque que computa `slope`.

### RN-056 — Árbol N4: 3 ramas mutuamente exclusivas
**Categoría**: Cálculo
**Fase origen**: F3
**Servicio(s)**: classifier-service
**Severidad**: Crítica

**Regla**: `classify(ct, ccd, cii, reference_profile)` devuelve EXACTAMENTE una de: `"delegacion_pasiva"`, `"apropiacion_superficial"`, `"apropiacion_reflexiva"`. Orden de evaluación: (1) delegación pasiva, (2) apropiación reflexiva, (3) default superficial.

**Justificación**: Etiquetas del árbol N4 de la tesis. Ambigüedad o null invalidaría la clasificación.

**Verificación**: `apps/classifier-service/src/classifier_service/services/tree.py::classify`.

### RN-057 — Gatillo de delegación extrema: `ccd_orphan_ratio >= 0.8`
**Categoría**: Cálculo
**Fase origen**: F3
**Servicio(s)**: classifier-service
**Severidad**: Crítica

**Regla**: La rama "delegación pasiva" se activa si (a) extrema: `ccd_orphan_ratio >= EXTREME_ORPHAN_THRESHOLD = 0.8` (sin importar CT) o (b) clásica: `ccd_orphan_ratio >= th["ccd_orphan_high"]` Y `ct_summary < th["ct_low"]`. El gatillo extremo captura patrones copy-paste sin verbalización independientemente del ritmo temporal.

**Justificación**: Sin el gatillo extremo, un estudiante que copia rápido sin pausas pero sin reflexionar sería clasificado como superficial, no como delegación.

**Verificación**: `tree.py::EXTREME_ORPHAN_THRESHOLD = 0.8`; test `test_tree.py::copy_paste_extremo_es_delegacion`.

### RN-058 — `reference_profile` tiene 6 umbrales configurables
**Categoría**: Validación
**Fase origen**: F3
**Servicio(s)**: classifier-service
**Severidad**: Alta

**Regla**: `DEFAULT_REFERENCE_PROFILE.thresholds` DEBE contener las 6 claves: `ct_low=0.35`, `ct_high=0.65`, `ccd_orphan_high=0.5`, `ccd_mean_low=0.35`, `cii_stability_low=0.2`, `cii_evolution_low=0.3`. Cualquier profile custom debe proveer las 6.

**Justificación**: El árbol asume la presencia de estos umbrales; faltar uno rompe la clasificación.

**Verificación**: `tree.py::DEFAULT_REFERENCE_PROFILE`.

### RN-059 — Cada clasificación incluye `reason` explicativa en prosa
**Categoría**: Auditoría
**Fase origen**: F3
**Servicio(s)**: classifier-service
**Severidad**: Alta

**Regla**: `ClassificationResult.reason` DEBE ser un string en español que contenga los valores numéricos concretos que gatillaron la decisión (ej. `"Delegación extrema: ccd_orphan_ratio=0.82, ct_summary=0.30"`). No se admiten reasons genéricas tipo "delegation pattern detected".

**Justificación**: Auditabilidad para defensa de tesis. Un revisor debe poder reconstruir el árbol leyendo la razón.

**Verificación**: `tree.py::classify` — todas las ramas construyen `reason` con f-string de valores.

### RN-060 — AI Gateway: TODO llamado LLM pasa por él
**Categoría**: Seguridad
**Fase origen**: F3
**Servicio(s)**: ai-gateway + consumidores (tutor, classifier)
**Severidad**: Crítica

**Regla**: Ningún servicio EXCEPTO `ai-gateway` PUEDE invocar directamente a Anthropic, OpenAI ni ningún provider de LLM/embedding. El `tutor-service` y demás clientes consumen únicamente `POST /api/v1/complete` y `POST /api/v1/stream` del ai-gateway.

**Justificación**: Budget centralizado, caching determinista, fallback, observabilidad. Descentralizar rompe el control de costos por tenant.

**Verificación**: ausencia de `import anthropic` en servicios no-ai-gateway; presencia de `AIGatewayClient` en sus lugares.

**ADR/Doc**: ADR-004.

### RN-061 — Budget tracking: clave Redis `aigw:budget:{tenant_id}:{feature}:{YYYY-MM}` con TTL 35 días
**Categoría**: Operación
**Fase origen**: F3
**Servicio(s)**: ai-gateway
**Severidad**: Alta

**Regla**: `BudgetTracker.charge()` usa `INCRBYFLOAT` atómico sobre la clave `aigw:budget:{tenant}:{feature}:{YYYY-MM}` (mes UTC) con `expire = 35 * 24 * 3600` segundos. `check()` lee el valor actual y compara contra `limit_usd`.

**Justificación**: Contabilidad por tenant+feature+mes; TTL 35 días cubre todo el mes más margen.

**Verificación**: `apps/ai-gateway/src/ai_gateway/services/budget_and_cache.py::BudgetTracker`.

### RN-062 — ResponseCache sólo cachea cuando `temperature == 0.0` y `stream == False`
**Categoría**: Cálculo
**Fase origen**: F3
**Servicio(s)**: ai-gateway
**Severidad**: Alta

**Regla**: `ResponseCache._is_cacheable(request)` retorna True únicamente si `request.temperature == 0.0 AND not request.stream`. La clave de caché es SHA-256 del canonical JSON de `{messages, model, temperature, max_tokens}` con `sort_keys=True`. TTL default 7 días.

**Justificación**: Sólo invocaciones deterministas son cacheables; cachear con temperature > 0 serviría respuestas incorrectas del "mismo" prompt.

**Verificación**: `budget_and_cache.py::ResponseCache._is_cacheable`, `_key`; test `no_cachea_con_temperature>0`.

### RN-063 — Alerta AIBudgetNearExhausted al 80% del presupuesto
**Categoría**: Operación
**Fase origen**: F4 (seed F3)
**Servicio(s)**: ai-gateway
**Severidad**: Media

**Regla**: La regla Prometheus `AIBudgetNearExhausted` dispara warning cuando el uso acumulado supera el 80% del límite mensual por tenant+feature.

**Justificación**: Permite que el docente_admin suba el límite o avise al tenant antes del corte total.

**Verificación**: `ops/prometheus/slo-rules.yaml`.

### RN-064 — Pricing por modelo Anthropic está hardcoded y revisado por fecha
**Categoría**: Cálculo
**Fase origen**: F3
**Servicio(s)**: ai-gateway
**Severidad**: Alta

**Regla**: `AnthropicProvider.PRICING` mapea `claude-sonnet-4-6` → `{input: 3.0, output: 15.0}` USD por 1M tokens, `claude-haiku-4-5` → `{0.8, 4.0}`, `claude-opus-4-7` → `{15.0, 75.0}`. Al cambiar precios de Anthropic, esta tabla DEBE actualizarse con el mismo PR que cambia el modelo default.

**Justificación**: Cost tracking fiel; precios incorrectos desalinean budget y realidad.

**Verificación**: `apps/ai-gateway/src/ai_gateway/providers/base.py::AnthropicProvider.PRICING`.

### RN-065 — Modelo default del tutor: `claude-sonnet-4-6`
**Categoría**: Operación
**Fase origen**: F3 (override por feature flag en F6)
**Servicio(s)**: tutor-service
**Severidad**: Media

**Regla**: El `default_model` de `TutorCore` es `"claude-sonnet-4-6"`. Se puede sobreescribir por episodio vía argumento `model=...` a `open_episode()`, típicamente cuando el flag `enable_claude_opus=true` para el tenant. El modelo efectivo se guarda en `SessionState.model` y se registra en el payload del evento `episodio_abierto` (queda auditable en el CTR qué modelo se usó).

**Justificación**: Haiku es barato pero flojo para tutoría socrática; Opus es caro; Sonnet es el sweet spot.

**Verificación**: `tutor_core.py::default_model`; payload de `episodio_abierto`.

---

## F4 — Hardening y Observabilidad

### RN-066 — Rate limit de `/api/v1/episodes/*` = 30 req/min por principal
**Categoría**: Seguridad
**Fase origen**: F4
**Servicio(s)**: api-gateway
**Severidad**: Media

**Regla**: Rate limiter del api-gateway aplica los siguientes tiers por path prefix:
- `/api/v1/episodes` → 30/min
- `/api/v1/retrieve` → 60/min
- `/api/v1/classify_episode` → 20/min
- default → 300/min

Ventana de 60 segundos; principal = `user_id` si hay JWT, si no `tenant_id`, si no IP.

**Justificación**: Proteger al tutor (caro en LLM) y al clasificador (caro en cómputo) sin bloquear tráfico general.

**Verificación**: `apps/api-gateway/src/api_gateway/services/rate_limit.py::PATH_LIMITS`, `DEFAULT_LIMIT`.

### RN-067 — Rate limiter inference de principal: user → tenant → IP
**Categoría**: Seguridad
**Fase origen**: F4
**Servicio(s)**: api-gateway
**Severidad**: Media

**Regla**: `principal_from_request(user_id, tenant_id, client_host)` DEBE seguir el orden exacto: si hay `user_id`, usar `u:{user_id}`; si no, si hay `tenant_id`, usar `t:{tenant_id}`; si no, `ip:{client_host or 'unknown'}`.

**Justificación**: Granularidad decreciente — usuario individual es ideal, IP es último recurso.

**Verificación**: `rate_limit.py::principal_from_request`.

### RN-068 — Rate limiter fail-open si Redis cae
**Categoría**: Seguridad
**Fase origen**: F4
**Servicio(s)**: api-gateway
**Severidad**: Alta

**Regla**: Si Redis no responde, el middleware de rate limit DEBE permitir el request (fail-open) y loggear el error. NUNCA DEBE bloquear tráfico legítimo porque cayó la infra de rate limiting.

**Justificación**: Un incidente de Redis no debe tumbar el piloto; el rate limit es protección, no disponibilidad crítica.

**Verificación**: middleware `rate_limit.py` — try/except con log + allow.

### RN-069 — Respuesta 429 lleva `Retry-After` y headers `X-RateLimit-*`
**Categoría**: Seguridad
**Fase origen**: F4
**Servicio(s)**: api-gateway
**Severidad**: Baja

**Regla**: Al rechazar por rate limit, el gateway responde `429 Too Many Requests` con headers `Retry-After: <seconds>`, `X-RateLimit-Limit: <max>`, `X-RateLimit-Remaining: 0`. El `Retry-After` iguala el TTL restante del contador o la ventana si TTL <= 0.

**Justificación**: Semantic HTTP; clientes bien escritos lo usan para backoff.

**Verificación**: `rate_limit.py::check` — retorna `retry_after_seconds`; middleware setea headers.

### RN-070 — Health checks EXENTOS del rate limit
**Categoría**: Operación
**Fase origen**: F4
**Servicio(s)**: api-gateway
**Severidad**: Media

**Regla**: Las rutas `/health/*`, `/metrics`, `/docs` están exentas del rate limiter.

**Justificación**: Kubernetes probes y scraping de Prometheus son frecuentes y legítimos; rate-limitarlos rompería monitoring.

**Verificación**: middleware `rate_limit.py` — lista de rutas exentas.

### RN-071 — OTel W3C Trace Context propagation obligatoria
**Categoría**: Auditoría
**Fase origen**: F4
**Servicio(s)**: todos
**Severidad**: Alta

**Regla**: Todos los servicios usan `packages/observability::setup_observability(app)` que configura OTLP gRPC exporter, propaga header `traceparent` (W3C), y auto-instrumenta FastAPI + httpx + SQLAlchemy + Redis. Los logs structlog inyectan `trace_id` y `span_id`. Un request debe ser trazable end-to-end cruzando todos los servicios con un único query en Jaeger.

**Justificación**: Debugging de cadenas largas (gateway → tutor → content → ai-gateway → ctr) es imposible sin trazas correlacionadas.

**Verificación**: `packages/observability/src/platform_observability/setup.py`; tests `test_setup.py`.

**ADR/Doc**: ADR-013.

### RN-072 — SLO tutor: first-token latency P95 < 3s warning, P99 < 8s critical
**Categoría**: Operación
**Fase origen**: F4
**Servicio(s)**: tutor-service, api-gateway
**Severidad**: Alta

**Regla**: PrometheusRules `TutorFirstTokenLatencyP95High` dispara warning si P95 > 3 s durante 10 min. `TutorFirstTokenLatencyP99Critical` dispara critical si P99 > 8 s durante 5 min. Estos thresholds son referencia para el canary gate.

**Justificación**: UX del estudiante: un "tutor que tarda" ya falló pedagógicamente.

**Verificación**: `ops/prometheus/slo-rules.yaml`.

### RN-073 — SLO error rate servicios: < 1% 5xx
**Categoría**: Operación
**Fase origen**: F4
**Servicio(s)**: todos
**Severidad**: Alta

**Regla**: Regla `ServiceErrorRateHigh` dispara alerta si el error rate 5xx de cualquier servicio supera 1% sostenido. El canary gate aborta un rollout ante el mismo umbral.

**Justificación**: 1% de 5xx es el tope aceptable; arriba, hay bug introducido por el deploy.

**Verificación**: `ops/prometheus/slo-rules.yaml`; criterio `canary-tutor-service.yaml`.

### RN-074 — CTR DLQ creciendo = alerta warning
**Categoría**: Operación
**Fase origen**: F4
**Servicio(s)**: ctr-service
**Severidad**: Alta

**Regla**: Regla `CTRDLQGrowing` dispara warning si `ctr.dead` stream supera N mensajes (threshold definido en slo-rules.yaml). Regla `CTRWorkerBacklog` dispara warning si `ctr.p{N}` supera 1000 mensajes pendientes.

**Justificación**: Backpressure perceptible antes de perder eventos.

**Verificación**: `ops/prometheus/slo-rules.yaml`.

---

## F5 — Multi-tenant, JWT, privacidad

### RN-075 — JWT RS256 obligatorio, HS256 prohibido
**Categoría**: Seguridad
**Fase origen**: F5
**Servicio(s)**: api-gateway
**Severidad**: Crítica

**Regla**: `JWTValidator.validate()` DEBE rechazar tokens cuyo header `alg != "RS256"`. Esto previene alg-confusion attacks donde un atacante firma con HMAC usando la pública del servidor como clave secreta.

**Justificación**: Vulnerabilidad clásica de JWT; evitarla es requisito mínimo de seguridad.

**Verificación**: `apps/api-gateway/src/api_gateway/services/jwt_validator.py::validate` línea `if alg != "RS256": raise`.

### RN-076 — Claims obligatorios: iss, aud, exp, iat, sub, tenant_id
**Categoría**: Seguridad
**Fase origen**: F5
**Servicio(s)**: api-gateway
**Severidad**: Crítica

**Regla**: `jwt.decode()` se invoca con `options={"require": ["exp", "iat", "iss", "sub"], "verify_exp": True, "verify_iss": True, "verify_aud": True, "verify_signature": True}`. Adicionalmente, la ausencia del claim custom `tenant_id` en el payload válido provoca `JWTValidationError("Token sin claim 'tenant_id' (tenant not onboarded?)")`.

**Justificación**: Tokens sin tenant_id no pertenecen a un tenant onboardeado — podrían venir de un realm viejo o ser manipulados.

**Verificación**: `jwt_validator.py::validate` y `_build_principal`.

### RN-077 — API-Gateway es el ÚNICO que valida JWT; servicios internos confían en X-*
**Categoría**: Seguridad
**Fase origen**: F5
**Servicio(s)**: api-gateway + todos los downstream
**Severidad**: Crítica

**Regla**: Solo el `api-gateway` valida firma, issuer, audience y expiration de JWTs. Los servicios internos confían ciegamente en los headers `X-User-Id`, `X-Tenant-Id`, `X-User-Email`, `X-User-Roles` reescritos autoritativamente por el gateway. NINGÚN servicio downstream PUEDE re-validar el JWT; NINGÚN cliente externo PUEDE setear estos headers directamente (Traefik + Keycloak son el único path).

**Justificación**: Un único source of truth de identidad; revalidar duplica código y abre bugs de divergencia. Explícito en `CLAUDE.md` invariante #2.

**Verificación**: `apps/api-gateway/src/api_gateway/middleware/jwt_auth.py` — reescribe headers; ausencia de validación JWT en otros servicios.

### RN-078 — JWKS cache con force-refresh ante `kid` desconocido
**Categoría**: Seguridad
**Fase origen**: F5
**Servicio(s)**: api-gateway
**Severidad**: Alta

**Regla**: `JWKSCache.get_key(kid)` hace refresh si el cache está stale (> `jwks_cache_ttl_seconds = 300 s`) o si el `kid` no está presente. Si tras refresh normal sigue sin aparecer, se hace un segundo refresh con `force=True`. Si aún falla, se levanta `JWTValidationError`.

**Justificación**: Rotación de claves Keycloak debe ser transparente; sin force-refresh, una rotación genera falsos 401 durante el TTL.

**Verificación**: `jwt_validator.py::JWKSCache`.

### RN-079 — Leeway de clock skew = 10 segundos
**Categoría**: Seguridad
**Fase origen**: F5
**Servicio(s)**: api-gateway
**Severidad**: Media

**Regla**: `jwt.decode(leeway=10)` tolera hasta 10 s de desfasaje de reloj entre Keycloak y el gateway.

**Justificación**: NTP no siempre sincroniza perfecto; sin leeway, pequeños desfases producen 401 transitorios.

**Verificación**: `jwt_validator.py::JWTValidatorConfig.leeway_seconds = 10`.

### RN-080 — X-Request-Id inyectado para correlación
**Categoría**: Auditoría
**Fase origen**: F5
**Servicio(s)**: api-gateway
**Severidad**: Media

**Regla**: El middleware JWT inyecta un header `X-Request-Id` (UUID) en cada request si el cliente no lo provee. Se propaga a todos los servicios downstream y aparece en logs.

**Justificación**: Correlación log ↔ trace sin necesidad de buscar por timestamp.

**Verificación**: `middleware/jwt_auth.py` — setear `X-Request-Id`.

### RN-081 — Anonymize: rotar pseudónimo en episodes, NUNCA tocar eventos CTR
**Categoría**: Privacidad
**Fase origen**: F5
**Servicio(s)**: platform-ops
**Severidad**: Crítica

**Regla**: `anonymize_student(student_pseudonym, data_source)` DEBE:
1. Generar un `new_pseudonym = uuid4()`.
2. Ejecutar `UPDATE episodes SET student_pseudonym = new WHERE student_pseudonym = original`.
3. NO TOCAR la tabla `events` del CTR.
4. NO TOCAR la tabla `classifications`.

**Justificación**: Disociación (right-to-be-forgotten compatible con art. 17.3.e GDPR). Modificar eventos CTR rompería la cadena criptográfica.

**Verificación**: `packages/platform-ops/src/platform_ops/privacy.py::anonymize_student`; test verifica `events_untouched > 0` tras anonymize.

### RN-082 — Export de datos firma con SHA-256 el paquete completo
**Categoría**: Privacidad
**Fase origen**: F5
**Servicio(s)**: platform-ops
**Severidad**: Alta

**Regla**: `ExportedData.compute_signature()` canonicaliza el dict exportado (sin el campo `signature_hash` mismo) y hashea con SHA-256. El hash firma el paquete entero: episodes, classifications, materials, events embebidos.

**Justificación**: Integridad verificable por el estudiante o investigador que recibe el export.

**Verificación**: `platform_ops/privacy.py::ExportedData.compute_signature`.

### RN-083 — Export académico: salt ≥ 16 caracteres
**Categoría**: Privacidad
**Fase origen**: F5
**Servicio(s)**: platform-ops
**Severidad**: Crítica

**Regla**: `AcademicExporter.__init__(salt, ...)` DEBE levantar `ValueError("salt debe tener al menos 16 chars para anonimización robusta")` si `not salt or len(salt) < 16`.

**Justificación**: Salts cortos son brute-forceables. 16 chars es el mínimo defensable ante un adversario con recursos académicos.

**Verificación**: `platform_ops/academic_export.py::AcademicExporter.__init__`.

### RN-084 — Export académico: `include_prompts=False` por default
**Categoría**: Privacidad
**Fase origen**: F5
**Servicio(s)**: platform-ops
**Severidad**: Crítica

**Regla**: `export_cohort(..., include_prompts=False)` es el default. Cuando `include_prompts=True`, el caller asume responsabilidad sobre el incremento del riesgo de re-identificación (nombres, ubicaciones, referencias personales en prompts).

**Justificación**: Minimización de datos por default. Incluir prompts es decisión explícita del investigador con consentimiento correspondiente.

**Verificación**: `academic_export.py::export_cohort` signature; test de default.

### RN-085 — Pseudónimo académico = hash(salt + UUID) tomando 12 chars hex
**Categoría**: Cálculo
**Fase origen**: F5
**Servicio(s)**: platform-ops
**Severidad**: Alta

**Regla**: `AcademicExporter._pseudonymize(uuid, prefix)` devuelve `f"{prefix}{SHA256((salt + str(uuid)).encode()).hexdigest()[:12]}"`. El mismo UUID con el mismo salt produce siempre el mismo alias → permite cross-referencia entre investigadores con el mismo salt.

**Justificación**: Determinismo reproducible + corto suficiente para usar en tablas.

**Verificación**: `academic_export.py::AcademicExporter._pseudonymize`.

### RN-086 — `salt_hash` se incluye en el export
**Categoría**: Auditoría
**Fase origen**: F5
**Servicio(s)**: platform-ops
**Severidad**: Alta

**Regla**: El dataset exportado incluye `salt_hash = SHA256(salt.encode()).hexdigest()[:16]`. Dos exports con el mismo `salt_hash` son cross-referenciables; distinto `salt_hash` implica imposibilidad de cruzar sin conocer ambos salts.

**Justificación**: Reproducibilidad entre análisis sin exponer el salt en claro.

**Verificación**: `academic_export.py::CohortDataset.salt_hash`.

### RN-087 — Feature flags no-declaradas levantan `FeatureNotDeclaredError`
**Categoría**: Validación
**Fase origen**: F5
**Servicio(s)**: platform-ops
**Severidad**: Alta

**Regla**: `FeatureFlags.get_value(tenant_id, feature)` DEBE levantar `FeatureNotDeclaredError` si la feature no está en `defaults` ni en override del tenant. Nunca retornar silent false/None.

**Justificación**: Forza a declarar toda nueva feature en el YAML antes de consumirla en código; evita features "fantasmas" silenciosas.

**Verificación**: `platform_ops/feature_flags.py::get_value`.

### RN-088 — Feature flags reload por hash del archivo cada 60 s default
**Categoría**: Operación
**Fase origen**: F5
**Servicio(s)**: platform-ops
**Severidad**: Media

**Regla**: `FeatureFlags` recarga el archivo cada `reload_interval_seconds` (default 60). Si el SHA-256 del contenido no cambió, no rebuildea el snapshot (ahorra parsing).

**Justificación**: Cambios de flags se propagan en < 1 min sin restart.

**Verificación**: `feature_flags.py::_maybe_reload`.

### RN-089 — `is_enabled` tipado estricto: bool o TypeError
**Categoría**: Validación
**Fase origen**: F5
**Servicio(s)**: platform-ops
**Severidad**: Media

**Regla**: `FeatureFlags.is_enabled(tenant, feature)` DEBE levantar `TypeError` si el valor resuelto no es `bool`. Previene leer como flag una feature que en realidad contiene un int o string.

**Justificación**: Fail-fast ante mal uso; un `max_episodes_per_day=50` leído como `is_enabled` produciría `True` silenciosamente.

**Verificación**: `feature_flags.py::is_enabled`.

---

## F6 — Piloto UNSL (LDAP, código ejecutado, Kappa, canary)

### RN-090 — LDAP federation: `editMode = READ_ONLY`
**Categoría**: Privacidad
**Fase origen**: F6
**Servicio(s)**: platform-ops
**Severidad**: Crítica

**Regla**: `LDAPFederator._ldap_config_to_kc_config()` setea siempre `"editMode": ["READ_ONLY"]` en el config del provider Keycloak. Complementariamente, `"syncRegistrations": ["false"]`.

**Justificación**: Condición del convenio con UNSL — la plataforma nunca modifica el directorio institucional. Cambiarlo requiere nuevo convenio.

**Verificación**: `packages/platform-ops/src/platform_ops/ldap_federation.py::_ldap_config_to_kc_config`.

### RN-091 — Mapper `tenant_id` hardcoded en el provider LDAP
**Categoría**: Seguridad
**Fase origen**: F6
**Servicio(s)**: platform-ops
**Severidad**: Crítica

**Regla**: `LDAPFederator.configure()` DEBE instalar un mapper que inyecte `tenant_id` (literal, hardcoded con el UUID del tenant) en todos los tokens emitidos por el realm. Sin este mapper, los usuarios LDAP recibirían JWTs sin `tenant_id` → rechazados por api-gateway (RN-076).

**Justificación**: Cierra el círculo auth: LDAP → Keycloak → JWT con tenant_id → api-gateway acepta.

**Verificación**: `ldap_federation.py::_ensure_tenant_id_mapper`.

### RN-092 — Onboarding Keycloak es idempotente
**Categoría**: Operación
**Fase origen**: F5-F6
**Servicio(s)**: platform-ops
**Severidad**: Alta

**Regla**: `tenant_onboarding.py` DEBE poder correrse múltiples veces sin duplicar recursos: realm, client, claim mapper, roles, usuario admin. Si el objeto existe, se reutiliza; si no, se crea. Reporta qué se ejecutó y qué se reutilizó.

**Justificación**: Re-ejecutar el onboarding tras un fallo parcial NO debe corromper el realm.

**Verificación**: `packages/platform-ops/tests/test_tenant_onboarding.py::idempotencia`.

### RN-093 — Admin inicial creado con `requiredAction: UPDATE_PASSWORD`
**Categoría**: Seguridad
**Fase origen**: F5-F6
**Servicio(s)**: platform-ops
**Severidad**: Alta

**Regla**: El onboarding crea el usuario admin con password temporal + flag `requiredAction: ["UPDATE_PASSWORD"]`. En el primer login, Keycloak obliga a cambiar la password. La password temporal viene de env var `KEYCLOAK_ADMIN_PASSWORD`, nunca de argparse.

**Justificación**: Credenciales iniciales comprometidas son ataque clásico; el change-on-first-login lo mitiga.

**Verificación**: `tenant_onboarding.py`; test `password_temporal_con_update_password`.

### RN-094 — TenantSecretResolver: orden mount → env per-tenant → env global → error
**Categoría**: Seguridad
**Fase origen**: F5
**Servicio(s)**: platform-ops, ai-gateway
**Severidad**: Alta

**Regla**: `TenantSecretResolver.get_llm_api_key(tenant, provider)` busca en este orden exacto:
1. Archivo mount K8s: `/etc/platform/llm-keys/{tenant_id}/{provider}.key` (non-vacío).
2. Env var per-tenant: `LLM_KEY_{TENANT_UUID}_{PROVIDER}`.
3. Env var global: `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`.
4. Si nada: `SecretNotFoundError` con mensaje accionable.

**Justificación**: Aislamiento por tenant posible; fallback a global si el tenant no tiene key propia; archivo vacío NO cuenta (típico error de secret vacío).

**Verificación**: `packages/platform-ops/tests/test_tenant_secrets.py`.

### RN-095 — Kappa de Cohen con interpretación Landis & Koch
**Categoría**: Cálculo
**Fase origen**: F6
**Servicio(s)**: platform-ops, analytics-service
**Severidad**: Alta

**Regla**: `compute_cohen_kappa(ratings)` implementa la fórmula `κ = (p_o - p_e) / (1 - p_e)`. La interpretación de `KappaResult.interpretation` sigue Landis & Koch 1977:
- `< 0.20` → "pobre"
- `0.21 – 0.40` → "justo"
- `0.41 – 0.60` → "moderado"
- `0.61 – 0.80` → "sustancial"
- `0.81 – 1.00` → "casi perfecto"

Si `p_e == 1.0` (convergencia trivial), se reporta `kappa=1.0` por convención.

**Justificación**: Escala estándar de la literatura de investigación educativa; objetivo de la tesis κ ≥ 0.6.

**Verificación**: `packages/platform-ops/src/platform_ops/kappa_analysis.py::KappaResult.interpretation`.

### RN-096 — Categorías Kappa estrictas: 3 exactas
**Categoría**: Validación
**Fase origen**: F6
**Servicio(s)**: platform-ops, analytics-service
**Severidad**: Alta

**Regla**: `compute_cohen_kappa` valida que `r.rater_a` y `r.rater_b` pertenezcan a `CATEGORIES = ("delegacion_pasiva", "apropiacion_superficial", "apropiacion_reflexiva")`. Cualquier otro string produce `ValueError`. El endpoint `POST /analytics/kappa` usa Pydantic `Literal` para bloquear antes.

**Justificación**: Cálculo Kappa requiere matriz de confusión sobre categorías cerradas; admitir arbitrarias invalida la métrica.

**Verificación**: `kappa_analysis.py::CATEGORIES`; schema de endpoint.

### RN-097 — BruteForceRule: 5 logins fallidos en 5 minutos → HIGH
**Categoría**: Seguridad
**Fase origen**: F6
**Servicio(s)**: platform-ops
**Severidad**: Alta

**Regla**: `BruteForceRule(threshold=5, window=timedelta(minutes=5))` produce `SuspiciousAccess(severity=HIGH, rule_id="brute_force_login")` cuando un principal acumula ≥ 5 eventos `action="login_failed"` dentro de 5 minutos sliding window.

**Justificación**: Detección clásica; thresholds de la literatura.

**Verificación**: `packages/platform-ops/src/platform_ops/audit.py::BruteForceRule`.

### RN-098 — CrossTenantAccessRule: severidad CRITICAL
**Categoría**: Seguridad
**Fase origen**: F6
**Servicio(s)**: platform-ops
**Severidad**: Crítica

**Regla**: Cualquier `AccessEvent` con `status_code in (401, 403)` y `error_reason` conteniendo la palabra "tenant" (case-insensitive) genera `SuspiciousAccess(severity=CRITICAL)`. Aunque el gateway YA rechazó el request, el intento queda registrado.

**Justificación**: Intento de escalada horizontal es evento grave por definición.

**Verificación**: `audit.py::CrossTenantAccessRule`.

### RN-099 — RepeatedAuthFailuresRule: 10 errores 401 en 10 min → MEDIUM
**Categoría**: Seguridad
**Fase origen**: F6
**Servicio(s)**: platform-ops
**Severidad**: Media

**Regla**: `RepeatedAuthFailuresRule(threshold=10, window=timedelta(minutes=10))` detecta 10 respuestas 401 del mismo principal en 10 minutos → severidad MEDIUM (puede ser token podrido o refresh token robado).

**Verificación**: `audit.py::RepeatedAuthFailuresRule`.

### RN-100 — Canary tutor-service: 10% (2 min) → 50% (5 min) → 100%
**Categoría**: Operación
**Fase origen**: F6
**Servicio(s)**: tutor-service + Argo Rollouts
**Severidad**: Alta

**Regla**: El Rollout de tutor-service sigue strategy canary con pasos:
1. `setWeight: 10` por 2 min.
2. Análisis automático (3 métricas).
3. `setWeight: 50` por 5 min.
4. Segundo análisis.
5. `setWeight: 100`.

Criterios de rollback automático:
- Latencia P95 del tutor > 3 s.
- Error rate 5xx > 1%.
- `ctr_episodes_integrity_compromised_total` incrementa (cualquier delta positivo).

**Justificación**: Cambios al tutor afectan pedagogía en vivo; canary gradual + criterio específico de CTR previene catástrofes.

**Verificación**: `ops/k8s/canary-tutor-service.yaml`.

**ADR/Doc**: ADR-015 (reasoning).

### RN-101 — Deploy workers CTR: rolling (NUNCA blue-green)
**Categoría**: Operación
**Fase origen**: F6
**Servicio(s)**: ctr-service
**Severidad**: Crítica

**Regla**: Los 8 pods del StatefulSet del ctr-service (uno por partición) se actualizan con rolling update. Cada pod espera hasta que el anterior libere el lease (30 s grace period); `XCLAIM` transfiere mensajes pendientes al pod nuevo. NUNCA blue-green (requeriría dos instancias por partición → viola single-writer).

**Justificación**: ADR-015. La invariante single-writer por partición es inviolable.

**Verificación**: `infrastructure/helm/platform/templates/ctr-workers.yaml` + ADR-015.

### RN-102 — Servicios HTTP del plano académico: blue-green atómico
**Categoría**: Operación
**Fase origen**: F6
**Servicio(s)**: academic, evaluation, analytics, frontends
**Severidad**: Alta

**Regla**: academic-service, evaluation-service, analytics-service y los 3 frontends usan blue-green con selector Service que se flipea atómicamente. Rollback < 30 s flipando el selector.

**Justificación**: ADR-015. Servicios stateless sin conexiones persistentes permiten switch atómico seguro.

**Verificación**: `infrastructure/helm/platform/templates/*.yaml` con labels `version: blue|green`.

---

## F7 — Pipeline empírico (longitudinal, A/B, export async)

### RN-103 — Escala ordinal N4: delegacion=0 < superficial=1 < reflexiva=2
**Categoría**: Cálculo
**Fase origen**: F7
**Servicio(s)**: platform-ops
**Severidad**: Alta

**Regla**: `APPROPRIATION_ORDINAL = {"delegacion_pasiva": 0, "apropiacion_superficial": 1, "apropiacion_reflexiva": 2}`. Esta escala se usa para comparar trayectorias de progresión. Cualquier cálculo de "mejora/empeora" por estudiante usa esta escala.

**Justificación**: Orden pedagógico explícito; el número es ordinal, no intervalar (NO sumar ni promediar entre categorías incompatibles).

**Verificación**: `packages/platform-ops/src/platform_ops/longitudinal.py::APPROPRIATION_ORDINAL`.

### RN-104 — progression_label: tolerancia 0.25 en primer vs último tercio
**Categoría**: Cálculo
**Fase origen**: F7
**Servicio(s)**: platform-ops
**Severidad**: Alta

**Regla**: `StudentTrajectory.progression_label()` compara la media ordinal del primer tercio de episodios contra la media del último tercio:
- `last - first > 0.25` → "mejorando"
- `first - last > 0.25` → "empeorando"
- Si ninguna: "estable"
- Si `n_episodes < 3`: "insuficiente"

**Justificación**: Tolerancia 0.25 absorbe ruido dentro de una misma categoría; 3 episodios es el mínimo para terciles significativos.

**Verificación**: `longitudinal.py::StudentTrajectory.progression_label`, `tercile_means`.

### RN-105 — CohortProgression.net_progression_ratio ∈ [-1, 1]
**Categoría**: Cálculo
**Fase origen**: F7
**Servicio(s)**: platform-ops
**Severidad**: Alta

**Regla**: `net_progression_ratio = (mejorando - empeorando) / n_students_with_enough_data`. Si `n_students_with_enough_data == 0`, devuelve 0.0. El rango está acotado en [-1, 1]; positivo = cohorte mejorando netamente.

**Justificación**: Indicador único interpretable para respuesta cuantitativa a la hipótesis central de la tesis.

**Verificación**: `longitudinal.py::CohortProgression.net_progression_ratio`.

### RN-106 — Dashboard piloto: net_progression thresholds visuales
**Categoría**: Operación
**Fase origen**: F8
**Servicio(s)**: Grafana
**Severidad**: Media

**Regla**: El panel "net_progression_ratio time-series" en `unsl-pilot.json` usa thresholds visuales: rojo < 0, amarillo 0–0.3, verde > 0.3.

**Justificación**: Lectura rápida por parte del investigador durante el piloto.

**Verificación**: `ops/grafana/dashboards/unsl-pilot.json`.

### RN-107 — A/B profile determinista: mismo profile dos veces = mismas predicciones
**Categoría**: Invariante
**Fase origen**: F7
**Servicio(s)**: platform-ops, classifier-service
**Severidad**: Crítica

**Regla**: `compare_profiles(episodes, profiles, classify_fn, compute_hash_fn)` es determinista. Correr con la misma lista de episodios y el mismo profile dos veces produce exactamente las mismas predicciones y el mismo Kappa.

**Justificación**: Reproducibilidad empírica — condición para publicar resultados A/B en la tesis.

**Verificación**: `packages/platform-ops/tests/test_ab_integration.py` — test de reproducibilidad.

### RN-108 — Export worker: transiciones PENDING → RUNNING → SUCCEEDED | FAILED
**Categoría**: Persistencia
**Fase origen**: F7
**Servicio(s)**: platform-ops, analytics-service
**Severidad**: Alta

**Regla**: `ExportWorker` consume jobs con `status=PENDING` → `RUNNING` → (`SUCCEEDED` si el export terminó | `FAILED` si hubo excepción, con `error` lleno). No se permiten otras transiciones (no saltar estados, no volver de SUCCEEDED a RUNNING).

**Justificación**: Máquina de estados simple y trazable; cualquier consumidor del `status` puede confiar en el invariante.

**Verificación**: `platform_ops/export_worker.py::ExportWorker.run_forever`.

### RN-109 — Export worker lifecycle integrado al lifespan del analytics-service
**Categoría**: Operación
**Fase origen**: F7
**Servicio(s)**: analytics-service
**Severidad**: Alta

**Regla**: El worker async se arranca en el `lifespan` del FastAPI app (`start_worker()` en startup, `stop_worker()` con timeout en shutdown). No se usa `asyncio.create_task` suelto; el cleanup debe ser graceful (terminar jobs en curso o marcarlos FAILED antes de exit).

**Justificación**: Shutdown sucio deja jobs en estado inconsistente.

**Verificación**: `apps/analytics-service/src/analytics_service/main.py`.

### RN-110 — `cleanup_old()` borra jobs SUCCEEDED/FAILED tras N tiempo
**Categoría**: Operación
**Fase origen**: F7
**Servicio(s)**: platform-ops
**Severidad**: Media

**Regla**: `ExportJobStore.cleanup_old(older_than_seconds)` elimina jobs con `status in (SUCCEEDED, FAILED)` cuyo `completed_at` supere la antigüedad dada. PENDING y RUNNING NO se tocan.

**Justificación**: Retention automática sin riesgo de matar jobs vivos.

**Verificación**: `platform_ops/export_worker.py::ExportJobStore.cleanup_old`.

### RN-111 — Análisis Kappa para A/B requiere gold standard humano
**Categoría**: Validación
**Fase origen**: F7
**Servicio(s)**: analytics-service
**Severidad**: Alta

**Regla**: `POST /api/v1/analytics/ab-test-profiles` requiere que cada episodio del set incluya `human_label` válido (una de las 3 categorías N4). El endpoint valida con Pydantic `Literal` antes de clasificar.

**Justificación**: A/B sin gold standard no produce Kappa útil.

**Verificación**: `apps/analytics-service/src/analytics_service/routes/*` schema del endpoint.

---

## F8 — Integración DB real y protocolo

### RN-112 — `set_tenant_rls(session, tenant_id)` se llama al inicio de cada transacción
**Categoría**: Invariante
**Fase origen**: F8
**Servicio(s)**: analytics-service + packages/platform-ops/real_datasources
**Severidad**: Crítica

**Regla**: Cualquier sesión SQLA que consulta tablas con RLS DEBE ejecutar `SELECT set_config('app.current_tenant', :t, true)` (o su helper `set_tenant_rls(session, tenant_id)`) al comienzo de la transacción. Sin este SET LOCAL, la query retorna resultados vacíos (por RN-137) o dispara error si alguna constraint NOT NULL lo requiere.

**Justificación**: Activa el filtro RLS para el tenant correspondiente.

**Verificación**: `packages/platform-ops/src/platform_ops/real_datasources.py::set_tenant_rls`.

### RN-113 — data_source_factory cae al stub si faltan env vars DB
**Categoría**: Operación
**Fase origen**: F8
**Servicio(s)**: analytics-service
**Severidad**: Alta

**Regla**: `data_source_factory(tenant_id)` inspecciona `CTR_STORE_URL` y `CLASSIFIER_DB_URL`. Si ambas están seteadas, crea sesiones reales (`RealCohortDataSource`). Si al menos una falta, cae al stub in-memory (modo dev). El binario es idéntico en dev y prod; sólo cambian env vars.

**Justificación**: Reduce divergencia entre código-dev y código-prod.

**Verificación**: `apps/analytics-service/src/analytics_service/services/factory.py`.

### RN-114 — Doble filtro en queries del real_datasources (defensivo)
**Categoría**: Seguridad
**Fase origen**: F8
**Servicio(s)**: platform-ops, analytics-service
**Severidad**: Crítica

**Regla**: Las queries de `RealCohortDataSource` aplican tanto `SET LOCAL app.current_tenant` (RLS automático) como `WHERE tenant_id = :t` explícito. Mismo patrón que retrieval (RN-024).

**Justificación**: Defensa en profundidad documentada.

**Verificación**: `packages/platform-ops/src/platform_ops/real_datasources.py`.

### RN-115 — Longitudinal agrupa en Python (tablas en DBs distintas)
**Categoría**: Operación
**Fase origen**: F8
**Servicio(s)**: platform-ops
**Severidad**: Media

**Regla**: `RealLongitudinalDataSource` NO ejecuta JOINs cross-base. La agrupación de classifications por estudiante se hace en memoria Python después de fetchear las dos tablas separadamente. Acepta el costo para volúmenes del piloto.

**Justificación**: ADR-003 prohíbe JOINs cross-base. El volumen del piloto (180 estudiantes × 30 episodios) permite agrupar en memoria.

**Verificación**: `real_datasources.py::RealLongitudinalDataSource`.

### RN-116 — Protocolo UNSL es DOCX regenerable desde docx-js
**Categoría**: Auditoría
**Fase origen**: F8
**Servicio(s)**: docs/pilot
**Severidad**: Alta

**Regla**: `docs/pilot/protocolo-piloto-unsl.docx` se genera desde `docs/pilot/generate_protocol.js` con `make generate-protocol`. La fuente es el JS, no el binario. Cambios al protocolo editan el JS + regeneran.

**Justificación**: Revisiones del comité de ética deben ser versionables; el binario no lo es.

**Verificación**: `Makefile::generate-protocol`; presencia de `generate_protocol.js`.

### RN-117 — Consentimiento informado: 4 derechos explícitos
**Categoría**: Privacidad
**Fase origen**: F8
**Servicio(s)**: docs/pilot
**Severidad**: Crítica

**Regla**: El Anexo A del protocolo (consentimiento informado) DEBE declarar explícitamente los 4 derechos del estudiante: (1) retiro, (2) acceso a sus datos, (3) olvido (anonymize), (4) queja ante autoridad de aplicación (Ley 25.326).

**Justificación**: Requerimiento del Comité de Ética de UNSL + GDPR compatibility.

**Verificación**: `docs/pilot/protocolo-piloto-unsl.docx` sección Anexo A.

### RN-118 — Stopping rules documentadas en sección 4
**Categoría**: Auditoría
**Fase origen**: F8
**Servicio(s)**: docs/pilot
**Severidad**: Alta

**Regla**: La sección 4 del protocolo define criterios explícitos de ajuste/stop (umbrales de éxito, criterios bajo los cuales el piloto se modifica o interrumpe).

**Justificación**: Científicamente obligatorio para estudio humano de 16 semanas.

**Verificación**: `docs/pilot/protocolo-piloto-unsl.docx` sección 4.

---

## F9 — Preflight operacional

### RN-119 — RLS activado con `FORCE ROW LEVEL SECURITY`
**Categoría**: Seguridad
**Fase origen**: F9
**Servicio(s)**: ctr-service, classifier-service (las que faltaban)
**Severidad**: Crítica

**Regla**: Las migraciones F9 `20260721_0002_enable_rls_on_ctr_tables` y `20260902_0002_enable_rls_on_classifier_tables` aplican `ENABLE ROW LEVEL SECURITY` + `FORCE ROW LEVEL SECURITY` sobre `episodes`, `events`, `dead_letters` y `classifications`. El `FORCE` asegura que incluso el owner de la tabla respete la policy.

**Justificación**: Sin `FORCE`, el usuario DB propietario bypassea RLS accidentalmente — bug típico en primeros despliegues.

**Verificación**: migraciones citadas; `packages/platform-ops/tests/test_rls_postgres.py`.

### RN-120 — Default empty: sin `SET LOCAL`, queries retornan 0 filas
**Categoría**: Seguridad
**Fase origen**: F9
**Servicio(s)**: ctr-service, classifier-service, content-service, academic-service
**Severidad**: Crítica

**Regla**: Sin ejecutar `SET LOCAL app.current_tenant`, las queries sobre tablas RLS retornan set vacío (fail-safe). Olvidar el set produce "no veo nada" en vez de "veo todo".

**Justificación**: Default seguro: un bug de código que olvida setear el tenant no expone data de todos los tenants.

**Verificación**: `packages/platform-ops/tests/test_rls_postgres.py::sin_set_local_queries_vacias`.

### RN-121 — INSERT con `tenant_id` diferente al `SET LOCAL` falla por WITH CHECK
**Categoría**: Seguridad
**Fase origen**: F9
**Servicio(s)**: ctr-service, classifier-service
**Severidad**: Crítica

**Regla**: Las policies RLS incluyen `WITH CHECK (tenant_id = current_setting('app.current_tenant')::uuid)` además del `USING`. Un INSERT con `tenant_id` distinto al seteado falla.

**Justificación**: No permite escribir cross-tenant aunque el USING lo permitiera leer.

**Verificación**: `test_rls_postgres.py::insert_tenant_distinto_falla`.

### RN-122 — `SET LOCAL` se resetea al commit
**Categoría**: Seguridad
**Fase origen**: F9
**Servicio(s)**: Postgres RLS
**Severidad**: Alta

**Regla**: Cada transacción nueva requiere re-setear `app.current_tenant`. Confiar en el setting de una transacción anterior es bug.

**Justificación**: Comportamiento estándar de `SET LOCAL` en Postgres; aislar transacciones.

**Verificación**: `test_rls_postgres.py::set_local_se_resetea_al_commit`.

### RN-123 — `make check-rls` es gate de CI
**Categoría**: Operación
**Fase origen**: F0-F9
**Servicio(s)**: CI
**Severidad**: Crítica

**Regla**: El workflow `.github/workflows/ci.yml` incluye `make check-rls`. Si el script detecta una tabla con columna `tenant_id` sin policy RLS, el job falla y el PR no se mergea.

**Justificación**: Prevenir que una tabla nueva se introduzca sin RLS por descuido.

**Verificación**: `.github/workflows/ci.yml`; `scripts/check-rls.py`.

### RN-124 — Runbook: 10 incidentes codificados I01-I10
**Categoría**: Operación
**Fase origen**: F9
**Servicio(s)**: docs/pilot
**Severidad**: Alta

**Regla**: `docs/pilot/runbook.md` documenta 10 códigos de incidente con severidad + síntomas + diagnóstico + acción:
- I01 Integridad CTR (Crítica) · I02 Tutor timeout (Alta) · I03 Clasificador detenido (Alta) · I04 Kappa <0.4 (Media) · I05 Progresión negativa (Media) · I06 Borrado solicitado (Normal) · I07 Export falla (Normal) · I08 LDAP no autentica (Normal) · I09 Budget agotado (Media) · I10 Backup falló (Alta).

Cada incidente durante el piloto se registra en `docs/pilot/incidents/INNN-YYYY-MM-DD.md`.

**Justificación**: Paper trail operacional exigible por revisores de tesis + comité de ética.

**Verificación**: `docs/pilot/runbook.md`; template en `docs/pilot/incidents/`.

### RN-125 — Notebook de análisis replica `progression_label` en Python
**Categoría**: Auditoría
**Fase origen**: F9
**Servicio(s)**: docs/pilot
**Severidad**: Alta

**Regla**: `docs/pilot/analysis-template.ipynb` replica el algoritmo de `StudentTrajectory.progression_label()` directamente en Python para garantizar que el notebook produce resultados coincidentes con el endpoint `/progression` del backend.

**Justificación**: Coherencia notebook ↔ backend es propiedad defendible ante el jurado.

**Verificación**: `docs/pilot/analysis-template.ipynb` celda replicante.

---

## Reglas transversales

Las reglas de esta sección ya están enumeradas en sus fases. Acá se agrupan temáticamente para facilitar búsqueda.

### Multi-tenancy y RLS

Referencias: RN-001 (RLS obligatorio), RN-010 (universidades sin RLS), RN-011 (casbin_rules global), RN-024 (doble filtro retrieval), RN-077 (JWT único source), RN-112 (set_tenant_rls), RN-114 (doble filtro real_datasources), RN-119 (FORCE RLS), RN-120 (default empty), RN-121 (WITH CHECK), RN-122 (SET LOCAL reset), RN-123 (check-rls gate).

### Criptografía y auditabilidad (CTR)

Referencias: RN-002 (GENESIS_HASH), RN-004 (canonicalización), RN-005 (self_hash exclusiones), RN-006 (chain_hash fórmula), RN-034 (append-only), RN-035 (seq=0 inicial), RN-036 (seq sin gaps), RN-037 (idempotencia), RN-038 (sharding), RN-039 (3 reintentos → DLQ), RN-040 (integrity checker 6h), RN-042 (codigo_ejecutado con user_id estudiante), RN-044 (chunks_used_hash propagado), RN-048 (hash contenido prompt), RN-101 (rolling CTR workers).

### Reproducibilidad (clasificador)

Referencias: RN-049 (classifier_config_hash), RN-050 (append-only classifications), RN-051 (5 coherencias separadas), RN-052 (CT pausa 5min), RN-053 (CCD ventana 2min), RN-054 (CII Jaccard), RN-055 (CII slope), RN-056 (3 ramas exclusivas), RN-057 (gatillo extremo 0.8), RN-058 (6 umbrales), RN-059 (reason explicativa), RN-107 (A/B determinista).

### Privacidad y ética

Referencias: RN-081 (anonymize no toca CTR), RN-082 (firma export), RN-083 (salt ≥ 16), RN-084 (include_prompts=False default), RN-085 (pseudónimo determinista), RN-086 (salt_hash), RN-090 (LDAP READ_ONLY), RN-117 (4 derechos consentimiento).

### Identidad y autenticación

Referencias: RN-075 (RS256 obligatorio), RN-076 (claims obligatorios + tenant_id), RN-077 (único validador), RN-078 (JWKS force-refresh), RN-079 (leeway 10s), RN-080 (X-Request-Id), RN-091 (tenant_id mapper LDAP), RN-093 (UPDATE_PASSWORD), RN-094 (secret resolver order).

### Rate limiting y SLOs

Referencias: RN-066 (tiers), RN-067 (principal inference), RN-068 (fail-open), RN-069 (429 headers), RN-070 (health exento), RN-072 (SLO tutor P95/P99), RN-073 (SLO 5xx < 1%), RN-074 (CTR DLQ alerta).

### Observabilidad

Referencias: RN-071 (W3C traceparent), RN-072-074 (SLOs), RN-080 (X-Request-Id), RN-106 (dashboard thresholds).

### Deploy

Referencias: RN-100 (canary tutor), RN-101 (rolling CTR), RN-102 (blue-green HTTP).

### Backups

Ver RN-126 y RN-127 abajo (nuevas, no cubiertas en otras fases).

### RN-126 — Backup: `pg_dump --format=custom --compress=9`
**Categoría**: Operación
**Fase origen**: F5
**Servicio(s)**: scripts/backup.sh
**Severidad**: Alta

**Regla**: `scripts/backup.sh` usa `pg_dump --format=custom --compress=9` por base, produce `manifest.txt` con SHA-256 de cada dump, y corre como CronJob diario a las 03:00 UTC. Retención 7 días de backups exitosos. PVC `platform-backups` de 50Gi mínimo. Alerta `PlatformBackupMissing` si pasan > 26 h sin backup exitoso.

**Justificación**: Backup verificable (checksum) con compresión óptima + retention razonable.

**Verificación**: `scripts/backup.sh`, `ops/k8s/backup-cronjob.yaml`.

### RN-127 — Restore requiere `CONFIRM=yes` + verify checksums
**Categoría**: Operación
**Fase origen**: F5
**Servicio(s)**: scripts/restore.sh
**Severidad**: Crítica

**Regla**: `scripts/restore.sh` exige `CONFIRM=yes` o input interactivo (escribir literalmente "RESTORE"). Verifica SHA-256 de cada dump contra el manifest ANTES de hacer DROP + CREATE + pg_restore. Fail-fast si cualquier checksum no coincide.

**Justificación**: Restore sin confirmación es pie-de-bala; restore sobre backup corrupto destruye DB.

**Verificación**: `scripts/restore.sh`.

---

### RN-128 — Cada episodio cerrado emite attestation externa Ed25519 (eventual)
**Categoría**: Auditoría
**Fase origen**: F5 (ADR-021)
**Servicio(s)**: ctr-service (producer), integrity-attestation-service (consumer)
**Severidad**: Alta

**Regla**: Después del commit transaccional del evento `episodio_cerrado` en Postgres, el `ctr-service` emite un XADD al stream `attestation.requests` con `{episode_id, tenant_id, final_chain_hash, total_events, ts_episode_closed}`. El `integrity-attestation-service` (puerto 8012, deploy en infra institucional separada del cluster del piloto) consume el stream, firma con clave Ed25519 institucional usando el buffer canónico documentado en ADR-021, y appendea a `attestations-YYYY-MM-DD.jsonl`. SLO de attestation: 24h (soft, eventualmente consistente). **La ausencia o atraso de la attestation NO bloquea el cierre del episodio** — la cadena criptográfica del CTR queda commiteada en Postgres aunque el stream Redis o el attestation-service estén caídos.

**Justificación**: Cumple requisito tesis Sección 7.3 ("registro externo auditable") sin acoplar disponibilidad del piloto a la infra institucional. La fail-soft semantics + reconciliation futura es la única operación robusta — bloquear episodios si Redis cae degradaría el dev loop y el piloto.

**Verificación**: `apps/ctr-service/src/ctr_service/services/attestation_producer.py`; `apps/integrity-attestation-service/src/integrity_attestation_service/workers/attestation_consumer.py`; `apps/ctr-service/tests/unit/test_attestation_producer.py`; `apps/integrity-attestation-service/tests/integration/test_e2e_attestation_flow.py`; `scripts/verify-attestations.py` (tool del auditor externo).

---

### RN-129 — Detección preprocesamiento de intentos adversos en prompts del estudiante (Fase A)
**Categoría**: Seguridad
**Fase origen**: F4 (ADR-019)
**Servicio(s)**: tutor-service
**Severidad**: Alta

**Regla**: Antes de enviar el prompt del estudiante al `ai-gateway`, el `tutor-service` invoca `apps/tutor-service/src/tutor_service/services/guardrails.py::detect()` (función pura sobre regex compilados). Por CADA match emite un evento CTR `intento_adverso_detectado` con payload `{pattern_id, category, severity, matched_text, guardrails_corpus_hash}`, donde `category ∈ {jailbreak_indirect, jailbreak_substitution, jailbreak_fiction, persuasion_urgency, prompt_injection}` y `severity ∈ [1, 5]`. **La detección NO bloquea** el flow — el prompt llega al LLM sin modificación. El `guardrails_corpus_hash` es SHA-256 determinista del corpus de patrones (canónico: `sort_keys=True, ensure_ascii=False, separators=(",", ":")`); bumpear `GUARDRAILS_CORPUS_VERSION` o cualquier patrón cambia el hash. **Severidad >= 3** dispara inyección de un system message reforzante en `messages` antes del prompt del estudiante (Sección 8.5.1 — "recuerdo del rol"). Falla soft: si `detect()` lanza excepción, el tutor logea y continúa sin emitir eventos adversos.

**Justificación**: Cumple promesa tesis Sección 8.5 (4 tipos de comportamiento adverso con salvaguardas) para Fase A. Sección 17.8 (efectividad de salvaguardas) requiere los datos generados por estos eventos. Sin esto, la promesa es aspiracional. **Fase B** (postprocesamiento de respuesta del tutor + cálculo de `socratic_compliance` y `violations`) **NO está en v1.x** — declarada como agenda futura: un score mal calculado es peor que ninguno (audit G3 + ADR-019). **`overuse`** (8.5.3) requiere ventana cross-prompt — diferido a iteración separada.

**Verificación**: `apps/tutor-service/src/tutor_service/services/guardrails.py` (`compute_guardrails_corpus_hash`, `detect`, `_PATTERNS`); `apps/tutor-service/src/tutor_service/services/tutor_core.py::interact` (hook entre `prompt_enviado` y `ai_gateway.stream`); `apps/tutor-service/tests/unit/test_guardrails.py` (golden hash + cada categoría detecta + falsos positivos básicos); `apps/tutor-service/tests/unit/test_tutor_core.py` (hook integration tests con FakeCTRClient); `packages/contracts/src/platform_contracts/ctr/events.py::IntentoAdversoDetectado`.

---

### RN-130 — CII evolution longitudinal por `TareaPractica.template_id`, slope ordinal con N>=3
**Categoría**: Cálculo
**Fase origen**: F7 (ADR-018)
**Servicio(s)**: analytics-service, packages/platform-ops
**Severidad**: Alta

**Regla**: La métrica `cii_evolution_longitudinal` se calcula como slope de la regresión lineal sobre `APPROPRIATION_ORDINAL[appropriation]` ∈ {0, 1, 2} de las clasificaciones de un estudiante sobre el mismo `TareaPractica.template_id` (ADR-016), ordenadas por `classified_at` ascendente. Mínimo `MIN_EPISODES_FOR_LONGITUDINAL = 3` episodios para calcular; con N<3 el resultado es `null` con flag `insufficient_data: true`. Episodios sobre TPs **sin** `template_id` (TPs huérfanas pre-ADR-016) NO entran al cálculo — limitación declarada del piloto inicial. **NO se renombran `cii_stability`/`cii_evolution` actuales** (intra-episodio): el longitudinal es campo nuevo en `Classification.features['cii_evolution_longitudinal']` sin requerir migration. El cálculo es **on-demand** en `GET /api/v1/analytics/student/{id}/cii-evolution-longitudinal?comision_id=X`; persistirlo en `features` es opcional cuando el endpoint corre. La métrica es **slope cardinal sobre datos ordinales** — operacionalización conservadora declarada como tal en ADR-018.

**Justificación**: Cumple promesa tesis Sección 15.4 (CII como observación longitudinal de "estabilidad de criterios y patrones aplicados a través de problemas análogos"). H2 de la tesis es testeable empíricamente solo con esta métrica. Versión mínima: solo `cii_evolution_longitudinal`. **NO incluye `cii_criteria_stability` ni `cii_transfer_effective`** (Sección 15.4 los menciona pero requieren NLP del contenido — agenda futura piloto-2 cuando exista G1 / embeddings).

**Verificación**: `packages/platform-ops/src/platform_ops/cii_longitudinal.py` (`compute_evolution_per_template`, `compute_mean_slope`, `compute_cii_evolution_longitudinal`); `packages/platform-ops/tests/test_cii_longitudinal.py` (19 tests con casos golden mejorando/empeorando/estable + insufficient_data + multi-template + idempotencia); `apps/analytics-service/src/analytics_service/routes/analytics.py::get_cii_evolution_longitudinal` (endpoint con triple cross-DB ctr+classifier+academic); `apps/analytics-service/tests/unit/test_cii_evolution_longitudinal_endpoint.py` (auth + modo dev + response shape); `packages/platform-ops/src/platform_ops/real_datasources.py::list_classifications_with_templates_for_student`.

---

### RN-131 — Alertas predictivas (>=1σ vs cohorte) + cuartiles con privacidad N>=5
**Categoría**: Cálculo · Privacidad
**Fase origen**: F7 (ADR-022, agenda G7 piloto-2)
**Servicio(s)**: analytics-service, packages/platform-ops, web-teacher
**Severidad**: Alta

**Regla**: El endpoint `GET /api/v1/analytics/student/{student_pseudonym}/alerts?comision_id=X` calcula 3 alertas por estudiante con **estadística clásica** (NO ML): (a) `regresion_vs_cohorte` con z-score `(student_slope - mean) / stdev` ≤ -2σ → severidad `high`, ≤ -1σ → severidad `medium`; (b) `bottom_quartile` cuando el cuartil del estudiante es Q1 (estudiante en peor 25% de la cohorte) → severidad `medium`; (c) `slope_negativo_significativo` cuando `student_slope < -0.3` con `n_episodes_total >= 4` (umbral conservador para evitar ruido por pocos episodios) → severidad `medium`. La cohorte usa `cii_evolution_longitudinal.mean_slope` por estudiante (RN-130). El endpoint `GET /api/v1/analytics/cohort/{comision_id}/cii-quartiles` devuelve `q1`, `median`, `q3`, `min`, `max`, `mean`, `stdev` calculados con `statistics.quantiles(method="exclusive")`. **Privacidad**: si `len(student_slopes) < MIN_STUDENTS_FOR_QUARTILES = 5` la respuesta es `insufficient_data: true` SIN cuartiles ni stats — evita inferencia de individuos en cohortes pequeñas. Cuando insuficiente, el endpoint de alertas degrada graciosamente a solo `slope_negativo_significativo` (que NO requiere cohorte). Las alertas son **pedagógicas no clínicas** — sugieren intervención del docente, no diagnostican.

**Justificación**: Cumple promesa audit `audi1.md` G7 ("alertas predictivas: >1σ del propio trayecto del estudiante") con operacionalización conservadora declarada como tal en ADR-022. Versión clásica (z-score sobre slopes longitudinales) es testeable bit-a-bit y defendible ante el comité doctoral; ML predictivo verdadero queda como agenda piloto-2. El threshold N≥5 para cuartiles es estándar de privacidad k-anonymity para cohortes educativas — con 4 estudiantes o menos, los cuartiles son trivialmente reconstruibles.

**Verificación**: `packages/platform-ops/src/platform_ops/cii_alerts.py` (`compute_cohort_slopes_stats`, `position_in_quartiles`, `compute_student_alerts`, `compute_cohort_quartiles_payload`, `compute_alerts_payload`, `MIN_STUDENTS_FOR_QUARTILES = 5`, `ALERTS_VERSION = "1.0.0"`); `packages/platform-ops/tests/test_cii_alerts.py` (16 tests: stats con N=5, posición Q1-Q4, detección -2σ/-1σ, `bottom_quartile` informativa con sólo Q1, `slope_negativo_significativo` con threshold N≥4, fallback `insufficient_data`, payload helpers); `apps/analytics-service/src/analytics_service/routes/analytics.py::{get_student_alerts, get_cohort_cii_quartiles, get_student_episodes}`; `apps/analytics-service/tests/unit/test_student_episodes_endpoint.py` (9 tests); `apps/web-teacher/src/views/StudentLongitudinalView.tsx` (panel ámbar con badges de severidad + panel emerald "sin alertas"); `apps/web-teacher/tests/StudentLongitudinalView.test.tsx` (4 tests E2E con `setupFetchMock` mockeando 2 fetches simultáneos).

**ADR/Doc**: ADR-022.

---

### RN-132 — Resolver BYOK jerárquico materia → tenant → env_fallback (ADR-039)
**Categoría**: Cálculo · Configuración
**Fase origen**: epic ai-native-completion-and-byok (2026-05-04)
**Servicio(s)**: ai-gateway, packages/platform-ops
**Severidad**: Alta

**Regla**: El resolver `apps/ai-gateway/.../services/byok.py::resolve_byok_key(tenant_id, provider, materia_id)` busca BYOK keys en orden estricto: (1) `scope=materia` con `scope_id=materia_id` (sólo si `materia_id is not None`); (2) `scope=tenant` con `scope_id=NULL`; (3) env fallback (`ANTHROPIC_API_KEY`/`OPENAI_API_KEY`/etc según provider). scope=facultad está omitido en piloto-1 (requiere lookup cross-DB `materia.facultad_id`, deferido a piloto-2 con cache Redis). Si `BYOK_ENABLED=False`, salta directo al env fallback. Si `BYOK_MASTER_KEY` no está seteada y `BYOK_ENABLED=True`, también degrada a env fallback (sin master key no podemos desencriptar). El plaintext devuelto en `ResolvedKey` NUNCA se loguea — sólo `key_id` + `scope_resolved` + `provider`. Encriptación `AES-256-GCM` (RFC 5116, ADR-038).

**Justificación**: Multi-tenancy real exige que cada universidad pueda traer sus propias keys (BYOK) con costo a su cargo, y que dentro del tenant el scope materia permita cobrar contra presupuestos por materia (no compartir entre cursos). El env fallback existe para que dev/CI no requieran setup de BYOK_MASTER_KEY ni encriptación — sólo hay que setear `ANTHROPIC_API_KEY` y andar. Las métricas `byok_key_resolution_total{resolved_scope}` permiten alertas operacionales (si una materia que esperaba scope=materia cayó a tenant_fallback, indica config rota).

**Verificación**: `apps/ai-gateway/src/ai_gateway/services/byok.py::resolve_byok_key`; métricas instrumentadas vía `_emit()` interno (cuenta `materia` | `tenant` | `env_fallback` | `none`); test E2E del resolver DEFERIDO (requiere DB real).

**ADR/Doc**: ADR-038 (encriptación), ADR-039 (resolver), ADR-040 (propagación `materia_id`).

---

### RN-133 — Reflexión `reflexion_completada` excluida del feature extraction del classifier
**Categoría**: Invariante · Reproducibilidad
**Fase origen**: epic ai-native-completion-and-byok (2026-05-04)
**Servicio(s)**: classifier-service
**Severidad**: Crítica

**Regla**: El evento `reflexion_completada` (emitido post-`EpisodioCerrado` por el modal del web-student, ADR-035) **NO** entra al feature extraction del classifier. La exclusión está implementada como conjunto `_EXCLUDED_FROM_FEATURES = {"reflexion_completada"}` en `apps/classifier-service/src/classifier_service/services/pipeline.py` y se filtra **ANTES** del feature extraction. Cualquier evento side-channel post-cierre que se agregue en el futuro (analytics surveys, telemetry, etc.) DEBE agregarse a este set, o contaminará el `classifier_config_hash` con eventos posteriores al cierre del episodio y romperá la reproducibilidad bit-a-bit.

**Justificación**: Sin esta exclusión, una reflexión >5min post-cierre cambia `ct_summary` (la reflexión crea una nueva ventana de trabajo con pause >5min) — verificado durante la implementación de la epic. El bug habría contaminado silenciosamente las re-clasificaciones históricas. La reflexión es valiosa pedagógicamente y vive en el CTR como append-only (queda en la cadena criptográfica para audit), pero NO es señal del trabajo del episodio.

**Verificación**: `apps/classifier-service/tests/unit/test_pipeline_reproducibility.py::test_reflexion_completada_no_afecta_clasificacion_ni_features` (compara dos episodios idénticos uno con/sin reflexión, mismo classifier_config_hash + mismas features); event_labeler.py marca el evento como N-level "meta" en `test_reflexion_completada_es_meta_en_event_labeler`. **NO romper estos tests** al refactorizar el classifier.

**ADR/Doc**: ADR-035.

---

### RN-134 — Tests `is_public=false` no entran al feature extraction (`tests_hidden=0` invariante)
**Categoría**: Invariante · Reproducibilidad · Privacidad
**Fase origen**: epic ai-native-completion-and-byok (2026-05-04)
**Servicio(s)**: classifier-service, tutor-service, academic-service
**Severidad**: Alta

**Regla**: El client-side (Pyodide en el browser) ejecuta SOLO test_cases con `is_public=true` — los tests `is_public=false` se filtran en `GET /api/v1/tareas-practicas/{id}/test-cases?include_hidden=...` por rol (estudiante 403 con `include_hidden=true`). El endpoint `POST /api/v1/episodes/{id}/run-tests` valida `tests_hidden == 0` (vía `RunTestsRequest.tests_hidden: int = Field(le=0)`) y devuelve 422 si llega cualquier valor distinto. El evento `tests_ejecutados` que se persiste en el CTR lleva los conteos agregados (no el código del estudiante). Con esto, las features del classifier sobre `tests_ejecutados` consumen sólo agregados de tests públicos — preserva reproducibilidad bit-a-bit del `classifier_config_hash` aún cuando la cátedra rota tests hidden entre versiones.

**Justificación**: Tests `is_public=false` son artefactos de evaluación del docente — usarlos para alimentar al classifier viola la separación instrumento-intervención (si el classifier "ve" hidden tests, su comportamiento depende de cuáles tests están escondidos, lo cual cambia mes a mes y rompe re-clasificación histórica). El filtrado por rol en el endpoint también previene leakage del código de evaluación al alumno.

**Verificación**: `apps/academic-service/src/academic_service/routes/tareas_practicas.py::get_test_cases` (filtro por rol); `apps/tutor-service/src/tutor_service/routes/episodes.py::run_tests` (`RunTestsRequest.tests_hidden: int = Field(le=0)`); `apps/classifier-service/src/classifier_service/services/event_labeler.py` versión `1.2.0` (regla N3/N4 sobre `tests_ejecutados`); tests anti-regresión existentes en `apps/classifier-service/tests/unit/`.

**ADR/Doc**: ADR-033, ADR-034.

---

## Catálogo de severidades

### Reglas Críticas (39)

RN-001, RN-002, RN-004, RN-005, RN-006, RN-019, RN-023, RN-024, RN-026, RN-034, RN-035, RN-036, RN-038, RN-039, RN-042, RN-044, RN-047, RN-048, RN-049, RN-050, RN-051, RN-056, RN-057, RN-060, RN-075, RN-076, RN-077, RN-081, RN-083, RN-084, RN-090, RN-091, RN-098, RN-101, RN-107, RN-112, RN-114, RN-117, RN-119, RN-120, RN-121, RN-123, RN-127, RN-133.

### Reglas Altas (61)

RN-003, RN-010, RN-011, RN-012, RN-013, RN-014, RN-016, RN-018, RN-020, RN-021, RN-025, RN-030, RN-031, RN-037, RN-040, RN-041, RN-043, RN-045, RN-046, RN-050 (ver crítica también), RN-052, RN-053, RN-054, RN-055, RN-058, RN-059, RN-061, RN-062, RN-064, RN-068, RN-071, RN-072, RN-073, RN-074, RN-078, RN-080 (parcial), RN-082, RN-085, RN-086, RN-087, RN-092, RN-093, RN-094, RN-095, RN-096, RN-097, RN-100, RN-102, RN-103, RN-104, RN-105, RN-108, RN-109, RN-111, RN-113, RN-115, RN-116, RN-118, RN-122, RN-124, RN-125, RN-126, RN-128, RN-129, RN-130, RN-131, RN-132, RN-134.

### Reglas Medias (34)

RN-007, RN-008, RN-015, RN-017, RN-022, RN-027, RN-028, RN-029, RN-032, RN-033, RN-063, RN-065, RN-066, RN-067, RN-079, RN-088, RN-089, RN-099, RN-106, RN-110, RN-115 (ver Alta también).

### Reglas Bajas (10)

RN-009, RN-022, RN-069.

*Nota: algunas reglas aparecen en múltiples severidades cuando cubren aspectos distintos. El recuento nominal total es 138; la suma por severidad excede 138 por reglas con dualidad.*

---

## Trazabilidad RN → Fase → Verificación

| RN | Fase | Categoría | Verificación / archivo |
|---|---|---|---|
| RN-001 | F0 | Invariante | `scripts/check-rls.py`, `make check-rls` |
| RN-002 | F0 | Cálculo | `apps/ctr-service/src/ctr_service/models/base.py` |
| RN-003 | F0 | Persistencia | `.env.example`, ADR-003 |
| RN-004 | F0 | Cálculo | `apps/ctr-service/src/ctr_service/services/hashing.py::canonicalize` |
| RN-005 | F0 | Cálculo | `hashing.py::compute_self_hash` (set de exclusiones) |
| RN-006 | F0 | Cálculo | `hashing.py::compute_chain_hash` |
| RN-007 | F0 | Operación | `scripts/check-health.sh`, cada `tests/test_health.py` |
| RN-008 | F0 | Operación | `Makefile` targets test |
| RN-009 | F0 | Persistencia | `models/base.py::NAMING_CONVENTION` |
| RN-010 | F1 | Persistencia | migración inicial academic |
| RN-011 | F1 | Persistencia | schema `casbin_rules` |
| RN-012 | F1 | Persistencia | `repositories/base.py::soft_delete` |
| RN-013 | F1 | Validación | `tests/integration/test_comision_periodo_cerrado.py` |
| RN-014 | F1 | Validación | `MateriaService` unit tests |
| RN-015 | F1 | Operación | `BaseRepository.list()` |
| RN-016 | F1 | Auditoría | revisión de services |
| RN-017 | F1 | Validación | `tests/unit/test_schemas.py` |
| RN-018 | F1 | Autorización | `seeds/casbin_policies.py`, `test_casbin_matrix.py` |
| RN-019 | F1 | Autorización | code review |
| RN-020 | F1 | Autorización | policy Casbin |
| RN-021 | F1 | Validación | enrollment-service tests |
| RN-022 | F1 | Operación | realm template Keycloak |
| RN-023 | F2 | Validación | `content-service/schemas/__init__.py` |
| RN-024 | F2 | Invariante | `services/retrieval.py` query SQL |
| RN-025 | F2 | Cálculo | `retrieval.py::VECTOR_TOP_N = 20` |
| RN-026 | F2 | Cálculo | `retrieval.py::_hash_chunk_ids` |
| RN-027 | F2 | Cálculo | `services/chunker.py::MAX_CODE_TOKENS = 1500` |
| RN-028 | F2 | Cálculo | `chunker.py::DEFAULT_TARGET_TOKENS`, `DEFAULT_OVERLAP_TOKENS` |
| RN-029 | F2 | Cálculo | `chunker.py::_as_single_chunk` |
| RN-030 | F2 | Persistencia | `chunker.py::_hash_text` |
| RN-031 | F2 | Cálculo | `embedding/sentence_transformer_embedder.py` |
| RN-032 | F2 | Operación | migración inicial content |
| RN-033 | F2 | Validación | `routes/materiales.py` |
| RN-034 | F3 | Invariante | code review CTR; ADR-010 |
| RN-035 | F3 | Invariante | `workers/partition_worker.py` lógica de `prev_chain` |
| RN-036 | F3 | Invariante | `partition_worker.py::_persist_event` (validación seq) |
| RN-037 | F3 | Persistencia | `partition_worker.py` `on_conflict_do_nothing` |
| RN-038 | F3 | Cálculo | `services/producer.py::shard_of`, `NUM_PARTITIONS = 8` |
| RN-039 | F3 | Invariante | `partition_worker.py::MAX_ATTEMPTS = 3`, `_move_to_dlq` |
| RN-040 | F4 | Operación | `ops/k8s/ctr-integrity-checker.yaml` |
| RN-041 | F3 | Invariante | `tutor_core.py::TUTOR_SERVICE_USER_ID` |
| RN-042 | F6 | Invariante | `tutor_core.py::emit_codigo_ejecutado`; test caller_id |
| RN-043 | F3 | Invariante | `tutor_core.py::interact`; test seqs consecutivos |
| RN-044 | F3 | Invariante | `tutor_core.py::interact`; test chunks_used_hash |
| RN-045 | F3 | Persistencia | `services/session.py::SESSION_TTL = 6 * 3600` |
| RN-046 | F3 | Validación | `routes/episodes.py::OpenEpisodeRequest` |
| RN-047 | F3 | Seguridad | `prompt_loader.py::load`; test fail_loud |
| RN-048 | F3 | Cálculo | `prompt_loader.py::compute_content_hash` |
| RN-049 | F3 | Cálculo | `classifier/services/pipeline.py::compute_classifier_config_hash` |
| RN-050 | F3 | Persistencia | `pipeline.py::persist_classification` |
| RN-051 | F3 | Invariante | schema `classifications`; `CLAUDE.md` |
| RN-052 | F3 | Cálculo | `classifier/services/ct.py::PAUSE_THRESHOLD = 5min`, `MIN_EVENTS_FOR_SCORE = 3` |
| RN-053 | F3 | Cálculo | `ccd.py::CORRELATION_WINDOW = 2min` |
| RN-054 | F3 | Cálculo | `cii.py::_jaccard_tokens` |
| RN-055 | F3 | Cálculo | `cii.py` bloque slope |
| RN-056 | F3 | Cálculo | `tree.py::classify` |
| RN-057 | F3 | Cálculo | `tree.py::EXTREME_ORPHAN_THRESHOLD = 0.8` |
| RN-058 | F3 | Validación | `tree.py::DEFAULT_REFERENCE_PROFILE.thresholds` |
| RN-059 | F3 | Auditoría | `tree.py::classify` — f-strings `reason=` |
| RN-060 | F3 | Seguridad | ADR-004; ausencia de SDK LLM en no-ai-gateway |
| RN-061 | F3 | Operación | `ai-gateway/services/budget_and_cache.py::BudgetTracker` |
| RN-062 | F3 | Cálculo | `budget_and_cache.py::ResponseCache._is_cacheable` |
| RN-063 | F4 | Operación | `ops/prometheus/slo-rules.yaml` |
| RN-064 | F3 | Cálculo | `ai-gateway/providers/base.py::AnthropicProvider.PRICING` |
| RN-065 | F3 | Operación | `tutor_core.py::default_model` |
| RN-066 | F4 | Seguridad | `api-gateway/services/rate_limit.py::PATH_LIMITS` |
| RN-067 | F4 | Seguridad | `rate_limit.py::principal_from_request` |
| RN-068 | F4 | Seguridad | middleware rate_limit try/except |
| RN-069 | F4 | Seguridad | `rate_limit.py::check` + middleware headers |
| RN-070 | F4 | Operación | middleware exempt list |
| RN-071 | F4 | Auditoría | `packages/observability/src/platform_observability/setup.py` |
| RN-072 | F4 | Operación | `ops/prometheus/slo-rules.yaml` |
| RN-073 | F4 | Operación | `ops/prometheus/slo-rules.yaml` |
| RN-074 | F4 | Operación | `ops/prometheus/slo-rules.yaml` |
| RN-075 | F5 | Seguridad | `api-gateway/services/jwt_validator.py::validate` |
| RN-076 | F5 | Seguridad | `jwt_validator.py::_build_principal` |
| RN-077 | F5 | Seguridad | `middleware/jwt_auth.py` |
| RN-078 | F5 | Seguridad | `jwt_validator.py::JWKSCache` |
| RN-079 | F5 | Seguridad | `jwt_validator.py::JWTValidatorConfig.leeway_seconds = 10` |
| RN-080 | F5 | Auditoría | `middleware/jwt_auth.py` |
| RN-081 | F5 | Privacidad | `platform_ops/privacy.py::anonymize_student` |
| RN-082 | F5 | Privacidad | `privacy.py::ExportedData.compute_signature` |
| RN-083 | F5 | Privacidad | `platform_ops/academic_export.py::AcademicExporter.__init__` |
| RN-084 | F5 | Privacidad | `academic_export.py::export_cohort` default |
| RN-085 | F5 | Cálculo | `academic_export.py::_pseudonymize` |
| RN-086 | F5 | Auditoría | `academic_export.py::CohortDataset.salt_hash` |
| RN-087 | F5 | Validación | `feature_flags.py::get_value` |
| RN-088 | F5 | Operación | `feature_flags.py::_maybe_reload` |
| RN-089 | F5 | Validación | `feature_flags.py::is_enabled` |
| RN-090 | F6 | Privacidad | `ldap_federation.py::_ldap_config_to_kc_config` |
| RN-091 | F6 | Seguridad | `ldap_federation.py::_ensure_tenant_id_mapper` |
| RN-092 | F6 | Operación | `tests/test_tenant_onboarding.py::idempotencia` |
| RN-093 | F6 | Seguridad | `tenant_onboarding.py` |
| RN-094 | F5 | Seguridad | `tenant_secrets.py`, tests |
| RN-095 | F6 | Cálculo | `kappa_analysis.py::KappaResult.interpretation` |
| RN-096 | F6 | Validación | `kappa_analysis.py::CATEGORIES` |
| RN-097 | F6 | Seguridad | `audit.py::BruteForceRule` |
| RN-098 | F6 | Seguridad | `audit.py::CrossTenantAccessRule` |
| RN-099 | F6 | Seguridad | `audit.py::RepeatedAuthFailuresRule` |
| RN-100 | F6 | Operación | `ops/k8s/canary-tutor-service.yaml` |
| RN-101 | F6 | Operación | `infrastructure/helm/platform/templates/ctr-workers.yaml`; ADR-015 |
| RN-102 | F6 | Operación | helm templates blue-green; ADR-015 |
| RN-103 | F7 | Cálculo | `longitudinal.py::APPROPRIATION_ORDINAL` |
| RN-104 | F7 | Cálculo | `longitudinal.py::progression_label` |
| RN-105 | F7 | Cálculo | `longitudinal.py::net_progression_ratio` |
| RN-106 | F8 | Operación | `ops/grafana/dashboards/unsl-pilot.json` |
| RN-107 | F7 | Invariante | `tests/test_ab_integration.py` |
| RN-108 | F7 | Persistencia | `export_worker.py::ExportWorker.run_forever` |
| RN-109 | F7 | Operación | `analytics-service/main.py` lifespan |
| RN-110 | F7 | Operación | `export_worker.py::ExportJobStore.cleanup_old` |
| RN-111 | F7 | Validación | schema endpoint `POST /ab-test-profiles` |
| RN-112 | F8 | Invariante | `real_datasources.py::set_tenant_rls` |
| RN-113 | F8 | Operación | `analytics-service/services/factory.py` |
| RN-114 | F8 | Seguridad | `real_datasources.py` queries |
| RN-115 | F8 | Operación | `real_datasources.py::RealLongitudinalDataSource` |
| RN-116 | F8 | Auditoría | `Makefile::generate-protocol` |
| RN-117 | F8 | Privacidad | `docs/pilot/protocolo-piloto-unsl.docx` Anexo A |
| RN-118 | F8 | Auditoría | protocolo sección 4 |
| RN-119 | F9 | Seguridad | migraciones F9 con FORCE |
| RN-120 | F9 | Seguridad | `test_rls_postgres.py::sin_set_local` |
| RN-121 | F9 | Seguridad | `test_rls_postgres.py::insert_tenant_distinto_falla` |
| RN-122 | F9 | Seguridad | `test_rls_postgres.py::set_local_se_resetea` |
| RN-123 | F0-F9 | Operación | `.github/workflows/ci.yml` |
| RN-124 | F9 | Operación | `docs/pilot/runbook.md` |
| RN-125 | F9 | Auditoría | `docs/pilot/analysis-template.ipynb` |
| RN-126 | F5 | Operación | `scripts/backup.sh`, `ops/k8s/backup-cronjob.yaml` |
| RN-127 | F5 | Operación | `scripts/restore.sh` |
| RN-128 | F5 | Auditoría | `apps/ctr-service/src/ctr_service/services/attestation_producer.py`, `apps/integrity-attestation-service/`, `scripts/verify-attestations.py`, ADR-021 |
| RN-129 | F4 | Seguridad | `apps/tutor-service/src/tutor_service/services/guardrails.py`, `tutor_core.py::interact`, ADR-019 |
| RN-130 | F7 | Cálculo | `packages/platform-ops/src/platform_ops/cii_longitudinal.py`, `analytics-service/routes/analytics.py::get_cii_evolution_longitudinal`, ADR-018 |
| RN-131 | F7 | Cálculo · Privacidad | `packages/platform-ops/src/platform_ops/cii_alerts.py`, `analytics-service/routes/analytics.py::{get_student_alerts,get_cohort_cii_quartiles,get_student_episodes}`, `apps/web-teacher/src/views/StudentLongitudinalView.tsx`, ADR-022 |

---

## Reglas con verificación pendiente

Las siguientes reglas se derivaron del diseño documentado pero no se pudieron cotejar byte-a-byte con el código fuente disponible en este pass de lectura. Quedan marcadas para verificación directa:

- **⚠ Verificar RN-074** — Threshold exacto del stream DLQ size para `CTRDLQGrowing` no fue hallado en `slo-rules.yaml` durante la lectura; asumido "N" mensajes. Revisar `ops/prometheus/slo-rules.yaml` para el valor concreto.
- **⚠ Verificar RN-040** — El schedule "cada 6 horas" del CronJob está documentado en F4-STATE.md pero el manifest `ops/k8s/ctr-integrity-checker.yaml` no se abrió en este pass. Confirmar `schedule: "0 */6 * * *"` o equivalente.
- **⚠ Verificar RN-100** — Los tiempos 2 min y 5 min del canary están en F6-STATE.md. Confirmar los valores exactos en `ops/k8s/canary-tutor-service.yaml`.
- **⚠ Verificar RN-111** — El mínimo de ratings del gold standard para correr A/B no está explícito en el texto leído; inferido "≥N" sin N concreto. Revisar el schema del endpoint y/o tests de `test_ab_integration.py`.
- **⚠ Verificar RN-126** — Retención de "7 días de backups exitosos" y PVC "50Gi" derivados de F5-STATE.md; validar con `ops/k8s/backup-cronjob.yaml`.
- **⚠ Verificar RN-065** — El string literal `"claude-sonnet-4-6"` como default se leyó en `tutor_core.py`, pero el mapeo a `settings.default_model` (que puede override) conviene confirmarlo en `apps/tutor-service/src/tutor_service/config.py`.
- **RN-018** — Histórico: count actualizado en sesión 2026-04-21 a 92 policies; ADR-016 (`tarea_practica_template:CRUD`) lo llevó a 107 policies (count real del seed, verificado). Ver RN-018 actualizada (el count específico se removió de la spec; el código del seed es source of truth).

Estas pendientes no cambian la sustancia de las reglas — sólo un número o path puntual a precisar antes de tratar el documento como referencia autoritativa de producción.
