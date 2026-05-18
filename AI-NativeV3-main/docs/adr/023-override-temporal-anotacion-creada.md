# ADR-023 — Override semántico de `anotacion_creada` en el labeler N1-N4 (heurística temporal v1.1.0)

- **Estado**: Aceptado
- **Fecha**: 2026-04-29
- **Deciders**: Alberto Cortez, director de tesis
- **Tags**: classifier, instrumentación, tesis, labeler
- **Extiende**: ADR-020 (etiquetador derivado en lectura).
- **Cierra**: G8a del audi2.md (variante heurística simple — la opción ligera del trifecta G8a/G8b/G8c).

## Contexto y problema

[`event_labeler.py`](../../apps/classifier-service/src/classifier_service/services/event_labeler.py) etiquetaba `anotacion_creada` como **N2 fijo** en v1.0.0. La Tabla 4.1 de la tesis vigente asigna las anotaciones a:

- **N1** (Comprensión y planificación): "notas tomadas; reformulación verbal en el asistente" — cuando ocurren durante la lectura del enunciado.
- **N4** (Apropiación): "apropiación de argumento; reproducción razonada de una explicación del asistente en producción posterior propia" — cuando ocurren tras una respuesta del tutor.

El docstring del labeler reconocía el gap explícitamente como decisión de implementación. Pero el efecto operacional es que `time_in_level` y `n_level_distribution` producían un sesgo sistemático: sub-reporta N1 y N4, sobre-reporta N2. Esa es exactamente la métrica que la Sección 15.6 de la tesis declara como **gap pendiente** ("operacionalización de CT v1.0.0 no implementa la proporción de tiempo por nivel N1–N4 por dependencia de la instrumentación completa de eventos") — pero al cerrar el gap con N2 fijo, introducíamos un sesgo nuevo no declarado.

audi2.md G8 propuso tres niveles de fix: G8a heurístico temporal simple (~30 LOC), G8b heurístico léxico (~80 LOC + corpus), G8c clasificación semántica con embeddings (~200 LOC, agenda Eje B).

## Drivers de la decisión

- **Cerrar el sesgo más obvio antes de defensa** sin introducir dependencias nuevas (embeddings, corpus etiquetado, integración con `ai-gateway`).
- **Reproducibilidad bit-a-bit preservada por construcción**: bumpear `LABELER_VERSION` re-etiqueta históricos sin tocar el CTR (ADR-020 cubre el patrón).
- **Honestidad metodológica**: el override es heurístico; no debe presentarse como verdad académica. La operacionalización debe ser declarable como tal en el ADR y en la tesis.
- **Backward-compat de la API pública**: callers que no tienen el episodio entero a mano (tests directos, código legacy) no deben ver cambio de comportamiento.

## Opciones consideradas

### G8a — heurístico temporal (elegida)

Override por **posición temporal en el episodio**:

- Anotación dentro de los primeros `ANOTACION_N1_WINDOW_SECONDS` (default **120s**) desde `episodio_abierto` → **N1**.
- Anotación dentro de `ANOTACION_N4_WINDOW_SECONDS` (default **60s**) post `tutor_respondio` → **N4**.
- Otros casos → **N2** (fallback v1.0.0).

Si las dos ventanas se solapan: **N4 gana**. Pedagógicamente "apropiación tras respuesta del tutor" es más informativo que "lectura inicial".

LOC efectivo: ~150 (incluye dataclass `EpisodeContext`, helper `_build_event_contexts`, hilo del contexto a través de `time_in_level` / `n_level_distribution`, 7 tests nuevos).

### G8b — heurístico léxico

Reglas regex sobre el contenido de la anotación. Patrones tipo "no entendí…" / "leyendo…" → N1; "ahora me doy cuenta…" / "siguiendo lo que el tutor explicó…" → N4.

**Descartada para pre-defensa porque**: requiere validación κ contra juicio docente sobre subset etiquetado a mano (mismo protocolo que el clasificador N4, Capítulo 14). Sin esa validación el corpus regex es un decisión arbitraria con apariencia de rigor — peor que declararlo como heurística temporal honesta.

### G8c — semántico vía embeddings

Enviar la anotación + contexto al `ai-gateway`, clasificar contra prototipos N1/N2/N4. Requiere endpoint nuevo en ai-gateway, integración con budget tracking, decisión de modelo.

**Descartada para pre-defensa porque**: alcance de Eje B post-defensa. Tiene mismas restricciones que G14 (CCD semántico, ADR-017 reservado).

## Decisión

**G8a** — heurística temporal con override **opt-in via `EpisodeContext`**. `LABELER_VERSION` 1.0.0 → **1.1.0**.

### API y semántica

```python
def label_event(
    event_type: str,
    payload: dict[str, Any] | None = None,
    context: EpisodeContext | None = None,
) -> NLevel:
    ...
```

- **Sin `context`** → comportamiento v1.0.0 puro (N2 fijo). Útil para tests y callers que no tienen el episodio entero.
- **Con `context`** → aplica override v1.1.0.

`time_in_level()` y `n_level_distribution()` construyen contextos automáticamente desde la lista de eventos vía `_build_event_contexts()`. Los caminos del piloto (analytics-service `/n-level-distribution`, classifier pipeline) usan el override.

### Consistencia entre conteos y duraciones

Ambos `time_in_level` y `n_level_distribution` usan los mismos contextos pre-computados → mismo evento → mismo nivel para conteo Y duración. Anti-regresión cubierta por `test_n_level_distribution_aplica_override_temporal_de_anotacion`.

### Constantes inmutables

| Constante | Valor v1.1.0 | Justificación |
|---|---|---|
| `ANOTACION_N1_WINDOW_SECONDS` | 120.0 | Tiempo razonable de "lectura inicial" del enunciado antes de empezar a editar código. Validable con análisis empírico del piloto. |
| `ANOTACION_N4_WINDOW_SECONDS` | 60.0 | Ventana de "apropiación inmediata" post-respuesta. Más conservadora que la N1 porque las anotaciones reflexivas tienden a ser cercanas a la respuesta del tutor. |

Cambiar cualquiera de estos valores obliga a bumpear `LABELER_VERSION` y a re-etiquetar reportes empíricos del piloto.

## Consecuencias

### Positivas

- **Cierra el sesgo sistemático sub-reporta-N1/sobre-reporta-N2** que introducía la asignación fija de v1.0.0. El reporte empírico del piloto refleja la distribución pedagógica más fiel a la Tabla 4.1.
- **Reproducibilidad bit-a-bit preservada**: el `LABELER_VERSION="1.1.0"` se propaga en cada `n_level_distribution()` response y en cada `Classification.classifier_config_hash` (vía `tree_version` + `profile`). Históricos pre-bump siguen reproducibles recomputando con v1.0.0.
- **Backward-compat de la API**: 21 tests pre-existentes del labeler pasan sin cambios. Solo cambian los tests que **explícitamente** verifican el override (tests nuevos) y el sanity check de `LABELER_VERSION` (que ahora exige minor ≥ 1).
- **Cero impacto en CTR / contracts / Pydantic / TS**: el labeler es derivado en lectura (ADR-020).
- **Heurística declarable**: el ADR documenta "es heurística temporal, no verdad académica" — el comité doctoral puede evaluar la operacionalización sin sorpresas.

### Negativas / trade-offs

- **Las ventanas (120s / 60s) son arbitrarias**: la elección no surge de validación empírica ex-ante. Mitigación: el ADR las documenta explícitamente; el análisis de sensibilidad se ejecuta con `scripts/g8a-sensitivity-analysis.py` sobre corpus sintético (ver [`023-sensitivity-analysis.md`](./023-sensitivity-analysis.md), seed=42, 2000 episodios). Resultados clave:
  - Estrechar N1 a 60s reduce `anotaciones_N1` en **-52.7%** vs baseline — el sesgo sub-reporta-N1 reaparece.
  - Ampliar N1 a 180s agrega **+2.5%** vs baseline — saturación por la mezcla de eventos del corpus.
  - Ampliar N4 a 120s aumenta `anotaciones_N4` en **+9.1%** vs baseline — anotaciones reflexivas con latencia 60-120s post-`tutor_respondio` quedan en N2 con la ventana actual.
  - El ratio total de tiempo por nivel es **insensible** a la elección de ventanas (anotaciones son fracción pequeña del total de eventos por episodio). El override afecta principalmente la asignación de anotaciones, no la composición global.
  - El reporte empírico del piloto-1 debe re-ejecutar este análisis sobre corpus real al cierre del cuatrimestre.
- **Detecta posición pero no contenido**: una anotación tipo "hola" en los primeros 120s queda etiquetada N1 por la ventana, aunque el contenido no sea reflexivo. La validación semántica queda en agenda Eje B (G8b o G8c, ADR futuro).
- **Solapes resueltos arbitrariamente**: cuando una anotación está dentro de ambas ventanas (N1 por reciencia al `episodio_abierto` Y N4 por reciencia al `tutor_respondio`), la regla "N4 gana" es declaración pedagógica del piloto. Documentada en el módulo y en este ADR.

### Neutras

- El `episodio_abandonado` (ADR-025) sigue siendo `meta`. El override solo aplica a `anotacion_creada`.
- El override usa el mismo patrón de "data class + función pura" que ya tenía el labeler — sin nuevas dependencias.

## Coordinación con piloto

- **Cutover**: el bump v1.1.0 implica que **reportes pre y post** tienen distribuciones N1/N2/N4 distintas para los mismos episodios crudos. El reporte empírico **debe declarar la versión** activa en el período (principio P6 de la tesis 21.4).
- **Mid-cohort**: aplicable en cualquier momento — no afecta runtime del tutor ni del CTR. La re-clasificación con la nueva versión es un cómputo derivado del CTR.

## Ejes de la agenda confirmatoria que NO cierra

- **G8b** (heurístico léxico) — sigue como agenda. Requiere validación κ contra juicio docente.
- **G8c** (semántico vía embeddings) — agenda Eje B. Misma restricción que G14 (CCD semántico, ADR-017 reservado).

## Referencias

- audi2.md G8 — trifecta G8a/G8b/G8c con recomendación G8a antes de defensa.
- ADR-020 — etiquetador N1-N4 derivado en lectura. Cubre la convención de bump de `LABELER_VERSION`.
- Tesis Tabla 4.1 — asignación pedagógica de las anotaciones a N1/N4 según contexto.
- Tesis Sección 15.6 — declaración del gap del time-in-level.
- Tesis Sección 17.3 — sesgo sistemático del labeler v1.0.0 (a actualizar para reflejar v1.1.0).
- Tesis Sección 19.5 — gap pendiente de override por contenido (sigue vigente para Eje B).
- Tests: `apps/classifier-service/tests/unit/test_event_labeler.py` (32 tests pasando, 7 nuevos del override v1.1.0).
- Tests críticos pre-existentes que NO se rompen: `test_pipeline_reproducibility.py` (auditabilidad bit-a-bit del clasificador).
