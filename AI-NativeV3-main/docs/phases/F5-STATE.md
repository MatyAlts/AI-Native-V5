# Estado del repositorio — F5 completado

F5 transforma la plataforma de F4 (funcional + observable) en una
plataforma **multi-tenant lista para producción**: auth real con
Keycloak, onboarding automatizado de universidades, secrets por tenant,
feature flags, backup/restore, privacy controls según GDPR, y ejecución
real de código Python en el navegador vía Pyodide.

## Entregables F5

### 1. JWT validation real en api-gateway

`apps/api-gateway/src/api_gateway/services/jwt_validator.py` +
`middleware/jwt_auth.py`:

- **Validación RS256 obligatoria** (rechaza HS256 para prevenir
  alg-confusion attacks).
- **JWKS cache con rotación automática**: si llega un JWT firmado con
  `kid` desconocido, se hace force-refresh del JWKS antes de fallar.
- **Claims obligatorios**: `iss`, `aud`, `exp`, `sub`, custom
  `tenant_id`. Tokens sin `tenant_id` se rechazan — garantiza que el
  tenant haya pasado por el onboarding.
- **Middleware** reescribe headers `X-*` autoritativamente con los
  claims del JWT — los servicios internos confían ciegamente en esos
  headers, y el gateway es el único que los puede setear.
- **Modo `dev_trust_headers`** para desarrollo local sin Keycloak
  (producción debe setear `dev_trust_headers=False`).
- **X-Request-Id** inyectado para correlación de logs.

Tests: 12/12 incluyendo casos críticos de seguridad (token expirado,
issuer erróneo, audience errónea, firma manipulada, `kid` desconocido,
HS256 rechazado, token sin `tenant_id`, header Authorization malformado).

### 2. Onboarding automatizado de tenants

`packages/platform-ops/src/platform_ops/tenant_onboarding.py`:

Script **idempotente** que hace el setup completo de un tenant nuevo
con un solo comando:

```bash
python -m platform_ops.tenant_onboarding \
    --tenant-name "UNSL" \
    --tenant-uuid aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa \
    --admin-email admin@unsl.edu.ar \
    --keycloak-url https://keycloak.platform.ar
```

Pasos ejecutados:
1. Crear realm Keycloak (o reutilizar existente).
2. Crear client `platform-backend` con audience correcta.
3. Agregar **claim mapper `tenant_id`** que inyecta el UUID del tenant
   en todos los tokens del realm — esta es la pieza que cierra el
   círculo con el JWT validator.
4. Crear los 4 roles del realm: `estudiante`, `docente`, `docente_admin`,
   `superadmin`.
5. Crear usuario admin con password temporal + `requiredAction:
   UPDATE_PASSWORD` → fuerza cambio en primer login.
6. Reportar qué pasos se ejecutaron y qué se reutilizó.

Secrets (password del admin Keycloak) vienen de env vars —
`KEYCLOAK_ADMIN_PASSWORD`, nunca en argparse.

Tests: 4/4 incluyendo verificación de que el mapper configura el UUID
correcto, idempotencia (re-correr no duplica nada), password temporal
con `UPDATE_PASSWORD`.

### 3. Tenant secrets — API keys por tenant

`packages/platform-ops/src/platform_ops/tenant_secrets.py`:

`TenantSecretResolver.get_llm_api_key(tenant_id, provider)` resuelve en
este orden:

1. Archivo mountado en K8s: `/etc/platform/llm-keys/{tenant_id}/{provider}.key`
2. Env var per-tenant: `LLM_KEY_{TENANT_UUID}_{PROVIDER}`
3. Env var global fallback: `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`
4. Si nada, `SecretNotFoundError` con mensaje accionable.

Ventaja: tenants grandes (UNSL pilot) pueden tener su **propia cuenta
Anthropic** con su propio budget, mientras tenants más chicos pueden
compartir la cuenta de la plataforma. Sin cambios en el ai-gateway.

Tests: 9/9 incluyendo aislamiento entre tenants, fallback global,
override per-tenant pisando global, archivo vacío no cuenta como key.

### 4. Feature flags por tenant

`packages/platform-ops/src/platform_ops/feature_flags.py`:

YAML versionado con `default:` + overrides `per_tenant:`:

```yaml
default:
  enable_code_execution: false
  enable_claude_opus: false
  max_episodes_per_day: 50

tenants:
  aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa:
    enable_code_execution: true
    enable_claude_opus: true
    max_episodes_per_day: 200
```

API:
- `flags.is_enabled(tenant_id, "enable_code_execution")` → bool
- `flags.get_value(tenant_id, "max_episodes_per_day")` → int
- `flags.get_all_for_tenant(tenant_id)` → dict con todos los resueltos

**Propiedades**:
- Reload automático del archivo cada N segundos (hash de contenido
  evita rebuild innecesario).
- Feature no declarada → `FeatureNotDeclaredError` (nunca silent false).
- `is_enabled` tipado estricto: si el valor no es bool, `TypeError`.
- Parser YAML minimal sin dependencias externas.

Tests: 10/10 incluyendo override parcial + complete con default,
feature no declarada, tipado estricto, reload tras modificación.

### 5. Privacy controls — GDPR / Ley 25.326

`packages/platform-ops/src/platform_ops/privacy.py`:

**`export_student_data(student_pseudonym, data_source)`**:
- Recolecta: episodios + eventos CTR embebidos + clasificaciones +
  materiales subidos
- Firma SHA-256 del paquete entero para verificación de integridad
- Exit: JSON serializable listo para entregar al estudiante

**`anonymize_student(student_pseudonym, data_source)`** (right to be
forgotten compatible con append-only del CTR):
- Rota el `student_pseudonym` en `episodes` (nuevo UUID aleatorio)
- **NO toca los eventos del CTR** — modificarlos rompería la cadena
  criptográfica, que es evidencia auditable (art. 17.3.e GDPR)
- El estudiante original ya no es vinculable a los eventos
  externamente: sin la fila del episodio con su pseudónimo, no hay forma
  de ir del estudiante a los eventos
- Las clasificaciones apuntan por `episode_id`, se preservan sin cambios

**Propiedad crítica verificada con test**: `anonymize_student` preserva
los eventos CTR byte-a-byte.

Tests: 9/9 incluyendo verificación de que la cadena criptográfica
permanece intacta tras anonimización.

### 6. Backup / Restore automatizados

`scripts/backup.sh`, `scripts/restore.sh`:

**Backup**:
- `pg_dump --format=custom --compress=9` de las 3 bases
  (academic_main, ctr_store, identity_realms)
- Genera `manifest.txt` con SHA-256 de cada dump
- Variables de entorno para credenciales (nunca hardcoded)

**Restore**:
- Requiere `CONFIRM=yes` o input interactivo (escribir "RESTORE")
- **Verifica checksums** contra el manifest antes de restaurar
- DROP + CREATE + pg_restore por cada base
- Fail-fast si cualquier checksum no coincide

**`ops/k8s/backup-cronjob.yaml`**:
- CronJob diario a las 03:00 UTC
- Retiene 7 días de backups exitosos
- PVC dedicado `platform-backups` con 50Gi
- `PrometheusRule` con 2 alertas: `PlatformBackupJobFailed` (crítica) y
  `PlatformBackupMissing` (warning si >26h sin backup exitoso).

### 7. Editor Monaco + Pyodide sandbox en web-student

`apps/web-student/src/components/CodeEditor.tsx`:

- **Monaco Editor** (mismo engine que VS Code) con syntax highlighting
  Python, auto-layout responsive, theme vs-dark
- **Pyodide 0.26** cargado dinámicamente del CDN (~6 MB una vez,
  luego cacheado)
- Ejecución Python 100% en el navegador — **cero costo** de infra
  backend, cero riesgo de abuso, latencia mínima tras el primer load
- stdout/stderr capturados y mostrados en panel inferior
- Callback `onCodeExecuted` para que el caller emita eventos CTR
  `codigo_ejecutado` con el output real
- Limitaciones documentadas: sin network calls, stdlib completa, PyPI
  requiere micropip, ejecución sincrónica

Package.json actualizado con `monaco-editor@^0.52.0`.

## Suite completa — 216/216 tests pasan

```
packages/contracts/tests/test_hashing.py ..................... 7
packages/observability/tests/test_setup.py ................... 6
packages/platform-ops/tests/test_feature_flags.py ........... 10   ← F5
packages/platform-ops/tests/test_privacy.py .................. 9   ← F5
packages/platform-ops/tests/test_tenant_onboarding.py ........ 4   ← F5
packages/platform-ops/tests/test_tenant_secrets.py ........... 9   ← F5
apps/academic-service/tests/*/*.py ........................... 33
apps/content-service/tests/unit/*.py ......................... 24
apps/ctr-service/tests/unit/*.py ............................. 19
apps/governance-service/tests/unit/*.py ...................... 7
apps/ai-gateway/tests/unit/*.py .............................. 13
apps/tutor-service/tests/unit/*.py ........................... 12
apps/classifier-service/tests/unit/*.py ...................... 39
apps/api-gateway/tests/unit/*.py ............................. 24   ← +12 JWT
──────────────────────────────────────────────────────────────────
                                                              216

Delta F5: +44 tests nuevos (12 JWT + 4 onboarding + 9 privacy
          + 9 secrets + 10 feature flags)
```

## Propiedades críticas preservadas + añadidas por F5

1. **Identidad autoritativa**: el api-gateway es el único componente que
   puede setear `X-User-Id` / `X-Tenant-Id`. Los clientes no pueden
   spoofear identidad.

2. **Aislamiento de budget de LLM por tenant**: cada universidad paga su
   consumo desde su propia cuenta Anthropic. La plataforma nunca expone
   keys de un tenant a otro.

3. **Right to be forgotten sin romper auditoría**: el anonymize rota el
   pseudónimo y deja los eventos CTR intactos. Se cumple la obligación
   legal (el estudiante ya no es identificable) y se preserva la
   evidencia auditable del registro (importante para casos de sospecha
   de fraude académico).

4. **Backups verificados**: los checksums de manifest.txt se verifican
   en restore; backup corrupto se detecta antes de sobreescribir prod.

5. **Ejecución de código sin costo incremental**: Pyodide descarga el
   riesgo del backend al navegador. 1000 alumnos ejecutando código al
   mismo tiempo no saturan nada del servidor.

6. **Feature flags declarativas**: nuevas features llegan con
   default conservador (apagadas para todos); onboarding de tenant
   piloto activa selectivamente.

## Cómo correr F5 localmente

```bash
# Suite completa
cd /home/claude/platform
EMBEDDER=mock RERANKER=identity STORAGE=mock LLM_PROVIDER=mock \
PYTHONPATH=apps/academic-service/src:apps/content-service/src:apps/ctr-service/src:apps/governance-service/src:apps/ai-gateway/src:apps/tutor-service/src:apps/classifier-service/src:apps/api-gateway/src:packages/contracts/src:packages/test-utils/src:packages/observability/src:packages/platform-ops/src \
  python3 -m pytest \
    apps/*/tests/unit/ \
    apps/academic-service/tests/integration/test_casbin_matrix.py \
    packages/*/tests/

# Esperado: 216 passed

# Onboarding de tenant nuevo (requiere Keycloak corriendo)
KEYCLOAK_ADMIN_PASSWORD=admin python -m platform_ops.tenant_onboarding \
    --tenant-name "UNSL" \
    --tenant-uuid aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa \
    --admin-email admin@unsl.edu.ar \
    --keycloak-url http://localhost:8180

# Backup manual
PG_BACKUP_PASSWORD=xxx ./scripts/backup.sh /tmp/platform-backup

# Restore
CONFIRM=yes PG_ADMIN_PASSWORD=xxx ./scripts/restore.sh /tmp/platform-backup
```

## Qué queda para F6

- **Adoptar el `platform-observability` unificado en cada servicio**:
  reemplazar los 8 `observability.py` dispersos por un único import.
- **OIDC flow real en los frontends**: hoy los frontends mandan headers
  X-* de dev. F6 integra `keycloak-js` para obtener tokens y enviar
  `Authorization: Bearer ...`.
- **Canary deployments con Argo Rollouts**: reemplazar deploy directo
  por rollout gradual (10% → 50% → 100%) con análisis automático de
  métricas.
- **Evento CTR `codigo_ejecutado`** emitido desde web-student cuando
  Pyodide corre código. El callback está listo pero falta el wire al
  tutor-service.
- **Feature flags consumidas en runtime por tutor-service y
  classifier-service**: hoy el package existe pero los servicios
  todavía no las consultan. Wire simple pero falta hacerlo.
- **Auditoría de accesos sospechosos**: logs de login fallidos
  repetidos, acceso a recursos fuera del tenant, etc.
- **Exportación académica de datos para investigadores** (tesis): dump
  anonymizado del CTR + clasificaciones para análisis externo.

## Próxima fase — F6 (meses 16-18): Piloto en UNSL

- Integración con la infraestructura existente de UNSL (SSO, LDAP)
- Piloto con 3 cátedras: Programación 1, Programación 2, TSU en IA
- Métricas de adopción + refinamiento de árbol N4 con datos reales
- Análisis inter-rater (Kappa) del clasificador vs etiquetado humano
- Paper científico con resultados del piloto
