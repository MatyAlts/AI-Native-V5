/**
 * Andamio comun de los tests de Pyodide real: montar el editor de verdad,
 * esperar a que el interprete termine su bootstrap, y guionar `window.prompt`.
 */
import { act, render, screen, waitFor } from "@testing-library/react"
import { expect, vi } from "vitest"
import { CodeEditor, type CodeEditorProps } from "../../src/components/CodeEditor"
import { editoresCreados, resetMonacoMock } from "../_monacoMock"
import { instalarPyodideReal } from "./_pyodideReal"

/**
 * Se busca por `data-tour`, no por nombre accesible: mientras la corrida esta
 * en curso el `aria-label` cambia a "Ejecutando codigo Python", que NO empieza
 * con "Ejecutar" (Ejecutan-do vs Ejecutar). Buscarlo por nombre funciona en
 * reposo y falla justo en el estado que estos tests necesitan observar.
 */
export const botonEjecutar = (): HTMLButtonElement => {
  const b = document.querySelector<HTMLButtonElement>('button[data-tour="ejecutar-codigo"]')
  if (!b) throw new Error("no se encontro el boton Ejecutar")
  return b
}

export const botonProbar = (): HTMLButtonElement =>
  screen.getByTestId("run-tests-button") as HTMLButtonElement

/** Texto que el alumno ve en el panel SALIDA. */
export const salidaVisible = (): string =>
  (screen.getByRole("status").textContent ?? "").replace(/ /g, " ")

/**
 * Monta `CodeEditor` con Pyodide real y espera a que quede operativo.
 *
 * Devuelve el desinstalador del parche de `window.loadPyodide`; el interprete
 * en si se comparte entre montajes (ver `_pyodideReal.ts`).
 */
export async function montarEditor(
  props: Partial<CodeEditorProps> & { initialCode: string },
): Promise<{ desmontar(): void }> {
  resetMonacoMock()
  const real = instalarPyodideReal()
  const { unmount } = render(<CodeEditor language="python" {...props} />)
  await waitFor(() => expect(editoresCreados.length).toBeGreaterThanOrEqual(1))
  // El boton se habilita recien cuando el bootstrap completo (watchdog, guard
  // de imports, runner de tests) corrio contra el interprete real.
  await waitFor(() => expect(botonEjecutar().disabled).toBe(false), { timeout: 60_000 })
  return {
    desmontar() {
      unmount()
      real.desinstalar()
    },
  }
}

/**
 * Aprieta "Ejecutar" y espera a que la corrida TERMINE.
 *
 * El `await act(...)` solo no alcanza: la corrida es una cadena de promesas y
 * act devuelve el control antes de que el `finally` de `runCode` haya corrido.
 * El sintoma es traicionero — `onCodeExecuted` todavia no se llamo y el test
 * afirma sobre un array vacio, o sea que pasa por las razones equivocadas. Se
 * espera a que el boton se vuelva a habilitar, que es la senal de que
 * `running` volvio a false.
 */
export async function ejecutar(): Promise<void> {
  await act(async () => {
    botonEjecutar().click()
  })
  await waitFor(() => expect(botonEjecutar().disabled).toBe(false), { timeout: 60_000 })
}

export async function probar(): Promise<void> {
  await act(async () => {
    botonProbar().click()
  })
  await waitFor(() => expect(botonProbar().disabled).toBe(false), { timeout: 60_000 })
}

export interface GuionPrompt {
  /** Mensajes con los que el programa llamo a `window.prompt`, en orden. */
  mensajes: string[]
  /** Cuantas veces se abrio la ventanita. */
  veces(): number
}

/**
 * Guiona `window.prompt` con una lista de respuestas.
 *
 * `null` en la lista = el alumno apreto **Cancelar** (que es literalmente lo
 * que devuelve el `window.prompt` del navegador en ese caso).
 *
 * Agotada la lista, `sobrante` decide que pasa: por default se lanza, para que
 * un test que pide mas inputs de los que declaro falle en vez de colgarse.
 */
export function guionarPrompt(
  respuestas: readonly (string | null)[],
  sobrante: "lanzar" | (() => string | null) = "lanzar",
): GuionPrompt {
  const mensajes: string[] = []
  let i = 0
  const impl = (mensaje?: string): string | null => {
    mensajes.push(mensaje ?? "")
    if (i < respuestas.length) {
      const r = respuestas[i] as string | null
      i += 1
      return r
    }
    if (sobrante === "lanzar") {
      throw new Error(
        `El programa pidio ${mensajes.length} inputs y el guion declaro ${respuestas.length}.`,
      )
    }
    return sobrante()
  }
  vi.stubGlobal("prompt", impl)
  // jsdom expone `window.prompt` como propia del objeto window; `stubGlobal`
  // sobre globalThis no siempre la alcanza.
  Object.defineProperty(window, "prompt", { value: impl, configurable: true, writable: true })
  return { mensajes, veces: () => mensajes.length }
}
