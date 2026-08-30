/**
 * Bugs del `input()` interactivo del editor de Python — REPRODUCIDOS, no leidos.
 *
 * Estos tests NO documentan el comportamiento deseado: FIJAN el comportamiento
 * ROTO de hoy. Cada `it` dice, en su nombre, cual es el bug. Cuando alguien lo
 * arregle, el test se pone rojo y ahi se reescribe la expectativa — que es
 * exactamente lo que tiene que pasar.
 *
 * Todos ejercitan el `askForInput` REAL del componente (la closure que vive
 * dentro del effect de carga de Pyodide), no una copia: el doble de Pyodide de
 * este archivo captura la funcion que `CodeEditor` le pasa a
 * `globals.set("__tutor_ask_input", ...)` y a `setStdout({batched})`, y despues
 * la llama como la llamaria el interprete.
 *
 * (El `_pyodideFake.ts` compartido no sirve para esto: su `globals.set` es un
 * no-op y descarta justo la funcion que hay que observar. No se lo toca para no
 * pisarle el trabajo a nadie.)
 */
import { act, render, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { CodeEditor } from "../src/components/CodeEditor"
import { editoresCreados, resetMonacoMock } from "./_monacoMock"

/** Lo que el componente le entrega a Pyodide, capturado para poder llamarlo. */
interface GanchosDelEditor {
  /** El `askForInput` real: recibe el prompt de `input(...)` y devuelve texto. */
  askInput: (prompt: string) => string
  /** El `batched` de `setStdout`: por aca entra cada `print()` del alumno. */
  stdout: (texto: string) => void
  /** El `stdin` crudo (`sys.stdin.read()`), que apunta a `askForInput("")`. */
  stdin: () => string | null
}

let ganchos: GanchosDelEditor
let promptOriginal: typeof window.prompt
/** Se guarda para restaurarlo; `exactOptionalPropertyTypes` no deja asignar
 * `undefined` a la prop opcional, asi que se borra la clave cuando no habia. */
let loadPyodideOriginal: NonNullable<typeof window.loadPyodide> | undefined

function instalarPyodideQueCapturaGanchos() {
  const capturado: Partial<GanchosDelEditor> = {}
  const api = {
    runPythonAsync: async () => undefined,
    setStdout: (o: { batched: (t: string) => void }) => {
      capturado.stdout = o.batched
    },
    setStderr: () => {},
    setStdin: (o: { stdin: () => string | null }) => {
      capturado.stdin = o.stdin
    },
    globals: {
      set: (nombre: string, valor: unknown) => {
        if (nombre === "__tutor_ask_input") {
          capturado.askInput = valor as (p: string) => string
        }
      },
    },
  }
  loadPyodideOriginal = window.loadPyodide
  window.loadPyodide = (async () => api) as unknown as NonNullable<typeof window.loadPyodide>
  return capturado as GanchosDelEditor
}

async function montarEditorPython() {
  const capturado = instalarPyodideQueCapturaGanchos()
  render(<CodeEditor initialCode="x = input()" language="python" testCases={[]} />)
  await waitFor(() => expect(editoresCreados.length).toBeGreaterThanOrEqual(1))
  await waitFor(() => expect(capturado.askInput).toBeTypeOf("function"))
  ganchos = capturado
}

beforeEach(() => {
  resetMonacoMock()
  promptOriginal = window.prompt
})

afterEach(() => {
  window.prompt = promptOriginal
  if (loadPyodideOriginal) {
    window.loadPyodide = loadPyodideOriginal
  } else {
    delete window.loadPyodide
  }
  vi.restoreAllMocks()
})

describe("BUG: Cancelar el cartel de input() es indistinguible de tipear nada", () => {
  it("window.prompt -> null se convierte en cadena vacia, no en 'el alumno quiso salir'", async () => {
    await montarEditorPython()
    // El alumno aprieta Cancelar (o Esc). El navegador devuelve `null`.
    window.prompt = () => null

    let devuelto = "sin llamar"
    await act(async () => {
      devuelto = ganchos.askInput("Precio: ")
    })

    // `?? ""` en CodeEditor.tsx (~askForInput). Para el programa del alumno,
    // cancelar y apretar Aceptar con el campo vacio son EL MISMO evento.
    expect(devuelto).toBe("")
  })

  it("un while-True de validacion vuelve a preguntar para siempre: cancelar no sale", async () => {
    await montarEditorPython()
    let cartelesMostrados = 0
    window.prompt = () => {
      cartelesMostrados += 1
      return null // el alumno cancela SIEMPRE
    }

    // El bucle que ensena la catedra, simulado en JS con el askForInput real:
    //   while True:
    //       try: precio = float(input("Precio: ")); break
    //       except ValueError: print("Eso no es un numero")
    const TOPE = 500 // sin este tope, el test no termina nunca — ese ES el bug
    let vueltas = 0
    await act(async () => {
      while (vueltas < TOPE) {
        vueltas += 1
        const texto = ganchos.askInput("Precio: ")
        const n = texto.trim() === "" ? Number.NaN : Number(texto)
        if (!Number.isNaN(n)) break // nunca pasa: "" no es un numero
        ganchos.stdout("Eso no es un numero. Proba de nuevo.")
      }
    })

    // El bucle no salio solo: lo corto el tope artificial del test.
    expect(vueltas).toBe(TOPE)
    expect(cartelesMostrados).toBe(TOPE)
    // Y en produccion no hay tope: ni boton de Detener en la UI, ni watchdog
    // (se pausa y se reinicia en cada input, ver `__tutor_input`).
  })
})

describe("BUG: input() sin texto muestra TODA la salida acumulada en la ventanita", () => {
  it("el mensaje del cartel crece con cada print y con cada dato ya tipeado", async () => {
    await montarEditorPython()
    const mensajes: string[] = []
    window.prompt = (m?: string) => {
      mensajes.push(m ?? "")
      return "42"
    }

    // Un programa que pide 3 datos con el print aparte y el input pelado
    // (`input()` sin argumento) — como lo escribe medio curso de primer ano.
    await act(async () => {
      for (const eti of ["Ingresa el nombre:", "Ingresa el precio:", "Ingresa el descuento:"]) {
        ganchos.stdout(eti)
        ganchos.askInput("") // input() sin prompt
      }
    })

    expect(mensajes).toHaveLength(3)
    const primero = mensajes[0] as string
    const ultimo = mensajes[2] as string

    // El ultimo cartel arrastra TODO: los tres carteles anteriores y los
    // valores que el alumno ya tipeo.
    expect(ultimo).toContain("Ingresa el nombre:")
    expect(ultimo).toContain("Ingresa el precio:")
    expect(ultimo).toContain("Ingresa el descuento:")
    expect(ultimo).toContain("42") // el eco de lo que ya tipeo
    // El primer cartel tiene una linea de guia; el tercero tiene seis.
    expect(ultimo.length).toBeGreaterThan(primero.length)

    // Y la pregunta REAL queda al FINAL de la pared. (Si el navegador ademas
    // recorta mensajes largos de prompt(), lo que se pierde es justo eso — no
    // esta verificado contra un navegador real.)
    // 5 lineas de historia (3 carteles + 2 ecos) + la linea que pide el dato.
    const lineas = ultimo.split("\n").filter(Boolean)
    expect(lineas.length).toBe(6)
    expect(lineas[0]).toBe("Ingresa el nombre:") // arranca por lo mas viejo
    // La pregunta que importa quedo sepultada en la anteultima linea.
    expect(lineas[4]).toBe("Ingresa el descuento:")
  })

  it("con 14 inputs (el ejercicio 'Caja del Kiosco') el cartel pasa los 400 caracteres y 28 lineas", async () => {
    await montarEditorPython()
    let ultimo = ""
    window.prompt = (m?: string) => {
      ultimo = m ?? ""
      return "10"
    }

    await act(async () => {
      for (let producto = 1; producto <= 7; producto += 1) {
        ganchos.stdout(`Producto ${producto}`)
        ganchos.stdout("Ingresa el nombre:")
        ganchos.askInput("")
        ganchos.stdout("Ingresa el precio:")
        ganchos.askInput("")
      }
    })

    // Medido: 422 caracteres y 29 lineas para 7 productos x 2 datos. En el
    // ejercicio real son ~15 inputs y hay mas texto por producto.
    expect(ultimo.length).toBeGreaterThan(400)
    expect(ultimo.split("\n").filter(Boolean).length).toBeGreaterThanOrEqual(28)
  })
})

describe("BUG: el eco de input() no tiene tope y la consola no se pinta durante la corrida", () => {
  it("cada input agrega al buffer sin limite: 2000 carteles = decenas de KB", async () => {
    await montarEditorPython()
    window.prompt = () => "x"
    await act(async () => {
      for (let i = 0; i < 2000; i += 1) ganchos.askInput("dato: ")
    })

    // La unica forma de leer el buffer desde afuera es el mensaje del cartel
    // cuando no hay prompt inline (`guia = outputBufferRef.current.trim()`).
    let mensajeFinal = ""
    window.prompt = (m?: string) => {
      mensajeFinal = m ?? ""
      return "x"
    }
    await act(async () => {
      ganchos.askInput("")
    })

    // ~8 chars por vuelta ("dato: x\n"): mas de 15 KB metidos en un window.prompt.
    expect(mensajeFinal.length).toBeGreaterThan(15_000)
  })

  it("mientras el programa corre, el <pre> de la consola sigue vacio", async () => {
    await montarEditorPython()
    let consolaDurante = "no se leyo"
    window.prompt = () => {
      // Esto corre DENTRO de la corrida, igual que en el navegador: Pyodide
      // ejecuta sincrono y window.prompt bloquea el event loop, asi que React
      // no repinto nada de lo que el programa ya imprimio.
      consolaDurante = document.body.textContent ?? ""
      return "x"
    }

    await act(async () => {
      ganchos.stdout("Producto 1 cargado")
      ganchos.stdout("Producto 2 cargado")
      ganchos.askInput("")
    })

    expect(consolaDurante).not.toContain("Producto 1 cargado")
  })
})

describe("BUG: sys.stdin.read() crudo pierde toda guia", () => {
  it("el stdin crudo entra por askForInput('') y arrastra el mismo problema", async () => {
    await montarEditorPython()
    const mensajes: string[] = []
    window.prompt = (m?: string) => {
      mensajes.push(m ?? "")
      return null
    }
    let leido: string | null = "sin llamar"
    await act(async () => {
      ganchos.stdout("linea previa")
      leido = ganchos.stdin()
    })

    expect(leido).toBe("") // cancelar tampoco da EOF: da cadena vacia
    expect(mensajes[0]).toContain("linea previa")
  })
})
