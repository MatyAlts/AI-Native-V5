/**
 * El CABLE: que `CodeEditor` de verdad use la decision sobre el timeout.
 *
 * POR QUE EXISTE ESTE ARCHIVO
 * ---------------------------
 * `corridaRemota.test.ts` prueba `mensajeDeCorrida` aislada, y la prueba bien.
 * Pero nadie probaba que el componente la LLAME. Una auditoria adversarial lo
 * midio sobre este mismo PR: revirtiendo SOLO `CodeEditor.tsx` a su version
 * anterior —dejando `corridaRemota.ts` intacta— los 503 tests del frontend
 * seguian en verde con los dos defectos vivos:
 *
 *   - el timeout volvia a ser mudo;
 *   - la corrida cortada volvia a registrarse como exitosa y a viajar asi al
 *     CTR, que es la señal que mira el etiquetador.
 *
 * Es la segunda vez que aparece esta forma: en el PR #86 pasaba lo mismo con
 * `_reabrir_ejercicios` y `return_entrega`. No es descuido de nadie — es una
 * propiedad del codigo: la logica vive enterrada adentro de handlers `async`,
 * sacarla a `lib/` es lo que la vuelve testeable, y el cable que la conecta
 * queda sin red.
 *
 * Estos tests montan el componente y preguntan por lo que el ALUMNO ve y por
 * lo que sale hacia el CTR. Si alguien desconecta la decision, se ponen rojos.
 */
import { act, render, screen, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { CodeEditor } from "../src/components/CodeEditor"
import type { ExecutionResult } from "../src/lib/api"
import { runRemote } from "../src/lib/runRemote"
import { editoresCreados, resetMonacoMock } from "./_monacoMock"

vi.mock("../src/lib/runRemote", () => ({ runRemote: vi.fn() }))

/** Lo que devuelve el servidor cuando mata el contenedor por wall-time.
 *
 * `outcome: "completed"` NO es un descuido del fixture: el payload de modo
 * libre lo manda siempre, y por eso el timeout no entraba por la rama de
 * `infrastructure_failure`. `stderr` vacio tampoco: lo matamos nosotros, no
 * hubo excepcion Java que parsear. Ese par es exactamente el estado en el que
 * el alumno no veia nada. */
const CORTADA_POR_TIMEOUT: ExecutionResult = {
  outcome: "completed",
  total: 0,
  passed: 0,
  failed: 0,
  cases: [],
  compile_output: "",
  stdout: "1\n2\n3\n",
  stderr: "",
  timed_out: true,
} as unknown as ExecutionResult

const TERMINO_BIEN: ExecutionResult = {
  ...CORTADA_POR_TIMEOUT,
  stdout: "listo\n",
  timed_out: false,
} as unknown as ExecutionResult

beforeEach(() => {
  resetMonacoMock()
  vi.mocked(runRemote).mockReset()
})

afterEach(() => {
  vi.restoreAllMocks()
})

async function correr(props: Record<string, unknown> = {}) {
  const onCodeExecuted = vi.fn()
  render(
    <CodeEditor
      initialCode="class Main {}"
      language="java"
      ejercicioId="ej-timeout"
      testCases={[]}
      onCodeExecuted={onCodeExecuted}
      {...props}
    />,
  )
  await waitFor(() => expect(editoresCreados.length).toBeGreaterThanOrEqual(1))
  await act(async () => {
    ;(screen.getByRole("button", { name: /^Ejecutar/ }) as HTMLButtonElement).click()
  })
  return onCodeExecuted
}

describe("una corrida remota cortada por timeout", () => {
  it("le DICE al alumno que se corto — el sintoma que reporto Prog 2", async () => {
    vi.mocked(runRemote).mockResolvedValue(CORTADA_POR_TIMEOUT)

    await correr()

    // Lo que ve en pantalla, no lo que devuelve una funcion pura.
    expect(await screen.findByText(/supero el limite de tiempo/i)).toBeTruthy()
  })

  it("NO la registra como exitosa: el CTR recibe el error", async () => {
    vi.mocked(runRemote).mockResolvedValue(CORTADA_POR_TIMEOUT)

    const onCodeExecuted = await correr()

    // `codigo_ejecutado` es una de las señales que mira el etiquetador. Un
    // evento que dice "ejecuto bien" sobre un programa que no termino
    // contamina la traza, y la cadena es append-only: no se corrige despues.
    await waitFor(() => expect(onCodeExecuted).toHaveBeenCalled())
    const evento = onCodeExecuted.mock.calls[0]?.[0] as { error: string | null; output: string }
    expect(evento.error).toBeTruthy()
    // Y la salida parcial NO se pierde: es lo unico que el alumno tiene para
    // saber hasta donde llego su programa.
    expect(evento.output).toContain("1")
  })

  it("una corrida que termina bien sigue sin mensaje", async () => {
    vi.mocked(runRemote).mockResolvedValue(TERMINO_BIEN)

    const onCodeExecuted = await correr()

    await waitFor(() => expect(onCodeExecuted).toHaveBeenCalled())
    const evento = onCodeExecuted.mock.calls[0]?.[0] as { error: string | null }
    expect(evento.error).toBeNull()
    expect(screen.queryByText(/supero el limite de tiempo/i)).toBeNull()
  })

  it("con la caja Entrada VACIA da la pista del Scanner", async () => {
    vi.mocked(runRemote).mockResolvedValue(CORTADA_POR_TIMEOUT)

    await correr()

    expect(await screen.findByText(/caja "Entrada" esta vacia/i)).toBeTruthy()
  })
})
