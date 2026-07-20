# Informe cognitivo sobre la implementación del tutor socrático y la categorización del aprendizaje

**Autor del informe**: análisis externo en rol de especialista en ciencia cognitiva del aprendizaje y medición educativa.
**Objeto de análisis**: plataforma AI-Native N4 (`AI-NativeV3-main/`), prompt activo `v1.1.0`, etiquetador `LABELER_VERSION = 1.2.0`, classifier `tree.py` con árbol de 3 categorías, paper Cortez & Garis (`paper-draft.md`).
**Fecha**: 2026-05-16.
**Complementa**: `informeSoc.md` (análisis desde didáctica socrática). Este informe enfoca la **lente cognitiva**: cómo el sistema modela, mide y clasifica el **aprendizaje como objeto cognitivo**.
**Destinatario implícito**: Alberto A. Cortez (autor de la tesis), co-dirección, comité doctoral UTN.

---

## 0. Resumen ejecutivo

Desde la lente de la ciencia cognitiva del aprendizaje, el sistema AI-Native N4 exhibe **una elección teórica conservadora poco frecuente** en plataformas de learning analytics: distingue tres órdenes epistemológicos (eventos → indicadores → constructos sintéticos) y se rehúsa explícitamente a colapsar las coherencias en un score único. Esa decisión —documentada en `paper-draft.md` §4.3 y §4.5— sitúa al modelo en la tradición de **evidence-centered design** (Mislevy, Steinberg & Almond, 2003; Pellegrino, Chudowsky & Glaser, 2001) en lugar de la tradición simplista del *score-único-comparable-entre-estudiantes*. Es defendible académicamente y operacionalmente íntegro.

Dicho esto, identifico **seis observaciones cognitivamente sustantivas** que el informe desarrolla:

1. **El sistema mide proceso observable, no aprendizaje en sentido estricto.** Las cinco coherencias (CT, CCD_mean, CCD_orphan_ratio, CII_stability, CII_evolution) son indicadores conductuales sin transferencia validada, sin pre/post-test, sin baseline individual, sin medidas convergentes de carga cognitiva o metacognición. El paper lo reconoce honestamente; el público doctoral debe leerlo en clave.
2. **El árbol de 3 categorías es una tipología, no una dimensión psicométrica.** Operacionalmente útil; teóricamente más débil que una variable latente continua con propiedades dimensionales validadas (Cronbach & Meehl, 1955; Messick, 1989).
3. **La Coherencia Código-Discurso (CCD) está parcialmente comprometida en runtime**: depende de `prompt_kind == "reflexion"` que el tutor-service nunca emite en v1.0.0. Limitación declarada en el código (`ccd.py` líneas 18-41), pero impacta la validez del constructo más de lo que el paper enfatiza.
4. **La operacionalización temporal está sesgada hacia patrones detectables algorítmicamente**, no hacia patrones cognitivamente significativos. Una anotación a los 119 segundos es N1; a los 121 segundos es N2 — la frontera temporal es arbitraria en términos de proceso cognitivo, aunque defendible en términos de reproducibilidad bit-a-bit.
5. **El sistema implementa cognición distribuida (Hutchins, 1995) pero no la mide.** Las cinco coherencias miden al estudiante, no al *sistema cognitivo extendido* estudiante+tutor+IDE+tests. La promesa teórica del marco no se materializa completamente en los indicadores operacionales.
6. **La validación intercoder (κ ≥ 0,70) es necesaria pero insuficiente para validez de constructo.** Acuerdo entre etiquetadores no implica que el constructo esté correctamente operacionalizado; solo que la operacionalización es reproducible (Messick, 1989; AERA, APA & NCME, 2014).

Las recomendaciones C0-C4 (§9) se ordenan no por urgencia sino por **profundidad de validación cognitiva** que aportan al piloto y al paper.

---

## 1. Marco de referencia: la pregunta cognitiva

La lente didáctica que apliqué en `informeSoc.md` preguntó: *¿el tutor enseña socráticamente en sentido fuerte?* La pregunta cognitiva que aplico acá es distinta y complementaria: *¿qué constructo de aprendizaje está implícito en la operacionalización, y cuán bien lo mide?*

La diferencia importa. Un tutor puede enseñar bien (lente didáctica) sin que el sistema mida bien el aprendizaje subyacente (lente cognitiva); y un sistema puede medir bien procesos cognitivos (lente cognitiva) sin que el tutor llegue a ser socrático en sentido fuerte (lente didáctica). Las dos lentes son ortogonales.

La ciencia cognitiva del aprendizaje contemporánea trabaja con al menos cuatro distinciones que la lente didáctica no captura:

- **Comportamiento vs proceso cognitivo interno** (Anderson, 1983; ACT-R): un clic, un prompt, una ejecución son comportamientos; las representaciones, esquemas y operaciones mentales que los producen son procesos internos. Un sistema bien diseñado distingue qué mide y qué infiere.
- **Carga cognitiva** (Sweller, 1988, 1994): intrínseca (complejidad del material), extrínseca (carga impuesta por el diseño instructivo), germana (carga productiva para la formación de esquemas). Distintas cargas tienen efectos opuestos sobre el aprendizaje.
- **Conocimiento vs aprendizaje** (Koedinger, Corbett & Perfetti, 2012; KLI framework): el conocimiento es un estado; el aprendizaje es el cambio entre estados. Sin medidas pre/post o longitudinales individuales, un sistema mide procesos pero no aprendizaje.
- **Validez de constructo** (Cronbach & Meehl, 1955; Messick, 1989): un indicador puede ser confiable (reproducible) sin ser válido (medir el constructo que dice medir). La validación de constructo requiere triangulación con instrumentos convergentes y demostración de discriminación contra constructos divergentes.

Este informe interroga al sistema AI-Native N4 desde esas cuatro distinciones.

---

## 2. Tres órdenes epistemológicos: una elección teóricamente sofisticada

`paper-draft.md` §4.3 introduce —y este es uno de los aciertos cognitivos más fuertes del proyecto— una distinción en tres órdenes:

- **Primer orden (eventos observables)**: clics, tipeos, prompts, respuestas, tests. Sin interpretación. Marca temporal y contexto.
- **Segundo orden (indicadores derivados)**: construcciones que sintetizan secuencias de eventos aplicando reglas de codificación explícitas. Cuantitativos, contrastables empíricamente. Son los inputs de H1, H2, H3.
- **Tercer orden (constructos sintéticos)**: abstracciones teóricas (calidad epistémica, apropiación reflexiva en sentido fuerte). No se definen por fórmula sino por articulación conceptual. Operan como horizontes interpretativos —MI1, MI2, MI3—. *Validación indirecta* por triangulación con juicio experto.

**Por qué esto es teóricamente sofisticado**: la mayoría de las plataformas de learning analytics colapsan los tres niveles. Reportan "engagement_score = 0.73" como si fuera una observación, cuando es una construcción de tercer orden disfrazada de primer orden. El AI-Native N4 hace lo contrario: separa explícitamente lo que se observa, lo que se infiere algorítmicamente, y lo que se interpreta humanamente.

**Anclaje teórico**: la distinción se alinea con el modelo **evidence-centered design (ECD)** de Mislevy, Steinberg y Almond (2003), donde la evaluación se construye sobre cuatro modelos articulados (student model, evidence model, task model, assembly model). El AI-Native N4 implementa los primeros dos: el `tree.py` es el evidence model que actualiza el student model (la categoría de apropiación).

**Riesgo a marcar**: el marco interpretativo MI1, MI2, MI3 está **declarado** en el paper (§4.3, Fig. 2) pero **no enunciado explícitamente**. La fig. 2 menciona su existencia pero el cuerpo del paper no enumera qué afirma cada MI. Esto es un agujero académico subsanable —y debería subsanarse antes de la defensa, no después.

---

## 3. Las cinco coherencias bajo escrutinio cognitivo

### 3.1 Coherencia Temporal (CT) — `ct.py`

**Lo que mide operacionalmente**: la función `compute_ct` (líneas 87-117) calcula un promedio ponderado sobre ventanas de actividad (separadas por pausas >5 minutos). Para cada ventana:
- `density_score` normalizado: eventos por minuto, transformación lineal con piso 0.5 y techo 5.0 eventos/min.
- `balance`: distancia al ratio 1:2 entre prompts y ejecuciones — el rango "saludable" definido en el módulo.

**Constructo cognitivo implícito**: *patrón de trabajo sostenido y equilibrado entre consulta y acción*. Aproximación funcional al *time-on-task* clásico (Carroll, 1963; Bloom, 1968) modulado por el ratio prompts/ejecuciones.

**Crítica cognitiva**:
- **Tiempo en tarea ≠ aprendizaje**. Cuatro décadas de investigación muestran que tiempo-en-tarea correlaciona con resultado solo bajo ciertas condiciones (calidad de la tarea, atención sostenida, ausencia de fatiga). El piloto no controla por estas (Bjork & Bjork, 2011; Roediger & Karpicke, 2006).
- **La pausa >5min como frontera de ventana es heurística**. No hay evidencia cognitiva de que 5 minutos sea el umbral entre "ventana coherente" y "ventana fragmentada". Es operacionalización pragmática.
- **El ratio prompt:exec=1:2 como "saludable"** es decisión del implementador (`ct.py:42`). No hay literatura cognitiva que justifique ese ratio específico vs otros (1:1, 1:3). Calibrarlo empíricamente o documentarlo como elección de diseño.
- **La carga cognitiva (Sweller, 1988) está ausente**. Una ventana de alta densidad puede indicar productividad O sobrecarga cognitiva extrínseca. Sin medida convergente, CT no distingue.

### 3.2 Coherencia Código-Discurso (CCD) — `ccd.py`

**Lo que mide operacionalmente**: pares (acción, reflexión) dentro de ventanas de 2 minutos. `ccd_mean` mide proximidad temporal promedio; `ccd_orphan_ratio` mide fracción de acciones sin reflexión correlacionada.

**Constructo cognitivo implícito**: *alineamiento entre verbalización y artefacto producido* — aproximación al **efecto de auto-explicación** (Chi, Bassok, Lewis, Reimann & Glaser, 1989; Chi, 2000). Los estudiantes que verbalizan su razonamiento mientras producen exhiben mejor comprensión conceptual y mejor transferencia.

**Crítica cognitiva — la grave**:
Lo que el módulo declara que mide está parcialmente desactivado en runtime (`ccd.py:18-41`):

> "[Verbalización reflexiva] ocurre cuando el estudiante (...) verbaliza explícitamente su comprensión/confusión (prompt_enviado con `prompt_kind=reflexion`). Sin embargo, 'reflexion' NO es uno de los valores admitidos por `PromptKind` en los contratos vigentes... El tutor-service emite siempre `prompt_kind='solicitud_directa'` en v1.0.0. Por tanto la rama (b) **nunca se activa con datos reales del piloto** y CCD subestima la reflexividad de prompts cuyo contenido es reflexivo pero quedan etiquetados como 'solicitud_directa'."

Es decir: CCD en runtime mide solo (`anotacion_creada` ↔ `codigo_ejecutado`), no (prompts reflexivos del estudiante ↔ acciones). Una parte importante del constructo —la mitad probablemente más relevante pedagógicamente— está fuera del cálculo del piloto-1.

Esto es honestidad académica de parte del equipo (lo declara el módulo y la limitación declarada §3, ADR-045). Pero impacta la **validez de constructo** de CCD más de lo que el paper enfatiza. Una métrica que mide la mitad de su definición conceptual es una métrica que captura un proxy del proxy.

**Crítica cognitiva — la menor**:
- **La ventana de 2 minutos** es heurística. La literatura de auto-explicación no tiene ventana temporal universal; depende del dominio (Chi & Wylie, 2014: ICAP framework). Calibrar o declarar como decisión.

### 3.3 Coherencia Inter-Iteración (CII) — `cii.py`

**Lo que mide operacionalmente**:
- `cii_stability`: **Jaccard léxico** entre prompts consecutivos. Set de tokens lowercase intersectados sobre unión.
- `cii_evolution`: pendiente de regresión simple sobre **largo en palabras** de los prompts a lo largo del episodio, normalizada a [0, 1].

**Constructo cognitivo implícito**:
- `cii_stability` → *persistencia conceptual del foco de pensamiento* dentro del episodio. Cercana a la idea de *cognitive focus* (Posner & Petersen, 1990).
- `cii_evolution` → *sofisticación creciente del discurso del estudiante* — aproximación a la idea de **desarrollo del lenguaje técnico** como indicador de internalización conceptual (Vygotsky, 1934/1986).

**Críticas cognitivas**:
- **Jaccard léxico es ciego al significado**. "función iteradora" y "función iterativa" son léxicamente distintos pero conceptualmente sinónimos. Inversamente, "función" puede aparecer en prompts sobre conceptos completamente distintos. La **tesis extendida** (documento de tesis doctoral, no el paper en sí) documenta esto como limitación en su §15.6 según ADR-045, y la cita como agenda futura (G8c semántico via embeddings). El paper-draft.md actual NO tiene §15 equivalente — la limitación se atiende en §8 (riesgos a priori) o queda implícita.
- **Largo en palabras no es complejidad cognitiva**. Un estudiante puede sofisticar su prompt sin elaborar su pensamiento (copiando registro técnico del tutor); inversamente, un prompt breve puede ser cognitivamente más sofisticado que uno largo si formula una pregunta epistemológicamente más productiva. La operacionalización es **superficial** en sentido literal (mide la superficie léxica, no la profundidad cognitiva).
- **Slope sobre N prompts** —si el episodio tiene 3 prompts, la pendiente sobre 3 puntos es ruido. La función pura no impone mínimo de iteraciones para reportar `cii_evolution`. (Contrastar con `cii_longitudinal.py` que sí exige `MIN_EPISODES_FOR_LONGITUDINAL = 3`.)
- **CII intra-episodio vs CII longitudinal**: la implementación tiene dos versiones que **no se renombran** para preservar compatibilidad histórica (CLAUDE.md sección Estado actual). Esto es deuda técnica con consecuencia cognitiva: dos constructos distintos llevan etiquetas casi iguales —`cii_evolution` (intra-episodio, pendiente léxica) vs `cii_evolution_longitudinal` (inter-episodio, pendiente ordinal de apropiación). Para un lector externo del paper, la distinción no es obvia.

### 3.4 Lo que las cinco coherencias dicen juntas

Operativamente, las cinco son **proxies temporales-léxicos del proceso cognitivo**. Capturan:
- Ritmo (CT density).
- Balance entre consulta y acción (CT prompt_exec_ratio).
- Acoplamiento temporal verbalización↔acción (CCD).
- Persistencia léxica del foco (CII_stability).
- Sofisticación léxica creciente (CII_evolution).

No capturan:
- Contenido semántico de los prompts (declarado como agenda Eje B).
- Calidad de los esquemas mentales (Anderson, 1983, 1996; Sweller, 2011).
- Carga cognitiva extrínseca o germana.
- Conciencia metacognitiva.
- Conocimiento previo (priors / pre-test).
- Transfer a tareas relacionadas.

Esto es **honesto y declarado**. Pero el lector del paper debe entender que el AI-Native N4, en su versión actual, mide *procesos observables de uso del asistente*, no *aprendizaje* en sentido cognitivo estricto. La distinción entre proceso y aprendizaje es la distinción entre estado y cambio de estado (Koedinger et al., 2012).

---

## 4. El árbol de 3 categorías: tipología vs psicometría

`tree.py` produce una de tres categorías por episodio: `apropiacion_reflexiva`, `apropiacion_superficial`, `delegacion_pasiva`. La pregunta cognitiva: *¿qué tipo de variable es esto?*

### 4.1 Tipologías vs dimensiones

En psicometría educativa moderna, las clasificaciones discretas en pocas categorías (3 o 4) son **tipológicas**: enclasan a los individuos en grupos sin asumir relación lineal entre ellos. Las dimensiones continuas (z-scores, IRT theta) **escalan** a los individuos en una variable latente con propiedades métricas.

Ambos approaches tienen tradición:
- **Tipológico**: ICAP framework (Chi & Wylie, 2014: passive/active/constructive/interactive); Biggs & Collis SOLO (1982); Marton & Säljö approaches to learning (1976).
- **Dimensional**: IRT (Rasch, 1960; Lord, 1980); modelos de competencia cognitiva continua.

El AI-Native N4 elige tipológico. **No es decisión equivocada**, pero tiene consecuencias:
- **A favor**: las categorías son interpretables, comunicables a docentes, no inducen el mito de la métrica continua sobre una construcción esencialmente cualitativa.
- **En contra**: pierde poder estadístico para correlacionar con outcomes (transfer, calificaciones finales). Un test de transfer continuo correlacionando con 3 categorías nominales requiere ANOVA o equivalente; un test continuo correlacionando con una dimensión continua permite correlación product-moment con más sensibilidad.

### 4.2 La frontera entre categorías es algorítmica, no cognitiva

`tree.py` aplica umbrales sobre las cinco coherencias para decidir la categoría:
- `delegacion_pasiva` si `ccd_orphan_ratio ≥ 0.8` (sub-rama "extreme") O (`orphan ≥ 0.5` Y `ct_summary < 0.35`).
- `apropiacion_reflexiva` si `ct ≥ 0.65` Y `ccd_mean ≥ 0.65` Y `orphan < 0.5` Y `cii_stab > 0.2`.
- `apropiacion_superficial` default.

**Crítica cognitiva**: los umbrales (0.8, 0.65, 0.35, 0.2) son operacionalización del implementador, **sin validación empírica documentada**. Dos estudiantes con `ccd_orphan_ratio` de 0.49 y 0.51 quedan en categorías distintas si el resto de coherencias está al borde. Esa frontera no tiene anclaje cognitivo —es algorítmica.

**Lo que sí tiene el sistema**: el `Classification.reason` documenta qué rama se aplicó y con qué valores, lo cual permite auditoría. Pero no elimina el problema epistemológico: el sistema clasifica con precisión binaria sobre proceso cognitivo que es probablemente continuo y multidimensional.

### 4.3 Sin baseline individual

El árbol clasifica el episodio en absoluto, no relativamente al estudiante que lo produjo. Un estudiante con dificultades sostenidas que mejora marginalmente queda en `apropiacion_superficial` igual que un estudiante consistentemente promedio. Esto es **limitación declarada** (ADR-022 sobre alertas predictivas, sin baseline individual) y reconocida en la limitaciones-declaradas.md §2.

Desde la lente cognitiva, esto es lo más grave de la categorización del aprendizaje: el aprendizaje **es por definición cambio individual**. Sin baseline, el sistema mide proceso pero no aprendizaje. El paper lo reconoce con honestidad al posicionar H1 como "diferenciabilidad observacional entre tipos de apropiación" en lugar de "diferenciabilidad entre niveles de aprendizaje".

---

## 5. Lo que el sistema mide genuinamente

Antes de seguir con críticas, importa enumerar lo que el sistema sí captura, y lo hace mejor que muchas plataformas comerciales:

### 5.1 Auditabilidad epistémica

El **encadenamiento criptográfico append-only** (ADR-010) del CTR garantiza que cualquier tampering sobre eventos históricos invalida algorítmicamente los hashes posteriores. Esto convierte el corpus de trazas en **evidencia psicométrica auditable** —no en score arbitrario. La integridad académica del piloto descansa en esta propiedad y es defendible doctoralmente.

**Análogo en psicometría tradicional**: las pruebas estandarizadas tienen *test security protocols* para evitar adulteración. El AI-Native N4 logra equivalencia funcional para datos de proceso (trazas) en lugar de datos de resultado (respuestas). Esto es contribución metodológica genuina.

### 5.2 Reproducibilidad bit-a-bit

`LABELER_VERSION = 1.2.0` y `classifier_config_hash` permiten que un investigador externo re-ejecute la clasificación sobre los mismos eventos y obtenga el mismo resultado byte-exact. Esto cumple uno de los criterios duros de la ciencia abierta contemporánea (Open Science Foundation, 2017) y supera al estándar de muchos papers de learning analytics donde la implementación es opaca.

### 5.3 Distinción declarada entre proxy y constructo

El paper §4.3 separa explícitamente eventos (proxy directo) de constructos sintéticos (interpretación teórica). Esto es más sofisticado que la mayoría de la literatura del campo, que confunde sistemáticamente los dos niveles.

### 5.4 Rechazo del score único

El paper §4.5 declara que las cinco coherencias **no se colapsan**. Esto es una decisión cognitivamente correcta: el aprendizaje complejo es multidimensional y colapsarlo en un escalar pierde información. Reconoce explícitamente el riesgo de "usos evaluativos reduccionistas de alto stake".

### 5.5 Versionado pedagógico de prompts

`prompt_system_version` (ADR-009, RN-002) viaja con cada evento `tutor_respondio`. Esto permite que un investigador rastree qué versión del prompt produjo qué interacciones, separando el efecto de la intervención (prompt) del efecto del estudiante (interacciones). Análogo cognitivo: un tratamiento clínico con dosis registrada.

---

## 6. Lo que el sistema NO mide (y debería declararlo más claramente)

El paper (riesgos a priori declarados al final de §8 y limitación del posicionamiento al final de §9) y `docs/limitaciones-declaradas.md` reconocen varias limitaciones, pero la siguiente lista —que junto enumera lo crítico desde lente cognitiva— vale tematizarla integralmente en el paper, posiblemente creando una sub-sección dedicada (no presente en la versión actual del paper, que va de §1 a §10):

### 6.1 Validez de constructo formal

- **Ausente**: validación convergente con instrumentos estandarizados de cognición o aprendizaje (no se compara CT con instrumentos de atención sostenida, ni CCD con instrumentos de auto-explicación, ni CII con instrumentos de elaboración).
- **Ausente**: validación discriminante (no se demuestra que las cinco coherencias miden cosas teóricamente distintas; se asume).
- **Ausente**: validación criterial (no se correlaciona con outcomes externos validados).
- Cronbach & Meehl (1955) y Messick (1989) son explícitos: un instrumento puede ser confiable (kappa alto) sin ser válido. La validación intercoder (H3) cierra la confiabilidad pero deja abierta la validez.

### 6.2 Carga cognitiva

- **Ausente**: no se mide carga intrínseca, extrínseca ni germana (Sweller, 1988, 2011).
- **Implicación**: una sesión con baja CT puede ser fragmentación o puede ser sobrecarga cognitiva extrínseca (mal diseñada). El sistema no distingue.
- **Instrumentos disponibles** (a citar): NASA-TLX (Hart & Staveland, 1988), Cognitive Load Scale (Paas, 1992).

### 6.3 Metacognición

- **Parcialmente abordada por R5** (devolución metacognitiva, esqueleto OFF en ADR-050).
- **Ausente**: medidas explícitas de monitorización metacognitiva, planificación, evaluación (Flavell, 1979; Schraw, 1998).
- **Instrumentos** (a citar): MAI (Schraw & Dennison, 1994), Jr. MAI (Sperling et al., 2002).

### 6.4 Conocimiento previo / esquemas

- **Ausente**: ningún pre-test al inicio del cuatrimestre. La diferenciación entre "estudiante con esquemas previos sólidos" y "estudiante novato" es invisible para el sistema.
- **Consecuencia cognitiva**: dos estudiantes con la misma `apropiacion_reflexiva` pueden estar en momentos cognitivos muy distintos. Para uno es retención; para otro, construcción nueva. El sistema los iguala.

### 6.5 Transfer

- **Mencionado en H2** ("tareas de transferencia, controlando por nivel inicial de competencia") pero el instrumento de transfer **no está descrito ni desplegado en el piloto-1**.
- **Sin transfer**, el sistema mide proceso intra-tarea, no aprendizaje generalizable. La distinción entre aprendizaje superficial (vinculado a la tarea específica) y profundo (transferible) es históricamente la diferencia entre rote learning y meaningful learning (Ausubel, 1968; Bransford, Brown & Cocking, 2000).

### 6.6 Autoeficacia y motivación

- **Ausente**: ninguna medida de autoeficacia (Bandura, 1997), motivación intrínseca/extrínseca (Deci & Ryan, 1985), engagement afectivo.
- **Por qué importa**: las cinco coherencias son comportamentales. Dos estudiantes con la misma huella conductual pueden tener disposiciones afectivas opuestas, y esas disposiciones predicen retención y transfer.

### 6.7 Cognición distribuida — la promesa que no se mide

El marco teórico del paper (§3) declara cognición distribuida (Hutchins, 1995) y mente extendida (Clark & Chalmers, 1998) como anclajes. Pero **las cinco coherencias miden al estudiante, no al sistema cognitivo extendido** estudiante+tutor+editor+tests+enunciado. El tutor, por ejemplo, aporta cognitivamente pero su contribución no está separada operacionalmente del proceso del estudiante.

Esto es brecha entre marco teórico declarado y operacionalización efectiva. No invalida el marco, pero el paper podría tematizarlo: *"reconocemos cognición distribuida como modelo teórico pero medimos al estudiante como el componente que cambia. El sistema completo es objeto de investigación futura"*.

---

## 7. Cinco riesgos cognitivos específicos

### 7.1 Confundir patrón observable con proceso interno

`apropiacion_reflexiva` es **un patrón observable** (alta CT + alta CCD + baja orphan + cii_stab > umbral). **No es** apropiación reflexiva como evento cognitivo. El paper §4.3 lo aclara —es indicador de segundo orden— pero el lector menos atento puede tratarlo como observación. Riesgo de reificación.

**Mitigación**: en el paper, usar consistentemente *"perfil tipológico de apropiación reflexiva"* en lugar de *"apropiación reflexiva"* a secas, al menos en la primera mención.

### 7.2 La "apropiación reflexiva" como artefacto de la ventana temporal

Un estudiante que hace exactamente las mismas cosas pero las distribuye en el tiempo de manera distinta puede aterrizar en categorías distintas. Las ventanas de CT (>5min de pausa = ventana nueva) y de CCD (2min de correlación) son parámetros del implementador, no propiedades del proceso cognitivo. Dos calibraciones razonables (5 vs 6 minutos para CT) pueden producir clasificaciones distintas para los mismos eventos.

**Mitigación**: análisis de sensibilidad sobre las constantes temporales, similar al sensitivity analysis ya hecho para ADR-023 (`docs/adr/023-sensitivity-analysis.md`). Aplicar el mismo rigor a las ventanas de CT, CCD y a los umbrales de `tree.py`.

### 7.3 Ausencia de baseline individual

Sin pre-test ni medidas individuales repetidas, no hay "delta de aprendizaje". El sistema reporta procesos como si fueran estados absolutos. Si un estudiante tiene siempre `apropiacion_superficial`, el sistema no distingue entre "estabilidad" (siempre fue así) y "estancamiento" (estaba progresando y se frenó).

**Mitigación**: documentar explícitamente que el sistema mide proceso comparado con cohorte (z-score), no aprendizaje individual. Esto ya está parcialmente en limitaciones, pero merece sección propia.

### 7.4 La cadena CCD parcialmente desactivada

Repito porque es el punto más fuerte: `ccd.py:18-41` declara que la rama de prompts reflexivos **nunca se activa con datos reales del piloto**. Esto significa que CCD en el piloto-1 mide una **versión reducida** de su definición conceptual. La validación intercoder κ ≥ 0,70 sobre el árbol que usa CCD valida la versión reducida, no la conceptual.

**Mitigación**: el paper debe distinguir explícitamente *"CCD vigente en piloto-1"* (versión reducida) de *"CCD según definición conceptual"* (versión completa, post-G9). Sin esa distinción, un lector podría asumir que la validación valida el constructo completo.

### 7.5 Coherencia entre LABELER versions y CTR histórico

Las 106 classifications históricas tienen hash legacy `9dd96894...` (pre-LABELER_VERSION 1.2.0). Cualquier validación intercoder sobre clasificaciones legacy compara los etiquetadores humanos con un algoritmo distinto del que correrá en piloto-2. La re-clasificación A1 es no-negociable cognitivamente: sin ella, las correlaciones intercoder son sobre el pasado, no sobre el sistema vigente.

---

## 8. Lo que el sistema mide bien cognitivamente — síntesis positiva

Para no quedarme en crítica, sintetizo lo que el sistema mide bien:

1. **Patrones temporales de uso del asistente** (CT, CCD_mean) — observación válida en sentido descriptivo, replicable byte-exact, auditable criptográficamente.
2. **Acoplamiento conductual entre verbalización y acción** (CCD_orphan_ratio, vigente) — proxy razonable para el efecto de auto-explicación (Chi et al., 1989), aunque parcial.
3. **Persistencia léxica intra-episodio** (CII_stability) — proxy razonable para cognitive focus.
4. **Cambio léxico longitudinal** (CII_evolution intra y `cii_evolution_longitudinal` inter-episodio) — proxy razonable para sofisticación de lenguaje técnico (Vygotsky, 1934/1986), aunque superficial.
5. **Tres tipologías observacionalmente distinguibles** (H1) — diferenciabilidad de patrones de uso entre estudiantes que delegan, que ejecutan superficialmente, y que reflexionan. Hipótesis empíricamente contrastable.
6. **Cadena auditable bit-a-bit** — contribución metodológica genuina para learning analytics.

Lo que el sistema mide bien es **valioso, defendible y operacionalmente reproducible**. Lo que NO mide es **explícitamente declarado** en limitaciones y H1-H3 — y eso es académicamente íntegro.

---

## 9. Recomendaciones desde ciencia cognitiva

Cuatro líneas de profundización ordenadas no por urgencia sino por **profundidad de validación cognitiva** que aportan.

### C0 — Antes de la defensa (no requiere piloto adicional)

| # | Recomendación | Por qué cognitivamente |
|---|---|---|
| **C0.1** | Enunciar explícitamente MI1, MI2, MI3 en §4.3 del paper. Hoy están declarados pero no enunciados. | Sin la enunciación, el marco interpretativo de tercer orden queda como caja vacía. La distinción entre H y MI pierde fuerza. |
| **C0.2** | Renombrar en prosa académica `cii_evolution` → `cii_evolution_intra` (intra-episodio) en todas las menciones del paper, para distinguir de `cii_evolution_longitudinal`. Mantener nombres del código por compatibilidad. | Dos constructos distintos con etiquetas casi iguales son trampa epistemológica. La distinción semántica vale incluso si los nombres del código quedan congelados por reproducibilidad bit-a-bit. |
| **C0.3** | Documentar en el paper la **versión reducida de CCD** vigente en piloto-1 (sin rama de prompts reflexivos). Distinguir de la versión conceptual completa. | Sin esa distinción, la validación intercoder se lee como validando el constructo completo cuando en realidad valida el reducido. |
| **C0.4** | Análisis de sensibilidad sobre las constantes temporales de CT (5min) y CCD (2min) y los umbrales de `tree.py`. Mismo rigor que el ya hecho para ADR-023. | Mostrar que las clasificaciones son robustas a variaciones razonables de los parámetros aumenta la validez ecológica de las categorías. |

### C1 — Validez convergente (post-piloto-1, agenda piloto-2)

| # | Recomendación | Por qué cognitivamente |
|---|---|---|
| **C1.1** | Administrar **NASA-TLX** o Cognitive Load Scale al cierre de algunos episodios seleccionados. Correlacionar con CT y orphan_ratio. | Validez convergente con instrumento estandarizado de carga cognitiva. Si CT correlaciona negativamente con carga extrínseca, eso confirma el constructo. |
| **C1.2** | Administrar **MAI (Schraw & Dennison, 1994)** al inicio y fin del cuatrimestre. Correlacionar con CII_stability y CII_evolution. | Validez convergente con instrumento estandarizado de metacognición. Confirma que CII captura algo cognitivamente significativo. |
| **C1.3** | Diseñar e implementar el **test de transfer** mencionado en H2. Una prueba breve (15-20 min) con problemas isomórficos al banco pero no idénticos, al final del cuatrimestre. | Sin instrumento de transfer, H2 es declarativa, no contrastable. La carga doctoral del paper exige operacionalizar lo que se afirma medir. |
| **C1.4** | Administrar **escala de autoeficacia en programación** (variante de Bandura, 1997, calibrada para programación universitaria) al inicio. Controlar por autoeficacia en los análisis de H1 y H2. | Sin control de autoeficacia, las diferencias entre tipos de apropiación pueden confundirse con diferencias de disposición afectiva previa. |

### C2 — Validez discriminante (post-piloto-1)

| # | Recomendación | Por qué cognitivamente |
|---|---|---|
| **C2.1** | Análisis factorial exploratorio sobre las cinco coherencias del piloto-1 (post-A1). Reportar KMO, Bartlett, análisis paralelo. | Confirmar (o refutar) que las cinco coherencias miden cinco cosas teóricamente distintas. Si CT y CII_evolution cargan en el mismo factor, una de las dos es redundante. |
| **C2.2** | Correlacionar las cinco coherencias con el test de transfer (C1.3). Validez criterial. | Si ninguna de las cinco correlaciona con transfer, el constructo es psicométricamente débil. Si algunas sí y otras no, identificar cuáles aportan. |

### C3 — Validez de la categorización (agenda piloto-2)

| # | Recomendación | Por qué cognitivamente |
|---|---|---|
| **C3.1** | Comparar la categorización tipológica (3 categorías) con una operacionalización dimensional alternativa (por ejemplo, IRT sobre las cinco coherencias). Reportar capacidad predictiva relativa sobre el test de transfer. | Justificar empíricamente que el approach tipológico es preferible al dimensional, o reconocer que la elección es teórica más que predictiva. |
| **C3.2** | Replicar el análisis con un classifier alternativo basado en clustering (k-means o latent profile analysis) sobre las cinco coherencias. Si los clusters emergentes coinciden con las tres categorías del árbol, hay validez convergente; si no, revisar el árbol. | El árbol actual es operacionalización del implementador. Una operacionalización guiada por los datos puede validar o refutar la elección de tres categorías. |

### C4 — Cognición distribuida (agenda piloto-3 o investigación futura)

| # | Recomendación | Por qué cognitivamente |
|---|---|---|
| **C4.1** | Diseñar indicador que mida al **sistema cognitivo extendido** (estudiante+tutor+IDE+tests) en lugar de al estudiante solo. Por ejemplo: latencia entre prompt-respuesta y siguiente edición, calidad de las respuestas del tutor según evaluación humana, contribución del IDE (autocompletes, linter feedback). | Materializa el marco teórico declarado. Hoy el marco de cognición distribuida está en el paper pero la operacionalización es individual. |
| **C4.2** | Caracterizar la contribución del tutor por episodio (cantidad de información aportada, complejidad del andamiaje socrático). Separarlo de la contribución del estudiante. | Permite responder: ¿la apropiación reflexiva es del estudiante, o del par estudiante-tutor? La respuesta tiene implicancias teóricas. |

---

## 10. Conclusiones

El AI-Native N4, leído desde la lente cognitiva, es un sistema que mide **patrones observables del uso del asistente con auditabilidad criptográfica e integridad metodológica**. No es —y no pretende ser— un sistema que mide aprendizaje en sentido cognitivo estricto. La distinción no es sutileza: es **la diferencia entre evaluación de proceso (process assessment) y evaluación de aprendizaje (learning assessment)** en el sentido de Pellegrino, Chudowsky y Glaser (2001).

Las virtudes que reconozco son sustantivas: tres órdenes epistemológicos explícitos, rechazo del score único, encadenamiento criptográfico append-only, reproducibilidad bit-a-bit, anclaje en evidence-centered design y cognición distribuida, declaración honesta de las limitaciones. Estas virtudes posicionan al proyecto teóricamente por delante de la mayoría de las plataformas de learning analytics que reducen la operacionalización a un score de engagement opaco.

Las brechas que identifico son brechas de **profundidad de validación**, no de concepción: el constructo de apropiación está operacionalizado pero no validado contra instrumentos convergentes; el aprendizaje en sentido cognitivo está implícito pero no medido directamente; el marco de cognición distribuida está declarado pero no instrumentado completamente. Estas brechas son legítimas en un piloto académico de primer año y son cerrables en agendas sucesivas (recomendaciones C1-C4).

Doctoralmente, mi lectura es: el modelo cognitivo subyacente al AI-Native N4 es **defendible y sofisticado** en su versión actual. Lo que falta —y debería hacerse explícito en el paper antes de la defensa— es la **declaración cuidadosa de qué exactamente se mide**: procesos observables de uso del asistente con interpretación tipológica, validados internamente por intercoder, sin pretensión por ahora de validar el constructo de aprendizaje en sentido cognitivo estricto. Esa declaración es honestidad académica, no debilidad; es la diferencia entre un piloto bien situado y uno que sobreafirma.

Sócrates no escribió. Lo que pasó a la posteridad pasó por la mediación de Platón. Hoy el AI-Native N4 escribe cada acción del estudiante con hash criptográfico determinista. La mediación es algoritmo, no es Platón —pero es mediación al fin. Lo que el sistema hace bien es preservar la trazabilidad de esa mediación. Lo que aún no hace —y debería tematizar— es declarar que la mediación no es el proceso cognitivo subyacente. El proceso vive en el estudiante; el sistema captura su sombra.

Lo cual, leído con generosidad académica, es exactamente lo que el paper §4.3 dice cuando distingue tres órdenes epistemológicos. La consigna para la defensa es **honrar literalmente esa distinción** en cada afirmación del paper, sin que el entusiasmo por las cinco coherencias colapse la sombra con el cuerpo.

---

**Documentos consultados** (en orden de relevancia para este informe):

- `AI-NativeV3-main/docs/papers/paper-draft.md` §§2-4, §6, §8 (marco teórico, hipótesis, hallazgos preliminares)
- `AI-NativeV3-main/apps/classifier-service/src/classifier_service/services/ct.py` (158 líneas)
- `AI-NativeV3-main/apps/classifier-service/src/classifier_service/services/ccd.py` (162 líneas)
- `AI-NativeV3-main/apps/classifier-service/src/classifier_service/services/cii.py` (85 líneas)
- `AI-NativeV3-main/apps/classifier-service/src/classifier_service/services/tree.py` (158 líneas)
- `AI-NativeV3-main/apps/classifier-service/src/classifier_service/services/event_labeler.py` (309 líneas)
- `AI-NativeV3-main/docs/limitaciones-declaradas.md` (110 líneas)
- `AI-NativeV3-main/CLAUDE.md` secciones "Propiedades críticas" y "Estado actual"
- ADRs relevantes: 010, 018, 020, 022, 023, 027, 035, 043, 044, 045, 046
- `informeSoc.md` (informe complementario desde lente didáctica socrática, 2026-05-16)

**Marco teórico de referencia** (en orden alfabético):

- Anderson, J. R. (1983). *The architecture of cognition*. Harvard University Press.
- Anderson, J. R. (1996). ACT: A simple theory of complex cognition. *American Psychologist*, 51(4), 355-365.
- Anderson, L. W., & Krathwohl, D. R. (Eds.). (2001). *A taxonomy for learning, teaching, and assessing*. Longman.
- AERA, APA, & NCME (2014). *Standards for educational and psychological testing*. American Educational Research Association.
- Ausubel, D. P. (1968). *Educational psychology: A cognitive view*. Holt, Rinehart and Winston.
- Bandura, A. (1997). *Self-efficacy: The exercise of control*. W. H. Freeman.
- Biggs, J. B., & Collis, K. F. (1982). *Evaluating the quality of learning: The SOLO taxonomy*. Academic Press.
- Bjork, R. A., & Bjork, E. L. (2011). Making things hard on yourself, but in a good way. *Psychology and the real world*, 2(59-68).
- Bransford, J. D., Brown, A. L., & Cocking, R. R. (Eds.). (2000). *How people learn: Brain, mind, experience, and school*. National Academy Press.
- Carroll, J. B. (1963). A model of school learning. *Teachers College Record*, 64(8), 723-733.
- Chi, M. T. H., Bassok, M., Lewis, M. W., Reimann, P., & Glaser, R. (1989). Self-explanations: How students study and use examples in learning to solve problems. *Cognitive Science*, 13(2), 145-182.
- Chi, M. T. H. (2000). Self-explaining expository texts. En R. Glaser (Ed.), *Advances in instructional psychology* (Vol. 5, pp. 161-238). Lawrence Erlbaum.
- Chi, M. T. H., & Wylie, R. (2014). The ICAP framework: Linking cognitive engagement to active learning outcomes. *Educational Psychologist*, 49(4), 219-243.
- Clark, A., & Chalmers, D. (1998). The extended mind. *Analysis*, 58(1), 7-19.
- Cronbach, L. J., & Meehl, P. E. (1955). Construct validity in psychological tests. *Psychological Bulletin*, 52(4), 281-302.
- Deci, E. L., & Ryan, R. M. (1985). *Intrinsic motivation and self-determination in human behavior*. Plenum.
- Flavell, J. H. (1979). Metacognition and cognitive monitoring. *American Psychologist*, 34(10), 906-911.
- Hart, S. G., & Staveland, L. E. (1988). Development of NASA-TLX. *Advances in Psychology*, 52, 139-183.
- Hutchins, E. (1995). *Cognition in the wild*. MIT Press.
- Koedinger, K. R., Corbett, A. T., & Perfetti, C. (2012). The Knowledge-Learning-Instruction framework. *Cognitive Science*, 36(5), 757-798.
- Landis, J. R., & Koch, G. G. (1977). The measurement of observer agreement for categorical data. *Biometrics*, 33(1), 159-174.
- Lord, F. M. (1980). *Applications of item response theory to practical testing problems*. Lawrence Erlbaum.
- Marton, F., & Säljö, R. (1976). On qualitative differences in learning. *British Journal of Educational Psychology*, 46(1), 4-11.
- Messick, S. (1989). Validity. En R. L. Linn (Ed.), *Educational measurement* (3rd ed., pp. 13-103). American Council on Education.
- Mislevy, R. J., Steinberg, L. S., & Almond, R. G. (2003). On the structure of educational assessments. *Measurement: Interdisciplinary Research and Perspectives*, 1(1), 3-62.
- Paas, F. G. W. C. (1992). Training strategies for attaining transfer of problem-solving skill in statistics. *Journal of Educational Psychology*, 84(4), 429-434.
- Pellegrino, J. W., Chudowsky, N., & Glaser, R. (Eds.). (2001). *Knowing what students know*. National Academy Press.
- Posner, M. I., & Petersen, S. E. (1990). The attention system of the human brain. *Annual Review of Neuroscience*, 13, 25-42.
- Rabardel, P. (1995). *Les hommes et les technologies*. Armand Colin.
- Rasch, G. (1960). *Probabilistic models for some intelligence and attainment tests*. Danish Institute for Educational Research.
- Roediger, H. L., & Karpicke, J. D. (2006). The power of testing memory. *Perspectives on Psychological Science*, 1(3), 181-210.
- Schraw, G. (1998). Promoting general metacognitive awareness. *Instructional Science*, 26(1), 113-125.
- Schraw, G., & Dennison, R. S. (1994). Assessing metacognitive awareness. *Contemporary Educational Psychology*, 19(4), 460-475.
- Sperling, R. A., Howard, B. C., Miller, L. A., & Murphy, C. (2002). Measures of children's knowledge and regulation of cognition. *Contemporary Educational Psychology*, 27(1), 51-79.
- Sweller, J. (1988). Cognitive load during problem solving. *Cognitive Science*, 12(2), 257-285.
- Sweller, J. (1994). Cognitive load theory, learning difficulty, and instructional design. *Learning and Instruction*, 4(4), 295-312.
- Sweller, J. (2011). Cognitive load theory. *Psychology of Learning and Motivation*, 55, 37-76.
- Veenman, M. V. J., Van Hout-Wolters, B. H. A. M., & Afflerbach, P. (2006). Metacognition and learning. *Metacognition and Learning*, 1(1), 3-14.
- Vygotsky, L. S. (1934/1986). *Thought and language* (A. Kozulin, Trad.). MIT Press.
- Vygotsky, L. S. (1978). *Mind in society*. Harvard University Press.
