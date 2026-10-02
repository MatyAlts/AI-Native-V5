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

## Fuera de alcance

- El resto del backlog de `EpisodePage`/`CodeEditor` no mencionado en los tres
  pedidos.
- Backend, prompts del tutor, contrato del CTR: sin cambios.
