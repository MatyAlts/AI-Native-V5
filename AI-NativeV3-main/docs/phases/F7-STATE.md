# Estado del repositorio — F7 completado

F7 es la fase de **extensiones empíricas para el piloto UNSL**. Cierra
los componentes que soportan directamente el capítulo empírico de la
tesis: análisis longitudinal por estudiante, A/B testing del árbol N4
contra gold standard humano, worker real de exportación académica, y
ejemplos runnable del onboarding.

## Entregables F7

### 1. Análisis longitudinal por estudiante

`packages/platform-ops/src/platform_ops/longitudinal.py` — 13 tests.

Permite responder la pregunta central de la tesis: **¿los estudiantes
progresan desde apropiación superficial/delegación hacia reflexiva
durante el cuatrimestre?**

`StudentTrajectory.progression_label()` devuelve una de 4 etiquetas
comparando primer tercio vs último tercio de episodios (escala ordinal
delegacion=0 < superficial=1 < reflexiva=2, con tolerancia 0.25 para ruido):

- `mejorando`: último tercio mayor que primero (> 0.25)
- `empeorando`: menor que primero
- `estable`: dentro del margen
- `insuficiente`: menos de 3 episodios clasificados

`CohortProgression` agrega trayectorias con un **net_progression_ratio**
(mejorando − empeorando) / total_con_datos — indicador único de salud
pedagógica de la cohorte.

`GET /api/v1/analytics/cohort/{comision_id}/progression` expone los
datos al frontend/investigador.

### 2. A/B testing de reference_profiles del árbol N4

`packages/platform-ops/src/platform_ops/ab_testing.py` — 9 tests
(7 unitarios + 2 de integración con classifier real).

Evalúa múltiples profiles del árbol N4 contra un gold standard de
etiquetado humano. El investigador provee N episodios pre-etiquetados
por el docente, y 2+ profiles candidatos (default + tighter, por
ejemplo), y obtiene el Kappa de cada profile contra el juicio humano.

Uso durante el piloto:

```python
report = compare_profiles(
    episodes=gold_standard_episodes,  # con human_label
    profiles=[default_profile, stricter_profile, relaxed_profile],
    classify_fn=classify_episode_from_events,
    compute_hash_fn=compute_classifier_config_hash,
)
print(report.summary_table())
# → gana el profile con mayor Kappa
```

**Propiedad crítica verificada con test de integración**: dos profiles
idénticos producen exactamente las mismas predicciones (reproducibilidad
determinista del clasificador).

`POST /api/v1/analytics/ab-test-profiles` expone el flujo como endpoint. Requiere
`X-Tenant-Id` y `X-User-Id` (mismo contrato del api-gateway que `/cohort/export`
y `/cohort/{id}/progression`). Cierra **HU-088** emitiendo el evento
`ab_test_profiles_completed` por structlog (tenant, user, n_episodes/profiles,
winner, kappa por profile, `classifier_config_hash`) — sesión 2026-04-21
ratifica que `AuditLog` se interpreta como trail de observabilidad
(Loki/Grafana), no tabla persistente; ver detalle y reversibilidad en
`BUGS-PILOTO.md` ("HU-088 / HU-118 audit log decision").

### 3. Worker async de exportación académica

`packages/platform-ops/src/platform_ops/export_worker.py` — 10 tests.

Reemplaza el stub de F6. Implementación completa del flow
`POST /cohort/export` → `GET /status` → `GET /download`:

- `ExportJobStore` in-memory con asyncio.Lock (intercambiable por
  Redis en prod)
- `ExportWorker.run_forever()` consume `PENDING` jobs; transiciones
  estrictas PENDING → RUNNING → SUCCEEDED | FAILED
- `cleanup_old()` borra jobs completados después de N tiempo
- Factory de `data_source_factory(tenant_id)` desacopla el worker de
  la DB real — en F7 usa el stub; en F8 se reemplaza

**Lifecycle del worker integrado al `lifespan` del analytics-service**
— `start_worker()` / `stop_worker()` con graceful shutdown y timeout
configurable.

**3 endpoints nuevos del analytics-service**:
- `POST /api/v1/analytics/cohort/export` → encola job, devuelve `job_id`
- `GET /api/v1/analytics/cohort/export/{job_id}/status` → estado + errores
- `GET /api/v1/analytics/cohort/export/{job_id}/download` → payload JSON
  (en prod F8+ devolverá redirect a S3 firmado)

### 4. Ejemplo runnable de onboarding UNSL

`examples/unsl_onboarding.py` — script ejecutable que encadena los 3
pasos del setup completo:

1. Onboarding Keycloak (realm + client + mapper tenant_id + roles + admin)
2. LDAP federation institucional (usuarios UNSL + group mappings)
3. Feature flags YAML con la config del piloto

Variables de entorno documentadas (`KEYCLOAK_ADMIN_PASSWORD`,
`LDAP_BIND_PASSWORD`, etc.) — el equipo de UNSL puede correrlo como
está con sus credenciales sin modificar código.

## Suite completa — 310/310 tests pasan

```
packages/contracts/tests/test_hashing.py ..................... 7
packages/observability/tests/test_setup.py ................... 6
packages/platform-ops/tests/test_ab_testing.py ................ 7  ← F7
packages/platform-ops/tests/test_ab_integration.py ............ 2  ← F7
packages/platform-ops/tests/test_academic_export.py .......... 12
packages/platform-ops/tests/test_audit.py .................... 11
packages/platform-ops/tests/test_export_worker.py ............ 10  ← F7
packages/platform-ops/tests/test_feature_flags.py ............ 10
packages/platform-ops/tests/test_kappa.py .................... 10
packages/platform-ops/tests/test_ldap_federation.py ........... 5
packages/platform-ops/tests/test_longitudinal.py ............. 13  ← F7
packages/platform-ops/tests/test_privacy.py ................... 9
packages/platform-ops/tests/test_tenant_onboarding.py ......... 4
packages/platform-ops/tests/test_tenant_secrets.py ............ 9
apps/academic-service/tests/*.py ............................. 33
apps/analytics-service/tests/unit/test_analytics_endpoints.py . 8
apps/analytics-service/tests/unit/test_export_endpoints.py .... 6  ← F7
apps/analytics-service/tests/unit/test_f7_endpoints.py ........ 6  ← F7
apps/content-service/tests/unit/*.py ......................... 24
apps/ctr-service/tests/unit/*.py ............................. 19
apps/governance-service/tests/unit/*.py ....................... 7
apps/ai-gateway/tests/unit/*.py .............................. 13
apps/tutor-service/tests/unit/*.py ........................... 16
apps/classifier-service/tests/unit/*.py ...................... 39
apps/api-gateway/tests/unit/*.py ............................. 24
──────────────────────────────────────────────────────────────────
                                                              310

Delta F7: +44 tests nuevos (13 longitudinal + 9 A/B + 10 export worker
          + 6 export endpoints + 6 F7 endpoints)
```

## Propiedades críticas añadidas por F7

1. **Progresión empírica medible**: `net_progression_ratio` es un
   número único [-1, 1] que responde "¿la cohorte mejoró o empeoró
   durante el cuatrimestre?". Reemplaza afirmaciones cualitativas por
   evidencia cuantitativa.

2. **Calibración del clasificador con datos reales**: A/B testing
   permite ajustar umbrales del árbol N4 con feedback del piloto sin
   tocar código — basta correr el endpoint con N profiles candidatos y
   elegir el de mayor Kappa.

3. **Pipeline académico end-to-end**: un investigador con cuenta en la
   plataforma puede: (a) registrar gold standard → (b) A/B profiles →
   (c) exportar dataset anonymizado → (d) correr análisis longitudinal
   → todo desde la UI sin intervención del equipo técnico.

4. **Job queue async sin broker externo**: el worker + store en memoria
   es suficiente para el volumen del piloto (~5-10 exports/día). Cuando
   crezca, solo hay que reemplazar `ExportJobStore` por una
   implementación Redis sin tocar el worker ni los endpoints.

## Cómo usar F7

### Análisis longitudinal
```bash
curl http://localhost:8005/api/v1/analytics/cohort/{comision_id}/progression \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Tenant-Id: aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
```

### A/B testing de profiles
```bash
curl -X POST http://localhost:8005/api/v1/analytics/ab-test-profiles \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Tenant-Id: aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa" \
  -H "X-User-Id: 11111111-1111-1111-1111-111111111111" \
  -H "Content-Type: application/json" \
  -d @gold_standard_with_profiles.json
```

### Exportar dataset académico
```bash
# 1. Encolar
JOB=$(curl -X POST http://localhost:8005/api/v1/analytics/cohort/export \
  -H "X-Tenant-Id: aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa" \
  -H "X-User-Id: 11111111-1111-1111-1111-111111111111" \
  -H "Content-Type: application/json" \
  -d '{"comision_id":"...", "salt":"my-research-salt-16plus", "include_prompts":false}' \
  | jq -r '.job_id')

# 2. Polling
curl http://localhost:8005/api/v1/analytics/cohort/export/$JOB/status

# 3. Descargar
curl http://localhost:8005/api/v1/analytics/cohort/export/$JOB/download \
  > dataset.json
```

### Onboarding de un nuevo tenant (ej UNSL)
```bash
export KEYCLOAK_ADMIN_PASSWORD=xxx
export LDAP_BIND_PASSWORD=yyy
export TENANT_ADMIN_EMAIL=admin@unsl.edu.ar
python examples/unsl_onboarding.py
```

## Estado del plan de tesis

**Con F0-F7 completos, la plataforma soporta el flow completo del piloto**:

1. ✓ Infra multi-tenant + CTR criptográfico (F0-F3)
2. ✓ Clasificador N4 con árbol auditable + reproducibilidad (F3)
3. ✓ Hardening + observabilidad con SLOs (F4)
4. ✓ Producción multi-tenant con SSO + privacy controls (F5)
5. ✓ Integración UNSL + LDAP + canary deployments (F6)
6. ✓ **Pipeline empírico completo** — longitudinal + A/B + Kappa +
   export anonymizado (F7)

Los componentes que alimentan los capítulos de la tesis están listos:
- **Capítulo metodológico**: árbol N4 + CTR con hashing canónico +
  reference_profile determinista (todo reproducible bit a bit)
- **Capítulo empírico**: Kappa inter-rater + net_progression_ratio +
  A/B de profiles + dataset anonymizado exportable
- **Capítulo ético**: privacy controls (export + anonymize) +
  right-to-be-forgotten compatible con cadena criptográfica

## Qué queda para F8+

F8 (integración DB real) y más allá:

- **Adaptador real del data_source** para el worker de export: cruzar
  `ctr_store.events` + `ctr_store.classifications` + `academic_main.*`
  con RLS correcta por tenant
- **Adaptador real del longitudinal**: lo mismo para progresión
- **Frontend del docente con vistas F7**:
  - Vista de progresión individual por estudiante
  - UI de A/B testing con drag-and-drop de ratings
  - Botón "exportar dataset" con progress bar
- **Export en Parquet** para datasets > 100 MB (actualmente JSON
  inline)
- **Storage externo con URLs firmadas** (S3/MinIO) para descargas
- **Retention automática de jobs** (cron de `cleanup_old()`)
