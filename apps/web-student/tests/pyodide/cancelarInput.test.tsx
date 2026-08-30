/**
 * 🚨 El boton **Cancelar** de la ventanita de `input()`.
 *
 * `askForInput` hace:
 *
 *     const value = window.prompt(mensaje) ?? ""
 *
 * `window.prompt` devuelve `null` cuando el alumno cancela. El `?? ""` lo
 * convierte en cadena vacia ANTES de que Python se entere, con lo cual
 * **cancelar es indistinguible de escribir nada**.
 *
 * Eso, solo, seria una molestia. El problema es la forma que ensena la
 * catedra, que es la misma que usa el alumno del video de produccion:
 *
 *     while True:
 *         dato = input("...")
 *         try:
 *             n = int(dato)
 *             break
 *         except ValueError:
 *             print("Eso no es un numero")
 *
 * Cancelar devuelve `""`, `int("")` levanta `ValueError`, el programa imprime
 * el error y **vuelve a preguntar**. Para siempre. No hay boton para salir:
 * "Ejecutar" y "Probar" estan `disabled` mientras `running`, y no existe un
 * "Detener".
 *
 * Y el watchdog —lo unico que podria cortarlo— NO lo corta, por construccion:
 * `__tutor_input` llama a `_tutor_reset_deadline()` en su `finally`, o sea que
 * **cada input() le regala 5 segundos frescos**. Un bucle que pasa por un
 * input() en cada vuelta nunca acumula 5 s de computo continuo, y por lo tanto
 * el deadline nunca vence. Los tests de abajo lo demuestran de dos maneras
 * independientes: midiendo el deadline desde Python, y dejando correr el bucle
 * mas tiempo del que le alcanza al watchdog para matar un `while True: pass`.
 *
 * Con `tests/_pyodideFake.ts` nada de esto es observable: el doble no ejecuta
 * Python, no tiene watchdog y `input()` no existe.
 */
import { screen } from "@testing-library/react"
import { afterEach, beforeAll, describe, expect, it } from "vitest"
import { botonEjecutar, ejecutar, guionarPrompt, montarEditor } from "./_editorHarness"
import { limpiarGlobals, precalentar } from "./_pyodideReal"

let editor: { desmontar(): void } | null = null

beforeAll(async () => {
  await precalentar()
})

afterEach(async () => {
  editor?.desmontar()
  editor = null
  await limpiarGlobals()
})

/** La forma que ensena la catedra: revalidar en un `while True`. */
const BUCLE_DE_LA_CATEDRA = `while True:
    dato = input("Ingrese un numero entero: ")
    try:
        n = int(dato)
        break
    except ValueError:
        print("Eso no es un numero. Intente de nuevo.")
print("listo:", n)`

/**
 * Marca para salir del bucle desde el test.
 *
 * Se lanza desde el stub de `window.prompt`. Pyodide la convierte en una
 * excepcion Python que NO es `ValueError`, asi que el `except ValueError` del
 * alumno no la traga y el bucle termina. Es el unico "boton de salida" que
 * existe — y no lo tiene el alumno, lo tiene el test.
 */
const CORTE = "CORTE_DEL_TEST"

describe("cancelar la ventanita de input()", () => {
  it("BUG: Cancelar deja al alumno atrapado en el bucle de revalidacion", async () => {
    // El alumno aprieta Cancelar una y otra vez tratando de salir. Cada
    // Cancelar vuelve como "", falla la validacion, y le vuelven a preguntar.
    const INTENTOS = 25
    let cancelaciones = 0
    guionarPrompt([], () => {
      cancelaciones += 1
      if (cancelaciones > INTENTOS) throw new Error(CORTE)
      return null // <- el alumno aprieta Cancelar
    })

    const corridas: Array<{ error: string | null; output: string }> = []
    editor = await montarEditor({
      initialCode: BUCLE_DE_LA_CATEDRA,
      onCodeExecuted: ({ error, output }) => corridas.push({ error, output }),
    })
    await ejecutar()

    // Apretar Cancelar 25 veces no lo saco: siguio preguntando las 25 veces.
    expect(cancelaciones).toBe(INTENTOS + 1)
    const ultima = corridas.at(-1)
    // El programa NO termino por su cuenta: termino porque el TEST lo corto.
    expect(ultima?.error, "el bucle termino solo — el bug esta arreglado?").toContain(CORTE)
    // Y el alumno vio 25 veces el mismo mensaje de error de su propio programa.
    const repeticiones = (ultima?.output.match(/Eso no es un numero/g) ?? []).length
    expect(repeticiones).toBe(INTENTOS)
  })

  it("BUG: cada input() le regala al watchdog 5 s frescos, asi que nunca vence", async () => {
    // La prueba directa del mecanismo, sin esperar reloj: se mira el deadline
    // del watchdog antes y despues de un input(). Si `_tutor_reset_deadline()`
    // lo empuja hacia adelante en CADA vuelta, un bucle con input() adentro no
    // puede acumular los 5 s de computo continuo que el watchdog exige.
    guionarPrompt(["", "", "1"])
    const corridas: string[] = []
    editor = await montarEditor({
      initialCode: `import time
deadlines = []
for _ in range(3):
    input("dato: ")
    deadlines.append(_tutor_watchdog["deadline"] - time.monotonic())
print("restante", [round(d, 1) for d in deadlines])`,
      onCodeExecuted: ({ output }) => corridas.push(output),
    })
    await ejecutar()

    // Las tres veces el presupuesto vuelve a ~5 s: es un reloj que se reinicia,
    // no uno que corre.
    expect(corridas.at(-1)).toContain("restante [5.0, 5.0, 5.0]")
  })

  it("el watchdog SI corta un bucle sin input() (o sea: existe y funciona)", async () => {
    // Control del test de abajo. Sin esto, "no salto el watchdog" podria
    // significar "el watchdog esta roto", no "el watchdog no aplica aca".
    const corridas: Array<{ error: string | null }> = []
    editor = await montarEditor({
      initialCode: "while True:\n    pass",
      onCodeExecuted: ({ error }) => corridas.push({ error }),
    })
    const t0 = Date.now()
    await ejecutar()
    const transcurrido = Date.now() - t0

    expect(corridas.at(-1)?.error).toMatch(/TimeoutError|supero los 5 segundos/)
    expect(transcurrido).toBeGreaterThanOrEqual(4500)
  }, 60_000)

  it("BUG: el mismo bucle CON input() sobrevive mas alla del limite del watchdog", async () => {
    // Mismo `while True`, misma maquina, mas tiempo del que le alcanza al
    // watchdog para matar el `while True: pass` de arriba. Y sigue vivo.
    const LIMITE_MS = 7_000 // > 5 s del watchdog, con margen
    const t0 = Date.now()
    let cancelaciones = 0
    guionarPrompt([], () => {
      cancelaciones += 1
      if (Date.now() - t0 > LIMITE_MS) throw new Error(CORTE)
      return null
    })

    const corridas: Array<{ error: string | null }> = []
    editor = await montarEditor({
      initialCode: BUCLE_DE_LA_CATEDRA,
      onCodeExecuted: ({ error }) => corridas.push({ error }),
    })
    await ejecutar()
    const transcurrido = Date.now() - t0

    expect(transcurrido).toBeGreaterThan(LIMITE_MS)
    // Ni un TimeoutError: el bucle no fue interrumpido por la plataforma.
    expect(corridas.at(-1)?.error).toContain(CORTE)
    expect(corridas.at(-1)?.error).not.toMatch(/Timeout/i)
    // Y no fueron dos vueltas: el alumno estuvo apretando Cancelar todo ese rato.
    expect(cancelaciones).toBeGreaterThan(10)
  }, 60_000)

  it("mientras esta atrapado no hay ningun control para frenarlo", async () => {
    // La otra mitad del problema de producto: aunque el alumno se de cuenta de
    // que esta en un bucle, la UI no le ofrece salida. Los dos unicos botones
    // de corrida estan deshabilitados y no existe un "Detener".
    const visto: { ejecutarDeshabilitado?: boolean; hayDetener?: boolean; fallo?: string } = {}
    guionarPrompt([], () => {
      try {
        visto.ejecutarDeshabilitado = botonEjecutar().disabled
        visto.hayDetener =
          screen.queryAllByRole("button", { name: /detener|frenar|interrumpir|abortar/i }).length >
          0
      } catch (e) {
        visto.fallo = String(e)
      }
      throw new Error(CORTE)
    })

    editor = await montarEditor({ initialCode: BUCLE_DE_LA_CATEDRA })
    await ejecutar()

    expect(visto.fallo).toBeUndefined()
    expect(visto.ejecutarDeshabilitado, "Ejecutar quedo habilitado durante la corrida").toBe(true)
    expect(visto.hayDetener, "aparecio un boton para frenar: el bug esta arreglado?").toBe(false)
  })

  it("la ventanita tampoco le avisa al alumno que cancelar no lo saca", async () => {
    // Lo unico que ve el alumno es el mensaje que arma `askForInput`. Si ahi
    // dijera "cancelar no interrumpe el programa", al menos sabria donde esta.
    const guion = guionarPrompt(["7"])
    editor = await montarEditor({ initialCode: 'x = input("Ingrese un numero: ")' })
    await ejecutar()

    const mensaje = guion.mensajes[0] ?? ""
    expect(mensaje).toContain("Ingrese un numero:")
    expect(mensaje.toLowerCase()).not.toContain("cancelar")
  })
})
