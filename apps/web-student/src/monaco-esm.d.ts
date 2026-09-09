/**
 * Tipos para los subpaths ESM de `monaco-editor`.
 *
 * El paquete publica los `.d.ts` SOLO para su entry principal: los modulos de
 * `esm/vs/**` son `.js` pelados, asi que importarlos directo da TS7016
 * ("implicitly has an 'any' type") y voltea el `tsc -b` del build.
 *
 * Se declaran aca porque `lib/monaco.ts` entra por ahi a proposito — para no
 * arrastrar las ~80 gramaticas del barrel `editor.main`. Ver ese archivo para
 * el porque del corte.
 *
 * `edcore.main` reexporta exactamente la misma API publica que el entry
 * principal (`export * from './editor.api.js'` al final de la cadena), asi que
 * el `export *` de abajo no es una aproximacion: es el tipo correcto.
 */

declare module "monaco-editor/esm/vs/editor/edcore.main" {
  export * from "monaco-editor"
}

// Las contribuciones se importan por su efecto —registrar la gramatica en el
// registry de Monaco— y no exportan nada.
declare module "monaco-editor/esm/vs/basic-languages/python/python.contribution"
declare module "monaco-editor/esm/vs/basic-languages/java/java.contribution"
