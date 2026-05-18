# ADR-020 — Etiquetador de eventos por nivel analítico N1–N4 (componente C3.2)

- **Estado**: Accepted
- **Fecha**: 2026-04-27 (propuesto), 2026-05-08 (promovido a Accepted tras verificación bidireccional tesis-código)
- **Deciders**: Alberto Alejandro Cortez, director de tesis
- **Tags**: clasificador, observabilidad, tesis, CTR, piloto-UNSL

## Contexto y problema

La tesis declara en la **Sección 4.3** que cada evento del CTR pertenece a uno de los niveles analíticos **N1–N4** (más "meta" para apertura/cierre/abandono de episodio):

- **N1 — Comprensión y planificación**: lectura del enunciado, anotaciones de planificación.
- **N2 — Elaboración estratégica**: escritura/edición de código, decisiones de diseño.
- **N3 — Validación**: ejecución de código, tests.
- **N4 — Interacción con IA**: prompts al tutor, respuestas recibidas, copias de código del tutor.
- **meta**: apertura/cierre/abandono del episodio.

La **Sección 6.4** describe el componente arquitectónico **C3.2 ("Etiquetador de eventos")**: "aplica reglas de primer orden para etiquetar cada evento del CTR con un nivel N1–N4 (o «no clasificable»)". La **Sección 15.2** habla de **proporción de tiempo por nivel** como dimensión central de la Coherencia Temporal (CT).

**En el código no existe nada de esto.** Verificación contra `apps/ctr-service/src/ctr_service/models/event.py:80-143`: el modelo `Event` tiene `event_type`, `payload`, `self_hash`, `chain_hash`, etc. **No hay campo `n_level`**, ni view derivada, ni tabla paralela, ni módulo `event_labeler.py` en classifier-service. El mapping `event_type → N1/N2/N3/N4` es **implícito** — vive en la cabeza del autor.

Consecuencias de este gap:

1. **No se puede calcular "tiempo en N1 vs N2"** que la tesis Sección 15.2 promete como dimensión central de CT.
2. **Análisis empírico del piloto pierde una dimensión central** — el dashboard docente del Capítulo 4 ("Acceso al proceso, no solo al producto") asume el etiquetado.
3. **El componente C3.2 es retórico** — declarado en la arquitectura pero ausente del código.

Fuerzas en juego:

1. **Reproducibilidad bit-a-bit** (CLAUDE.md "Constantes que NO deben inventarse"): el `self_hash` de eventos del CTR usa `event.model_dump_json(exclude={"self_hash","chain_hash"})`. Cualquier campo agregado al payload **modifica el hash de eventos nuevos** y rompe simetría con eventos históricos del piloto.
2. **Append-only** (ADR-010): ni siquiera por bug se reescriben eventos. El etiquetado debe ser idempotente y reversible (poder cambiar las reglas de etiquetado sin tocar la cadena criptográfica).
3. **Reglas de etiquetado pueden evolucionar**: el corpus de patrones de la tesis puede refinarse en piloto-2. Hay que poder versionar las reglas sin romper datos históricos.
4. **Algunos eventos no son uniformes**: `anotacion_creada` puede ser N1 (planificar), N2 (estrategia), o N4 (reaccionar a tutor) según contenido. La tesis Tabla 4.1 lo reconoce explícitamente.
5. **`edicion_codigo` ya tiene granularidad útil**: el payload incluye `origin: "student_typed" | "copied_from_tutor" | "pasted_external" | None` (`packages/contracts/src/platform_contracts/ctr/events.py:147-149`). Una edición copiada del tutor es semánticamente N4, no N2.

## Drivers de la decisión

- **D1** — Cumplir promesa Sección 4.3 + 6.4 C3.2 + 15.2 sin agregar deuda retórica adicional.
- **D2** — **NO** modificar el `self_hash` ni el payload de los eventos. Cadena criptográfica intacta.
- **D3** — Reglas versionables sin re-hashear el CTR. Si en piloto-2 cambian las reglas, los datos históricos se pueden re-etiquetar sin tocar el CTR.
- **D4** — Implementación pequeña y testeable. Coherente con la prioridad "G4 primero" del análisis de auditoría: ~200 LOC, 2 días reales.
- **D5** — Aprovechar la información que **ya está** en el payload (`EdicionCodigoPayload.origin`, `PromptEnviadoPayload.prompt_kind`) para etiquetar más finamente, sin pedir datos nuevos al frontend.

## Opciones consideradas

### Opción A — Derivar `n_level` en lectura (función pura sobre `event_type` + payload)

Función `label_event(event_type: str, payload: dict) -> NLevel` en `classifier-service/services/event_labeler.py`. **NO se almacena en la DB**. Cada vez que se necesita el nivel (analytics, dashboard), se recalcula.

Ventajas:
- Cero impacto en la cadena criptográfica. El `self_hash` no cambia. Eventos históricos quedan intactos.
- Reglas versionables trivialmente: bumpear `LABELER_VERSION` y todos los datos se re-etiquetan al próximo read.
- Cero migración. Cero ALTER TABLE.
- Test loop simple: input → output, función pura.

Desventajas:
- Latencia de cómputo en cada query analytics. Mitigable con cache si crece. Hoy con ~30 episodios y ~50 eventos/episodio = 1500 cálculos triviales — irrelevante.
- No queryable por SQL directo (`WHERE n_level='N4'`). Mitigable con view materializada en una iteración futura si hace falta.

### Opción B — Agregar `n_level` al payload del evento

Extender cada `*Payload` Pydantic con `n_level: NLevel`. El frontend o el productor del evento (tutor-service) lo setea al emitir.

Ventajas:
- Queryable por SQL.
- Una sola fuente de verdad — el evento dice su nivel.

Desventajas que la descartan:
- **ROMPE el `self_hash`**: agregar un campo al payload modifica el output de `model_dump_json` para eventos nuevos. Eventos viejos NO tienen el campo y siguen con su hash viejo (correcto). Pero **comparar hashes de eventos "del mismo tipo" antes/después** se vuelve ambiguo. Choca frontalmente con D2.
- **Acopla productor con clasificador**: el tutor-service (productor) tendría que saber del esquema de niveles N1-N4 (responsabilidad del classifier). Viola separación de planos del CLAUDE.md.
- Cambiar las reglas en piloto-2 = re-emitir eventos = rompe append-only.

### Opción C — Tabla paralela `event_labels`

Tabla nueva con `(event_uuid, n_level, labeler_version, computed_at)`. Append-only. Permite re-etiquetar con nueva versión de reglas sin tocar el CTR.

Ventajas:
- Queryable por SQL (con JOIN).
- Versionable sin romper hashes.
- Auditable: "este evento fue etiquetado N4 con labeler v1 y N3 con labeler v2".

Desventajas:
- Para un override de estudiante (caso `anotacion_creada` con clasificación manual) es la solución correcta — pero ese override **no está en esta iteración**.
- Complejidad de schema + migration + RLS + Casbin para un caso de uso que hoy no se ejerce.

## Decisión

**Opción A — derivación en lectura**, con tres aclaraciones:

1. **El módulo `event_labeler.py` es source of truth único** del mapping `event_type → n_level`.
2. **Se aprovecha `payload.origin` de `edicion_codigo`** y **`payload.prompt_kind` de `prompt_enviado`** para etiquetar más finamente (info ya disponible en el evento, no requiere cambios al payload).
3. **`anotacion_creada` se etiqueta como N2 fijo en esta iteración**. La tesis Tabla 4.1 sugiere que puede ser N1/N2/N4 según contenido — el override por estudiante o por NLP queda **diferido** (ver "Agenda futura"). N2 es el default más honesto: una anotación es típicamente reflexión estratégica.

### Mapping canónico

```python
# apps/classifier-service/src/classifier_service/services/event_labeler.py

NLevel = Literal["N1", "N2", "N3", "N4", "meta"]
LABELER_VERSION = "1.0.0"  # bumpea si cambian las reglas

EVENT_N_LEVEL_BASE: dict[str, NLevel] = {
    "episodio_abierto":     "meta",
    "episodio_cerrado":     "meta",
    "episodio_abandonado":  "meta",
    "lectura_enunciado":    "N1",
    "anotacion_creada":     "N2",   # default; override deferido
    "edicion_codigo":       "N2",   # override por origin abajo
    "codigo_ejecutado":     "N3",
    "prompt_enviado":       "N4",
    "tutor_respondio":      "N4",
}

# Override condicional por contenido del payload
def label_event(event_type: str, payload: dict) -> NLevel:
    base = EVENT_N_LEVEL_BASE.get(event_type)
    if base is None:
        return "meta"  # fallback conservador para event_types no conocidos
    if event_type == "edicion_codigo":
        origin = payload.get("origin")
        if origin in ("copied_from_tutor", "pasted_external"):
            return "N4"  # vino de afuera, es interacción IA o externa
        # student_typed o None (legacy) → N2
    return base
```

### Función `time_in_level`

```python
def time_in_level(events: list[Event]) -> dict[NLevel, float]:
    """Suma duración (en segundos) entre eventos consecutivos del mismo nivel.

    Asume eventos ordenados por seq. Para el último evento del episodio
    asume duración 0 (no hay siguiente para medir).
    """
    durations: dict[NLevel, float] = {"N1": 0, "N2": 0, "N3": 0, "N4": 0, "meta": 0}
    for current, next_ev in zip(events, events[1:]):
        level = label_event(current.event_type, current.payload)
        delta = (next_ev.ts - current.ts).total_seconds()
        durations[level] += delta
    return durations
```

### Endpoint analytics

`GET /api/v1/analytics/episode/{episode_id}/n-level-distribution` en `analytics-service`. Lee eventos del episodio del CTR, aplica `label_event` + `time_in_level`, devuelve:

```json
{
  "episode_id": "...",
  "labeler_version": "1.0.0",
  "distribution_seconds": {"N1": 120.5, "N2": 340.1, "N3": 88.0, "N4": 215.3, "meta": 0.0},
  "distribution_ratio":   {"N1": 0.16, "N2": 0.46, "N3": 0.12, "N4": 0.29, "meta": 0.0},
  "total_events_per_level": {"N1": 3, "N2": 12, "N3": 5, "N4": 8, "meta": 2}
}
```

Auth: `X-Tenant-Id` + `X-User-Id` headers (mismo patrón que `/cohort/{id}/progression`). Casbin: requiere `episode:read`.

## Consecuencias

### Positivas

- **Cumple Sección 4.3 + 6.4 C3.2 + 15.2** sin tocar la cadena criptográfica.
- **CTR-safe**: cero modificación al modelo `Event`, cero ALTER TABLE, cero migración. RN-034 / RN-036 / RN-039 / RN-040 intactas.
- **Reproducibilidad bit-a-bit preservada**: `classifier_config_hash` no cambia, `self_hash` no cambia, `chain_hash` no cambia. `test_pipeline_reproducibility.py` sigue verde sin tocar.
- **Versionable**: bumpear `LABELER_VERSION` re-etiqueta todo en lectura. El campo va en la respuesta del endpoint para que análisis empírico sepa con qué versión de reglas se generaron los datos.
- **Aprovecha info existente**: `origin` de `edicion_codigo` y (futuro) `prompt_kind` de `prompt_enviado` permiten etiquetado más rico sin tocar payload.
- **Habilita G7 (dashboard docente con drill-down N1-N4)** — dependencia explícita listada por el audit.

### Negativas / trade-offs

- **`anotacion_creada` queda con N2 fijo**. Pierde la riqueza que la tesis Tabla 4.1 sugiere ("depende del contenido"). **Mitigación**: declararlo como agenda futura (override por estudiante via UI, o por NLP cuando se implemente G1). El N2 default no es engañoso — es la operacionalización conservadora más honesta.
- **No queryable por SQL directo**: `SELECT count(*) FROM events WHERE n_level='N4'` no funciona. Hay que pasar por el endpoint o re-implementar el mapping en SQL. Aceptable hoy; si analítica masiva lo demanda, agregar view materializada en iteración posterior (no requiere ADR — es optimización).
- **Latencia de cómputo en cada read**: para episodios pequeños (< 100 eventos) es trivial. Para queries de cohorte (1000s de episodios) puede sumar — mitigable con cache en `analytics-service` (pattern del repo: Redis por tenant).
- **`labeler_version` debe propagarse**: si el endpoint cachea, la cache key debe incluir la versión. Si en algún momento se persiste el resultado (ej. dashboard pre-computado), versionar también.

### Neutras

- **NO requiere migración Alembic**.
- **NO requiere cambios en Casbin** (el endpoint nuevo reutiliza `episode:read` que ya existe).
- **NO requiere cambios en el frontend** para esta iteración. La UI con drill-down N1-N4 es G7 (ADR separado).
- **NO toca el tutor-service ni el ctr-service**. Solo classifier-service y analytics-service.
- **NO afecta el seed de Casbin** (108 policies actuales se mantienen).

## Agenda futura (NO en esta iteración)

Estos puntos quedan declarados como trabajo futuro. Cuando se aborden, requieren ADR propio:

1. **Override de `anotacion_creada` por estudiante**: agregar UI en `web-student` para que el estudiante etiquete manualmente N1/N2/N4 al crear anotación. Implementación natural: tabla paralela `event_labels` (Opción C de este ADR), append-only, indexada por `event_uuid`. Supersede parcialmente la regla N2 fija de este ADR.
2. **Clasificación automática de `anotacion_creada` por NLP**: requiere G1 (CCD con embeddings) primero. Cuando exista provider de embeddings, el labeler puede leer el `content` y derivar N1/N2/N4 por similitud con prototipos.
3. **Etiquetado de `intento_adverso_detectado`** (evento nuevo de G3): por default N4 con sub-tag "adversarial". Agregar al `EVENT_N_LEVEL_BASE` cuando el evento se cree.
4. **View materializada SQL** si analytics masiva lo demanda. Versionada con `labeler_version`.
5. **Tabla `event_labels` (Opción C)** si se ejerce el caso de override por estudiante o re-etiquetado histórico múltiple.

## API BC-breaks

Ninguno. Endpoint nuevo en namespace `/api/v1/analytics/episode/{id}/n-level-distribution`. No modifica respuestas existentes.

## Tasks de implementación (orden sugerido)

1. **Módulo `event_labeler.py`** (`apps/classifier-service/src/classifier_service/services/event_labeler.py`):
   - Constantes `NLevel`, `LABELER_VERSION`, `EVENT_N_LEVEL_BASE`.
   - Función `label_event(event_type: str, payload: dict) -> NLevel` con override para `edicion_codigo.origin`.
   - Función `time_in_level(events: list) -> dict[NLevel, float]`.
   - Función `n_level_distribution(events: list) -> dict` (combina ambas + `total_events_per_level` + ratios).
2. **Tests unitarios** (`apps/classifier-service/tests/unit/test_event_labeler.py`):
   - Cada `event_type` → nivel correcto.
   - `edicion_codigo` con cada valor de `origin` (4 casos: `student_typed`, `copied_from_tutor`, `pasted_external`, `None`).
   - `time_in_level` con episodio mixto: verifica suma == duración total.
   - `n_level_distribution` con episodio vacío (devuelve todo en cero).
   - `event_type` desconocido → `meta` (fallback).
   - Idempotencia: `label_event` es función pura, sin side-effects.
3. **Endpoint en `analytics-service`** (`apps/analytics-service/src/analytics_service/routes/analytics.py`):
   - `GET /api/v1/analytics/episode/{episode_id}/n-level-distribution`.
   - Auth via `X-Tenant-Id` + `X-User-Id` headers (`Depends`).
   - Lee eventos del CTR (vía `CTRClient` existente o consulta directa al `ctr-service` por HTTP).
   - Llama a `n_level_distribution()` del classifier-service. Si la dependencia HTTP es rebuscada, replicar la función en `analytics-service` (las reglas son triviales) — decisión de implementación a tomar al codear, no bloquea ADR.
4. **Test integration** (`apps/analytics-service/tests/integration/test_n_level_distribution.py`):
   - Episodio mockeado con N eventos → endpoint responde distribución correcta.
   - Episodio inexistente → 404.
   - Sin headers → 401.
5. **Wire-up en `api-gateway`**: agregar ruta al `ROUTE_MAP` en `apps/api-gateway/src/api_gateway/routes/proxy.py` para que `/api/v1/analytics/episode/{id}/n-level-distribution` proxee a analytics-service.
6. **Documentación**:
   - Actualizar `CLAUDE.md`: ADR count → 17, "numerar 018+", agregar invariante "n_level es derivado en lectura, NUNCA almacenado en payload" a "Propiedades críticas". Bumpear `Última verificación` a 2026-04-27.
   - Agregar entrada en `docs/SESSION-LOG.md` con fecha 2026-04-27 (sesión: implementación G4).
   - Sumar `RN-013ter` (o número que corresponda) en `reglas.md`: "El nivel analítico N1-N4 de cada evento del CTR se deriva en lectura por el etiquetador C3.2; no se almacena en el payload para preservar reproducibilidad bit-a-bit".

## Referencias

- ADR-010 (append-only clasificaciones) — el labeler NO modifica eventos; solo los lee.
- Tesis Sección 4.3 — define los niveles N1-N4.
- Tesis Sección 6.4 — describe el componente C3.2.
- Tesis Sección 15.2 — proporción de tiempo por nivel como dimensión de CT.
- Tesis Tabla 4.1 — mapping conceptual `event_type → n_level`.
- `packages/contracts/src/platform_contracts/ctr/events.py:22-177` — eventos del CTR vigentes.
- `packages/contracts/src/platform_contracts/ctr/events.py:143-154` — `EdicionCodigoPayload.origin` (utilizado por el override).
- `apps/classifier-service/src/classifier_service/services/pipeline.py` — pipeline existente al que se integra el labeler.
- `apps/analytics-service/src/analytics_service/routes/analytics.py` — patrón existente para endpoint nuevo.
- `audi1.md` G4 — análisis de auditoría que motivó este ADR (verificación empírica confirmada 2026-04-27 contra `apps/ctr-service/src/ctr_service/models/event.py:80-143`).
