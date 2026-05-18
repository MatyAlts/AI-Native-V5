# Parches a la tesis — segunda iteración

Cambios al **texto de la tesis** (no al código) que cierran inconsistencias entre lo afirmado en la versión vigente (v3.4) y lo efectivamente implementado tras `iter 1` y `iter 2` de auditoría.

Cada parche está numerado `Tnn` y ata explícitamente con su contraparte de código (`Gnn` del audi1.md / audi2.md o ADR específico). Mantienen la línea editorial **modelo híbrido honesto**: la tesis preserva sus definiciones aspiracionales (Capítulos 4, 7, 8, 15) y declara honestamente la cobertura v1.0.0 / v1.1.0 (4.3.1, 7.2, 8.4.1, 15.6, 17.3, 19.5, 20.5.1).

Numeración: T1–T13 reservadas para parches de iter 1 (no documentados acá; quedaron en `docs/RESUMEN-EJECUTIVO-2026-04-27.md`). Iter 2 arranca en T14.

**Importante**: cada parche incluye una **propuesta de redacción borrador**. Como este documento NO tiene acceso al texto literal del manuscrito doctoral, los borradores son **andamios** — el doctorando los refina contra el texto real preservando estilo y precisión académica. Las **referencias de sección, ADR y rutas de código son verificables y deben citarse exactamente** en el manuscrito final.

---

## T14 — Precisar override v1.1.0 de `anotacion_creada` en 4.3.1 / 15.6 + declarar G8b/G8c como Eje B

**Coordinado con:** G8a (audi2.md) → [ADR-023](docs/adr/023-override-temporal-anotacion-creada.md) → bump `LABELER_VERSION` 1.0.0 → 1.1.0 (commit de iter 2, 2026-04-29).

### Estado pre-parche

La tesis 4.3.1 (cobertura v1.0.0 del componente C3.2 — etiquetador) y 15.6 (gap declarado de `time_in_level`) afirman que la primera versión etiqueta `anotacion_creada` como **N2 fijo** por no requerir clasificación semántica del contenido. La 17.3 documenta el sesgo sistemático introducido (sub-reporta-N1, sobre-reporta-N2). La 15.6 declara la migración a override por contenido como **agenda Eje B post-defensa**.

### Problema

Tras iter 2 (commit 2026-04-29), el labeler **ya no etiqueta N2 fijo**: aplica un **override por posición temporal** ([ADR-023](docs/adr/023-override-temporal-anotacion-creada.md)) que aproxima la Tabla 4.1 sin embeddings. Anotación dentro de los primeros 120s del episodio → N1; dentro de 60s post-`tutor_respondio` → N4; otros casos → N2 (fallback v1.0.0). El bump `LABELER_VERSION` 1.0.0 → 1.1.0 cubre la convención (ADR-020). Si la tesis sigue diciendo "N2 fijo", afirma una operacionalización que el código ya superó.

### Propuesta de redacción (4.3.1 — fragmento sobre etiquetador)

> El etiquetador de eventos N1–N4 (componente C3.2) opera como función pura derivada en lectura sobre el CTR (ADR-020), sin almacenar el `n_level` en el payload del evento. La versión vigente del piloto es la **v1.1.0** (`LABELER_VERSION="1.1.0"`, ADR-023), que extiende v1.0.0 con un override temporal para `anotacion_creada`: la asignación N2 fija de v1.0.0 — declarada explícitamente como **decisión de implementación, no como verdad académica derivada de la Tabla 4.1** — fue reemplazada por una heurística posicional liviana que aproxima la asignación de la Tabla 4.1 (N1 para anotaciones durante la lectura del enunciado; N4 para anotaciones tras una respuesta del tutor) usando proximidad temporal a `episodio_abierto` y al último `tutor_respondio` respectivamente. La heurística NO inspecciona el contenido de la anotación. La operacionalización semántica completa (clasificación del contenido vía embeddings o reglas léxicas validadas con κ docente) queda como agenda Eje B (ver 20.5.1 y G8b/G8c en `audi2.md`).

### Propuesta de redacción (15.6 — fragmento sobre `time_in_level`)

> La operacionalización de la métrica de proporción de tiempo por nivel (`time_in_level`) en v1.0.0 estaba constreñida por la asignación N2 fija de `anotacion_creada` (decisión de implementación documentada en 4.3.1). v1.1.0 cierra parcialmente esa restricción mediante el override temporal (ADR-023), reduciendo el sesgo sistemático sub-reporta-N1 / sobre-reporta-N2 documentado en 17.3 sin introducir dependencias externas (embeddings, corpus etiquetado). La operacionalización plena por contenido — distinguir, dentro del subconjunto de anotaciones que caen fuera de las dos ventanas temporales del override, las que reflejan reformulación del enunciado (N1) frente a apropiación del aporte del tutor (N4) — requiere clasificación semántica y queda diferida a Eje B post-defensa, donde se calibrará con κ docente sobre subset etiquetado del corpus del piloto.

### Propuesta de actualización (17.3 — sección sobre sesgo del labeler)

Agregar al final de la sección actual:

> **Cierre parcial en v1.1.0**: el override temporal introducido por ADR-023 cierra el caso más obvio del sesgo sub-reporta-N1: anotaciones en los primeros 120s del episodio (típicamente "leyendo el enunciado…") se etiquetan N1. Análogamente, el caso N4-vía-apropiación queda cubierto para anotaciones <60s post-`tutor_respondio`. El sesgo residual se concentra en anotaciones tardías que la Tabla 4.1 asignaría a N1 (relectura del enunciado mid-episodio) o a N4 (apropiación con latencia >60s tras la respuesta) — éstas siguen cayendo a N2 por fallback. Cuantificar el sesgo residual contra clasificación manual de un subset es objetivo declarado del análisis empírico del piloto-1 (ver 19.5).

### Coordinación con código

- ADR-023 — decisión, opt-in via `EpisodeContext`, regla de desempate N4 > N1, constantes inmutables (120s / 60s).
- `apps/classifier-service/src/classifier_service/services/event_labeler.py` — implementación.
- `apps/classifier-service/tests/unit/test_event_labeler.py` — 32 tests, 7 nuevos del override v1.1.0.
- `LABELER_VERSION="1.1.0"` se propaga en cada `n_level_distribution()` response (analytics-service `/episode/{id}/n-level-distribution`).
- `test_pipeline_reproducibility.py` 7/7 sigue pasando — auditabilidad bit-a-bit del clasificador preservada.

### Riesgo doctoral

**Bajo**. El parche **fortalece** la honestidad metodológica: la tesis pasa de afirmar "N2 fijo es decisión de implementación" (correcto pero limitado) a "v1.1.0 introduce override temporal heurístico, agenda Eje B cierra el residual con embeddings". Es exactamente el patrón que define el modelo híbrido honesto.

**Mitigación**: el ADR-023 documenta explícitamente que las constantes (120s / 60s) son **decisiones arbitrarias del piloto sujetas a análisis de sensibilidad**. El reporte empírico del piloto-1 incluirá ese análisis (ver script `scripts/g8a-sensitivity-analysis.py` agregado en iter 2).

---

## T15 — Precisar en 15.6 que la rama "prompt reflexivo" del CCD no se materializa en v1.0.x; activación es Eje B

**Coordinado con:** G9 (audi2.md) → [ADR-024](docs/adr/024-prompt-kind-reflexivo-runtime.md) — DIFERIDO a Eje B post-defensa.

### Estado pre-parche

La tesis 15.6 menciona "prompt con intencionalidad reflexiva" como una de las dos fuentes de verbalización contempladas por CCD v1.0.0 (junto con `anotacion_creada`).

### Problema

En runtime, **la rama de prompts reflexivos del CCD nunca se activa**:

- El contract Pydantic (`packages/contracts/src/platform_contracts/ctr/events.py`) admite cinco valores de `PromptKind`: `solicitud_directa`, `comparativa`, `epistemologica`, `validacion`, `aclaracion_enunciado`. **Ninguno es `"reflexion"`.**
- El tutor-service (`apps/tutor-service/src/tutor_service/services/tutor_core.py:200`) hardcodea `prompt_kind="solicitud_directa"` para todos los prompts.
- El módulo CCD (`apps/classifier-service/src/classifier_service/services/ccd.py:52,62`) busca `prompt_kind == "reflexion"` — match imposible con el conjunto vigente.

Resultado: la única fuente activa de verbalización en CCD es `anotacion_creada`. La afirmación de 15.6 sobre dos fuentes es operacionalmente falsa para v1.0.x.

### Propuesta de redacción (15.6 — fragmento sobre fuentes de verbalización en CCD)

> El módulo CCD (Code-Discourse Coherence) considera teóricamente dos fuentes de verbalización del estudiante: (i) anotaciones explícitas (evento `anotacion_creada`) y (ii) prompts con intencionalidad reflexiva. **En la versión v1.0.x del piloto, sólo la primera fuente está operacional**: el contract de eventos admite cinco categorías de `prompt_kind` (`solicitud_directa`, `comparativa`, `epistemologica`, `validacion`, `aclaracion_enunciado`) y el tutor-service hardcodea `solicitud_directa` por ausencia de un clasificador heurístico de prompts en runtime. La activación de la rama "prompt reflexivo" del CCD requiere (a) extender el contract con un sexto valor o redefinir el subconjunto reflexivo sobre los cinco existentes, y (b) clasificar `prompt_kind` en el momento de la emisión desde el tutor-service mediante reglas heurísticas validadas contra juicio docente con κ ≥ 0.6 (mismo protocolo que el clasificador N4, Capítulo 14). Ambos pasos están documentados en ADR-024 y diferidos a Eje B post-defensa por el costo metodológico de aplicarlos mid-cohort (introduciría sesgo de comparabilidad longitudinal, ya que episodios pre-cambio quedarían con todos los prompts marcados como `solicitud_directa`).

### Coordinación con código

- ADR-024 — decisión de DIFERIR, criterios de re-evaluación (corpus etiquetado disponible + pausa entre cuatrimestres + acuerdo del comité doctoral).
- `apps/tutor-service/src/tutor_service/services/tutor_core.py:200` — `prompt_kind` hardcoded.
- `apps/classifier-service/src/classifier_service/services/ccd.py:52,62` — rama muerta del CCD.
- `packages/contracts/src/platform_contracts/ctr/events.py` — `PromptKind` literal con cinco valores.

### Riesgo doctoral

**Bajo, pero importante de aplicar**. Mantener 15.6 sin esta precisión deja una afirmación operacionalmente falsa sobre v1.0.x — exactamente el tipo de inconsistencia que un comité doctoral atento puede señalar. El parche cierra el gap declarándolo honestamente.

---

## T16 — Precisar en 19.5 que el campo `origin` de `edicion_codigo` está parcialmente operacional

**Coordinado con:** G11 (audi2.md) → [ADR-026](docs/adr/026-boton-insertar-codigo-tutor.md) — DIFERIDO a post-defensa.

### Estado pre-parche

La tesis 19.5 (gaps declarados de v1.0.0) probablemente menciona el campo `origin` de `edicion_codigo` (introducido en F6) como instrumentación que distingue tipeo del estudiante (`student_typed`) de copia desde el tutor (`copied_from_tutor`) y paste externo (`pasted_external`).

### Problema

El frontend `web-student` **sólo emite `student_typed | pasted_external`**. La rama `copied_from_tutor` requiere un botón "Insertar código" en el panel del tutor que aún no está implementado (ADR-026 lo difiere). Verificación: `grep -rn "copied_from_tutor" apps/web-student` → solo aparece como type literal de TypeScript, no como string emitido en runtime.

El event_labeler (ADR-020) sí reconoce los tres valores y aplica override a N4 para `copied_from_tutor` y `pasted_external` — pero el primero no llega al CTR. La consecuencia pedagógica: la métrica que distingue **adopción deliberada** (botón) de **paste manual** (Ctrl+V de fuente externa cualquiera) está colapsada en el segundo.

### Propuesta de redacción (19.5 — fragmento sobre `origin` de `edicion_codigo`)

> El payload del evento `edicion_codigo` incluye desde F6 un campo opcional `origin: Literal["student_typed", "copied_from_tutor", "pasted_external"] | None` que distingue tres procedencias del cambio en el editor del estudiante. El etiquetador (ADR-020) aplica override `→ N4` para `copied_from_tutor` y `pasted_external` — interpretándolos pedagógicamente como acciones que provienen de una interacción IA o externa, no de elaboración propia. **En la versión v1.0.x del piloto, sólo dos de los tres valores se emiten en runtime**: `student_typed` (tipeo directo en el editor Monaco) y `pasted_external` (paste desde el clipboard, detectado por el handler `onPaste`). El tercer valor `copied_from_tutor` está declarado en el contract y reconocido por el etiquetador, pero requiere una afordancia UX — un botón "Insertar código" junto a cada bloque de código en las respuestas del tutor — que no está implementada en v1.0.x. La consecuencia operacional es que la métrica colapsa **adopción deliberada de un bloque sugerido por el tutor** (que sería evidencia de apropiación con intencionalidad declarada por la UX) con **paste manual de fuente externa cualquiera** (que captura tanto adopción deliberada vía copy-paste manual desde el chat como paste desde Stack Overflow u otra fuente). Ambos casos se etiquetan N4 vía override, pero pedagógicamente son distinguibles. La afordancia UX está diferida a post-defensa porque su introducción mid-cohort modifica la condición experimental (ADR-026, ver también confound 11.6).

### Coordinación con código

- ADR-026 — decisión de DIFERIR; criterios de re-evaluación (cohorte limpia o estudio cuasi-experimental con grupo control).
- `apps/web-student/src/components/CodeEditor.tsx` — emite sólo dos valores.
- `apps/classifier-service/src/classifier_service/services/event_labeler.py` — override reconoce los tres.
- `packages/contracts/src/platform_contracts/ctr/events.py` — `EdicionCodigoPayload.origin` admite los tres.

### Riesgo doctoral

**Bajo**. El parche fortalece la auditabilidad: la tesis admite que el campo está parcialmente operacional sin perder la declaración del invariante (override N4 aplicable a los tres valores cuando estén presentes). Cuando G11 se implemente, basta con reabrir el ADR-026 y agregar una nota a 19.5 sobre el cierre del gap.

---

## T17 (variante A) — `EpisodioAbandonado` ahora SÍ se emite; actualizar 7.2 + nueva sección sobre triggers + idempotencia

**Coordinado con:** G10-A (audi2.md) → [ADR-025](docs/adr/025-episodio-abandonado-beforeunload-timeout.md) — IMPLEMENTADO en iter 2 (commit 2026-04-29).

### Estado pre-parche

La tesis 7.2 lista `EpisodioAbandonado` entre los 8 eventos instrumentados v1.0.0. **Esa afirmación era operacionalmente falsa hasta iter 2**: el contract Pydantic existía desde F3, pero ningún servicio backend ni frontend emitía el evento. Verificación pre-iter-2: `grep -rn "episodio_abandonado" apps/` devolvía sólo el labeler (ADR-020) catalogándolo como `meta` y el contract — ningún emisor.

### Problema (resuelto en iter 2)

Era la asimetría más visible entre la tesis y el código (audi2.md G10). audi2.md proponía una decisión bifurcada: opción A (emitir efectivamente con `beforeunload` frontend + worker timeout server-side) u opción B (eliminar del contract y declarar como agenda). Iter 2 ejecutó **opción A** ([ADR-025](docs/adr/025-episodio-abandonado-beforeunload-timeout.md)).

### Propuesta de redacción (7.2 — fragmento sobre los 8 eventos instrumentados)

Mantener la lista de los 8 eventos, pero precisar el bloque de `EpisodioAbandonado`:

> **`EpisodioAbandonado`** (`reason ∈ {timeout, beforeunload, explicit}`, `last_activity_seconds_ago: float`): registra cierre **no intencional** del episodio, distinto del cierre deliberado vía `EpisodioCerrado`. Se emite por dos triggers complementarios (ADR-025): (i) **`beforeunload`** del navegador — el web-student dispara un POST al endpoint `/api/v1/episodes/{id}/abandoned` cuando el usuario cierra la pestaña o navega afuera con un episodio abierto, usando `navigator.sendBeacon` o `fetch` con `keepalive: true` según disponibilidad; (ii) **worker server-side de timeout** — tarea async del tutor-service que cada 60 segundos escanea las sesiones activas en Redis y emite `reason="timeout"` para sesiones con `last_activity_at` con antigüedad mayor a 30 minutos. Cubre los casos en que el `beforeunload` del browser no se dispara (mobile, crashes, conexión caída). La idempotencia entre ambos triggers se garantiza por **estado de sesión**: la primera emisión gana y la segunda es no-op silenciosa, eliminando el riesgo de doble-emisión al CTR. El `caller_id` distingue los dos casos para auditoría: para `reason ∈ {beforeunload, explicit}` el caller es el UUID del estudiante (acción del usuario); para `reason="timeout"` el caller es el service-account `TUTOR_SERVICE_USER_ID = 00000000-0000-0000-0000-000000000010` (acción del sistema).

### Propuesta de redacción (sección nueva o ampliada — política de cierre de episodios)

Agregar (probablemente al final de 7.2 o como subsección):

> **Política de cierre de episodios**. La plataforma distingue tres cierres: (i) **deliberado** vía `EpisodioCerrado` — el estudiante presiona "Finalizar" en la UI; el tutor-service emite el evento con `reason="student_finished"` y borra la sesión Redis; (ii) **abandono** vía `EpisodioAbandonado` — `beforeunload` del browser o detección server-side de inactividad, ver triggers arriba; (iii) **expiración por TTL** — la sesión Redis tiene TTL de 6 horas; si el episodio sobrevive sin actividad, expira sin emitir evento. La distinción entre (i), (ii) y (iii) es informativa: pedagógicamente, abandono ≠ cierre deliberado y ≠ inactividad pura. La métrica `proportion_abandoned_episodes` por cohorte queda como observable longitudinal del piloto (ver 17.x cuando se especifique).

### Coordinación con piloto

- **Cutover**: aplicar al cierre del cuatrimestre vigente o entre cuatrimestres. Episodios pre-cutover **no tienen el evento**; el reporte empírico debe declarar la fecha del cutover y tratar abandono pre-cutover como "no observable" (consistente con append-only ADR-010 — los eventos históricos no se modifican retroactivamente).
- Documentar el cutover en el reporte siguiendo el principio P6 de la tesis 21.4 (declaración de versiones en reportes empíricos).

### Coordinación con código

- ADR-025 — decisión, drivers, idempotencia, caller distinto por reason, constantes inmutables.
- `apps/tutor-service/src/tutor_service/services/{session.py,tutor_core.py,abandonment_worker.py}` — implementación backend.
- `apps/tutor-service/src/tutor_service/routes/episodes.py` — endpoint `POST /api/v1/episodes/{id}/abandoned`.
- `apps/web-student/src/{lib/api.ts,pages/EpisodePage.tsx}` — implementación frontend.
- `apps/tutor-service/tests/unit/test_episodio_abandonado.py` — 7 tests (idempotencia, sweep, fail-soft, caller).

### Riesgo doctoral

**Bajo y favorable**. El parche cierra una afirmación que era operacionalmente falsa. El comité doctoral ahora encuentra alineación tesis-código en este punto.

---

## T18 — Cuenta de guardarrailes en 8.4.1: 4/10 → 3/10 (corrección post-bump v1.0.1)

**Coordinado con:** G12 (audi2.md) → bump documental v1.0.1 del prompt + 5 tests pasando + manifest fail-loud (commit de iter 2, 2026-04-29).

### Estado pre-parche

La tesis 8.4.1 (probablemente Capítulo 8.4 sobre cobertura del prompt frente a los guardarrailes formales del Capítulo 8) declara que el prompt v1.0.0 cubre **4/10 guardarrailes formales**: GP1, GP2, GP3, GP4. El HTML comment al pie de `ai-native-prompts/prompts/tutor/v1.0.0/system.md` reproducía esa cuenta y mapeaba GP3 al Principio 3 ("dejar equivocarse").

### Problema

El mapeo era incorrecto:

- El Principio 3 del prompt ("Dejar que se equivoque… NO lo corrigés de inmediato — guialo a que descubra el bug por sí mismo") cubre **semánticamente GP4** (estimulación de la verificación ejecutiva), no GP3 (descomposición ante incomprensión).
- El mismo HTML comment mapeaba GP4 al mismo Principio 3, asignando el mismo principio a dos guardarrailes distintos.
- La cuenta correcta es **3/10**: GP1 (Principio 1 + Lo-que-NO-hace punto 1), GP2 (Principio 2), GP4 (Principio 3). **GP3 no tiene cobertura explícita en v1.0.x**.

Iter 2 cerró el gap con un bump **PATCH** documental v1.0.1 (G12 + commit 2026-04-29): nuevo `ai-native-prompts/prompts/tutor/v1.0.1/system.md` con texto **idéntico** del prompt (excepto el header `(v1.0.0)` → `(v1.0.1)`) y el HTML comment corregido. Manifest fail-loud `v1.0.1/manifest.yaml` con SHA-256 declarado (`2ecfcdddd29681b24539114975b601f9ec432560dc3c3a066980bb2e3d36187b`). v1.0.0 sigue accesible para reproducibilidad histórica del piloto.

**Importante**: v1.0.1 está disponible en el repo de prompts pero **NO es la versión activa por default** todavía. La activación es decisión académica del doctorando — pendiente al cierre de iter 2.

### Propuesta de redacción (8.4.1 — fragmento sobre cobertura del prompt)

> El prompt del tutor v1.0.x cubre **3 de los 10 guardarrailes formales** del Capítulo 8: GP1 (no entregar la solución directa, vinculado al Principio 1 y al ítem 1 de "Lo que NO hace el tutor"), GP2 (responder preguntas con preguntas, vinculado al Principio 2) y GP4 (estimulación de la verificación ejecutiva, vinculado al Principio 3 — "dejar equivocarse" y "guiar a que descubra el bug por sí mismo"). **GP3 (descomponer ante incomprensión) no tiene cobertura explícita en v1.0.x**: la versión v1.0.0 originalmente atribuyó GP3 al Principio 3 en el HTML comment de auditoría, pero ese principio cubre semánticamente GP4 (verificación ejecutiva), no GP3 (descomposición). El bump PATCH v1.0.1 (ADR-009 + commit de iter 2, 2026-04-29) corrige el comentario de auditoría sin modificar el texto del prompt entregado al modelo — preservando reproducibilidad bit-a-bit del piloto histórico (v1.0.0 sigue accesible). Los siete guardarrailes restantes están agendados para v1.1.0+: GP3 + GP5 (reconocer alcance excedido) requieren reglas explícitas en el prompt; GC1, GC2, GC4, GC5 requieren restricciones de contenido también explícitas; GC3 (no contenido ofensivo) está delegado a la safety layer base del LLM (Anthropic / OpenAI).

### Coordinación con código

- `ai-native-prompts/prompts/tutor/v1.0.1/system.md` — bump PATCH con HTML comment corregido.
- `ai-native-prompts/prompts/tutor/v1.0.1/manifest.yaml` — hash declarado fail-loud.
- `apps/governance-service/tests/unit/test_prompt_v1_0_1_bump.py` — 5 tests pasando (v1.0.0 sigue cargable, v1.0.1 valida fail-loud, hashes distintos, texto idéntico modulo HTML comment + version, cuenta 4/10 → 3/10).
- ADR-009 — Git como fuente de verdad del prompt; cubre la convención de bumps y el verifier fail-loud.

### Decisión binaria pendiente

¿La activación global de v1.0.1 se hace ahora o se difiere al cierre del cuatrimestre? Audi2.md G12 timing recomienda diferir por rigor metodológico (el HTML comment es invisible al modelo, pero el cambio del `prompt_system_hash` propagado a eventos del CTR sí cambia la auditoría). Mientras la decisión esté pendiente, mantener v1.0.0 como activa (default actual del `prompt_loader`) y v1.0.1 como disponible-pero-inactiva.

### Riesgo doctoral

**Muy bajo**. El parche es una corrección puntual de una cuenta. La tesis pasa de afirmar 4/10 (incorrecto) a 3/10 (verificable contra el HTML comment de v1.0.1). El comité doctoral encuentra alineación. El bump PATCH v1.0.1 documenta explícitamente la corrección.

### Importante: aplicar T18 con o sin G12 activado

T18 puede aplicarse al **manuscrito de la tesis** sin requerir que v1.0.1 esté activo en runtime — el HTML comment es invisible al modelo (no afecta el comportamiento del tutor) y el bump PATCH documenta la corrección textual. La consideración importante: **o se cambia ambas (T18 en tesis + G12 en código), o ninguna**. No mezclar parche tesis sin parche código — el comité encontraría una corrección documental sin contraparte en el repo. Iter 2 ya hizo G12; T18 cierra el lado tesis.

---

## Resumen de coordinación tesis ↔ código tras iter 2

| Parche | G original | ADR | Estado código | Estado tesis (post-T) |
|---|---|---|---|---|
| T14 | G8a | ADR-023 | Implementado v1.1.0 | Por aplicar — describe override temporal + Eje B |
| T15 | G9 | ADR-024 (diferido) | NO implementado | Por aplicar — declara rama "prompt reflexivo" inactiva en v1.0.x |
| T16 | G11 | ADR-026 (diferido) | Parcialmente operacional | Por aplicar — declara `origin` parcial |
| T17 | G10-A | ADR-025 | Implementado | Por aplicar — describe triggers + idempotencia |
| T18 | G12 | ADR-009 | Implementado v1.0.1 (no activado global) | Por aplicar — corrige cuenta 4/10 → 3/10 |

**Lectura de coherencia**: tras aplicar T14-T18, la tesis vigente queda alineada con el repo post-iter-2 al nivel exigible para defensa. Quedan los 5 stubs ADR (017/024/026/027/028) declarados como agenda confirmatoria — la tesis 20.5.1 ya cubre la línea editorial de "Eje A/B/C como agenda futura"; cada stub ADR redactado en iter 2 puede citarse en 20.5.1 como evidencia de decisión informada (no deuda silenciosa).

## Próximos pasos sugeridos para el doctorando

1. **Aplicar T14-T18 al manuscrito** preservando estilo y precisión académica. Los borradores propuestos son andamios — el doctorando los refina contra el texto real.
2. **Verificar referencias cruzadas** — cada T cita ADR + ruta de código + sección de tesis. Las rutas y ADRs son verificables y deben citarse exactamente en el manuscrito final.
3. **Coordinar con el director de tesis** la aceptación de T17 + T18 antes del cierre del cuatrimestre — son los dos parches con mayor visibilidad al comité (afirmaciones operacionales corregidas).
4. **Decidir activación de v1.0.1 globalmente** (bloqueante para la coherencia T18 + G12 — ver decisión binaria pendiente arriba).
