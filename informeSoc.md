# Informe pedagógico sobre la implementación del tutor socrático y la trazabilidad cognitiva N4

**Autor del informe**: análisis externo en rol de especialista en didáctica universitaria y método socrático aplicado.
**Objeto de análisis**: plataforma AI-Native N4 (monorepo `AI-NativeV3-main/`), prompt activo `v1.1.0`, etiquetador `LABELER_VERSION = 1.2.0`, classifier con cinco coherencias separadas.
**Fecha**: 2026-05-16.
**Destinatario implícito**: Alberto A. Cortez (autor de la tesis), co-dirección, y eventual comité doctoral UTN.

---

## 0. Resumen ejecutivo

La plataforma exhibe **dos virtudes pedagógicas estructurales** poco frecuentes en sistemas de tutoría con LLM: (a) la **negativa explícita a colapsar la evaluación cognitiva en un score único** —las cinco coherencias (CT, CCD_mean, CCD_orphan_ratio, CII_stability, CII_evolution) viven separadas hasta el final del pipeline y no se promedian— y (b) la **trazabilidad criptográfica append-only** que vuelve el corpus auditable y reproducible bit-a-bit. Ambas decisiones tienen lectura pedagógica: rechazan la métrica única como artefacto cognitivo, y vuelven la práctica del estudiante un texto reanalizable.

Dicho eso, identifico **cinco brechas pedagógicas sustantivas** que el informe desarrolla:

1. **El prompt v1.1.0 implementa "tutor que no da la respuesta", no método socrático en sentido estricto.** Carece de la mayéutica como secuencia, del *elenchos* (refutación interna) y de la *aporía* productiva.
2. **La taxonomía N4 mide actos observables, no movimientos de pensamiento.** "Prompt enviado" puede ser N4 en cuanto canal (interacción con el tutor) sin ser pensamiento de nivel superior.
3. **El estudiante es objeto del análisis, no sujeto.** No ve su propio diagnóstico N4, no recibe devolución metacognitiva personalizada, y la reflexión post-cierre actual es un trámite breve sin estructura socrática.
4. **El árbol de decisión a tres categorías de apropiación es una caja negra para el estudiante** y, en su forma actual, una operacionalización por umbral más que un instrumento pedagógico. (Nota 2026-05-16: la primera versión de este informe afirmaba que el paper tenía cinco categorías y la implementación tres; **verificación posterior mostró que ambos coinciden en tres** —el listado de cinco aparece sólo en el README del wrapper, sin respaldo. Ver §3.4 actualizada y la corrección del README ejecutada en esta sesión.)
5. **El cuello de botella real no es técnico sino formativo**: la validación intercoder κ ≥ 0,70 sobre el protocolo dual del ADR-046 (200 eventos + 50 episodios, ~25-30 h por docente) requiere **una calibración previa entre etiquetadores** que el repositorio no documenta como protocolo explícito.

Las recomendaciones P0 son tres y se desarrollan en §8: introducir una **fase de elenchos** en el prompt v1.2.0, mostrar al estudiante una **devolución metacognitiva narrativa** al cierre (sin colapsar score, sin nombrar categoría de apropiación), y **redactar el manual del etiquetador** antes de invitar a los dos docentes UTN al estudio intercoder.

---

## 1. Marco de referencia: qué entendemos por "socrático"

El término "tutor socrático" se ha vuelto, en la literatura de tecnologías educativas, equivalente a "no entrega la solución" o "responde con preguntas". Esa lectura es operacionalmente útil pero filosóficamente débil. La tradición distingue al menos cuatro elementos del método de Sócrates en los diálogos de Platón:

- **Ironía**: el tutor adopta el lugar del que no sabe para que el estudiante explicite lo que cree saber. Es asimétrica: el tutor sabe pero suspende su saber instrumentalmente.
- **Mayéutica**: la conducción del estudiante hacia la articulación de un saber latente mediante una secuencia *ordenada* de preguntas que cada una problematiza la anterior.
- **Elenchos**: la refutación dialéctica. El tutor pone al estudiante en contradicción consigo mismo —no con la "respuesta correcta"— para que esa contradicción genere el movimiento intelectual.
- **Aporía**: el desconcierto productivo. Reconocer "no sé" no como fracaso sino como punto de partida.

Vlastos (1983), Boghossian y Lipman han mostrado que sólo el segundo —la mayéutica— sobrevive con vitalidad en la pedagogía contemporánea, y casi siempre **descontextualizado de los otros tres**. Una tutoría que hace preguntas pero no refuta internamente, ni cultiva aporía, es socrática en un sentido sociológico (parece a Sócrates) pero no en sentido fuerte (hace lo que Sócrates hacía).

Este marco es la lente con la que leo lo que la plataforma implementa.

---

## 2. Análisis del tutor en runtime (lo que el estudiante experimenta)

### 2.1 El prompt v1.1.0: lo que dice bien

El prompt activo (`ai-native-prompts/prompts/tutor/v1.1.0/system.md`) tiene aciertos pedagógicos importantes:

- **Prohibición clara de la solución directa.** Es una valla bien puesta y bien defendida (los guardrails de la categoría `direct_answer` la refuerzan).
- **Inversión del flujo conversacional.** "Validar conocimientos previos. Si el estudiante usa un concepto, preguntale qué es y cómo funciona antes de seguir." Esa instrucción está alineada con el principio constructivista de no avanzar sobre arena (Ausubel, Vygotsky).
- **No corregir el error inmediatamente.** "Si propone algo con un bug, NO lo corrigís de inmediato — guialo a que descubra el bug por sí mismo." Esto preserva el espacio del error productivo, esencial en didáctica de la programación (Ben-Ari, Sorva).
- **Uso del RAG sin citar.** La instrucción "no lo cites textualmente ni menciones que estás usando un apunte" evita el efecto "el sistema lee del manual" y mantiene la voz del tutor como propia. Es una decisión de diseño pedagógico fino.
- **La rúbrica como mapa privado del tutor.** "NUNCA reveles los criterios por nombre... tratá la rúbrica como tu mapa privado de navegación." Esto es excelente: previene que el estudiante optimice contra la rúbrica en lugar de aprender, sin perder el norte didáctico que la rúbrica representa.

### 2.2 El prompt v1.1.0: lo que no dice y debería

Tres ausencias estructurales:

**(a) No hay mayéutica como secuencia.** El prompt instruye al tutor a "hacer preguntas antes que dar respuestas" (Principio 2), pero no le da un *esquema de conducción*. Una mayéutica genuina tiene una arquitectura: explicitar la creencia inicial → exhibir un caso límite → mostrar contradicción → reformular. El prompt deja esa estructura implícita en la "intuición pedagógica" del LLM, que es justamente lo que un LLM no tiene. Resultado predecible: el tutor hace preguntas, pero son preguntas en serie, no preguntas que escalonen.

**(b) No hay elenchos.** En ningún lugar del prompt aparece la instrucción de **poner al estudiante en contradicción consigo mismo**. La diferencia con "guiar al descubrimiento del bug" es importante: el bug es contradicción con el compilador, no con el propio pensamiento del estudiante. Un tutor socrático en sentido fuerte diría: "Hace cinco minutos me dijiste que los strings en Python son inmutables. Ahora me estás diciendo que tu función modifica el string. ¿Cómo se concilia?". Eso es elenchos. La plataforma no lo pide ni lo evalúa.

**(c) No hay tratamiento de la aporía.** El prompt asume que toda conversación avanza. No prevé qué hacer cuando el estudiante queda genuinamente desconcertado —ni en términos de validar ese desconcierto como pedagógicamente fértil, ni de ofrecer técnicas para habitarlo. La consecuencia operativa es que el tutor, frente a un "no entiendo", tiende a simplificar (es lo que un LLM hace por default), no a sostener la productividad del no-saber.

**Riesgo de fondo:** un tutor que **prohibe la respuesta** sin **enseñar a pensar** termina siendo un obstáculo amable. El estudiante percibe que no puede obtener la respuesta y desarrolla estrategias para extraerla por vías indirectas (los guardrails de "overuse" detectan precisamente esto, lo cual confirma el problema en lugar de resolverlo).

### 2.3 Los guardrails: lo que protegen y lo que no detectan

`apps/tutor-service/src/tutor_service/services/guardrails.py` v1.2.0 cubre cinco categorías de intentos adversos y agrega `overuse` para detectar consumo desmedido del tutor. **Es un sistema serio de defensa contra fraude del rol.**

Limitación pedagógica: detectan **patrones léxicos** de mal uso, pero no detectan **dependencia cognitiva benigna**. Un estudiante puede mantenerse dentro de las 6 preguntas por ventana y aun así estar **delegando el pensamiento** sin saberlo —preguntando paso a paso sin nunca formular hipótesis propias. El guardrail `overuse` lo captura solo si supera la ventana temporal; un estudiante "moderado en su delegación" pasa inadvertido. La categoría `delegacion_pasiva` del classifier debería estar conectada a estos guardrails, pero hoy son sistemas paralelos.

### 2.4 El "Aviso pedagógico" silencioso

Cuando se detecta un intento adverso con severidad ≥ 3, el sistema inyecta un `_REINFORCEMENT_SYSTEM_MESSAGE` ANTES del prompt del estudiante. El refuerzo opera en el espacio del modelo (que ahora "sabe" que hubo un intento) pero **no en el espacio del estudiante** (que no recibe ninguna devolución sobre que su intento fue clasificado como adverso).

Esto es una decisión defendible (no exponer la detección puede aumentar su efectividad) pero pedagógicamente discutible: una de las tareas formativas de la universidad es **enseñar al estudiante a reconocer cuándo está intentando atajar el aprendizaje**. Esconderle la detección le quita una oportunidad metacognitiva.

**Sugerencia operativa**: bajo el flag `metacognitive_feedback_enabled` (nuevo), agregar al cierre del episodio una línea del tipo "durante este episodio el tutor detectó tres pedidos que rozaron pedir solución directa; eso es información útil para vos, no una sanción". Sin nombrar la categoría técnica.

---

## 3. Análisis de la trazabilidad cognitiva N4

### 3.1 El acierto estructural: ortogonalidad declarada

El paper (Sección 4) declara explícitamente que **N1-N4 no son una jerarquía**. Esa afirmación —sostenida contra Bloom/SOLO/Anderson— es valiente y, en mi lectura, correcta. La cognición situada en programación universitaria no es escalonada (primero lectura, después código, después interacción): es paralela. Un estudiante puede estar leyendo el enunciado, escribiendo código y consultando al tutor en una ventana de 90 segundos, atravesando N1, N3 y N4 sin "subir" en ningún sentido cognitivo.

La implementación honra esta declaración: `event_labeler.py` mapea evento → nivel sin imponer secuencia, y el classifier deriva el `n_level` en lectura (ADR-020) sin almacenarlo en el payload. Esto preserva la posibilidad de re-etiquetar históricamente al refinar el modelo.

### 3.2 El problema operacional: actos vs movimientos

La taxonomía N4 mide **actos observables**:

| Nivel | Acto representativo |
|---|---|
| N1 | Lectura de enunciado, anotación inicial |
| N2 | Anotación (no inicial, no derivada del tutor) |
| N3 | Edición de código, ejecución, tests |
| N4 | Interacción con tutor, edición pegada del tutor |

El problema pedagógico es que **el acto no es el movimiento de pensamiento**. Un `prompt_enviado` puede ser:

- Una pregunta socráticamente fértil del estudiante ("¿por qué pensás que mi función falla en este caso?")
- Una solicitud de validación ("¿está bien así?")
- Un pedido encubierto de solución ("¿podés mostrarme un ejemplo de este patrón?")
- Una delegación pasiva ("no entiendo nada, ayudame")

Las cuatro son N4 en el etiquetador actual. **Cognitivamente no son comparables.**

El override léxico (`event_labeler_lexical.py`) y el `socratic_compliance` (Fase B en ADR-027/044) son intentos de capturar esta diferencia, **ambos OFF por flag**. La validación intercoder está pendiente. **Esta es la brecha pedagógica más grande del sistema**, y el repositorio la reconoce honestamente (es deuda declarada, no oculta).

### 3.3 Las cinco coherencias: lo que miden bien y lo que no miden

| Coherencia | Lo que mide | Lo que no mide |
|---|---|---|
| **CT** (densidad temporal + transiciones) | Sostén atencional, ritmo de trabajo | Si el ritmo corresponde a pensamiento o a copy-paste exploratorio |
| **CCD_mean** (proximidad prompt↔código) | Acoplamiento discurso/acción | Si el discurso *informa* al código o lo *justifica a posteriori* |
| **CCD_orphan_ratio** (ediciones huérfanas) | Acción sin reflexión verbalizada | Si el huérfano es ejecución de plan o tanteo ciego |
| **CII_stability** (Jaccard léxico intra-episodio) | Persistencia conceptual del estudiante | Si la persistencia es comprensión o fijación |
| **CII_evolution** (pendiente de complejidad léxica) | Sofisticación creciente del discurso | Si la sofisticación léxica es saber o imitación del registro |

Las cinco son **proxies operacionalizables**. Eso es virtud (son medibles, reproducibles, auditables). Es también límite: cada una mide *la sombra* de un fenómeno cognitivo, no el fenómeno. El paper hace bien en no afirmar más.

**Observación crítica**: el corpus actual de cinco coherencias está sesgado hacia lo **verbal** (Jaccard, pendiente léxica, alineamiento texto-código). Falta una dimensión que la didáctica de la programación lleva 40 años estudiando: la **estructura del código mismo como objeto cognitivo**. Pausch, Soloway, Spohrer mostraron que la calidad del *plan* implícito en el código es un predictor más fuerte de comprensión que ninguna métrica verbal. La plataforma podría agregar una sexta coherencia —"coherencia estructural del código" (ej. depth of nesting variability, function granularity, naming consistency)— sin colapsarla en las otras cinco.

### 3.4 El árbol de decisión: operacionalización conservadora pero opaca

El árbol que mapea las cinco coherencias en tres categorías (`apropiacion_reflexiva`, `apropiacion_superficial`, `delegacion_pasiva`) es honestamente reconocido en el ADR-018 como "operacionalización conservadora, NO verdad académica". Eso es académicamente íntegro.

**Corrección al borrador original de este informe (2026-05-16, post-verificación)**: la primera versión de esta sección afirmaba que "el paper identifica cinco categorías de apropiación (`autonomo`, `superficial`, `delegacion_pasiva`, `delegacion_extrema`, `regresivo`) pero la implementación colapsa a tres". Esa afirmación es **incorrecta**. El paper-draft.md §4.4 (Tabla 2) define explícitamente "tres tipos de apropiación", coincidentes con las tres ramas implementadas en `tree.py`. El listado de cinco aparece únicamente en `README.md` del wrapper (líneas 263-267) sin respaldo en el paper ni en el código; el "Autonomo" que aparece en `ProgressionView.tsx:415` es un label de display para `apropiacion_reflexiva` (CSS var `--color-appropriation-reflexiva`). El README fue corregido en esta sesión para alinearlo con paper y código. La recomendación P0 "R2 reconciliación 3→5" del borrador anterior queda **anulada**: no hay reconciliación pendiente entre paper y código.

Mi observación pedagógica válida sí persiste: el árbol actual tiene **tres ramas y cinco coherencias**, lo que significa que **dos coherencias (CCD_orphan_ratio y CII_evolution) entran al árbol pero no individualizan ramas propias** —operan como condiciones de cruce dentro de las tres ramas existentes. Esto es defendible (la apropiación es un constructo de tercer orden, no de quinto) pero podría refinarse a futuro distinguiendo, por ejemplo, sub-ramas más finas dentro de `apropiacion_superficial` según qué coherencia falla. Esa refinación sería trabajo de piloto-2, post-validación intercoder del modelo de tres categorías.

---

## 4. La asimetría visibilidad docente ↔ estudiante

`apps/web-student/src/pages/EpisodePage.tsx` muestra al estudiante: el editor, el chat con el tutor, el panel del TP, y al cierre, el modal de reflexión. **El estudiante no ve**:

- Su etiqueta N1-N4 por evento.
- Su categoría de apropiación.
- Sus cinco coherencias.
- Su slope longitudinal vs el de su comisión.
- Sus alertas predictivas (si las hay sobre él).

Todo esto vive en `web-teacher`. La asimetría es deliberada: el estudiante es el **objeto** del análisis, el docente es el **sujeto** que interpreta.

Esta decisión tiene defensores legítimos (evitar el efecto Heisenberg, evitar gaming del clasificador, proteger al estudiante de etiquetas que podría leer como sentencias). Pero también tiene **costos pedagógicos** que no aparecen tematizados en los ADRs:

1. **Pérdida de la dimensión metacognitiva.** La investigación contemporánea (Flavell, Schraw, Veenman) muestra que la metacognición se entrena haciendo visible al estudiante el patrón de su propio pensamiento. Esconder los datos al productor de esos datos es renunciar a la mitad del potencial formativo.

2. **El docente como único intérprete.** En una comisión de 30 estudiantes, el docente UTN no va a leer 30 progresiones longitudinales con cinco coherencias cada una. Sí va a leer las alertas que el sistema le destaque. El estudiante "que no dispara alertas" queda invisibilizado por su propia regularidad —incluso si esa regularidad es estancamiento.

3. **Asimetría como pedagogía implícita.** "Vos producís datos, otros los interpretan" es una pedagogía. No es neutral. En un piloto de tesis doctoral conviene tematizarla en la sección ética del paper, no naturalizarla.

**Recomendación**: implementar una **devolución metacognitiva narrativa al cierre del episodio**, dirigida al estudiante, en lenguaje *no técnico* y *sin nombrar categoría de apropiación*. Algo como: "En este episodio hablaste con el tutor cinco veces. Tres de esas conversaciones ocurrieron después de ejecutar tests y antes de modificar el código —eso suele indicar que estás integrando el feedback. Las otras dos ocurrieron en los primeros tres minutos, antes de leer el enunciado completo —eso es información útil para vos." Sin score. Sin etiqueta. Narrativo, situado, devolutivo.

---

## 5. La reflexión post-cierre: oportunidad bien identificada, ejecución mejorable

`ReflectionModal.tsx` ofrece al estudiante, al cerrar el episodio, un textarea con la pregunta "¿Qué aprendiste de este episodio? ¿Qué te costó?" y permite "saltar reflexión". El evento `reflexion_completada` se emite al CTR pero está excluido del classifier (ADR-035), preservando reproducibilidad.

Tres observaciones:

**(a) La pregunta es genérica y los estudiantes responden genéricamente.** "Aprendí a usar listas. Me costó el bucle." Eso no es reflexión metacognitiva, es resumen ejecutivo. Una reflexión genuina requiere preguntas como: "¿En qué momento del episodio sentiste que algo hizo click? ¿Qué pregunta del tutor te resultó más útil y por qué? ¿Si tuvieras que explicarle a un compañero qué fue lo más importante de este ejercicio, qué le dirías?".

**(b) "Saltar reflexión" es una opción que casi todos los estudiantes van a tomar.** El diseño actual hace de la reflexión un gravamen opcional. Reformular: la reflexión no debería ser saltable, pero **debería ser brevísima y bien diseñada** —dos preguntas, treinta segundos, sin botón de skip pero con "no quiero reflexionar ahora" que emita un evento `reflexion_omitida` (también excluido del classifier).

**(c) Corrección 2026-05-16**: el borrador anterior de este informe afirmaba que "el tutor responde la reflexión". Verificación posterior del código (`ReflectionModal.tsx` y backend `tutor-service`) mostró que **el tutor NO responde la reflexión** —solo se persisten tres strings (`que_aprendiste`, `dificultad_encontrada`, `que_haria_distinto`) en el CTR como evento `reflexion_completada`. Esa afirmación queda anulada.

La sugerencia válida que sí persiste: **ofrecer al estudiante, al ingresar al siguiente episodio, una vista "tu reflexión anterior decía X; sigue siendo válido?"**. Reflexión sostenida en el tiempo > reflexión conversada en el momento. Esto requeriría un endpoint nuevo `GET /api/v1/episodes/{id}/previous-reflection` que devuelva la última reflexión completada del estudiante (excluyendo PII si el episodio no es del mismo TP), y un componente nuevo en `EpisodePage.tsx`. Trabajo de R5 (devolución metacognitiva) en versión extendida.

---

## 6. El cuello de botella real: el κ y el manual del etiquetador

ADR-046 formaliza el protocolo dual: 200 eventos (Protocolo A) + 50 episodios (Protocolo B), dos etiquetadores, κ ≥ 0,70. Estimación: 25-30 h por etiquetador.

**Lo que falta y no veo documentado en los ADRs**: el **manual del etiquetador**. Sin un manual operativo con:

- Definición operacional de cada nivel N1-N4 en términos de criterios *observables al lector humano de eventos*, no al sistema.
- Casos límite resueltos con justificación (ej. "anotación creada a los 119 segundos del episodio: ¿N1 o N2?").
- Protocolo de pre-calibración (los dos etiquetadores etiquetan los mismos 20 eventos, comparan, discuten discrepancias, *después* recién empiezan los 200).
- Protocolo de reconciliación (cuando discrepan en los 200: ¿se promedia? ¿se vota? ¿se discute?).

...el κ va a salir bajo no porque los etiquetadores estén en desacuerdo conceptual, sino porque van a interpretar los criterios operacionales de manera diferente. **Es estadísticamente esperable**.

**Recomendación P0 absoluta**: antes de invitar a los dos docentes al estudio intercoder, redactar `docs/research/manual-etiquetador-N4.md` con los puntos anteriores, y pilotearlo con el director de tesis o el co-director sobre 20 eventos. Si la calibración interna ya da κ < 0,70 con quien conoce el modelo, **ese es el problema a resolver primero**, no la inversión de 50 h docentes.

---

## 7. Observaciones de menor calado pero relevantes

### 7.1 El prompt y la voz del tutor

"En español rioplatense neutro, sin modismos fuertes. Sin emojis." Es buena instrucción. Pero el prompt no especifica **persona narrativa** (¿vos o tú? ¿el tutor se nombra a sí mismo? ¿tiene historia, edad, especialidad?). Un tutor *encarnado* facilita el contrato pedagógico. Un tutor abstracto invita al gaming.

Sugerencia: dar al tutor un personaje mínimo. "Soy un ayudante de cátedra que te acompaña en este TP. No tengo nombre, no sé tu historia, pero me importa que pienses por vos mismo." Una línea, suficiente para anclar la relación.

### 7.2 El RAG y la fidelidad pedagógica

El prompt instruye a usar el material de cátedra "sin citarlo textualmente". Académicamente esto es ambivalente: por un lado evita el efecto "lee del apunte"; por otro, en universidad, **citar al docente y al apunte ES pedagogía** (transmite la cadena del saber, marca autoridad situada). Un tutor que oculta sus fuentes le enseña al estudiante a no citarlas. Vale revisar la decisión.

### 7.3 La complejidad léxica como proxy

`cii_evolution` mide pendiente de complejidad léxica de prompts. Pedagógicamente delicado: un estudiante puede sofisticar su léxico porque está aprendiendo el registro técnico (lo cual es deseable) o porque está copiando el registro del tutor (lo cual es N4 trivial). La métrica no distingue. Worth considerar agregar un control: ¿el léxico nuevo del estudiante apareció antes en el corpus de respuestas del tutor en este episodio?

### 7.4 Las alertas predictivas y la ética

Las tres alertas (`regresion_vs_cohorte`, `bottom_quartile`, `slope_negativo_significativo`) son honestamente declaradas "pedagógicas, no clínicas" en ADR-022. Mi observación: una alerta que el docente lee como sentencia opera *de facto* como diagnóstico, aunque el ADR la enmarque pedagógicamente. **El piloto debería medir cómo los docentes interpretan las alertas en la práctica** —encuesta breve después del primer cuatrimestre— y reportarlo en el paper. Si los docentes están usando "bottom_quartile" como "este estudiante va a desaprobar", la alerta funciona como predicción aunque haya sido diseñada como guía.

---

## 8. Recomendaciones priorizadas

### P0 — Antes del intercoder

| # | Recomendación | Esfuerzo estimado |
|---|---|---|
| **R1** | Redactar `docs/research/manual-etiquetador-N4.md` con criterios operacionales, casos límite resueltos y protocolo de pre-calibración. | 8-12 h |
| **R2** | ~~Reconciliar 3→5 categorías~~ ANULADA tras verificación: paper y código coinciden en 3. Reemplazada por R2-corregido: alinear README del wrapper (corregido en sesión 2026-05-16). | 30 min (ejecutado) |
| **R3** | Pilotar el manual del R1 con director/co-director sobre 20 eventos. Si κ_interno < 0,70, refinar antes de invitar a los dos docentes. | 4-6 h |

### P1 — Antes de publicar v1.2.0 del prompt

| # | Recomendación | Esfuerzo estimado |
|---|---|---|
| **R4** | Reescribir el prompt v1.2.0 incorporando estructura mayéutica (escalonamiento de preguntas), instrucción explícita de elenchos (poner al estudiante en contradicción consigo mismo, no con el compilador), y manejo de aporía. | 6-10 h |
| **R5** | Implementar devolución metacognitiva narrativa al cierre del episodio (sin score, sin categoría, sin etiqueta N), bajo flag `metacognitive_feedback_enabled`. | 16-24 h (UI + backend) |
| **R6** | Rediseñar la reflexión post-cierre: dos preguntas situadas, no saltable pero con `reflexion_omitida` válida, sin respuesta del tutor. | 6-10 h |

### P2 — Agenda piloto-2

| # | Recomendación | Esfuerzo estimado |
|---|---|---|
| **R7** | Agregar sexta coherencia: estructural del código (depth of nesting variability, function granularity, naming consistency). Sin colapsar con las otras cinco. | 20-30 h |
| **R8** | Conectar guardrails (overuse, direct_answer) con el classifier para que `delegacion_pasiva` no sea un cómputo paralelo sino integrado. | 8-12 h |
| **R9** | Medir interpretación docente de las alertas predictivas: encuesta semi-estructurada al final del primer cuatrimestre piloto. Reportar en el paper. | 4-8 h (instrumento) + análisis |
| **R10** | Decidir y documentar la política de visibilidad de datos al estudiante (qué ve, qué no, por qué). Tematizar en sección ética del paper. | 6-10 h |

### Estado de implementación al cierre de la sesión 2026-05-16

Resumen de qué quedó implementado, qué quedó como design/ADR pendiente de activación, y qué requiere participación humana. Esta sección complementa las tres tablas anteriores y debe leerse como **seguimiento operacional**, no como reformulación del plan.

| # | Estado | Entregable concreto |
|---|---|---|
| **R1** | ✅ Implementado | `AI-NativeV3-main/docs/research/manual-etiquetador-N4.md` con criterios operacionales, casos límite y protocolo de pre-calibración. |
| **R2** | ✅ Ejecutado (anulado) | Verificación reveló que paper §4.4 y `tree.py` coinciden en 3 categorías. README del wrapper líneas 263-267 alineadas. Auto-corrección documental, no ADR. |
| **R3** | 🔲 Requiere humanos | Pre-calibración con dir + co-dir sobre 20 eventos + 5 episodios. El manual de R1 está listo para ejecutar. |
| **R4** | 🟡 DRAFT | `ai-native-prompts/prompts/tutor/v1.2.0/system.md` con 4 movimientos socráticos explícitos (ironía/mayéutica/elenchos/aporía) y cobertura 9/10 guardarrailes. **NO activado en `manifest.yaml`** — bloqueado por revisión coautoral + decisión dir/co-dir. |
| **R5** | 🟡 Esqueleto OFF | Módulo `packages/platform-ops/src/platform_ops/metacognitive_feedback.py` (~280 LOC) + 11 tests + plantillas marcadas DRAFT + ADR-050. Endpoint/UI/schema de preferencia y revisión coautoral de plantillas pendientes (R5 fase 2). |
| **R6** | ✅ Implementado | `apps/web-student/src/components/ReflectionModal.tsx` reescrito: 3 preguntas situadas, copy intro reescrito, botón "Saltar" → "No quiero reflexionar ahora". Keys del payload preservadas → tests del backend siguen verdes. |
| **R7** | 🟡 Esqueleto desconectado | Módulo `cec_features.py` (~270 LOC) + 14 tests + ADR-051. **NO conectado a `pipeline.py` ni `tree.py`** — bloqueo arquitectónico por A1 + validación empírica de no-redundancia. |
| **R8** | 🟡 Esqueleto desconectado + flag OFF | Módulo `guardrail_signals.py` (~190 LOC) + 14 tests + flag `guardrail_modifier_enabled=False` en `classifier-service/config.py` + ADR-052. **NO conectado al pipeline** — bloqueo por A1 + Protocolo B intercoder + calibración empírica. |
| **R9** | ✅ Instrumento entregado | `AI-NativeV3-main/docs/research/encuesta-interpretacion-docente-alertas.md` con 4 secciones, 3 viñetas, métrica primaria `framing_pedagogico`. Aplicación + análisis pendientes (requiere docentes piloto). |
| **R10** | ✅ Política documentada | `AI-NativeV3-main/docs/research/politica-visibilidad-estudiante.md` con 3 niveles + excepciones críticas + agenda piloto-2. Decisión política sobre default (OFF/ON con opt-in) pendiente de dir/co-dir. |

**Leyenda**: ✅ ejecutado, 🟡 esqueleto/draft listo para activación, 🔲 requiere participación humana o gates externos.

**Lo que la sesión NO modificó** (preservación de invariantes):
- El `classifier_config_hash` no cambia.
- `LABELER_VERSION` sigue en `1.2.0`.
- El contrato del CTR no se altera.
- Las 106 classifications históricas conservan su hash legacy hasta A1.
- El prompt activo del manifest sigue siendo v1.1.0.
- Ningún flag de producción se prendió.

**ADRs nuevos derivados de esta sesión** (siguen el patrón de ADR-044/045):
- **ADR-050** — esqueleto metacognitive_feedback + flag user-level OFF.
- **ADR-051** — esqueleto CEC desconectado del pipeline, bloqueado por A1.
- **ADR-052** — esqueleto guardrail modifier desconectado + flag classifier OFF.

**Próximos sub-agents recomendables (cuando los gates humanos se levanten)**:
1. Implementar endpoint + UI de R5 fase 2 (post-revisión coautoral de plantillas).
2. Script ad-hoc para R7 Gate B (validar no-redundancia de CEC sobre 106 históricas post-A1).
3. Script ad-hoc para R8 Gate C (calibrar umbral severity_3_plus_count sobre 106 históricas post-A1).
4. Activación del prompt v1.2.0: bumpear `default_prompt_version` en `tutor-service/config.py` coordinadamente con el manifest (G12).

---

## 9. Conclusiones

La plataforma AI-Native N4 tiene una **base arquitectónica pedagógicamente sólida**: trazabilidad criptográfica auditable, separación de cinco coherencias sin colapso, taxonomía explícitamente ortogonal, prompt versionado, manejo serio de intentos adversos. Estos son aciertos de fondo, no decorativos.

Las brechas que identifico son **brechas de profundización**, no de concepción: el tutor es socrático en sentido débil (no entrega solución) pero no en sentido fuerte (no practica mayéutica estructurada ni elenchos); la trazabilidad mide actos pero aún no movimientos de pensamiento; el estudiante es objeto de análisis pero no sujeto de su propia metacognición; el cuello de botella académico (κ ≥ 0,70) requiere una calibración previa que no está protocolizada.

Las recomendaciones R1, R2 y R3 son urgentes en el sentido de que **condicionan la validez de la inversión de 50 h docentes** del estudio intercoder. R4-R6 elevan el techo pedagógico del piloto sin tocar invariantes criptográficas ni reproducibilidad. R7-R10 son agenda de piloto-2 y de paper.

En términos doctorales: la tesis está defendiblemente sólida en su arquitectura y en su honestidad académica (los ADRs reconocen sus propias deudas, lo cual es académicamente íntegro). El refinamiento pedagógico que sugiero no invalida el aporte; lo profundiza. Sócrates no daba respuestas, pero sabía a dónde llevaba al interlocutor. Hoy el tutor sabe que no debe dar la respuesta. Falta enseñarle a dónde está llevando al estudiante —y, sobre todo, al estudiante, *que está siendo llevado*.

---

**Documentos consultados** (en orden de relevancia para este informe):

- `AI-NativeV3-main/ai-native-prompts/prompts/tutor/v1.1.0/system.md`
- `AI-NativeV3-main/ai-native-prompts/manifest.yaml`
- `AI-NativeV3-main/apps/tutor-service/src/tutor_service/services/postprocess_socratic.py`
- `AI-NativeV3-main/apps/tutor-service/src/tutor_service/services/guardrails.py`
- `AI-NativeV3-main/apps/tutor-service/src/tutor_service/services/tutor_core.py`
- `AI-NativeV3-main/apps/classifier-service/src/classifier_service/services/event_labeler.py`
- `AI-NativeV3-main/apps/classifier-service/src/classifier_service/services/event_labeler_lexical.py`
- `AI-NativeV3-main/apps/classifier-service/src/classifier_service/services/pipeline.py`
- `AI-NativeV3-main/packages/platform-ops/src/platform_ops/cii_longitudinal.py`
- `AI-NativeV3-main/packages/platform-ops/src/platform_ops/cii_alerts.py`
- `AI-NativeV3-main/apps/web-student/src/pages/EpisodePage.tsx`
- `AI-NativeV3-main/apps/web-student/src/components/ReflectionModal.tsx`
- ADR-010, ADR-018, ADR-020, ADR-022, ADR-027, ADR-035, ADR-044, ADR-046
- `paper-draft.md`, `ppconarev.md`

**Marco teórico de referencia**: Vlastos (1983), Lipman (1988), Boghossian (2013), Paul-Elder (2006), Flavell (1979), Schraw (1998), Veenman (2006), Ben-Ari (1998), Soloway & Spohrer (1989), Ausubel (1968), Landis & Koch (1977).
