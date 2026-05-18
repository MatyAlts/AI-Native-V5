# ADR-049 — `ejercicio_id` en CTR payload desde el inicio

- **Estado**: Propuesto
- **Fecha**: 2026-05-14
- **Deciders**: Alberto Cortez, director de tesis
- **Tags**: ctr, append-only, reproducibilidad, trazabilidad, schema
- **Sucede a / depende de**: ADR-010 (CTR append-only), ADR-016 (Episode.problema_id = instancia), ADR-020 (n_level derivado en lectura), ADR-047 (Ejercicio primera clase), ADR-048 (schema pedagógico)

## Contexto y problema

Hoy `EpisodioAbiertoPayload` (en `packages/contracts/src/platform_contracts/ctr/events.py`) tiene los siguientes campos relevantes:

```python
class EpisodioAbiertoPayload(BaseModel):
    problema_id: UUID                       # TareaPractica.id (instancia, no template)
    comision_id: UUID
    materia_id: UUID | None
    ejercicio_orden: int | None             # posición del ejercicio dentro del array JSONB de la TP
    # ... otros campos
```

Cuando un estudiante abre un episodio sobre un ejercicio específico de una TP, el CTR registra `(problema_id, ejercicio_orden)`. El `ejercicio_orden` es un entero **relativo a la posición** del ejercicio dentro del array `TareaPractica.ejercicios` JSONB.

ADR-047 introduce la tabla `ejercicios` como entidad de primera clase con UUID propio. El `ejercicio_orden` deja de ser identificador estable — pasa a vivir en la tabla intermedia `tp_ejercicios(tarea_practica_id, ejercicio_id, orden, peso_en_tp)`. **El orden es ahora una propiedad de la relación TP↔Ejercicio**, no del ejercicio en sí.

Esto crea una decisión sobre cómo el CTR identifica al ejercicio de un episodio. Tres caminos posibles:

1. **Solo `ejercicio_orden`**: mantener el payload como está hoy. La trazabilidad por ejercicio requiere joinear posteriormente con `tp_ejercicios` para resolver el UUID — y solo funciona si la TP y su tabla intermedia siguen intactas (riesgo de pérdida de trazabilidad si se reordenan ejercicios en una nueva versión de TP).
2. **Solo `ejercicio_id`**: reemplazar `ejercicio_orden` por `ejercicio_id`. Trazabilidad limpia, pero rompe la lógica de validación de secuencialidad del tutor-service (`_validate_ejercicio_secuencialidad`) que hoy compara `orden - 1` con el último ejercicio completado.
3. **Ambos**: `ejercicio_id` como identidad autoritativa + `ejercicio_orden` denormalizado para queries rápidas y para preservar la lógica de secuencialidad.

**Contexto crítico — reproducibilidad bit-a-bit**: el CLAUDE.md del proyecto declara como invariante que el `classifier_config_hash` debe ser reproducible bit-a-bit sobre los eventos del piloto. Modificar el shape de `EpisodioAbiertoPayload` cambia el `self_hash` de eventos nuevos (porque la fórmula es `sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")))`). En BD con eventos legacy, esto rompe el invariante.

**Contexto que destraba la decisión**: la BD piloto local está limpia para el refactor (ADR-047 explica el verificado empírico). El piloto real UNSL aún no corrió contra el sistema actual con `ejercicio_orden` poblado — todos los episodios del seed apuntan a TPs monolíticas (`ejercicio_orden = NULL`). Por lo tanto **no hay eventos históricos con `ejercicio_orden` no-nulo que el cambio de schema invalide**.

## Drivers de la decisión

- **Trazabilidad cognitiva por ejercicio reusable**: el principal aporte de ADR-047 a la tesis. Para que funcione, el CTR debe poder responder "dame todos los episodios sobre `ejercicio_id = X` a lo largo del cuatrimestre". Sin `ejercicio_id` en el payload, esta query requiere joinear con `tp_ejercicios` — y si una TP se versiona y se reordenan los ejercicios, la query histórica se vuelve ambigua.
- **Reproducibilidad bit-a-bit**: el invariante del proyecto. Cualquier cambio al payload tiene que ser justificable y consciente del impacto.
- **BD piloto limpia habilita refactor con-coste-cero**: no hay eventos con `ejercicio_orden` poblado; cambiar el schema ahora es gratis. Hacerlo después es caro.
- **Compatibilidad con la lógica de secuencialidad del tutor**: hoy `_validate_ejercicio_secuencialidad` valida que el ejercicio anterior (`orden - 1`) esté completado. Esta lógica es semánticamente sobre el **orden dentro de la TP**, no sobre la identidad del ejercicio. Por lo tanto requiere `ejercicio_orden` en el payload — un ejercicio puede aparecer en posiciones distintas en TPs distintas.
- **Consistencia con la decisión del CTR sobre `problema_id`** (ADR-016, RN-013bis): el CTR apunta a la **instancia** (`TareaPractica.id`), no al template. Por simetría, debería apuntar al **ejercicio resuelto** (`ejercicio_id` UUID), no a la posición dentro de la TP.
- **Inmunidad ante reordenamiento en versiones futuras de TP**: si una TP versiona y reordena ejercicios, los episodios históricos siguen vinculados al `ejercicio_id` correcto (el contenido pedagógico que el estudiante vio), no a "posición 3 de la TP v2 que ahora es un ejercicio distinto".

## Opciones consideradas

### Opción A — Solo `ejercicio_orden` (sin cambio)

Mantener el payload como está. La trazabilidad por ejercicio se resuelve siempre por JOIN con `tp_ejercicios`.

**Ventajas**:
- Cero cambio al schema del CTR.
- `self_hash` del payload `EpisodioAbiertoPayload` queda bit-a-bit idéntico a la fórmula actual.
- Cero riesgo sobre reproducibilidad.

**Desventajas**:
- Trazabilidad histórica frágil: si una TP versiona y reordena ejercicios, las queries cross-temporales por ejercicio se vuelven ambiguas o requieren reconstruir la tabla intermedia en el estado en que estaba al momento del episodio.
- El driver principal de ADR-047 (Ejercicio como unidad analítica de la tesis) queda parcialmente debilitado.
- Rechazada porque pierde el aporte académico principal.

### Opción B — Solo `ejercicio_id`

Reemplazar `ejercicio_orden` por `ejercicio_id` en el payload. La validación de secuencialidad del tutor-service tiene que resolver el orden via `tp_ejercicios` en runtime.

**Ventajas**:
- Payload más limpio, una sola fuente de identidad.
- Trazabilidad histórica robusta.

**Desventajas**:
- La validación de secuencialidad del tutor-service necesita lookup adicional al academic-service por turno de apertura de episodio.
- Las consultas analíticas que quieren "el orden del ejercicio en el TP" tienen que joinear igual.
- Rechazada porque agrega latencia sin beneficio adicional vs Opción C.

### Opción C — Ambos: `ejercicio_id` autoritativo + `ejercicio_orden` denormalizado

`ejercicio_id` es la identidad permanente; `ejercicio_orden` es metadata denormalizada útil para queries y para la lógica de secuencialidad (que es semánticamente sobre el orden dentro de la TP).

**Ventajas**:
- Trazabilidad histórica robusta por `ejercicio_id`.
- Queries analíticas tienen el orden disponible sin JOIN.
- Validación de secuencialidad funciona sin lookup adicional.
- Coherencia con el resto del payload (que ya tiene campos denormalizados como `comision_id`, `materia_id`).

**Desventajas**:
- Levísima duplicación de información (el orden también está en `tp_ejercicios`).
- Riesgo de drift teórico si alguien actualiza `tp_ejercicios.orden` sin actualizar eventos viejos (pero eventos viejos son **append-only e inmutables** por ADR-010 — el orden en el payload es snapshot del momento del episodio, no espejo del estado actual).

## Decisión

Opción elegida: **C** — agregar `ejercicio_id: UUID | None` al payload, manteniendo `ejercicio_orden: int | None` como metadata denormalizada.

### Shape del payload nuevo

```python
class EpisodioAbiertoPayload(BaseModel):
    problema_id: UUID                       # TareaPractica.id (sin cambio)
    comision_id: UUID                       # sin cambio
    materia_id: UUID | None                 # sin cambio
    ejercicio_id: UUID | None               # NUEVO — identidad permanente del ejercicio
    ejercicio_orden: int | None             # sin cambio — orden dentro de la TP al momento del episodio
    # ... resto sin cambio
```

Semántica:
- `ejercicio_id = None AND ejercicio_orden = None` → episodio sobre TP monolítica sin ejercicios (comportamiento legacy compatible).
- `ejercicio_id = UUID AND ejercicio_orden = int` → episodio sobre ejercicio específico de la TP. Ambos deben ser consistentes con la fila correspondiente de `tp_ejercicios` al momento del episodio.
- `ejercicio_id = UUID AND ejercicio_orden = None` o `ejercicio_id = None AND ejercicio_orden = int` → **inválido**. Validar en la boundary del tutor-service antes de emitir el evento.

### Justificación del cambio en BD limpia

La modificación del payload cambia el `self_hash` de los eventos `episodio_abierto` futuros respecto a la fórmula actual aplicada a payloads sin el campo `ejercicio_id`. Esto **NO rompe la cadena** de ningún episodio: cada episodio tiene su propia cadena criptográfica independiente. Lo que cambia es el shape canónico del payload.

Como la BD piloto local está limpia para el refactor (no hay eventos `episodio_abierto` con `ejercicio_orden` poblado en el seed actual — verificado contra `seed-3-comisiones.py`), y el piloto real UNSL todavía no corrió este shape, **el cambio se hace antes de que existan eventos históricos que invaliden**.

El piloto real, cuando se corra, lo hará con el shape nuevo desde el día cero. La reproducibilidad bit-a-bit del `classifier_config_hash` se evalúa contra los eventos del piloto real — todos producidos con el shape nuevo. **El invariante se preserva.**

### Producer del evento (tutor-service)

En `apps/tutor-service/src/tutor_service/services/tutor_core.py::open_episode`:

```python
# Resolver el ejercicio (post-ADR-047)
if ejercicio_id is not None:
    ejercicio = await academic_client.get_ejercicio_by_id(ejercicio_id)
    tp_ejercicio = await academic_client.get_tp_ejercicio_relation(
        tarea_practica_id=problema_id,
        ejercicio_id=ejercicio_id,
    )
    ejercicio_orden = tp_ejercicio.orden
else:
    ejercicio = None
    ejercicio_orden = None

# Validar consistencia
assert (ejercicio_id is None) == (ejercicio_orden is None), \
    "ejercicio_id y ejercicio_orden deben ser ambos None o ambos no-None"

# Emitir evento
payload = EpisodioAbiertoPayload(
    problema_id=problema_id,
    comision_id=comision_id,
    materia_id=materia_id,
    ejercicio_id=ejercicio_id,
    ejercicio_orden=ejercicio_orden,
    # ... resto
)
```

### Consumidor (classifier-service)

El classifier-service hoy excluye `ejercicio_orden` del feature extraction (forma parte del payload pero no se usa para features — solo metadata). **`ejercicio_id` recibe el mismo tratamiento**: no entra al feature extraction. Esto preserva el `classifier_config_hash`. Verificado: el `_EXCLUDED_FROM_FEATURES` set (ver `pipeline.py:63-69`) está pensado para event types completos; el shape del payload de `episodio_abierto` no entra al feature extraction porque `episodio_abierto` no es un event_type que el classifier procese para features (las features se construyen sobre eventos in-episodio: `prompt_enviado`, `tutor_respondio`, `code_edit`, etc.).

### Endpoint POST /episodes

El endpoint del tutor-service que abre episodios pasa a aceptar:

```python
class OpenEpisodeRequest(BaseModel):
    problema_id: UUID
    comision_id: UUID
    ejercicio_id: UUID | None = None        # NUEVO — opcional para TPs monolíticas
    ejercicio_orden: int | None = None      # DEPRECATED — kept for transition
```

Frontends (web-student principalmente) se actualizan para enviar `ejercicio_id`. El parámetro `ejercicio_orden` se mantiene unos batches por compatibilidad y se elimina cuando todos los frontends están migrados.

## Consecuencias

### Positivas

- **Trazabilidad cognitiva por ejercicio reusable consolidada**: la tesis puede agrupar episodios por `ejercicio_id` con garantía de identidad permanente, inmune a reordenamientos o versionados de TP.
- **Unidad analítica robusta**: si en piloto-2 una TP cambia su composición de ejercicios, los episodios históricos siguen ligados a los ejercicios correctos por UUID, no a posiciones que cambiaron de significado.
- **Queries analíticas eficientes**: comparar trayectorias N4 sobre "el mismo ejercicio" entre cohortes es una query `WHERE payload->>'ejercicio_id' = ?` sin joins.
- **Validación de secuencialidad preservada**: `ejercicio_orden` denormalizado evita lookup adicional en cada apertura de episodio.
- **Snapshot inmutable del momento**: el payload registra el orden que el ejercicio tenía en la TP **al momento del episodio**, no el orden actual. Si la TP versiona, los eventos históricos no se contaminan.

### Negativas / trade-offs

- **Cambia el shape canónico del payload de `episodio_abierto`**: el `self_hash` de eventos nuevos es diferente al de cualquier evento hipotético con el shape viejo. **Mitigación**: aplicado mientras la BD está limpia. El piloto real UNSL corre solo con shape nuevo. Documentado explícitamente como decisión consciente.
- **Drift teórico entre payload y `tp_ejercicios`**: si después de un episodio alguien edita `tp_ejercicios.orden` (cambio del orden de un ejercicio en una TP), el payload del evento conserva el orden viejo. Esto es **correcto y deseable** (es snapshot), pero hay que documentarlo. La tabla `tp_ejercicios` es la verdad del estado actual; los payloads son la verdad histórica del momento.
- **Frontends y servicios deben actualizarse coordinadamente**: el endpoint `POST /episodes` cambia de aceptar `ejercicio_orden` a aceptar `ejercicio_id`. Frontends viejos que envíen `ejercicio_orden` deben seguir funcionando durante una transición acotada (ver "Migration path").
- **Riesgo de inconsistencia entre `ejercicio_id` y `ejercicio_orden` en el payload**: si el productor (tutor-service) no calcula bien la consistencia, queda un evento con campos contradictorios. **Mitigación**: assert explícito en el productor; test unit que cubre el caso.

### Neutras

- **No requiere bumpear `LABELER_VERSION`**: este ADR no toca el labeler ni el pipeline del classifier. Las features que el classifier extrae sobre eventos in-episodio (`prompt_enviado`, etc.) no cambian. El `classifier_config_hash` permanece igual.
- **No requiere bumpear el prompt version del tutor**: el contexto que el tutor recibe (ver ADR-048) no depende del shape del payload del CTR.
- **`Episode.problema_id` sigue siendo `TareaPractica.id`**: el invariante ADR-016 / RN-013bis se preserva. El `ejercicio_id` es información complementaria del payload, no reemplazo del `problema_id`.

## Migration path

### Paso 1 — Update `EpisodioAbiertoPayload` schema

En `packages/contracts/src/platform_contracts/ctr/events.py`:

```python
class EpisodioAbiertoPayload(BaseModel):
    # ... campos existentes ...
    ejercicio_id: UUID | None = None        # AGREGADO
    ejercicio_orden: int | None = None      # sin cambio
```

Test golden del `self_hash` en `apps/ctr-service/tests/unit/`: actualizar el fixture con un evento que tenga `ejercicio_id` poblado y verificar que el hash queda determinista. Documentar el nuevo hash golden.

### Paso 2 — Update tutor-service producer

En `apps/tutor-service/src/tutor_service/services/tutor_core.py`:
- `open_episode()` resuelve `ejercicio` por UUID (lookup al academic-service via `get_ejercicio_by_id`).
- Resuelve `ejercicio_orden` via `get_tp_ejercicio_relation`.
- Construye el payload con ambos campos consistentes.
- Assert de consistencia antes de emitir.

### Paso 3 — Update endpoint `POST /episodes`

Aceptar `ejercicio_id` en el request. Mantener `ejercicio_orden` aceptado durante una transición acotada (1 release) para no romper frontends mid-migration; loggear warning si solo viene `ejercicio_orden`.

### Paso 4 — Update frontends

`web-student` envía `ejercicio_id` (UUID) en lugar de `ejercicio_orden` al abrir episodios. `web-teacher` no se afecta (no abre episodios).

### Paso 5 — Update validación de secuencialidad

`_validate_ejercicio_secuencialidad` sigue usando `ejercicio_orden` (sin cambio), pero el lookup del "ejercicio previo completado" se hace por `(tarea_practica_id, orden = orden_actual - 1)` resuelto en `tp_ejercicios` → `ejercicio_id` previo. La validación en evaluation-service compara contra el `ejercicio_id` o `orden` registrado en `Entrega.ejercicio_estados`.

### Paso 6 — Eliminar `ejercicio_orden` del request (futuro)

Cuando todos los frontends estén migrados (1-2 releases después), remover `ejercicio_orden` del request del endpoint `POST /episodes`. El payload del CTR sigue teniendo ambos campos por las razones de denormalización explicadas.

### Paso 7 — Smoke E2E

Test en `tests/e2e/smoke/test_ctr_ejercicio_id_e2e.py`:
- Abrir episodio con `ejercicio_id`.
- Verificar que el evento `episodio_abierto` en `ctr_store.events` tiene ambos campos poblados y consistentes.
- Verificar que `self_hash` matchea la fórmula canónica determinista.
- Verificar que el evento se clasifica correctamente sin alterar el `classifier_config_hash`.

## Riesgos identificados

- **Inconsistencia productor**: si el tutor-service emite un evento con `ejercicio_id` no-None y `ejercicio_orden` None (o viceversa), queda un evento en append-only que es inconsistente para siempre. **Mitigación**: assert explícito en el productor + test unit dedicado.
- **Drift entre snapshot y estado actual**: documentar en `CLAUDE.md` que el `ejercicio_orden` en payloads es snapshot inmutable, no espejo. Cualquier futuro dashboard que muestre "el orden del ejercicio" debe decidir si lee del payload (verdad histórica) o de `tp_ejercicios` (verdad actual). Por defecto, para análisis longitudinal: payload.
- **Versionado de Ejercicio (ADR-047 deuda diferida)**: si un ejercicio se versiona (clonado con `parent_ejercicio_id`), el `ejercicio_id` del payload sigue apuntando al UUID que el estudiante vio. La trazabilidad se preserva. Las queries que quieran "todos los episodios sobre cualquier versión de ejercicio E1" requieren resolver la cadena `parent_ejercicio_id` — fuera de scope de este ADR.
- **Compatibilidad temporal del endpoint**: durante la transición de 1 release, el endpoint acepta ambos parámetros. Frontends viejos que envíen solo `ejercicio_orden` reciben un warning loggeado y el tutor-service resuelve `ejercicio_id` via `tp_ejercicios` para construir el payload completo. Eliminar la compat después de migrar frontends.

## Referencias

- ADR-010 — CTR append-only (invariante respetado).
- ADR-016 — Episode.problema_id = instancia, no template (invariante respetado).
- ADR-020 — n_level derivado en lectura (patrón de "no contaminar el payload" — este ADR justifica una excepción consciente: `ejercicio_id` NO es derivable, es identidad).
- ADR-047 — Ejercicio como entidad de primera clase reusable (provee el UUID).
- ADR-048 — Schema pedagógico del Ejercicio.
- `packages/contracts/src/platform_contracts/ctr/events.py` — definición de `EpisodioAbiertoPayload`.
- `apps/ctr-service/src/ctr_service/services/producer.py` — productor del CTR.
- CLAUDE.md sección "Propiedades críticas (invariantes del sistema)" — reproducibilidad bit-a-bit.
