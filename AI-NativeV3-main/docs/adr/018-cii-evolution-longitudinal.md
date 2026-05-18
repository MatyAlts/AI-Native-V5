# ADR-018 — CII evolution longitudinal: medir mejora del estudiante entre episodios análogos

- **Estado**: Accepted
- **Fecha**: 2026-04-27 (propuesto), 2026-05-08 (promovido a Accepted tras verificación bidireccional tesis-código)
- **Deciders**: Alberto Alejandro Cortez, director de tesis
- **Tags**: clasificador, analytics, tesis, piloto-UNSL

## Contexto y problema

La tesis declara en la **Sección 15.4** que la **Coherencia Inter-Iteración (CII)** es:

> "estabilidad de los criterios y patrones aplicados por el estudiante a través de problemas análogos... requiere observación longitudinal y no puede ser evaluada desde un único episodio."

**Verificación empírica (audit `audi1.md` G2, confirmada 2026-04-27)**:

- `apps/classifier-service/src/classifier_service/services/cii.py` calcula dos métricas que se **llaman** `cii_stability` y `cii_evolution` pero son **intra-episodio**: similitud Jaccard entre prompts consecutivos del mismo episodio, slope de longitud de prompts del mismo episodio.
- **No hay nada longitudinal** — no se cruzan episodios distintos del mismo estudiante.
- El nombre `cii_*` es engañoso: lo que mide es **focus intra-episodio**, no **estabilidad longitudinal**.

**Consecuencia**: la **hipótesis H2 de la tesis** ("asociación entre coherencia estructural y juicio docente longitudinal") **no es testeable empíricamente** con el código actual. La Sección 15.4 queda como promesa retórica.

Fuerzas en juego:

1. **NO renombrar `cii_stability` y `cii_evolution`**: son BC-incompatible. Eventos `clasificacion_emitida` históricos del piloto y exports académicos ya tienen estos nombres. Renombrar rompe consumers.
2. **NO requerir migration Alembic**: el modelo `Classification` ya tiene `features: JSONB` (`Mapped[dict[str, Any]]`). Cualquier campo nuevo va ahí sin tocar el schema.
3. **Definición de "problemas análogos" debe ser objetiva**: con ADR-016 (TareaPracticaTemplate), tenemos un identificador canónico — dos `TareaPractica` con el mismo `template_id` son instancias del mismo problema lógico. Sin template, no podemos discriminar análogos vs distintos.
4. **N mínimo para calcular slope**: 3 episodios. Con 2 episodios el slope es trivial (línea entre 2 puntos), con 1 indefinido.
5. **Apropiación es ordinal, NO cardinal**: `delegacion_pasiva (0) < apropiacion_superficial (1) < apropiacion_reflexiva (2)`. Calcular slope cardinal sobre estos números **es una operacionalización**, no una verdad — se documenta como tal.

## Drivers de la decisión

- **D1** — Cumplir promesa Sección 15.4 con observación longitudinal real, NO simular con datos intra-episodio.
- **D2** — **NO BC-break**: `cii_stability` y `cii_evolution` siguen siendo lo que son hoy (intra-episodio). El nuevo cálculo se llama distinto y vive en otro lugar.
- **D3** — **NO migration Alembic**: usar `Classification.features['cii_evolution_longitudinal']` como JSONB.
- **D4** — Solo lo mínimo defendible: `cii_evolution_longitudinal` (slope ordinal de apropiación). NO `cii_criteria_stability` ni `cii_transfer_effective` (Sección 15.4 los sugiere pero requieren NLP del contenido — agenda futura).
- **D5** — Definición operacional de "análogos" reproducible: misma `template_id`. Si `template_id` es NULL (TP huérfana pre-ADR-016), el episodio NO entra en el cálculo (declarado como limitación).
- **D6** — Función pura aislable, testeable sin DB: el cálculo del slope vive en `packages/platform-ops/`, igual que `compute_cohen_kappa` y `build_trajectories`.

## Opciones consideradas

### Opción A — `cii_evolution_longitudinal` por template, slope sobre `APPROPRIATION_ORDINAL` (elegida)

Para cada estudiante con N≥3 episodios cerrados sobre el mismo `template_id`:
1. Ordenar episodios por `classified_at` ascendente.
2. Mapear cada `appropriation` → score ordinal (0/1/2) vía `APPROPRIATION_ORDINAL` (ya existe en `platform_ops.longitudinal`).
3. Calcular slope vía regresión lineal simple (mismo algoritmo que el `cii_evolution` intra-episodio actual, pero sobre datos longitudinales en lugar de prompts del mismo episodio).
4. Slope > 0 = el estudiante **mejora** sobre ese problema lógico a lo largo del piloto.
5. Si el estudiante tiene episodios de varios templates (ej. TP1 + TP3 ambos sobre "recursión"), se calcula UN slope por template. El slope agregado del estudiante (`mean_slope`) es el promedio de slopes con N≥3.

Ventajas:
- Implementación pequeña (~80 LOC + tests).
- Reusa código existente: `APPROPRIATION_ORDINAL`, `RealLongitudinalDataSource`, el patrón de `build_trajectories`.
- BC-compatible: cero cambio a tablas existentes.
- Función pura → testeable bit-exact con golden inputs.
- Defendible academicamente: el slope es la operacionalización más simple de "evolución" sobre datos ordinales.

Desventajas declaradas:
- Episodios sin `template_id` (TPs huérfanas) NO entran. Para el piloto inicial UNSL **es aceptable**: los TPs nuevos se crean desde templates (ADR-016 lo documenta como flujo principal). TPs huérfanas legacy del periodo de transición no contribuyen a CII longitudinal.
- N=3 es mínimo arbitrario pero defensible (tesis dice "longitudinal" sin especificar mínimo; con N=2 el slope es trivial).
- Slope cardinal sobre datos ordinales es operacionalización conservadora — el ADR lo declara como tal, no como verdad académica.

### Opción B — Renombrar `cii_*` a `iis_*` y agregar todos los `cii_*` longitudinales (descartada para versión mínima)

Lo que el audit G2 propone como versión completa:
- Renombrar `cii_stability/cii_evolution` → `iis_stability/iis_evolution` (Iteration-Internal-Stability).
- Agregar `cii_criteria_stability`, `cii_transfer_effective`, `cii_evolution_longitudinal`.

Ventajas: nombres alineados con la tesis. Cobertura completa.

Desventajas que la descartan PARA VERSIÓN MÍNIMA:
- **BC-break grande**: toca classifications históricas, exports académicos, dashboards, contracts.
- `cii_criteria_stability` requiere NLP del contenido de prompts (qué patrones se aplican), eso es del nivel de G1 (embeddings) — out of scope.
- `cii_transfer_effective` requiere clasificar feedback del docente, no implementado.
- Calendario: ~2 semanas vs ~3-4 días.

**Diferido a piloto-2** con ADR sucesor cuando se implemente G1 (embeddings).

### Opción C — Migration Alembic con columna nueva `cii_evolution_longitudinal: Float` (descartada)

Agregar columna nullable nueva en `classifications`.

Ventajas: queryable por SQL directo (sin JSONB selector).

Desventajas que la descartan:
- Requiere migration Alembic + revisión de exports.
- `Classification.features: JSONB` ya está pensado para esto (campo "extras explicabilidad").
- Si la métrica se descarta o se renombra en piloto-2, dejamos columna huérfana.

### Opción D — Diferir / declarar como agenda futura

NO implementar nada para piloto-1, mantener Sección 15.4 como aspiracional.

Descartada por la misma razón que G3/G4/G5: H2 es la **hipótesis central** de la tesis sobre longitudinalidad. Sin esto, H2 no se prueba empíricamente.

## Decisión

**Opción A — `cii_evolution_longitudinal` por `template_id`, slope sobre `APPROPRIATION_ORDINAL`, persistido en `Classification.features: JSONB`.**

### Operacionalización exacta

Para un estudiante S y un `template_id` T, sea `episodes_S_T` la lista de episodios cerrados de S apuntando a TPs con `template_id = T`, ordenados por `classified_at` ascendente. Sea N = `len(episodes_S_T)`.

Si N < 3:
- `cii_evolution_longitudinal` para (S, T) **NO se computa** (`null` / `insufficient_data: true`).

Si N ≥ 3:
- Para cada episodio: `score_i = APPROPRIATION_ORDINAL[appropriation_i]` ∈ {0, 1, 2}.
- `xs_i = i` (índice 0-based).
- Slope (regresión lineal):
  ```
  mean_x = mean(xs)
  mean_y = mean(scores)
  num = sum((xs[i] - mean_x) * (scores[i] - mean_y) for i)
  den = sum((xs[i] - mean_x) ** 2 for i)
  slope = num / den if den > 0 else 0.0
  ```
- Slope crudo (sin normalizar). Rango teórico: `[-1.0, +1.0]` (en piloto típico con N=3..10 episodios).
- **NO se normaliza a [0, 1]** como hace el `cii_evolution` intra-episodio del `cii.py` actual. Razón: el slope crudo es interpretable directamente como "cuántas categorías ordinales sube por episodio en promedio". Normalizar pierde esa interpretación.

### Agregación a nivel estudiante

Para un estudiante S con K templates donde N≥3:
- `mean_slope_S = mean(slope_per_template) for templates with N >= 3`.
- Si K = 0 (ningún template con N≥3), `mean_slope_S = null`.
- Templates con N<3 se reportan en el output con `slope: null`, NO se incluyen en el promedio.

### Persistencia (BC-compatible)

`Classification.features['cii_evolution_longitudinal']` se popula con un dict:

```json
{
  "template_id": "<uuid>",
  "n_episodes_in_group": 4,
  "scores_ordinal": [0, 1, 1, 2],
  "slope": 0.5,
  "labeler_version": "1.0.0"
}
```

**Decisión clave**: esto **NO se computa en el classifier-service por evento individual** — no tiene sentido, requiere el conjunto de classifications del estudiante. **Se computa ON-DEMAND en el endpoint analytics** o en un job batch nightly.

Por lo tanto: el `Classification.features['cii_evolution_longitudinal']` **se popula opcionalmente** post-clasificación inicial, cuando el job/endpoint corre. Si nunca corre, el campo está ausente — no es bug, es trabajo deferido.

### Endpoint nuevo

`GET /api/v1/analytics/student/{student_pseudonym}/cii-evolution-longitudinal?comision_id=X` (filtros opcionales por `materia_id`, `periodo_id`).

Response shape:
```json
{
  "student_pseudonym": "<uuid>",
  "comision_id": "<uuid>",
  "n_groups_evaluated": 2,
  "n_groups_insufficient": 1,
  "n_episodes_total": 8,
  "evolution_per_template": [
    {
      "template_id": "<uuid>",
      "n_episodes": 4,
      "slope": 0.5,
      "scores_ordinal": [0, 1, 1, 2]
    },
    {
      "template_id": "<uuid>",
      "n_episodes": 3,
      "slope": -0.5,
      "scores_ordinal": [2, 1, 1]
    },
    {
      "template_id": "<uuid>",
      "n_episodes": 2,
      "slope": null,
      "scores_ordinal": [0, 1],
      "insufficient_data": true
    }
  ],
  "mean_slope": 0.0,
  "sufficient_data": true,
  "labeler_version": "1.0.0"
}
```

Auth: `X-Tenant-Id` + `X-User-Id` (mismo patrón que el resto de los endpoints analytics, alineado con FIX 4 de la revisión 2026-04-27).

Modo dev (sin CTR_STORE_URL + CLASSIFIER_DB_URL): devuelve estructura vacía con 200, mismo patrón que `/cohort/progression` y `/n-level-distribution`.

### Naturaleza de la métrica

**Slope cardinal sobre datos ordinales** — operacionalización conservadora, no verdad académica. El `mean_slope` agregado tiene la misma limitación que la severidad de guardrails (ADR-019): **es ordinal/orientativo, NO cardinal**. Reportar comparativas estudiante-a-estudiante (ranking) tiene sentido; promediar slopes de toda la cohorte para sacar "el slope promedio del piloto" tiene sentido limitado y debe interpretarse con cuidado en la tesis.

## Consecuencias

### Positivas

- **Cumple Sección 15.4 con observación longitudinal real**: H2 es testeable empíricamente.
- **Cero BC-break**: `cii_stability/cii_evolution` siguen como están. Schema sin tocar. Exports compatibles.
- **Cero migration Alembic**: `features: JSONB` absorbe el campo nuevo.
- **Reuso máximo de código**: `APPROPRIATION_ORDINAL`, `RealLongitudinalDataSource`, patrón de `/cohort/progression` ya existen.
- **Testeable bit-exact**: función pura con golden inputs (mismo patrón que `event_labeler` de ADR-020).
- **Aprovecha ADR-016**: `template_id` da definición canónica de "problemas análogos" — sin este ADR, G2 mínimo NO sería posible sin migration adicional.

### Negativas / trade-offs

- **TPs huérfanas (sin `template_id`) NO entran al cálculo**. Mitigación: documentar como limitación del piloto inicial. En piloto-2, cuando todos los TPs tengan templates, no hay caso edge.
- **Se calcula on-demand, no se persiste eagerly**. Si el endpoint NO se llama, el `features['cii_evolution_longitudinal']` queda vacío. Aceptable para el piloto: el dashboard del docente lo computa al renderizar.
- **N=3 es mínimo arbitrario**. Estudiantes con 1-2 episodios (caso real al inicio del piloto) NO tienen señal longitudinal. Es esperado y correcto — la tesis Sección 15.4 dice "longitudinal" justamente para excluir cohortes con poca data.
- **Slope cardinal sobre datos ordinales** es operacionalización debatible. Defendible si se documenta como tal. Alternativas (Spearman rank correlation, Mann-Kendall trend test) son más robustas estadísticamente pero requieren más código. Diferidas a piloto-2 si el comité doctoral las pide.
- **No cubre `cii_criteria_stability` ni `cii_transfer_effective`** (Sección 15.4 los sugiere). Declarado explícitamente como agenda futura del Cap 20.

### Neutras

- **NO requiere cambios al `tutor-service`** ni al `ctr-service`. El cálculo es retrospectivo sobre clasificaciones existentes.
- **NO requiere cambios al `classifier-service` per-episodio** (no se calcula al clasificar individualmente).
- **NO requiere cambios a Casbin** (mismo recurso `episode:read` que `/cohort/progression`).
- **NO requiere cambios al frontend** todavía. La UI que consume este endpoint es G7 (dashboard docente), agenda futura.

## API BC-breaks

Ninguno. Endpoint nuevo. `Classification.features` extendido sin romper consumers (es JSONB con `Any`).

## Tasks de implementación

1. **`packages/platform-ops/src/platform_ops/cii_longitudinal.py`** (nuevo, ~80 LOC):
   - Función `compute_evolution_per_template(classifications: list[dict]) -> dict[UUID, dict]`. Recibe lista de clasificaciones con `template_id` y `appropriation`, agrupa por template, calcula slope.
   - Función `compute_mean_slope(per_template: dict) -> float | None`. Promedia slopes de templates con N≥3.
   - Constante `MIN_EPISODES_FOR_LONGITUDINAL = 3`.
   - Reusa `APPROPRIATION_ORDINAL` de `longitudinal.py`.

2. **Tests `packages/platform-ops/tests/test_cii_longitudinal.py`** (nuevo):
   - Golden cases: N<3 → null; N=3 mejorando → slope > 0; N=3 empeorando → slope < 0; N=3 estable → slope = 0.
   - Estudiante con múltiples templates → un slope por template.
   - Estudiantes sin classifications → estructura vacía.
   - Test de orden temporal (input desordenado → mismo resultado).

3. **Extender `RealLongitudinalDataSource`** (`packages/platform-ops/src/platform_ops/real_datasources.py`):
   - Modificar `list_classifications_grouped_by_student` para incluir en cada dict `episode["problema_id"]` y `episode["template_id"]`.
   - Cross-DB: agregar query a `academic_main` (vía `academic-service` HTTP o DB directa — TBD durante implementación).
   - Alternativa simpler: agregar método nuevo `list_classifications_with_templates_grouped_by_student(comision_id)` que hace el cross-reference. Mantener el método viejo intacto para no romper `/cohort/progression`.

4. **Endpoint en `analytics-service`** (`apps/analytics-service/src/analytics_service/routes/analytics.py`):
   - `GET /api/v1/analytics/student/{student_pseudonym}/cii-evolution-longitudinal?comision_id=X`.
   - Auth: `X-Tenant-Id` + `X-User-Id` (alineado con FIX 4).
   - Modo dev: estructura vacía (mismo patrón que `/cohort/progression`).
   - Modo real: dual session + `set_tenant_rls` + nuevo método del DataSource + función pura.

5. **Tests del endpoint** (`apps/analytics-service/tests/unit/test_cii_evolution_longitudinal_endpoint.py`):
   - Sin headers → 401.
   - Headers válidos en modo dev → 200 con estructura vacía.
   - UUID inválido en path → 422.

6. **Documentación**:
   - `CLAUDE.md`: agregar invariante "CII evolution longitudinal: persistido en `Classification.features['cii_evolution_longitudinal']` (BC-compatible, no requiere migration). Definición de problemas análogos via `template_id` (ADR-018)".
   - `reglas.md`: agregar `RN-130` (CII longitudinal por template_id, N>=3).
   - `SESSION-LOG.md`: entrada con G2 mínimo cerrado.

## Referencias

- ADR-016 (TareaPracticaTemplate) — `template_id` da la definición canónica de "problemas análogos".
- ADR-010 (append-only) — `Classification.features` es campo append-only via JSONB; bumping del campo NO requiere `is_current=false` en filas viejas (es metadata, no clasificación).
- ADR-019 (guardrails Fase A) — patrón de "severidad ordinal, NO cardinal" aplica también acá.
- ADR-020 (event_labeler) — patrón de "función pura testeable + endpoint analytics" se replica.
- Tesis Sección 15.4 — define CII longitudinal.
- Tesis Sección 15.2 — el `cii_evolution` intra-episodio actual responde a esto, NO al longitudinal.
- `apps/classifier-service/src/classifier_service/services/cii.py` — código actual (intra-episodio), NO se toca.
- `packages/platform-ops/src/platform_ops/longitudinal.py:35-39` — `APPROPRIATION_ORDINAL` reusable.
- `packages/platform-ops/src/platform_ops/real_datasources.py:137-217` — `RealLongitudinalDataSource` a extender.
- `apps/analytics-service/src/analytics_service/routes/analytics.py:289-367` — patrón de `/cohort/progression`.
- `audi1.md` G2 — análisis de auditoría que motivó este ADR.
