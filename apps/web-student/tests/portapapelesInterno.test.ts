/**
 * Portapapeles interno (change `copiar-pegar-interno-en-el-episodio`).
 *
 * El portapapeles guarda `{texto, origen}` en memoria al copiar dentro de la
 * pagina. Al pegar se compara el contenido real del clipboard contra lo
 * guardado: coincide -> se permite, no coincide -> se bloquea (como hoy).
 *
 * PREGUNTA ABIERTA DEL PROPOSAL: Monaco puede normalizar fin de linea
 * (CRLF vs LF) entre el copiado y el pegado. Si la comparacion fuera byte a
 * byte, un copiado multilinea legitimo con CRLF podria fallar contra lo
 * guardado en LF (o viceversa).
 *
 * DECISION: normalizar CRLF -> LF de LOS DOS LADOS antes de comparar. El
 * fin de linea es un detalle de transporte (SO / clipboard del navegador),
 * no una diferencia de CONTENIDO — dos copias del mismo texto con distinto
 * separador de linea son la misma señal para la tesis. Bloquear por eso
 * seria un falso negativo: un pegado genuinamente interno (consigna ->
 * editor) quedaria indistinguible de un pegado externo, exactamente el
 * error que el change existe para evitar.
 */
import { describe, expect, it } from "vitest"
import { esPegadoValido, normalizarFinDeLinea } from "../src/lib/portapapelesInterno"

describe("normalizarFinDeLinea", () => {
  it("convierte CRLF a LF", () => {
    expect(normalizarFinDeLinea("linea1\r\nlinea2\r\nlinea3")).toBe("linea1\nlinea2\nlinea3")
  })

  it("deja LF intacto (no le agrega ni saca nada)", () => {
    expect(normalizarFinDeLinea("linea1\nlinea2")).toBe("linea1\nlinea2")
  })

  it("texto sin saltos de linea no cambia", () => {
    expect(normalizarFinDeLinea("x = 1")).toBe("x = 1")
  })
})

describe("esPegadoValido", () => {
  it("coincide exacto -> valido", () => {
    expect(esPegadoValido("x = 1", { texto: "x = 1", origen: "editor" })).toBe(true)
  })

  it("nada guardado (portapapeles null) -> invalido", () => {
    expect(esPegadoValido("x = 1", null)).toBe(false)
  })

  it("contenido distinto -> invalido", () => {
    // Esto NO es el caso de normalizacion: son dos contenidos DISTINTOS
    // (no solo distinto fin de linea). Triangula contra el test de arriba
    // para que la normalizacion no degenere en "todo pasa".
    expect(esPegadoValido("import os", { texto: "x = 1", origen: "editor" })).toBe(false)
  })

  it("el pegado llega con CRLF, lo guardado esta en LF -> sigue siendo valido", () => {
    // El caso real: se copio multilinea de la consigna (LF, como vive el
    // markdown en el DOM) y el clipboard del SO devuelve CRLF al pegar.
    const guardado = { texto: "for i in range(3):\n    print(i)", origen: "pagina" as const }
    const pegado = "for i in range(3):\r\n    print(i)"
    expect(esPegadoValido(pegado, guardado)).toBe(true)
  })

  it("el pegado llega en LF, lo guardado esta en CRLF -> tambien valido (simetrico)", () => {
    const guardado = { texto: "a\r\nb\r\nc", origen: "editor" as const }
    const pegado = "a\nb\nc"
    expect(esPegadoValido(pegado, guardado)).toBe(true)
  })

  it("normalizar fin de linea no hace que cualquier cosa matchee: el contenido real difiere", () => {
    // Ancla contra una implementacion tramposa que normalizara de mas (p.ej.
    // comparando solo longitudes, o solo la primera linea).
    const guardado = { texto: "a\r\nb\r\nc", origen: "editor" as const }
    const pegado = "a\nb\nZ"
    expect(esPegadoValido(pegado, guardado)).toBe(false)
  })
})
