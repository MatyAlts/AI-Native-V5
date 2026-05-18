# Cambios grandes al código — segunda iteración

Cambios de alto impacto que tocan semántica del sistema, requieren ADR, y/o coordinación con análisis empírico. Cada uno explicita el gap conceptual entre la tesis vigente (v3.4) y el código, propone rediseño con detalle, declara impactos sobre reproducibilidad y costos del piloto si aplica, y sugiere timing.

Esta iteración continúa la numeración de la primera ronda. La iter 1 cerró parcialmente G3 (fase A — preprocesamiento), G4 (etiquetador N1-N4) y G5 (registro externo Ed25519), todos documentados en `docs/RESUMEN-EJECUTIVO-2026-04-27.md` con sus ADRs (019, 020, 021). Adicionalmente cerró G2 mínimo (CII longitudinal slope, ADR-018) que el RESUMEN-EJECUTIVO no menciona pero está en el código. Quedan abiertos:

- G1 (CCD semántica con embeddings)
- G3 fase B (postprocesamiento + `socratic_compliance`)
- G6 (desacoplamiento instrumento-intervención)
- G7 completo (dashboard docente con alertas predictivas; el MVP está parcialmente en ADR-022)

Empiezo la numeración nueva en G8. Línea editorial: **modelo híbrido**. Cada cambio se justifica como cierre de gap declarado en la agenda confirmatoria del Capítulo 20 o como integridad técnica del sistema.

---

## G8 — Override semántico de `anotacion_creada` en el labeler

### Problema raíz

`apps/classifier-service/src/classifier_service/services/event_labeler.py:41` etiqueta `anotacion_creada` como N2 fijo. La Tabla 4.1 de la tesis vigente asigna las anotaciones a **N1** ("notas tomadas; reformulación verbal en el asistente") cuando ocurren durante la lectura del enunciado, y a **N4** ("apropiación de argumento: reproducción razonada de una explicación del asistente en producción posterior propia") cuando ocurren tras una respuesta del tutor.

El docstring del labeler reconoce el gap y lo declara como decisión de implementación para no introducir embeddings en v1.0.0. Pero el efecto es que `time_in_level` produce un sesgo sistemático: sub-reporta N1 y N4, sobre-reporta N2. Esa es exactamente la métrica que cierra el gap declarado en 15.6 ("la operacionalización de CT v1.0.0 no implementa en esta versión la proporción de tiempo por nivel N1–N4 por dependencia de la instrumentación completa de eventos") — pero al cerrarlo introduce un sesgo nuevo no declarado.

### Propuesta de rediseño

Tres niveles de fix posibles, en orden de complejidad creciente:

**G8a (heurístico simple):** override por **posición temporal en el episodio**. Si la anotación ocurre dentro de los primeros N segundos desde `episodio_abierto` (umbral configurable, default 120s), etiquetar N1; si ocurre dentro de los M segundos posteriores a un `tutor_respondio`, etiquetar N4; en todos los demás casos, mantener N2. ~30 LOC + tests.

**G8b (heurístico léxico):** además de la posición temporal, aplicar reglas léxicas sobre el contenido de la anotación. Patrones tipo "no entendí…", "leyendo…", "la consigna pide…" → N1; patrones tipo "ahora me doy cuenta…", "siguiendo lo que el tutor explicó…", "reescribo con el método de…" → N4. ~80 LOC + corpus + tests κ contra juicio docente.

**G8c (semántico vía embeddings):** enviar la anotación + el contexto inmediato al embedding provider del `ai-gateway` y clasificar contra prototipos de N1/N2/N4. Costo computacional alto, agenda Eje B. ~200 LOC + integración con el budget tracking del ai-gateway.

**Recomendación:** G8a antes de defensa (cierra el sesgo más obvio sin introducir dependencias nuevas), G8b post-defensa con validación κ, G8c como agenda Eje B.

### Impacto

- **LOC:** 30 (G8a) / 80 (G8b) / 200 (G8c).
- **Reproducibilidad:** preservada **si se bumpea `LABELER_VERSION`** (1.0.0 → 1.1.0). Las clasificaciones existentes siguen reproducibles bit-a-bit con la versión anterior; las nuevas usan la versión nueva. ADR-020 ya cubre esa convención ("bumpear re-etiqueta históricos sin tocar el CTR").
- **Coordinación con piloto:** ninguna si el bump es honesto y los reportes empíricos declaran qué versión se usó (principio P6 del documento maestro de la tesis 21.4).
- **ADR asociado:** **ADR-023** "Override semántico de anotacion_creada en el labeler N1-N4" (extiende ADR-020).

### Riesgo y mitigaciones

- Riesgo G8a: el umbral temporal (120s, M=N a definir) es arbitrario. Mitigación: documentar el umbral en el ADR; reportar sensibilidad en el análisis empírico.
- Riesgo G8b: falsos positivos por reglas léxicas. Mitigación: validación κ contra juicio docente sobre subset etiquetado a mano.

### Acción paralela en tesis

Ver `03-cambios-tesis.md` → T14 (precisar en 4.3.1 / 15.6 que la primera versión del `time_in_level` usa override simplificado y declarar la migración como Eje B).

### Timing sugerido

**G8a antes de defensa.** El sesgo `anotacion_creada → N2 fijo` es lo suficientemente grueso como para distorsionar reportes empíricos del piloto si no se cierra. G8b/G8c quedan en agenda.

---

## G9 — Activar `prompt_kind` reflexivo en runtime

### Problema raíz

(Persistente desde iter 1, no resuelto.) `apps/classifier-service/src/classifier_service/services/ccd.py:52,62` busca `prompt_kind == "reflexion"` para identificar verbalización reflexiva por prompt. Pero ni el contract Pydantic admite `"reflexion"` como valor de `PromptKind` (admite cinco valores, ninguno es ése), ni el tutor-service lo emite (línea 176 hardcodea `"solicitud_directa"`). En consecuencia, en runtime CCD nunca activa la rama de prompts reflexivos: la única fuente activa de verbalización es `anotacion_creada`.

La 15.6 de la tesis menciona "prompt con intencionalidad reflexiva" como una de las dos fuentes de verbalización contempladas por CCD v1.0.0. La discrepancia entre lo descrito y lo implementado es lo más visible que queda entre 15.6 y el clasificador real.

### Propuesta de rediseño

Tres pasos:

1. **Alinear el contract.** Decidir el conjunto canónico de `PromptKind`. Opción de mínimo cambio: mantener los cinco valores existentes y agregar `"reflexion"` como sexto valor. Definir el subconjunto "reflexivo" para CCD: `{epistemologica, validacion, reflexion}` versus el subconjunto "acción": `{solicitud_directa, comparativa, aclaracion_enunciado}`.

2. **Clasificar el `prompt_kind` en el momento de la emisión** desde `tutor-service`. Dos opciones:
   - **2a (preferida v1.1.0):** reglas heurísticas livianas en tutor-service. Patrones tipo "no entendí…", "creo que…", "me confunde…" → `reflexion`. Patrones tipo "dame la solución…", "escribime…" → `solicitud_directa`. Patrones tipo "vs", "diferencia entre…" → `comparativa`. Default: `solicitud_directa`. ~80 LOC + tests determinísticos.
   - **2b (agenda Eje B):** clasificador ML sobre corpus etiquetado de prompts del piloto.

3. **Adaptar CCD para leer el conjunto canónico.** Reemplazar `prompt_kind != "reflexion"` por `prompt_kind in ACCION_KINDS` y `prompt_kind == "reflexion"` por `prompt_kind in REFLEXION_KINDS`.

### Impacto

- **LOC:** ~150 sumados (50 reglas + 30 contracts + 30 classifier + 40 tests).
- **Reproducibilidad:** preservada si la opción 2a es determinista. Eventos previos siguen válidos: `solicitud_directa` sigue siendo valor admitido. Eventos nuevos clasifican mejor.
- **Coordinación con piloto:** si el cambio se aplica mid-cohort, los episodios anteriores quedan con todos los prompts marcados como `solicitud_directa`. Aplicar al cierre del cuatrimestre o documentar separadamente. Conviene reclasificar todo el corpus con el `classifier_config_hash` nuevo (ADR-010 cubre append-only).
- **ADR asociado:** **ADR-024** "Clasificación heurística de `prompt_kind` y mapeo a verbalización en CCD".

### Riesgo y mitigaciones

- Riesgo: las reglas heurísticas pueden producir falsos positivos. Mitigación: validación κ de Cohen sobre subset etiquetado, mismo protocolo que el Clasificador N4 (Capítulo 14).
- Riesgo: agregar valor al enum puede romper consumers TS con `match` exhaustivo. Mitigación: cambio backwards-compatible (agregar al enum, no quitar valores).

### Acción paralela en tesis

Ver `03-cambios-tesis.md` → T15 (precisar en 15.6 que en v1.0.0 la rama "prompt reflexivo" no se materializa, y que la activación es scope Eje B).

### Timing sugerido

**Agenda confirmatoria.** No aplicar antes de defensa. La tesis ya lo declara honestamente como gap si se acepta T15.

---

## G10 — Decidir el destino de `EpisodioAbandonado`: emitir o eliminar

### Problema raíz

`EpisodioAbandonado` está declarado en `packages/contracts/src/platform_contracts/ctr/events.py:68-75` con payload (`reason`, `last_activity_seconds_ago`). El labeler (`event_labeler.py:39`) lo categoriza como `meta`. Sin embargo, ningún servicio backend ni frontend lo emite (verificado con grep). El TS lo omite.

La Sección 7.2 de la tesis vigente lo lista entre los 8 instrumentados v1.0.0. **Esa afirmación es operacionalmente falsa**: en runtime no se emite. Es la asimetría más visible que queda entre la tesis y el código.

### Decisión bifurcada

**Opción A — emitir efectivamente.** Implementar la emisión desde web-student con dos triggers:

1. `beforeunload` del navegador: si hay episodio abierto y el usuario cierra la pestaña / navega afuera, emitir con `reason="beforeunload"`.
2. Worker de timeout en tutor-service: tarea periódica que detecta sesiones inactivas (umbral N minutos, default 30); emite con `reason="timeout"`.

LOC: ~80 frontend (hook beforeunload + endpoint POST con reintento) + ~50 backend (método en tutor_core.py replicando el patrón de `record_lectura_enunciado` + worker). Cierra T17-A en tesis.

**Opción B — eliminar del contract y declarar en tesis.** Quitar la clase `EpisodioAbandonado` y su payload del Pydantic; quitar de `__init__.py`. Renumerar la tesis 7.2 a 7 instrumentados (+ `lectura_enunciado` y `intento_adverso_detectado` que sí se emiten = 9 totales reales en runtime, distribución distinta). Cierra T17-B en tesis.

### Impacto

- **Opción A:** ~130 LOC, requiere coordinación con piloto (si se aplica mid-cohort, episodios anteriores no tienen el evento — distorsiona análisis longitudinal). **ADR asociado:** **ADR-025** "Política de cierre de episodios y emisión de `episodio_abandonado`" (triggers, umbrales, idempotencia).
- **Opción B:** ~10 LOC + parche de tesis. **Sin ADR**, es vuelta atrás.

### Recomendación

**Opción A si la defensa está a más de 6 semanas; opción B si está a menos.** El argumento metodológico para A es que `episodio_abandonado` es informativo: distingue cierre intencional de cierre por inactividad, lo que en CCD y en el árbol de apropiación es relevante. La opción B preserva el rigor a costa de ambición.

### Riesgo y mitigaciones

- Riesgo A: emisión doble si tanto `beforeunload` como timeout server detectan abandono. Mitigación: idempotencia por `event_uuid` + estado de sesión.
- Riesgo A: `beforeunload` no garantiza emisión en mobile. Mitigación: el timeout server cubre el caso base.

### Acción paralela en tesis

Ver `03-cambios-tesis.md` → T17 (variante A o B según decisión).

### Timing sugerido

**Antes de defensa, decisión obligatoria** (sin importar cuál de A o B). La tesis no debe mantener una afirmación operacional falsa sobre v1.0.0.

---

## G11 — Implementar el botón "Insertar código del tutor" en web-student

### Problema raíz

F6 (iter 1) agregó el campo `origin: Literal["student_typed", "copied_from_tutor", "pasted_external"]` al payload de `edicion_codigo`. El backend lo recibe y persiste. El `event_labeler` (G4) lo lee para hacer el override `edicion_codigo → N4` cuando origin ∈ {`copied_from_tutor`, `pasted_external`}.

Sin embargo, **el frontend (`apps/web-student/src/components/CodeEditor.tsx`) solo emite `student_typed | pasted_external`**. La rama `copied_from_tutor` requiere un botón "Insertar código" en el panel del tutor que aún no está implementado. Verificación: `grep -rn "copied_from_tutor" apps/web-student` → solo aparece en el type literal de TypeScript, no como string emitido.

Resultado: el override del labeler captura `pasted_external` (estudiante pegó algo de afuera) pero no el caso pedagógicamente más informativo: el estudiante adoptó deliberadamente un bloque de código sugerido por el tutor.

### Propuesta de rediseño

En el panel de chat del tutor, cuando la respuesta incluye un bloque de código (detectable por triple-backtick), añadir junto al bloque un botón "Insertar en el editor". Al hacer click:

1. El componente parent del editor recibe el bloque + flag de origen.
2. El editor inserta el código en la posición del cursor o reemplaza la selección.
3. La emisión `edicion_codigo` resultante lleva `origin: "copied_from_tutor"`.

Parser: regex simple sobre `^```/m` en v1; no hace falta parser markdown completo. ~120 LOC (parser + UI button + propagación del flag al hook que emite el evento).

### Impacto

- **LOC:** ~120.
- **Reproducibilidad:** preservada. El campo es opcional, retro-compatible. Al activarse el botón, los nuevos eventos de `copied_from_tutor` empiezan a alimentar el override del labeler. Eventos previos siguen reproducibles bit-a-bit.
- **Coordinación con piloto:** mid-cohort introduce sesgo (estudiantes que recibieron el botón vs los que no). No mid-cohort. Aplicar entre cuatrimestres.
- **ADR asociado:** **ADR-026** "Botón 'Insertar código del tutor' en web-student y consumo de `origin` en el labeler".

### Riesgo y mitigaciones

- Riesgo: el botón cambia la economía de la interacción — ofrece un canal "barato" para tomar código del tutor, lo que puede inducir delegación pasiva como variable confound. Mitigación: documentar como variable independiente del estudio; el labeler detecta el efecto y los reportes lo separan. Coherente con la tesis 11.6 (confound intervención-medición).

### Acción paralela en tesis

Ver `03-cambios-tesis.md` → T16 (precisar en 19.5 que el campo `origin` está parcialmente operacional).

### Timing sugerido

**Agenda confirmatoria, post-defensa.** Toca la UX del estudiante y disrumpe condición experimental.

---

## G12 — Corrección documental del HTML comment del prompt como bump v1.0.1

### Problema raíz

(Reagendado desde F23 tras verificar que `compute_content_hash` hashea el archivo entero, incluyendo el comment.)

El HTML comment al pie de `ai-native-prompts/prompts/tutor/v1.0.0/system.md` mapea GP3 al Principio 3 ("dejar equivocarse") cuando ese principio cubre semánticamente GP4 (estimulación de la verificación ejecutiva). El mismo comment también mapea GP4 al mismo Principio 3, asignando el mismo principio a dos guardarraíles distintos. La cuenta declarada es 4/10; la cuenta correcta es **3/10** (GP1, GP2, GP4).

### Propuesta

Crear `ai-native-prompts/prompts/tutor/v1.0.1/system.md` con:

- Texto del prompt **idéntico** a v1.0.0 (no cambia comportamiento del tutor; preserva la base experimental del piloto).
- HTML comment corregido: GP3 movido a "sin cobertura explícita en v1.0.0", cuenta 3/10.
- Nuevo `manifest.yaml` con hash recomputado.

Bump PATCH (v1.0.0 → v1.0.1) según tesis 7.4: "corrección de redacción, refinamiento de instrucciones sin cambio sustantivo". Mantener v1.0.0 accesible para reproducibilidad histórica del piloto.

### Impacto

- **LOC:** copia del archivo (~70 LOC) + edición de ~6 LOC en el comment + nuevo manifest.
- **Reproducibilidad:** episodios v1.0.0 siguen reproducibles; episodios nuevos apuntan a v1.0.1.
- **Coordinación con piloto:** mid-cohort sería problemático **solo** si la documentación interna afecta el flujo (no afecta — el HTML comment es invisible al modelo). Por rigor metodológico, conviene aplicar entre cuatrimestres.
- **ADR asociado:** ninguno nuevo. Cubierto por ADR-009 y la política de bump de tesis 7.4.

### Riesgo

Bajo. El comportamiento del tutor no cambia (por construcción del bump). Único riesgo: que el comité interprete el bump como sustantivo cuando es solo documental.

### Acción paralela en tesis

Ver `03-cambios-tesis.md` → T18 (cuenta 4/10 → 3/10 en 8.4.1).

### Timing sugerido

**Antes de defensa, idealmente al cierre del cuatrimestre actual.** Si la defensa se acerca y no hay margen, T18 puede aplicarse sola con nota a pie aclarando que el HTML comment del archivo del prompt vigente está desactualizado y se corrige post-defensa. La consideración importante: **o se cambia ambas (T18 + G12), o ninguna**. No mezclar parche tesis sin parche código.

---

## G13 — Postprocesamiento de la respuesta del tutor (G3 fase B)

### Problema raíz

G3 cerró su fase A en iter 1: detección heurística regex de patrones adversos en el prompt del estudiante, antes del envío al LLM, con emisión de `intento_adverso_detectado`. ADR-019 documenta esto como "Fase A SOLO" y declara que la fase B (postprocesamiento de la respuesta del tutor + cálculo de `socratic_compliance`) queda fuera de scope de v1.x.

El RESUMEN-EJECUTIVO confirma esa decisión: "G3 Fase B — postprocesamiento + `socratic_compliance`: 'Un score mal calculado es peor que ninguno.' El campo queda como `None` en eventos hasta que la calibración con docentes valide el cálculo."

La tesis vigente (Sección 8.5.1) describe el postprocesamiento como parte del diseño del tutor, y la 19.5 lo declara como gap. No hay incoherencia en la tesis — el modelo híbrido funciona — pero el campo `socratic_compliance: float | None` en `TutorRespondioPayload` queda permanentemente `None` en runtime y eso es señal explícita de gap.

### Propuesta de rediseño

Implementar `apps/tutor-service/src/tutor_service/services/postprocess.py` con tres módulos:

1. **Detector de patrones en la respuesta del tutor.** Regex análoga a `guardrails.py` pero sobre el output, no el input. Detecta:
   - Bloque de código completo en respuesta a un prompt de tipo "dame la solución" (penaliza compliance).
   - Respuesta sin pregunta al final (penaliza si el prompt era reflexivo).
   - Off-topic (la respuesta no menciona conceptos del prompt).

2. **Cálculo de `socratic_compliance`.** Score [0, 1] derivado de las penalizaciones del detector. Documentar el cálculo en el ADR de modo que sea reproducible bit-a-bit (mismo patrón que `classifier_config_hash` y `guardrails_corpus_hash`).

3. **Inclusión en el evento `tutor_respondio`.** Los campos ya están en el contract (F8 iter 1 los hizo opcionales): `socratic_compliance: float`, `violations: list[str]`. Llenarlos cuando la fase B esté activa.

### Impacto

- **LOC:** ~250 (detector + score + tests + corpus de regex).
- **Reproducibilidad:** preservada. Las heurísticas son deterministas. `prompt_system_hash` no cambia. Eventos previos con `socratic_compliance=None` siguen válidos.
- **Coordinación con piloto:** introducir el postprocesamiento mid-cohort no cambia las respuestas del tutor (el postprocesamiento es side-channel, no modifica la respuesta entregada al estudiante). Sí cambia las clasificaciones del clasificador si éste empieza a leer `socratic_compliance` — eso sí requiere bumpear `classifier_config_hash`.
- **ADR asociado:** **ADR-027** "G3 Fase B — postprocesamiento de respuesta del tutor y cálculo de `socratic_compliance`".

### Riesgo y mitigaciones

- Falsos positivos: respuesta legítima penalizada como no-socrática. Mitigación: el campo no bloquea ni modifica la respuesta; es señal evaluativa. Validación κ contra juicio docente sobre subset.
- "Un score mal calculado es peor que ninguno" (RESUMEN-EJECUTIVO): la fase B exige más rigor que la fase A. Mitigación: bloquear el wireado del campo en el clasificador (no afecta el árbol de decisión de apropiación) hasta que la validación κ esté hecha. Mientras tanto, `socratic_compliance` se persiste pero solo se reporta separadamente.

### Acción paralela en tesis

No requiere parche; la tesis 8.5.1 / 19.5 ya describe el plan. Si se implementa, mencionar en 17.8 los resultados de la fase B al cierre del cuatrimestre.

### Timing sugerido

**Agenda confirmatoria, post-defensa. Prioridad alta previa a despliegue institucional más amplio que el pilotaje de investigación** (consistente con tesis 20.5.1 Eje C).

---

## G14 — CCD con embeddings semánticos (Eje B, G1 original)

### Problema raíz

(Heredado del audi1.md original como G1; sigue vigente.) `apps/classifier-service/src/classifier_service/services/ccd.py` opera por proximidad temporal de 2 minutos entre acciones y verbalizaciones. La tesis 15.3 caracteriza CCD como "similitud semántica entre explicaciones en chat y contenido del código (mediante técnicas de embeddings)", y la 15.6 lo declara como gap explícito de v1.0.0 ("La operacionalización temporal es computacionalmente liviana, determinista, reproducible bit-a-bit y libre de dependencias externas; captura una señal importante del proceso pero no su contenido").

Un estudiante que escribe "hola" en una nota cada vez que ejecuta código sacaría CCD altísimo con la implementación actual.

### Propuesta de rediseño

Pipeline propuesto (alineado con audi1.md original):

1. **Extracción de pares acción ↔ discurso.** Para cada `edicion_codigo` o `codigo_ejecutado`, buscar los N `prompt_enviado`, `tutor_respondio` y `anotacion_creada` en una ventana de 5 min alrededor.

2. **Embeddings.**
   - Código: embedding del diff o del snapshot completo. Usar `text-embedding-3-small` u offline (`fastembed` con `BAAI/bge-small-en` o equivalente español-friendly).
   - Discurso: embedding del texto concatenado.

3. **Score de alineación por par.** Coseno normalizado a [0, 1].

4. **Agregación a episodio.** `ccd_mean` (con semántica real), `ccd_orphan_ratio` con umbral de score < 0.30 (no solo "ausencia"), y un tercer indicador `ccd_contradiction_ratio` (score < 0.15 con discurso vecino presente — pedagógicamente rico, captura "hablaste de X, escribiste Y").

### Impacto

- **LOC:** ~400 (pipeline + integración con `ai-gateway` para embeddings + tests + golden fixtures).
- **Dependencias nuevas:** acceso a embedding provider. Dos opciones documentadas en audi1.md G1: depender del `ai-gateway` (agregar endpoint `/embeddings`), o servicio local con `sentence-transformers`/`fastembed` (~500MB pesos en CPU).
- **Reproducibilidad bit-a-bit:** comprometida solamente si el modelo cambia. Mitigación: pin exacto del modelo + versión, incluirlo en `classifier_config_hash` (ya es `json.dumps({tree_version, profile})`, agregar `embedding_model`). El append-only con `is_current=false` (ADR-010) cubre la reclasificación.
- **Costo del piloto:** ~$0.80 USD total (500 estudiantes × 20 episodios × 10 pares × 2 embeddings × ~200 tokens × $0.00002/1k tokens). Negligible.
- **ADR asociado:** **ADR-017** (libre, ya estaba reservado en el audi1.md original) "CCD con embeddings semánticos (supersedes operacionalización temporal v1)".

### Riesgo y mitigaciones

- Cambio de modelo upstream invalida hashes. Mitigación: pin de versión + bump explícito + reclasificación append-only.
- Latencia: ~100ms/embedding en CPU local. Mitigación: batch processing diferido, no bloquea el cierre del episodio.

### Acción paralela en tesis

No requiere parche; la tesis 15.6 declara la migración como Eje B explícitamente.

### Timing sugerido

**Agenda confirmatoria, post-defensa.** Defender con la operacionalización temporal v1.0.0 + 15.6 declarada honestamente es coherente con el modelo híbrido.

---

## G15 — Desacoplamiento instrumento-intervención (Eje agenda confirmatoria, G6 original)

### Problema raíz

(Heredado del audi1.md como G6; sigue vigente y en agenda.) La tesis 11.6 reconoce el confound intervención-medición: el tutor socrático y el CTR están acoplados arquitectónicamente (ambos viven en el mismo plano "pedagógico-evaluativo"), por lo que cualquier estudio cuasi-experimental sobre el efecto del tutor también está midiendo el efecto del CTR. La 20.5.1 lo declara explícitamente como agenda futura: "se propone el desacoplamiento arquitectónico entre el tutor como mediador pedagógico y el CTR como instrumento de registro... habilita condiciones control donde la mediación IA ocurra externa al sistema evaluativo".

En código, esto significa refactor: introducir una capa "instrumento-only" del CTR que pueda registrar eventos generados por interacciones con LLMs externos al sistema (Claude estándar, ChatGPT) en condiciones control, sin que el `tutor-service` esté en el medio.

### Propuesta de rediseño

Refactor de ~1500 LOC distribuido entre:

1. **Capa "ingest" del CTR independiente del tutor**: endpoint `POST /api/v1/ctr/external-event` que acepta eventos generados por una extensión de navegador o un proxy externo, con schema discriminado y validación de origen.

2. **Extensión de Chrome/Firefox** que captura interacciones con LLMs externos y las traduce al formato CTR. Esto es el componente más nuevo y desafiante: ~600-800 LOC.

3. **Schema de "condition_control" en `episodio_abierto`** que distingue tres condiciones: `tutor_socratico_uns_native`, `llm_externo_capturado`, `sin_llm`. El árbol de clasificación lee esta condición para no aplicar reglas de delegación cuando la mediación es externa pero el estudiante explícitamente declaró usarla.

### Impacto

- **LOC:** ~1500 (servicios) + ~700 (extensión).
- **Reproducibilidad:** la cadena del CTR sigue siendo bit-a-bit dentro de cada condición. Cross-condición no es comparable y los reportes deben separarlos.
- **Costo del piloto:** alto. Requiere reclutamiento adicional, capacitación en la extensión, gestión de consentimiento ampliado para captura de interacciones con LLMs externos. **No es viable antes de defensa.**
- **ADR asociado:** **ADR-028** "Desacoplamiento instrumento-intervención: condiciones control con LLM externo capturado".

### Acción paralela en tesis

No requiere parche; la tesis 20.5.1 lo declara como agenda. Si se implementa, mencionar la condición de captura externa en 11.6 al revisitar el confound.

### Timing sugerido

**Agenda confirmatoria, post-defensa. Idealmente como parte del estudio confirmatorio multisite del Capítulo 20.**

---

## Tabla resumen + ruta mínima para defensa

| ID | Título corto | LOC | Riesgo | Eje agenda | ADR | Timing |
|----|--------------|-----|--------|------------|-----|--------|
| G8a | Override temporal de `anotacion_creada` en labeler | 30 | Bajo | (cierra v1) | 023 | Antes de defensa |
| G9 | Activar `prompt_kind` reflexivo en runtime | ~150 | Medio | Eje B | 024 | Agenda confirmatoria |
| G10 | `EpisodioAbandonado`: emitir o eliminar | A: ~130 / B: ~10 | Medio (A) / Nulo (B) | Eje A | 025 (si A) | Antes de defensa (decisión) |
| G11 | Botón "Insertar código del tutor" + consumo `origin` | ~120 | Medio | Eje A/B | 026 | Agenda confirmatoria |
| G12 | PATCH v1.0.1 documental (corrección HTML comment) | ~80 | Bajo | — | (cubre 009) | Antes de defensa o no-aplicar |
| G13 | G3 Fase B: postprocesamiento + `socratic_compliance` | ~250 | Medio | Eje C | 027 | Agenda confirmatoria |
| G14 | CCD con embeddings semánticos (G1 original) | ~400 | Medio | Eje B | 017 | Agenda confirmatoria |
| G15 | Desacoplamiento instrumento-intervención (G6 original) | ~2200 | Alto | Eje B + 11.6 | 028 | Post-piloto-1 |

### Ruta mínima para defensa

Lo que **sí o sí** hay que hacer:

- Todos los chicos del 01-fixes (F14, F15, F16, F17, F18, F19, F20, F21, F22).
- **G10 — decisión binaria.** O se emite `episodio_abandonado` (opción A) o se reconoce explícitamente como agenda en la tesis (opción B). En cualquier caso, la tesis no debe seguir afirmando instrumentación falsa.
- **G8a — override temporal de `anotacion_creada`.** Cierra el sesgo sistemático más visible introducido por la implementación de G4.
- (Recomendado pero opcional) **G12 — bump documental v1.0.1** del prompt si se acepta T18 en la tesis.

Lo que **se declara como agenda confirmatoria** y se documenta en 20.5.1 Ejes A/B/C:

- G9 (Eje B), G11 (Ejes A/B), G13 (Eje C), G14 (Eje B), G15 (Eje B + 11.6).

### Lectura honesta de cuán cerca está la defensa

La iter 1 cerró tres de los cambios grandes que en la auditoría del repo anterior estaban en agenda confirmatoria: G3 fase A (detección preprocesamiento adversa), G4 (etiquetador N1-N4), G5 (registro externo Ed25519). Adicionalmente G2 mínimo (CII longitudinal). Esto es trabajo sustantivo: cierra los Ejes A, C y D parcialmente, y lleva a cumplir las promesas más fuertes de la Sección 7.3, 8.5.1 y 4.3 / 6.4 de la tesis.

Lo que queda son los gaps más finos y los grandes que el modelo híbrido legítimamente difiere a Eje B (CCD semántico, prompt_kind reflexivo, dashboard predictivo completo) y a post-piloto-1 (desacoplamiento). Tras aplicar los chicos y G8a + G10, la tesis y el código quedan alineados al nivel exigible para defensa.

Mi lectura: **el sistema está al ~90% de listo para defensa**. La diferencia más fuerte respecto a la auditoría del repo anterior (que estimaba 85%) es que G3 fase A, G4, G5 y G2 mínimo ya están adentro con tests y ADRs serios, lo cual eleva sustancialmente el peso técnico del trabajo.
