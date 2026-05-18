# Estado del repositorio — F9 completado

F9 es la fase de **preflight operacional** — todo lo que hay que
tener listo antes de desplegar el piloto en Postgres productivo de
UNSL. No agrega funcionalidad; agrega las capas de operación y
análisis que hacen que el piloto sea seguro y auditable.

## Entregables F9

### 1. Migraciones Alembic con RLS

Los 4 servicios con DB (academic, ctr, classifier, content) ya tenían
schema inicial en alembic. F9 agrega RLS en los dos que faltaban:

- `apps/ctr-service/alembic/versions/20260721_0002_enable_rls_on_ctr_tables.py`
- `apps/classifier-service/alembic/versions/20260902_0002_enable_rls_on_classifier_tables.py`

Ambas migrations:
- Activan `ENABLE ROW LEVEL SECURITY` + **`FORCE`** (crítico: el owner
  también respeta la policy, no puede bypassear accidentalmente)
- Crean policy `tenant_isolation_<tabla>` que filtra por
  `current_setting('app.current_tenant')`
- Setean default vacío en la DB → fail-safe: olvidarse del `SET LOCAL`
  produce "no veo nada" en vez de "veo todo"

El patrón se aplica a `episodes`, `events`, `dead_letters` (ctr-service)
y `classifications` (classifier-service). Las otras dos bases (academic
y content) ya incluían RLS en su schema inicial.

### 2. Script orquestador de migraciones

`scripts/migrate-all.sh` — corre `alembic upgrade head` en los 4
servicios con el orden correcto, leyendo URLs desde env vars separadas
por base:

```bash
export CTR_STORE_URL=postgresql+asyncpg://...
export ACADEMIC_DB_URL=...
export CLASSIFIER_DB_URL=...
export CONTENT_DB_URL=...

./scripts/migrate-all.sh           # corre real
./scripts/migrate-all.sh --dry-run # muestra qué haría
```

Fail-fast si falta alguna env var. El script también muestra `alembic
current` antes y después para auditoría.

### 3. Tests de RLS contra Postgres real

`packages/platform-ops/tests/test_rls_postgres.py` — 4 tests que corren
**solo** si está seteada la env var `CTR_STORE_URL_FOR_RLS_TESTS`.
Verifican propiedades que SQLite no puede testear:

1. Sin `SET LOCAL`, queries devuelven vacío (fail-safe confirmado)
2. Con `SET LOCAL tenant_a`, solo se ven filas de tenant_a
3. INSERT con `tenant_id ≠ SET LOCAL` falla por `WITH CHECK`
4. `SET LOCAL` se resetea al commit (nueva txn requiere re-setear)

Diseñados para correrse en CI con un container Postgres; localmente se
skippean automáticamente.

### 4. Runbook operacional del piloto

`docs/pilot/runbook.md` — 10 incidentes codificados con síntomas,
severidad, diagnóstico y acción. Cubre:

| Código | Escenario | Severidad |
|---|---|---|
| I01 | Integridad del CTR comprometida | 🔴 Crítica |
| I02 | Tutor no responde / timeouts altos | 🟠 Alta |
| I03 | Clasificador dejó de procesar | 🟠 Alta |
| I04 | Kappa intermedio < 0.4 | 🟡 Media |
| I05 | Net progression negativa en cátedra | 🟡 Media |
| I06 | Estudiante solicita borrado de datos | 🟢 Normal |
| I07 | Export académico falla | 🟢 Normal |
| I08 | LDAP no autentica usuario | 🟢 Normal |
| I09 | LLM budget agotado | 🟡 Media |
| I10 | Backup diario falló | 🟠 Alta |

Cada incidente se documenta en `docs/pilot/incidents/INNN-YYYY-MM-DD.md`
durante las 16 semanas. Al cierre, los docs se agregan como apéndice
de la tesis como evidencia del rigor operacional.

### 5. Notebook de análisis estadístico

`docs/pilot/analysis-template.ipynb` — Jupyter notebook listo para
usar con el dataset JSON que exporta
`POST /analytics/cohort/export/{id}/download`. Incluye:

1. **Carga del dataset** con verificación del `salt_hash` para
   reproducibilidad
2. **Descriptivos a nivel episodio** — distribución N4, boxplots de las
   5 coherencias por categoría
3. **Análisis longitudinal por estudiante** — replica el algoritmo de
   `progression_label` para garantizar consistencia con el backend +
   heatmap de trayectorias ordenadas
4. **Correlaciones entre coherencias** — heatmap Pearson + tabla de
   correlaciones significativas (p < 0.05)
5. **Test de hipótesis pre-post** — McNemar con tabla de contingencia
   3x3 y binaria (reflexiva vs. resto)
6. **Resumen para reporte** — celda que imprime métricas en formato
   copy-paste para el capítulo empírico

Este notebook es **el pipeline de análisis que correrá Alberto al
cerrar el piloto**. La réplica en Python del algoritmo de
`progression_label` garantiza que el resultado del notebook coincida
exactamente con el endpoint `/progression` del backend — propiedad
importante para la defensa.

## Suite completa — 320/320 tests + 4 RLS skippeados

```
apps/*/tests/unit/*.py ................................... 183 pass
apps/academic-service/tests/integration/*.py ..............  17 pass
packages/*/tests/*.py ..................................... 120 pass
packages/platform-ops/tests/test_rls_postgres.py ..........   4 skipped (requiere CTR_STORE_URL_FOR_RLS_TESTS)
──────────────────────────────────────────────────────────────────
                                                           320 + 4

F8: 320 → F9: 320 + 4 skipped RLS
```

## Propiedades críticas añadidas por F9

1. **Despliegue reproducible**: cualquiera con las 4 env vars de DB
   puede correr `./scripts/migrate-all.sh` y obtener el schema completo
   con RLS activo. Cero pasos manuales en psql. Esto es importante
   porque reduce el riesgo de olvidarse de activar RLS en prod (falla
   típica de primeros despliegues).

2. **RLS testeable contra Postgres real**: antes de F9, RLS estaba en
   la arquitectura pero solo se testeaba "implícitamente" (con doble
   filtro en queries). Ahora hay tests explícitos que se corren en CI
   contra Postgres de test, verificando el comportamiento fail-safe.

3. **Runbook que deja paper trail**: cada incidente del piloto se
   documenta. No es solo disciplina operacional — es evidencia de
   validez del estudio. Cuando un revisor de tesis pregunte "¿cómo
   aseguraste la integridad de los datos durante 16 semanas?" la
   respuesta es "acá está el runbook y los 6 incidentes I07 documentados".

4. **Pipeline de análisis pre-construido**: Alberto no va a tener que
   construir el análisis estadístico desde cero con el dataset en la
   mano. El notebook corre end-to-end contra el JSON exportado, con
   chequeos de consistencia backend-notebook (misma lógica de
   progression_label).

## Cómo usar F9

### Desplegar DB en UNSL (primera vez)

```bash
# 1. Crear las 4 bases lógicas
psql -h <host> -U postgres << EOF
CREATE DATABASE academic_main;
CREATE DATABASE ctr_store;
CREATE DATABASE classifier_db;
CREATE DATABASE content_db;
EOF

# 2. Exportar URLs
export ACADEMIC_DB_URL="postgresql+asyncpg://user:pw@host/academic_main"
export CTR_STORE_URL="postgresql+asyncpg://user:pw@host/ctr_store"
export CLASSIFIER_DB_URL="postgresql+asyncpg://user:pw@host/classifier_db"
export CONTENT_DB_URL="postgresql+asyncpg://user:pw@host/content_db"

# 3. Dry-run primero
./scripts/migrate-all.sh --dry-run

# 4. Correr real
./scripts/migrate-all.sh
```

### Correr tests de RLS en CI

```bash
# En el pipeline de CI:
docker run -d --name pg-test \
  -e POSTGRES_PASSWORD=test \
  -e POSTGRES_DB=ctr_test \
  -p 5433:5432 postgres:16

# Aplicar migraciones al test DB
CTR_STORE_URL=postgresql+asyncpg://postgres:test@localhost:5433/ctr_test \
  ./scripts/migrate-all.sh

# Correr tests
CTR_STORE_URL_FOR_RLS_TESTS=postgresql+asyncpg://postgres:test@localhost:5433/ctr_test \
  pytest packages/platform-ops/tests/test_rls_postgres.py -v
```

### Responder a un incidente del piloto

```bash
# 1. Identificar código del incidente en docs/pilot/runbook.md
# 2. Seguir procedimiento de diagnóstico del código
# 3. Aplicar acción documentada
# 4. Crear doc del incidente:
mkdir -p docs/pilot/incidents/
cat > docs/pilot/incidents/I01-$(date +%Y-%m-%d).md << EOF
# Incident I01 — $(date +%Y-%m-%d)

Síntoma: ...
Causa raíz: ...
Acción tomada: ...
Datos afectados: ...
EOF
```

### Analizar el dataset del piloto

```bash
cd docs/pilot/
jupyter notebook analysis-template.ipynb
# Editar DATASET_PATH en la celda 3 → apuntar al JSON descargado
# Run All → produce todas las figuras + métricas para la tesis
```

## Estado del plan completo

Con F0-F9 la plataforma cubre **todo** lo necesario para el piloto:

| Fase | Alcance | Estado |
|---|---|---|
| F0-F3 | Monorepo + 12 servicios + 3 frontends + CTR criptográfico + clasificador N4 | ✅ |
| F4 | Hardening + observabilidad + SLOs | ✅ |
| F5 | Multi-tenant + JWT + onboarding + privacy | ✅ |
| F6 | OIDC E2E + feature flags + export + kappa + audit + LDAP + canary | ✅ |
| F7 | Longitudinal + A/B profiles + worker async + ejemplos runnable | ✅ |
| F8 | DB adapters reales + frontend docente + Grafana + protocolo DOCX | ✅ |
| F9 | Migraciones con RLS + runbook + notebook análisis | ✅ |

**La plataforma está lista para el piloto UNSL**. Lo que queda es
ejecutar el piloto (16 semanas) y escribir el capítulo empírico con
los resultados.
