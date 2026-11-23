/**
 * Aceptacion HU-022, boton "Ver como alumno" del panel docente (orquestador,
 * antes de construir; el constructor no la modifica). Juani (23/11): "sisi" y
 * "dale" (version chica, nivel M).
 *
 * Contrato (mismo origen que el web-student: comparten localStorage):
 *  - `src/components/BotonVerComoAlumno.tsx` exporta `BotonVerComoAlumno()`:
 *    muestra "Ver como alumno"; al tocarlo guarda
 *    `localStorage["modo-vista"] = "alumno"` y hace `window.location.assign("/")`.
 *  - `src/routes/__root.tsx` lo renderiza (el panel lo muestra siempre: todo el
 *    que entra al panel docente es docente).
 *
 * C01  Desde el panel docente se puede pasar a la vista de alumno.
 */
import { readFileSync } from "node:fs"
import { join } from "node:path"
import { cleanup, fireEvent, render, screen } from "@testing-library/react"
import type { ReactElement } from "react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import * as boton from "../src/components/BotonVerComoAlumno"

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

describe("HU-022 · Ver como alumno", () => {
  it("C01: el boton guarda la eleccion y lleva a la vista de alumno", () => {
    const Boton = (boton as Record<string, unknown>).BotonVerComoAlumno as
      | (() => ReactElement)
      | undefined
    expect(typeof Boton, "falta BotonVerComoAlumno").toBe("function")
    if (!Boton) return
    render(<Boton />)
    fireEvent.click(screen.getByText(/ver como alumno/i))
    expect(window.localStorage.getItem("modo-vista")).toBe("alumno")
    expect(assign).toHaveBeenCalledWith("/")
  })

  it("C01: el panel docente muestra el boton", () => {
    const src = readFileSync(join(__dirname, "..", "src/routes/__root.tsx"), "utf8")
    expect(src).toMatch(/<BotonVerComoAlumno\b/)
  })
})
