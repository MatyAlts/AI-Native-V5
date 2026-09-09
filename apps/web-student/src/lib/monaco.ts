/**
 * Carga de Monaco con SOLO los lenguajes que la plataforma enseña.
 *
 * ── El problema ───────────────────────────────────────────────────────────
 * `import("monaco-editor")` resuelve al barrel `esm/vs/editor/editor.main.js`,
 * que son exactamente seis lineas:
 *
 *     import '../basic-languages/monaco.contribution';       // ~80 gramaticas
 *     import '../language/css/monaco.contribution';          // language service
 *     import '../language/html/monaco.contribution';         // language service
 *     import '../language/json/monaco.contribution';         // language service
 *     import '../language/typescript/monaco.contribution';   // language service
 *     export * from './edcore.main';                         // el editor real
 *
 * O sea que el alumno se bajaba la gramatica de ABAP, Solidity, PowerQuery,
 * FreeMarker, Redshift, Postiats, Julia, Scala y otras setenta y pico, mas los
 * language services completos de TypeScript, CSS, HTML y JSON — en una
 * plataforma que enseña Python y Java (ver LANGUAGES_RUNTIME_LOCAL /
 * LANGUAGES_RUNTIME_REMOTO en `components/CodeEditor.tsx`).
 *
 * Medido sobre el build del 2026-09-09: 3,4 MB de JS (856 kB gzip) en ~85
 * chunks, para un editor que necesita dos.
 *
 * ── Por que este corte y no otro ──────────────────────────────────────────
 * Se entra por `edcore.main`, que es `editor.all.js` (las 62 contribuciones de
 * EDICION: find, folding, comentarios, multicursor, suggest, rename, bracket
 * matching…) mas los quick-access, mas `editor.api`. No se pierde una sola
 * funcion del editor: lo unico que queda afuera son gramaticas de lenguajes
 * que nadie abre y los cuatro language services.
 *
 * Armar la lista de contribuciones a mano —la otra forma de adelgazar Monaco—
 * se descarto a proposito: cualquier olvido le saca al alumno el Ctrl+F o el
 * Ctrl+/ sin que ningun test lo note.
 *
 * ── Si algun dia se agrega un lenguaje ────────────────────────────────────
 * Sumar su `.contribution` aca. Sin eso el editor abre igual, pero SIN
 * colores: el `language` que no tiene gramatica registrada cae a texto plano
 * y no falla, no avisa. Es el unico modo de romperse que tiene este archivo.
 */

import type * as Monaco from "monaco-editor"

export type MonacoModule = typeof Monaco

/**
 * Modulo de Monaco, cacheado. Segunda llamada en adelante no vuelve a
 * importar: el `CodeEditor` la invoca desde DOS `useEffect` distintos (crear
 * el editor y registrar los snippets) y sin esto el segundo se quedaria
 * esperando de nuevo la resolucion del chunk.
 */
let cache: Promise<MonacoModule> | null = null

/**
 * Los imports son DINAMICOS, y eso no es estilo: es lo que mantiene a Monaco
 * fuera del bundle de la ruta. Con un `import` estatico arriba, cualquiera que
 * importara `cargarMonaco` se traeria los ~1 MB del editor en su propio chunk
 * — que es justo lo que el `await import()` original del `CodeEditor` estaba
 * evitando, y lo que este archivo no debe romper al centralizarlo.
 *
 * Secuencial y no `Promise.all` a proposito: las gramaticas se registran
 * contra el registry del core, asi que se pide primero el core. Cuesta cero
 * latencia — Vite los agrupa en el mismo chunk, ya estan los dos en red.
 */
export async function cargarMonaco(): Promise<MonacoModule> {
  if (cache) return cache
  cache = (async () => {
    // El core: 62 contribuciones de edicion + quick access + la API.
    const monaco = await import("monaco-editor/esm/vs/editor/edcore.main")
    // Las dos gramaticas que la plataforma usa de verdad.
    await import("monaco-editor/esm/vs/basic-languages/python/python.contribution")
    await import("monaco-editor/esm/vs/basic-languages/java/java.contribution")
    return monaco
  })()
  return cache
}
