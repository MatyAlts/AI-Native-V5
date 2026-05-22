# Informe pre-producción — AI-Native N4

**Destinatario:** Alberto Alejandro Cortez · Doctorando UTN
**Autor del informe:** Juani Sarmiento
**Fecha:** 2026-05-15
**Estado del repo:** `JuaniSarmiento/AI-Native-V4` · branch `main` · último commit `acd92f3`

Este documento sintetiza el estado del piloto antes de migrarlo al VPS institucional UTN. Lista lo que hay operativo, lo que bloquea producción, y las dependencias externas que no se resuelven desde código.

---

## 1. Resumen ejecutivo

| Eje | Estado |
|---|---|
| Núcleo académico (CTR + classifier + RAG + tutor socrático) | **Operativo y defendible doctoralmente como prototipo** |
| Invariantes criptográficas | Verificadas end-to-end (incluyendo tampering test) |
| Multi-tenant con aislamiento real | Aplicado hoy: 1 universidad = 1 tenant con RLS forced |
| Frontends (admin, docente, alumno, landing) | Operativos en dev |
| Listo para piloto académico controlado | Sí, con observación de un investigador |
| Listo para producción real (cientos de alumnos, sin supervisión) | **No** — requiere 6 bloqueantes + dependencias externas |

**Tiempo estimado a producción:** 3-4 meses, principalmente por coordinaciones humanas (DI UTN, docentes para κ, infra institucional), no por código.

---

## 2. Lo que está operativo y defendible hoy

### 2.1. Invariantes académicas verificadas

| Invariante | Mecanismo | Test que la valida |
|---|---|---|
| **CTR append-only** | SHA-256 self_hash + chain_hash encadenados | `make test-smoke` (suite E2E, <2s) |
| **Tampering detection** | Verify endpoint recomputa hashes y reporta `failing_seq` | Validado manualmente con `UPDATE events SET self_hash='deadbeef...'` |
| **`classifier_config_hash` determinista** | Función pura sobre `(tree_version, profile)` | Re-clasificar el mismo episodio → mismo hash |
| **3 coherencias separadas en 5 métricas** (CT, CCD_mean, CCD_orphan_ratio, CII_stability, CII_evolution) | Persistidas en columnas distintas de `classifications` | Schema enforza separación |
| **Multi-tenant RLS** | Postgres FORCE ROW LEVEL SECURITY en todas las tablas con `tenant_id` | Cross-tenant leak test: GET con header swap → 404 |
| **K-anonymity N≥5 en cuartiles** | Guard explícito en `cii_alerts.py` | Endpoint `/cohort/{id}/cii-quartiles` devuelve `insufficient_data` |
| **Eventos excluidos del classifier** | `_EXCLUDED_FROM_FEATURES` frozenset | Test golden en `test_pipeline_reproducibility.py` |
| **Aislamiento de universidades** | `tenant_id = universidad.id`, ADR aplicado 2026-05-15 | Universidad nueva arranca con 0 ejercicios |

### 2.2. Capabilities funcionales

Sobre 20 capabilities evaluadas en `docs/research/audi2.md`:

- **11 al 100%**: gestión multi-tenant, bulk-import, TP templates, dashboard cohorte, alertas k-anonymity, clasificación N4, reflexión post-cierre, longitudinal CII, auditoría CTR, generación TP por IA, BYOK multi-provider.
- **9 parciales** con bloqueador específico identificable.
- **6 en skeleton OFF** (agenda piloto-2 o gates externos).

### 2.3. Métricas del repo

| | |
|---|---|
| Servicios Python activos | 11 |
| Bases lógicas | 4 (`academic_main`, `ctr_store`, `classifier_db`, `content_db`) |
| Frontends | 4 (admin, docente, alumno, **landing nueva**) |
| ADRs documentados | 49 (43 originales + 6 de aislamiento/banco/landing) |
| Migraciones Alembic | 19 |
| Tests E2E smoke | 30 (corren en <2s) |

---

## 3. Bloqueantes para subir a producción real

Estos **no se pueden saltar**. Sin ellos, el sistema no es deployable o no es defendible doctoralmente.

### 3.1. Autenticación real (Keycloak + JWT)

**Estado:** `api-gateway` corre con `dev_trust_headers=True`. Confía en los headers `X-User-Id`, `X-Tenant-Id`, `X-User-Roles` sin validar nada. Cualquiera con `curl` puede simular cualquier usuario.

**Qué falta:**
- Configurar realm institucional UTN en Keycloak
- Federación LDAP read-only con DI UTN (condición del convenio)
- Validador JWT RS256 en `api-gateway`
- Wirear `keycloak-js` en los 3 frontends (la dependencia ya está instalada)
- Quitar el monkey-patch de `window.fetch` que inyecta `x-selected-tenant` (en prod el JWT decide el tenant)
- Quitar los UUIDs hardcoded en `vite.config.ts`

**Esfuerzo estimado:** 1-2 semanas + coordinación DI UTN.

**Dependencia externa:** **Sí.** Requiere coordinación formal con DI UTN.

### 3.2. Claim `comisiones_activas` en JWT (gap B.2)

**Estado:** El endpoint legacy `/api/v1/comisiones/mis` joinea `usuarios_comision` (docentes), pero los alumnos viven en `inscripciones` con `student_pseudonym`. El alumno hoy ve 0 comisiones en ese endpoint. Hay un workaround vigente (`/materias/mias` joinea contra `inscripciones`).

**Qué falta:**
- DI UTN emite claim `comisiones_activas` en el JWT
- Backend lee el claim en lugar de joinear tablas según rol
- Plan operativo documentado en `AI-NativeV3-main/docs/research/plan-b2-jwt-comisiones-activas.md`

**Esfuerzo estimado:** 1-2 días de trabajo mecánico, **bloqueado por DI UTN**.

### 3.3. Validación intercoder κ ≥ 0.70

**Estado:** El clasificador N4 funciona, pero la categorización en niveles N1-N4 **no está validada estadísticamente contra etiquetado humano**. Sin esto la tesis no es defendible.

**Qué falta:**
- Coordinar 2 docentes UTN para etiquetar manualmente:
  - 200 eventos estratificados (50 por nivel N1-N4) — Protocolo A
  - 50 episodios cerrados en 3 categorías de apropiación — Protocolo B
- Calcular Cohen's κ — debe dar ≥ 0.70 (umbral del ADR-046)
- Si pasa, activar feature flags:
  - `socratic_compliance` (ADR-044): postprocesador del tutor
  - `lexical_anotacion_override` (ADR-045): override léxico por contenido

**Esfuerzo estimado:** ~25-30 horas por docente × 2 docentes = ~50-60h de trabajo humano externo.

**Dependencia externa:** **Sí.** Cuello de botella académico más grande del piloto.

### 3.4. Re-clasificar 106 classifications históricas

**Estado:** En la DB del piloto real (no en dev) hay 106 classifications con `classifier_config_hash` legacy, anteriores al bump a `LABELER_VERSION=1.2.0`. La idempotencia ya está cumplida.

**Qué falta:**
- Correr batch worker sobre la DB del piloto real
- Verificar consistencia de hashes nuevos

**Esfuerzo estimado:** 1 hora de ejecución, una vez que hay DB real disponible.

### 3.5. Hashes ceremoniales del piloto

**Estado:** Hoy el frontend del alumno tiene `curso_config_hash = "c".repeat(64)` y `classifier_config_hash = "d".repeat(64)` como fallback ceremonial. **Avance hecho hoy:** bootstrap real implementado via `GET /api/v1/comisiones/{id}/config-hashes` (commit anterior), pero el fallback hardcoded se mantiene como red de seguridad.

**Qué falta:**
- Pruebas de carga sobre el endpoint nuevo
- Eliminar el fallback hardcoded una vez que el bootstrap esté estable en producción
- En piloto-2, el `curso_config_hash` debería incluir más campos (rúbrica firmada, versión del curso, etc.)

**Esfuerzo estimado:** 1 día.

### 3.6. `integrity-attestation-service` en VPS UTN

**Estado:** Puerto `:8012` siempre 503 en dev local. El stream Redis `attestation.requests` acumula eventos sin consumer.

**Qué falta:**
- Provisionar VPS institucional UTN
- Desplegar `integrity-attestation-service` con su clave Ed25519
- Configurar drenaje del stream `attestation.requests`
- Backup del archivo append-only `attestations-YYYY-MM-DD.jsonl` (es evidencia criptográfica crítica)

**Esfuerzo estimado:** 1 semana incluyendo coordinación de infra.

**Dependencia externa:** **Sí.** Requiere provisión de infra institucional.

### 3.7. Backup strategy real

**Estado:** Existen `scripts/backup.sh` y `restore.sh` pero corren manuales en dev. **No hay backup automático ni en dev ni en prod.**

**Qué falta:**
- `pg_basebackup` + WAL archiving continuo a S3 / MinIO institucional
- Snapshot semanal de MinIO con artefactos pedagógicos
- Procedimiento de DR (Disaster Recovery) probado, restauración en <4h
- Backup específico del `attestations-*.jsonl` (es append-only criptográfico, perderlo invalida evidencia)

**Esfuerzo estimado:** 3-5 días + testing.

### 3.8. Rotación de secrets

**Estado:** `BYOK_MASTER_KEY` vive como env var del `ai-gateway`. Si se pierde, todas las BYOK keys del piloto quedan inservibles.

**Qué falta:**
- Vault o KMS (AWS/GCP/Azure) institucional para `BYOK_MASTER_KEY`
- Procedimiento de rotación documentado (los 5 pasos del ADR-038)
- Audit log de quién accede a secrets

**Esfuerzo estimado:** 1 semana + audit.

### 3.9. Auditoría de seguridad externa

**Estado:** Nadie de afuera revisó el código. La cadena CTR + RLS + BYOK son críticos académicamente.

**Qué falta:**
- Pentest del `api-gateway`
- Audit de RLS por consultora externa (¿hay leak cross-tenant no detectado?)
- Confirmación operativa de que `dev_trust_headers=True` está **OFF** en producción
- Static analysis (Bandit, Semgrep)
- Dependency vulnerability scan continuo

**Esfuerzo estimado:** 2-3 semanas + presupuesto de auditoría.

---

## 4. No bloqueantes (mejoras recomendadas, no impiden subir)

### 4.1. Branch protection en GitHub
Procedimiento documentado en `docs/BRANCH-PROTECTION.md`. Activación manual desde Settings de GitHub. **30 min.**

### 4.2. Rate limiting persistente
Hoy: `slowapi` in-memory por `X-User-Id`, 100/min. Si reinicia el `api-gateway`, los buckets se pierden. **Mejora:** migrar a Redis como backend. **1 día.**

### 4.3. Observabilidad operacional
Hoy: Grafana, Prometheus, Loki, Jaeger corren en dev pero no hay alertas configuradas. **Mejora:** dashboards por dominio + runbooks + on-call rotation. **1-2 semanas.**

### 4.4. Despliegue real (Helm + Kubernetes)
Hoy: solo `docker-compose.dev.yml`. **Mejora:** Helm chart por servicio, StatefulSets para Postgres, Argo Rollouts (ADR-015). **1-2 semanas de devops.**

### 4.5. Performance testing
Hoy: 0 load testing. Piloto con 18 alumnos. Universidad real tiene cientos. **Mejora:** k6 simulando ~500 episodios concurrentes. **1 semana.**

### 4.6. Selector dinámico de tenant en docente/alumno
Hoy: implementado en los 3 frontends. **Limitación:** el cambio fuerza `window.location.replace("/")` y pierde el contexto del browser. **Mejora:** usar router de TanStack para cambio sin reload. **2 días.**

### 4.7. CDN para frontends
Hoy: Vite dev server. **Mejora:** build optimizado servido desde CloudFront / Cloudflare + Service Worker para cache offline del banco de ejercicios. **1 semana.**

### 4.8. Test coverage formal
Hoy: 30 smoke E2E + tests unitarios. No hay reporte de cobertura. **Mejora:** target 80%, mutation testing en invariantes (CTR hash, classifier hash). **1 semana.**

---

## 5. Deuda técnica menor (no es bug, es scope deliberado)

| Item | Detalle | Cuándo |
|---|---|---|
| Typecheck errors en `CorreccionesView.tsx`, `EjerciciosView.tsx`, tests de `ExerciseListView` | Pre-existentes. No afectan runtime. Mismatch de campos `EjercicioEstado.ejercicio_id` | Migración del schema, 1 día |
| Workers `ctr-service` ocasionalmente duplicados (10 en lugar de 8) | Restarts dejan zombies | Mejorar `dev-stop-all.sh` + monitoreo |
| Reset script no borra universidades creadas dinámicamente | Preserva catálogo. Limpiar a mano con SQL | Mejorar `reset-to-seed.sh` |
| Panels resizables no persisten tamaño entre reloads | `react-resizable-panels` v4 no expone `autoSaveId` | Implementar persistencia manual via `onLayout` |
| Wizard IA: prompt puede generar campos extra | El parser rechaza con 502 | Endurecer el prompt `ejercicio_generator/v1.0.0` |
| TenantSelector limpia URL al cambiar (pierde contexto) | `window.location.replace("/")` | Migrar a router de TanStack |

---

## 6. Dependencias externas (no son código)

Estas son **responsabilidad de Alberto + equipo institucional**, no del dev:

1. **Coordinación con DI UTN**
   - Configurar realm Keycloak
   - Definir claim `comisiones_activas` en el JWT
   - Convenio LDAP read-only (condición de uso del directorio institucional)

2. **2 docentes UTN para validación κ**
   - ~25-30 horas cada uno
   - Protocolo dual (200 eventos + 50 episodios)
   - Si κ < 0.70, refinar etiquetador y repetir

3. **Provisión de infra institucional**
   - VPS para `integrity-attestation-service`
   - S3 / MinIO institucional para backups
   - Vault / KMS para `BYOK_MASTER_KEY`

4. **API keys reales por universidad**
   - Cada universidad provee sus BYOK keys (Mistral / OpenAI / Anthropic / Gemini)
   - Coordinación con áreas de IT de cada institución

5. **Auditoría de seguridad externa**
   - Pentest del api-gateway
   - Audit de RLS por consultora
   - Presupuesto institucional

6. **Defensa doctoral**
   - Coordinación con jurado
   - Submission del paper

---

## 7. Plan de cronograma recomendado

| Fase | Duración | Foco |
|---|---|---|
| **Fase 0 — Cleanup último (1 semana)** | Resolver deuda técnica menor del punto 5. Activar branch protection. Migrar rate limiting a Redis. | Equipo dev |
| **Fase 1 — Validación intercoder (4-6 semanas)** | Coordinar 2 docentes UTN. Calibrar protocolos. Etiquetar. Calcular κ. Si κ ≥ 0.70 → activar feature flags. | Alberto + 2 docentes |
| **Fase 2 — Infra institucional (3-4 semanas)** | Coordinar con DI UTN para Keycloak realm. Provisión de VPS. Despliegue de `integrity-attestation-service`. Backup strategy. | Alberto + DI UTN + devops |
| **Fase 3 — Auth real + JWT (1-2 semanas)** | Quitar `dev_trust_headers`. Wirear `keycloak-js`. Validador JWT en api-gateway. | Equipo dev |
| **Fase 4 — Auditoría externa (2-3 semanas)** | Pentest + Audit de RLS + dependency scan. | Consultora externa |
| **Fase 5 — Despliegue real (1-2 semanas)** | Helm charts. Argo Rollouts. Migración de DB del piloto al VPS. Re-clasificar las 106 históricas. | Equipo devops |
| **Fase 6 — Defensa doctoral** | Submission del paper. Defensa. | Alberto |

**Total realista a producción: 3-4 meses.**

---

## 8. Lo que **sí** está listo para mostrar mañana

El piloto, en estado actual, sirve para:

- **Demo controlada a jurado o comité doctoral**, con un dev presente para responder dudas técnicas
- **Testing por QA interno** (Neyen) sobre el flujo end-to-end
- **Captura de evidencia académica** para el paper: hashes verificables, clasificación N4, eventos CTR
- **Mostrar el modelo de aislamiento por universidad** (1 = 1 tenant, multi-institución)
- **Capturar feedback pedagógico** del tutor socrático con LLM real (BYOK)
- **Probar el flujo completo del alumno** desde la landing hasta el diagnóstico N4

Lo que **no** se debería:

- Abrir a alumnos reales sin supervisión
- Operar sin un dev disponible para responder incidentes
- Confiar en backups (no existen automatizados)
- Migrar datos de producción sin auditoría previa
- Defender doctoralmente sin completar la validación κ

---

## 9. Anexo: comandos útiles para revisión

### 9.1. Acceso al repo
```bash
git clone git@github.com:JuaniSarmiento/AI-Native-V4.git
cd AI-Native-V4
# Toda la operación vive bajo AI-NativeV3-main/
```

### 9.2. Levantar el stack local
```bash
cd AI-NativeV3-main
docker compose -f infrastructure/docker-compose.dev.yml up -d
uv sync --all-packages && pnpm install
bash scripts/migrate-all.sh
uv run python -m academic_service.seeds.casbin_policies
uv run python scripts/seed-3-comisiones.py
uv run python scripts/seed-ejercicios-piloto.py
bash scripts/dev-start-all.sh &
make dev   # 4 frontends en :5172/:5173/:5174/:5175
```

### 9.3. URLs para inspeccionar
- Landing: http://localhost:5172
- Admin: http://localhost:5173
- Docente: http://localhost:5174
- Alumno: http://localhost:5175
- Grafana: http://localhost:3000
- Jaeger: http://localhost:16686

### 9.4. Reset entre demos
```bash
bash AI-NativeV3-main/scripts/reset-to-seed.sh
```

### 9.5. Verificar integridad de un episodio
```bash
curl -X POST "http://127.0.0.1:8000/api/v1/audit/episodes/{episode_id}/verify" \
  -H "X-Tenant-Id: 7a7a143c-31f8-461b-be08-d86ac36b41a3" \
  -H "X-User-Id: 33333333-3333-3333-3333-333333333333" \
  -H "X-User-Roles: superadmin"
```

### 9.6. Documentos clave
| Documento | Para |
|---|---|
| `AI-NativeV3-main/CLAUDE.md` | Invariantes y constantes (los hashes, las versiones, los umbrales). No tocar lo de ahí sin ADR. |
| `docs/research/audita1.md` | Auditoría inicial del repo |
| `docs/research/audi2.md` | Auditoría de completitud (20 capabilities × 4 criterios) |
| `docs/research/plan-accion.md` | Plan con 26 acciones priorizadas + DAG |
| `docs/research/ppconarev.md` | Revisión paper vs implementación |
| `docs/papers/paper-draft.md` | Draft consolidado del paper doctoral |
| `AI-NativeV3-main/docs/adr/` | 49 ADRs |
| `ONBOARDING.md` | Guía para QA (Neyen) |

---

## 10. Contacto

| Rol | Responsable |
|---|---|
| Doctorando | Alberto Alejandro Cortez |
| Co-directora | Daniela Carbonari |
| Dev / repo owner | Juani Sarmiento (este informe) |
| QA | Neyen |

Cualquier duda técnica del informe se contesta con el código a la vista o consultando los documentos del anexo 9.6.
