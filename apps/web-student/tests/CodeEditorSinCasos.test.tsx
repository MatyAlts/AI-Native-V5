/**
 * "Ejecutar" sobre un ejercicio remoto SIN casos de prueba.
 *
 * Este archivo nacio el 2026-08-28 afirmando que el boton quedaba BLOQUEADO, y
 * ese era el arreglo correcto para el codigo de ese momento: en un lenguaje
 * remoto "Ejecutar" y "Probar" eran la MISMA llamada. El navegador no tiene
 * runtime de Java, asi que la unica corrida posible era contra los casos. Con
 * `test_cases: []` el servidor iteraba sobre una lista vacia, no ejecutaba
 * nada, y devolvia `total=0, passed=0, failed=0` — el `failed == 0` que el
 * labeler traduce a N4 sobre un episodio donde el codigo nunca corrio.
 *
 * El mismo dia, mas tarde, se cerro la causa en vez del sintoma: `modo:
 * "libre"` corre el programa una vez con el stdin del alumno y devuelve su
 * salida, sin evaluar nada y sin emitir conteos. El ciclo
 * escribir-correr-ver-que-sale, que en Python siempre existio, ahora existe
 * tambien en Java — y el boton no tiene por que bloquearse.
 *
 * Asi que los dos primeros tests estan INVERTIDOS respecto de como nacieron:
 * antes afirmaban que no se mandaba nada; ahora afirman que se manda en modo
 * libre. Lo que NO cambio es la propiedad de fondo, y es la que siguen
 * cuidando entre los dos archivos: una corrida sobre un ejercicio sin casos no
 * puede terminar contada como "aprobo todo".
 *
 * El backend la cierra por su lado (`debe_emitir_conteos`, con un test por
 * cada termino). Acá se cuida que el cliente pida el modo correcto: si
 * "Ejecutar" volviera a mandar `tests`, el agujero se reabre desde este lado
 * sin que el backend pueda distinguirlo.
 */
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { CodeEditor } from "../src/components/CodeEditor"
import type { ExecutionResult, TestCasePublic } from "../src/lib/api"
import { runRemote } from "../src/lib/runRemote"
import { editoresCreados, resetMonacoMock } from "./_monacoMock"
import { type PyodideFake, instalarPyodideFake } from "./_pyodideFake"

vi.mock("../src/lib/runRemote", () => ({ runRemote: vi.fn() }))

/** Lo que devuelve el servidor cuando el ejercicio no tiene ni un caso. */
const EJECUCION_SIN_CASOS: ExecutionResult = {
  outcome: "completed",
  total: 0,
  passed: 0,
  failed: 0,
  cases: [],
  compile_output: "",
}

const UN_CASO: TestCasePublic[] = [
  { id: "c1", name: "caso 1", type: "stdin_stdout", code: "", expected: "ok", is_public: true },
]

let pyodide: PyodideFake | null = null

beforeEach(() => {
  resetMonacoMock()
  // Los contadores del mock NO se limpian solos entre tests. Sin esto, si el
  // primer test empieza a llamar a `runRemote` (o sea: si el guard se rompe),
  // el `toHaveBeenCalledTimes(1)` del tercero tambien falla — y el rojo
  // aparecerja en el test equivocado.
  vi.mocked(runRemote).mockReset()
  vi.mocked(runRemote).mockResolvedValue(EJECUCION_SIN_CASOS)
})

afterEach(() => {
  pyodide?.desinstalar()
  pyodide = null
})

async function esperarEditor() {
  await waitFor(() => expect(editoresCreados.length).toBeGreaterThanOrEqual(1))
}

const botonEjecutar = () =>
  screen.getByRole("button", { name: /^Ejecutar/ }) as HTMLButtonElement

describe("Ejecutar en remoto sin casos de prueba", () => {
  it("no manda la corrida (ni con el boton ni con el atajo)", async () => {
    const onCodeExecuted = vi.fn()
    render(
      <CodeEditor
        initialCode="class Main {}"
        language="java"
        ejercicioId="ej-1"
        testCases={[]}
        onCodeExecuted={onCodeExecuted}
      />,
    )
    await esperarEditor()

    await act(async () => {
      botonEjecutar().click()
    })
    // El atajo de teclado NO pasa por el boton deshabilitado: es el camino que
    // se cuela si el guard vive solo en el `disabled`.
    const ed = editoresCreados[0]
    if (!ed) throw new Error("no se creo el editor")
    const atajo = ed.__comandos.get(2048 | 3) // CtrlCmd | Enter
    if (!atajo) throw new Error("no se registro Ctrl+Enter")
    await act(async () => {
      atajo()
    })

    // Dos veces: el boton y el atajo. Los dos tienen que llegar al mismo lado
    // — el guard viejo vivia en el `disabled` y el atajo se le colaba.
    expect(runRemote).toHaveBeenCalledTimes(2)
    for (const llamada of vi.mocked(runRemote).mock.calls) {
      expect(llamada[0]?.modo).toBe("libre")
    }
    // Y la corrida queda en la trazabilidad como `codigo_ejecutado`, igual que
    // la de Python: no se pierde, cambia de evento.
    expect(onCodeExecuted).toHaveBeenCalled()
  })

  it("el boton esta HABILITADO: sin casos igual se puede correr", async () => {
    render(
      <CodeEditor initialCode="class Main {}" language="java" ejercicioId="ej-1" testCases={[]} />,
    )
    await esperarEditor()
    expect(botonEjecutar().disabled).toBe(false)
  })

  it("el alumno ve lo que imprimio su programa, no un caso", async () => {
    // En libre no hay `cases`: la salida viene en `stdout`. Si el cliente
    // siguiera leyendo `cases[0].got`, la consola quedaria vacia — que es
    // exactamente el sintoma que esta feature vino a sacar.
    vi.mocked(runRemote).mockResolvedValue({
      ...EJECUCION_SIN_CASOS,
      modo: "libre",
      stdout: "hola mundo\n",
    })
    render(
      <CodeEditor initialCode="class Main {}" language="java" ejercicioId="ej-1" testCases={[]} />,
    )
    await esperarEditor()
    await act(async () => {
      botonEjecutar().click()
    })
    await waitFor(() => expect(screen.getByText(/hola mundo/)).toBeTruthy())
  })

  it("la entrada que escribe el alumno viaja con la corrida", async () => {
    render(
      <CodeEditor initialCode="class Main {}" language="java" ejercicioId="ej-1" testCases={[]} />,
    )
    await esperarEditor()
    const entrada = screen.getByLabelText(/entrada del programa/i)
    // `fireEvent.change` y no asignar `.value`: el textarea es controlado, y
    // escribirle la propiedad directo no pasa por el setter de React — el
    // estado queda en "" y el test verifica el DOM, no el componente.
    await act(async () => {
      fireEvent.change(entrada, { target: { value: "42\nJuani\n" } })
    })
    await act(async () => {
      botonEjecutar().click()
    })
    expect(vi.mocked(runRemote).mock.calls[0]?.[0]?.stdin).toBe("42\nJuani\n")
  })

  it("con casos publicos, 'Ejecutar' SIGUE siendo libre (no corre los tests)", async () => {
    // La separacion es el punto: "Ejecutar" corre el programa, "Probar" corre
    // los casos. Que el ejercicio TENGA casos no convierte a "Ejecutar" en
    // "Probar" — si asi fuera, volveriamos al estado en que los dos botones
    // hacian lo mismo.
    const onCodeExecuted = vi.fn()
    render(
      <CodeEditor
        initialCode="class Main {}"
        language="java"
        ejercicioId="ej-1"
        testCases={UN_CASO}
        onCodeExecuted={onCodeExecuted}
      />,
    )
    await esperarEditor()
    expect(botonEjecutar().disabled).toBe(false)
    await act(async () => {
      botonEjecutar().click()
    })
    expect(runRemote).toHaveBeenCalledTimes(1)
    expect(vi.mocked(runRemote).mock.calls[0]?.[0]?.modo).toBe("libre")
  })
})

describe("Ejecutar en local sigue sin pedir casos", () => {
  it("Python sin test_cases ejecuta igual: no hay tests de por medio", async () => {
    // En Pyodide "Ejecutar" corre el codigo suelto del alumno y le muestra su
    // stdout. No emite conteo de tests, asi que no puede inventar un "paso
    // todo". Pedirle casos seria romperle la herramienta principal al alumno.
    pyodide = instalarPyodideFake()
    const onCodeExecuted = vi.fn()
    render(
      <CodeEditor
        initialCode="print('hola')"
        language="python"
        testCases={[]}
        onCodeExecuted={onCodeExecuted}
      />,
    )
    await esperarEditor()
    await waitFor(() => expect(botonEjecutar().disabled).toBe(false))
    await act(async () => {
      botonEjecutar().click()
    })
    await waitFor(() => expect(onCodeExecuted).toHaveBeenCalledTimes(1))
  })
})
