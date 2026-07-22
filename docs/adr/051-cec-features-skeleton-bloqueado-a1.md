# ADR-051 — Esqueleto de Coherencia Estructural del Código (CEC) como funciones puras, bloqueado por A1 + validación empírica

- **Estado**: Aceptado
- **Fecha**: 2026-05-16
- **Deciders**: Alberto Cortez, director de tesis
- **Tags**: classifier, coherencia-codigo, informeSoc-R7, esqueleto-bloqueado, piloto-2, reproducibilidad
- **Cierra parcialmente**: R7 del `informeSoc.md` (componente técnico de funciones puras; conexión al pipeline queda bloqueada por A1).

## Contexto y problema

El piloto AI-Native N4 calcula la apropiación de la IA en base a **cinco coherencias** (CT, CCD_mean, CCD_orphan_ratio, CII_stability, CII_evolution). El informeSoc.md §3.3 identificó que estas cinco están sesgadas hacia la dimensión **verbal**: Jaccard léxico de prompts (CII_stability), pendiente léxica (CII_evolution), alineamiento texto-código (CCD). La didáctica de la programación (Pausch 1992, Soloway & Spohrer 1989, Ben-Ari 1998) muestra que la **calidad estructural del código producido** —plan implícito, granularidad funcional, consistencia léxica de identificadores— es predictor independiente de comprensión que las métricas verbales no capturan.

La recomendación R7 propuso una sexta coherencia, **Coherencia Estructural del Código (CEC)**, con tres sub-indicadores derivables del AST de Python sin LLM: `depth_variance` (varianza de profundidad de anidamiento entre snapshots), `function_granularity` (líneas-por-función + outliers), `naming_consistency` (homogeneidad léxica de identificadores).

**Restricción operacional dura**: agregar CEC al pipeline cambia la estructura del `ClassificationResult` y los inputs del árbol → bumpea el `classifier_config_hash`. Las 106 classifications históricas del piloto-1 tienen `classifier_config_hash` legacy. Activar CEC antes de **A1** (re-clasificación de las 106 con el hash actual post-LABELER_VERSION 1.2.0) deja el corpus en dos generaciones obsoletas, invalidando la auditabilidad académica del piloto-1.

**Restricción epistemológica complementaria**: aún cumplido A1, una sexta coherencia debe pasar **validación empírica de no-redundancia** antes de entrar al árbol. Si CEC correlaciona >0.85 con apropiacion_reflexiva, no aporta señal ortogonal y debe descartarse.

El presente ADR materializa la decisión de **implementar CEC como funciones puras disponibles offline, sin conexión al pipeline ni al classifier_config_hash** durante el período entre el cierre del piloto-1 y la disponibilidad de A1 + validación empírica.

## Decisión

Se implementa CEC como **utilidad de análisis offline en `platform-ops`** sin conexión a `pipeline.py` ni a `tree.py`. Específicamente:

1. **Módulo `packages/platform-ops/src/platform_ops/cec_features.py`** con cuatro funciones puras:
   - `depth_variance(snapshots: list[str]) -> float` — varianza poblacional de profundidad de anidamiento del AST sobre la serie de snapshots de código.
   - `function_granularity(code: str) -> FunctionGranularityResult` — promedio de líneas-por-función + conteo de outliers (debajo de 5 líneas o encima de 30).
   - `naming_consistency(code: str) -> float` — heurística por regex de homogeneidad lexical (snake/camel/pascal) entre identificadores definidos.
   - `compute_cec(snapshots, final_code=None) -> CECResult` — agregador que combina las tres en `cec_summary ∈ [0, 1]`.

2. **Versión `CEC_VERSION = "1.0.0"`**. Sin sufijo `-draft` porque las funciones son matemáticamente determinadas (no contenido textual sujeto a revisión académica). Lo provisional son **las constantes de calibración**: `FUNCTION_GRANULARITY_MIN_LINES = 5`, `MAX_LINES = 30`, `DEPTH_VARIANCE_NORM = 4.0`. Estos rangos pedagógicos son operacionalización inicial — calibrar con docentes UTN post-A1.

3. **NO conectado al pipeline**:
   - `apps/classifier-service/src/classifier_service/services/pipeline.py` no importa este módulo.
   - `apps/classifier-service/src/classifier_service/services/tree.py` no importa este módulo.
   - `Classification.appropriation` y `Classification.features` no contienen señales CEC en piloto-1.
   - El `classifier_config_hash` no cambia por la existencia de este módulo.

4. **Uso recomendado durante el bloqueo**: análisis offline sobre snapshots históricos via scripts ad-hoc o un futuro endpoint `POST /classifier/cec/preview` (no en piloto-1). Permite a la dirección computar CEC sobre las 106 históricas post-A1 sin afectar el corpus actual.

5. **Activación bloqueada hasta**:
   - **Gate A — A1 ejecutado**: las 106 classifications históricas re-clasificadas con el `classifier_config_hash` actual (post-LABELER 1.2.0). Corpus consistente disponible.
   - **Gate B — Validación empírica de no-redundancia**: computar CEC sobre las 106 históricas + cruzar con `appropriation`. Si correlación pearson o spearman entre `cec_summary` y `APPROPRIATION_ORDINAL[appropriation]` es > 0.85, CEC es redundante con CT/CCD/CII y se descarta (cierra el experimento). Si < 0.70, CEC aporta señal ortogonal y se procede a Gate C.
   - **Gate C — Calibración de rangos pedagógicos**: dirección + docentes UTN revisan los rangos `MIN_LINES`, `MAX_LINES`, `DEPTH_VARIANCE_NORM` sobre código real del piloto. Ajustar si corresponde, bumpear `CEC_VERSION`.
   - **Gate D — Decisión de incorporación**: ADR-NNN posterior que decide **Opción A** (sexta entrada del árbol — requiere Protocolo C intercoder) o **Opción B** (campo paralelo `code_structural_quality` sin afectar appropriation — no requiere Protocolo C). El `design-sexta-coherencia-estructural.md` recomienda Opción B para piloto-2.

## Drivers de la decisión

- **D1**: respetar la reproducibilidad bit-a-bit del piloto-1. La inexistencia de CEC en el pipeline garantiza que las 106 classifications históricas siguen comparables con las que se computen durante el piloto activo (hasta A1 + Gate D).
- **D2**: separar **disponibilidad técnica** de **incorporación productiva**. La función pura puede inspeccionarse, criticarse y validarse empíricamente sobre datos reales sin necesidad de afectar el pipeline. Esto es la diferencia con ADR-044/045 (esqueletos OFF "ya conectados pero gateados") — acá el esqueleto está **completamente desconectado**, no solo gateado.
- **D3**: reducir lead-time entre A1 y Gate D. Cuando A1 cierre, computar CEC sobre las 106 toma minutos (función pura). El gate B se puede ejecutar en una sesión. El cuello de botella pasa a ser la decisión de Opción A vs B.
- **D4**: preservar reproducibilidad de CEC misma. Función pura sobre snapshots → resultado determinista. Tests golden cubren los 3 sub-indicadores + el agregado. Cualquier bump de `CEC_VERSION` debe ir acompañado de los nuevos golden values.
- **D5**: fail-soft sobre código con sintaxis inválida. `_safe_parse` devuelve `None` para snapshots con SyntaxError; las funciones degradan graciosamente (los snapshots inválidos se excluyen de `depth_variance`, `function_granularity` devuelve count=0, `naming_consistency` devuelve 1.0 por convención de "trivialmente consistente"). Esto es crítico: durante el episodio el estudiante escribe código con errores transientes; CEC no puede romperse.
- **D6**: documentar el bloqueo de A1 **en el código del módulo** (docstring del archivo) además de en el ADR. Cualquier dev que llegue al módulo sin leer este ADR debe ver de inmediato que NO debe conectarlo al pipeline.
- **D7**: anticipar la decisión Opción A vs B. El design doc R7 recomienda B (campo paralelo). Esto evita Protocolo C intercoder adicional y permite activación más temprana — pero limita el aporte de CEC a "información complementaria" en lugar de "modificación de apropiación". Decisión final en Gate D.

## Opciones consideradas

### Opción A — Esqueleto desconectado (elegida)

Ya descrita en la sección Decisión.

**Ventajas**:
- Cero riesgo de romper invariantes del piloto-1 mientras CEC se valida.
- Funciones puras inspeccionables y testeables sin tocar el classifier.
- Validación empírica de no-redundancia (Gate B) se puede ejecutar sobre datos reales antes de comprometer arquitectura.

**Desventajas**:
- Líneas de código sin uso productivo durante el bloqueo. ~270 LOC del módulo + 14 tests.
- Riesgo de que CEC se valide como no-redundante (Gate B pasa) pero la incorporación al pipeline se postergue, dejando el módulo en limbo.

### Opción B — Esqueleto conectado al pipeline con flag OFF

Patrón análogo a ADR-044: importar el módulo desde `pipeline.py` con un `if settings.cec_enabled:` antes de invocarlo.

**Desventajas que la descartan**:
- Mero hecho de **importar** el módulo desde el pipeline modifica el árbol de dependencias del classifier-service y puede introducir efectos sutiles sobre tests de reproducibilidad (`test_pipeline_reproducibility.py`) que verifican el hash del archivo.
- Riesgo de prender el flag accidentalmente en producción del piloto-1, corrompiendo las 106 históricas. El blast radius es enorme: cualquier flag flip bumpea `classifier_config_hash`.
- El gate de A1 es no-negociable arquitectónicamente, no operacionalmente. Acoplarlo a un flag es semánticamente incorrecto.

### Opción C — Implementar CEC y bumpear `classifier_config_hash` simultáneamente con A1

Coordinar A1 + CEC + intercoder Protocolo C en una sola operación de re-clasificación.

**Desventajas que la descartan**:
- Multiplica el riesgo de A1. A1 ya es operación cara (re-clasificación de 106 episodios sobre DB real del piloto). Agregarle CEC en el mismo bump significa que cualquier falla de CEC contamina la re-clasificación, obligando a tercera ronda.
- Antes de re-clasificar con CEC, hay que **validar** que CEC aporta (Gate B). Validar requiere computar CEC sobre las 106 ya re-clasificadas con `classifier_config_hash` post-1.2.0. Es decir, A1 viene primero por necesidad lógica.

### Opción D — Postergar implementación hasta A1 + Gate B

No implementar nada hasta que A1 + Gate B estén cerrados.

**Desventajas que la descartan**:
- Lead-time alto entre A1 y la decisión de Gate D. La función pura toma horas; A1 + Gate B toman semanas (coordinación con piloto real). Tener las funciones listas reduce el tiempo de Gate B a "correr un script", no "implementar + correr un script".
- Sin la implementación es más difícil discutir con dirección los rangos pedagógicos provisionales — discusiones sobre métricas abstractas son menos productivas que sobre métricas computadas sobre código real.

## Criterios de éxito

1. El módulo `packages/platform-ops/src/platform_ops/cec_features.py` existe y exporta `compute_cec`, `depth_variance`, `function_granularity`, `naming_consistency`.
2. Los 14 tests en `tests/test_cec_features.py` pasan en CI.
3. `apps/classifier-service/src/classifier_service/services/pipeline.py` NO importa este módulo (verificable: `grep -r "cec_features" apps/classifier-service/` devuelve 0 matches).
4. `Classification.features` no contiene claves con prefijo `cec_` en piloto-1 (verificable sobre la DB: `SELECT features FROM classifications WHERE features::text LIKE '%cec_%'` devuelve 0 rows).
5. El docstring del módulo cita literalmente "BLOQUEO CRITICO" + ADR-051.
6. `CEC_VERSION = "1.0.0"` y constantes (`MIN_LINES=5`, `MAX_LINES=30`, `DEPTH_VARIANCE_NORM=4.0`) coinciden con los tests anti-regresión.

## Criterios de revisita (para activar)

- **Gate A — A1 cerrado**: las 106 classifications históricas re-clasificadas. Documento de cierre de A1 referenciable.
- **Gate B — Validación empírica de no-redundancia**: correlación CEC ↔ appropriation computada y reportada. Decisión registrada en ADR-NNN nuevo.
- **Gate C — Calibración de rangos**: rangos pedagógicos revisados sobre código real, bumpear `CEC_VERSION` si se ajustan.
- **Gate D — Decisión Opción A (sexta entrada del árbol, requiere Protocolo C intercoder) o B (campo paralelo, no requiere Protocolo C)**: ADR-NNN nuevo que documente la elección y los cambios al pipeline.

Cuando los cuatro gates se cumplan, este ADR queda **superseded** por el ADR-NNN que documente la activación efectiva.

## Consecuencias

### Positivas

- Cero riesgo para el piloto-1.
- Funciones disponibles para análisis offline sobre datos reales post-A1.
- Fail-soft documentado y testeado (código con SyntaxError no rompe CEC).
- Patrón "esqueleto desconectado" establecido para futuras métricas estructurales que tengan bloqueo arquitectónico similar.

### Negativas

- Líneas de código sin uso productivo hasta gates levantados (~270 LOC + 14 tests).
- Las constantes de calibración (`MIN_LINES`, `MAX_LINES`) están en código sin validación empírica — riesgo de que se "naturalicen" como definitivas sin pasar por Gate C.

### Neutras

- Contrato del CTR no cambia. `classifier_config_hash` no cambia. `LABELER_VERSION` no se bumpea.
- El módulo `cec_features.py` puede usarse en scripts ad-hoc (`scripts/eval-cec-historicas.py`) sin necesidad de levantar el classifier-service.

## Referencias

- ADR-010 — CTR append-only y reproducibilidad bit-a-bit del `classifier_config_hash`. La restricción fundacional que motiva el bloqueo.
- ADR-018 — CII evolution longitudinal. Patrón análogo de "función pura en platform-ops, persistencia opcional en features JSONB".
- ADR-020 — Event labeler derivado en lectura. Patrón análogo de versionado de reglas.
- `informeSoc.md` §3.3 — diagnóstico del sesgo verbal del corpus actual.
- `docs/research/design-sexta-coherencia-estructural.md` — design completo de R7 con análisis Opción A vs B.
- `packages/platform-ops/src/platform_ops/cec_features.py` — implementación.
- `packages/platform-ops/tests/test_cec_features.py` — 14 tests golden.
- `plan-accion.md` A1 — re-clasificación pendiente con DB real del piloto. Gate A de este ADR.
- Pausch, R. (1992). The next generation of programming environments. (Granularidad funcional.)
- Soloway, E., & Spohrer, J. (Eds.). (1989). Studying the novice programmer. Routledge.
- Ben-Ari, M. (1998). Constructivism in computer science education. *Journal of Computers in Mathematics and Science Teaching*, 20(1), 45-73.
