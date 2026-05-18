# ADR-047 — Ejercicio como entidad de primera clase reusable

- **Estado**: Propuesto
- **Fecha**: 2026-05-14
- **Deciders**: Alberto Cortez, director de tesis
- **Tags**: datos, schema, academic-service, ejercicios, trazabilidad
- **Sucede a / depende de**: ADR-016 (TareaPracticaTemplate), ADR-034 (test_cases JSONB en TP), ADR-042 (templates piloto-1), ADR-041 (unidades-trazabilidad)

## Contexto y problema

Hoy los ejercicios de un TP viven como **array JSONB embebido** en `TareaPractica.ejercicios` (validado por `EjercicioSchema` y `EjerciciosValidator` en `packages/contracts/src/platform_contracts/academic/schemas.py`). Cada ejercicio es un dict con `orden`, `titulo`, `enunciado_md`, `inicial_codigo`, `test_cases`, `peso`. La identidad del ejercicio es **posicional** (`orden`) y vive **adentro** del JSONB de una TP específica.

Este shape impide tres cosas que el piloto y la tesis necesitan:

1. **Reuso del mismo ejercicio entre TPs**. Hoy, si un docente quiere usar el ejercicio "Hola Mundo" en el TP1 de Comisión A-Mañana y en el TP de recuperación de Comisión B-Tarde, tiene que **duplicar el JSON** dentro de cada TP. No hay forma de decir "el ejercicio E1 del banco PID-UTN aparece en estas dos TPs". Cada copia diverge silenciosamente con cualquier edición.

2. **Banco institucional de ejercicios como unidad analítica**. La tesis quiere comparar trayectorias cognitivas N4 entre cohortes sobre **el mismo estímulo**. Hoy, "el mismo ejercicio" en TPs distintas no es referenciable por identidad — solo por contenido textual. La unidad de análisis termina siendo la TP (variable entre cohortes) en lugar del ejercicio (estable).

3. **Schema pedagógico rico por ejercicio**. ADR-048 (paralelo) propone sumar al ejercicio campos pedagógicos PID-UTN (banco socrático N1-N4, misconceptions, tutor_rules, anti-patrones, heurística de cierre). Si el ejercicio sigue siendo dict JSONB anidado en TP, esos campos se duplican cada vez que el ejercicio aparece en otra TP — desincronización garantizada.

Los datos pedagógicos vienen del trabajo del PID Línea 5 (UTN-FRM × UTN-FRSN). Los 3 bancos docentes (`b1.docx` secuenciales, `condi.docx` condicionales, `mixtos.docx` integrador) suman **25 ejercicios** ya diseñados con todo el material socrático asociado. Son la materia prima del piloto: ejercicios que existen como **artefactos pedagógicos canónicos**, no como contenido inline de TPs.

**Verificación empírica del estado actual** (2026-05-14): el seed `seed-3-comisiones.py` produce 15 TPs en `tenant_demo` y **ninguna** tiene `jsonb_array_length(ejercicios) > 0`. El campo está vacío en producción del piloto local. Los frontends y el tutor-service tienen el plumbing para consumir ejercicios (`GET /tareas-practicas/{id}/ejercicios`, `ejercicio_orden` en `EpisodioAbiertoPayload`) pero **nunca se ejercita con datos reales**. Esto significa que **la BD piloto local es desechable a efectos del refactor** — no hay datos legacy que migrar.

## Drivers de la decisión

- **Reuso entre TPs**: requisito de producto explícito — un ejercicio se diseña una vez y aparece en N TPs.
- **Trazabilidad cognitiva por ejercicio**: la tesis necesita poder reconstruir "todos los episodios sobre el ejercicio E4 — Área de Círculo a lo largo del cuatrimestre, comparando cohortes". Esto requiere identidad UUID estable del ejercicio.
- **Schema pedagógico rico no duplicable**: ADR-048 introduce campos pedagógicos (banco N1-N4, misconceptions, etc.) cuya copia entre TPs es inviable.
- **BD piloto limpia**: no hay datos legacy del JSONB que migrar; la migración puede ser destructiva en una sola pasada.
- **Compatibilidad con CTR**: ADR-016 declara que `Episode.problema_id = TareaPractica.id` (instancia, no template). Este invariante NO cambia. Lo que cambia es que el episodio puede referenciar **adicionalmente** un `ejercicio_id` (ver ADR-049).
- **Versionado inmutable de TP** (ADR-016): la TP versiona on edit post-`published`. La tabla intermedia `tp_ejercicios` debe acompañar el patrón — cada versión nueva de TP clona sus filas.

## Opciones consideradas

### Opción A — Mantener JSONB embebido, sumar campo `ejercicio_uuid` por elemento

Cada elemento del array JSONB recibe un campo `id: UUID`. El reuso se "simula" copiando el UUID entre TPs. Sin tabla separada.

**Ventajas**: cero cambios estructurales en `TareaPractica`, sin migration nueva.

**Desventajas**:
- El "reuso" es por convención, no por integridad referencial. Dos copias del mismo UUID pueden divergir en contenido sin que el sistema lo detecte.
- Sin queries cross-TP por ejercicio (`SELECT * FROM ejercicios WHERE unidad_tematica='condicionales'` no se puede expresar sin parsear JSONB).
- El schema pedagógico rico (ADR-048) sigue duplicándose por copia.
- Rechazada por ineficacia.

### Opción B — Tabla `ejercicios` + tabla intermedia `tp_ejercicios` (N:M)

Tabla nueva `ejercicios` con UUID propio, todos los campos del schema (base + pedagógicos). Tabla intermedia `tp_ejercicios(tarea_practica_id, ejercicio_id, orden, peso_en_tp)` con UNIQUE constraints. El campo `TareaPractica.ejercicios` JSONB se elimina.

**Ventajas**:
- Reuso real: el mismo `Ejercicio` puede aparecer en N TPs.
- Queries cross-TP por ejercicio triviales.
- Schema pedagógico vive una sola vez por ejercicio.
- Edición del ejercicio se propaga automáticamente (con caveat de versionado — ver Consecuencias).
- La unidad de análisis de la tesis pasa a ser el `Ejercicio`, estable entre cohortes.

**Desventajas**:
- Migración destructiva del JSONB (drop column + tablas nuevas). Aceptable porque la BD piloto está limpia.
- Versionado de TP debe clonar filas de `tp_ejercicios` además del registro de TP — una línea extra en `new_version()`, pero hay que recordarla.
- Impacto coordinado en tutor-service, CTR (ADR-049), evaluation-service, frontends — ver Consecuencias.

### Opción C — Tabla `ejercicios` separada, pero TPs referencian con FK directa (1:N en lugar de N:M)

Tabla `ejercicios` con UUID, pero cada ejercicio pertenece a **una** TP via FK `tarea_practica_id`. Reuso por "clonado" (copiar la fila al usar en otra TP).

**Ventajas**: schema más simple, sin tabla intermedia.

**Desventajas**:
- El reuso vuelve a ser por copia, no por referencia. Pierde el driver principal.
- Los campos pedagógicos se duplican cada vez que se clona.
- Rechazada por no resolver el problema raíz.

## Decisión

Opción elegida: **B** — tabla `ejercicios` standalone con identidad UUID + tabla intermedia `tp_ejercicios` (N:M).

Justificación: es la única que satisface los tres drivers principales (reuso, trazabilidad por ejercicio, schema pedagógico no duplicable). La migración destructiva es viable porque la BD piloto local es desechable. El costo coordinado en otros servicios queda contenido por el contexto (BD limpia, sin backward compat necesaria).

### Shape de la tabla `ejercicios`

```python
class Ejercicio(Base, TenantMixin, TimestampMixin):
    __tablename__ = "ejercicios"

    id: Mapped[UUID] = uuid_pk()

    # Identificación
    titulo: Mapped[str]                            # max 200
    enunciado_md: Mapped[str]                      # Text, markdown
    inicial_codigo: Mapped[str | None]             # Text, scaffold opcional

    # Clasificación pedagógica
    unidad_tematica: Mapped[str]                   # 'secuenciales' | 'condicionales' | 'repetitivas' | 'mixtos'
    dificultad: Mapped[str | None]                 # 'basica' | 'intermedia' | 'avanzada'
    prerequisitos: Mapped[dict]                    # JSONB tipado, ver ADR-048

    # Tests ejecutables (mismo formato que ADR-034)
    test_cases: Mapped[list[dict]]                 # JSONB, default []

    # Evaluación
    rubrica: Mapped[dict | None]                   # JSONB tipado, ver ADR-048

    # Pedagogía PID-UTN (ver ADR-048 para shape detallado)
    tutor_rules: Mapped[dict | None]               # JSONB tipado
    banco_preguntas: Mapped[dict | None]           # JSONB tipado por fase N1-N4
    misconceptions: Mapped[list[dict]]             # JSONB, default []
    respuesta_pista: Mapped[list[dict]]            # JSONB, default []
    heuristica_cierre: Mapped[dict | None]         # JSONB tipado
    anti_patrones: Mapped[list[dict]]              # JSONB, default []

    # Autoría y origen
    created_by: Mapped[UUID]                       # FK a usuarios (docente)
    created_via_ai: Mapped[bool]                   # default False
```

CHECK constraints:
- `unidad_tematica IN ('secuenciales', 'condicionales', 'repetitivas', 'mixtos')`.
- `dificultad IS NULL OR dificultad IN ('basica', 'intermedia', 'avanzada')`.

RLS: política estándar `tenant_id = current_setting('app.current_tenant')::uuid` por ADR-001.

### Shape de la tabla `tp_ejercicios`

```python
class TpEjercicio(Base, TenantMixin):
    __tablename__ = "tp_ejercicios"

    id: Mapped[UUID] = uuid_pk()
    tarea_practica_id: Mapped[UUID] = fk_uuid("tareas_practicas.id")
    ejercicio_id: Mapped[UUID] = fk_uuid("ejercicios.id")
    orden: Mapped[int]                              # >= 1, unico por TP
    peso_en_tp: Mapped[Decimal]                     # > 0, <= 1
```

UNIQUE constraints:
- `(tenant_id, tarea_practica_id, ejercicio_id)` — un ejercicio aparece a lo sumo una vez por TP.
- `(tenant_id, tarea_practica_id, orden)` — el orden es único dentro de la TP.

CHECK: `peso_en_tp > 0 AND peso_en_tp <= 1`.

RLS estándar.

### Endpoints REST

Prefijos nuevos en api-gateway `ROUTE_MAP`:

| Método | Path | Descripción |
|--------|------|-------------|
| POST   | `/api/v1/ejercicios` | Crear ejercicio (manual) |
| GET    | `/api/v1/ejercicios` | Listar con filtros: `unidad_tematica`, `dificultad`, `created_by`, cursor |
| GET    | `/api/v1/ejercicios/{id}` | Detalle |
| PATCH  | `/api/v1/ejercicios/{id}` | Editar |
| DELETE | `/api/v1/ejercicios/{id}` | Soft delete |
| POST   | `/api/v1/ejercicios/generate` | Wizard IA (ver ADR-050 cuando se redacte) |
| GET    | `/api/v1/tareas-practicas/{id}/ejercicios` | Listar ejercicios de una TP (lee de `tp_ejercicios` JOIN `ejercicios`) |
| POST   | `/api/v1/tareas-practicas/{id}/ejercicios` | Agregar ejercicio a TP |
| PATCH  | `/api/v1/tareas-practicas/{id}/ejercicios/{ejercicio_id}` | Editar `orden`/`peso_en_tp` |
| DELETE | `/api/v1/tareas-practicas/{id}/ejercicios/{ejercicio_id}` | Quitar ejercicio de TP |

Casbin policies a sumar al seed `apps/academic-service/src/academic_service/seeds/casbin_policies.py`:
- `ejercicio:CRUD` para `superadmin`, `docente_admin`, `docente`.
- `ejercicio:read` para `estudiante`.
- (las acciones sobre `tp_ejercicios` se autorizan via `tarea_practica:CRUD`).

## Consecuencias

### Positivas

- **Reuso real entre TPs** — un `Ejercicio` puede aparecer en N TPs sin duplicación.
- **Trazabilidad cognitiva por ejercicio** — la tesis puede agrupar episodios por `ejercicio_id` (con ADR-049) y comparar trayectorias inter-cohorte sobre el mismo estímulo. Esto es lo que más empuja la tesis: el `Ejercicio` se convierte en unidad analítica reproducible, no la TP.
- **Schema pedagógico vive una sola vez** — el banco socrático del ejercicio, sus misconceptions, sus anti-patrones, viven en un solo lugar (ver ADR-048).
- **Queries cross-TP** — "todos los ejercicios de unidad `condicionales` con dificultad `intermedia`" es una query trivial.
- **Bootstrap del piloto con los 25 ejercicios PID-UTN** — se cargan una vez como datos canónicos institucionales y se referencian desde las TPs.
- **Modelo coherente con tabla `unidades`** (ADR-041) — la `unidad_tematica` del ejercicio es ortogonal a `TareaPractica.unidad_id`; un ejercicio puede usarse en TPs de unidades académicas distintas.

### Negativas / trade-offs

- **Migración destructiva del JSONB**: el campo `TareaPractica.ejercicios` se elimina en la migration que crea las tablas nuevas. Esto rompe cualquier consumidor que asuma el shape viejo. Mitigación: el endpoint `GET /tareas-practicas/{id}/ejercicios` mantiene su contrato HTTP (devuelve lista de ejercicios ordenados con campos base + ahora pedagógicos), pero internamente cambia el origen del dato. Frontends y tutor-service deben actualizarse coordinadamente — el orden de implementación está en el plan de migración del refactor (ver "Migration path" abajo).
- **Versionado de TP requiere clonar `tp_ejercicios`**: `tarea_practica_service.new_version()` debe insertar filas nuevas de `tp_ejercicios` para la versión nueva, copiando `ejercicio_id`/`orden`/`peso_en_tp` del parent. El `Ejercicio` en sí **no se clona** (se sigue referenciando por el mismo UUID), salvo que se edite el ejercicio post-publicación de la TP — caso documentado abajo.
- **Edición de `Ejercicio` post-publicación de TP**: si un docente edita el `Ejercicio E1` después de que ya existe `TP1 v1 → E1`, la edición se ve en futuras lecturas de `TP1 v1` (porque la FK apunta al mismo UUID). Esto rompe la inmutabilidad del versionado de TP, que el piloto sostiene como invariante académico. **Mitigación**: el endpoint `PATCH /api/v1/ejercicios/{id}` queda **prohibido para ejercicios referenciados por TPs en estado `published`** salvo via "nueva versión del ejercicio" (clonado explícito con campo `parent_ejercicio_id`). El detalle del versionado de `Ejercicio` queda fuera del scope de este ADR — se documenta como **deuda diferida** y se aborda cuando aparezca el primer caso de uso real (ej. corregir un typo del enunciado mid-piloto). Workaround inicial: si el docente edita un ejercicio mid-piloto, la edición se propaga; documentar el riesgo en `CLAUDE.md` y dejarlo como agenda piloto-2.
- **Impacto cruzado en servicios**:
  - **tutor-service** (`tutor_core.py::open_episode`): el lookup pasa de `(tarea_id, orden) → ejercicio_dict` a `ejercicio_id → Ejercicio`. Un solo roundtrip al academic-service en lugar de cargar toda la lista de ejercicios de la TP.
  - **evaluation-service** (`Entrega.ejercicio_estados`): el schema del elemento pasa de `{orden, episode_id, completado, completed_at}` a `{ejercicio_id, orden, episode_id, completado, completed_at}`. El `ejercicio_id` es autoritativo; el `orden` queda denormalizado para queries rápidas y para preservar el contrato del endpoint `PATCH /entregas/{id}/ejercicio/{n}` (que sigue recibiendo `n` como path param).
  - **CTR**: cambio coordinado en ADR-049 (sumar `ejercicio_id` al payload de `episodio_abierto`).
  - **classifier-service**: sin cambio. No referencia `ejercicios` en el feature extraction.
  - **content-service / RAG**: sin cambio. El scope sigue siendo `materia_id`/`comision_id`.
- **Frontend web-teacher**: el step de ejercicios en el wizard de creación de TP cambia de "crear ejercicios inline" a "seleccionar desde la biblioteca de ejercicios" (con opción "crear ejercicio rápido" que persiste en biblioteca + lo agrega a la TP en un paso para evitar fricción). Nueva vista `EjerciciosView.tsx` con su entry en `helpContent.tsx` (key `ejercicios`).

### Neutras

- **`EjercicioSchema` y `EjerciciosValidator` del JSONB se eliminan** de `packages/contracts/.../academic/schemas.py` — son reemplazados por `EjercicioCreate`/`Update`/`Read` en `ejercicio.py` (ver ADR-048 para el shape completo). Esto rompe imports — el `__init__.py` del paquete debe actualizarse.
- **Reproducibilidad bit-a-bit del `classifier_config_hash`**: este refactor **NO toca** el config del classifier ni el labeler. El hash sigue intacto. Lo que cambia es el payload del CTR (ver ADR-049).
- **El campo `unidad_id` de `TareaPractica`** (FK a `unidades`, ADR-041) sigue como está. La `unidad_tematica` del `Ejercicio` es un campo informativo distinto (taxonomía pedagógica vs unidad académica institucional). Pueden coincidir o no.

## Migration path

### Paso 1 — Schemas Pydantic en `packages/contracts/`

Antes de tocar DB, crear `packages/contracts/src/platform_contracts/academic/ejercicio.py` con todos los sub-schemas (`EjercicioCreate`, `EjercicioUpdate`, `EjercicioRead`, `TpEjercicioCreate`, `TpEjercicioRead` + sub-schemas pedagógicos del ADR-048). Exportarlos desde `__init__.py`. Los schemas existentes `EjercicioSchema`/`EjerciciosValidator` se marcan como **deprecated** y se eliminan en el Paso 4.

### Paso 2 — Migration Alembic destructiva

Una sola migration (`20260515_0001_ejercicio_primera_clase.py`) que:

1. `CREATE TABLE ejercicios` con RLS policy.
2. `CREATE TABLE tp_ejercicios` con RLS policy y UNIQUE constraints.
3. `ALTER TABLE tareas_practicas DROP COLUMN ejercicios`.

No hay backfill porque la BD piloto no tiene datos en el JSONB (verificado 2026-05-14 contra `seed-3-comisiones`).

Downgrade: dropear las dos tablas nuevas y agregar el column `ejercicios` vacío. (No restaura datos, pero la BD piloto es regenerable via re-seed.)

### Paso 3 — Servicios y endpoints

En orden:
1. `apps/academic-service`: modelo `Ejercicio` + `TpEjercicio`, `EjercicioService`, router `/api/v1/ejercicios`, registro en `api-gateway/ROUTE_MAP`, seed Casbin policies.
2. `apps/tutor-service`: `academic_client.get_ejercicio_by_id()`, refactor de `open_episode()` para resolver por UUID, inyección de campos pedagógicos al system message (depende de ADR-048).
3. `apps/evaluation-service`: extender `ejercicio_estados` con `ejercicio_id`.
4. Frontend `apps/web-teacher`: nueva ruta `/ejercicios`, refactor del step de TPs.
5. Frontend `apps/web-student`: actualizar `listEjercicios()` y la navegación a episodios.

### Paso 4 — Seed de los 25 ejercicios PID-UTN

Script `scripts/seed-ejercicios-piloto.py` que lee `scripts/data/ejercicios-piloto.yaml` (provisto por el doctorando) e inserta los 25 ejercicios (10 secuenciales + 10 condicionales + 5 integrador). Idempotente. Los campos pedagógicos completos (banco N1-N4, misconceptions, etc.) se cargan en una segunda pasada cuando el doctorando los provea estructurados.

### Paso 5 — Smoke E2E

Test en `tests/e2e/smoke/test_ejercicios_e2e.py` que valida:
- `POST /ejercicios` + `GET /ejercicios/{id}` round-trip.
- `POST /tareas-practicas/{id}/ejercicios` linkea correctamente.
- `GET /tareas-practicas/{id}/ejercicios` devuelve los ejercicios ordenados.
- `POST /episodes` con `ejercicio_id` abre episodio (cuando ADR-049 esté implementado).

### Paso 6 — Aprobación y status

Cambiar `Estado: Propuesto` → `Estado: Aceptado` con commit `docs(adr): aceptar ADR-047 ejercicio primera-clase reusable`.

## Riesgos identificados

- **Versionado de `Ejercicio` queda como deuda diferida**: si un docente edita un ejercicio que ya forma parte de una TP publicada, la edición se propaga retroactivamente — rompe inmutabilidad de TP. Mitigación inicial: `PATCH /api/v1/ejercicios/{id}` requiere flag explícito `force=true` si el ejercicio está en TPs publicadas; el caller (frontend) advierte al docente. Solución completa (versionado `parent_ejercicio_id`) se aborda en ADR aparte cuando aparezca el caso de uso.
- **Coordinación de cambios cross-service**: el refactor toca academic-service, tutor-service, evaluation-service, 2 frontends. Ejecución debe ser disciplinada — cada batch deployable independiente. El orden está en "Migration path Paso 3".
- **Seed de los 25 ejercicios PID-UTN depende del doctorando**: los `.docx` originales (`b1.docx`, `condi.docx`, `mixtos.docx`) no tienen los campos del schema en formato machine-readable. El doctorando debe producir el YAML estructurado. Inicialmente se cargan los campos base (`titulo`, `enunciado_md`, `unidad_tematica`); los campos pedagógicos (banco N1-N4, etc.) se completan iterativamente.
- **Estudiantes con sesiones abiertas durante la migration**: la migration es destructiva y dropea el campo `ejercicios`. Si se aplica con sesiones activas en el tutor, las sesiones que apunten a TPs con ejercicios fallan al hacer el siguiente turno. Mitigación: aplicar la migration en ventana de mantenimiento del piloto (irrelevante en BD local; relevante cuando se aplique a piloto real UNSL).

## Referencias

- ADR-016 — TareaPracticaTemplate (versionado de TPs).
- ADR-034 — test_cases como JSONB en `tareas_practicas` (patrón JSONB tipado seguido por este ADR).
- ADR-041 — Deprecación identity-service + tabla `unidades`.
- ADR-042 — Templates piloto-1 longitudinal-eligible.
- ADR-048 (paralelo) — Schema pedagógico del Ejercicio.
- ADR-049 (paralelo) — `ejercicio_id` en CTR payload.
- Bancos PID-UTN: `Descargas/b1.docx`, `Descargas/condi.docx`, `Descargas/mixtos.docx`.
