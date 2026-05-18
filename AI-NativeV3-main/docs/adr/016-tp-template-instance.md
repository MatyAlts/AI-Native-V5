# ADR-016 — TareaPractica: plantilla (Materia+Período) + instancia (Comisión) con tracking de drift

- **Estado**: Propuesto
- **Fecha**: 2026-04-23
- **Deciders**: Alberto Alejandro Cortez, director de tesis
- **Tags**: datos, académico, tesis, piloto-UNSL, CTR, casbin

## Contexto y problema

El piloto UNSL tiene una cátedra con **múltiples comisiones** de la misma Materia y Período (típicamente 2–4 comisiones de "Programación 1 — 2026-S1"). Hoy la entidad `TareaPractica` (en adelante **TP**) vive **a nivel de Comisión**:

- Modelo: `apps/academic-service/src/academic_service/models/operacional.py:154-217`.
- FK: `TareaPractica.comision_id → comisiones.id`.
- Unique: `(tenant_id, comision_id, codigo, version)`.
- CRUD: `apps/academic-service/src/academic_service/routes/tareas_practicas.py` + service + schema + migración `20260421_0002_add_tareas_practicas.py`.

**Problema operativo**: si una cátedra quiere dar "TP1 — Recursión" a sus tres comisiones, el docente lo carga tres veces (una por comisión) o lo duplica con scripts. Cualquier corrección de un typo en el enunciado obliga a repetir la edición N veces. Si dos comisiones terminan con versiones sutilmente distintas, la comparación entre cohortes se vuelve ambigua.

**Problema para la tesis**: la clasificación CTR agrupa episodios por `problema_id` (= `TareaPractica.id`). Si el mismo TP lógico vive con 3 IDs distintos, los estudios longitudinales por TP tienen que aplicar mapping manual "TP1 de la comisión A = TP1 de la comisión B", que es frágil.

**Problema de integridad**: `reglas.md` RN-046 exige que `curso_config_hash` (ADR-009) sea **por-Comisión** — cada comisión puede tener su prompt/profile/classifier-config propio. Compartir TP no puede contradecir eso.

Fuerzas en juego:

1. Compartir enunciado entre comisiones **sin** romper la cadena CTR (`problema_id` estable por episodio) ni el `curso_config_hash` per-Comisión (ADR-009 / RN-046).
2. Preservar inmutabilidad de versiones publicadas (status quo: `update` rechaza 409 si `estado != draft`; `new_version` crea fila con `version+1` y `parent_tarea_id`).
3. Permitir que un docente **diverja** (override el enunciado o la rúbrica en una comisión particular) sin perder el vínculo semántico con la fuente original. A esto lo llamamos **drift**.
4. Respetar Casbin: el recurso `tarea_practica:CRUD` existe en `apps/academic-service/src/academic_service/seeds/casbin_policies.py` (67–70, 107–110, 121–124, 133, 137). Cualquier cambio es un cambio de superficie de autorización y rompería el test de matriz mencionado en `reglas.md:294-296`.
5. No romper el contrato del CTR (`EpisodioAbiertoPayload.problema_id` sigue siendo UUID) ni el de `tutor_core.open_episode` que valida 6 condiciones sobre la TP (existe / tenant / comisión / estado / fechas inicio-fin).

## Drivers de la decisión

- **D1** — Una única fuente canónica editable por la cátedra, con versionado (alineado con ADR-010 append-only).
- **D2** — Preservar `problema_id` como UUID estable de la **instancia** (no del template) para no romper la cadena CTR histórica (RN-034, RN-036, RN-039, RN-040).
- **D3** — Permitir personalización por comisión (drift) con rastreo explícito, no silencioso.
- **D4** — Minimizar BC-break en `POST /api/v1/tareas-practicas` y en `TareaPracticaCreate` del frontend (`apps/web-teacher/src/lib/api.ts:297-306`).
- **D5** — Mantener la superficie Casbin predecible (el test de matriz declara el count actual). Cualquier recurso nuevo debe ser explícito en las policies.
- **D6** — `curso_config_hash` **no cambia su naturaleza**: sigue viviendo en `Comision` (RN-046). El template NO lo redefine.

## Opciones consideradas

### Opción A — Refactor limpio: mover `comision_id` a `materia_id+periodo_id` en `TareaPractica`

Reemplazar la FK `comision_id` por `(materia_id, periodo_id)` directamente en `tareas_practicas`. El CTR referenciaría el mismo `problema_id` para episodios de las 3 comisiones (pues la TP es una sola fila).

Ventajas:
- Schema simple. Una sola tabla.
- Cero duplicación de texto.

Desventajas que la descartan:
- **Rompe `tutor_core._validate_tarea_practica`**: hoy valida `tarea.comision_id == comision_id` (condición 3 de las 6 validaciones, `tutor_core.py:443`). Habría que rediseñar ese contrato y su test `test_open_episode_tarea_practica_validation.py`.
- **Rompe `Episode.comision_id ↔ curso_config_hash`** a nivel semántico: si dos comisiones con configs distintas comparten problema, los episodios del CTR arrastran `curso_config_hash` distintos para la **misma fila de TP** — interpretable, pero destruye la simetría "una TP publicada es un objeto con un único conjunto de config aplicable".
- **Drift no modelable**: si la comisión B necesita bajar el peso del TP de 0.3 → 0.2 porque está fuera de fase, no hay dónde guardarlo. Se termina creando una TP "shadow" rompiendo la premisa de la opción.
- Migración destructiva sobre `tareas_practicas` (cambia la forma del unique `(tenant_id, comision_id, codigo, version)`). Todos los tests de `test_tareas_practicas_crud.py` y `test_bulk_import.py` se rompen.

### Opción B — Solo UI: duplicar TP en N comisiones al crear, mantener schema

El botón "Nuevo TP" en `apps/web-teacher/src/views/TareasPracticasView.tsx:197-202` abre un modal con checkboxes "aplicar a comisiones X/Y/Z". El backend crea N filas. Cero cambio de schema.

Ventajas:
- Zero-risk en el backend. Cero migración.
- Contratos CTR, Casbin y tutor quedan intactos.

Desventajas que la descartan:
- **No resuelve D1** (no hay fuente canónica editable): cambiar un typo sigue siendo N PATCHes.
- Las N filas divergen en el momento cero y no hay forma de rastrear que "vinieron de la misma creación". El estudio cross-cohorte sigue siendo manual.
- Cada "new_version" hay que hacerlo N veces manualmente — el dolor operativo que motivó el ticket no desaparece.

### Opción C — Plantilla + instancia con tracking de drift (elegida)

Nueva entidad `TareaPracticaTemplate` anclada a `(materia_id, periodo_id)` como fuente canónica. `TareaPractica` existente gana FK nullable `template_id` y flag `has_drift`. Al crear un template, el sistema auto-instancia una TP en **cada** comisión de esa materia+periodo (al momento de creación del template). Editar la instancia marca `has_drift=true` pero mantiene el link. Versionar el template crea `TareaPracticaTemplate v+1` y (opcionalmente, según decisión del docente en UI) re-instancia en las comisiones que no hayan drifteado.

Ventajas (D1, D2, D3, D4, D6):
- `problema_id` sigue apuntando a la **instancia** → cadena CTR estable, `curso_config_hash` per-Comisión intacto, zero migración del CTR.
- Drift explícito (`has_drift` booleano) + link preservado (`template_id` NOT NULL cuando viene del template).
- La API `POST /api/v1/tareas-practicas` sigue funcionando para crear TPs "huérfanas" (sin template) — compatible con tests existentes y con docentes que no quieran adoptar templates.

Desventajas (trade-offs en "Consecuencias"):
- Superficie Casbin nueva (`tarea_practica_template`): +12 policies mínimo.
- Complejidad de re-instanciación cuando se crea una comisión **nueva** en una materia+período con templates ya publicados (decisión diferida en "Consecuencias neutras").
- Dos estados de "versionado": la `TareaPractica` ya versionaba vía `parent_tarea_id`; el template agrega su propio `parent_template_id`. Mental model duplicado — hay que documentarlo.

### Opción D — Solo template, `TareaPractica` deja de ser tabla y se vuelve vista materializada

Descartada al vuelo: rompe FK `episodes.problema_id` (que no existe como FK dura porque son bases separadas por ADR-003, pero el contrato lógico sí), y la cadena CTR necesita un UUID persistente que no puede ser reasignado por la vista.

## Decisión

**Opción C — `TareaPracticaTemplate` como fuente canónica + `TareaPractica` como instancia por comisión con `template_id` + `has_drift`.**

### Estructura (diagrama textual)

```
Comision (1) ─┐
              │  FK comision_id (existente, inmutable)
              ▼
         TareaPractica (instancia, existente, gana template_id + has_drift)
              ▲
              │  FK template_id (nullable — NULL = TP huérfana, pre-ADR-016)
              │
TareaPracticaTemplate (nuevo, fuente canónica)
        ▲
        │  FK (materia_id, periodo_id)  ← N comisiones comparten una (materia, periodo)
        │
   Materia ─── Periodo
```

### Flujo operativo

1. **Docente crea template** (`POST /api/v1/tareas-practicas-templates`) con `materia_id + periodo_id + codigo + ...`.
2. Servicio auto-instancia `TareaPractica` en **cada** `Comision WHERE materia_id=X AND periodo_id=Y` con `estado='draft'`, `template_id=<nuevo template>`, `has_drift=false`. El `codigo` se hereda del template; el constraint `uq_tarea_codigo_version` lo protege por comisión.
3. **Docente edita instancia directamente** (PATCH existente): si `template_id IS NOT NULL` y el cambio toca un campo "canónico" (enunciado, titulo, inicial_codigo, rubrica, peso, fechas), el servicio setea `has_drift=true`. El campo sigue siendo mutable si `estado='draft'`; 409 si `published/archived`, sin cambio respecto al comportamiento actual.
4. **Docente versiona el template** (`POST /api/v1/tareas-practicas-templates/{id}/new-version`): crea `TareaPracticaTemplate v+1` en estado `draft`. UI presenta flag booleano "re-instanciar en comisiones sin drift": si true, se crea **una nueva versión** (`TareaPractica.version+1`, `parent_tarea_id=<instancia vieja>`) en cada comisión cuya instancia actual tenga `has_drift=false`. Las comisiones con drift quedan como estaban (la cadena CTR no se mueve).
5. **Publicar template** (`POST /api/v1/tareas-practicas-templates/{id}/publish`): NO publica automáticamente las instancias — la publicación de instancia sigue siendo una decisión del docente de esa comisión (para no saltearse su workflow local). El template pasar a `published` sirve como "la cátedra dio luz verde".

### Schema detallado

#### Nueva tabla `tareas_practicas_templates`

```sql
CREATE TABLE tareas_practicas_templates (
    id                 UUID PRIMARY KEY,
    tenant_id          UUID NOT NULL,
    materia_id         UUID NOT NULL REFERENCES materias(id)   ON DELETE RESTRICT,
    periodo_id         UUID NOT NULL REFERENCES periodos(id)   ON DELETE RESTRICT,

    codigo             VARCHAR(20)  NOT NULL,
    titulo             VARCHAR(200) NOT NULL,
    enunciado          TEXT         NOT NULL,
    inicial_codigo     TEXT         NULL,
    rubrica            JSONB        NULL,
    peso               NUMERIC(5,4) NOT NULL DEFAULT 1.0,
    fecha_inicio       TIMESTAMPTZ  NULL,
    fecha_fin          TIMESTAMPTZ  NULL,

    estado             VARCHAR(20)  NOT NULL DEFAULT 'draft',  -- draft|published|archived
    version            INTEGER      NOT NULL DEFAULT 1,
    parent_template_id UUID         NULL REFERENCES tareas_practicas_templates(id) ON DELETE RESTRICT,

    created_by         UUID         NOT NULL,
    created_at         TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at         TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    deleted_at         TIMESTAMPTZ  NULL,

    CONSTRAINT uq_template_codigo_version
        UNIQUE (tenant_id, materia_id, periodo_id, codigo, version),
    CONSTRAINT ck_template_estado CHECK (estado IN ('draft','published','archived')),
    CONSTRAINT ck_template_peso   CHECK (peso >= 0 AND peso <= 1),
    CONSTRAINT ck_template_version CHECK (version >= 1)
);

CREATE INDEX ix_template_tenant_id            ON tareas_practicas_templates(tenant_id);
CREATE INDEX ix_template_materia_periodo      ON tareas_practicas_templates(tenant_id, materia_id, periodo_id);
CREATE INDEX ix_template_parent               ON tareas_practicas_templates(parent_template_id);
CREATE INDEX ix_template_deleted_at           ON tareas_practicas_templates(deleted_at);

-- RLS obligatorio (RN-001)
SELECT apply_tenant_rls('tareas_practicas_templates');
```

#### Cambios sobre `tareas_practicas` (ALTER TABLE)

```sql
ALTER TABLE tareas_practicas
    ADD COLUMN template_id UUID NULL
        REFERENCES tareas_practicas_templates(id) ON DELETE RESTRICT,
    ADD COLUMN has_drift   BOOLEAN NOT NULL DEFAULT false;

CREATE INDEX ix_tareas_practicas_template_id ON tareas_practicas(template_id);

-- Invariante: si has_drift=true entonces template_id debe no ser NULL
-- (no tiene sentido drift sin template de referencia)
ALTER TABLE tareas_practicas
    ADD CONSTRAINT ck_tp_drift_needs_template
    CHECK (has_drift = false OR template_id IS NOT NULL);
```

Notas:
- Se **mantiene** `uq_tarea_codigo_version (tenant_id, comision_id, codigo, version)` — la instancia sigue siendo única por comisión. Cuando el auto-instanciador crea N filas, todas tienen el mismo `codigo` pero distinto `comision_id`, por lo que no hay colisión.
- Se **mantiene** `parent_tarea_id` (FK self) y `version` de la instancia. Se mantiene append-only conceptual (ADR-010) en la cadena de instancias.

### Migration strategy

Migración `20260423_0001_add_tareas_practicas_templates.py` (next Alembic rev después de `20260422_0001`):

```
down_revision = "20260422_0001"
revision = "20260423_0001"
```

Orden de operaciones en `upgrade()`:

1. `op.create_table("tareas_practicas_templates", ...)` con los indices + check constraints del schema.
2. `op.execute("SELECT apply_tenant_rls('tareas_practicas_templates')")`.
3. `op.add_column("tareas_practicas", "template_id", ...nullable=True)`.
4. `op.add_column("tareas_practicas", "has_drift", ...nullable=False, server_default=sa.false())`.
5. `op.create_index("ix_tareas_practicas_template_id", ...)`.
6. `op.create_check_constraint("ck_tp_drift_needs_template", "tareas_practicas", "has_drift = false OR template_id IS NOT NULL")`.
7. **Auto-promoción (opcional, gated por env `AUTO_PROMOTE_UNIQUE_TPS=1`)**: para cada TP existente, agrupar por `(tenant_id, materia_id, periodo_id, codigo)` vía JOIN con `comisiones`. Si el grupo tiene una sola TP lógica compartida (mismo enunciado hash SHA-256, mismo titulo, etc.), crear un template con esos campos y backfillear `tareas_practicas.template_id` de todas las filas del grupo a ese template con `has_drift=false`. Si el grupo tiene variaciones de enunciado entre comisiones, elegir el más reciente como fuente del template y marcar las otras con `has_drift=true`. **Por defecto este paso se desactiva** — los TPs existentes del piloto quedan como "huérfanos" (`template_id=NULL, has_drift=false`) y el docente decide si promoverlos manualmente.

`downgrade()`: invierte con `op.drop_constraint`, `op.drop_column`, `op.drop_table`. La auto-promoción NO se revierte (los templates creados sobreviven al downgrade como filas huérfanas si se volvió a correr up).

**Importante sobre seeds**: `scripts/seed-3-comisiones.py:211` y `scripts/seed-demo-data.py:416` usan un `PROBLEMA_ID` constante para generar CTR events — **no insertan filas en `tareas_practicas`**. Por lo tanto el seed no necesita cambios para que la migración sea segura. Los únicos escritores actuales son tests (`test_tareas_practicas_crud.py`, `test_bulk_import.py`) y el docente interactivamente via web-teacher.

### Cambios en código (vista alto nivel)

#### Models (`apps/academic-service/src/academic_service/models/operacional.py`)

- Nueva clase `TareaPracticaTemplate(Base, TenantMixin, TimestampMixin)` con FKs a `materias.id` y `periodos.id`, unique `(tenant_id, materia_id, periodo_id, codigo, version)`, relationship bidireccional con `TareaPractica`.
- `TareaPractica` gana `template_id: Mapped[uuid.UUID | None]` y `has_drift: Mapped[bool]`.

#### Schemas (`apps/academic-service/src/academic_service/schemas/tarea_practica_template.py` — nuevo)

- `TareaPracticaTemplateCreate(materia_id, periodo_id, codigo, titulo, enunciado, ...)`.
- `TareaPracticaTemplateOut(..., id, tenant_id, estado, version, parent_template_id, created_by, created_at)`.
- `TareaPracticaTemplateUpdate` (solo campos editables; estado mutable vía endpoints dedicados).
- `TareaPracticaOut` (existente) gana `template_id: UUID | None = None` y `has_drift: bool = False`.

#### Service (`apps/academic-service/src/academic_service/services/tarea_practica_template_service.py` — nuevo)

- `create(data, user)`: crea template + itera `SELECT id FROM comisiones WHERE tenant_id=? AND materia_id=? AND periodo_id=?` + inserta `TareaPractica` por cada comisión con `template_id=<nuevo>`, `has_drift=false`, `estado='draft'`. Emite audit log `tarea_practica_template.create` + N `tarea_practica.create_from_template`.
- `publish(template_id, user)`: marca template como `published`. NO publica instancias.
- `archive(template_id, user)`: marca template como `archived`. NO archiva instancias.
- `new_version(template_id, patch, user, reinstance_non_drifted: bool)`: crea `Template v+1` en draft; si `reinstance_non_drifted=true`, para cada instancia con `has_drift=false` crea una nueva versión de la `TareaPractica` con `version+1`, `parent_tarea_id=<instancia vieja>`, `template_id=<nuevo template>`, `has_drift=false`. Las instancias con `has_drift=true` quedan apuntando al template viejo (decisión consciente: drift bloquea auto-upgrade).
- `list_instances(template_id)`: devuelve las instancias vigentes y su estado/drift para la UI.

#### Service existente — cambios sobre `TareaPracticaService`

- `update(id, data, user)`: si `obj.template_id IS NOT NULL` y el patch toca campos canónicos, setear `obj.has_drift = true` **antes** del flush. Agregar al audit log un campo `"drift_triggered": true` cuando corresponda.
- `new_version(parent_id, patch, user)`: si el parent tenía `template_id`, el hijo hereda `template_id` y hereda `has_drift` (para no "lavar" drift creando versión). Si el docente quiere "volver al template", endpoint dedicado `POST /tareas-practicas/{id}/resync-to-template` (scope opcional, ver Tasks).
- `create` (docente crea TP sin template): preserva comportamiento actual, `template_id=NULL`, `has_drift=false`.

#### Endpoints (`apps/academic-service/src/academic_service/routes/tareas_practicas_templates.py` — nuevo)

```
POST   /api/v1/tareas-practicas-templates
GET    /api/v1/tareas-practicas-templates
GET    /api/v1/tareas-practicas-templates/{id}
PATCH  /api/v1/tareas-practicas-templates/{id}
DELETE /api/v1/tareas-practicas-templates/{id}
POST   /api/v1/tareas-practicas-templates/{id}/publish
POST   /api/v1/tareas-practicas-templates/{id}/archive
POST   /api/v1/tareas-practicas-templates/{id}/new-version
GET    /api/v1/tareas-practicas-templates/{id}/instances
GET    /api/v1/tareas-practicas-templates/{id}/versions
```

Todas guardadas por `require_permission("tarea_practica_template", "<action>")`.

Endpoints TP existentes **sin cambios en contrato** (solo agregan dos campos opcionales en respuesta).

#### Casbin

Agregar a `apps/academic-service/src/academic_service/seeds/casbin_policies.py` un bloque `tarea_practica_template:CRUD` paralelo al de `tarea_practica:CRUD`, para los 3 roles con escritura (superadmin, docente_admin, docente) y con `read` para estudiante y `tutor_service`. +12 policies mínimo (4 acciones × 3 roles con escritura). El count pasa de 92 → 104 (aprox.); actualizar el histórico en `reglas.md:296`.

Justificación de "recurso separado" vs. "permisos transitivos por materia": el recurso separado es consistente con la filosofía del sistema (cada entidad del dominio es su propio objeto Casbin), y permite revocar el permiso de templates sin afectar TPs.

#### Contratos TS (`apps/web-teacher/src/lib/api.ts`)

- Agregar `TareaPracticaTemplate`, `TareaPracticaTemplateCreate`, `TareaPracticaTemplateUpdate`, `TareaPracticaTemplateVersionRef`, `TareaPracticaInstancesResponse`.
- Extender `TareaPractica` con `template_id: string | null` y `has_drift: boolean`.
- Agregar `tareasPracticasTemplatesApi` con `list`, `get`, `create`, `update`, `delete`, `publish`, `archive`, `newVersion`, `versions`, `instances`.
- **No romper** shapes existentes: `TareaPracticaCreate` sigue exigiendo `comision_id` para el caso "TP huérfana".

#### UI `web-teacher`

- Nueva vista `TemplatesView.tsx` a nivel Materia+Período (ruta actual es a nivel Comisión → necesita un contexto "planner de cátedra").
- `TareasPracticasView.tsx` muestra badge "derivado de template" cuando `template_id !== null` y badge "drifted" cuando `has_drift === true`. El texto "(derivado)" existente (`TareasPracticasView.tsx:360`) se refactoriza a `(drift del template XYZ)`.
- Al editar una instancia con template, mostrar warning "Editar este TP desconectará la sincronización con el template. ¿Continuar?" — la confirmación es opt-in pero el docente puede ignorarla (el backend igual marca drift).

#### Tutor `_validate_tarea_practica`

**NO cambia**. Las 6 condiciones (existe, tenant, comision, estado=published, fecha_inicio, fecha_fin) aplican a la **instancia**, que sigue teniendo `comision_id` y estado publicado por comisión. `problema_id` del evento `EpisodioAbierto` sigue apuntando a la instancia — ni el CTR ni el classifier necesitan saber que hay un template arriba. Esto es un beneficio grande de la Opción C.

## Consecuencias

### Positivas

- **Edición canónica única**: cambio un typo en el template, re-instancio con un click en las comisiones sin drift. Gran ROI operativo.
- **CTR-safe**: `problema_id` sigue siendo la instancia → RN-034, RN-036, RN-038, RN-039, RN-040 intactas; cadena criptográfica no se toca; migración CTR = 0 líneas.
- **`curso_config_hash` intacto**: RN-046 preservado. Cada comisión sigue aportando su `curso_config_hash` en `Episode.opened_at` sin interferencia del template.
- **Drift rastreado**: `has_drift=true` es queryable → paneles de "qué comisiones divergieron del estándar de cátedra" para tesis y dashboards.
- **Backwards compatible**: TPs pre-ADR-016 quedan con `template_id=NULL, has_drift=false` y todo sigue funcionando; los tests `test_tareas_practicas_crud.py` no se modifican (pero hay que ajustar mocks para el campo nuevo, ver Tasks).
- **Versioning doble coherente con ADR-010**: el template tiene su propia cadena `parent_template_id` (fuente canónica), la instancia sigue con `parent_tarea_id` (snapshot vigente por comisión). Append-only conceptual se conserva: publicados no se editan, se versionan.

### Negativas / trade-offs

- **Casbin superficie crece**: +12 policies, nuevo recurso `tarea_practica_template`. Requiere actualizar el test de matriz y `reglas.md:296` (count histórico). Riesgo medio de regresión en `test_casbin_matrix.py`.
- **`tutor_service` NO necesita permisos sobre templates**, pero hay que declararlo explícitamente en el seed (omitirlo es lo mismo, pero documentar es mejor).
- **Drift no es transitivo hacia versiones**: si la instancia A v1 tiene `has_drift=true` y el docente crea v2 vía `new_version`, la v2 hereda drift. No hay UI "desdriftear". Mitigación: endpoint opcional `resync-to-template` en fase posterior.
- **Auto-instanciación implica N escrituras en la misma transacción**: para 4 comisiones = 4 INSERTs + 4 audit logs + 1 template. Aceptable (se espera piloto con ≤ 4 comisiones/materia), pero para una universidad con 40 comisiones/materia el endpoint create podría tardar >1s. Mitigación: hacer el fan-out asíncrono vía bus es una evolución futura, no bloquea F-actual.
- **Comisiones creadas DESPUÉS del template**: la auto-instanciación ocurre en el `create` del template. Una comisión creada tres días después en la misma (materia, período) NO tiene automáticamente la TP. Decisión: **lazy-instantiate on demand** — endpoint `POST /api/v1/comisiones/{id}/sync-templates` que el docente llama manualmente. Alternativa descartada (trigger en `ComisionService.create`): acopla dominios y es impredecible. Documentado en la UI como "Nueva comisión: no olvidar sincronizar TPs de cátedra".
- **Conflicto codigo con TP huérfanas**: si la comisión tiene ya una `TP` con `codigo='TP1'` (sin template) y se crea un template con `codigo='TP1'` para esa materia+período, la auto-instanciación en esa comisión específica explota contra `uq_tarea_codigo_version`. Mitigación en el service: detectar colisión antes del INSERT, elegir estrategia (skip / error / rename a `TP1-T`). Recomendado: error 409 al crear template con `detail` listando comisiones conflictivas — el docente resuelve manualmente.
- **Soft delete en cascada**: borrar un template (soft) NO borra las instancias (sería destruir evidencia CTR). El endpoint `DELETE /tareas-practicas-templates/{id}` solo marca el template. La instancia queda "huérfana-con-link-muerto" — benigno, pero el `list_versions` del template debe filtrar `deleted_at IS NULL` para no confundir al docente.
- **ADR-009 curso_config_hash**: el template **no contribuye** al hash. Eso es una decisión consciente — aporta aún más peso a la interpretación "la configuración del curso vive en la Comisión, no en el enunciado del problema". Si en el futuro se quisiera incluir el template como parte del hash (para que reclasificar cuando cambia el enunciado del problema fuese válido), sería un ADR nuevo. Por ahora, cambiar el enunciado del template (via new_version) **no dispara reclasificación CTR** — coherente con ADR-010 append-only: lo que se publicó se queda como se clasificó.

### Neutras

- **RN-039/RN-040 (integridad CTR)**: no se afectan. El DLQ y el integrity checker operan sobre `Events` y `Episodes`, que no tocan `tareas_practicas_templates`.
- **bulk_import**: se puede agregar `tareas_practicas_templates` a `SUPPORTED_ENTITIES` en `apps/academic-service/src/academic_service/services/bulk_import.py:61-69` en una iteración posterior; no es gate de esta decisión.
- **web-student y tutor UI**: no cambia nada. El estudiante nunca ve "template" — ve el TP de su comisión.
- **Retroactividad de drift**: si se habilita `AUTO_PROMOTE_UNIQUE_TPS=1` en la migración, los TPs que difieren entre comisiones arrancan con `has_drift=true` desde el día 0, lo cual es la semántica correcta.

## API BC-breaks

Ninguno. `TareaPracticaCreate` sigue requiriendo `comision_id`. `TareaPracticaOut` agrega dos campos opcionales con defaults (`template_id: null`, `has_drift: false`) → los consumers que no los conozcan siguen deserializando bien. Nuevos endpoints en namespace `/api/v1/tareas-practicas-templates` no compiten con los existentes.

## Tasks de implementación (orden sugerido)

1. **Alembic**: crear `apps/academic-service/alembic/versions/20260423_0001_add_tareas_practicas_templates.py` con `down_revision="20260422_0001"`. Schema + indices + RLS + ALTER TABLE + CHECK constraint. `downgrade()` completo. **No** activar auto-promoción por default.
2. **Modelo SQLAlchemy**: agregar `TareaPracticaTemplate` en `operacional.py`; extender `TareaPractica` con `template_id` y `has_drift` + la relationship. Exportar en `academic_service/models/__init__.py`.
3. **Schemas Pydantic**: crear `schemas/tarea_practica_template.py` con Create/Update/Out/VersionRef. Extender `TareaPracticaOut` con los dos campos nuevos.
4. **Repositorio**: agregar `TareaPracticaTemplateRepository` en `repositories/__init__.py`.
5. **Service**: `services/tarea_practica_template_service.py` con métodos `create/get/list/update/publish/archive/new_version/list_instances/soft_delete/list_versions`. Tests unitarios en `tests/integration/test_tareas_practicas_templates_crud.py` usando el mismo patrón mock-based de `test_tareas_practicas_crud.py`.
6. **Update de `TareaPracticaService.update`**: setear `has_drift=true` cuando se edita instancia con `template_id` y el campo cambia. Actualizar `test_tareas_practicas_crud.py` existente con casos para drift.
7. **Endpoints**: `routes/tareas_practicas_templates.py` con los 10 endpoints listados. Registrar en `main.py`. Tests de route-level si hay (seguir patrón de `tareas_practicas.py`).
8. **Casbin seed**: agregar las 12+ policies en `seeds/casbin_policies.py`. Correr `python -m academic_service.seeds.casbin_policies` para dev; actualizar `test_casbin_matrix.py` y el histórico en `reglas.md:296`.
9. **TS contracts**: extender `apps/web-teacher/src/lib/api.ts` con los nuevos tipos + `tareasPracticasTemplatesApi`. Mirror en `apps/web-student/src/lib/api.ts` **solo si** el estudiante leyera templates (no lo hace — no tocar).
10. **UI**: nueva `TemplatesView.tsx` en web-teacher; actualizar `TareasPracticasView.tsx` para renderizar badges `template_id`/`has_drift`; dialog de confirmación al editar instancia con template; ruta nueva en `apps/web-teacher/src/App.tsx` (o equivalente).
11. **Tutor service**: verificación extra (no código nuevo, pero test explícito): agregar a `tests/unit/test_open_episode_tarea_practica_validation.py` un caso "TP con template_id != null sigue pasando las 6 validaciones". Confirma que el cambio no rompe el contrato.
12. **Classifier/CTR**: sanity check, no cambios de código. El test `test_pipeline_reproducibility.py` sigue verde al no tocar `comision_id` ni `problema_id`.
13. **ADR y reglas**: merge de `docs/adr/016-tp-template-instance.md` + entrada en `reglas.md` bajo F1 (sugerencia: RN-013bis "Templates de TP son la fuente canónica cuando existen; la instancia gana flag `has_drift` al editarse directamente").
14. **Seed de piloto (opcional)**: si `scripts/seed-3-comisiones.py` se quiere extender para crear 1 template + 3 instancias, agregarlo como función nueva — no alterar el flujo actual que usa `PROBLEMA_ID` constante.
15. **docs/F1-STATE.md / docs/SESSION-LOG.md**: registrar ADR-016, nueva superficie de Casbin (92 → 104), nueva tabla, nuevos endpoints.

## Referencias

- ADR-001 (multi-tenancy RLS) — `tareas_practicas_templates` requiere `apply_tenant_rls`.
- ADR-003 (separación de bases) — los templates viven en `academic_main`, no cross-DB.
- ADR-009 (Git como fuente del prompt) — `curso_config_hash` sigue per-Comisión; el template NO contribuye.
- ADR-010 (append-only clasificaciones) — al cambiar el template, NO se reclasifica; coherente con la filosofía.
- RN-001, RN-013 (HU-F1), RN-046 (hash shapes).
- `apps/academic-service/src/academic_service/models/operacional.py:154-217` — modelo base.
- `apps/academic-service/src/academic_service/routes/tareas_practicas.py` — endpoints existentes.
- `apps/academic-service/src/academic_service/services/tarea_practica_service.py` — lógica existente, base para el patrón.
- `apps/tutor-service/src/tutor_service/services/tutor_core.py:64-138, 393-476` — `open_episode` + `_validate_tarea_practica` (no cambia).
- `apps/academic-service/alembic/versions/20260422_0001_carrera_facultad_required.py` — última revisión; la nueva migración va a continuación con `down_revision="20260422_0001"`.
- `apps/academic-service/src/academic_service/seeds/casbin_policies.py:67-137` — policies actuales de `tarea_practica`.
- `apps/web-teacher/src/views/TareasPracticasView.tsx` — UI actual.
- `apps/web-teacher/src/lib/api.ts:275-454` — contratos TS.
- `packages/contracts/src/platform_contracts/ctr/events.py:38-47` + `packages/contracts/src/ctr/index.ts:33-42` — `EpisodioAbiertoPayload` (no cambia).
