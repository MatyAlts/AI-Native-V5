# Design doc — Sexta coherencia: estructural del código (R7 informeSoc.md)

**Versión**: 1.0.0 — propuesta de diseño, NO implementación
**Fecha**: 2026-05-16
**Autor**: derivado de informeSoc.md §3.3 (corpus actual sesgado a lo verbal)
**Estado**: design **bloqueado** por A1 (re-clasificación con DB real del piloto). Implementación NO debe arrancar antes de A1.

---

## 0. Por qué este diseño existe

informeSoc.md §3.3 identificó que las cinco coherencias actuales (CT, CCD_mean, CCD_orphan_ratio, CII_stability, CII_evolution) están sesgadas hacia la dimensión verbal: Jaccard léxico, pendiente léxica, alineamiento texto-código. La didáctica de la programación (Pausch, Soloway, Spohrer, Ben-Ari) muestra que la calidad del **plan** implícito en el código es predictor más fuerte de comprensión que las métricas verbales.

Una sexta coherencia —"Coherencia Estructural del Código" (CEC)— podría agregar esa dimensión sin colapsar con las otras cinco. Este documento especifica qué mediría, cómo, y **por qué su activación es de alto riesgo** para la reproducibilidad bit-a-bit del piloto-1.

---

## 1. Restricción crítica — esta feature está bloqueada por A1

**No implementar hasta que A1 (re-clasificación de las 106 classifications históricas con DB real del piloto) esté ejecutada y verificada.**

Razón: agregar una sexta coherencia bumpea el `classifier_config_hash` (porque cambia la estructura del `ClassificationResult` y los inputs del árbol). Las 106 classifications históricas tienen el hash legacy `9dd96894...` (pre-bump LABELER 1.2.0). Si CEC se activa antes de A1, esas 106 quedan en un estado de dos generaciones obsoletas, complicando la re-clasificación.

**Secuencia obligatoria**:
1. Ejecutar A1 — re-clasificar las 106 con el classifier_config_hash actual (post-1.2.0).
2. Validar intercoder κ ≥ 0,70 sobre el modelo de 5 coherencias actual (ADR-046).
3. Activar CEC como **opcional** (flag `cec_enabled = False` por default).
4. Re-clasificar las históricas con CEC activado, comparando ambas para validar que CEC aporta info no redundante.
5. Solo entonces decidir si CEC se vuelve default.

Saltarse esta secuencia invalida el corpus auditable del piloto-1 sin razón académica.

---

## 2. Qué mediría CEC

### 2.1 Definición operacional

CEC pretende medir si **el código que el estudiante escribe a lo largo del episodio tiene coherencia interna estructural** —es decir, si exhibe un plan consistente o si parece escrito sin plan.

Tres sub-indicadores propuestos (las funciones puras viven en `packages/platform-ops/src/platform_ops/cec_features.py`):

**Sub-1 — Varianza de profundidad de anidamiento (depth_variance)**:
Para cada snapshot de código en el episodio (estado tras cada `edicion_codigo` o `tests_ejecutados`), calcular la profundidad máxima de anidamiento del AST. Reportar la varianza poblacional de esa serie.

Hipótesis: estudiantes con plan coherente convergen a una profundidad de anidamiento ~estable (varianza baja). Estudiantes que prueban-y-borran tienen varianza alta.

**Sub-2 — Granularidad funcional (function_granularity)**:
Promedio de líneas-por-función al cierre del episodio. Funciones de 50+ líneas indican falta de descomposición; funciones de 1-2 líneas pueden indicar over-engineering.

Hipótesis: hay un rango "sano" pedagógicamente (10-25 líneas en programación universitaria, a calibrar por curso). Estar fuera del rango es señal interpretable.

**Sub-3 — Consistencia de nombres (naming_consistency)**:
Para los identificadores del último snapshot, computar una métrica de homogeneidad léxica (todos snake_case o todos camelCase, no mezcla; nombres sustantivos para variables, verbales para funciones). Implementación sugerida: heurística por regex, no LLM.

Hipótesis: inconsistencia léxica correlaciona con código pegado de fuentes distintas (tutor, web, compañero).

### 2.2 Agregación a una métrica

CEC se reporta como un objeto, **no** un escalar:

```python
@dataclass
class CECResult:
    depth_variance: float  # [0, +inf), 0 = perfecto plan único
    function_granularity_mean: float  # promedio líneas/func
    function_granularity_outliers: int  # cantidad de funciones fuera de rango
    naming_consistency_ratio: float  # [0, 1], 1 = perfecto
    cec_summary: float  # [0, 1] derivado, ver §2.3
```

`cec_summary` es derivado, no fuente de verdad. La fuente son los 4 campos individuales.

### 2.3 Fórmula de `cec_summary`

Operacionalización conservadora (la única que tiene sentido sin validación empírica):

```
cec_summary = mean([
    1.0 - clip(depth_variance / depth_variance_norm, 0, 1),
    1.0 if function_granularity_mean in [10, 25] else 0.5,
    1.0 - clip(function_granularity_outliers / 5, 0, 1),
    naming_consistency_ratio,
])
```

Constantes (`depth_variance_norm`, rangos, divisores) viven en `DEFAULT_REFERENCE_PROFILE["thresholds"]` del nuevo profile `cec_v1_0_0`. Profile-aware: cursos avanzados pueden tolerar más complejidad estructural.

---

## 3. Cómo se conecta con el árbol de decisión existente

**Opción A — CEC como sexta entrada del árbol** (recomendada):

`tree.py::classify` recibe 6 coherencias en lugar de 5. Las ramas existentes se mantienen pero agregan condiciones de cruce con CEC:

- `apropiacion_reflexiva` requiere además `cec_summary >= cec_high` (0.65).
- `delegacion_pasiva` se confirma si `cec_summary < cec_low` (0.35) Y orphan alto.
- `apropiacion_superficial` default si no cumple ni una ni otra.

**Opción B — CEC como sub-rama nueva** (más conservadora):

Mantener las 3 categorías actuales pero agregar un campo `code_structural_quality` independiente al `ClassificationResult`. No afecta la `appropriation` categórica, queda como información paralela.

**Recomendación**: **Opción B** para piloto-2. Razón: Opción A cambia el árbol y requiere re-validación intercoder completa (Protocolo B nuevo). Opción B agrega información sin modificar el árbol, permitiendo validar CEC de manera incremental con un Protocolo C separado.

---

## 4. Impacto en reproducibilidad bit-a-bit

### 4.1 Cambios necesarios

| Componente | Cambio | Bumpea |
|---|---|---|
| `ClassificationResult` schema | +4 campos CEC | `classifier_config_hash` |
| `DEFAULT_REFERENCE_PROFILE` | +rangos para CEC | `classifier_config_hash` |
| `pipeline.py::classify_episode_from_events` | +llamada a `cec.compute_cec` | `classifier_config_hash` |
| Migration de tabla `classifications` | +columnas CEC (JSONB en `features` posiblemente, sin migration de schema) | n/a si va en JSONB |

`LABELER_VERSION` NO se bumpea porque CEC opera sobre el código (texto serializado por el cliente), no sobre la asignación de niveles N1-N4. El etiquetador queda intacto.

### 4.2 Validación obligatoria pre-activación

1. Calcular CEC sobre los 106 episodios históricos del piloto-1 sin afectar el `classifier_config_hash` (computar pero no persistir en `classifications.appropriation`).
2. Comparar distribuciones: CEC vs. apropiation categorica. Si CEC > 0.7 correlaciona >0.85 con `apropiacion_reflexiva`, CEC es redundante con CT/CCD/CII y no aporta. Descartar.
3. Si la correlación es <0.7, CEC aporta información ortogonal: proceder.
4. ADR-051 documentando la decisión + bump de versión coordinado.

---

## 5. Limitaciones declaradas del approach

- **CEC asume Python ejecutable**: Pyodide corre Python. Otras universidades con piloto en C/Java requerirían re-implementar AST + heurísticas. Atado al stack del piloto-1.
- **AST snapshots son caros**: calcular AST tras cada `edicion_codigo` puede ser O(n^2) en episodios largos. Implementación debe muestrear (cada 5 ediciones, o cada 30s) y documentar el sesgo introducido.
- **CEC mide código, no proceso**: dos estudiantes pueden converger al mismo código pero por caminos distintos. CEC los vería iguales. CT/CCD/CII los distinguen. CEC complementa, no reemplaza.
- **Naming consistency es heurístico**: regex no captura nombres semánticamente coherentes pero léxicamente mezclados. Limitación declarable.

---

## 6. Trabajo de implementación estimado

Solo si los gates de §1 y §4.2 están cumplidos:

| Tarea | Esfuerzo |
|---|---|
| Implementar `cec_features.py` (3 funciones puras + tests golden) | 8-12 h |
| Validación empírica sobre 106 históricas (correlación CEC ↔ apropiación) | 4-6 h |
| Decisión humana de A vs B | 2-3 h (revisión coautoral) |
| Si A: modificar `tree.py` + `pipeline.py` + re-validación intercoder C | 16-24 h |
| Si B: agregar `cec_features` al output del `pipeline.py` sin tocar tree | 4-6 h |
| ADR-051 + migraciones + golden tests | 4-6 h |
| Tests smoke E2E | 2-3 h |
| **Total Opción A** | **36-54 h** |
| **Total Opción B** | **24-36 h** |

Estimado del informeSoc.md original era 20-30 h. Refinado: 24-54 h dependiendo de opción y de si requiere re-validación intercoder C (Opción A sí, Opción B no).

---

## 7. Decisiones pendientes (requieren participación humana)

1. **Aprobar el approach** (Opción A vs Opción B) con dirección + co-dirección + Ana Garis.
2. **Calibrar los rangos pedagógicos** (function_granularity 10-25? naming_consistency_ratio mínimo?) con docentes UNSL que enseñan programación I.
3. **Decidir si Protocolo C** (intercoder sobre 50 episodios con CEC visible) se ejecuta antes de la defensa o queda como agenda piloto-2.

---

## 8. Referencias

- informeSoc.md §3.3 — diagnóstico del sesgo verbal del corpus actual.
- ADR-010 — append-only.
- ADR-046 — protocolo intercoder. Análogo de Protocolo C si CEC se valida.
- Pausch, R. (1992). The next generation of programming environments. (Sobre granularidad funcional.)
- Soloway, E., & Spohrer, J. (Eds.). (1989). Studying the novice programmer. Routledge.
- Ben-Ari, M. (1998). Constructivism in computer science education. *Journal of Computers in Mathematics and Science Teaching*, 20(1), 45-73.
- `apps/classifier-service/src/classifier_service/services/tree.py` — árbol actual a extender.
- `packages/platform-ops/src/platform_ops/cii_longitudinal.py` — patrón de función pura a replicar.
