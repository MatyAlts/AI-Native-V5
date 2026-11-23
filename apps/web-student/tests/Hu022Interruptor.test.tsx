/**
 * Aceptacion HU-022, interruptor docente/alumno (orquestador, antes de construir;
 * el constructor no la modifica). Juani (23/11): "no es posible que un docente
 * pueda cambiar el interruptor, de docente a alumno ... para testeo" y "sisi" a
 * los criterios (nivel M).
 *
 * Hoy toda cuenta con comisiones asignadas como docente rebota sola a /teacher/
 * (`main.tsx` y `routes/__root.tsx`, por `GET /comisiones/mis`) y no puede ver
 * el lado del alumno.
 *
 * Contrato (web-student y web-teacher comparten origen, asi que comparten
 * localStorage):
 *  - clave `localStorage["modo-vista"]`: "alumno" | "docente" (ausente = docente).
 *  - `src/utils/modoVista.ts` exporta:
 *      `MODO_VISTA_KEY = "modo-vista"`,
 *      `elegirVistaAlumno(): void`, `elegirPanelDocente(): void`,
 *      `debeIrAlPanelDocente(esDocente: boolean): boolean`.
 *    `main.tsx` y `routes/__root.tsx` redirigen a /teacher/ solo si
 *    `debeIrAlPanelDocente(...)` da true.
 *  - `src/components/BotonVolverPanelDocente.tsx` exporta
 *    `BotonVolverPanelDocente({ esDocente })`: sin `esDocente` no renderiza nada;
 *    con `esDocente` muestra "Volver al panel docente", que guarda "docente" y
 *    hace `window.location.assign("/teacher/")`.
 *
 * C01/C02  Elegir la vista de alumno evita el rebote, y se recuerda.
 * C03      Un docente en la vista de alumno ve "Volver al panel docente".
 * C04      Un alumno comun no ve el interruptor ni rebota nunca.
 * N01      Sin elegir nada, el docente sigue yendo a su panel.
 * N02      Sin inscripciones no hace falta nada nuevo: al no rebotar, el docente
 *          ve la pantalla de codigo de invitacion que ya existe en
 *          `__root.tsx` (POST /comisiones/join) y se inscribe con el codigo
 *          de la comision de prueba. Se verifica en el navegador en la demo.
 */
import { readFileSync } from "node:fs"
import { join } from "node:path"
import { cleanup, fireEvent, render, screen } from "@testing-library/react"
import type { ReactElement } from "react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import * as boton from "../src/components/BotonVolverPanelDocente"
import * as modo from "../src/utils/modoVista"

type Fn = (...a: never[]) => unknown
const f = <T extends Fn>(m: Record<string, unknown>, n: string): T => {
  const v = m[n]
  expect(typeof v, `falta ${n}`).toBe("function")
  return v as T
}

let assign: ReturnType<typeof vi.fn>

beforeEach(() => {
  window.localStorage.clear()
  assign = vi.fn()
  vi.stubGlobal("location", { ...window.location, assign })
})

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  window.localStorage.clear()
})

describe("HU-022 · a donde va un docente", () => {
  it("N01: sin elegir nada, el docente va a su panel", () => {
    const debe = f<(b: boolean) => boolean>(modo, "debeIrAlPanelDocente")
    expect(debe(true)).toBe(true)
  })

  it("C01 y C02: elegir alumno evita el rebote y se guarda", () => {
    const debe = f<(b: boolean) => boolean>(modo, "debeIrAlPanelDocente")
    f<() => void>(modo, "elegirVistaAlumno")()
    expect(window.localStorage.getItem("modo-vista")).toBe("alumno")
    expect(debe(true)).toBe(false)
    f<() => void>(modo, "elegirPanelDocente")()
    expect(debe(true)).toBe(true)
  })

  it("C04: un alumno comun nunca rebota", () => {
    const debe = f<(b: boolean) => boolean>(modo, "debeIrAlPanelDocente")
    expect(debe(false)).toBe(false)
    f<() => void>(modo, "elegirPanelDocente")()
    expect(debe(false)).toBe(false)
  })

  it("C01: los dos puntos de rebote usan la regla", () => {
    for (const archivo of ["src/main.tsx", "src/routes/__root.tsx"]) {
      const src = readFileSync(join(__dirname, "..", archivo), "utf8")
      expect(src, archivo).toMatch(/debeIrAlPanelDocente\(/)
    }
  })
})

describe("HU-022 · boton para volver", () => {
  it("C04: sin ser docente no aparece", () => {
    const Boton = f<(p: { esDocente: boolean }) => ReactElement | null>(
      boton,
      "BotonVolverPanelDocente",
    )
    render(<Boton esDocente={false} />)
    expect(screen.queryByText(/volver al panel docente/i)).toBeNull()
  })

  it("C03: un docente lo ve y vuelve a su panel", () => {
    const Boton = f<(p: { esDocente: boolean }) => ReactElement | null>(
      boton,
      "BotonVolverPanelDocente",
    )
    window.localStorage.setItem("modo-vista", "alumno")
    render(<Boton esDocente={true} />)
    fireEvent.click(screen.getByText(/volver al panel docente/i))
    expect(window.localStorage.getItem("modo-vista")).toBe("docente")
    expect(assign).toHaveBeenCalledWith("/teacher/")
  })
})
