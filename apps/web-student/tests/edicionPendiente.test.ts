/**
 * `resolverEdicionPendiente` decide el `origin` de cada `edicion_codigo`, y ese
 * campo es el que el labeler mira para aplicar —o no— el override a N4. O sea
 * que un error aca no rompe la UI: miente sobre el nivel de apropiacion del
 * alumno, en silencio y para siempre, porque la cadena del CTR es inmutable.
 *
 * El archivo no tenia tests. Se agregan junto con `pasted_internal` porque la
 * precedencia pasa de tres casos a cuatro y es justo donde se puede colar una
 * mentira: `pasted_internal` es el alumno reordenando SU codigo (N2) y
 * `pasted_external` es codigo que vino de afuera (N4). Confundirlos invierte el
 * resultado.
 */

import { describe, expect, it } from "vitest"
import { resolverEdicionPendiente } from "../src/lib/edicionPendiente"

const SIN_MARCAS = { paste: null, snippet: false } as const

describe("resolverEdicionPendiente", () => {
  it("no emite nada si el buffer volvio al contenido ya emitido", () => {
    // Tecla + Ctrl+Z dentro de la misma ventana de debounce. Emitirlo meteria
    // un `edicion_codigo` con diff_chars 0 en la cadena.
    expect(resolverEdicionPendiente("x = 1", "x = 1", SIN_MARCAS)).toBeNull()
  })

  it("sin marcas, el origen es tipeo del alumno", () => {
    const e = resolverEdicionPendiente("x = 12", "x = 1", SIN_MARCAS)
    expect(e?.origin).toBe("student_typed")
  })

  it("un pegado INTERNO es pasted_internal", () => {
    const e = resolverEdicionPendiente("x = 1\nx = 1", "x = 1", {
      paste: "interno",
      snippet: false,
    })
    expect(e?.origin).toBe("pasted_internal")
  })

  it("un pegado EXTERNO es pasted_external", () => {
    const e = resolverEdicionPendiente("x = 1\nfoo()", "x = 1", {
      paste: "externo",
      snippet: false,
    })
    expect(e?.origin).toBe("pasted_external")
  })

  it("una expansion de snippet es snippet_expanded", () => {
    const e = resolverEdicionPendiente("print()", "", { paste: null, snippet: true })
    expect(e?.origin).toBe("snippet_expanded")
  })

  describe("precedencia cuando pasan varias cosas en la misma ventana", () => {
    it("el pegado externo le gana al snippet", () => {
      const e = resolverEdicionPendiente("algo", "", { paste: "externo", snippet: true })
      expect(e?.origin).toBe("pasted_external")
    })

    it("el pegado interno le gana al snippet", () => {
      const e = resolverEdicionPendiente("algo", "", { paste: "interno", snippet: true })
      expect(e?.origin).toBe("pasted_internal")
    })

    it("el pegado EXTERNO le gana al interno", () => {
      // El externo es la unica marca que lleva override a N4. Si en la misma
      // ventana entraron las dos, perder el externo subestima la dependencia
      // del alumno — el error que mas caro sale de los dos posibles.
      const e = resolverEdicionPendiente("algo", "", { paste: "externo", snippet: true })
      expect(e?.origin).toBe("pasted_external")
    })
  })

  it("diffChars es negativo cuando el alumno borro", () => {
    const e = resolverEdicionPendiente("x", "x = 1", SIN_MARCAS)
    expect(e?.diffChars).toBe(-4)
  })

  it("diffChars es el delta contra la ULTIMA emision, no contra cero", () => {
    const e = resolverEdicionPendiente("x = 100", "x = 1", SIN_MARCAS)
    expect(e?.diffChars).toBe(2)
  })
})
