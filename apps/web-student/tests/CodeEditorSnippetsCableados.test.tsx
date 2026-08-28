/**
 * ED-3 — que `CodeEditor` REGISTRE los proveedores de snippets.
 *
 * `javaSnippetsCanonicos.test.ts` y `pythonSnippets.test.ts` prueban lo que los
 * registradores producen: se les inyecta un monaco falso y se les pide las
 * sugerencias. Lo que NINGUNO puede probar es que `CodeEditor` los llame — esos
 * tests le pasan el monaco a mano.
 *
 * Ese hueco es el mutante que sobrevivia: borrar la linea
 * `registerPythonSnippets(monaco, marcarSnippet)` de `CodeEditor` apaga ED-3
 * entero para Python —el alumno pierde TODO el autocompletado— y la suite
 * quedaba en verde, porque el doble de Monaco descartaba el registro
 * (`registerCompletionItemProvider: () => disposable`).
 *
 * No hay funcion pura que extraer acá: la conexion ES un efecto. Lo que se
 * puede anclar es que el efecto ocurrio, y para eso el mock ahora acumula los
 * lenguajes en `lenguajesConSnippets`. Este archivo es lo unico que mira ese
 * registro; sin el, el seam que el coder abrio queda sin usar.
 */

import { render, waitFor } from "@testing-library/react"
import { beforeEach, describe, expect, it } from "vitest"
import { CodeEditor } from "../src/components/CodeEditor"
import { lenguajesConSnippets, resetMonacoMock } from "./_monacoMock"

beforeEach(() => {
  resetMonacoMock()
})

describe("CodeEditor — los proveedores de snippets quedan cableados", () => {
  it("registra java Y python, no uno solo", async () => {
    // Los DOS en la misma asercion a proposito: el bug real fue que se agrego
    // Python y quedo desconectado mientras Java andaba, asi que probar solo
    // "hay algun proveedor" no lo habria agarrado.
    render(<CodeEditor initialCode="x = 1" language="python" />)
    await waitFor(() => expect(lenguajesConSnippets).toContain("java"))
    await waitFor(() => expect(lenguajesConSnippets).toContain("python"))
  })

  it("los registra sin importar el lenguaje del episodio", async () => {
    // El editor no filtra: registra los dos proveedores y Monaco despacha por
    // lenguaje del modelo. Si alguien "optimizara" registrando solo el del
    // episodio, cambiar de ejercicio dentro de la misma pestana dejaria al
    // alumno sin snippets hasta recargar.
    render(<CodeEditor initialCode="class Main {}" language="java" />)
    await waitFor(() => expect([...lenguajesConSnippets].sort()).toEqual(["java", "python"]))
  })

  it("un re-montaje vuelve a registrarlos (los disposables no dejan el editor mudo)", async () => {
    // El efecto que los registra devuelve disposables que se limpian al
    // desmontar. Si el registro quedara fuera del ciclo —o si el cleanup
    // corriera sin volver a registrar— el editor sobrevive al re-montaje del
    // breakpoint mobile sin autocompletado.
    const { unmount } = render(<CodeEditor initialCode="x = 1" language="python" />)
    await waitFor(() => expect(lenguajesConSnippets.length).toBe(2))
    unmount()

    resetMonacoMock()
    render(<CodeEditor initialCode="x = 1" language="python" />)
    await waitFor(() => expect([...lenguajesConSnippets].sort()).toEqual(["java", "python"]))
  })
})
