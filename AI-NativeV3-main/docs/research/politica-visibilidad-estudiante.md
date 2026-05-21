# Política de visibilidad de datos del estudiante (R10 informeSoc.md)

**Versión**: 1.0.0 — propuesta inicial para revisión coautoral
**Fecha**: 2026-05-16
**Autor**: derivado de informeSoc.md §4 (asimetría visibilidad docente↔estudiante)
**Estado**: propuesta — requiere decisión académica de dir/co-dir + revisión Ana Garis antes de operacionalizarse.

---

## 0. Por qué este documento existe

El piloto AI-Native N4 implementa una asimetría deliberada: el estudiante produce datos que el docente interpreta. El estudiante no ve su propia etiqueta N1-N4 por evento, su categoría de apropiación, sus cinco coherencias, su slope longitudinal, ni las alertas predictivas que el docente sí puede leer sobre él.

Esa asimetría tiene defensores legítimos (evitar el efecto Heisenberg, evitar gaming del clasificador, proteger al estudiante de etiquetas que podría leer como sentencias) y costos pedagógicos (renunciar a la dimensión metacognitiva, el docente como único intérprete, la pedagogía implícita de "vos producís, otros interpretan").

Este documento existe para tematizar la decisión, explicitar el criterio, y sentar las bases para que el paper la documente en su sección ética en vez de naturalizarla por omisión.

---

## 1. Estado actual (descripción, no propuesta)

### 1.1 Lo que el estudiante VE en `web-student`

- El editor Monaco con su código.
- El TP con consigna, enunciado, criterios de aceptación visibles (test cases pero **no** rúbrica de evaluación pedagógica).
- El chat streaming con el tutor en tiempo real.
- El modal de reflexión post-cierre con 3 preguntas situadas (R6 de esta sesión).
- Los tests pasando o fallando.
- La selección de comisión donde está inscripto.

### 1.2 Lo que el estudiante NO VE

- Su etiqueta N1-N4 por evento (`event_labeler.label_event` corre en `classifier-service`, no se expone al frontend del estudiante).
- Su categoría de apropiación (`apropiacion_reflexiva` / `apropiacion_superficial` / `delegacion_pasiva`) tras el cierre del episodio.
- Sus cinco coherencias (CT, CCD_mean, CCD_orphan_ratio, CII_stability, CII_evolution).
- Su slope longitudinal por template (CII_evolution_longitudinal).
- Su posición en los cuartiles de la cohorte (k-anon N≥5).
- Las alertas predictivas que el sistema genera sobre él (`regresion_vs_cohorte`, `bottom_quartile`, `slope_negativo_significativo`).
- La rúbrica de evaluación del ejercicio (el tutor la usa como mapa privado, instrucción del prompt v1.1.0).
- Las detecciones del módulo `guardrails` (intentos adversos, overuse).
- La cadena criptográfica de su CTR (puede sospechar que existe pero no la inspecciona).

### 1.3 Lo que el docente SÍ VE en `web-teacher`

Toda la lista de "no ve" del §1.2, agregada por cohorte vía las vistas: ProgressionView, StudentLongitudinalView, CohortAdversarialView, EpisodeNLevelView, KappaRatingView, CorreccionesView. Más auditoría criptográfica del CTR vía `AuditoriaPage` (ADR-031).

### 1.4 Lo que ve administración en `web-admin`

Configuración de tenant, BYOK keys, bulk-import de inscripciones, gestión de universidades/facultades/carreras. **No** ve diagnósticos pedagógicos por estudiante.

---

## 2. Justificación pedagógica de la asimetría actual

### 2.1 Argumentos a favor (los que sostienen el diseño actual)

**A1. Efecto Heisenberg**: si el estudiante ve su etiqueta N1-N4 en tiempo real, puede modificar su comportamiento para optimizar la métrica en vez de aprender. Caso clásico: estudiante que ve que está en N2 mucho tiempo y empieza a "hacer prompts" no porque tenga preguntas sino porque sabe que N4 "está bien visto". El acto de medir cambia lo medido.

**A2. Gaming del clasificador**: si el estudiante conoce las cinco coherencias y sus umbrales, puede optimizar para los umbrales sin desarrollar el constructo subyacente. CCD_orphan_ratio se infla artificialmente con prompts vacíos, CII_evolution se infla copiando registro del tutor.

**A3. Etiqueta como sentencia**: "delegación pasiva" leído por un estudiante puede convertirse en identidad ("soy un estudiante delegador") en vez de en observación situada de un episodio puntual. La estabilidad léxica de las categorías (las mismas tres en todos los episodios) refuerza ese riesgo.

**A4. Asimetría docente-estudiante en evaluación**: la evaluación universitaria tradicional tiene esa asimetría —el docente sabe la nota antes que el estudiante, el examinador ve la rúbrica que el examinado no ve. No es novedad ética del piloto.

**A5. Carga cognitiva**: agregar al estudiante un panel con 5 coherencias + 1 categoría + n_level por evento + slope + cuartil + alertas es introducir 9+ variables nuevas sin pedagogía de uso. Probablemente sería ignorado o malinterpretado.

### 2.2 Argumentos en contra (los que cuestionan el diseño actual)

**B1. Pérdida de metacognición**: la investigación contemporánea (Flavell 1979, Schraw 1998, Veenman 2006) muestra que la metacognición se entrena haciendo visible al estudiante el patrón de su propio pensamiento. Esconder los datos al productor de esos datos es renunciar a la mitad del potencial formativo.

**B2. El docente como único intérprete no escala**: en una comisión de 30 estudiantes, el docente UTN no va a leer 30 progresiones longitudinales con 5 coherencias cada una. Las alertas predictivas funcionan como filtro, pero el estudiante "que no dispara alertas" queda invisibilizado por su propia regularidad —incluso si esa regularidad es estancamiento.

**B3. Pedagogía implícita de "objeto vs sujeto"**: el contrato actual le enseña al estudiante que él es la fuente del dato y que el saber sobre su pensamiento vive en otro. Eso es una pedagogía, no es neutral, no aparece tematizada en el paper.

**B4. Asimetría de la evaluación tradicional es justamente lo que el modelo crítica**: el paper (§2 Antecedentes) se posiciona contra la evaluación tradicional que solo mira producto y no proceso. Mantener la asimetría docente-estudiante del proceso reproduce el patrón que se proponía superar.

**B5. Consentimiento informado real**: si el estudiante firma consentimiento para participar del piloto pero NO ve qué se infiere sobre él, el consentimiento es formal pero no sustantivo. Sabe que se recolectan datos pero no qué se concluye con ellos.

### 2.3 Síntesis de la tensión

Los argumentos A son operacionales y conservadores —protegen el experimento y al estudiante de identidades reductivas. Los argumentos B son normativos y formativos —exigen coherencia entre el discurso pedagógico del modelo y el contrato real con el estudiante.

**Ambos lados tienen razón parcial**. La política propuesta a continuación intenta capturar lo legítimo de cada lado sin imponer una solución por defecto.

---

## 3. Política propuesta (para revisión, NO operacional aún)

### 3.1 Principio rector

**Visibilidad asimétrica calibrada por riesgo de identidad reductiva, NO por capacidad técnica de mostrar el dato.**

Lo que se muestra al estudiante NO depende de "se puede graficar fácilmente" sino de "es lo que mejor le sirve a su metacognición sin riesgo de identidad reductiva".

### 3.2 Tres niveles de visibilidad

**Nivel 0 (estudiante ve siempre)** — datos sin riesgo de identidad reductiva:
- Su código y su historia de ejecuciones (ya visible).
- Su historial de mensajes con el tutor (ya visible).
- Sus reflexiones post-cierre anteriores (R6 extendido — proponer endpoint `GET /api/v1/students/me/reflections/recent` con paginación).
- Su tiempo total invertido por TP (no comparado con cohorte, solo absoluto).

**Nivel 1 (estudiante ve si opta-in)** — datos con potencial metacognitivo y bajo riesgo:
- Devolución metacognitiva narrativa al cierre del episodio (R5 design doc separado). En lenguaje no técnico, sin score, sin nombrar categoría de apropiación. Ej: *"Durante este episodio le hiciste 5 preguntas al tutor. Tres de esas conversaciones ocurrieron después de ejecutar tests y antes de modificar el código —eso suele indicar que estás integrando el feedback. Las otras dos ocurrieron en los primeros tres minutos, antes de leer el enunciado completo —eso es información útil para vos."*
- Distribución de su tiempo entre N1/N2/N3/N4 (sin nombrar los niveles, con etiquetas descriptivas: "tiempo leyendo/pensando", "tiempo escribiendo código", "tiempo ejecutando", "tiempo conversando con el tutor").

**Nivel 2 (estudiante NO ve, solo docente)** — datos con alto riesgo de identidad reductiva o gaming:
- Categoría de apropiación (`reflexiva` / `superficial` / `delegacion_pasiva`).
- Cinco coherencias numéricas.
- Slope longitudinal.
- Cuartiles de cohorte.
- Alertas predictivas.
- Patrón adversarial detectado.

### 3.3 Régimen de opt-in para Nivel 1

El estudiante debe poder activar/desactivar la devolución metacognitiva de Nivel 1 desde su perfil. Default sugerido: **OFF** durante piloto-1, **ON con posibilidad de OFF** en piloto-2 (post-validación intercoder).

El opt-in del Nivel 1 va al CTR como evento `preferencia_visibilidad_actualizada` (nuevo evento sin n_level, etiquetado como `meta`, excluido del classifier vía `_EXCLUDED_FROM_FEATURES`). Esto permite trazabilidad académica de qué estudiantes operaron con qué nivel de visibilidad —insumo posterior para analizar si la visibilidad cambia el patrón de uso.

### 3.4 Excepciones críticas (siempre visibles independientemente del nivel)

- **Detección de intento adverso con severidad ≥ 3**: el estudiante debe recibir una notificación post-cierre indicando que "durante este episodio se detectaron N intentos que rozaron pedir solución directa". Sin nombrar la categoría técnica (`jailbreak_indirect`, etc.) pero sí informando que la detección existió. **Esta es la línea ética del piloto**: detectar sin avisar normaliza un mecanismo de vigilancia que el estudiante no consintió explícitamente.
- **Hash de su propio CTR**: el estudiante debería poder ver el `chain_hash` final de su episodio post-cierre, como garantía de que su corpus existe y es auditable. No le sirve para nada operacionalmente pero es un acto de transparencia mínima.

---

## 4. Lo que esto implica documentar en el paper

El paper Cortez & Garis, en su sección ética (probablemente §7 o §9, a confirmar con co-autoría), debería incorporar:

1. **Declaración explícita de la asimetría** en la sección de instrumentos: "El piloto opera con un régimen de visibilidad asimétrica entre estudiante y docente. El estudiante recolecta datos sobre su propio proceso pero no accede en tiempo real a las inferencias del clasificador sobre él. Esta decisión..."

2. **Justificación pedagógica de la asimetría**: combinación de A1-A5 de este documento, no como obvias sino como elegidas.

3. **Reconocimiento de los costos**: combinación de B1-B5. La integridad académica del paper exige reconocer lo que se sacrifica con la decisión, no solo lo que se gana.

4. **Régimen de excepciones (§3.4)**: declarar las dos excepciones críticas como compromiso mínimo de transparencia.

5. **Agenda piloto-2**: documentar el opt-in del Nivel 1 como agenda explícita pendiente, no como capacidad futurible vaga.

---

## 5. Decisiones pendientes (requieren participación humana)

1. **Aprobación de la política de tres niveles**: dirección + co-dirección + Ana Garis deben acordar antes de implementarla.
2. **Default de opt-in en piloto-1**: ¿OFF (conservador) o ON (apuesta por metacognición)? Recomendación: OFF en piloto-1, ON en piloto-2.
3. **Implementación técnica de la notificación de intento adverso**: requiere endpoint nuevo + componente UI en el modal de cierre. Estimado 8-12 h coordinado con ADR-019.
4. **Decisión sobre incluir/excluir esta política en el paper**: ¿en sección ética o en sección de instrumentos? Co-autoría decide.

---

## 6. Referencias

- informeSoc.md §4 — diagnóstico de la asimetría como observación pedagógica.
- ADR-022 — alertas predictivas con k-anon N≥5 (justifica por qué los cuartiles no son visibles ni siquiera a otros docentes con cohortes <5).
- ADR-035 — `reflexion_completada` excluida del classifier.
- Flavell, J. H. (1979). Metacognition and cognitive monitoring: A new area of cognitive-developmental inquiry. *American Psychologist*, 34(10), 906-911.
- Schraw, G. (1998). Promoting general metacognitive awareness. *Instructional Science*, 26(1), 113-125.
- Veenman, M. V. J., Van Hout-Wolters, B. H. A. M., & Afflerbach, P. (2006). Metacognition and learning: Conceptual and methodological considerations. *Metacognition and Learning*, 1(1), 3-14.
- `apps/web-teacher/src/views/` — vistas docentes hoy.
- `apps/web-student/src/pages/EpisodePage.tsx` — vista estudiante hoy.
