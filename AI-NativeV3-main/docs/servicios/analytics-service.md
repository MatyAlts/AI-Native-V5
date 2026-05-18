# analytics-service

## 1. Qué hace (una frase)

Expone la capa de análisis empírico del piloto: Cohen's κ inter-rater, A/B testing de profiles del clasificador contra gold standard humano, progresión longitudinal por cohorte, y export académico anonimizado como jobs asíncronos — leyendo cross-base (CTR + classifier + academic) con RLS por tenant.

## 2. Rol en la arquitectura

Pertenece al **plano académico-operacional**. Materializa el componente "Servicio de analítica" descrito en el Capítulo 6 de la tesis (arquitectura C4 del sistema AI-Native), cuyas responsabilidades nominales son: producir los indicadores empíricos que sostienen los resultados publicables de la tesis (κ ≥ 0.6 como meta, progresión longitudinal de cohortes, calibración del árbol N4) y ofrecer los datasets anonymizados que el investigador entrega al comité de ética UNSL.

Es el único servicio del repo que lee **cross-base** (`ctr_store` + `classifier_db`) — y lo hace con sesiones separadas, cada una con su propio `SET LOCAL app.current_tenant` (RN-108).

## 3. Responsabilidades

- Exponer `POST /api/v1/analytics/kappa` que calcula Cohen's κ sobre un batch de ratings (`rater_a`, `rater_b` de 1–10.000 episodios). Devuelve `kappa`, `observed_agreement`, `expected_agreement`, interpretación Landis & Koch, `per_class_agreement` y matriz de confusión (RN-095, RN-096).
- Exponer `POST /api/v1/analytics/ab-test-profiles` que recibe un gold standard de episodios con `human_label` + 2+ profiles candidatos, clasifica cada episodio contra cada profile **in-process** (importando `classifier_service.services.pipeline`), calcula κ por profile y devuelve el `winner_by_kappa` (HU-118).
- Exponer `GET /api/v1/analytics/cohort/{comision_id}/progression` que construye trayectorias por estudiante (primer/último clasificación, `max_appropriation_reached`, `progression_label ∈ {mejorando, estable, empeorando, insuficiente}`), agrega por cohorte y devuelve `net_progression_ratio`.
- Exponer `POST /api/v1/analytics/cohort/export` que encola un job asíncrono de export académico anonimizado; `GET /status/{job_id}` + `GET /download/{job_id}` cierran el flujo.
- Exponer las vistas de drill-down del MVP G7 ([ADR-022](../adr/022-tanstack-router-migration.md), RN-131) consumidas por `web-teacher`: `GET /episode/{id}/n-level-distribution` (etiquetador N1-N4 derivado, [ADR-020](../adr/020-event-labeler-n-level.md)), `GET /student/{id}/cii-evolution-longitudinal` (slope longitudinal por `template_id`, [ADR-018](../adr/018-cii-evolution-longitudinal.md)), `GET /student/{id}/episodes` (lista de episodios + clasificaciones del estudiante), `GET /cohort/{id}/cii-quartiles` (estadística de cohorte con privacy gate N≥5), `GET /student/{id}/alerts` (3 alertas predictivas estadística clásica), `GET /cohort/{id}/adversarial-events` (eventos `intento_adverso_detectado` agregados, [ADR-019](../adr/019-guardrails-fase-a.md)).
- **Nuevo (epic `unidades-trazabilidad`)**: `compute_evolution_per_unidad()` análogo a `cii_evolution_longitudinal` pero agrupando por `unidad_id` (cuando `template_id=NULL`). Función pura en `packages/platform-ops/src/platform_ops/cii_longitudinal.py`.
- **Nuevo (ADR-037)**: `GET /api/v1/analytics/governance/events` cross-cohort para gobernanza institucional desde web-admin (filtros cascade facultad → materia → período + CSV export con headers ASCII cp1252-safe).
- Correr un `ExportWorker` en el `lifespan` de FastAPI (RN-109) que consume el `ExportJobStore` global y procesa los jobs en background.
- Aplicar las reglas de anonimización: `salt` mínimo 16 chars obligatorio (validado por Pydantic), `include_prompts=False` por default, `cohort_alias` para identificar la cohorte en el dataset publicable.
- Seleccionar la fuente de datos: `RealCohortDataSource` + `RealLongitudinalDataSource` si `CTR_STORE_URL` y `CLASSIFIER_DB_URL` están configuradas, o `_StubDataSource` (data vacía) en su ausencia — permite arrancar en dev sin DB real sin que el servicio crashee.
- Emitir logs estructurados (`kappa_computed`, `ab_test_profiles_completed`) con `tenant_id`, `user_id`, métricas resultantes y `classifier_config_hash` como trail de auditoría (HU-088 — structlog a Loki, no tabla persistente).

## 4. Qué NO hace (anti-responsabilidades)

- **NO tiene DB propia**: lee read-only de `ctr_store` + `classifier_db` + `academic_main` (vía `platform_ops.real_datasources`). No hay migraciones Alembic.
- **NO persiste el audit log de κ/AB**: emite el evento a structlog → Loki → Grafana. Si el compliance team del piloto requiere tabla queryable, hay que agregarla (documentado en CLAUDE.md "HU-088 audit log es structlog").
- **NO hace joins cross-base en SQL**: usa sesiones separadas (`ctr_engine` + `cls_engine`, cada una con su `async_sessionmaker`) y combina los resultados en Python (`platform_ops.build_trajectories`). ADR-003 prohíbe joins cross-base.
- **NO reclasifica episodios persistidos**: el A/B testing es **in-process** — los episodios del gold standard se pasan en el request con sus eventos embebidos, se clasifican contra cada profile sin tocar `classifier_db`. Ni el gold ni los predicciones quedan persistidos. La reclasificación real (persistida) se invoca via `POST /classify_episode/{id}` de [classifier-service](./classifier-service.md).
- **NO valida JWT**: confía en los headers `X-Tenant-Id` + `X-User-Id` inyectados por [api-gateway](./api-gateway.md). `get_tenant_id`/`get_user_id` dependencies los extraen y rechazan con 401 si faltan (RN aplicada a todos los endpoints del servicio).
- **NO ofrece UI**: el A/B de profiles es **API-only por diseño en F7** (CLAUDE.md). El investigador arma el JSON con `gold_standard` + `profiles` candidatos y pega con curl. UI con drag-and-drop deferida a F8+.

## 5. Endpoints HTTP

| Método | Path | Qué hace | Headers |
|---|---|---|---|
| `POST` | `/api/v1/analytics/kappa` | Cohen's κ sobre batch de 1–10k ratings. | `X-Tenant-Id`, `X-User-Id`. |
| `POST` | `/api/v1/analytics/ab-test-profiles` | Compara ≥2 profiles contra gold standard humano. | Mismos headers. 503 si no puede importar `classifier_service`. |
| `GET` | `/api/v1/analytics/cohort/{comision_id}/progression` | Trayectorias por estudiante + agregado de cohorte. | `X-Tenant-Id`. |
| `POST` | `/api/v1/analytics/cohort/export` | Encola job async de export anonimizado. 202 con `job_id`. | `X-Tenant-Id`, `X-User-Id`. |
| `GET` | `/api/v1/analytics/cohort/export/{job_id}/status` | Estado del job (`pending\|running\|succeeded\|failed`). | — |
| `GET` | `/api/v1/analytics/cohort/export/{job_id}/download` | Payload inline si succeeded. 425 si aún running, 500 si failed. | — |
| `GET` | `/api/v1/analytics/episode/{episode_id}/n-level-distribution` | Distribución de tiempo por nivel N1–N4 derivada en lectura ([ADR-020](../adr/020-event-labeler-n-level.md)). Consumido por `EpisodeNLevelView` del web-teacher. | `X-Tenant-Id`. |
| `GET` | `/api/v1/analytics/student/{student_pseudonym}/cii-evolution-longitudinal` | Slope ordinal por `template_id` ([ADR-018](../adr/018-cii-evolution-longitudinal.md), RN-130). Mínimo 3 episodios por template; `insufficient_data: true` si N<3. | `X-Tenant-Id`. |
| `GET` | `/api/v1/analytics/student/{student_pseudonym}/episodes` | Lista de episodios del estudiante + última clasificación de cada uno (drill-down navegacional desde el cohort progression). | `X-Tenant-Id`. |
| `GET` | `/api/v1/analytics/cohort/{comision_id}/cii-quartiles` | Estadística de cohorte (cuartiles + media) sobre `cii_evolution_longitudinal` per-template. **Privacy gate**: con N<5 → `insufficient_data: true` SIN cuartiles ([ADR-022](../adr/022-tanstack-router-migration.md), RN-131). | `X-Tenant-Id`. |
| `GET` | `/api/v1/analytics/student/{student_pseudonym}/alerts` | 3 alertas predictivas (`regresion_vs_cohorte`, `bottom_quartile`, `slope_negativo_significativo`) computadas con z-score vs cohorte (NO ML). Degrada graciosamente si cohorte<5. | `X-Tenant-Id`. |
| `GET` | `/api/v1/analytics/cohort/{comision_id}/adversarial-events` | Eventos `intento_adverso_detectado` agregados por estudiante + categoría ([ADR-019](../adr/019-guardrails-fase-a.md), Sección 17.8). Consumido por `CohortAdversarialView`. | `X-Tenant-Id`. |
| `GET` | `/api/v1/analytics/governance/events` | Eventos cross-cohort de gobernanza institucional ([ADR-037](../adr/037-governance-ui.md)). Filtros cascade facultad/materia/período + CSV export. Consumido por `GovernanceEventsPage` del web-admin. | `X-Tenant-Id`. |
| `GET` | `/health`, `/health/ready` | Health real con `check_postgres` (cross-base) + `check_classifier_db` (epic `real-health-checks`, 2026-05-04). | — |

## 6. Dependencias

**Depende de (infraestructura):**
- PostgreSQL — lee cross-base. `CTR_STORE_URL` (ctr_store), `CLASSIFIER_DB_URL` (classifier_db). Sesiones separadas con `set_tenant_rls(session, tenant_id)`.

**Depende de (otros servicios):**
- [ctr-service](./ctr-service.md) y [classifier-service](./classifier-service.md) — no via HTTP, sino **compartiendo las bases lógicas** read-only. La dependencia es de datos, no de API.
- `classifier_service.services.pipeline` — importado **in-process** en el A/B endpoint (no HTTP). El `sys.path.insert` en `routes/analytics.py:423` agrega `apps/classifier-service/src` al path. Acoplamiento intra-monorepo.
- `packages/platform-ops` — `compute_cohen_kappa`, `compare_profiles`, `build_trajectories`, `summarize_cohort`, `ExportJobStore`, `ExportWorker`, `RealCohortDataSource`, `RealLongitudinalDataSource`, `set_tenant_rls`. Casi toda la lógica analítica vive en ese package.

**Dependen de él:**
- [web-teacher](./web-teacher.md) — consumidor principal. Vista "Progresión" (progression), "Inter-rater" (kappa), "Exportar" (export).
- CLI / scripts del piloto — `make kappa`, `make progression`, `make export-academic`, `make ab-test-profiles` pegan via curl a este servicio.

## 7. Modelo de datos

**No tiene DB propia**. Lee read-only de:
- `ctr_store.episodes` + `ctr_store.events` (propiedad de [ctr-service](./ctr-service.md)).
- `classifier_db.classifications` (propiedad de [classifier-service](./classifier-service.md)).
- `academic_main.comisiones` + `academic_main.inscripciones` (propiedad de [academic-service](./academic-service.md)).

Estado en memoria del proceso:
- `ExportJobStore` — singleton via `@lru_cache(maxsize=1)`. Jobs en memoria del process. Si el pod reinicia, los jobs en curso se pierden.
- `ExportWorker` — task de asyncio corriendo en el `lifespan`. Start en startup, stop en shutdown.

## 8. Archivos clave para entender el servicio

- `apps/analytics-service/src/analytics_service/routes/analytics.py` — los 12 endpoints HTTP (los 6 originales F7 + los 6 nuevos del MVP G7 / ADR-022). La densidad es deliberada: cada endpoint hace su propio setup del data source según feature flag.
- `apps/analytics-service/src/analytics_service/services/export.py` — singleton del `ExportJobStore` + `get_worker_salt()` + `_real_data_source_enabled()` + `start_worker()`/`stop_worker()` integrados al lifespan.
- `apps/analytics-service/src/analytics_service/main.py` — lifespan que arranca el export worker (RN-109).
- `apps/analytics-service/src/analytics_service/config.py` — declaración de `ctr_store_url` + `classifier_db_url` en el model `Settings` (**crítico**: sin esto, aunque el `.env` las tenga, `pydantic_settings` las ignora y el servicio cae a `_StubDataSource` — ver Gotchas).
- `packages/platform-ops/src/platform_ops/kappa.py` — `compute_cohen_kappa()` + `KappaRating` + validación de categorías (RN-096).
- `packages/platform-ops/src/platform_ops/longitudinal.py` — `build_trajectories()`, `summarize_cohort()`, `StudentTrajectory` con `max_appropriation_reached()`, `progression_label()`, `tercile_means()`.
- `packages/platform-ops/src/platform_ops/ab_testing.py` — `compare_profiles()`, `EpisodeForComparison`.
- `packages/platform-ops/src/platform_ops/real_datasources.py` — `RealCohortDataSource`, `RealLongitudinalDataSource` con sesiones separadas + RLS.
- `packages/platform-ops/src/platform_ops/export_worker.py` — `ExportWorker`, `ExportJob`, `JobStatus`.
- `apps/analytics-service/tests/unit/test_analytics_endpoints.py` + `test_f7_endpoints.py` + `test_export_endpoints.py` — cubren los endpoints con data source stub. Las suites de los nuevos endpoints del MVP G7 (alertas, cuartiles, longitudinal, drill-downs) están bajo el mismo árbol; ver `apps/analytics-service/tests/`.

## 9. Configuración y gotchas

**Env vars críticas** (`apps/analytics-service/src/analytics_service/config.py`):

- `CTR_STORE_URL` — **debe estar declarada en el Settings** (no sólo en `.env`). Default `""`.
- `CLASSIFIER_DB_URL` — idem. Default `""`.
- `KEYCLOAK_URL`, `KEYCLOAK_REALM` — convencionales.

**Puerto de desarrollo**: `8005`.

**Gotchas específicos**:

- **Trap del `.env` + `pydantic_settings`**: este servicio sufrió exactamente el caso documentado en CLAUDE.md. Leía `CTR_STORE_URL`/`CLASSIFIER_DB_URL` por `os.environ.get()` sin declararlas en el modelo `Settings`. Resultado: caían a stub silenciosamente y `/cohort/{id}/progression` devolvía `n_students=0`. Fix: declarar las vars en el modelo. Si agregás una env var nueva, asegurate que esté en `config.py:Settings` — no alcanza con `os.environ`. Caso resuelto en sesión 2026-04-23.
- **Export worker sin persistencia**: `ExportJobStore` vive en memoria del process. El rolling update de K8s descarta jobs en vuelo. En F8+ está previsto Redis o tabla; hoy para el piloto con pocos jobs manuales es tolerable.
- **`_real_data_source_enabled()` es todo-o-nada**: si sólo está `CTR_STORE_URL` pero no `CLASSIFIER_DB_URL`, el servicio cae a stub. No hay modo parcial.
- **Connection pool chico** (`pool_size=2` en `routes/analytics.py:312`): la idea es crear los engines por request y disponerlos en el `finally`. Costo: latencia extra (handshake SSL). Si el volumen del piloto crece, migrar a engines globales es una optimización.
- **A/B endpoint acopla a classifier-service por import**: `sys.path.insert` + `from classifier_service.services.pipeline import ...`. Si classifier-service cambia nombres de funciones, analytics-service rompe en runtime. El 503 que devuelve en el `ImportError` es el fallback.
- **κ mínimo de 2 episodios**: `ab_test_profiles` valida `len(req.episodes) < 2 → 400`. Con <2 episodios Cohen's κ no está definido.
- **`include_prompts=False` por default**: el export académico no incluye los prompts del estudiante por default. Habilitarlo requiere flag explícito — protege contra leaks accidentales de contenido escrito por estudiantes en papers/datasets públicos (RN de privacidad).
- **`salt_hash` en lugar de `salt`**: el `ExportJob` guarda sólo `sha256(salt)[:16]` para trazabilidad. El salt real viaja una sola vez y no se persiste. Si el investigador pierde el salt, no puede re-derivar los aliases.
- **Endpoints no son idempotentes**: cada `POST /kappa` recomputa desde cero. Cada `POST /ab-test-profiles` también. No hay cache — κ es barato, el A/B con 50+ episodios puede tardar varios segundos.

## 10. Relación con la tesis doctoral

El analytics-service produce los **indicadores empíricos que sostienen los resultados publicables** de la tesis. Tres afirmaciones que materializa:

1. **Cohen's κ como gate de calidad del clasificador** (Capítulo 8 de la tesis, RN-095/RN-096): la meta de la tesis es κ ≥ 0.6 contra etiquetado intercoder de dos docentes sobre 50 episodios. El endpoint `/kappa` y el workflow en `docs/pilot/kappa-workflow.md` son la implementación directa. Si κ < 0.6, la calibración del árbol es insuficiente y el A/B de profiles (`/ab-test-profiles`) es el siguiente paso para refinar umbrales.

2. **Progresión longitudinal como evidencia pedagógica** (Capítulo 9): el indicador `net_progression_ratio` por cohorte — fracción de estudiantes que mejoran menos los que empeoran sobre el total con datos suficientes — es una métrica agregada directamente referenciable en discusión de resultados. El cálculo por terciles (primer tercio vs último tercio de episodios del estudiante) permite detectar mejora temporal sin confundirla con ruido de episodios aislados.

3. **Export anonimizado como condición del convenio UNSL**: el protocolo del comité de ética UNSL exige que el dataset publicable no permita re-identificación de estudiantes. `salt ≥ 16 chars`, `student_pseudonym` ya opaco en origen, `include_prompts=False` por default son las tres defensas. [`docs/pilot/protocolo-piloto-unsl.docx`](../pilot/protocolo-piloto-unsl.docx) documenta el procedimiento formal.

El A/B testing de profiles (HU-118) es la operacionalización de la **calibración del árbol N4** descrita en la tesis: en vez de elegir umbrales a priori, se parte de un gold standard humano y se optimiza sobre κ contra ese gold. El `classifier_config_hash` de cada profile lo hace reproducible — el investigador puede correr el mismo A/B meses después y obtener la misma respuesta.

## 11. Estado de madurez

**Tests** (3 archivos unit):
- `tests/unit/test_analytics_endpoints.py` — κ con casos borderline.
- `tests/unit/test_f7_endpoints.py` — progresión + A/B profiles + validación de gold standard.
- `tests/unit/test_export_endpoints.py` — enqueue + status + download del export worker.

Más tests en `packages/platform-ops/tests/` cubren la lógica analítica pura (Kappa, trayectorias, datasources mockeados).

**Known gaps**:
- ExportJobStore sin persistencia — jobs se pierden en rolling update.
- Audit log (κ, AB) en structlog a Loki, no en tabla queryable (documentado en CLAUDE.md).
- Connection pool `pool_size=2` ad-hoc por request — oportunidad de optimización.
- Acople por `sys.path.insert` con classifier-service — fragile bajo refactors.
- A/B endpoint sólo via API (UI deferida F8+).
- ML predictivo verdadero (>1σ del propio trayecto del estudiante, no de cohorte) DEFERIDO a piloto-2 ([ADR-032](../adr/032-ml-predictive-deferred.md)) — el MVP estadístico (z-score vs cohorte + cuartiles + drill-down) cubre defensa pre-defensa.
- CII longitudinal por `unidad_id` (epic `unidades-trazabilidad`) implementado en `packages/platform-ops/cii_longitudinal.py::compute_evolution_per_unidad`; endpoint análogo a `/cii-evolution-longitudinal` por unidad pendiente de wireup formal (verificar).

**Fase de consolidación**:
- F6 — κ + export básico (`docs/F6-STATE.md`).
- F7 — `/progression`, `/ab-test-profiles`, export worker con `ExportJobStore`.
- F8 — `RealCohortDataSource` + `RealLongitudinalDataSource` con RLS real por tenant.
- F9 — declaración correcta de env vars en `Settings` (fix del trap `pydantic_settings`).
- 2026-04-27 (MVP G7 / [ADR-022](../adr/022-tanstack-router-migration.md)) — 6 endpoints nuevos: `/episode/{id}/n-level-distribution`, `/student/{id}/cii-evolution-longitudinal`, `/student/{id}/episodes`, `/cohort/{id}/cii-quartiles`, `/student/{id}/alerts`, `/cohort/{id}/adversarial-events`. Privacy gate N≥5 para cuartiles.
- 2026-05-04 (epic `ai-native-completion-and-byok`) — `/governance/events` cross-cohort ([ADR-037](../adr/037-governance-ui.md)) con CSV export cp1252-safe.
- 2026-05-04 (epic `real-health-checks`) — `/health/ready` real con check de cross-base.
- 2026-05-07 (epic `unidades-trazabilidad`) — `compute_evolution_per_unidad()` análogo al longitudinal por template, pero agrupando por `unidad_id`.
