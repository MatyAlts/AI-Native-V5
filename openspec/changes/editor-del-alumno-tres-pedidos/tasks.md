# Tareas — editor del alumno, tres pedidos

## 0. Red de seguridad

- [x] 0.1 Baseline acotado ANTES de tocar `cascadaCodigo.ts` / `artefactos.ts`:
      `pnpm test -- --run tests/cascadaCodigo.test.ts tests/CodigoPrevioSiembra.test.tsx`
      → 14/14 verde.
- [x] 0.2 Baseline completo DESPUES de todos los cambios (no se corrio un
      baseline completo ANTES de tocar `EpisodePage.tsx`/`CodeEditor.tsx` por
      proceso — ver nota en el informe de cierre):
      `pnpm test -- --run` → 630/630 verde (53 archivos).

## 1. Borrador local al reabrir

- [x] 1.1 `readArtefactoDraft(scopeId, orden)` en `artefactos.ts` — clave
      exacta, corrupto/vacio/ausente -> `null`.
- [x] 1.2 Candidato `borradorLocal` en `cascadaCodigo.ts`, maxima precedencia,
      nuevo `OrigenCodigo: "borrador-local"`.
- [x] 1.3 `EpisodePage.tsx`: resolver el candidato con la misma clave que la
      escritura, aceptar solo si `draft.episode_id === episodeId`.
- [x] 1.4 Verificar (lectura de codigo, no test) que la siembra no emite
      `edicion_codigo` y que el codigo sembrado, al editarse, entra como
      `student_typed` sin necesitar un `origin` nuevo.
- [x] 1.5 Tests en `tests/BorradorLocalAlReabrir.test.tsx`: cascada pura (4
      casos), `readArtefactoDraft` (5 casos), integracion monolitica (2 casos),
      integracion multi-ejercicio mismo/otro episodio (2 casos). 13/13 verde.

## 2. Panel de salida: agarrable y persistente

- [x] 2.1 `min-h-0` en el div raiz de `CodeEditor`.
- [x] 2.2 `style={{ overflow: "hidden" }}` en `Panel id="editor-code"` (no
      clase de Tailwind — ver el porque en `proposal.md`).
- [x] 2.3 `fixedOverflowWidgets: true` en `monaco.editor.create` — evita que
      el nuevo recorte le tape el widget de sugerencias de Monaco.
- [x] 2.4 Manubrio: area de agarre mas alta, grip visible en reposo (no solo
      en hover), mismo lenguaje visual que los divisores laterales. Sin test
      automatizado (requiere layout/juicio visual — declarado en el docstring
      del archivo de test).
- [x] 2.5 Persistencia ED-2 replicada: `OUTPUT_PANEL_STORAGE_KEY`,
      `readStoredOutputPanelLayout`/`persistOutputPanelLayout` (funciones
      puras, try/catch), cableadas a `Group` via `defaultLayout`/
      `onLayoutChanged`.
- [x] 2.6 Tests en `tests/CodeEditorPanelDeSalida.test.tsx`: min-h-0, overflow
      inline, fixedOverflowWidgets, accesibilidad del separador (role +
      tabIndex), lectura/escritura de la clave de persistencia (6 casos +
      robustez ante error). 10/10 verde.
- [x] 2.7 Confirmado que no rompe el suite existente de `CodeEditor`
      (arrastre, marcas de origen, remonte, portapapeles, timeout, sin casos,
      snippets, orden de eventos, sugerencias): 53/53 verde.

## 3. `wordBasedSuggestions` fijado

- [x] 3.1 `wordBasedSuggestions: "currentDocument"` en `SUGERENCIAS_OPTIONS`,
      con el criterio del docente citado textual y por que no
      `matchingDocuments`.
- [x] 3.2 Test en `tests/CodeEditorSugerenciasPorPalabra.test.tsx`: asertado
      sobre `create()`, no sobre `updateOptions()` (el mock descarta ese
      argumento — ver docstring). 3/3 verde.
- [x] 3.3 Declarado en el docstring del test que las sugerencias por palabra
      incluyen el scaffold del docente, como consecuencia deseada y no
      accidente.

## 4. Cierre

- [x] 4.1 `pnpm test -- --run` completo: 630/630 verde.
- [x] 4.2 `pnpm exec biome check --write .` corrido. Fijo 1 error propio
      (exhaustive-deps en el `useEffect` de hidratacion de `EpisodePage.tsx`
      por referenciar `ejercicioContext` directo) reformateando con variables
      derivadas ya establecidas en el archivo (mismo patron que
      `ejercicioOrden`). Reformateo automatico de 6 archivos de test
      preexistentes no tocados por esta change (solo wrapping/orden de
      imports, sin cambio de logica — verificado con `git diff`), commiteado
      junto por instruccion explicita del cierre.
- [x] 4.3 1 warning preexistente de biome en `tests/episodioDownload.test.ts`
      (`suppressions/unused`) — **NO tocado**, reportado como falla
      preexistente, no arreglado.
- [x] 4.4 `proposal.md` + `tasks.md` escritos.

## 5. QA round 2 — huecos de cobertura y foco (sobre el commit `8486551`)

QA mutó el código y midió que sacar `defaultLayout`/`onLayoutChanged` del
`<Group>` dejaba la suite en 630/630 verde: los tests de persistencia probaban
las funciones puras aisladas, nunca el cableado contra el componente. Frontend
encontró además un foco sin anillo y sin nombre accesible en el manubrio
nuevo. Nada de esto rehace lo hecho; cierra huecos sobre ello.

- [x] 5.1 Test de cableado en `tests/CodeEditorPanelDeSalida.test.tsx`: un
      layout guardado en `localStorage` llega de verdad al `<Group>` —
      leído contra el `flexGrow` inline que la librería le pone a cada
      `Panel` (observable en jsdom sin layout real). Mutación manual de
      `defaultLayout={savedOutputPanelLayout}` confirmada en rojo
      (`expected '50' to be '30'`), restaurada y vuelta a verde. **La mitad
      de escritura (`onLayoutChanged`) queda sin test** — investigado un
      camino honesto (keyboard resize, que opera en espacio de porcentajes) y
      descartado porque jsdom tira `Previous layout not found for panel
      index 0` antes de llegar al cálculo; declarado en el docstring del
      archivo, mutación manual confirmó que sigue sin detectarse si se borra
      esa línea.
- [x] 5.2 Dos tests nuevos en `tests/BorradorLocalAlReabrir.test.tsx` para
      `readArtefactoDraft`: `episode_id` ausente del JSON y `episode_id:
      null` — confirman que la función NO filtra por `episode_id` (esa es
      responsabilidad del `===` en `EpisodePage.tsx`, el candado anti-ED-4).
      Mutación manual (forzar un `episode_id` inventado cuando falta)
      confirmada en rojo en los dos asserts, restaurada y vuelta a verde.
- [x] 5.3 Test de integración en `tests/BorradorLocalAlReabrir.test.tsx`:
      `localStorage.getItem` que tira para la clave puntual del borrador — el
      episodio hidrata igual y cae al snapshot del servidor. Mutación manual
      (sacar el try/catch de `readArtefactoDraft`) confirmada en rojo
      (`Episode hydration failed`, el editor cae al placeholder en vez del
      snapshot), restaurada y vuelta a verde.
      **Gotcha de entorno encontrado y declarado en el test**:
      `vi.spyOn(window.localStorage, "getItem")` NO intercepta en este
      proyecto (Node 22 + vitest/jsdom) — hay que espiar
      `Storage.prototype.getItem`. Afecta también al test preexistente de
      `setItem` en `CodeEditorPanelDeSalida.test.tsx` ("si localStorage.
      setItem tira..."), que espía la instancia y por lo tanto **no
      discrimina nada** en este entorno (pasa igual sin importar si el mock
      intercepta) — reportado al orquestador, **no corregido** acá (no era
      parte del encargo de esta ronda).
- [x] 5.4 Foco del manubrio (`CodeEditor.tsx` ~2056): agregado
      `focus-visible:ring-2 focus-visible:ring-accent-brand/40` (mismo patrón
      que `CodeEditor.tsx:1921,1955`) y `aria-label="Redimensionar el panel
      de salida"`. Dos tests nuevos en rojo antes del cambio (`toHaveClass`/
      `toHaveAttribute` fallando contra el markup real), verde después.
      **Deuda preexistente declarada, no tocada en este PR**: los dos
      separadores laterales de `EpisodePage.tsx:1473,1481` tampoco tienen
      nombre accesible — pendiente para otro cambio.
- [x] 5.5 Comentario ampliado en `CodeEditor.tsx` (`fixedOverflowWidgets`,
      ~líneas 578-605): documentado que `animate-fade-in-up` deja un
      `transform` permanente en el ancestro `section` de `EpisodePage.tsx`
      (containing block para `position: fixed`), que el orquestador verificó
      en browser real que Monaco posiciona el widget con coordenadas medidas
      y lo absorbe (mismas coordenadas con/sin `transform`, desborda igual
      42px fuera del panel recortado), y que la geometría extrema (panel de
      salida arrastrado al mínimo, popup pegado al borde inferior de la
      `section`) **quedó sin verificar** — declarado como supuesto, no como
      cubierto. Sin cambio de código (`fixedOverflowWidgets: true` se
      mantiene intacto).
- [x] 5.6 `pnpm test -- --run` completo: 636/636 verde (+6 sobre los 630 de
      la ronda anterior).
- [x] 5.7 `pnpm exec biome check --write .`: reformateó
      `tests/CodeEditorPanelDeSalida.test.tsx` (el archivo tocado en esta
      ronda). Mismo warning preexistente de `tests/episodioDownload.test.ts`
      (`suppressions/unused`) — sigue sin tocarse.
- [x] 5.8 `pnpm run typecheck`: limpio.

## Fuera de alcance

- El resto del backlog de `EpisodePage`/`CodeEditor` no mencionado en los tres
  pedidos.
- Backend, prompts del tutor, contrato del CTR: sin cambios.
- Nombre accesible de los 2 separadores laterales preexistentes de
  `EpisodePage.tsx:1473,1481` — deuda declarada en 5.4, no en este cambio.
- El test preexistente de `setItem` roto en `CodeEditorPanelDeSalida.test.tsx`
  que no discrimina en este entorno (ver 5.3) — reportado, no corregido acá.
- Test de `onLayoutChanged` (escritura de persistencia del panel) contra el
  componente — investigado y descartado por limitación real de jsdom, ver
  5.1 y el docstring del archivo de test.
