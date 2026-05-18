# Estado del repositorio — F6 completado

F6 convierte la plataforma multi-tenant de F5 en una plataforma **lista
para el piloto en UNSL**: integración SSO/LDAP institucional, eventos
`codigo_ejecutado` cerrando el loop con Pyodide, exportación académica
anonymizada para investigadores, análisis Kappa inter-rater para la
validación empírica de la tesis, auditoría de accesos sospechosos, y
canary deployments para rollouts seguros.

## Entregables F6

### 1. Observabilidad unificada en todos los servicios

Los 12 `observability.py` dispersos (~46 LOC cada uno) se colapsaron a
wrappers de ~20 LOC que delegan al package `platform-observability`.
La API pública `setup_observability(app)` se mantiene intacta; cualquier
cambio futuro al stack OTel se hace en un único lugar.

Servicios migrados: academic-service, ai-gateway, analytics-service,
api-gateway, classifier-service, content-service, ctr-service,
enrollment-service, evaluation-service, governance-service,
identity-service, tutor-service.

### 2. OIDC flow real end-to-end

**`packages/auth-client/src/http.ts`** — cliente HTTP autenticado:
- `useAuthenticatedFetch()` hook inyecta `Authorization: Bearer`
  automáticamente
- Auto-retry con token refrescado si recibe 401
- `authenticatedSSE()` para SSE con auth (EventSource nativo no soporta
  headers custom)
- Redirige a login si el refresh falla

**`apps/web-student/src/lib/api.ts`** — migrado a JWT:
- Reemplazó headers `X-*` dev por `Authorization: Bearer`
- Todas las funciones toman ahora `TokenGetter` como primer parámetro
- Nueva función `emitCodeExecuted()` para el evento CTR del código

### 3. Evento `codigo_ejecutado` end-to-end

Cierra el loop entre Pyodide (F5) y la cadena criptográfica del CTR.

**Backend** (`tutor-service`):
- `POST /api/v1/episodes/{id}/events/codigo_ejecutado` recibe
  code/stdout/stderr/duration_ms
- `TutorCore.emit_codigo_ejecutado()` asigna `seq` atómicamente,
  publica al ctr-stream
- **Propiedad crítica**: usa el `user_id` del estudiante (no el service
  account del tutor) — el estudiante es el autor real del código,
  quedando auditable en la cadena CTR

**Frontend**: el callback `onCodeExecuted` de `CodeEditor` ya existe
desde F5; en F6 se wire a `emitCodeExecuted()` del api client.

Tests: 4 nuevos en `test_tutor_core.py` incluyendo preservación de
orden con eventos intercalados y verificación de que el caller_id
correcto se pasa al CTR.

### 4. Feature flags consumidas en runtime

**`tutor-service/services/features.py`** — singleton `FeatureFlags` del
package `platform-ops`. Config extendida con `feature_flags_path` y
`feature_flags_reload_seconds`.

**`POST /api/v1/episodes`** ahora consulta
`flags.is_enabled(tenant_id, "enable_claude_opus")` para elegir el modelo:
- Flag ON → `claude-opus-4-7`
- Flag OFF o no declarada → `claude-sonnet-4-6` (fallback seguro)

El modelo elegido se persiste en `SessionState` (nuevo campo `model`) y
se registra en el payload del evento `episodio_abierto` → queda en la
cadena CTR auditable qué modelo se usó en cada episodio.

### 5. Exportación académica anonymizada

**`packages/platform-ops/src/platform_ops/academic_export.py`** — 12 tests.

`AcademicExporter.export_cohort()` produce un dataset para investigadores
con:
- Episodios con pseudónimos determinísticos (hash del UUID real + salt
  de investigación)
- Las 5 coherencias N4 (ct_summary, ccd_mean, ccd_orphan_ratio,
  cii_stability, cii_evolution)
- Contadores de eventos por tipo (prompts, code executions, annotations)
- Distribution summary global
- `include_prompts=False` por default (minimiza riesgo de
  re-identificación)
- `salt_hash` incluido para reproducibilidad entre exports

**Propiedades críticas verificadas con tests**:
- Mismo UUID + mismo salt → mismo alias (permite cross-referencia entre
  investigadores que compartan salt)
- Salt distinto → aliases distintos (sin el salt no se puede
  cross-referenciar)
- Salt mínimo 16 chars (rechaza salts débiles)

**Endpoint**: `POST /api/v1/analytics/cohort/export` valida el request y
encola (stub para F7 con worker async + link firmado de descarga).

### 6. Análisis Kappa inter-rater

**`packages/platform-ops/src/platform_ops/kappa_analysis.py`** — 10 tests.

`compute_cohen_kappa(ratings)` devuelve:
- `kappa` con interpretación Landis & Koch (pobre/justo/moderado/
  sustancial/casi perfecto)
- `observed_agreement` y `expected_agreement` separados
- `per_class_agreement` para identificar qué categoría está fallando
- `confusion_matrix` completa

**Endpoint**: `POST /api/v1/analytics/kappa` — validación estricta con
Literal pydantic (categorías exactas), 8 tests incluyendo casos borde.

Este endpoint es el corazón de la validación empírica de la tesis:
cualquier docente del piloto puede evaluar N episodios clasificados por
el modelo, comparar con su propia intuición, y obtener el κ del
clasificador en segundos.

### 7. Auditoría de accesos sospechosos

**`packages/platform-ops/src/platform_ops/audit.py`** — 11 tests.

3 reglas implementadas:
- `BruteForceRule`: 5 logins fallidos en 5min (HIGH)
- `CrossTenantAccessRule`: requests con tenant mismatch en el error
  reason (CRITICAL)
- `RepeatedAuthFailuresRule`: 10 errores 401 en 10min (MEDIUM)

`AuditEngine` corre todas las reglas contra un batch y ordena findings
por severidad. Cada finding serializable a JSON para integración SIEM.

### 8. Integración SSO/LDAP institucional

**`packages/platform-ops/src/platform_ops/ldap_federation.py`** — 5 tests.

`LDAPFederator.configure(spec)` hace setup **idempotente** de user
federation LDAP en un realm Keycloak:
- Provider con config completa (connection_url, bind_dn, users_dn, TLS)
- `editMode: READ_ONLY` — la plataforma nunca modifica el LDAP
  institucional
- Mappers estándar: email, first_name, last_name (desde atributos LDAP
  como `mail`, `givenName`, `sn`)
- **Mapper `tenant_id` hardcoded** en el provider — garantiza que
  usuarios que entran vía LDAP también reciben el claim `tenant_id` en
  su JWT
- Mappers de grupo LDAP → rol del realm (ej grupo `cn=docentes,...` →
  role `docente`)

Ejemplo config UNSL:
```python
LDAPConfig(
    connection_url="ldaps://ldap.unsl.edu.ar:636",
    bind_dn="cn=admin,dc=unsl,dc=edu,dc=ar",
    users_dn="ou=people,dc=unsl,dc=edu,dc=ar",
    use_tls=True,
)
```

### 9. Canary deployments con Argo Rollouts

**`ops/k8s/canary-tutor-service.yaml`**:

Strategy:
1. 10% del tráfico → 2 min
2. **Análisis automático** contra 3 métricas Prometheus
3. 50% → 5 min
4. Segundo análisis (más largo = más confianza)
5. 100%

Criterios de análisis (si falla → rollback automático):
- Latencia P95 del tutor < 3s
- Error rate 5xx < 1%
- `ctr_episodes_integrity_compromised_total` no incrementa
  (cualquier violación = rollback inmediato)

Este último criterio es específico del dominio: una regresión que
rompa la cadena CTR es catastrófica, y el canary la detecta antes de
full rollout.

## Suite completa — 266/266 tests pasan

```
packages/contracts/tests/test_hashing.py ..................... 7
packages/observability/tests/test_setup.py ................... 6
packages/platform-ops/tests/test_academic_export.py .......... 12  ← F6
packages/platform-ops/tests/test_audit.py .................... 11  ← F6
packages/platform-ops/tests/test_feature_flags.py ............ 10
packages/platform-ops/tests/test_kappa.py .................... 10  ← F6
packages/platform-ops/tests/test_ldap_federation.py ........... 5  ← F6
packages/platform-ops/tests/test_privacy.py ................... 9
packages/platform-ops/tests/test_tenant_onboarding.py ......... 4
packages/platform-ops/tests/test_tenant_secrets.py ............ 9
apps/academic-service/tests/*.py ............................. 33
apps/analytics-service/tests/unit/*.py ......................... 8  ← F6
apps/content-service/tests/unit/*.py ......................... 24
apps/ctr-service/tests/unit/*.py ............................. 19
apps/governance-service/tests/unit/*.py ....................... 7
apps/ai-gateway/tests/unit/*.py .............................. 13
apps/tutor-service/tests/unit/*.py ........................... 16  ← +4 codigo_ejecutado
apps/classifier-service/tests/unit/*.py ...................... 39
apps/api-gateway/tests/unit/*.py ............................. 24
──────────────────────────────────────────────────────────────────
                                                              266

Delta F6: +50 tests nuevos (12 academic_export + 10 kappa + 11 audit
          + 5 LDAP + 8 analytics endpoints + 4 codigo_ejecutado)
```

## Propiedades críticas añadidas por F6

1. **Identidad federada institucional**: los usuarios UNSL se
   autentican con su cuenta institucional existente (LDAP) — no hay que
   re-registrar a cientos de estudiantes.

2. **codigo_ejecutado auditable**: toda ejecución de código en Pyodide
   queda en la cadena CTR con el `user_id` del estudiante que la
   ejecutó, preservando la propiedad crítica de auditabilidad del
   CTR.

3. **Investigación reproducible**: dos investigadores con el mismo
   salt pueden cross-referenciar análisis; sin el salt, no se puede
   re-identificar a ningún estudiante del dataset exportado.

4. **Kappa computable on-demand**: el docente puede validar el
   clasificador contra su juicio en cualquier momento sin intervención
   del equipo técnico. Fundamental para iterar el árbol N4 con
   feedback empírico durante el piloto.

5. **Selección de modelo por feature flag**: la universidad puede
   activar Claude Opus para cohortes específicas (cuando requieran
   mejor calidad) sin cambios de código.

6. **Canary con rollback inmediato ante regresión del CTR**: un deploy
   que rompa la integridad criptográfica se revierte automáticamente
   en minutos.

## Cómo correr F6 localmente

```bash
cd /home/claude/platform
EMBEDDER=mock RERANKER=identity STORAGE=mock LLM_PROVIDER=mock \
PYTHONPATH=apps/academic-service/src:apps/content-service/src:apps/ctr-service/src:apps/governance-service/src:apps/ai-gateway/src:apps/tutor-service/src:apps/classifier-service/src:apps/api-gateway/src:apps/analytics-service/src:packages/contracts/src:packages/test-utils/src:packages/observability/src:packages/platform-ops/src \
  python3 -m pytest \
    apps/*/tests/unit/ \
    apps/academic-service/tests/integration/test_casbin_matrix.py \
    packages/*/tests/

# Esperado: 266 passed

# Ejecutar un análisis Kappa (requiere analytics-service corriendo)
curl -X POST http://localhost:8005/api/v1/analytics/kappa \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Tenant-Id: aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa" \
  -H "X-User-Id: 11111111-1111-1111-1111-111111111111" \
  -H "Content-Type: application/json" \
  -d '{"ratings": [
    {"episode_id": "ep1", "rater_a": "apropiacion_reflexiva", "rater_b": "apropiacion_reflexiva"},
    {"episode_id": "ep2", "rater_a": "apropiacion_superficial", "rater_b": "apropiacion_reflexiva"}
  ]}'

# Setup LDAP federation para UNSL
KEYCLOAK_ADMIN_PASSWORD=xxx LDAP_BIND_PASSWORD=yyy python -c "
import asyncio
from platform_ops import LDAPFederator, LDAPFederationSpec, LDAPConfig, LDAPGroupMapping
from uuid import UUID
# ... (ver examples/unsl_ldap_setup.py)
"
```

## Qué queda para futuras fases

F6 cierra el scope planificado del plan detallado (4 años, 5 fases
ordinarias + piloto). Los pendientes remanentes son extensiones
naturales:

- **Worker async de exportación académica** (F7): el endpoint
  `/cohort/export` hoy es stub; el worker que lee de las 3 DBs + sube
  a S3 firmado queda para implementación real post-piloto.
- **Export streaming Parquet** para datasets grandes.
- **SIEM integration**: enviar los `SuspiciousAccess` findings a Splunk
  o ELK del departamento de seguridad de UNSL.
- **Análisis longitudinal** de evolución N4 por estudiante (actualmente
  tenemos timeseries a nivel comisión).
- **A/B testing del árbol N4**: múltiples `reference_profile` corriendo
  en paralelo comparados con kappa inter-rater, para refinar umbrales.
- **Integración con TSU en IA**: el curriculum de Alberto (4 semestres)
  como segundo tenant del piloto.

## Estado del plan de tesis

Con F0-F6 completos, la plataforma contiene:
- Infraestructura multi-tenant con RLS + append-only CTR ✓
- Clasificador N4 explicable con árbol auditable ✓
- Tutor socrático con RAG + streaming ✓
- Ejecución de código en sandbox (Pyodide) ✓
- Auth federada con LDAP institucional ✓
- Exportación anonymizada para investigación ✓
- Kappa inter-rater on-demand ✓
- Dashboards de SLOs + canary deployments ✓
- Privacy controls GDPR/Ley 25.326 ✓

El siguiente paso del plan de tesis es el **piloto real en UNSL con
tres cátedras** (Programación 1, Programación 2, TSU en IA), usando
esta plataforma. Los resultados del piloto alimentan el capítulo
empírico de la tesis.
