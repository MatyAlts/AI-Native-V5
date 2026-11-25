/**
 * Mejoras #49 y #50 del campus (MEJORAS-PLATAFORMA.md), vistas probando el
 * PR #158 en local el 2026-11-25.
 *
 * #49  "Usar estructura sugerida" solo aparece dentro del editor de una unidad
 *      que ya existe. Con la comision sin unidades el docente no lo encontraba:
 *      el aviso ahora linkea a Unidades (con la comision) y explica que el
 *      boton aparece al tocar Editar. Con unidades, una linea lo dice.
 * #50  Aplicar una plantilla sobre la comision de la que salio no crea nada
 *      (no pisa lo existente) y "Se crearon 0" se leia como falla. Cuando el
 *      resultado no cambia nada, se explica por que y que hacer.
 */
import { cleanup, fireEvent, screen, waitFor } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { CampusView, aplicacionSinCambios } from "../src/views/CampusView"
import { renderWithRouter } from "./_mocks"

const COM = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
const P1 = "11111111-aaaa-aaaa-aaaa-111111111111"

const UNIDAD = {
  id: "11111111-1111-1111-1111-111111111111",
  tenant_id: "t",
  comision_id: COM,
  nombre: "Unidad prueba 1",
  descripcion: null,
  orden: 1,
  introduccion_html: null,
  fecha_apertura: null,
}

const SIN_CAMBIOS = {
  unidades_creadas: 0,
  unidades_omitidas: ["Unidad prueba 1"],
  tps_creados: 0,
  bienvenida_aplicada: false,
}

function montar(opciones: { unidades?: unknown[]; aplicacion?: unknown } = {}) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input.toString()
      const method = (init?.method ?? "GET").toUpperCase()
      const json = (status: number, data: unknown) =>
        ({
          ok: status < 400,
          status,
          json: async () => data,
          text: async () => JSON.stringify(data),
        }) as Response
      if (url.includes("/aplicar") && method === "POST") {
        return json(200, opciones.aplicacion ?? SIN_CAMBIOS)
      }
      if (url.includes("/api/v1/plantillas-campus")) {
        return json(200, {
          data: [{ id: P1, nombre: "Mi plantilla", materia_id: "m1", created_at: "2026-11-25" }],
          meta: { cursor_next: null },
        })
      }
      if (url.includes(`/comisiones/${COM}/bienvenida`)) return json(200, { html: "<h1>Hola</h1>" })
      if (url.includes("/api/v1/unidades"))
        return json(200, { data: opciones.unidades ?? [], meta: { cursor_next: null } })
      return json(200, { data: [], meta: { cursor_next: null } })
    }),
  )
  renderWithRouter(<CampusView comisionId={COM} getToken={async () => "t"} />)
}

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

describe("Mejora #49 · encontrar la estructura sugerida", () => {
  it("sin unidades, linkea a Unidades con la comision y explica donde esta el boton", async () => {
    montar({ unidades: [] })
    const link = (await screen.findByRole("link", {
      name: "Crealas en la seccion Unidades",
    })) as HTMLAnchorElement
    expect(link.getAttribute("href")).toContain("/unidades")
    expect(link.getAttribute("href")).toContain(`comisionId=${COM}`)
    expect(screen.getByText(/le cargas la\s+estructura sugerida/)).toBeTruthy()
  })

  it("con unidades, dice que la estructura sugerida esta en Editar", async () => {
    montar({ unidades: [UNIDAD] })
    expect(await screen.findByText(/cargarle la estructura sugerida \(7 secciones\)/)).toBeTruthy()
    expect(screen.queryByRole("link", { name: "Crealas en la seccion Unidades" })).toBeNull()
  })
})

describe("Mejora #50 · aplicar sin cambios no parece una falla", () => {
  it("si no se creo ni cargo nada, explica por que y que hacer", async () => {
    montar({ unidades: [UNIDAD] })
    const select = (await screen.findByLabelText("Plantilla para aplicar")) as HTMLSelectElement
    await waitFor(() => expect(select.value).toBe(P1))
    fireEvent.click(screen.getByRole("button", { name: "Aplicar plantilla" }))
    expect(await screen.findByText(/No cambió nada/)).toBeTruthy()
    expect(screen.getByText(/cambiá a otra comisión de la materia/)).toBeTruthy()
  })

  it("si la aplicacion creo algo, no muestra el aviso", async () => {
    montar({
      unidades: [UNIDAD],
      aplicacion: { ...SIN_CAMBIOS, unidades_creadas: 1, unidades_omitidas: [] },
    })
    const select = (await screen.findByLabelText("Plantilla para aplicar")) as HTMLSelectElement
    await waitFor(() => expect(select.value).toBe(P1))
    fireEvent.click(screen.getByRole("button", { name: "Aplicar plantilla" }))
    expect(
      await screen.findByText("Se crearon 1 unidad y 0 trabajos prácticos en borrador."),
    ).toBeTruthy()
    expect(screen.queryByText(/No cambió nada/)).toBeNull()
  })

  it("aplicacionSinCambios: solo la bienvenida ya cuenta como cambio", () => {
    expect(aplicacionSinCambios(SIN_CAMBIOS)).toBe(true)
    expect(aplicacionSinCambios({ ...SIN_CAMBIOS, bienvenida_aplicada: true })).toBe(false)
    expect(aplicacionSinCambios({ ...SIN_CAMBIOS, tps_creados: 2 })).toBe(false)
  })
})
