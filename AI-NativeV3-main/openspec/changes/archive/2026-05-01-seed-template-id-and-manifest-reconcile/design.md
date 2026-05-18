## Context

El piloto UNSL para defensa doctoral usa `scripts/seed-3-comisiones.py` como fuente unica de data demo (3 comisiones / 18 estudiantes / 94 episodios). Tres bugs chicos pero visibles desfasan la data demo de las invariantes que la tesis defiende:

1. `Episode.problema_id` apunta a una constante hardcodeada (`99999999-...`) en lugar de las 6 instancias reales de `TareaPractica` que el mismo seed crea con `template_id` poblado. Esto rompe el JOIN `episodes -> tareas_practicas -> tareas_practicas_templates` y deja a `cii-evolution-longitudinal` y `cii-quartiles` devolviendo `insufficient_data: true` aunque haya data suficiente.
2. El seed registra eventos CTR con `prompt_system_version="v1.0.0"`, pero el runtime usa `v1.0.1` (`Settings.default_prompt_version` + `manifest.yaml`). Episodios viejos y nuevos no concuerdan (viola G12).
3. La columna `nombre` no existe en la tabla `comisiones` — el modelo solo tiene `codigo`. El seed pasa `nombre` como key del dict pero nunca persiste, asi que los frontends solo muestran "A", "B", "C".

**Stakeholders**: doctorando (defensa), comite doctoral (verifica criterios objetivos), DI UNSL (recibe la migracion). Constraint duro: NO romper hashes CTR ni reproducibilidad bit-a-bit (ADR-010).

## Goals / Non-Goals

**Goals:**
- Datos de demo internamente consistentes con las invariantes de la tesis (template_id resoluble, prompt_version alineada con runtime, nombres humanos en comisiones).
- Migracion Alembic backfill-safe (NOT NULL con default desde `codigo` para filas existentes).
- Idempotencia preservada: re-correr el seed sigue siendo seguro (borra y rehace tenant `aaaa...`).
- `make migrate && make test && make check-rls` siguen pasando.

**Non-Goals:**
- NO tocar `seed-demo-data.py` (el seed chico, fuera del piloto UNSL).
- NO denormalizar `materia_nombre` ni otros campos en el response de comisiones — solo `nombre`.
- NO modificar el cuerpo de `prompts/tutor/v1.0.1/system.md` ni su manifest firmado.
- NO incorporar `nombre` al UNIQUE constraint (sigue siendo `(tenant_id, materia_id, periodo_id, codigo)`).
- NO regenerar classifications historicas — el seed reconstruye desde cero.
- NO modificar `LABELER_VERSION` (sigue en `1.1.0` por ADR-023).

## Decisions

### D1: Mapping `(comision_id, ep_idx) -> tarea_practica_instance_id` round-robin estable

**Decision**: reemplazar la constante `PROBLEMA_ID = "99999999-..."` en `seed-3-comisiones.py` por un dict `tp_instances_by_comision: dict[UUID, list[UUID]]` que el seed ya construye al crear las 6 instancias (3 comisiones x 2 templates). El loop de episodios indexa con `tp_instances_by_comision[comision_id][ep_idx % 2]` para distribuir round-robin entre los 2 templates de cada comision.

**Rationale**:
- Distribucion uniforme entre los 2 templates -> ambos tienen `n >= MIN_EPISODES_FOR_LONGITUDINAL = 3` por estudiante en cohortes con `>= 6 episodios` -> el slope longitudinal es computable para cada template.
- Determinista (`ep_idx` ya viene del enumerate del loop) -> idempotente bit-a-bit -> no rompe la promesa de reproducibilidad del seed.
- Cero cambios al CTR — solo afecta el valor que se inserta en `Episode.problema_id`.

**Alternativas consideradas**:
- *Crear 1 instancia de TP por episodio*: explotaria el conteo `>=3 por template` (cada template tendria solo 1 episodio). Rechazado: rompe el sentido de longitudinal por template.
- *Asignar todos los episodios al mismo template*: trivializa el analisis (1 sola serie temporal). Rechazado: el dashboard tiene que mostrar `slope_per_template` con multiples templates.

### D2: Bump de `PROMPT_SYSTEM_VERSION` del seed con SHA recomputado

**Decision**: cambiar la constante `PROMPT_SYSTEM_VERSION = "v1.0.0"` (linea 82 del seed) a `"v1.0.1"`, y `PROMPT_SYSTEM_HASH` al sha256 declarado en `ai-native-prompts/prompts/tutor/v1.0.1/manifest.yaml:8`. Verificar tras el bump que `SELECT DISTINCT prompt_system_version FROM events WHERE tenant_id='aaaa...'` devuelve solo `v1.0.1`.

**Rationale**:
- Alinea seed con runtime — cierra el gap G12 sin tocar tutor-service ni governance-service.
- El `prompt_system_hash` es parte del payload del evento `prompt_enviado` y entra al `self_hash` del CTR — recomputarlo apropiadamente preserva la cadena. El seed reconstruye desde cero asi que no hay invalidacion de eventos viejos.

**Alternativa rechazada**: dejar el seed en v1.0.0 y "esperar a que el piloto real genere v1.0.1". Esto perpetua la inconsistencia visible en queries durante la defensa.

### D3: Migracion Alembic con backfill desde `codigo`

**Decision**: nueva migracion `apps/academic-service/alembic/versions/20260430_0001_comision_nombre.py`:

```python
def upgrade():
    op.add_column("comisiones", sa.Column("nombre", sa.String(100), nullable=True))
    op.execute("UPDATE comisiones SET nombre = codigo WHERE nombre IS NULL")
    op.alter_column("comisiones", "nombre", nullable=False)
```

Tres pasos en una sola migracion: add nullable -> backfill -> alter NOT NULL. Esto evita el caso degenerado de filas con NULL si la base ya tiene comisiones (relevante para staging del piloto si se aplico ya algun seed previo).

**Rationale**:
- Backfill-safe sin downtime — es Postgres, agregar columna nullable es metadata-only; el UPDATE corre rapido en tablas chicas (piloto: <100 comisiones).
- `nombre = codigo` como default semantico: las comisiones existentes muestran "A" como nombre, lo cual no es lindo pero no es incorrecto. El re-seed despues sobreescribe con "A-Manana", etc.

**Alternativa rechazada**: agregar la columna como `NOT NULL DEFAULT 'sin nombre'` en una sola sentencia. Es mas corto pero deja basura semantica si alguien agrega filas sin updatear.

### D4: Modelos y schemas se actualizan en tandem

**Decision**: el cambio toca 3 capas en orden: (a) `models/operacional.py` agrega `nombre: Mapped[str]`, (b) `schemas/comision.py` agrega `nombre: str = Field(min_length=1, max_length=100)` en `ComisionBase` y `nombre: str | None` en `ComisionUpdate`, (c) `services/comision_service.py` ya recibe `**data.model_dump()` asi que no requiere logica nueva — solo verificar que el INSERT del seed (lineas 482-496) pase el `nombre` correcto.

**Rationale**: cambios de schema requieren tocar las 3 capas o el codigo no compila / runtime falla. El servicio ya delega al model — no hay que escribir logica de update custom.

## Risks / Trade-offs

- **[Riesgo] Re-ejecutar `seed-3-comisiones.py` borra tenant demo** -> Mitigation: el seed siempre fue scopeado a `TENANT_ID = aaaa...` (no toca tenants reales). Documentar en docstring + `docs/SESSION-LOG.md` la fecha de re-corrida.
- **[Riesgo] Tests existentes asumen shape viejo de `ComisionOut` sin `nombre`** -> Mitigation: convencion CLAUDE.md exige actualizar tests en el mismo PR. El sub-agente de apply tiene que correr `make test` y arreglar cualquier breakage.
- **[Riesgo] Migracion en staging si tiene comisiones reales** -> Mitigation: el backfill (`UPDATE ... SET nombre = codigo`) hace que la migracion sea segura aun con data preexistente. La migracion es idempotente por Alembic.
- **[Trade-off] `nombre` no entra al UNIQUE constraint** -> Acepto: es etiqueta humana, no clave logica. La unicidad sigue siendo `(tenant_id, materia_id, periodo_id, codigo)`. Dos comisiones distintas pueden tener el mismo nombre (raro pero permitido).
- **[Trade-off] El bump del prompt version solo cubre data demo** -> Acepto: en el piloto real cuando arranque, el tutor-service ya emite v1.0.1 nativamente. Eventos historicos (si los hubiera, no hay aun) quedarian en v1.0.0 — ADR-023 cubre el patron de versionado de etiquetadores y se aplica analogamente al prompt.

## Migration Plan

1. **Correr migracion**: `make migrate` agrega columna `nombre` con backfill desde `codigo`. Filas pre-existentes tienen `nombre = codigo`.
2. **Re-correr seed**: `uv run python scripts/seed-3-comisiones.py` — borra tenant `aaaa...` y rehace 3 comisiones / 18 estudiantes / 94 episodios con: (a) `nombre` populado ("A-Manana", "B-Tarde", "C-Noche"), (b) `Episode.problema_id` apuntando a 6 instancias reales, (c) eventos CTR con `prompt_system_version="v1.0.1"` y hash recomputado.
3. **Verificar criterios** (acceptance del proposal): los 8 criterios numerados deben pasar.
4. **Rollback**: si algo falla, `alembic downgrade -1` revierte la migracion (`drop column nombre`); el seed legacy sigue funcionando porque la columna era opcional en el dict de Python (key sin persistir).

## Open Questions

Ninguna abierta. Las 3 decisiones tecnicas (D1, D2, D3) son cerradas; el proposal tiene los criterios verificables y los riesgos estan mitigados.
