# Protocolo de entrevistas semi-estructuradas para el piloto UNSL 2026

**Versión**: 1.0.0 — DRAFT pendiente revisión coautoral (Ana Garis) + comité ético UNSL + pilotaje con 2-3 estudiantes.
**Fecha**: 2026-05-17.
**Origen**: cierre de P2-4 del `PlanMejora.md` (root del wrapper `AI-Native-V4-main/`). Materializa la triangulación cualitativa de MI1 y MI2 documentada en ADR-053 y la mitigación del confound intervención-medición R2 documentada en `docs/limitaciones-declaradas.md`. Cumple instrumento "Reconstrucción del proceso por el estudiante" + "juicio docente sobre trayectoria" de la Tabla 4 del paper Cortez & Garis (`paper_conaiisi.pdf`, versión 2026-05-16, §6.2).

---

## 0. Resumen

Protocolo de entrevistas semi-estructuradas con submuestra estratificada de estudiantes del grupo experimental, aplicado al final del ciclo lectivo 2026. La función del instrumento es **triangular cualitativamente** las inferencias cuantitativas del Clasificador N4 sobre las trayectorias de apropiación, validar el marco interpretativo MI1 (calidad epistémica de la trayectoria) y MI2 (apropiación reflexiva en sentido fuerte), y mitigar el confound intervención-medición (R2) mediante el contraste entre la reconstrucción basada en CTR y la auto-reconstrucción del estudiante.

La entrevista NO sirve para calificar al estudiante ni para validar el clasificador frente al juicio del entrevistado. Sirve para:

1. Verificar si los patrones que el clasificador identifica son **fenomenológicamente reconocibles** por el estudiante.
2. Detectar **divergencias sistemáticas** entre la trayectoria registrada por el CTR y la trayectoria auto-reconstruida — esas divergencias son hallazgos relevantes para discusión.
3. Recoger reportes de **sobrecarga cognitiva (R5)**, **brecha digital previa (R4)** y **performatividad (R2)** que el cuestionario inicial no captura.

---

## 1. Marco metodológico

### 1.1 Análisis temático según Braun & Clarke (2006)

Se adopta el framework de análisis temático reflexivo de Braun & Clarke (2006, "Using thematic analysis in psychology", *Qualitative Research in Psychology*, 3(2), 77-101). Las seis fases del análisis se ejecutan secuencialmente sobre las transcripciones de las entrevistas:

1. **Familiarización**: lectura íntegra y repetida de cada transcripción por dos codificadores independientes.
2. **Generación de códigos iniciales**: codificación abierta línea por línea, sin marco teórico previo impuesto.
3. **Búsqueda de temas**: agrupación de códigos en temas candidatos.
4. **Revisión de temas**: contraste de cada tema candidato contra (a) los códigos que lo sustentan, (b) la transcripción completa, (c) las trayectorias del CTR de cada estudiante entrevistado.
5. **Definición y nombrado de temas**: formulación textual concisa de cada tema con su definición operativa y un nombre identificable.
6. **Producción del reporte**: redacción del análisis con citas textuales seleccionadas que ilustren cada tema.

### 1.2 Posición epistemológica

Análisis temático **reflexivo** (no análisis temático "coder reliability" en el sentido de Boyatzis 1998). Esto significa:

- Se acepta que los temas emergen del análisis activo del investigador, no del descubrimiento neutral.
- Se reporta el **proceso de generación** de temas como parte del análisis, no como pre-análisis a separar.
- La fiabilidad inter-codificadores **NO se reporta como kappa** sobre los temas (Braun & Clarke 2019 advierten explícitamente contra esa práctica). Se reporta como **acuerdo discursivo** sobre la formulación de temas tras discusión entre codificadores.

### 1.3 Software

- **Codificación primaria**: análisis manual en archivos `.md` con tags inline `[CODIGO]` y exportación final a hoja de cálculo para tabular frecuencias.
- **Verificación cruzada con CTR**: scripts ad-hoc en `apps/analytics-service/scripts/` (a crear post-pilotaje) que extraen indicadores cuantitativos del estudiante entrevistado para contrastar contra su auto-reconstrucción.
- **Software opcional**: ATLAS.ti o NVivo si el equipo lo prefiere; manual es suficiente para n=15-20 entrevistas.

---

## 2. Muestreo estratificado

### 2.1 Tamaño y criterios

La submuestra de entrevistados se diseña sobre el **grupo experimental** del piloto. Tamaño: **15-20 estudiantes**, distribuidos estratificadamente.

### 2.2 Estratos

Tres ejes de estratificación con prioridad descendente:

1. **Perfil tipológico de apropiación dominante** (clasificación del Clasificador N4 sobre el conjunto de episodios cerrados del estudiante en el ciclo):
   - 5-7 estudiantes con perfil **apropiación reflexiva** dominante (≥60% de episodios cerrados en esa categoría).
   - 5-7 estudiantes con perfil **apropiación superficial** dominante.
   - 4-6 estudiantes con perfil **delegación pasiva** dominante.

2. **Nivel inicial de competencia** (resultado del pretest estandarizado, P2-1 del `PlanMejora.md`):
   - Dentro de cada estrato de apropiación, balancear con representantes de los tres tercios (alto, medio, bajo) del pretest.

3. **Experiencia previa con IA** (cuestionario inicial, P2-2 del `PlanMejora.md`):
   - Dentro de cada celda anterior, intentar tener al menos un estudiante de "alta experiencia previa" y uno de "baja experiencia previa".

Si la matriz no se llena por disponibilidad de estudiantes, priorizar el eje 1 (perfil de apropiación) y reportar las celdas que quedaron sin representación.

### 2.3 Reclutamiento

- Invitación voluntaria via web-student al final del ciclo lectivo.
- Compensación: certificado de participación firmado por la cátedra. **Prohibido** ofrecer compensación económica o ventajas académicas (puede sesgar autoreporte).
- Consentimiento informado escrito + verbal al inicio de la entrevista.

### 2.4 Anonimización en el análisis

- Cada estudiante se referencia por `student_pseudonym` UUID a lo largo del análisis y por **alias narrativo** (E01, E02, ...) en el reporte final. La tabla de correspondencia `pseudonym → alias` vive en `docs/research/piloto-2026/pseudonyms-aliases.md` (no commiteado al repo público).
- Citas textuales en el reporte se editan sólo para eliminar identificadores accidentales (nombres de docentes, materias específicas) — el contenido se preserva literal.

---

## 3. Guía de entrevista

**Duración estimada**: 45-60 minutos.
**Modalidad**: sincrónica, en persona o por videollamada. Grabación de audio + nota tomada por entrevistador.
**Entrevistador**: docente del PID UTN o investigador del equipo de tesis. NO el docente titular del curso del estudiante entrevistado (evita conflicto de rol).

### 3.1 Apertura (5 min)

- Bienvenida + repaso del consentimiento.
- Explicación del propósito: *"Quiero entender cómo trabajaste vos con el sistema durante el cuatrimestre. No hay respuestas correctas o incorrectas. No estamos evaluando tu desempeño en la materia, sino aprendiendo sobre cómo el sistema fue útil o no fue útil para vos."*
- Permiso para grabar.

### 3.2 Bloque 1 — Reconstrucción de un episodio prototípico (15-20 min)

El entrevistador trae preparado **un episodio cerrado seleccionado del CTR del estudiante** que sea representativo de su perfil de apropiación dominante. NO se le dice al estudiante qué categoría tiene asignada el clasificador.

Preguntas (en orden flexible):

1. *"Si pudieras volver a este trabajo práctico, ¿qué recordás de cómo lo abordaste?"*
2. *"¿Qué hiciste primero cuando abriste la consigna?"*
3. *"¿Cuándo decidiste consultar al tutor? ¿Qué le preguntaste y por qué?"*
4. *"¿Cómo decidiste si la respuesta del tutor era útil o no?"*
5. *"¿Volviste a leer la consigna en algún momento? ¿Cuándo y por qué?"*
6. *"¿Ejecutaste tu código antes o después de la última consulta al tutor? ¿Qué hiciste con el resultado?"*
7. *"¿Hubo algún momento en que te sentiste perdido o cargado? ¿Qué hiciste para destrabarte?"*

**Triangulación interna**: al finalizar el bloque, el entrevistador muestra al estudiante una visualización simple del CTR del episodio (timeline de eventos por nivel) y pregunta:

8. *"¿Esto se parece a lo que recordás haber hecho? ¿Qué te resulta raro o distinto?"*

Las divergencias entre auto-reconstrucción y CTR son **hallazgo central** del análisis cualitativo, no fallo del estudiante ni del sistema.

### 3.3 Bloque 2 — Percepción del tutor socrático (10 min)

1. *"En general, ¿cómo te fue con el tutor del sistema?"*
2. *"¿Notaste que el tutor te respondía con preguntas en lugar de darte la solución? ¿Qué pensaste de eso?"*
3. *"¿Hubo algún momento en que el tutor te frustró? ¿Y algún momento en que te ayudó especialmente?"*
4. *"¿Probaste hacer trampa o esquivar al tutor de alguna manera? ¿Cómo te fue?"* (Pregunta delicada — se hace sólo si el rapport está establecido. Útil para detectar `intento_adverso_detectado` no reportados.)
5. *"¿Cómo comparás este tutor con otros asistentes de IA que hayas usado por fuera del sistema (ChatGPT, Claude, Copilot)?"*

### 3.4 Bloque 3 — Percepción de IA generativa en general (10 min)

1. *"¿Usás IA generativa para otras cosas, dentro o fuera de la facultad?"*
2. *"¿Pensás que aprender programación con IA cambió lo que esperás aprender?"*
3. *"¿Te imaginás trabajar como programador en cinco años sin usar IA?"*
4. *"¿Notaste que cambiaba la forma en que pensabas un problema cuando sabías que ibas a poder consultar al tutor?"* (Pregunta clave para R2 performatividad cognitiva.)
5. *"¿Te incomodó saber que el sistema registraba todo lo que hacías? ¿Te acordabas de eso mientras trabajabas?"* (Pregunta clave para R1 efecto Hawthorne.)

### 3.5 Cierre (5 min)

1. *"¿Hay algo que no te haya preguntado y que quieras decir sobre tu experiencia con el sistema?"*
2. *"¿Tenés alguna sugerencia para mejorar el sistema?"*
3. Agradecimiento + entrega de certificado + repaso del uso de los datos.

---

## 4. Procedimiento de aplicación

### 4.1 Cuándo

- Al final del ciclo lectivo 2026 (noviembre-diciembre 2026), después del cierre del último TP del cuatrimestre.
- Antes de la entrega de calificaciones finales — para evitar que la conversación quede contaminada por preocupación sobre la nota.

### 4.2 Cómo

- Convocatoria escrita 7-10 días antes via web-student.
- Reserva de aula privada o sala virtual con buena conexión.
- Grabación: audio mp3 al menos en dos dispositivos (redundancia).
- Transcripción: por el entrevistador dentro de las 72 hs siguientes para preservar contexto. Software opcional: Whisper localmente para transcripción base, edición humana posterior.

### 4.3 Consentimiento informado

Documento escrito con:

- Propósito del estudio.
- Carácter voluntario + derecho a retirarse en cualquier momento sin consecuencias.
- Uso de los datos (análisis académico, posibles citas anónimas en tesis y paper).
- Almacenamiento: audio + transcripción en servidor UNSL durante 5 años; anonimización antes de publicación.
- Contacto del comité ético UNSL para reclamos.
- Firma del estudiante + del entrevistador.

---

## 5. Procesamiento y análisis temático

### 5.1 Codificación inicial (fase 2 de Braun & Clarke)

- Dos codificadores independientes leen las transcripciones y aplican códigos abiertos línea por línea.
- Cada código es una frase corta (≤5 palabras) que captura el contenido del fragmento.
- Codificadores: equipo de tesis (Cortez + Garis + idealmente un tercer codificador externo para reducir sesgo de equipo).

### 5.2 Búsqueda y revisión de temas (fases 3-4)

- Sesión de discusión presencial entre codificadores tras 5 entrevistas codificadas (no esperar al total).
- Mapeo visual de códigos en grupos temáticos candidatos (post-its físicos o pizarra digital).
- Verificación de cada tema candidato contra (a) sus códigos sustentadores, (b) la transcripción de origen, (c) los indicadores cuantitativos del CTR del estudiante respectivo.

### 5.3 Definición y nombrado (fase 5)

Para cada tema final, el reporte produce:

- **Nombre**: corto y memorable (3-6 palabras).
- **Definición operacional**: 2-4 oraciones que precisen qué cuenta como caso del tema.
- **Frecuencia**: número de estudiantes entrevistados que el tema captura.
- **Citas ilustrativas**: 2-3 citas textuales editadas (anonimización de identificadores).
- **Triangulación con CTR**: si el tema admite indicador cuantitativo en el CTR, reportar la correspondencia (cuántos estudiantes con el tema exhibieron también el indicador, cuántos no).

### 5.4 Producción del reporte (fase 6)

Reporte final en `docs/research/piloto-2026/reporte-entrevistas.md` (a crear post-aplicación), con secciones:

1. Resumen ejecutivo.
2. Métodos (referencia a este protocolo).
3. Caracterización de la submuestra (sin identificadores individuales).
4. Temas identificados (sección extensa, núcleo del reporte).
5. Discusión: contraste con MI1, MI2 (paper §4.3 + ADR-053).
6. Limitaciones del análisis cualitativo.
7. Apéndice: tabla de correspondencia tema → códigos sustentadores.

---

## 6. Triangulación con MI1 y MI2 (ADR-053)

El protocolo materializa la triangulación cualitativa que MI1 y MI2 requieren para validación indirecta:

### 6.1 Validación de MI1 (calidad epistémica de la trayectoria)

El paper §4.3 define MI1 como horizonte interpretativo cuya validación procede por triangulación con juicio docente experto sobre las trayectorias y con la auto-reconstrucción del estudiante. La entrevista aporta la auto-reconstrucción.

**Criterio de soporte indirecto a MI1**: si los estudiantes con perfil reflexivo dominante reconstruyen sus episodios con coherencia narrativa que articula propósito, decisión y verificación (independientemente del orden temporal que el CTR registra), y si los estudiantes con perfil delegativo dominante exhiben dificultad para reconstruir el porqué de cada interacción con el tutor, MI1 recibe respaldo indirecto.

**Criterio de no-soporte (o reformulación)**: si los estudiantes con perfil reflexivo dominante NO logran reconstruir narrativamente sus decisiones más allá de "le pregunté al tutor y me funcionó", la operacionalización de MI1 requiere revisita. El reporte de entrevistas debe declarar honestamente este hallazgo si aplica.

### 6.2 Validación de MI2 (apropiación reflexiva en sentido fuerte)

El paper §4.3 define MI2 como horizonte que el sistema instrumental captura mediante proxies observacionales (verificación crítica, reformulación productiva, integración con capacidad de explicación posterior) sin agotar el constructo. La entrevista aporta la "capacidad de explicación posterior".

**Criterio de soporte indirecto a MI2**: si los estudiantes con clasificación de apropiación reflexiva en el episodio mostrado exhiben capacidad de explicar a posteriori por qué eligieron interactuar con el tutor de cierta manera, y si los estudiantes con clasificación de delegación pasiva no exhiben esa capacidad, MI2 recibe respaldo indirecto.

**Criterio de no-soporte**: si la capacidad de explicación posterior NO discrimina entre perfiles del clasificador, la operacionalización de MI2 requiere revisita o ampliación de proxies observacionales.

---

## 7. Gates de calidad y reportabilidad

### 7.1 Gates de calidad de la aplicación

- **Tasa de respuesta esperada**: ≥ 50% de los estudiantes invitados (n=30-40 invitaciones para llegar a 15-20 entrevistas).
- **Distribución por perfil**: si el muestreo termina con menos del 25% del total en alguna categoría (delegación pasiva, apropiación superficial, apropiación reflexiva), reportarlo y discutir el sesgo en la sección "Limitaciones".
- **Acuerdo discursivo entre codificadores**: discusión presencial al menos cada 5 entrevistas codificadas; consenso sobre formulación de temas finales antes del reporte. Sin reporte de kappa sobre temas (ver §1.2).

### 7.2 Gates de reportabilidad

- **Citas textuales**: editadas sólo para anonimización; nunca recortadas para "favorecer" una lectura.
- **Hallazgos negativos**: deben reportarse con el mismo peso que los positivos. Si los estudiantes con perfil reflexivo NO reconstruyen sus decisiones narrativamente, eso es el hallazgo y debe formularse explícitamente.
- **Distinción**: el reporte distingue entre (a) hallazgos cualitativos que sustentan MI1/MI2 indirectamente y (b) hallazgos cuantitativos sobre H1/H2 que dependen del análisis estadístico del piloto principal. Confundir ambos comprometería la integridad metodológica.

### 7.3 Difusión

- Reporte completo: tesis doctoral + apéndice del paper.
- Citas anonimizadas: paper Cortez & Garis si el espacio del paper lo permite, en sección "Hallazgos preliminares" o equivalente.
- Dataset: el audio y la transcripción quedan en servidor UNSL durante 5 años, no se publican. Tabla de pseudonyms se destruye al cierre del estudio (post-defensa + 5 años).

---

## 8. Cronograma estimado

| Fase | Cuándo | Dependencias |
|---|---|---|
| Revisión coautoral del protocolo | Junio 2026 | Garis disponible |
| Revisión por comité ético UNSL | Julio 2026 | Documento de consentimiento informado finalizado |
| Pilotaje con 2-3 estudiantes voluntarios | Agosto 2026 | Final ciclo lectivo del cuatrimestre |
| Aplicación al grupo principal | Noviembre-diciembre 2026 | Cierre TPs del cuatrimestre |
| Transcripción | Noviembre 2026 - enero 2027 | Concurrente con aplicación |
| Codificación inicial | Enero-febrero 2027 | Transcripciones completas |
| Análisis temático completo | Marzo-abril 2027 | Codificación cerrada |
| Reporte | Abril-mayo 2027 | Análisis temático cerrado |

El cronograma se sincroniza con la agenda confirmatoria del paper §8 y con el calendario de la defensa doctoral.

---

## 9. Referencias

- Braun, V., & Clarke, V. (2006). Using thematic analysis in psychology. *Qualitative Research in Psychology*, 3(2), 77-101.
- Braun, V., & Clarke, V. (2019). Reflecting on reflexive thematic analysis. *Qualitative Research in Sport, Exercise and Health*, 11(4), 589-597. (Aclara contra el uso de coder reliability/kappa en análisis temático.)
- Paper Cortez & Garis (`paper_conaiisi.pdf`, versión 2026-05-16) — §4.3 (marcos MI1-MI3), §4.4 (perfiles tipológicos), §6.2 (Tabla 4 instrumentos cualitativos), §6.3 (confound intervención-medición), §7.3 (consideraciones de equidad).
- ADR-053 — Marcos interpretativos MI1-MI3 + protocolo interpretativo de 7 principios.
- `docs/limitaciones-declaradas.md` — Los cinco riesgos a priori del diseño cuasi-experimental (R1-R5).
- `docs/research/protocolo-autoeficacia-programacion.md` — pretest estandarizado (P2-1 del `PlanMejora.md`).
- `docs/research/diseno-test-transfer.md` — pruebas de transferencia (P2-3 del `PlanMejora.md`).
- `PlanMejora.md` (root del wrapper `AI-Native-V4-main/`) — P2-4 que este protocolo cierra.

---

## 10. Versionado del documento

| Fecha | Cambio |
|---|---|
| 2026-05-17 | Versión inicial 1.0.0 — DRAFT. Crea el protocolo desde cero como cierre de P2-4 del `PlanMejora.md`. Estructura: marco metodológico Braun & Clarke (análisis temático reflexivo), muestreo estratificado por perfil tipológico × pretest × experiencia previa IA, guía de entrevista de 3 bloques (reconstrucción episodio + percepción tutor + percepción IA), procesamiento y análisis temático en 6 fases, triangulación explícita con MI1 y MI2 del ADR-053, gates de calidad sin kappa sobre temas (siguiendo Braun & Clarke 2019). Pendiente: revisión coautoral con Garis + comité ético UNSL + pilotaje con 2-3 estudiantes voluntarios. |
