# ADR-032 — G7 ML predictivo: alertas con modelo entrenado sobre baseline individual del estudiante (DIFERIDO a piloto-2)

- **Estado**: Aceptado
- **Fecha**: 2026-05
- **Deciders**: Alberto Cortez, director de tesis
- **Tags**: pedagogía, ml, alertas, frontera-piloto-2, modelo-híbrido-honesto

## Contexto y problema

`audi1.md` G7 identifica la versión "verdadera" de las alertas predictivas como un modelo entrenado sobre el **trayecto individual** de cada estudiante: una alerta dispara cuando el desempeño del episodio actual cae más de 1 desviación estándar respecto del baseline propio del estudiante (no del baseline de la cohorte). Esa formulación es el contrato pedagógico que la tesis describe en Capítulo 20.

El MVP estadístico que efectivamente operativizamos pre-defensa (ADR-022 + RN-131) usa **z-score contra la cohorte + cuartiles privacy-safe N≥5**. Es una operacionalización conservadora, defendible como heurística de monitoreo grupal, pero NO es lo que `audi1.md` G7 propone como contrato final. La diferencia es académicamente relevante: el MVP detecta "estudiantes que rinden distinto al promedio de su comisión", la versión ML detecta "estudiantes que rinden distinto a sí mismos".

Hoy quedan dos caras del problema:

1. **Sin un ADR propio para G7 ML predictivo**, la decisión de NO entrenarlo pre-defensa queda como **deuda silenciosa**: el comité doctoral puede preguntar "¿por qué no implementaron la versión real?" y no hay un único documento al que apuntar para defender la decisión informada. ADR-022 cubre el MVP estadístico, no la versión ML.
2. **El dataset etiquetado mínimo no existe**: el piloto-1 todavía no terminó de generar trayectos longitudinales de longitud suficiente, validados κ contra intervención docente real. Entrenar sobre ese vacío produce un modelo no falseable, y un modelo malo defendido es peor que ninguno.

Hay que redactar la decisión formal de DIFERIR con criterio cuantificable de revisitar — eso es lo que el principio del modelo híbrido honesto del CLAUDE.md exige antes de cerrar un G como "no se hace pre-defensa".

## Drivers de la decisión

- **Honestidad académica**: el comité va a preguntar por la diferencia entre lo descrito en Capítulo 20 (G7 verdadero) y lo entregado pre-defensa (G7 MVP). Necesitamos un ADR único al que apuntar.
- **Falseabilidad del modelo**: sin dataset etiquetado mínimo, cualquier ML que entrenemos no se puede validar — se transforma en pseudo-ciencia.
- **Costo de oportunidad**: implementar G7 ML pre-defensa requiere ~3-4 semanas (data prep + training loop + evaluación + integración API + tests + UI), sin ROI defendible si el dataset no alcanza.
- **Continuidad piloto-1 → piloto-2**: la decisión debe declarar el **criterio cuantificable** que destrabaría G7 ML en piloto-2, para que el siguiente equipo (o el mismo doctorando en su próxima iteración) sepa exactamente cuándo retomar.

## Opciones consideradas

### Opción A — Implementar G7 ML predictivo pre-defensa

Entrenar un modelo (regresión logística simple sobre features del trayecto del estudiante: slope CII per-template, frecuencia de intentos adversos, distribución N1-N4) que dispare alertas cuando el episodio actual cae >1σ del baseline individual.

**Ventajas**: cierra el gap entre Capítulo 20 y código; defensa puede mostrar el modelo "real".

**Desventajas**:
- Dataset insuficiente: piloto-1 al cierre tiene <100 estudiantes con trayectos de >5 episodios — no alcanza para split train/val sin overfitting.
- Sin ground truth de docente real para κ-validar el output del modelo (eso requiere intervenciones docentes etiquetadas, que el piloto recién ahora empieza a generar).
- ~3-4 semanas de scope creep contra un cronograma de defensa que ya está apretado.
- Riesgo de defensa peor: modelo malo presentado como "real" expone más debilidades que un MVP estadístico declarado como tal.

### Opción B — DIFERIR a piloto-2 con ADR formal y criterio cuantificable

Mantener el MVP estadístico vigente (ADR-022) como la implementación entregable del piloto-1, y declarar formalmente en este ADR que la versión ML queda para piloto-2 con condiciones objetivas de revisitar.

**Ventajas**:
- Honesto: el comité ve la decisión documentada, no la deuda silenciosa.
- Defendible: el MVP estadístico tiene una caracterización académica clara (heurística poblacional con privacy gate), no es presentado como ML.
- Mantiene el cronograma de defensa.
- Continuidad explícita para piloto-2: el siguiente equipo sabe qué dataset producir y qué métricas exigir.

**Desventajas**:
- Capítulo 20 de la tesis tiene que mencionar explícitamente que el ADR-032 declara la diferencia entre versión descripta y versión entregada (gap documental cerrable con un párrafo).
- Si el comité presiona "¿pero entonces no es lo que prometieron?", la respuesta es el ADR — preparación del defensor obligatoria.

### Opción C — Implementación parcial (ML entrenado solo para alertas críticas)

Entrenar solo para una clase de alerta (ej. "abandono inminente") con dataset reducido pero curado.

**Ventajas**: parcialmente cubre el discurso "G7 ML existe".

**Desventajas**:
- Frankenstein: parte ML, parte estadístico — más difícil de explicar al comité que cualquiera de los extremos.
- Mismo problema de dataset insuficiente para esa clase específica.
- Multiplica las decisiones que el ADR tiene que documentar (qué clases sí, cuáles no, por qué) sin reducir el riesgo de fondo.

## Decisión

Opción elegida: **B — DIFERIR a piloto-2 con criterio cuantificable de revisitar**.

**Justificación**: el MVP estadístico (ADR-022 + RN-131) es una operacionalización honesta del problema de monitoreo grupal con los datos que tenemos. La versión ML predictiva sobre baseline individual requiere dataset que el piloto-1 no produce — entrenarla ahora produce ruido defendible peor que la decisión de DIFERIR.

### Criterio cuantificable para revisitar G7 ML en piloto-2

G7 ML predictivo se retoma cuando se cumplan **simultáneamente** las 3 condiciones:

1. **Dataset etiquetado mínimo**: ≥200 estudiantes con trayectos de ≥10 episodios cerrados completos (Episode con Classification asociada y CTR íntegro). El número 200/10 viene de la regla práctica de tener al menos 20 muestras por feature en un modelo de ~10 features (slope CII per-template + distribución N1-N4 + frecuencia adversa + dispersión CCD), con suficiente densidad para split 70/15/15 train/val/test.
2. **Ground truth docente**: ≥30 intervenciones docentes etiquetadas (¿alerta justificada? sí/no/parcial) provenientes de docentes que pasaron el protocolo κ del piloto (ver `docs/pilot/kappa-workflow.md`), con κ ≥ 0.6 entre docentes — para validar el output del modelo contra criterio pedagógico calibrado, no contra "lo que el modelo se inventó".
3. **Validación cruzada split por estudiante** (no por episodio): el split debe ser leave-one-student-out o k-fold con stratificación por estudiante, para evitar leakage de baseline individual entre folds. Métricas mínimas exigibles: AUC ≥ 0.75 vs ground truth docente, calibración Brier ≤ 0.20.

Si en piloto-2 cualquiera de las 3 condiciones no se cumple, este ADR se mantiene vigente y la decisión sigue siendo DIFERIR. Cualquier propuesta de relajar las 3 condiciones tiene que documentarse en un ADR sucesor que supersede a este.

## Consecuencias

### Positivas

- **Cierra deuda documental**: el comité doctoral tiene un ADR único al que apuntar para entender la diferencia entre Capítulo 20 (versión descripta) y entregable piloto-1 (MVP estadístico).
- **Continuidad piloto-2 explícita**: el siguiente equipo sabe exactamente qué dataset producir y qué métricas exigir antes de retomar G7 ML.
- **Defensa doctoral más limpia**: la pregunta "¿implementaron la versión ML?" tiene respuesta clara — "decidimos DIFERIR con criterio formal, ver ADR-032", no "no llegamos".
- **Alinea con el principio del modelo híbrido honesto**: convierte deuda silenciosa en decisión informada, que es lo que el CLAUDE.md exige.

### Negativas / trade-offs

- **Capítulo 20 de la tesis necesita un párrafo de cross-reference** a este ADR para cerrar el lado documental. Sin ese párrafo, el lector de la tesis no sabe que la diferencia está reconocida.
- **MVP estadístico sigue siendo sub-óptimo en sentido estricto**: detecta outliers grupales, no individuales. Pedagógicamente útil pero no es lo que la tesis idealiza.
- **Si piloto-2 nunca se materializa**, G7 ML predictivo queda en limbo permanente. Asumido — el riesgo del piloto-2 es del programa de doctorado, no de este ADR.

### Neutras

- No afecta ningún test ni código existente — la implementación vigente (ADR-022) sigue siendo la canónica del piloto.
- No afecta los hashes deterministas (`classifier_config_hash`, `self_hash`, `chain_hash`) ni la reproducibilidad bit-a-bit.
- No afecta el contrato del CTR ni de los eventos.

## Referencias

- `audi1.md` G7 — formulación original del problema: alertas verdaderas con modelo entrenado sobre baseline individual del estudiante (>1σ de su propio trayecto).
- ADR-022 — alertas predictivas con estadística clásica (z-score vs cohorte) + cuartiles privacy-safe (MVP entregado pre-defensa).
- `reglas.md` RN-131 — reglas de las alertas predictivas y cuartiles del MVP.
- `packages/platform-ops/src/platform_ops/cii_alerts.py` — implementación actual de las alertas estadísticas.
- `docs/pilot/kappa-workflow.md` — protocolo κ para etiquetar ground truth docente (insumo para condición 2 del criterio de revisitar).
- Capítulo 20 de la tesis — espacio reservado para G7 ML; este ADR cierra el lado decisional del gap.
- CLAUDE.md sección "Modelo híbrido honesto" — principio operativo: redactar ADR antes de cerrar un G como "no se hace".
