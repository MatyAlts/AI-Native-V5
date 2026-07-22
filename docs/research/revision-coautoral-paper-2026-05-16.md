# Material para sesión coautoral — revisión de las 7 ediciones DRAFT del paper

**Fecha de preparación**: 2026-05-16
**Para**: Alberto A. Cortez (autor principal) y Ana Garis (co-autora)
**Origen**: ejecución de `plan1Socra.md` (acciones P0 derivadas del análisis cognitivo `informeSocra1.md`).
**Objetivo de la sesión**: aprobar, modificar o rechazar las 7 ediciones DRAFT aplicadas al `paper-draft.md` antes de submisión. Cada edición estuvo marcada en el paper con `<!-- DRAFT csXX -->` durante la fase de preparación.

> **ACTUALIZACIÓN 2026-05-16 (cierre de sesión)**: las 7 ediciones fueron **consolidadas en el paper y propagadas a la tesis** (`tesis16mayo.docx`) sin esperar a la sesión coautoral, por decisión del autor principal. Los HTML comments `<!-- DRAFT csXX -->` fueron removidos del paper-draft.md. Las ediciones son ahora texto del paper. La sesión coautoral con Ana Garis sigue siendo recomendable como **revisión post-consolidación** —para refinar redacción o reformular puntos específicos— pero no es bloqueante para el avance del trabajo. Este documento se mantiene como **registro de la motivación y de las opciones consideradas** para cada edición, útil si la revisión post-consolidación decide rollback de alguna o reformulación.

---

## 0. Antes de la sesión

### 0.1 Cómo se preparó este material

Las 7 ediciones se aplicaron al paper-draft.md como respuesta a observaciones específicas del informe cognitivo externo (`informeSocra1.md`). Cada edición lleva su comentario HTML que la identifica. Para esta sesión:

1. Leer las 7 ediciones en el orden propuesto a continuación (de menor a mayor complejidad de revisión).
2. Para cada una: aprobar tal cual, aprobar con modificaciones (con propuesta de texto), o rechazar (con justificación).
3. Las decisiones se marcan en este mismo documento al final de cada sección.
4. Post-sesión: sub-agente o el propio autor remueve los HTML comments de las ediciones aprobadas, aplica las modificaciones acordadas, y registra los rechazos en `docs/SESSION-LOG.md`.

### 0.2 Tiempo total estimado

**2h 15min** dividido en 7 bloques:

| Orden | Edición | Tipo | Tiempo |
|---|---|---|---|
| 1 | CS02 | Prosa terminológica simple | 5 min |
| 2 | CS08 | Nota a pie sobre decisión de diseño | 5 min |
| 3 | CS07 | Glosa terminológica + reformulación | 10 min |
| 4 | CS03 | Distinción CCD-piloto-1 vs CCD-conceptual | 15 min |
| 5 | CS06 | Asimetría cognición distribuida (1 párrafo) | 20 min |
| 6 | CS05 | Process vs learning assessment (2 párrafos) | 30 min |
| 7 | CS01 | Enumeración MI1, MI2, MI3 (4 párrafos) | 50 min |
| — | Síntesis + próximos pasos | — | 10 min |
| **Total** | | | **2h 25min** |

---

## 1. Edición CS02 — Distinción `cii_evolution_intra` vs `cii_evolution_longitudinal` en prosa

**Ubicación**: `paper-draft.md` §4.5 línea 132 (párrafo sobre correspondencia 3 dimensiones → 5 métricas).
**Tipo**: prosa académica. Cambio mínimo, no agrega tesis nueva.

### 1.1 Texto ANTES (versión original)

> "La coherencia inter-iteración (CII) se desdobla en CII estabilidad, que captura la similitud léxica intra-episodio mediante Jaccard de tokens entre prompts consecutivos, y CII evolución, que captura la pendiente longitudinal multi-episodio de complejidad de prompts a través de tareas análogas; ambos sub-indicadores operan en escalas temporales distintas y responden a preguntas analíticas separables."

### 1.2 Texto DESPUÉS (DRAFT cs02)

> "La coherencia inter-iteración (CII) se desdobla en CII estabilidad, que captura la similitud léxica intra-episodio mediante Jaccard de tokens entre prompts consecutivos, y **CII evolución intra-episodio**, que captura la pendiente intra-episodio de complejidad de prompts dentro de una misma sesión de trabajo, complementada por **CII evolución longitudinal**, que captura la pendiente inter-episodio de la categoría de apropiación a través de tareas análogas identificadas por una misma plantilla académica (Sección 5.2 sobre operacionalización); ambos sub-indicadores intra-episodio operan en la misma escala temporal pero responden a preguntas analíticas separables (similitud léxica versus elaboración creciente), y el indicador longitudinal opera en escala temporal distinta sobre la trayectoria del estudiante."

### 1.3 Motivación

`informeSocra1.md` §3.3: la versión original confundía `cii_evolution` (intra-episodio, pendiente léxica) con `cii_evolution_longitudinal` (inter-episodio, slope ordinal de apropiación). Dos constructos teóricamente distintos con etiquetas casi iguales — trampa epistemológica.

### 1.4 Pregunta para Ana Garis

¿La distinción explícita en prosa entre los dos indicadores (con el agregado de "intra-episodio" y "longitudinal") es la formulación correcta, o preferís otra terminología?

### 1.5 Decisión

- [ ] Aprobar tal cual
- [ ] Aprobar con modificación: ________________________________
- [ ] Rechazar — razón: ________________________________

---

## 2. Edición CS08 — Nota sobre ratio prompt:exec como decisión del implementador

**Ubicación**: `paper-draft.md` §4.5 Tabla 3, celda CT (línea 128).
**Tipo**: nota inline. No modifica el texto principal de la tabla.

### 2.1 Texto AGREGADO (DRAFT cs08, dentro de la celda CT)

Comentario HTML dentro de la celda, con un agregado de redacción a discutir:

> "(El 'rango saludable' del ratio prompt/(prompts+ejec) cercano a 1:1 es decisión de diseño del implementador y NO derivación de literatura cognitiva establecida; queda como operacionalización inicial sujeta a calibración empírica post-A1 sobre las 106 históricas.)"

### 2.2 Motivación

`informeSocra1.md` §3.1: el ratio 1:1 como "saludable" en `compute_ct_summary` (parte del módulo `ct.py`) es decisión del implementador, sin literatura cognitiva que lo justifique. Defensible como operacionalización inicial, problemático si se presenta como universal.

### 2.3 Pregunta para Ana Garis

¿La nota merece quedar **inline en la celda CT** de la Tabla 3, o vale mover a un párrafo aparte después de la tabla? Inline es más visible para el revisor; párrafo aparte es menos invasivo.

### 2.4 Decisión

- [ ] Aprobar nota inline en la celda
- [ ] Mover la nota a párrafo aparte después de la tabla
- [ ] Texto modificado: ________________________________
- [ ] Rechazar — razón: ________________________________

---

## 3. Edición CS07 — Glosa terminológica "perfil tipológico de"

**Ubicación**: `paper-draft.md` §4.4 líneas 95-108 (introducción de los tres tipos de apropiación).
**Tipo**: cambio léxico + nota terminológica.

### 3.1 Texto ANTES

> "Una contribución específica del modelo es la caracterización de tres tipos de apropiación de la IA observables al nivel N4. Estos tipos no son exhaustivos ni mutuamente excluyentes en sentido estricto (un mismo estudiante puede exhibir distintos tipos en distintos momentos del curso) pero operan como categorías pedagógicamente productivas."

### 3.2 Texto DESPUÉS (DRAFT cs07)

> "Una contribución específica del modelo es la caracterización de tres **perfiles tipológicos de apropiación de la IA** observables al nivel N4: **perfil de delegación pasiva, perfil de apropiación superficial y perfil de apropiación reflexiva**. Estos perfiles tipológicos no son exhaustivos ni mutuamente excluyentes en sentido estricto (un mismo estudiante puede exhibir distintos perfiles en distintos momentos del curso) pero operan como categorías pedagógicamente productivas."

**Más nota terminológica posterior** (5 líneas) explicando que en lo sucesivo el paper emplea "perfil tipológico de apropiación X" para anclar al lector en el segundo orden epistemológico (§4.3, Fig. 2), previniendo reificación.

### 3.3 Motivación

`informeSocra1.md` §7.1 (riesgo de reificación): "apropiación reflexiva" leído sin marca puede convertirse en identidad del estudiante en lugar de descripción de patrón observacional. El sustantivo "perfil" funciona como marcador léxico anclando la lectura.

### 3.4 Pregunta para Ana Garis

Tres opciones:
- **(a)** Usar "perfil tipológico" en primera mención y abreviado en menciones subsiguientes (propuesta actual).
- **(b)** Usar "perfil tipológico" siempre que aparezca la categoría — más pedante pero menos riesgo de drift.
- **(c)** No introducir el sustantivo "perfil" — confiar en la fuerza del §4.3 (tres órdenes epistemológicos) para anclar al lector. Rechazar la edición.

### 3.5 Decisión

- [ ] Aprobar opción (a) — perfil en primera mención + abreviado después
- [ ] Aprobar opción (b) — perfil siempre
- [ ] Rechazar — confiar en §4.3 (opción c)
- [ ] Otro: ________________________________

---

## 4. Edición CS03 — Distinción CCD-piloto-1 vs CCD-conceptual

**Ubicación**: `paper-draft.md` §4.5 Tabla 3, celda CCD (línea 129).
**Tipo**: nota crítica sobre validez del constructo.

### 4.1 Texto AGREGADO (DRAFT cs03, dentro de la celda CCD)

> "(La operacionalización de CCD vigente en piloto-1, CCD-piloto-1, considera únicamente `anotacion_creada` como fuente de verbalización reflexiva, ya que la clasificación automática de `prompt_kind` —G9, Eje B post-defensa— no está implementada y el tutor-service emite siempre `prompt_kind=solicitud_directa`. La CCD conceptual completa, CCD-conceptual, incluiría también prompts reflexivos y se materializará post-G9. La validación intercoder κ ≥ 0,70 del piloto-1 valida CCD-piloto-1, no CCD-conceptual.)"

### 4.2 Motivación

`informeSocra1.md` §3.2 (la crítica más grave del informe cognitivo): el módulo `ccd.py` declara explícitamente en su docstring que la rama de prompts reflexivos "nunca se activa con datos reales del piloto" porque el tutor-service no emite `prompt_kind="reflexion"`. La validación intercoder se hace sobre la versión reducida de CCD, no sobre la conceptual completa.

### 4.3 Impacto académico

Esta es la edición más sensible: la honestidad académica del paper depende de que la distinción quede explícita ANTES de submisión. Un reviewer del campo que detecte la discrepancia entre la operacionalización del paper y la del código (donde la limitación está claramente documentada) puede cuestionar la integridad metodológica del trabajo.

### 4.4 Pregunta para Ana Garis

Tres opciones:
- **(a)** Mantener la nota inline en la celda CCD (propuesta actual).
- **(b)** Expandir la nota a un párrafo propio después de la Tabla 3 con más contexto (la distinción es lo bastante importante para merecer espacio aparte).
- **(c)** Mover la nota a §8 (donde se declaran riesgos a priori del estudio) o crear sub-sección nueva §4.5.bis "Operacionalización vigente vs conceptual", dejando la Tabla 3 más limpia. *(Nota 2026-05-16: el paper actual no tiene §15 Limitaciones formal; lo que más se parece es la declaración de "cinco riesgos a priori" al final de §8.)*

Recomendación del que prepara este material: **(b)**, por la sensibilidad académica del punto.

### 4.5 Decisión

- [ ] Aprobar opción (a) — inline en celda
- [ ] Aprobar opción (b) — párrafo propio post-tabla
- [ ] Aprobar opción (c) — mover a §8 (riesgos a priori) o crear §4.5.bis
- [ ] Modificar texto: ________________________________
- [ ] Rechazar — razón: ________________________________

---

## 5. Edición CS06 — Asimetría cognición distribuida declarada vs operacionalizada

**Ubicación**: `paper-draft.md` §3 (Marco teórico), después del párrafo sobre los tres órdenes epistemológicos. Línea ~47-49.
**Tipo**: párrafo nuevo de ~10 líneas.

### 5.1 Texto AGREGADO (DRAFT cs06) — versión actual del paper post-arreglo 2026-05-16

> "Una asimetría entre el marco teórico declarado y la operacionalización efectiva del Modelo N4 merece tematización explícita. Las tesis de cognición distribuida (Hutchins, 1995) y mente extendida (Clark y Chalmers, 1998) sostienen que el sistema cognitivo relevante para el aprendizaje en interacción con asistentes de IA no es el estudiante individual considerado en aislamiento sino el sistema acoplado estudiante-tutor-IDE-tests-enunciado. La operacionalización empírica del Modelo N4 mediante las cinco coherencias agregadas mide, sin embargo, al estudiante como nodo del sistema; la contribución cognitiva específica del tutor (calidad del andamiaje socrático, complejidad pedagógica del prompt vigente, profundidad de las respuestas) no se desagrega operacionalmente de la trayectoria estudiantil en la versión actual del clasificador. La consecuencia metodológica es que las inferencias del clasificador sobre apropiación se realizan sobre un nodo del sistema distribuido y no sobre el sistema entero. Esta asimetría no invalida los indicadores —el estudiante es el componente que cambia y que el modelo se propone evaluar formativamente—, pero exige declarar el alcance de las afirmaciones: el sistema mide patrones de uso del asistente por el estudiante, no propiedades emergentes del sistema cognitivo distribuido completo. La operacionalización de indicadores del sistema extendido (caracterización de la contribución del tutor por episodio, separación de la contribución del IDE, latencias clave del bucle de retroalimentación) constituye **agenda de investigación futura sobre cognición distribuida instrumentada, articulada con la agenda confirmatoria de la Sección 8**."

### 5.2 Motivación

`informeSocra1.md` §6.7 ("Cognición distribuida — la promesa que no se mide"): el paper cita Hutchins y Clark & Chalmers como anclajes teóricos, pero las cinco coherencias miden al estudiante solo. Brecha entre marco declarado y operacionalización. Tematizarla es integridad académica.

### 5.3 Riesgo del texto actual — RESUELTO

El borrador inicial del párrafo cerraba con "Línea 8 de la agenda confirmatoria de la Sección 8". Verificación: §8 del paper actual cierra con "siete líneas" (no ocho), por lo que la referencia era inconsistente. **Aplicada opción (b) en sesión de preparación 2026-05-16**: el cierre se reformuló a "agenda de investigación futura sobre cognición distribuida instrumentada, articulada con la agenda confirmatoria de la Sección 8". El paper-draft.md ya tiene esta versión. La sesión coautoral igual puede revisar si conviene además agregar la Línea 8 explícita a §8 (opción a abajo), pero el párrafo CS06 ya no depende de ello.

### 5.4 Pregunta para Ana Garis

¿Aprobás la tematización del párrafo CS06 (texto ya consistente en paper)?
- **(a)** Aprobar **y además agregar una Línea 8 explícita a §8**: "operacionalización de indicadores del sistema cognitivo extendido (caracterización de la contribución del tutor, separación del IDE, latencias del bucle)". Esto refuerza la articulación entre §3 y §8.
- **(b)** Aprobar el párrafo tal como quedó (formulación genérica), **sin modificar §8**. Es la versión actual del paper. Es la opción más conservadora.
- **(c)** Rechazar la tematización — la asimetría se atiende mejor como nota corta en §9 o §10. Eliminar el párrafo CS06.

### 5.5 Decisión

- [ ] Aprobar opción (a) — párrafo + agregar Línea 8 a §8 (modificar §8)
- [ ] Aprobar opción (b) — párrafo con formulación genérica, no tocar §8 (versión actual)
- [ ] Aprobar opción (c) — eliminar CS06 y reemplazar por nota corta en §9/§10
- [ ] Rechazar — razón: ________________________________

---

## 6. Edición CS05 — Process assessment vs learning assessment (Pellegrino et al., 2001)

**Ubicación**: `paper-draft.md` §9 (Discusión), antes del último párrafo sobre limitaciones del posicionamiento.
**Tipo**: dos párrafos nuevos.

### 6.1 Texto AGREGADO (DRAFT cs05) — primer párrafo

> "Un segundo posicionamiento epistemológico merece tematizarse antes del cierre. El presente trabajo presenta un sistema de medición del proceso cognitivo del estudiante en interacción con un asistente de IA, no un sistema de medición del aprendizaje en sentido cognitivo estricto. La distinción es fundacional en el campo de la medición educativa contemporánea: Pellegrino, Chudowsky y Glaser (2001), en su síntesis fundamental sobre evaluación basada en evidencia, distinguen entre process assessment (medición de patrones del proceso cognitivo) y learning assessment (medición del cambio cognitivo entre estados, típicamente pre y post intervención). El sistema instrumental que materializa el Modelo N4 opera explícitamente sobre el primer registro: las cinco coherencias agregadas, los indicadores derivados y los perfiles tipológicos de apropiación capturan patrones observables del uso del asistente, no el aprendizaje individual generalizable. La hipótesis H1 se formula con precisión sobre esta operacionalización: postula diferenciabilidad observacional entre tipos de apropiación, no entre niveles de aprendizaje. La hipótesis H2 articula la asociación con desempeño en tareas de transferencia como articulación necesaria entre process assessment y learning assessment, articulación que el piloto actual no resuelve completamente porque el instrumento de transfer está operacionalizado pero el reclutamiento del grupo de comparación sigue en curso."

### 6.2 Texto AGREGADO (DRAFT cs05) — segundo párrafo

> "La consecuencia metodológica honesta es que las afirmaciones del paper sobre apropiación deben leerse como afirmaciones sobre proceso observable, no como afirmaciones sobre aprendizaje individual generalizable. Un estudiante clasificado con perfil reflexivo durante un episodio puede o no estar aprendiendo en sentido cognitivo estricto; el clasificador no responde esa pregunta. Lo que responde es: el perfil de uso del asistente que el estudiante exhibió en este episodio es distinguible observacionalmente de los perfiles delegativo o superficial. La validación de la asociación entre perfil de uso y aprendizaje generalizable es objeto del análisis cuantitativo de H2, pendiente al cierre de esta versión del reporte, y constituye uno de los hitos del estudio empírico completo. La distinción entre process assessment y learning assessment no es debilidad sino integridad metodológica: el modelo afirma exactamente lo que opera para verificar, y declara explícitamente lo que sus instrumentos no permiten todavía concluir."

### 6.3 Motivación

`informeSocra1.md` §0 (observación 1) y §10 (conclusiones): el sistema mide proceso observable, no aprendizaje en sentido cognitivo estricto. La distinción —fundacional en Pellegrino, Chudowsky & Glaser (2001)— debe quedar tematizada para que un reviewer no la lea como sobreafirmación.

### 6.4 Pregunta para Ana Garis

Cuatro opciones:
- **(a)** Aprobar los dos párrafos tal cual en §9 (propuesta actual).
- **(b)** Aprobar el primer párrafo y eliminar el segundo (que es más interpretativo).
- **(c)** Crear sub-sección nueva §9.X "Alcance epistemológico de las afirmaciones" en lugar de pegar los párrafos en el flujo de §9 actual. Alternativamente, integrar como extensión de los "cinco riesgos a priori" al final de §8. *(Nota 2026-05-16: el paper actual no tiene §15 Limitaciones formal; este tipo de declaraciones convive con la "limitación del posicionamiento" al final de §9 o con los riesgos a priori de §8.)*
- **(d)** Rechazar — riesgo de que el paper se vuelva demasiado defensivo.

Recomendación del que prepara: **(a)** o **(c)** según gusto académico. La tematización es necesaria; la ubicación es discutible.

### 6.5 Decisión

- [ ] Aprobar opción (a) — dos párrafos en §9 (versión actual)
- [ ] Aprobar opción (b) — solo el primer párrafo
- [ ] Aprobar opción (c) — sub-sección nueva §9.X o extensión de §8 riesgos
- [ ] Rechazar (opción d) — razón: ________________________________

---

## 7. Edición CS01 — Enumeración explícita de MI1, MI2, MI3 en §4.3

**Ubicación**: `paper-draft.md` §4.3, después del párrafo sobre los tres órdenes (línea ~80) y antes de §4.4. Cuatro párrafos nuevos.
**Tipo**: el más sustantivo. Agrega contenido teórico no menor.
**Importancia académica**: muy alta. Es el agujero más visible del paper (Fig. 2 menciona MI1-MI3 pero el cuerpo no los enuncia).

### 7.1 Texto AGREGADO (DRAFT cs01) — párrafos completos

**Párrafo 1 (MI1 — Calidad epistémica de la trayectoria):**
> "Tres marcos interpretativos de tercer orden articulan la lectura conceptual de los resultados sin pretender contrastación cuantitativa directa. El primero, MI1 (calidad epistémica de la trayectoria), formula que los perfiles tipológicos de apropiación capturados por el clasificador no son meramente conductuales sino epistémicamente diferenciados: el perfil reflexivo se sostiene sobre una relación con la IA en la que el estudiante interroga las razones, contrasta alternativas y verifica críticamente las propuestas, mientras que el perfil delegativo se sostiene sobre una relación en la que el estudiante recibe propuestas sin interrogarlas. La calidad epistémica no es propiedad observable directamente; es horizonte interpretativo de los indicadores de segundo orden. Su validación es indirecta y procede por triangulación con el juicio docente experto sobre las trayectorias y con la auto-reconstrucción del estudiante en entrevista."

**Párrafo 2 (MI2 — Apropiación reflexiva en sentido fuerte):**
> "El segundo, MI2 (apropiación reflexiva en sentido fuerte), formula que los perfiles clasificados como reflexivos por el sistema operacionalizan parcialmente —no agotan— el constructo filosófico-pedagógico de la apropiación en sentido fuerte. La apropiación en sentido fuerte implicaría que el estudiante puede explicar a posteriori el porqué de cada decisión interactuada con el asistente, integrar lo apropiado a su repertorio cognitivo activo y transferir lo aprendido a situaciones nuevas. El sistema instrumental captura proxies observacionales de este constructo (verificación crítica, reformulación productiva, integración con capacidad de explicación posterior) pero no el constructo entero. La distinción entre operacionalización empírica y constructo conceptual es deliberada y honra el principio de no-reducción del protocolo interpretativo (§7.4)."

**Párrafo 3 (MI3 — Coherencia estructural multidimensional como horizonte evaluativo):**
> "El tercero, MI3 (coherencia estructural multidimensional como horizonte evaluativo), formula que la coherencia estructural en sus tres dimensiones (CT, CCD, CII) opera como horizonte evaluativo del proceso cognitivo, distinto de las medidas individuales de cada dimensión. La coherencia estructural multidimensional no es la suma ni el promedio de las cinco métricas operacionalizadas en el clasificador; es la articulación interpretativa que el docente lee sobre el perfil conjunto. El rechazo explícito de la colapsación a un score único (§4.5) honra este marco: la coherencia es horizonte de lectura, no escalar comparable. La validación de MI3 procede por triangulación con el juicio docente sobre los perfiles completos y con la inspección del lenguaje narrativo del clasificador (Sección 5.2) que el docente contrasta con su propio juicio profesional."

**Párrafo 4 (Cierre — distinción MI vs H):**
> "Estos tres marcos interpretativos no son hipótesis contrastables (las hipótesis contrastables son H1-H3 sobre indicadores de segundo orden, presentadas en la Sección 6.1) sino horizontes que orientan la lectura conceptual de los resultados empíricos. Confundir MI con H comprometería la integridad metodológica del trabajo. La validación indirecta de MI1-MI3 procede por consistencia entre los hallazgos cuantitativos de H1-H3 y los hallazgos cualitativos del piloto (Sección 8): si los perfiles diferenciados por H1 son reconocibles por los docentes y reconstruibles por los estudiantes con coherencia narrativa, MI1-MI3 reciben respaldo indirecto. Si la consistencia no se establece, la formalización conceptual debe revisarse antes que abandonar los indicadores empíricos."

### 7.2 Motivación

`informeSocra1.md` §2: el paper §4.3 cita explícitamente "marco interpretativo MI1, MI2, MI3" en Fig. 2 pero **NO los enuncia en el cuerpo del paper**. Cualquier reviewer competente notaría la mención sin enunciación y consideraría que el paper está incompleto. Agujero académico subsanable.

### 7.3 Decisiones a tomar (las más sustantivas de la sesión)

**(A) Las tres formulaciones conceptuales** — ¿son las correctas?
- MI1 (calidad epistémica de la trayectoria) — ¿es el nombre adecuado, o preferís otro (ej. "calidad epistemológica del proceso")?
- MI2 (apropiación reflexiva en sentido fuerte) — ¿la distinción operacionalización-parcial / constructo-conceptual es clara?
- MI3 (coherencia estructural multidimensional como horizonte evaluativo) — ¿esto coincide con tu intención original al introducir MI3 en Fig. 2?

**(B) El orden de exposición** — ¿prefieren los 3 párrafos uno por MI, o un párrafo conjunto introductorio + 3 párrafos cortos por MI?

**(C) Las afirmaciones de validación indirecta** — ¿la formulación de cómo se valida cada MI (triangulación con juicio docente, auto-reconstrucción del estudiante, inspección narrativa) es la que vos tenías en mente?

**(D) El cierre — distinción MI vs H** — ¿el párrafo 4 cumple su rol de prevenir confusión MI/H o sobra?

### 7.4 Esfuerzo estimado de la decisión

**30-50 minutos**. Esta es la edición central de la sesión. Reservar el tiempo más largo. Es probable que después de discutir se necesite reescribir uno o más párrafos.

### 7.5 Decisión

- [ ] Aprobar los 4 párrafos tal cual
- [ ] Aprobar con modificaciones específicas:
  - MI1: ________________________________
  - MI2: ________________________________
  - MI3: ________________________________
  - Cierre: ________________________________
- [ ] Rechazar — el enunciado debe diferirse a versión 2 del paper, mantener MI1-MI3 solo en Fig. 2
- [ ] Otro: ________________________________

---

## 8. Próximos pasos post-sesión

Una vez tomadas las 7 decisiones:

### 8.1 Si la sesión aprueba todo (escenario optimista)

1. Sub-agente o autor remueve los 7 HTML comments `<!-- DRAFT csXX -->` del paper-draft.md.
2. Aplicar las modificaciones específicas acordadas en cada decisión.
3. Para CS06: si se eligió opción (a), agregar Línea 8 a §8 (agenda confirmatoria).
4. Recompilar bibliografía con las nuevas referencias incorporadas (Pellegrino, Chudowsky y Glaser, 2001 ya está mencionado; verificar que otros sean consistentes).
5. Pasada de coherencia final del paper completo.
6. Entrada en `docs/SESSION-LOG.md` documentando la revisión coautoral y las decisiones tomadas.

### 8.2 Si la sesión rechaza alguna edición (escenario realista)

Para cada edición rechazada:
1. Documentar el rechazo en `docs/SESSION-LOG.md` con la razón.
2. Si la motivación original del informe sigue siendo válida pero la edición específica no funcionó, abrir CS revisado en `plan1Socra.md` v1.1.0 con la nueva propuesta.
3. Si la motivación original ya no aplica (re-lectura del informe encontró que era incorrecta), marcar el CS como ANULADO en plan1Socra.md.

### 8.3 Si la sesión necesita más tiempo

Las 7 ediciones se pueden agrupar para revisión escalonada en 2 sesiones de ~1h:
- **Sesión 1** (CS02, CS07, CS08, CS03): ediciones ligeras + CCD reducida (35 min).
- **Sesión 2** (CS06, CS05, CS01): ediciones sustantivas (1h 40min).

---

## 9. Anexos: referencias cruzadas

### 9.1 Archivos relevantes para la sesión

- **`docs/papers/paper-draft.md`** — paper con las 7 ediciones marcadas DRAFT.
- **`informeSocra1.md`** (wrapper) — análisis cognitivo externo de origen.
- **`plan1Socra.md`** (wrapper) — plan de acción del que derivan estas 7 ediciones.
- **`AI-NativeV3-main/apps/classifier-service/src/classifier_service/services/ccd.py`** — docstring extendido en CS03.
- **`AI-NativeV3-main/apps/classifier-service/src/classifier_service/services/ct.py`** — comentario extendido en CS08.

### 9.2 Referencias bibliográficas nuevas a agregar al paper

Solo si se aprueban las ediciones correspondientes:

- **Por CS05 (process vs learning assessment)**: Pellegrino, J. W., Chudowsky, N., & Glaser, R. (Eds.). (2001). *Knowing what students know: The science and design of educational assessment*. National Academy Press. **Verificar si ya está citada por evidence-centered design en §3**; si sí, reutilizar.
- **Por CS06 (cognición distribuida)**: Hutchins (1995) y Clark & Chalmers (1998) ya están citadas en §3 — sin agregar nada nuevo.
- **Por CS01 (MI1-MI3)**: ninguna referencia nueva — son formulaciones propias de los autores.
- **Por CS03 (CCD reducida)**: ninguna referencia nueva — es declaración de limitación del piloto.

### 9.3 Quién hace qué post-sesión

| Tarea | Responsable |
|---|---|
| Remover HTML comments aprobados | Sub-agente o autor (1 h) |
| Aplicar modificaciones acordadas | Sub-agente o autor con autoridad delegada |
| Agregar Línea 8 a §8 (si CS06 opción a) | Sub-agente con redacción coordinada |
| Pasada de coherencia final | Co-autoría (autor + Ana Garis, conjunta) |
| Entrada al SESSION-LOG | Sub-agente |
| Decidir si el paper está listo para submisión post-pasada | Co-autoría |

---

## 10. Resumen de un párrafo para enviar a Ana Garis previa a la sesión

> "Ana, te paso este material para preparar la sesión coautoral del [fecha]. Son 7 ediciones que aplicamos al paper-draft.md derivadas de un análisis cognitivo externo (informeSocra1.md). Cada edición está marcada `<!-- DRAFT csXX -->` en el paper y documentada en este archivo con texto antes/después, motivación, y opciones de decisión. La sesión es de ~2h 15min. La edición más sustantiva (CS01) enuncia explícitamente MI1, MI2, MI3 que la Fig. 2 menciona pero el cuerpo no enumera — pedí que la mires con tiempo antes para que lleguemos con propuesta concreta. Las otras 6 son más ligeras. Decidimos en sesión y aplicamos post-sesión. ¿Te queda bien [fecha y hora propuestas]?"

(Adaptar fecha, hora y tono a la relación operativa entre Cortez y Garis.)
