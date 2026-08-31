/**
 * El diálogo de `input()` tiene que SUMAR lo que el programa imprimió, no elegir.
 *
 * EL BUG (QA 2026-08-31, evidencia: grabación de pantalla de un alumno del 28/08)
 * ------------------------------------------------------------------------------
 * En `CodeEditor.tsx` había un `||`:
 *
 *     const guia = inline || outputBufferRef.current.trim()
 *
 * Un `||` es una ALTERNATIVA. Y `inline` es el texto de `input("...")`, que TODO
 * alumno pasa — nadie escribe `input()` pelado. Así que `inline` siempre ganaba
 * el cortocircuito y lo que el programa había impreso no se mostraba NUNCA.
 *
 * La mitigación estaba escrita y era la correcta. Los desarrolladores VIERON el
 * problema. Sólo funcionaba en el único caso que no ocurre.
 *
 * Y hace falta porque `window.prompt` es SÍNCRONO: congela el event loop, React
 * no repinta SALIDA, y los `print()` del programa quedan invisibles hasta que la
 * corrida termina. Sobre el `while True: try: ... except ValueError: print(e)`
 * que enseña la cátedra, el alumno no veía un solo mensaje de error aunque el
 * `except` corriera perfecto. Se reportó como "pide todos los inputs de una y se
 * saltea el try".
 *
 * Estos tests son la razón por la que la función se sacó del `useEffect`: adentro
 * del closure de Pyodide era inejecutable sin bajar 30 MB de CDN, y por eso nadie
 * la había ejercitado nunca.
 */
import { describe, expect, it } from "vitest"
import { MENSAJE_SIN_GUIA, armarMensajeDeInput } from "../src/lib/inputDialogo"

describe("armarMensajeDeInput", () => {
  it("muestra el output pendiente AUNQUE haya prompt inline", () => {
    // El corazón del fix. Verificado por reversión: con el `||`, `pendiente`
    // no aparece y este assert falla.
    const mensaje = armarMensajeDeInput(
      "Error: El nombre no puede quedar vacio.",
      "Ingrese su nombre (Solo letras): ",
    )

    expect(mensaje).toContain("Error: El nombre no puede quedar vacio.")
    expect(mensaje).toContain("Ingrese su nombre (Solo letras):")
  })

  it("pone primero lo que el programa dijo y despues lo que pide", () => {
    // El orden de una consola real: el error de la vuelta anterior, y recién
    // después el pedido nuevo. Al revés se lee como si el error fuera la
    // respuesta al pedido.
    const mensaje = armarMensajeDeInput("Error: no puede quedar vacio.", "Ingrese su nombre: ")

    expect(mensaje.indexOf("Error:")).toBeLessThan(mensaje.indexOf("Ingrese su nombre"))
  })

  it("con solo prompt inline, lo muestra", () => {
    const mensaje = armarMensajeDeInput("", "Ingrese su edad: ")
    expect(mensaje).toContain("Ingrese su edad:")
  })

  it("con solo output pendiente, lo muestra", () => {
    // El caso que el `||` SÍ cubría: `input()` sin argumento. El único que no
    // ocurre en la práctica.
    const mensaje = armarMensajeDeInput("Ingrese su nombre:", "")
    expect(mensaje).toContain("Ingrese su nombre:")
  })

  it("sin nada que decir, cae al mensaje generico", () => {
    expect(armarMensajeDeInput("", "")).toBe(MENSAJE_SIN_GUIA)
    expect(armarMensajeDeInput("   ", "  \n ")).toBe(MENSAJE_SIN_GUIA)
  })

  it("no deja un separador colgando cuando falta una de las dos partes", () => {
    // Un `join` ciego dejaría "\n\n" al principio o al final: una ventana con
    // dos renglones en blanco arriba del texto.
    expect(armarMensajeDeInput("", "Edad: ").startsWith("\n")).toBe(false)
    expect(armarMensajeDeInput("Hola", "").startsWith("\n")).toBe(false)
  })

  it("siempre cierra con la instruccion para el alumno", () => {
    // Sin el pie, la ventana muestra el error del programa y nada que explique
    // qué se espera que el alumno escriba ahí.
    expect(armarMensajeDeInput("algo", "otra cosa")).toContain("Ingresá el dato")
  })

  it("el bucle de la catedra: cada vuelta muestra SU error", () => {
    // La simulación del patrón real. Lo que importa es que el mensaje de la
    // segunda vuelta traiga el error de la primera.
    const primera = armarMensajeDeInput("", "Ingrese su nombre (Solo letras): ")
    const segunda = armarMensajeDeInput(
      "Error: El nombre no puede quedar vacio.",
      "Ingrese su nombre (Solo letras): ",
    )

    expect(primera).not.toContain("Error:")
    expect(segunda).toContain("Error: El nombre no puede quedar vacio.")
  })
})
