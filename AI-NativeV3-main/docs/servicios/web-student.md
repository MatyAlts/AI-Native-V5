# web-student

## 1. Qué hace (una frase)

Es la única UI donde el estudiante interactúa con el tutor socrático: selecciona una TareaPractica publicada, abre un episodio, edita código Python en Monaco y lo ejecuta con Pyodide en el browser, conversa con el tutor vía SSE, toma notas personales, y recibe la clasificación N4 al cerrar.

## 2. Rol en la arquitectura

Pertenece a los **frontends**. Materializa la interfaz del componente "Aplicación web de estudiante" descrito en el Capítulo 6 de la tesis (arquitectura C4 del sistema AI-Native), cuyas responsabilidades nominales son: mediar la totalidad del flujo pedagógico del estudiante, capturar su actividad (código editado, código ejecutado, notas personales) como eventos del CTR, y renderizar la respuesta del tutor socrático sin que el estudiante perciba la cadena de servicios que la produce.

Es el único frontend que consume SSE (streaming del tutor), ejecuta código sandboxed (Pyodide WASM), y envía eventos de actividad directa del estudiante al CTR con su propio `user_id` (no el service account del tutor — distinción documentada en [tutor-service](./tutor-service.md) Sección 4).

## 3. Responsabilidades

- Ofrecer un selector en cascada: `ComisionSelector` → `TareaSelector` (sólo TPs `published` de la comisión elegida) → apertura de episodio via `POST /api/v1/episodes`.
- Renderizar el enunciado de la TP (Markdown via `react-markdown@9` + `remark-gfm@4`) arriba del editor.
- Montar Monaco Editor para Python con ejecución local via **Pyodide** (WASM, ~6 MB first-load desde CDN, cached): el estudiante corre código sin pegar al backend, sin consumir LLM budget, y sin compartir runtime con otros estudiantes.
- Emitir `edicion_codigo` debounced (snapshot del editor + `diff_chars` + `language` + `origin`) al `POST /api/v1/episodes/{id}/events/edicion_codigo` — crítico para CCD del clasificador (distingue "tipeando/pensando" de "idle").
- Detectar el origen de cada `edicion_codigo` y propagarlo en el campo `origin` (F6): `student_typed` (default) vs `pasted_external` (Monaco `onDidPaste`). El valor `copied_from_tutor` está reservado para cuando exista un botón "insertar al editor" en el chat del tutor (no implementado aún). Permite distinguir delegación pasiva sin depender solo de inferencia temporal.
- Emitir `lectura_enunciado` mientras el panel del enunciado está visible (F5: `IntersectionObserver` con threshold 0.25 + `document.visibilityState`). Flushea cada 30s acumulados o al desmontar el componente, con re-acumulación si el POST falla. Es la señal observable canónica de N1 (Comprensión) en el modelo N4 — sin esto el clasificador queda sin evidencia directa de tiempo en N1.
- Emitir `codigo_ejecutado` cada vez que el estudiante corre el código: `code`, `stdout`, `stderr`, `duration_ms`, `runtime="pyodide-0.26"`.
- Streamear la respuesta del tutor via SSE (`POST /api/v1/episodes/{id}/message`): parsear eventos `data: {"type": "chunk", ...}` y renderizar token por token; al `done`, mostrar la respuesta completa con Markdown.
- Ofrecer un `NotesPanel` para anotaciones libres del estudiante (1..5000 chars) — cada guardado emite `anotacion_creada` (alimenta CCD orphan ratio: sin notas, episodios reflexivos se marcan como huérfanos).
- Persistir el `episode_id` activo en **`sessionStorage`** (key `active-episode-id`, scope per-tab, G4 recovery). Al recargar (F5) el browser, el frontend llama `GET /api/v1/episodes/{id}` y reconstruye el estado (mensajes + último snapshot de código + notas) via `_build_episode_state` del tutor-service.
- Cerrar episodios con `POST /episodes/{id}/close` — emite `episodio_cerrado` y limpia el `sessionStorage`.
- **Detectar abandono** ([ADR-025](../adr/025-episodio-abandonado.md), G10-A): listener `beforeunload` → `POST /api/v1/episodes/{id}/abandoned` con `reason="beforeunload"`. Idempotente con worker server-side (que emite `reason="timeout"` si la sesión queda inactiva 30 min).
- **Renderizar el sandbox client-side de Pyodide** para tests unitarios ([ADR-033](../adr/033-sandbox-pyodide.md), [ADR-034](../adr/034-test-cases-tp.md)): el estudiante corre los `test_cases is_public=true` de la TP localmente; emite `POST /api/v1/episodes/{id}/run-tests` con SOLO conteos (no código). El classifier labeler v1.2.0 etiqueta como N3/N4. Hidden tests (`is_public=false`) NO se exponen al estudiante.
- **Renderizar `ReflectionModal` post-clasificación** ([ADR-035](../adr/035-reflexion-metacognitiva.md)): modal opcional con 3 textareas (≤500 chars c/u) post-evento `episodio_cerrado` que emite evento CTR `reflexion_completada` (excluido del classifier por RN-133). Ofrece al estudiante el espacio para reflexión metacognitiva sin afectar la categoría N4 ya asignada.

## 4. Qué NO hace (anti-responsabilidades)

- **NO ejecuta código en el backend**: toda ejecución Python es Pyodide WASM en el worker aislado del browser ([ADR-033](../adr/033-sandbox-pyodide.md): sandbox Pyodide-only para piloto-1, sin worker Docker para reducir blast radius). Ventaja documentada en `CodeEditor.tsx` (cero costo de infra, cero riesgo de abuso). Limitación: network calls bloqueadas, paquetes PyPI requieren `micropip`.
- **NO autora trabajos prácticos ni materiales**: eso es [web-teacher](./web-teacher.md). Acá se **consumen** las TPs `published` y el material de cátedra (via RAG del tutor, transparente al estudiante).
- **NO muestra la clasificación N4 inmediatamente al cerrar el episodio**: la clasificación es asíncrona (corre en [classifier-service](./classifier-service.md) cuando se la dispara manualmente). El MD del EpisodePage tiene handling para mostrar "clasificando..." y el resultado via `classifyEpisode()` pero el trigger automático post-cierre no está (ver [classifier-service](./classifier-service.md) Sección 4).
- **NO maneja identidad local**: en dev los headers los inyecta el proxy Vite (`x-user-id: b1b1b1b1-0001-0001-0001-000000000001` — estudiante 1 de A-Mañana del `seed-3-comisiones.py`). En prod via JWT de Keycloak validado por api-gateway.
- **NO persiste nada en `localStorage`**: sólo `sessionStorage` (scope tab) por diseño — cerrar la pestaña debe descartar la sesión, refrescar (F5) debe recuperarla. `@platform/auth-client` maneja tokens en memoria.
- **NO implementa chat multi-episodio simultáneo**: un episodio activo por tab. Si el estudiante quiere trabajar en dos TPs a la vez, abre otra pestaña.

## 5. Rutas principales

Frontend con **una sola página**: `EpisodePage.tsx`. No hay router real — `App.tsx` monta `<EpisodePage />` directo. El "routing" interno son estados de la página:

| Estado | Render |
|---|---|
| Sin comisión elegida | `ComisionSelector` |
| Con comisión, sin TP | `TareaSelector` (TPs `published` de la comisión) |
| Con TP, sin episodio | `OpeningStage` con CTAs "Abrir episodio" → `POST /episodes`. Estado de error con CTAs "Reintentar" / "Volver" (sesión 2026-05-08). |
| Con episodio activo | Layout full-screen 3 columnas: **consigna** (Markdown) \| **editor** (Monaco + Pyodide + tests) \| **tutor** (chat SSE + `NotesPanel`). Animaciones motion 2026. |
| Con episodio cerrado | Modo lectura (mensajes + último código + notas, sin enviar más) + **`ReflectionModal`** opcional post-clasificación ([ADR-035](../adr/035-reflexion-metacognitiva.md)). |
| `recovering` (F5 con `sessionStorage` activo) | Fetch estado + restaurar UI antes de aceptar input. |

`EpisodePage` es **excepción documentada** del patrón `PageContainer` del monorepo (CLAUDE.md "Sistema de ayuda in-app"): usa layout full-screen con header funcional propio (`ComisionSelector`, botón "Cambiar TP", info dinámica de TP/episodio) que `PageContainer` no puede sustituir. Usa `HelpButton` directo en el header existente.

## 6. Dependencias

**Depende de (servicios):**
- [api-gateway](./api-gateway.md) via proxy Vite `/api`.
- Aguas abajo: [tutor-service](./tutor-service.md) (abrir/cerrar episodio, SSE, eventos de actividad), [academic-service](./academic-service.md) (`GET /tareas-practicas?comision_id=...` y `GET /comisiones/mis` — con el gap conocido), [classifier-service](./classifier-service.md) (clasificación post-cierre).

**Depende de (CDN externo en runtime):**
- **Pyodide** — carga desde CDN en el primer run (~6 MB WASM). Si el estudiante está offline o la CDN cae, el editor no puede ejecutar código.

**Depende de (packages workspace):**
- `@platform/ui` — `HelpButton`, `MarkdownRenderer`, tokens CSS.
- `@platform/auth-client`, `@platform/contracts`.
- `monaco-editor@^0.52.0` — editor local.
- `react-markdown@9` + `remark-gfm@4` — renderizado del enunciado y de las respuestas del tutor.

**Dependen de él:** nadie (consumidor humano — el estudiante del piloto).

## 7. Modelo de datos

Frontend — sin persistencia de DB. Estado client-side:

- **`sessionStorage["active-episode-id"]`** — UUID del episodio activo (G4). Scope per-tab. Clears on tab close, survives refresh.
- **In-memory**: `messages: Message[]` (historia de la conversación en el turno actual), `lastCode: string` (última snapshot antes del refresh), `notes: SavedNote[]` (notas del turno, descartadas al refresh pero recuperadas del CTR via `GET /episodes/{id}`), `classification: Classification | null`.
- **Pyodide**: VM aislada del browser con su propia Python runtime + stdlib. Network calls bloqueadas. Si el estudiante hace `import numpy`, `micropip` debería cargarlo (no está documentado si se expone desde `CodeEditor`).

## 8. Archivos clave para entender el servicio

- `apps/web-student/src/pages/EpisodePage.tsx` — **la página única**. Orquesta selector → episodio abierto → SSE → cierre → clasificación → reflexión modal. Layout 3 columnas (consigna|editor|tutor) con animaciones motion 2026. Contiene la lógica del G4 recovery, el handler del SSE stream, listener `beforeunload` para abandono ([ADR-025](../adr/025-episodio-abandonado.md)), y el manejo de errores (`EpisodeStateError`).
- `apps/web-student/src/components/CodeEditor.tsx` — Monaco + Pyodide integration. Docstring explica el trade-off (costo cero + aislamiento vs. network bloqueado + stdlib-only). Handle de `runPythonAsync`, captura de stdout/stderr via `setStdout`/`setStderr`. Tests sandbox: ejecuta los `test_cases is_public=true` de la TP y emite conteos a `POST /run-tests` ([ADR-034](../adr/034-test-cases-tp.md)).
- `apps/web-student/src/components/NotesPanel.tsx` — panel de notas con límite 1..5000 chars. Cada save dispara `emitAnotacionCreada`.
- `apps/web-student/src/components/ReflectionModal.tsx` — modal post-clasificación ([ADR-035](../adr/035-reflexion-metacognitiva.md)) con 3 textareas (≤500 chars c/u). Emite `POST /api/v1/episodes/{id}/reflection` con evento CTR `reflexion_completada`.
- `apps/web-student/src/components/OpeningStage.tsx` — pantalla de apertura con CTAs Reintentar/Volver cuando hay error (sesión 2026-05-08).
- `apps/web-student/src/components/ComisionSelector.tsx` — selector de comisión. Depende de `GET /comisiones/mis` — hoy **devuelve [] para estudiantes reales** (CLAUDE.md "Brechas conocidas", gap F9 a destrabar con `comisiones_activas` en JWT, plan en `docs/plan-b2-jwt-comisiones-activas.md`).
- `apps/web-student/src/components/TareaSelector.tsx` — lista TPs `published` de la comisión elegida con paginación por cursor. Es el reemplazo del UUID hardcoded del problema inicial.
- `apps/web-student/src/components/MarkdownRenderer.tsx` — **duplicado** con web-teacher (CLAUDE.md "Modelos no obvios"). `[&_h1]:...` selectors arbitrarios.
- `apps/web-student/src/lib/api.ts` — `openEpisode`, `sendMessage` (SSE), `closeEpisode`, `getEpisodeState`, `classifyEpisode`, `emitAnotacionCreada`, `emitEdicionCodigo`, `emitCodigoEjecutado`, `runTests`, `submitReflection`, `notifyAbandoned`, `getTareaById`.
- `apps/web-student/src/utils/helpContent.tsx` — **1 sola entry** (el único dashboard del frontend).
- `apps/web-student/vite.config.ts` — headers dev con `b1b1b1b1-0001-0001-0001-000000000001` + role `estudiante`.

## 9. Configuración y gotchas

**Env vars**:
- `VITE_API_URL` — default `http://127.0.0.1:8000`.

**Puerto de desarrollo**: `5175`.

**Gotchas específicos**:

- **`x-user-id` debe matchear el seed activo**: el proxy inyecta `b1b1b1b1-0001-0001-0001-000000000001` — estudiante 1 de A-Mañana en el `seed-3-comisiones.py`. Si corrés un seed distinto que no crea ese `student_pseudonym` en `inscripciones`, el web-student **loguea como un estudiante que no existe** y `TareaSelector` viene vacío silenciosamente. El comentario en `vite.config.ts` documenta el mapping completo (`b1b1b1b1-000{1..6}` A-Mañana, `b2b2b2b2-` B-Tarde, `b3b3b3b3-` C-Noche). Sincronizar el UUID con el seed.
- **`ComisionSelector` vacío para estudiantes reales**: gap conocido F9 (`GET /comisiones/mis` JOINea `usuarios_comision` que es para docentes). `selectedComisionId` cae al fallback `DEMO_COMISION_ID` (`aaaaaaaa-...`). Se destraba con claim `comisiones_activas` en el JWT.
- **Pyodide first-load lento**: primera ejecución carga ~6 MB desde CDN. UX tiene que tener un loading claro; si el estudiante piensa que "cuelga" y refresca, pierde el load cacheado.
- **Pyodide bloquea en loops largos**: docstring lo declara. Código con `while True:` va a congelar la pestaña. Deliberado — no hay watchdog.
- **SSE via api-gateway puede buffearse**: gap declarado en [api-gateway](./api-gateway.md) Sección 9. Si el streaming no llega token-por-token al frontend, la UX se siente "todo de golpe". No verificado e2e.
- **Bootstrap del tutor depende de governance**: si el `governance-service` no tiene el prompt `tutor/v1.0.0` sembrado, `POST /episodes` devuelve 500 con stack `httpx.HTTPStatusError: '404 Not Found'`. En dev, `PROMPTS_REPO_PATH="$(pwd)/ai-native-prompts"` es obligatorio (CLAUDE.md "Gotchas de entorno").
- **`anotacion_creada` con whitespace-only**: el backend devuelve 422. El frontend debe validar `contenido.trim()` antes de enviar — si no, error visible al estudiante.
- **Recovery con episodio cerrado**: si el estudiante refresca después de cerrar, el fetch a `GET /episodes/{id}` devuelve `estado: "closed"` — el frontend entra en modo lectura + limpia `sessionStorage`.
- **PageContainer no aplica**: decisión arquitectónica documentada. Replicar la excepción requiere una justificación equivalente (layout full-screen con header funcional único que el PageContainer no puede sustituir).

## 10. Relación con la tesis doctoral

El web-student es la **puerta de entrada única al flujo pedagógico de la tesis**. Todo lo que la tesis mide — las 5 coherencias (CT, CCD, CII), κ inter-rater, progresión longitudinal — se origina en la actividad que el estudiante genera desde esta UI. Tres afirmaciones que materializa:

1. **Captura de la autoría del estudiante**: los tres eventos `codigo_ejecutado`, `edicion_codigo`, `anotacion_creada` se emiten con `user_id = estudiante real`, no con el `TUTOR_SERVICE_USER_ID`. Esta distinción (CLAUDE.md "Constantes que NO deben inventarse") es necesaria para que el clasificador pueda decir "acción del estudiante vs respuesta del tutor" al computar CCD.

2. **Aislamiento criptográfico del runtime**: Pyodide en el browser garantiza que el código ejecutado es el que el estudiante escribió, sin intermediación del backend. Si se ejecutara server-side, habría que auditar el sandbox; con Pyodide WASM, cada estudiante tiene su VM descartable y la "manipulación externa del runtime" queda descartada como hipótesis.

3. **Recuperabilidad del estado via CTR**: el G4 (recovery por refresh) no persiste estado en `localStorage` ni en una DB del frontend — reconstruye desde los eventos del CTR. Esto sostiene el invariante de la tesis: **la única fuente de verdad del episodio es la cadena criptográfica**. Si el browser se cae, el CTR está intacto y el GET reconstruye.

La decisión de **una sola página full-screen** (sin PageContainer) es una concesión de UX: el estudiante trabajando en un TP necesita ver simultáneamente el enunciado, el código, los mensajes del tutor y las notas. Fragmentarlo en rutas o panels cerrables rompe el flujo.

## 11. Estado de madurez

**Tests**: sin suite activa de componentes. Los tests de la foundation UI viven en `packages/ui/`. Los tests de Pyodide integration no existen — la verificación es manual end-to-end.

**Known gaps**:
- `ComisionSelector` vacío para estudiantes reales (F9 gap).
- Clasificación post-cierre manual (no automática — gap del backend, ver [classifier-service](./classifier-service.md)).
- Pyodide first-load visible (~6 MB) sin optimización (service worker cache específico).
- SSE via gateway posiblemente buffereado — verificación pendiente.
- `MarkdownRenderer` duplicado con web-teacher.
- Rubrica de TPs (si la hay en el enunciado) se renderiza como JSON crudo dentro del Markdown — no hay renderer estructurado.
- Sin offline mode (Pyodide ya está cacheado, pero la UI depende del backend en todo lo demás).

**Fase de consolidación**:
- F3 — integración SSE del tutor + eventos CTR básicos (`docs/F3-STATE.md`).
- F5 — Pyodide + `codigo_ejecutado` (`docs/F5-STATE.md`).
- F6 — `anotacion_creada` + `edicion_codigo` + G4 recovery con `sessionStorage`.
- F8 — `TareaSelector` real (reemplazo del UUID hardcoded) + markdown rendering del enunciado.
- 2026-04-29 ([ADR-025](../adr/025-episodio-abandonado.md)) — listener `beforeunload` con `POST /abandoned`.
- 2026-05-04 (epic `ai-native-completion-and-byok`) — `ReflectionModal` post-clasificación ([ADR-035](../adr/035-reflexion-metacognitiva.md)). Sandbox client-side de tests con Pyodide ([ADR-033](../adr/033-sandbox-pyodide.md), [ADR-034](../adr/034-test-cases-tp.md)).
- 2026-05-04 — refactor de tokens centralizados en `packages/ui` con paleta "Stack Blue institucional" #185FA5.
- 2026-05-08 — `OpeningStage` con CTAs "Reintentar" / "Volver" en error states; layout 3 columnas (consigna|editor|tutor) con animaciones motion 2026.
