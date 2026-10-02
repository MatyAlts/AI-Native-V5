## Why

Tres pedidos puntuales sobre el editor del alumno (`apps/web-student`), sin
relacion entre si salvo que los tres tocan la misma pantalla (`EpisodePage` +
`CodeEditor`):

### 1. El respaldo local no se lee al reabrir (la importante)

El alumno escribe; cada segundo se guarda una copia local en `localStorage`
(`saveArtefactoDraft`) Y se emite `edicion_codigo` al CTR (fire-and-forget).
Al reabrir un episodio pausado, el editor se sembraba SOLO con
`state.last_code_snapshot` (el que el servidor alcanzo a persistir) y nunca
miraba la copia local. Si el guardado al servidor fallo (red, server caido),
el alumno veia codigo viejo teniendo el suyo, mas fresco, en su propia
maquina.

### 2. El panel de salida: agarrable y persistente

El divisor vertical entre editor y consola existe y funciona mecanicamente,
pero dos defectos reales lo volvian inutilizable en la practica (medidos con
una repro aislada antes de este cambio):

- El div raiz del `CodeEditor` no tenia `min-h-0`: Monaco se renderizaba 15px
  mas alto que su contenedor y se comia el manubrio.
- Ni el `Panel` del editor ni Monaco recortaban su contenido
  (`overflow: visible`, puesto por la propia libreria `react-resizable-panels`):
  el manubrio quedaba a 2px del borde inferior de Monaco, sin margen de error.
- El manubrio (una rayita de 2px x 48px, color `border-soft`) es practicamente
  invisible sobre el panel oscuro de salida.
- El tamano elegido no se persistia entre sesiones (el patron ED-2 ya existe
  para los 3 paneles horizontales de `EpisodePage`, pero nunca se replico
  para este divisor vertical).

### 3. El autocompletado por palabra: fijar lo implicito

El autocompletado de ceremonia (snippets `print`/`input`/`main`) ya esta hecho
y probado (`pythonSnippets.ts`, `javaSnippets.ts`). Lo que faltaba fijar es el
criterio del docente de la materia, textual: *"obvio no haga toda una
funcion, pero si que le ahorre escribir la misma funcion 90 veces"*. Hoy eso
lo sostiene el **default implicito** de Monaco para `wordBasedSuggestions`, no
una decision escrita en el repo — un upgrade de Monaco o un cambio
descuidado en `SUGERENCIAS_OPTIONS` lo apaga en silencio y nadie se entera
hasta que un alumno lo nota.

## What Changes

### 1. Cuarto candidato en la cascada de siembra: `borradorLocal`

- `cascadaCodigo.ts` — nuevo candidato `borradorLocal`, con la MAYOR
  precedencia (por encima de `snapshot`). Nuevo valor de `OrigenCodigo`:
  `"borrador-local"`.
- `artefactos.ts` — nueva funcion `readArtefactoDraft(scopeId, orden)`:
  lectura puntual de UN borrador (hermana de lectura de
  `collectArtefactoDrafts`, que junta varios ordenes para el submit).
- `EpisodePage.tsx` — resuelve el candidato con la MISMA clave
  (`scopeId`+`orden`) que usa la escritura (`entregaId`+`ejercicioOrden` con
  `ejercicioContext`, `episodeId`+`MONOLITHIC_ORDEN` sin el), y lo acepta
  **solo si `draft.episode_id === episodeId`** — un borrador de OTRO episodio
  se ignora, porque `EpisodeStateResponse` no expone timestamp de
  `last_code_snapshot` y no hay forma de comparar frescura entre episodios
  distintos. Sembrar codigo de otro episodio es la puerta por la que volveria
  ED-4 (ver `openspec/changes/eliminar-ed4-siembra-codigo-previo/`).
- La siembra NO emite `edicion_codigo` (verificado leyendo el codigo: el
  `value` inicial de `editor.create` no dispara `onDidChangeModelContent`,
  y `CodeEditor` solo monta despues de que la hidratacion termino). El codigo
  sembrado, cuando el alumno lo edite despues, entra como `student_typed` —
  correcto, porque es codigo que ese mismo alumno escribio en ese mismo
  episodio. No hizo falta un `origin` nuevo.

### 2. Panel de salida: CSS + persistencia

- `CodeEditor.tsx`, div raiz: agrega `min-h-0`.
- `Panel id="editor-code"`: agrega `style={{ overflow: "hidden" }}`. **No** es
  una clase de Tailwind — la libreria le pone a su div interno un
  `overflow: "auto"` inline por default, y un inline style de la libreria le
  gana a cualquier clase sin `!important`. El `style` prop de `Panel` se
  mergea DESPUES de ese default en el mismo componente: es la unica via que
  lo pisa (verificado leyendo el bundle de `react-resizable-panels`).
- Monaco se crea con `fixedOverflowWidgets: true`: sin esto, el nuevo
  `overflow: hidden` del Panel podria recortar el widget de sugerencias de
  Monaco (que se posiciona `absolute` dentro de su propio contenedor por
  default). Esta opcion lo monta con `position: fixed` en un nodo que ignora
  cualquier `overflow: hidden` ancestro.
- Manubrio: area de agarre mas alta (`h-3` en vez de `h-2`) y grip mas visible
  en reposo (`bg-border-strong` en vez de `bg-border-soft`, que sobre fondo
  claro es casi invisible), siguiendo el lenguaje visual de los divisores
  laterales de `EpisodePage.tsx`.
- Persistencia: `OUTPUT_PANEL_STORAGE_KEY = "web-student.editor.outputPanel.v1"`,
  replicando el patron ED-2 (`readStoredOutputPanelLayout`/
  `persistOutputPanelLayout`, lectura con `useMemo`, escritura en
  `onLayoutChanged`, try/catch en ambas direcciones).

### 3. `wordBasedSuggestions` fijado explicitamente

- `SUGERENCIAS_OPTIONS` en `CodeEditor.tsx` agrega
  `wordBasedSuggestions: "currentDocument"` (no `"matchingDocuments"`: el
  alumno tiene un solo archivo abierto por ejercicio, y `matchingDocuments`
  sugeriria vocabulario de otros ejercicios). Consecuencia declarada: las
  sugerencias por palabra incluyen las palabras del scaffold del docente,
  porque estan en el documento.

## Impact

- `apps/web-student/src/lib/artefactos.ts`
- `apps/web-student/src/lib/cascadaCodigo.ts`
- `apps/web-student/src/pages/EpisodePage.tsx`
- `apps/web-student/src/components/CodeEditor.tsx`
- Tests nuevos: `tests/BorradorLocalAlReabrir.test.tsx`,
  `tests/CodeEditorPanelDeSalida.test.tsx`,
  `tests/CodeEditorSugerenciasPorPalabra.test.tsx`.
- Sin cambios de backend, sin cambios al contrato del CTR, sin cambios a
  prompts del tutor.

## Knowledge Base Impact

Ninguno. Este repo no tiene un directorio `knowledge-base/` generado por
`kb-creator` (verificado: no existe en la raiz del repo) — la documentacion
viva de este proyecto vive en `CLAUDE.md`, `docs/`, y la nota de Obsidian
(`obsidian.md`, fuera de `codigo/`). El cambio es ademas puramente de
frontend, acotado a 3 defectos puntuales de UI/UX sin tocar modelo de datos,
arquitectura de servicios, ni reglas de negocio documentadas centralmente —
no hay documento de esa naturaleza al que esto le cambie la verdad vigente.
