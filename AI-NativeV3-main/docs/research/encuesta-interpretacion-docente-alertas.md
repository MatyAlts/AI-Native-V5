# Instrumento de encuesta — Interpretación docente de las alertas predictivas (R9 informeSoc.md)

**Versión**: 1.0.0 — instrumento inicial
**Fecha**: 2026-05-16
**Autor**: derivado de informeSoc.md §7.4 (las alertas como diagnóstico de facto)
**Objetivo**: medir si los docentes UNSL interpretan las tres alertas predictivas (`regresion_vs_cohorte`, `bottom_quartile`, `slope_negativo_significativo`) como guía pedagógica situada o como predicción de resultado académico final.

---

## 0. Por qué este instrumento existe

ADR-022 declara las alertas como "pedagógicas, no clínicas". El framing es defendible pero opera *sólo* a nivel del documento. Una alerta que el docente lee como sentencia funciona de facto como diagnóstico, aunque el ADR la enmarque pedagógicamente.

El piloto necesita verificar empíricamente cómo los docentes interpretan las alertas en la práctica. Sin esa medición, el paper no puede afirmar honestamente que las alertas operaron como guía pedagógica vs como predicción de aprobación. Esta encuesta es ese instrumento.

---

## 1. Diseño general

### 1.1 Tipo de instrumento

Encuesta semi-estructurada de aplicación retrospectiva al final del primer cuatrimestre del piloto. Combina:
- 6 ítems Likert de 5 puntos (cuantitativos, comparables entre docentes).
- 4 preguntas abiertas (cualitativas, para capturar matices).
- 3 viñetas con casos sintéticos (estímulos comunes para reducir varianza interpretativa).

### 1.2 Aplicación

- **Cuándo**: 2 semanas después de la última clase del cuatrimestre. Antes de tener los promedios finales del semestre para evitar contaminación retrospectiva.
- **A quién**: todos los docentes UNSL que usaron el panel `web-teacher` al menos 4 veces en el cuatrimestre (filtro de exposición mínima).
- **Cómo**: formulario Google Forms o equivalente. Tiempo estimado de respuesta: 20-25 minutos.
- **Anonimato**: respuestas pseudonimizadas con `docente_pseudonym` (hash determinista del UUID con salt de la encuesta). Solo dirección de tesis tiene la tabla de mapeo.

### 1.3 Consentimiento informado

Antes del ítem 1 el docente lee:

> "Esta encuesta es parte de la investigación del piloto AI-Native N4 (tesis doctoral UNSL, A. Cortez). Sus respuestas serán pseudonimizadas y analizadas en agregado. Los resultados aparecerán en la sección 6 del paper Cortez & Garis. Puede dejar la encuesta en cualquier momento. ¿Está de acuerdo en participar?"

Sin la marca afirmativa el formulario no avanza.

---

## 2. Ítems del instrumento

### Sección A — Uso autorreportado (4 ítems Likert)

**A1.** "Durante el cuatrimestre revisé las alertas de mis estudiantes en `web-teacher`":
- Nunca / Una o dos veces / Varias veces al cuatrimestre / Varias veces al mes / Varias veces por semana

**A2.** "Cuando una alerta aparecía sobre un estudiante, lo siguiente que hacía era":
- (Respuesta de selección única, opciones aleatorizadas)
- (a) Anotaba el nombre para hablar con el estudiante en la próxima clase.
- (b) Abría el detalle del estudiante para entender qué pasaba.
- (c) Tomaba nota mental sin actuar inmediatamente.
- (d) Otra (especificar en A2_otra).

**A3_otra.** [Pregunta abierta condicional si seleccionó "Otra"]: "¿Cuál era esa otra acción?"

**A4.** "Las alertas me ayudaron a identificar estudiantes que necesitaban acompañamiento que no habría detectado sin ellas":
- Totalmente en desacuerdo / En desacuerdo / Ni acuerdo ni desacuerdo / De acuerdo / Totalmente de acuerdo

### Sección B — Interpretación (2 ítems Likert)

**B1.** Las alertas predictivas son una herramienta:
- "Para predecir qué estudiantes probablemente desaprobarán": [Likert 1-5]
- "Para guiar mi acompañamiento pedagógico situado": [Likert 1-5]
- "Ambas cosas por igual": [Likert 1-5]

(El estudiante debería marcar tres Likerts independientes; el patrón de respuesta revela el framing).

**B2.** "Si un estudiante apareció con la alerta `bottom_quartile` (cuartil inferior), ese estudiante":
- (Respuesta abierta de 50-150 palabras)

### Sección C — Viñetas (3 casos sintéticos)

Cada viñeta presenta un caso fabricado pero plausible. El docente lee y responde qué haría.

**Viñeta 1 — Solo `bottom_quartile`**
> "Marta es estudiante de tu comisión. Al cabo de 4 episodios cerrados, su slope longitudinal está en el cuartil inferior de la cohorte (Q1). No tiene otras alertas activas. Su asistencia es regular y entregó todas las consignas del cuatrimestre hasta ahora. ¿Qué hacés ante esta información?"

(Respuesta abierta de 100-200 palabras)

**Viñeta 2 — `slope_negativo_significativo` aislado**
> "Tomás es estudiante de tu comisión. Sus primeros 3 episodios mostraron apropiación reflexiva; los últimos 3 muestran apropiación superficial. El sistema dispara `slope_negativo_significativo` con slope -0.35. No está en cuartil inferior (la cohorte completa también tiene slope ligeramente negativo). ¿Qué hacés ante esta información?"

(Respuesta abierta de 100-200 palabras)

**Viñeta 3 — `regresion_vs_cohorte` con z-score severo**
> "Laura es estudiante de tu comisión. Su slope está 2.4 sigma por debajo del promedio de la cohorte. El sistema dispara `regresion_vs_cohorte` con severidad alta. Su asistencia es irregular y todavía no entregó el TP3 del cuatrimestre. ¿Qué hacés ante esta información?"

(Respuesta abierta de 100-200 palabras)

### Sección D — Reflexión libre (2 preguntas abiertas)

**D1.** "¿Hubo algún caso durante el cuatrimestre en que una alerta te ayudó a tomar una decisión pedagógica concreta que recordás especialmente? Contanos brevemente."

**D2.** "¿Hubo algún caso en que una alerta te haya parecido injusta o desorientadora sobre un estudiante? Contanos brevemente."

---

## 3. Análisis del instrumento

### 3.1 Métrica primaria — *framing pedagógico vs predictivo*

Construir una variable continua `framing_pedagogico` por docente, computada como:

```
framing_pedagogico = (B1.pedagogico - B1.predictivo) / 5
```

Rango [-1, +1]. Valor positivo → docente operó las alertas como guía pedagógica. Valor negativo → docente las operó como predicción de resultado.

**Hipótesis nula del instrumento**: la distribución de `framing_pedagogico` en la cohorte docente está centrada en 0 (sin sesgo neto). Esto sería la postura "ambas cosas por igual" agregada.

**Lectura crítica del paper**: si la media es positiva, el ADR-022 fue exitoso en su framing. Si es negativa, ADR-022 falló en la práctica y el paper debe reconocer que las alertas funcionaron como diagnóstico clínico-implícito.

### 3.2 Métrica secundaria — *coherencia entre uso autorreportado y viñetas*

Para cada docente comparar:
- Su `framing_pedagogico` declarado (sección B).
- El tono de sus respuestas a las viñetas (codificadas por dos investigadores con κ ≥ 0,70 sobre la dimensión "intervención pedagógica situada" vs "asunción de pronóstico").

Discrepancia entre declarado y situado → el docente "dice" usar las alertas pedagógicamente pero "actúa" predictivamente. Es la métrica de validez más interesante.

### 3.3 Lectura cualitativa — *categorías emergentes*

Análisis temático de las preguntas abiertas (D1, D2, B2 y las 3 viñetas) con dos codificadores independientes. Categorías iniciales sugeridas (a refinar inductivamente):

- **Acompañamiento situado**: el docente describe acercarse al estudiante, escuchar contexto, ajustar la próxima clase.
- **Comunicación directa**: el docente describe escribir al estudiante o llamarlo.
- **Vigilancia pasiva**: el docente describe "observar" sin acción explícita.
- **Diagnóstico de fragilidad**: el docente asume que el estudiante "tiene un problema" sin verificar.
- **Cuestionamiento de la alerta**: el docente desconfía del sistema y verifica antes de actuar.

---

## 4. Reporte en el paper

Resultados de este instrumento deberían aparecer en una sub-sección de la Sección 6 (Resultados) del paper Cortez & Garis, bajo el título tentativo "Interpretación docente de las alertas predictivas". Estructura sugerida:

1. Caracterización de la muestra (n docentes, exposición, ámbito).
2. Distribución de `framing_pedagogico` con histograma + media + IC95%.
3. Discrepancia declarado vs situado (correlación o coeficiente de acuerdo).
4. Categorías emergentes con conteos.
5. Citas representativas (con consentimiento).
6. **Discusión honesta**: si las alertas operaron pedagógicamente como ADR-022 estipula, o no, o parcialmente.

---

## 5. Limitaciones declaradas

- **n bajo**: el piloto-1 tendrá pocos docentes (estimado 3-5). Las inferencias estadísticas son ilustrativas, no concluyentes.
- **Efecto de deseabilidad social**: los docentes saben que la encuesta es de la tesis y pueden responder lo que "queda bien" en vez de lo que hicieron. Las viñetas mitigan esto pero no lo eliminan.
- **Sesgo de selección**: solo responden docentes que llegaron al final del cuatrimestre usando el panel. Los que dejaron de usarlo (posible señal de "no me sirvió") no quedan capturados a menos que se haga seguimiento separado.

---

## 6. Decisiones pendientes (requieren participación humana)

1. **Aprobación del instrumento** por dirección + co-dirección + Ana Garis.
2. **Selección de los 2 codificadores cualitativos**: ¿los mismos del intercoder o personas distintas? Lo deseable es **distintas** para evitar contaminación.
3. **Plataforma de aplicación**: Google Forms (rápido pero terceros) vs LimeSurvey hospedado en UNSL (más seguro pero más fricción).
4. **Inclusión del instrumento en `paper-draft.md` antes o después de aplicar**: lo metodológicamente honesto es **antes** —pre-registrar las hipótesis del análisis evita HARKing.

---

## 7. Referencias

- ADR-022 — alertas predictivas como estadística clásica, NO ML. Justifica el framing pedagógico que esta encuesta verifica.
- ADR-046 — protocolo intercoder para el análisis cualitativo de las preguntas abiertas.
- informeSoc.md §7.4 — diagnóstico de la necesidad del instrumento.
- `packages/platform-ops/src/platform_ops/cii_alerts.py` — implementación de las 3 alertas.
- AERA, APA, & NCME (2014). Standards for educational and psychological testing. American Educational Research Association.
