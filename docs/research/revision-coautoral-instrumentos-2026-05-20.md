# Material para sesión coautoral — validación de contenido de los 3 instrumentos del diseño cuasi-experimental

**Fecha de preparación**: 2026-05-20
**Para**: Alberto A. Cortez (autor principal) y Ana Garis (co-autora)
**Origen**: cierre del sprint `plan-mejora-instrumentos-research` (2026-05-17) que materializó el esqueleto técnico end-to-end de los 3 instrumentos del paper §6.2 Tabla 4. El **contenido académico** quedó marcado explícitamente con literales `[PLACEHOLDER GARIS]` y `[PLACEHOLDER CATEDRA UTN]` a la espera de esta revisión coautoral.
**Objetivo de la sesión**: aprobar, modificar o reemplazar **23 items distribuidos en 3 instrumentos** (8 cuestionario IA previa + 12 pretest autoeficacia + 3 problemas test transferencia) antes de la aplicación piloto. Cada item lleva su marker explícito en el código (`instrumentos_content.py`) que el test `test_catalogo_tiene_marcadores_placeholder` verifica que NO se haya quitado sin aprobación coautoral.

> **NOTA OPERATIVA**: cuando Garis o la cátedra apruebe un item específico, sacar el marker `[PLACEHOLDER GARIS]` / `[PLACEHOLDER CATEDRA UTN]` manualmente del literal — esa es la señal explícita de "contenido validado". El test golden falla para ese item, lo que marca el paso a producción. NO bumpear `instrument_version` antes de sacar los markers; NO sacar los markers sin aprobación coautoral.

---

## 0. Antes de la sesión

### 0.1 Cómo se preparó este material

El sprint 2026-05-17 construyó el **esqueleto técnico end-to-end** de los 3 instrumentos: migration con 3 tablas (`respuestas_cuestionario_ia`, `respuestas_pretest_autoeficacia`, `respuestas_test_transferencia`) con RLS forzado, schemas Pydantic, routes con k-anonymity gate `MIN_STUDENTS_FOR_COHORT_SUMMARY=5`, UI en web-student (`InstrumentosPage.tsx`) y web-teacher (`InstrumentosCohorteView.tsx`), seed demo con 90 inserts placeholder, 21 Casbin policies nuevas (total 205). El plumbing técnico está cerrado y testeado (`test_instrumentos.py`).

Lo que falta es el **contenido académico** que cada instrumento mide. Esta sesión decide ese contenido item por item.

Para cada item, este documento provee:
1. **Texto placeholder vigente** (qué dice hoy el código)
2. **Contexto académico** (qué variable mide, en qué hipótesis del paper interviene)
3. **Pregunta específica para Garis** o decisión a tomar
4. **Espacio de decisión** marcado con checkbox

### 0.2 Tiempo total estimado

**3h 15min** dividido en 4 bloques:

| Orden | Bloque | Items | Tiempo |
|---|---|---|---|
| 1 | Cuestionario IA previa (P2-2) | 8 | 45 min |
| 2 | Pretest autoeficacia — selección de instrumento base | — | 30 min |
| 3 | Pretest autoeficacia (P2-1) — items específicos | 12 | 1h 15min |
| 4 | Test transferencia (P2-3) | 3 + diseño 5 finales | 30 min |
| — | Síntesis + próximos pasos + cronograma comité ético | — | 15 min |
| **Total** | | **23 + diseño 5 finales** | **3h 15min** |

### 0.3 Documentos de referencia (leer antes de la sesión)

- **`paper-draft.md` §6.2 Tabla 4**: instrumentos del diseño cuasi-experimental y las variables que miden.
- **`paper-draft.md` §6.1 H1, H2, H3**: hipótesis que estos instrumentos sirven para validar.
- **`AI-NativeV3-main/docs/research/protocolo-autoeficacia-programacion.md`** (117 líneas): draft del pretest, 3 opciones de instrumento (Ramalingam & Wiedenbeck 1998, Schwarzer & Jerusalem 1995, Lishinski et al. 2016). Recomendación inicial: opción C (Lishinski).
- **`AI-NativeV3-main/docs/research/diseno-test-transfer.md`** (167 líneas): draft del test de transferencia, 5 análogos de transfer mapeados sobre problemas del banco. Bransford, Brown & Cocking (2000) — *near transfer*.
- **`AI-NativeV3-main/apps/academic-service/src/academic_service/services/instrumentos_content.py`** (~400 líneas): catálogo completo con los 23 items + funciones de validación + scoring.

---

## 1. INSTRUMENTO 1 — Cuestionario IA previa (P2-2)

**Variable que mide**: Experiencia previa con asistentes de IA generativa para programación.
**Función en el paper**: Covariable de control para H2 — sin controlar experiencia previa con IA, el efecto observado en perfiles de apropiación podría confundirse con efecto de exposición previa al asistente, NO con efecto del sistema de coherencia estructural propio del piloto.
**Estado actual**: 8 items con `[PLACEHOLDER GARIS]` en `instrumentos_content.py` líneas 38-120. Tabla `respuestas_cuestionario_ia` ya migrada con RLS. Schema validado.

### 1.1 Items propuestos (versión actual del código)

| # | ID | Texto actual | Tipo | Opciones / escala | Obligatorio |
|---|---|---|---|---|---|
| 1 | `uso_general_meses` | "¿Hace cuantos meses usas asistentes de IA generativa (ChatGPT, Claude, Copilot, etc.)?" | single_choice | Nunca / <1m / 1-6m / 6-12m / >12m | ✅ |
| 2 | `frecuencia_uso` | "¿Con que frecuencia los usas para programar?" | single_choice | Nunca / Mensual / Semanal / Diario / Múltiples veces al día | ✅ |
| 3 | `tipos_tarea` | "¿Para que tipos de tarea de programacion usas IA? (puede seleccionar varios)" | multiple_choice | Generar código / Depurar / Entender ajeno / Aprender / Refactor / Documentación / Otra | ✅ |
| 4 | `autopercepcion_dependencia` | "En una escala 1-5, ¿cuanto sentis que dependes de la IA para programar?" | likert 1-5 | 1=Nada, 3=Moderado, 5=Totalmente | ✅ |
| 5 | `episodios_delegacion_previos` | "¿Alguna vez aceptaste codigo de la IA sin entender por que funcionaba? (autorreporte honesto)" | single_choice | Nunca / Pocas / A veces / Frecuente / Casi siempre | ✅ |
| 6 | `verificacion_critica` | "Cuando la IA te da una respuesta, ¿cuanto verificas que sea correcta antes de usarla?" | likert 1-5 | 1=No verifico, 5=Siempre con tests | ✅ |
| 7 | `experiencia_otros_dominios` | "¿Usas IA para tareas no-programacion (escritura, estudio, etc.)?" | single_choice | Nunca / Raramente / A veces / Frecuente / Diario | ⚪ |
| 8 | `expectativa_carrera` | "¿Crees que vas a trabajar como programador sin usar IA en 5 anos?" | single_choice | Imposible / Improbable / Posible / Probable preferiría evitar / Seguro | ⚪ |

### 1.2 Preguntas específicas para Ana Garis

**(A) Cobertura conceptual del constructo**. La operacionalización vigente captura cinco dimensiones: cantidad (item 1), frecuencia (item 2), repertorio de uso (item 3), autopercepción afectiva (items 4-6), generalización a otros dominios (item 7) y expectativa (item 8). ¿La operacionalización cubre el constructo "experiencia previa con IA" como variable de control adecuada para H2, o falta alguna dimensión (ej. tipo de asistente usado, contexto formativo, autoeficacia con IA específicamente)?

**(B) Sensibilidad de los items**. El item 5 (`episodios_delegacion_previos`) es el más sensible: pregunta por delegación pasiva previa con marco explícitamente honesto ("autorreporte honesto"). Riesgos: (i) deseabilidad social que infla las respuestas hacia "Pocas veces" o "Nunca", (ii) revelación de prácticas que el estudiante percibe como negativas. ¿Conviene reformular para reducir el sesgo de deseabilidad social, o el framing del paper §4.4 (los perfiles son observacionales, no morales) lo neutraliza suficientemente?

**(C) Likert versus categórico**. Los items 4 y 6 son Likert 1-5, los items 1, 2, 5, 7, 8 son categóricos ordinales con 5 niveles. ¿Hay razón para uniformar (todo Likert o todo categórico) o la heterogeneidad refleja la naturaleza distinta de cada constructo (intensidad continua vs. frecuencia discreta)?

**(D) Tiempo de aplicación**. 8 items de respuesta rápida ≈ 4-6 minutos. ¿Conviene reducir a 5-6 items críticos (descartar los opcionales 7 y 8 o consolidar 1+2 en un solo item compuesto) para reducir carga si se aplica junto con el pretest de autoeficacia (~15 min) en la misma sesión?

### 1.3 Decisiones de Ana Garis

Para cada item:

- Item 1 (uso_general_meses): [ ] aprobar texto / [ ] modificar texto: ____________ / [ ] descartar item
- Item 2 (frecuencia_uso): [ ] aprobar / [ ] modificar: ____________ / [ ] descartar
- Item 3 (tipos_tarea): [ ] aprobar / [ ] modificar: ____________ / [ ] descartar / [ ] agregar/quitar opciones: ____________
- Item 4 (autopercepcion_dependencia): [ ] aprobar / [ ] modificar: ____________ / [ ] descartar
- Item 5 (episodios_delegacion_previos): [ ] aprobar tal cual / [ ] reformular para reducir deseabilidad social: ____________ / [ ] descartar
- Item 6 (verificacion_critica): [ ] aprobar / [ ] modificar: ____________ / [ ] descartar
- Item 7 (experiencia_otros_dominios) [opcional]: [ ] aprobar / [ ] descartar / [ ] hacer obligatorio
- Item 8 (expectativa_carrera) [opcional]: [ ] aprobar / [ ] descartar / [ ] hacer obligatorio

Decisión global de versión: [ ] mantener `cuestionario-ia-v0.1.0-draft` hasta nueva revisión / [ ] bumpear a `cuestionario-ia-v1.0.0` (apto piloto)

---

## 2. INSTRUMENTO 2 — Pretest de autoeficacia (P2-1) — Decisión de instrumento base

**Variable que mide**: Disposición previa de autoeficacia del estudiante en programación (Bandura, 1997).
**Función en el paper**: Covariable de control crítica para H1 y H2 — las diferencias entre tipos de apropiación deben mantenerse significativas **después de controlar por autoeficacia inicial**, descartando que el efecto se explique por disposición afectiva previa al estudio.
**Estado actual**: El draft `protocolo-autoeficacia-programacion.md` propone 3 opciones de instrumento. La implementación vigente en `instrumentos_content.py` materializa un extracto placeholder de **12 items** (3 por sub-escala) basado en la opción C (Lishinski 2016). La elección final de instrumento base depende de esta sesión.

### 2.1 Las tres opciones del draft

| Opción | Instrumento | Items | Tiempo | Validez documentada | Adaptación castellano |
|---|---|---|---|---|---|
| A | Computer Programming Self-Efficacy Scale (Ramalingam & Wiedenbeck, 1998) | 32 ítems Likert 1-7 específicos de programación | 15-20 min | n=300+ CS1/CS2 anglófono | No documentada |
| B | General Self-Efficacy Scale + 5 ítems específicos (Schwarzer & Jerusalem, 1995) | 10 generales + 5 programación | 8-10 min | Validez convergente con outcomes documentada por Lishinski et al. (2016) | Sí (escala general) |
| C ⭐ | CS Self-Efficacy Scale (Lishinski et al., 2016) | 28 ítems específicos de CS universitario | 12-15 min | n=190 EE.UU. | No documentada |

**Recomendación inicial del draft**: opción C por especificidad al dominio CS universitario + tiempo razonable. Pero la adaptación al castellano rioplatense no existe — habría que hacerla.

### 2.2 Preguntas específicas para Ana Garis

**(A) Selección de instrumento base**. ¿Mantener la recomendación inicial del draft (opción C, Lishinski 2016) o pivotar a una de las otras opciones por consideraciones que el draft no contempló (ej. tiempo de aplicación si se combina con cuestionario IA, disponibilidad de adaptación castellana ya validada, alineamiento con escala usada en otros estudios del programa de doctorado)?

**(B) Adaptación rioplatense**. Si se confirma opción C, el draft propone: traducción inversa por 2 traductores independientes + pilotaje cognitivo con 3-5 estudiantes UTN (think-aloud) + análisis preliminar Cronbach α ≥ 0,8 sobre n=30. ¿Es viable este protocolo en el calendario del piloto, o conviene optar por adaptación más rápida (un solo traductor + revisión coautoral, sin pilotaje cognitivo formal)?

**(C) Esfuerzo de adaptación versus rigor**. La adaptación completa son ~30-40 h (traducción + pilotaje + análisis). Una adaptación más ligera serían ~8-12 h. La diferencia se traduce en defensa: con adaptación rigurosa el comité puede preguntar "¿confiamos en los scores?" y se responde con Cronbach + pilotaje; con adaptación ligera el disclaimer del piloto-1 debe ser más fuerte.

### 2.3 Decisión

- [ ] Opción A (Ramalingam & Wiedenbeck, 1998) — adaptación necesaria
- [ ] Opción B (Schwarzer & Jerusalem, 1995) — escala general en castellano ya validada
- [ ] Opción C (Lishinski 2016) — recomendación inicial, adaptación necesaria
- [ ] Combinación: ____________

Protocolo de adaptación elegido:
- [ ] Riguroso (traducción inversa + pilotaje cognitivo + Cronbach n=30) — ~30-40 h
- [ ] Ligero (1 traductor + revisión coautoral) — ~8-12 h
- [ ] Otro: ____________

---

## 3. INSTRUMENTO 2 (cont.) — Items específicos del pretest autoeficacia

> Esta sección **solo se completa si la decisión §2 elige opción C (Lishinski 2016)**. Si se elige otra opción, este bloque se reformula con los items del instrumento elegido.

### 3.1 Items propuestos (extracto v0.1.0-draft, 12 de los 28 finales de Lishinski 2016)

**Sub-escala 1 — Dominio independiente** (3 items):

| # | ID | Texto adaptado | Likert |
|---|---|---|---|
| 1 | `ind_01` | "Puedo escribir un programa corto si tengo la consigna clara." | 1-7 |
| 2 | `ind_02` | "Puedo depurar un error de logica en mi propio codigo sin ayuda." | 1-7 |
| 3 | `ind_03` | "Puedo elegir entre dos estructuras de datos para resolver un problema." | 1-7 |

**Sub-escala 2 — Complejidad** (3 items):

| # | ID | Texto adaptado | Likert |
|---|---|---|---|
| 4 | `comp_01` | "Puedo entender codigo de mas de 100 lineas escrito por otra persona." | 1-7 |
| 5 | `comp_02` | "Puedo escribir un programa con varias funciones que interactuan entre si." | 1-7 |
| 6 | `comp_03` | "Puedo razonar sobre la complejidad temporal de un algoritmo (O(n), O(n log n))." | 1-7 |

**Sub-escala 3 — Aprendizaje** (3 items):

| # | ID | Texto adaptado | Likert |
|---|---|---|---|
| 7 | `apr_01` | "Puedo aprender un lenguaje de programacion nuevo en pocas semanas." | 1-7 |
| 8 | `apr_02` | "Puedo leer documentacion tecnica y aplicarla a mi codigo." | 1-7 |
| 9 | `apr_03` | "Puedo identificar mis lagunas de conocimiento y trabajarlas." | 1-7 |

**Sub-escala 4 — Persistencia** (3 items):

| # | ID | Texto adaptado | Likert |
|---|---|---|---|
| 10 | `per_01` | "Sigo intentando aunque mi programa no funcione despues de varios intentos." | 1-7 |
| 11 | `per_02` | "Confio en mi capacidad para resolver problemas dificiles si me da el tiempo." | 1-7 |
| 12 | `per_03` | "No me rindo aunque la consigna parezca demasiado dificil al principio." | 1-7 |

### 3.2 Preguntas específicas para Ana Garis

**(A) Extracto vs. instrumento completo**. La versión vigente del código tiene 12 items (3 por sub-escala) como placeholder para validar el flujo end-to-end. El instrumento completo de Lishinski son 28 items (~7 por sub-escala). Decisión: ¿se aplica el instrumento completo (28 items, ~15 min, mayor confiabilidad) o un extracto validado (~12 items, ~6 min, menor confiabilidad pero menor carga)?

**(B) Validación del extracto**. Si se opta por extracto, ¿estos 3 items por sub-escala son los más representativos del constructo de Lishinski, o conviene seleccionar otros 3 según criterios psicométricos del paper original (cargas factoriales más altas, mejor discriminación)?

**(C) Traducción rioplatense de cada item**. Los textos vigentes son traducciones literales del inglés con voseo simplificado. Tres ejemplos sensibles:
   - Item 4: "*more than 100 lines of code*" → "*mas de 100 lineas*". ¿Es el umbral correcto para el contexto UTN?
   - Item 6: ejemplos "O(n), O(n log n)". ¿Esta notación es la usada en la cátedra UTN o se prefiere notación verbal ("complejidad lineal vs. log-lineal")?
   - Item 11: "*solve hard problems if given enough time*" → "*resolver problemas dificiles si me da el tiempo*". El subjuntivo "me da" suena formal. ¿"si me dan el tiempo" o "si tengo tiempo suficiente"?

**(D) Scoring**. El draft no decide entre: (i) **suma total** (rango 12-84), (ii) **promedio por sub-escala** (4 scores), (iii) **z-score estandarizado sobre cohorte** (más sensible a posición relativa). La implementación vigente computa total + promedio por sub-escala. ¿Esto está OK como reporting básico, o se prefiere algún derivado adicional para el análisis covariado?

### 3.3 Decisiones por item

- Item 1 (ind_01): [ ] aprobar tal cual / [ ] modificar texto: ____________ / [ ] reemplazar por item alternativo de Lishinski #__
- Item 2 (ind_02): [ ] aprobar / [ ] modificar: ____________ / [ ] reemplazar
- Item 3 (ind_03): [ ] aprobar / [ ] modificar: ____________ / [ ] reemplazar
- Item 4 (comp_01): [ ] aprobar / [ ] modificar: ____________ / [ ] reemplazar
- Item 5 (comp_02): [ ] aprobar / [ ] modificar: ____________ / [ ] reemplazar
- Item 6 (comp_03): [ ] aprobar / [ ] modificar: ____________ / [ ] reemplazar
- Item 7 (apr_01): [ ] aprobar / [ ] modificar: ____________ / [ ] reemplazar
- Item 8 (apr_02): [ ] aprobar / [ ] modificar: ____________ / [ ] reemplazar
- Item 9 (apr_03): [ ] aprobar / [ ] modificar: ____________ / [ ] reemplazar
- Item 10 (per_01): [ ] aprobar / [ ] modificar: ____________ / [ ] reemplazar
- Item 11 (per_02): [ ] aprobar / [ ] modificar: ____________ / [ ] reemplazar
- Item 12 (per_03): [ ] aprobar / [ ] modificar: ____________ / [ ] reemplazar

Decisión sobre escala:
- [ ] mantener 12 items extracto piloto-1 (Cronbach esperado moderado, carga ~6 min)
- [ ] expandir a 28 items completos (Cronbach esperado alto, carga ~15 min)
- [ ] cantidad intermedia (ej. 20 items, 5 por sub-escala): ____________

Decisión sobre scoring:
- [ ] suma total + promedio por sub-escala (actual)
- [ ] z-score estandarizado sobre cohorte
- [ ] otra: ____________

---

## 4. INSTRUMENTO 3 — Test de transferencia (P2-3)

**Variable que mide**: Capacidad del estudiante de resolver problemas estructuralmente análogos a los del banco del piloto pero con cambio de dominio superficial (*near transfer*, Bransford, Brown & Cocking, 2000).
**Función en el paper**: Medida dependiente principal para H2 — sin este test, H2 ("la coherencia estructural se asocia con desempeño en transferencia") queda declarativa.
**Estado actual**: 3 problemas con `[PLACEHOLDER CATEDRA UTN]` en `instrumentos_content.py` líneas 349-384. El draft `diseno-test-transfer.md` propone **5 problemas finales** mapeados como análogos estructurales sobre el banco. Tabla `respuestas_test_transferencia` ya migrada con CheckConstraint para `group_assignment IN ('experimental', 'comparison')`.

### 4.1 Los 5 análogos propuestos por el draft (todavía no en código)

| # | Problema del banco | Análogo de transfer propuesto | Patrón algorítmico preservado |
|---|---|---|---|
| 1 | Encontrar el segundo mayor de una lista de enteros | Encontrar el segundo más largo de una lista de strings | Iteración + condición |
| 2 | Sumar elementos pares de una lista | Concatenar los strings que empiezan con vocal de una lista | Agregación condicional |
| 3 | Contar ocurrencias de un valor en una lista | Contar caracteres únicos en un string | Conteo |
| 4 | Invertir una lista | Invertir las palabras de una frase (manteniendo orden de letras) | Transformación |
| 5 | Determinar si una lista está ordenada | Determinar si las palabras de una frase están en orden alfabético | Validación |

**Decisión de diseño del draft**: los análogos no deben ser triviales (find-and-replace de la solución del banco) ni demasiado lejanos (debe ser plausible que un estudiante con apropiación reflexiva los resuelva). Distancia estructural objetivo: 2-4 sobre 5 según calificación de 3 docentes UTN independientes.

### 4.2 Lo que está en código vs. lo que falta

**En código (3 placeholders v0.1.0-draft)**:
- `transfer-01` "Segundo mayor de una lista" — replica el problema del banco, NO el análogo.
- `transfer-02` "Invertir un diccionario" — análogo libre, NO alineado a uno de los 5 del draft.
- `transfer-03` "Razonamiento sobre complejidad" — meta-pregunta, NO un near transfer.

**Falta migrar al código**: los 5 análogos del draft con su patrón algorítmico preservado y patrones de evaluación automática.

### 4.3 Preguntas específicas para la cátedra UTN (Garis + 3 docentes)

**(A) Validez de contenido de los 5 análogos**. ¿Los 5 mapeos propuestos son los más representativos del *near transfer* sobre el banco vigente del piloto, o algún docente sugiere reemplazos? Criterio del draft: distancia estructural 2-4 sobre 5.

**(B) Calibración de dificultad esperada**. Cada análogo debe tener dificultad esperada 2-4 sobre 5. ¿Hay análogos que la cátedra estima fuera de ese rango (muy fácil < 2 o muy difícil > 4)?

**(C) Scoring por problema**. El draft propone escala ordinal 0-2: 0 = sin intentar / 1 = estructura correcta con errores / 2 = solución funcional correcta. Total: 0-10 sobre los 5 problemas. ¿Esta escala discrimina suficiente, o conviene 0-3 (sin / parcial / con errores menores / completa)?

**(D) Rúbrica de explicación corta**. El draft propone que después de cada problema haya espacio de 50-150 caracteres para que el estudiante "explique brevemente cómo encararía el problema si tuviera más tiempo". Esto captura proceso autorreportado complementario. ¿Es valioso este componente cualitativo, o sobrecarga el instrumento? Si vale: análisis temático por 2 codificadores (κ ≥ 0,70) con categorías (a) estrategia algorítmica explícita, (b) reformulación, (c) bloqueo declarado, (d) sin respuesta.

**(E) Patrones de evaluación automática**. Para que el scoring sea consistente entre estudiantes, cada problema necesita un patrón de evaluación automática: regex sobre output / pattern matching sobre AST / ejecución de tests pasados-fallados. El código vigente devuelve `False` por default (no infla métricas espurias). ¿Quién diseña los 5 patrones? ¿Garis directamente, o un docente con experiencia en autograders?

**(F) Aplicación con grupo de comparación**. H2 requiere comparar transfer score entre grupo experimental (con CTR activo) y grupo de comparación (sin CTR). El grupo de comparación NO usa el sistema instrumentado — esto excluye el flujo normal de TP. **Decisión crítica**: ¿cómo se recolectan las respuestas del grupo de comparación? Opciones: (i) formulario externo (Google Forms / SurveyMonkey), (ii) endpoint público sin auth dentro del sistema, (iii) papel + transcripción. Cada opción tiene implicancias éticas y de validez.

### 4.4 Decisión

Para cada análogo del draft:
- Análogo 1 (segundo más largo de strings): [ ] aprobar / [ ] reemplazar por: ____________ / [ ] descartar
- Análogo 2 (concatenar strings con vocal inicial): [ ] aprobar / [ ] reemplazar / [ ] descartar
- Análogo 3 (contar caracteres únicos): [ ] aprobar / [ ] reemplazar / [ ] descartar
- Análogo 4 (invertir palabras de frase): [ ] aprobar / [ ] reemplazar / [ ] descartar
- Análogo 5 (palabras en orden alfabético): [ ] aprobar / [ ] reemplazar / [ ] descartar

Decisión sobre rúbrica cualitativa:
- [ ] mantener explicación corta de 50-150 caracteres por problema (carga +5 min, valor cualitativo)
- [ ] descartar componente cualitativo (carga menor, solo score numérico)
- [ ] modalidad mixta: ____________

Decisión sobre recolección del grupo de comparación:
- [ ] formulario externo sin auth (Google Forms o similar)
- [ ] endpoint público del sistema sin autenticación (privacy review del comité ético)
- [ ] papel + transcripción manual
- [ ] otra: ____________

Quién diseña los 5 patrones de evaluación automática:
- [ ] Garis directamente
- [ ] Docente designado: ____________
- [ ] Cortez + dev backend con revisión de Garis

---

## 5. Aprobación ética del comité UTN

Los 3 instrumentos requieren **aprobación del comité ético UTN** antes de la aplicación en el piloto real. El protocolo de entrevistas semi-estructuradas (P2-4, `docs/research/protocolo-entrevistas-piloto.md`) también requiere aprobación ética por separado.

### 5.1 Decisiones

- [ ] presentación al comité ético en sesión única consolidada (4 instrumentos + 1 protocolo entrevistas)
- [ ] presentación escalonada (instrumentos primero, entrevistas después)
- [ ] consultar con dirección del programa si los instrumentos requieren aprobación específica o están cubiertos por el protocolo general del piloto

Texto de consentimiento informado para los 3 instrumentos:
- [ ] usar el texto del draft autoeficacia §2.3 (líneas 67-69) adaptado a cada instrumento
- [ ] redactar texto unificado nuevo
- [ ] derivar a dirección + comité ético

---

## 6. Próximos pasos post-sesión

### 6.1 Si la sesión aprueba todo (escenario optimista)

1. **Por cada item aprobado**: sacar el marker `[PLACEHOLDER GARIS]` / `[PLACEHOLDER CATEDRA UTN]` del literal en `instrumentos_content.py` (manualmente, item por item). El test `test_catalogo_tiene_marcadores_placeholder` empezará a fallar para esos items — eso es señal explícita de validación pasada.
2. **Por cada item modificado**: actualizar el literal del texto antes de sacar el marker.
3. **Bumpear versión**: `cuestionario-ia-v0.1.0-draft` → `cuestionario-ia-v1.0.0`; `lishinski-2016-es-utn-v0.1.0-draft` → `lishinski-2016-es-utn-v1.0.0` (o nombre nuevo si se cambia instrumento base); `transfer-test-v0.1.0-draft` → `transfer-test-v1.0.0`.
4. **Migrar los 5 análogos del draft test transferencia al código** (`instrumentos_content.py` `TEST_TRANSFERENCIA_PROBLEMS`).
5. **Implementar patrones de evaluación automática** (`evaluate_test_transferencia_answer`) según decisión §4.3.E.
6. **Submitir al comité ético UTN** los 3 instrumentos + protocolo entrevistas.
7. **Entrada en `AI-NativeV3-main/docs/SESSION-LOG.md`** documentando esta sesión coautoral.

### 6.2 Si la sesión rechaza alguna sección (escenario realista)

Para cada item rechazado o pendiente de reformulación:
1. Documentar el rechazo en `SESSION-LOG.md` con la razón.
2. Mantener el marker `[PLACEHOLDER GARIS]` / `[PLACEHOLDER CATEDRA UTN]` activo — el item sigue marcado como no validado.
3. Si el rechazo afecta toda una sub-escala o instrumento entero, abrir CS nuevo en `plan1Socra.md` con propuesta alternativa.

### 6.3 Si la sesión necesita más tiempo

Los 4 bloques se pueden agrupar en 2 sesiones de ~1h 40min:
- **Sesión 1** — Cuestionario IA previa (1h) + Decisión instrumento autoeficacia (30 min) + Síntesis (10 min) = **1h 40 min**.
- **Sesión 2** — Items autoeficacia (1h 15min) + Test transferencia (25 min) = **1h 40 min**.

### 6.4 Coordinación con cátedra UTN para test de transferencia

El test de transferencia requiere validación de contenido con 3 docentes UTN independientes (no solo Garis). El draft propone:
- Sesión coordinada de 4-6 h con los 3 docentes simultáneamente.
- O sesiones individuales de 2-3 h por docente con consolidación posterior.

Decisión: ____________

Calendario propuesto post-sesión coautoral:
- Semana 1: cierre items del cuestionario IA + autoeficacia con Garis.
- Semana 2-3: validación de contenido del test de transferencia con 3 docentes UTN.
- Semana 4: submisión consolidada al comité ético.
- Semana 5-8: respuesta del comité y ajustes.
- Semana 9+: aplicación piloto real (dependiente del calendario académico UTN).

---

## 7. Anexos: referencias cruzadas

### 7.1 Archivos relevantes para la sesión

- **`docs/papers/paper-draft.md` §6.2 Tabla 4**: instrumentos del diseño y variables que miden.
- **`docs/papers/paper-draft.md` §6.1 H1, H2**: hipótesis que estos instrumentos validan.
- **`AI-NativeV3-main/apps/academic-service/src/academic_service/services/instrumentos_content.py`** (~400 líneas): catálogo completo de los 23 items + scoring.
- **`AI-NativeV3-main/docs/research/protocolo-autoeficacia-programacion.md`** (117 líneas): draft pretest, 3 opciones de instrumento.
- **`AI-NativeV3-main/docs/research/diseno-test-transfer.md`** (167 líneas): draft test transferencia, 5 análogos estructurales.
- **`AI-NativeV3-main/apps/academic-service/tests/unit/test_instrumentos.py`**: tests unit del esqueleto técnico, incluye `test_catalogo_tiene_marcadores_placeholder` que verifica que los markers no se hayan quitado sin aprobación.

### 7.2 Referencias bibliográficas (ya en el repo o pendientes de agregar al paper si aplica)

- Bandura, A. (1997). *Self-efficacy: The exercise of control*. W. H. Freeman.
- Ramalingam, V., & Wiedenbeck, S. (1998). Development and validation of scores on a computer programming self-efficacy scale. *Journal of Educational Computing Research*, 19(4), 367-381.
- Schwarzer, R., & Jerusalem, M. (1995). Generalized Self-Efficacy scale.
- Lishinski, A., Yadav, A., Good, J., & Enbody, R. (2016). Learning to program: Gender differences and interactive effects of students' motivation, goals, and self-efficacy on performance. *ICER '16 Proceedings*, 211-220.
- Bransford, J. D., Brown, A. L., & Cocking, R. R. (Eds.). (2000). *How People Learn: Brain, Mind, Experience, and School*. National Academy Press.
- Detterman, D. K. (1993). The case for the prosecution: Transfer as an epiphenomenon.
- Barnett, S. M., & Ceci, S. J. (2002). When and where do we apply what we learn? A taxonomy for far transfer. *Psychological Bulletin*, 128(4), 612-637.

### 7.3 Quién hace qué post-sesión

| Tarea | Responsable | Tiempo estimado |
|---|---|---|
| Sacar markers `[PLACEHOLDER GARIS]` de items aprobados en `instrumentos_content.py` | Sub-agente o Cortez | 30 min |
| Aplicar reformulaciones acordadas (texto de items) | Sub-agente o Cortez | 1-2 h |
| Migrar los 5 análogos del draft a `TEST_TRANSFERENCIA_PROBLEMS` | Cortez + dev | 2-3 h |
| Implementar `evaluate_test_transferencia_answer` con patrones reales | Diseñador asignado §4.3.E + dev | 8-16 h |
| Bumpear `instrument_version` de los 3 catálogos | Sub-agente | 15 min |
| Coordinar validación contenido test transfer con 3 docentes UTN | Cortez + Garis | semanas calendario |
| Submisión al comité ético UTN | Cortez + Garis | 4-6 h redacción + tiempo de comité |
| Entrada al `SESSION-LOG.md` documentando la sesión coautoral | Sub-agente | 30 min |

---

## 8. Resumen de un párrafo para enviar a Ana Garis previa a la sesión

> "Ana, te paso este material para preparar la sesión coautoral sobre la validación de contenido de los 3 instrumentos del diseño cuasi-experimental (Cuestionario IA previa, Pretest autoeficacia, Test transferencia). El sprint 2026-05-17 cerró el esqueleto técnico end-to-end — backend, migration, RLS, Casbin, frontend en web-student y web-teacher, k-anonymity gate, todo verificado por tests unit. Lo que falta es el contenido académico, marcado explícitamente con `[PLACEHOLDER GARIS]` y `[PLACEHOLDER CATEDRA UTN]` en `instrumentos_content.py`. Son 23 items (8 + 12 + 3) más el diseño final de los 5 análogos de transfer. Para el pretest hay 3 opciones de instrumento base (Ramalingam 1998, Schwarzer 1995, Lishinski 2016) con recomendación inicial Lishinski por especificidad CS. La sesión es de ~3h 15min, agrupable en 2 sesiones de ~1h 40min si te queda mejor. Las decisiones técnicamente más sustantivas son: (a) selección de instrumento base autoeficacia, (b) diseño final de los 5 análogos de transfer + sus patrones de evaluación automática, (c) recolección del grupo de comparación para H2. Las demás son aprobación/reformulación item por item, mecánicas. Cuando aprobamos un item, lo señalizo en código sacando el marker — el test golden falla, y eso marca el paso a contenido validado. ¿Cuándo te queda bien?"

---

**Generado**: 2026-05-20 por sesión de coordinación post-`PlanMejora.md` sub-sprint 4. Espejo estructural del `revision-coautoral-paper-2026-05-16.md` para que el formato sea familiar.
