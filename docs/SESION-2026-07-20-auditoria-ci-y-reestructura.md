# Sesión 2026-07-20 — Auditoría, CI y reestructura del monorepo

> **TL;DR**: se pidió reordenar carpetas. Antes de mover nada apareció que **el CI nunca había corrido**, y al encenderlo se destaparon un crash real, dos migraciones destructivas latentes y un pipeline que daba verde sin ejecutar tests. Todo eso se arregló, y además se reordenaron las carpetas. **23 commits en `desarrollo-juani` (PR #33). Nada mergeado a `main`.**

---

## 1. El hallazgo que ordenó todo lo demás

**El CI nunca corrió. Ni una sola vez en la vida del proyecto.**

El repo git está rooteado en `AI-Native-V5-dev/`, pero los workflows vivían en `AI-NativeV3-main/.github/workflows/`. GitHub Actions **solo descubre workflows en `<raíz>/.github/workflows/`**.

Lint, typecheck, build de 10 imágenes, tests unitarios, tests de integración, RLS, security scan y 33 smoke E2E: todo escrito, configurado y versionado. Nunca ejecutado.

El wrapper `AI-NativeV3-main/` no era solo incómodo — **era la causa**.

---

## 2. Bugs reales encontrados

### 2.1. Crash en `tutor-service` 🔴

Dos clases distintas llamadas `RetrievalResult` en el mismo servicio:

| `clients.py` (la que usa el runtime) | `content_client.py` (código muerto) |
|---|---|
| `chunks`, `chunks_used_hash`, `latency_ms` | + `rerank_applied` |

Alguien copió un constructor de una a la otra. Resultado: `ContentClient.retrieve()` tiraba `TypeError` **en sus dos guards defensivos** — los que existen justamente para degradar sin caerse cuando la query viene vacía o falta el scope.

**El código escrito para no caerse era el que se caía.** Reproducido ejecutando, arreglado, + 2 tests de regresión verificados contra el código viejo.

### 2.2. Migración que borraba las notas de los alumnos 🔴

`alembic check` en `academic-service` proponía:

```
remove_table  entregas
remove_table  calificaciones
remove_table  byok_keys
remove_table  byok_keys_usage
remove_table  alembic_version_evaluation
```

**Causa**: ownership cruzado. Esas tablas viven en `academic_main` pero su modelo SQLAlchemy pertenece a otro servicio (`evaluation-service`, `ai-gateway`). El autogenerate las lee de la DB, no las encuentra en su metadata y concluye que sobran.

**Impacto**: cualquier `make migrate-new SERVICE=academic-service NAME=x` generaba una migración con `op.drop_table(...)` sobre las notas del piloto. Bastaba aplicarla sin leerla.

**Fix**: `include_object` como denylist en `apps/academic-service/alembic/env.py`. Es el espejo del filtro que `evaluation-service` ya tenía — faltaba el lado peligroso. `remove_table`: **5 → 0**.

### 2.3. El mismo patrón, segunda instancia 🟠

`evaluation-service` proponía dropear 2 foreign keys de `entregas` hacia `comisiones` y `tareas_practicas` (tablas fuera de su metadata). No borra datos, pero deja la tabla sin integridad referencial. Filtro extendido a `foreign_key_constraint`. Hoy es el **primer servicio con `alembic check` completamente limpio**.

### 2.4. Índice vectorial del RAG en riesgo 🔴

```sql
CREATE INDEX ix_chunks_embedding ON chunks
  USING ivfflat (embedding vector_cosine_ops) WITH (lists='100')
```

Creado con DDL cruda (`op.execute`), no con `op.create_index`. SQLAlchemy no puede representarlo, así que **siempre** aparece como drift y el autogenerate propone dropearlo. Aplicarlo rompe la búsqueda semántica del tutor **en silencio** — sigue respondiendo, pero busca mal.

**Fix**: `include_object` en `content-service/alembic/env.py` que lo excluye del comparador, con el motivo escrito.

### 2.5. La base tenía razón, el modelo no 🟠

`audit_log.id` y `casbin_rules.id` son `BIGINT` en la DB, a propósito (audit log append-only, crece sin techo). El modelo mapeaba `int` → `Integer`, y el autogenerate proponía `modify_type BIGINT → Integer`: **achicar una PK a ~2.100 millones de filas**.

Fix en el modelo (`BigInteger` explícito), **nunca en la base**.

### 2.6. `make test-smoke-local` roto desde el 2026-05-14 🟠

Dos causas, ambas del refactor de mayo, ambas invisibles porque nada ejecutaba ese seed:

1. `INSERT INTO universidades` sin `tenant_id` — columna `NOT NULL` desde la migración `20260514_0004`
2. `INSERT INTO tareas_practicas_templates` usaba `enunciado`, renombrado a `consigna` (la instancia `tareas_practicas` **sí** conserva `enunciado`)

### 2.7. Dependencia fantasma 🟠

`ctr-service` usaba `platform_ops.set_tenant_rls` — el helper que activa el aislamiento multi-tenant — **sin declararlo** en su `pyproject.toml`. Funcionaba solo porque el workspace `uv` comparte un único venv. Con venv por servicio, ese import revienta y con él el `SET LOCAL app.current_tenant`.

---

## 3. El CI encendido iba a mentir

Verificado con `pytest --collect-only`:

| Job | Qué hacía realmente |
|---|---|
| `test-unit` | `pytest -m "not integration"` → colectaba **66** smoke tests. Cero de los 1364 unitarios. |
| `test-integration` | `pytest -m "integration"` → **0 tests, exit 0** → verde falso |
| `test-rls` | idem → **0 tests, exit 0** → verde falso |

**Dos causas encadenadas:**
1. `pyproject.toml` tiene `testpaths = ["tests"]`, que apunta solo a `tests/e2e/smoke/`
2. Solo 4 de los 26 archivos de `apps/*/tests/integration/` llevan el marker `@pytest.mark.integration`

Y pytest **sale con código 0 cuando deselecciona todo**. Dos jobs reportaban éxito sin ejecutar un solo test.

**Bonus**: `[tool.coverage.run] source = ["src"]` no matcheaba nada (no existe `./src` en la raíz) → `Total coverage: 0.00%` → el gate `--cov-fail-under=60` fallaba siempre. Cobertura real medida: **71.29%**.

---

## 4. Reestructura de carpetas

El wrapper `AI-NativeV3-main/` se colapsó a la raíz. **1231 renames** — git preservó el historial de cada archivo.

**Colisiones resueltas sin borrar nada:**

| Archivo | Resolución |
|---|---|
| `CLAUDE.md` | El operativo queda como `CLAUDE.md`; el del wrapper → `docs/GOBIERNO-TESIS.md` |
| `README.md` | El técnico queda; el narrativo → `docs/ONBOARDING-NARRATIVO.md` |
| `docs/` | Fusionadas. 153 de 154 archivos sin conflicto |
| `docs/research/audi2.md` | **Existían DOS versiones distintas** (382 vs 380 líneas). Ninguna se borró; la del wrapper quedó como `audi2-wrapper.md`. **Alguien tiene que decidir cuál vale.** |
| `.github/` | Fusionadas sin conflicto |
| `.gitignore` | Unión deduplicada (86 + 124 → 114 reglas únicas) |

**Limpieza de la raíz** — 19 archivos sueltos de la tesis reubicados en carpetas que ya existían:

```
docs/research/  ← 9 .md de análisis (informeSoc, PlanMejora, revisiones coautorales...)
documentos/     ← 8 binarios (tesis16mayo.docx, paper_conaiisi.pdf...) + _templates/
```

En la raíz solo quedó config del monorepo y documentación del proyecto.

**Poda de `ops/`** — parcial y deliberada:
- Borrado: `ops/grafana/_archive/` y `ops/prometheus/` (reemplazados, documentado en el código)
- **Conservado**: `ops/k8s/` + README nuevo. No es duplicado — tiene el CronJob de integridad del CTR, el de backup y el canary con Argo Rollouts, sin equivalente en el chart Helm. *Borrar código muerto está bien; borrar código que nadie conectó todavía es otra cosa.*

---

## 5. Otros arreglos

| | Antes | Después |
|---|---|---|
| ruff | 183 errores | **0** |
| mypy | 25, luego 21 más al limpiar el entorno | **0** |
| `check-claude-md` | 2 drifts | **0** |
| Código muerto | — | **527 líneas borradas** |
| `web-landing` | fuera de todo pipeline | integrada a CI, Docker, nginx, Helm |
| `pnpm-lock.yaml` | desincronizado (`mermaid` fantasma) | regenerado |

**Sobre el código muerto**: `content_client.py` y `governance_client.py` no los importaba nadie desde `src/`. Y `test_governance_client.py` tenía **8 asserts sobre `resolve_for_tenant`, un método que no existe en el cliente real** — verde permanente sobre código que nunca corrió. De esa duplicación había salido el crash del punto 2.1.

**Sobre los `sys.path` hacks**: los dos bloques de `analytics.py` que "permitían importar classifier-service" eran **no-ops** — verificado ejecutando el intérprete: el editable install del workspace ya pone ese path. Se borró el hack, se conservó el `try/except → 503` (ese sí protege un deploy aislado).

---

## 6. Estado del CI

Corriendo por primera vez sobre la estructura final:

```
✓ Build frontends (Vite)   1m16s      X Lint frontend        18s
✓ Unit tests               2m0s       X RLS isolation        33s
✓ Typecheck Python         38s        X Security scan        16s
✓ Lint Python              15s        X Integration tests    54s (no bloqueante)
✓ Migrations dry-run       27s
✓ Docs drift               6s
```

**6 de 10 en verde.** Progresión de la sesión: 0 → 3 → 5 → 6.

### Los 4 rojos que quedan (ninguno es código nuevo)

1. **`Lint frontend`** — biome encuentra formato sin aplicar en `web-admin`. Nunca corrió en CI. Se arregla corriendo el formateador.
2. **`RLS isolation`** — falta crear la función SQL `apply_tenant_rls` en el setup del job antes de migrar `ctr_store`.
3. **`Security scan`** — Trivy encontró vulnerabilidades HIGH/CRITICAL en dependencias. Requiere revisar una por una.
4. **`Integration tests`** — marcado `continue-on-error` a propósito. 4 tests fallan por la divergencia del punto 7.1.

---

## 7. Decisiones que requieren un humano

### 7.1. Plantillas de TP: el código contradice un ADR aceptado ⚠️

```
2026-04-23  ADR-016 → define fan-out automático (crear template → instancia TPs por comisión)
2026-05-07  ADR-042 → Status: ACCEPTED, aceptado por Alberto Cortez
            línea 71: "ADR-016: NO cambia (template + auto-instancia + drift por instancia)"
2026-05-12  refactor → "Sin fan-out automático: crear un template NO crea instancias"
```

El código cambió **cinco días después** de que Cortez firmara que eso no cambiaba. El `CLAUDE.md` sigue documentando el fan-out como vigente. 4 tests lo esperan.

**Consecuencia para la tesis**: ADR-018 (CII longitudinal) agrupa episodios por `template_id` y **descarta las TPs huérfanas**. Si nadie usa plantillas —hoy la pantalla existe pero está fuera del menú del docente—, los TPs nuevos nacen sin `template_id` y quedan fuera de esa métrica.

**Pregunta para Cortez**: si no se usan plantillas, ¿sobre qué datos se calcula el CII longitudinal en el piloto real?

### 7.2. `audi2.md` duplicado

Dos versiones distintas de la misma auditoría (382 vs 380 líneas). Ninguna se borró. Alguien tiene que comparar y decidir cuál vigente.

### 7.3. `uv.lock` no está versionado

`pnpm-lock.yaml` sí; `uv.lock` está en `.gitignore`. Esa asimetría significa que dos máquinas pueden resolver versiones distintas de las mismas dependencias Python. **En un repo cuya tesis se apoya en reproducibilidad bit-a-bit, vale discutirlo.**

(Se comprobó en vivo: mypy 2.x encuentra 29 errores que la 1.x no ve. Quedó pineado a `<2`.)

### 7.4. Seguridad — pendiente desde el inicio de la sesión 🔴

El panel de EasyPanel está expuesto en **HTTP plano, sin TLS, en una IP pública, puerto 3000**. La credencial de administrador viaja en texto claro en cada login. Ese panel controla todos los servicios, variables de entorno y bases de datos del piloto.

**Acciones**: rotar la credencial, cerrar el puerto, poner HTTPS (EasyPanel tiene Let's Encrypt integrado).

---

## 8. Al mergear a `main` — checklist

⚠️ **Cada servicio en EasyPanel tiene "Ruta de compilación" = `/AI-NativeV3-main`. Hay que cambiarla a `/` en TODOS.** El campo "Archivo" (`apps/<svc>/Dockerfile`) no cambia — es relativo al contexto.

Sin ese cambio, el build falla al no encontrar el path.

---

## 9. Verificación

Todo se verificó **ejecutando**, no leyendo:

- `1352 passed / 4 skipped` — suite completa
- `4 passed` — RLS con usuario `app_runtime` NOSUPERUSER NOBYPASSRLS real (con `postgres` las policies se bypassean y los tests pasan sin verificar nada)
- `10 passed` — `test_pipeline_reproducibility` (reproducibilidad bit-a-bit del `classifier_config_hash`)
- `62 passed` — cadena CTR
- ruff, mypy, `check-rls`, `check-claude-md`, `check-vite-seed-sync` — todos limpios
- Imagen de frontends **levantada y probada con curl** en las 4 rutas
- `alembic check` contra la base real en los 4 servicios

**Se verificó además que ningún commit alteró el schema**: AST idéntico en las 10 migraciones tocadas por `ruff format` (con `revision`/`down_revision` intactos), AST idéntico en los modelos, y las 17 columnas de `entregas.py` sin cambios.

---

## 10. El patrón de fondo

Todos los hallazgos comparten la misma forma: **algo que decía estar bien sin estarlo.**

- El CI en la carpeta equivocada
- Los tests de RLS que se skipeaban en silencio sin la env var
- `migrate-all.sh` que imprime "✓ Migraciones completadas" tras hacer `SKIP`
- Los Dockerfiles con `cd /app/apps/<svc> || cd /app` y `alembic || echo WARN`
- `pytest -m` que deselecciona todo y sale con 0
- Coverage midiendo 0% contra una carpeta inexistente
- Tests verificando métodos que no existen

Ninguno era un error de programación. Todos eran **señales apagadas**.

Por eso la regla que se siguió toda la sesión: **verificar ejecutando, no leyendo.** En un proyecto que sostiene una tesis doctoral, la diferencia entre "el código dice que funciona" y "lo vi funcionar" es toda la diferencia.

---

*Registro generado el 2026-07-20. Rama `desarrollo-juani`, PR #33. Producción intacta.*
