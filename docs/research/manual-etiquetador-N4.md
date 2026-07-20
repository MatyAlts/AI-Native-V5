# Manual del etiquetador — Estudio intercoder N4 (Protocolos A y B, ADR-046)

**Versión**: 1.0.0 — borrador para pre-calibración interna
**Fecha**: 2026-05-16
**Autor**: derivado del análisis pedagógico `informeSoc.md` (R1) y del marco operacional de ADR-046.
**Destinatarios**: dos docentes UTN que ejecutarán los Protocolos A y B; director y co-director de tesis para pre-calibración.

---

## 0. Por qué este manual existe

ADR-046 formaliza la validación intercoder con κ ≥ 0,70 sobre dos protocolos: Protocolo A (200 eventos estratificados N1-N4) y Protocolo B (50 episodios cerrados clasificados por apropiación). Sin un **manual operacional** explícito, dos etiquetadores que comparten el marco teórico pueden discrepar **no por desacuerdo conceptual sino por interpretación operacional**. Es estadísticamente esperable que κ caiga por debajo de 0,70 en la primera ronda si la operacionalización se deja a la intuición.

Este manual existe para que **dos lectores humanos llegados al mismo evento o episodio lleguen a la misma etiqueta por la misma razón**. Es el insumo para que la pre-calibración interna (con director y co-director sobre 20 eventos) preceda a la inversión de 25-30 h por docente externo.

El manual NO sustituye al paper ni al ADR-046. Los complementa con: definiciones operacionales en términos *observables al lector humano*, casos límite resueltos con justificación, y protocolo de pre-calibración.

---

## 1. Protocolo A — Etiquetado de eventos N1-N4

### 1.1 Qué se valida

La función pura `apps/classifier-service/src/classifier_service/services/event_labeler.py::label_event` con `LABELER_VERSION = 1.2.0`. Su tabla base (`EVENT_N_LEVEL_BASE`) más los overrides documentados en ADR-023 (anotación) y ADR-033/034 (tests) producen una etiqueta N1-N4 por evento.

El Protocolo A pregunta: **dado un evento concreto en su contexto temporal, ¿llegarían dos docentes a la misma etiqueta que la función?**

### 1.2 Muestra estratificada (de ADR-046)

200 eventos totales, 50 por nivel cognitivo. Estratificación necesaria porque las distribuciones reales son muy desbalanceadas (típicamente >70% N2/N3, <5% N1) y un muestreo proporcional dejaría algunos niveles sin muestras estadísticamente útiles.

**Selección sugerida** (a decidir con dirección antes de invitar a docentes):
- 50 eventos N1 reales: cualquier `lectura_enunciado` + `anotacion_creada` con override N1 (dentro de 120s del `episodio_abierto`).
- 50 eventos N2 reales: `edicion_codigo` con `origin=student_typed` + `anotacion_creada` sin overrides (fallback).
- 50 eventos N3 reales: `codigo_ejecutado` + `tests_ejecutados` etiquetados N3 por la regla v1.2.0.
- 50 eventos N4 reales: `prompt_enviado`, `tutor_respondio`, `intento_adverso_detectado`, `edicion_codigo` con `origin=copied_from_tutor`, `anotacion_creada` con override N4, `tests_ejecutados` etiquetados N4.

Los 200 eventos deben preservar su contexto: timestamps absolutos, `seq`, payload completo y los eventos cercanos (al menos ±60s) que afectan los overrides temporales.

### 1.3 Criterios operacionales por nivel

#### N1 — Comprensión y planificación

**Pregunta para el etiquetador**: ¿Este evento captura al estudiante intentando *entender qué pide el problema* o *armar un plan antes de codificar*?

**Eventos típicos N1**:
- `lectura_enunciado`: cualquier instancia. Es N1 por definición de la Tabla 4.1.
- `anotacion_creada` dentro de los **primeros 120 segundos** desde `episodio_abierto`, sin que haya habido un `tutor_respondio` previo en los últimos 60 segundos.

**Justificación pedagógica**: en los primeros dos minutos del episodio el estudiante está leyendo, no produciendo. Las anotaciones de este momento son notas de lectura, no de elaboración.

**Casos límite**:
- *Anotación a los 119 segundos*: N1 (la ventana es estricta, no aproximada).
- *Anotación a los 121 segundos*: N2 fallback (a menos que haya tutor en los 60s previos, ver §1.3-N4).
- *Anotación que el estudiante claramente está usando para describir el algoritmo*: aun así N1 si está dentro de 120s. La operacionalización temporal es deliberadamente ciega al contenido (ese es el punto de v1.1.0). Si el etiquetador discrepa, debe anotarlo como caso de revisión sin cambiar la etiqueta.

#### N2 — Elaboración estratégica

**Pregunta para el etiquetador**: ¿Este evento captura al estudiante *produciendo código propio* o *anotando algo elaborado*?

**Eventos típicos N2**:
- `edicion_codigo` con `payload.origin == "student_typed"`.
- `edicion_codigo` con `payload.origin == None` o `payload.origin` ausente (legacy).
- `anotacion_creada` fuera de las ventanas de override (N1 y N4).

**Casos límite**:
- *Edición con `origin` ausente del payload*: N2. El labeler trata `None` como student_typed por defecto. El etiquetador humano debe asumir lo mismo si la metadata no está presente.
- *Edición de pocas líneas vs edición masiva*: ambas N2 si origin=student_typed. El labeler no distingue por tamaño; el etiquetador tampoco debería.

#### N3 — Validación

**Pregunta para el etiquetador**: ¿Este evento captura al estudiante *ejecutando código o tests para verificar*?

**Eventos típicos N3**:
- `codigo_ejecutado`: siempre N3.
- `tests_ejecutados` con `payload.test_count_failed > 0`: N3 siempre (sin reflexión post-tutor cuando hay fallos).
- `tests_ejecutados` con `test_count_failed == 0` pero **sin tutor reciente** (>60s desde el último `tutor_respondio` o sin tutor todavía): N3.

**Casos límite**:
- *Tests pasando sin `tutor_respondio` previo en el episodio*: N3 (la regla N4 requiere que haya habido tutor previo y el delta sea ≥60s).
- *Ejecuciones de código rapidísimas (varias en pocos segundos)*: cada una es N3 independiente. El labeler no agrega.
- *Tests con `test_count_failed` no informado* (campo ausente del payload): N3 fallback.

#### N4 — Interacción con IA

**Pregunta para el etiquetador**: ¿Este evento captura al estudiante *interactuando con el asistente* o *usando código que vino del asistente*?

**Eventos típicos N4**:
- `prompt_enviado`: siempre N4.
- `tutor_respondio`: siempre N4.
- `intento_adverso_detectado`: siempre N4 (ADR-019).
- `edicion_codigo` con `payload.origin in {"copied_from_tutor", "pasted_external"}`: N4 por override de origen.
- `anotacion_creada` dentro de **60 segundos posteriores** a un `tutor_respondio`: N4 (apropiación post-respuesta, ADR-023).
- `tests_ejecutados` con `test_count_failed == 0` Y delta ≥60s desde último `tutor_respondio`: N4 (apropiación reflexiva, ADR-033/034 v1.2.0).

**Casos límite (importantes para κ)**:
- *Anotación que cae simultáneamente en ventana N1 (primeros 120s) Y ventana N4 (≤60s post-tutor)*: **N4 gana** (la regla del labeler: la señal "apropiación tras respuesta" es pedagógicamente más informativa que "lectura inicial"). Documentado en ADR-023.
- *Tests pasando a los 59 segundos post-tutor*: N3 (la ventana es estricta: ≥60s, no >60s. El labeler usa `delta >= TESTS_EJECUTADOS_N4_MIN_DELTA_SECONDS`).
- *Tests pasando a los 60.0 segundos exactos*: N4 (delta exactamente igual al umbral cuenta como ≥).
- *Anotación inmediatamente post-tutor (delta 0)*: N4. La ventana N4 es `0.0 <= delta < 60.0`.

### 1.4 Tabla resumen rápida

| Evento | Condición | N |
|---|---|---|
| `lectura_enunciado` | siempre | N1 |
| `anotacion_creada` | 0 ≤ delta_open < 120s, sin tutor ≤60s | N1 |
| `anotacion_creada` | 0 ≤ delta_tutor < 60s (gana sobre N1) | N4 |
| `anotacion_creada` | resto | N2 |
| `edicion_codigo` | `origin in {copied_from_tutor, pasted_external}` | N4 |
| `edicion_codigo` | resto | N2 |
| `codigo_ejecutado` | siempre | N3 |
| `tests_ejecutados` | `test_count_failed > 0` | N3 |
| `tests_ejecutados` | `failed == 0` y delta_tutor ≥ 60s | N4 |
| `tests_ejecutados` | resto (incluye sin contexto, sin tutor previo) | N3 |
| `prompt_enviado` | siempre | N4 |
| `tutor_respondio` | siempre | N4 |
| `intento_adverso_detectado` | siempre | N4 |
| `episodio_*` | siempre | meta (no etiquetar para Protocolo A) |

### 1.5 Formato del corpus para el etiquetador

Cada uno de los 200 eventos del Protocolo A se entrega como una **ficha**:

```yaml
event_id: ev_001
event_type: anotacion_creada
event_ts: 2026-04-15T14:22:33Z
seq: 17
payload:
  content: "[truncado para privacidad — primeros 40 chars]"
context:
  episodio_abierto_ts: 2026-04-15T14:20:50Z
  delta_desde_apertura_s: 103.0
  ultimo_tutor_respondio_ts: null
  delta_desde_ultimo_tutor_s: null
nivel_propuesto_por_etiquetador: ___
nota_libre: ___
```

El campo `content` se trunca a los primeros 40 caracteres por privacidad (consentimiento explícito no está cubierto por el piloto-1, ver `docs/limitaciones-declaradas.md`). Si la decisión depende del contenido completo, el etiquetador anota en `nota_libre` y la pre-calibración decidirá si se libera el contenido completo bajo NDA.

### 1.6 Protocolo de discrepancia (Protocolo A)

1. Cada etiquetador trabaja **independientemente** los 200 eventos. No ven la etiqueta de la función ni la del otro etiquetador.
2. Al finalizar, se computa κ de Cohen por **pares**: (etiquetador 1 vs función), (etiquetador 2 vs función), (etiquetador 1 vs etiquetador 2).
3. Se requiere κ ≥ 0,70 en **al menos 2 de los 3 pares**.
4. Si algún par cae entre 0,40 y 0,69: sesión de calibración conjunta sobre los eventos discrepantes + remuestreo de 50 nuevos eventos (segunda ronda).
5. Si κ < 0,40: reformular los criterios operacionales del manual y comenzar el Protocolo A desde cero.

---

## 2. Protocolo B — Etiquetado de episodios por apropiación

### 2.1 Qué se valida

La función pura `apps/classifier-service/src/classifier_service/services/tree.py::classify` con el `DEFAULT_REFERENCE_PROFILE`. Toma las 5 coherencias (ct_summary, ccd_mean, ccd_orphan_ratio, cii_stability, cii_evolution) y devuelve una de tres categorías de apropiación.

El Protocolo B pregunta: **dado un episodio cerrado en su totalidad, ¿llegarían dos docentes a la misma categoría de apropiación que la función?**

### 2.2 Las tres categorías (no son cinco)

ADR-046 estipula 50 episodios "distribuidos aproximadamente equilibrados entre las tres categorías esperadas (~16-17 por categoría)". Estas tres son **las únicas vigentes en paper y código**:

1. **`apropiacion_reflexiva`** — trabajo sostenido con coherencia en CT, CCD y CII. Patrón "epistemológicamente productivo" (Tabla 2 paper, §4.4).
2. **`apropiacion_superficial`** — engagement presente pero sin profundización. Verificación funcional sin verificación conceptual (Tabla 2 paper, §4.4).
3. **`delegacion_pasiva`** — prompts genéricos, aceptación acrítica, ausencia de verificación ejecutiva (Tabla 2 paper, §4.4). Internamente el código distingue dos sub-ramas (`extreme` con orphan ≥ 0,8 y `classic` con orphan ≥ 0,5 + CT bajo) pero ambas son `delegacion_pasiva` a nivel de la etiqueta principal.

**Nota documental**: el README del wrapper menciona cinco categorías (`autonomo, superficial, delegacion_pasiva, delegacion_extrema, regresivo`). **Ese listado no tiene respaldo en el paper ni en el código.** El paper-draft.md §4.4 (Tabla 2) define tres tipos; `tree.py` implementa tres ramas. El README es deuda documental a corregir y el "autonomo" que aparece en `ProgressionView.tsx:415` es solo un label de display para `apropiacion_reflexiva` (la CSS var es `--color-appropriation-reflexiva`).

### 2.3 Criterios operacionales por categoría

#### `apropiacion_reflexiva`

**Pregunta para el etiquetador**: ¿El estudiante mantuvo trabajo sostenido, con prompts que pidieron razones (no soluciones), verificación crítica, reformulación productiva, y capacidad implícita de explicación posterior?

**Evidencia observable a buscar en la cadena de eventos**:
- Prompts del estudiante con sustantivos abstractos ("por qué", "qué pasa si", "cuál es la diferencia entre"). Evitar prompts del tipo "dame", "mostrame", "escribime".
- Ediciones de código post-respuesta del tutor que reformulan lo que dijo el tutor en lugar de copiarlo (origen `student_typed` predominante post-tutor).
- Tests pasando con delta ≥60s respecto al último tutor (N4 reflexivo).
- Múltiples iteraciones código→tests con cambios sustantivos entre intentos.

**Patrón contraintuitivo a no confundir**: alta cantidad de mensajes con el tutor NO equivale a delegación. Si los mensajes son epistemológicamente productivos (preguntan por razones, no por soluciones), pueden ser apropiación reflexiva.

#### `apropiacion_superficial`

**Pregunta para el etiquetador**: ¿El estudiante mostró engagement (trabajó, hizo cosas, interactuó) pero sin profundizar?

**Evidencia observable**:
- Prompts más elaborados que en delegación pero todavía orientados a solución ("¿cómo hago para...", "¿podés mostrarme un ejemplo de...").
- Verificación ejecutiva presente (compila, tests parciales) pero sin reformulación tras fallos.
- Anotaciones post-tutor con baja densidad o reproducción casi literal.

**Categoría por default**: cuando los indicadores no cumplen los umbrales fuertes para reflexiva ni los patrones de delegación, el árbol devuelve apropiación superficial. El etiquetador humano debería tener el mismo sesgo: si dudás entre reflexiva y superficial, decantate por superficial; si dudás entre superficial y delegación, decantate por superficial.

#### `delegacion_pasiva`

**Pregunta para el etiquetador**: ¿El estudiante usó al tutor como oráculo? ¿Hay evidencia de que copió sin verificar, o de prompts genéricos seguidos de aceptación acrítica?

**Evidencia observable (sub-rama extreme — orphan ≥ 0,8)**:
- Predominio de ediciones de código sin prompts cercanos (huérfanas), incluyendo ediciones con `origin=copied_from_tutor` o `pasted_external`.
- Ausencia o casi-ausencia de anotaciones propias.
- Tests ejecutados sin reformulación entre fallos.

**Evidencia observable (sub-rama classic — orphan ≥ 0,5 + CT bajo)**:
- Algunas ediciones acompañadas de prompts, pero el ritmo temporal es errático: bloques densos seguidos de períodos largos sin actividad.
- Prompts genéricos del tipo "no funciona, ayudame" o transcripciones directas del enunciado.
- Anotaciones ausentes o triviales.

### 2.4 Formato del corpus para el etiquetador

Cada episodio del Protocolo B se entrega como un **dossier**:

```yaml
episode_id: ep_001
duracion_total_min: 47
n_eventos: 89
distribucion_niveles:
  N1: 0.12
  N2: 0.38
  N3: 0.21
  N4: 0.29
cadena_eventos:
  - { seq: 1, ts: ..., event_type: episodio_abierto }
  - { seq: 2, ts: ..., event_type: lectura_enunciado, ...payload truncado }
  - ...
  - { seq: 89, ts: ..., event_type: episodio_cerrado }
prompts_estudiante:  # extraídos del CTR, presentados juntos
  - "estoy leyendo el enunciado, parece que..."
  - "no entiendo cómo iterar"
  - ...
categoria_propuesta_por_etiquetador: ___
nota_libre: ___
```

Los prompts del estudiante se presentan completos al etiquetador (no truncados a 40 chars como en Protocolo A) porque la decisión de categoría depende fuertemente del contenido del discurso. Cubrir esto requiere **consentimiento informado** explícito de los estudiantes cuyo corpus se use, separado del consentimiento general del piloto. Documentar en `docs/limitaciones-declaradas.md`.

### 2.5 Protocolo de discrepancia (Protocolo B)

Idéntico al Protocolo A en estructura: pares de evaluadores, κ ≥ 0,70 en al menos 2 de 3 pares, sesión de calibración + remuestreo si cae entre 0,40 y 0,69, reformulación si κ < 0,40.

**Particularidad del Protocolo B**: las discrepancias entre etiquetadores sobre episodios son **pedagógicamente productivas** —incluso cuando no se alcanza κ ≥ 0,70 en primera ronda. La sesión de calibración sobre episodios discrepantes suele revelar matices del modelo que el árbol actual no captura, y esos matices son insumo directo para refinar el árbol post-defensa.

---

## 3. Pre-calibración interna (R3 del informeSoc.md)

**Antes de invitar a los dos docentes UTN al estudio intercoder formal**, dirección y co-dirección de tesis deben pilotar el manual sobre 20 eventos (de los 200 del Protocolo A) y 5 episodios (de los 50 del Protocolo B). Objetivo: detectar ambigüedades operacionales antes de invertir 25-30 h docentes.

### 3.1 Protocolo de pre-calibración

1. **Día 0**: dirección y co-dirección reciben este manual + 20 eventos del Protocolo A + 5 episodios del Protocolo B + el formato yaml de fichas/dossiers.
2. **Día 1-3**: cada uno etiqueta independientemente (no conversan).
3. **Día 4**: sesión conjunta de 90 minutos:
   - Comparar etiquetas.
   - Identificar discrepancias.
   - Para cada discrepancia: ¿es por ambigüedad del manual o por error de uno de los dos?
   - Si es por ambigüedad: añadir un caso límite a la sección §1.3 o §2.3 que la resuelva.
4. **Día 5**: re-etiquetar los 20 eventos y 5 episodios con el manual actualizado. Computar κ interno.
5. **Decisión de avance**:
   - κ_interno ≥ 0,70 → invitar a los dos docentes UTN.
   - κ_interno entre 0,40 y 0,70 → segunda iteración del manual + segunda ronda interna sobre 20 eventos nuevos.
   - κ_interno < 0,40 → revisar la operacionalización de fondo. **No invitar a los dos docentes hasta resolver**.

### 3.2 Por qué este paso es no-saltable

Estimación honesta: ejecutar el Protocolo A+B con dos docentes externos consume ~50 h docente acumuladas (25 por persona). Si el manual tiene ambigüedades operacionales, el κ va a salir bajo no por desacuerdo conceptual sino por uso inconsistente de criterios. La pre-calibración interna detecta esas ambigüedades **con el costo de 2 personas familiarizadas con el modelo trabajando 4-6 horas cada una** (~10 h vs. ~50 h docentes externas).

El cuello de botella académico de la tesis es la validación intercoder (A2 del `plan-accion.md`). Saltarse la pre-calibración por urgencia es la decisión más cara de las posibles.

---

## 4. Versionado de este manual

- **1.0.0** (2026-05-16) — borrador inicial derivado de `informeSoc.md` R1. Pre-calibración interna pendiente.
- *Pendiente 1.1.0* — incorporar casos límite descubiertos en pre-calibración interna.
- *Pendiente 1.2.0* — incorporar casos límite descubiertos en Protocolo A+B con docentes externos, si los hay.

Cada versión del manual debe quedar congelada como referencia del informe intercoder de su ronda. Las rondas con manuales distintos no son comparables entre sí.

---

## 5. Referencias

- ADR-046 — Umbral kappa intercoder a 0,70 + protocolo dual. Fuente del esquema A+B.
- ADR-020 — Event labeler como función pura derivada en lectura.
- ADR-023 — Override temporal de `anotacion_creada`. Define las ventanas N1=120s y N4=60s.
- ADR-033/034 — Regla N3/N4 para `tests_ejecutados` v1.2.0.
- `apps/classifier-service/src/classifier_service/services/event_labeler.py` — implementación de referencia del Protocolo A.
- `apps/classifier-service/src/classifier_service/services/tree.py` — implementación de referencia del Protocolo B.
- `paper-draft.md` §4.2 (Tabla 1, eventos N1-N4) y §4.4 (Tabla 2, tres tipos de apropiación).
- Landis, J. R., & Koch, G. G. (1977). The measurement of observer agreement for categorical data. *Biometrics*, 33(1), 159-174.
- `informeSoc.md` R1, R3 — recomendaciones P0 que motivan este manual.
- `docs/limitaciones-declaradas.md` — consentimiento informado para corpus textual completo (Protocolo B).
