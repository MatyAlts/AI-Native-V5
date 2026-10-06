/**
 * `wordBasedSuggestions`: fijar lo que hoy sostiene un default de Monaco.
 *
 * El autocompletado de ceremonia (snippets de `print`, `input`, `main`, etc.
 * — `pythonSnippets.ts` / `javaSnippets.ts`) ya esta hecho y cubierto por sus
 * propios tests. Lo que faltaba fijar es otra cosa: el criterio del docente
 * de la materia fue literalmente "obvio no haga toda una funcion, pero si que
 * le ahorre escribir la misma funcion 90 veces" — y ESO lo sostiene hoy el
 * default de Monaco para `wordBasedSuggestions` (ya viene prendido), no una
 * decision del repo. Un upgrade de Monaco, o cualquiera que toque
 * `SUGERENCIAS_OPTIONS` sin saber que ese default esta haciendo un trabajo
 * real, lo apaga en silencio y nadie se entera hasta que un alumno lo nota.
 *
 * Por que `"currentDocument"` y no `"matchingDocuments"`
 * --------------------------------------------------------
 * El alumno tiene UN solo archivo abierto por ejercicio. `matchingDocuments`
 * sugeriria palabras de OTROS modelos de Monaco que compartan lenguaje — en
 * este editor eso es compartir vocabulario entre ejercicios o episodios
 * distintos, que no es "ahorrale tipeo" sino "sugerile algo de otro lado".
 * `currentDocument` es la opcion que efectivamente aplica el criterio del
 * docente: solo lo que el YA escribio (el scaffold que dejo, mas lo que el
 * alumno ya tipeo) entra como sugerencia.
 *
 * Consecuencia declarada, no accidente
 * --------------------------------------
 * Con `currentDocument`, las sugerencias por palabra incluyen las palabras
 * del SCAFFOLD que dejo el docente (nombres de funciones, parametros): estan
 * en el documento desde que el editor abre. Es deseable — el alumno no
 * retipea los nombres que la consigna ya le dio — pero es una consecuencia de
 * la opcion elegida, no un efecto colateral sin explicar.
 *
 * El filo del mock (ver `_monacoMock.ts`)
 * ------------------------------------------
 * `editor.create` captura TODO el objeto de opciones en `__opciones`, y es lo
 * unico observable: `updateOptions` es un no-op que DESCARTA su argumento.
 * Una opcion seteada por `updateOptions` pasaria este test en falso. Por eso
 * se afirma sobre `SUGERENCIAS_OPTIONS`, que el componente spreadea dentro de
 * `monaco.editor.create(...)` y nunca pasa por `updateOptions` (eso solo lo
 * usa `fontSize`, para el control ED-3).
 */
import { render, waitFor } from "@testing-library/react"
import { beforeEach, describe, expect, it } from "vitest"
import { CodeEditor, SUGERENCIAS_OPTIONS } from "../src/components/CodeEditor"
import { editoresCreados, resetMonacoMock } from "./_monacoMock"

beforeEach(() => {
  resetMonacoMock()
})

describe("CodeEditor — wordBasedSuggestions, fijado explicitamente", () => {
  it('SUGERENCIAS_OPTIONS declara "currentDocument", no el default implicito', () => {
    expect(SUGERENCIAS_OPTIONS.wordBasedSuggestions).toBe("currentDocument")
  })

  it("Monaco se crea con la opcion puesta — no queda a merced del default de la libreria", async () => {
    render(<CodeEditor initialCode="def resolver():\n    pass\n" language="python" />)
    await waitFor(() => expect(editoresCreados.length).toBeGreaterThanOrEqual(1))
    // Si esto se leyera de `updateOptions` en vez de `create`, el mock lo
    // descarta silenciosamente (ver docstring) y esta linea pasaria igual
    // aunque la opcion nunca llegara a Monaco real.
    expect(editoresCreados[0]?.__opciones.wordBasedSuggestions).toBe("currentDocument")
  })

  it('"matchingDocuments" NO es el valor elegido — sugeriria vocabulario de otros ejercicios', () => {
    // Triangulacion: si alguien "corrige" esto a matchingDocuments pensando
    // que es mas completo, este test lo frena.
    expect(SUGERENCIAS_OPTIONS.wordBasedSuggestions).not.toBe("matchingDocuments")
  })
})
