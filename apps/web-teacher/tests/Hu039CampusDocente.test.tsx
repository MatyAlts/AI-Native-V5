/**
 * Aceptacion HU-039 (orquestador, antes de construir; el constructor no la
 * modifica). Hallazgos de la recorrida como docente del 25/11 en "Campus del
 * curso":
 *
 * C14  Al aplicar una plantilla, los TPs que no se crearon porque su codigo
 *      ya existe se informan: "No se crearon TP-01, TP-02: ya hay trabajos
 *      prácticos con ese código en esta comisión."
 * C15  En la lista de unidades, una fecha que ya paso dice "Abierta desde el
 *      dd/mm/aaaa" (no "Abre el"); una futura sigue diciendo "Abre el
 *      dd/mm/aaaa"; sin fecha, "Abierta". `textoApertura(fecha, hoy)`
 *      exportada de `CampusView.tsx`; la vista acepta `hoy` ("YYYY-MM-DD")
 *      opcional y por defecto usa el dia de hoy en Argentina.
 * C16  El cartel de "Usar estructura sugerida" se titula "Reemplazar la
 *      introducción" (con tilde).
 */
import { cleanup, fireEvent, screen, waitFor } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { CampusView, textoApertura } from "../src/views/CampusView"
import { renderWithRouter } from "./_mocks"

const COM = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
const P1 = "11111111-aaaa-aaaa-aaaa-111111111111"
const U1 = "11111111-1111-1111-1111-111111111111"

function montar() {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input.toString()
      const method = (init?.method ?? "GET").toUpperCase()
      const json = (data: unknown) =>
        ({
          ok: true,
          status: 200,
          json: async () => data,
          text: async () => JSON.stringify(data),
        }) as Response
      if (url.includes("/aplicar") && method === "POST")
        return json({
          unidades_creadas: 3,
          unidades_omitidas: [],
          tps_creados: 1,
          bienvenida_aplicada: true,
          tps_omitidos: ["TP-01", "TP-02"],
        })
      if (url.includes("/api/v1/plantillas-campus"))
        return json({
          data: [{ id: P1, nombre: "Base", materia_id: "m", created_at: "x" }],
          meta: {},
        })
      if (url.includes("/bienvenida")) return json({ html: "" })
      if (url.includes("/api/v1/unidades"))
        return json({
          data: [
            {
              id: U1,
              tenant_id: "t",
              comision_id: COM,
              nombre: "Unidad 1",
              descripcion: null,
              orden: 0,
              introduccion_html: "<p>Hola</p>",
              fecha_apertura: "2026-11-02",
              created_by: "u",
              created_at: "x",
              updated_at: null,
              deleted_at: null,
            },
          ],
          meta: { cursor_next: null },
        })
      return json({ data: [], meta: { cursor_next: null } })
    }),
  )
  renderWithRouter(<CampusView comisionId={COM} getToken={async () => "t"} hoy="2026-11-25" />)
}

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

describe("HU-039 · pulido del campus del docente", () => {
  it("C15: textoApertura distingue pasada, futura y sin fecha", () => {
    expect(textoApertura("2026-11-02", "2026-11-25")).toBe("Abierta desde el 02/11/2026")
    expect(textoApertura("2026-11-25", "2026-11-25")).toBe("Abierta desde el 25/11/2026")
    expect(textoApertura("2026-12-07", "2026-11-25")).toBe("Abre el 07/12/2026")
    expect(textoApertura(null, "2026-11-25")).toBe("Abierta")
  })

  it("C15: la lista usa la regla", async () => {
    montar()
    expect(await screen.findByText("Abierta desde el 02/11/2026")).toBeTruthy()
  })

  it("C14: informa los TPs que no se crearon", async () => {
    montar()
    const select = (await screen.findByLabelText("Plantilla para aplicar")) as HTMLSelectElement
    await waitFor(() => expect(select.options.length).toBeGreaterThan(0))
    fireEvent.change(select, { target: { value: P1 } })
    fireEvent.click(screen.getByRole("button", { name: "Aplicar plantilla" }))
    expect(
      await screen.findByText(
        "No se crearon TP-01, TP-02: ya hay trabajos prácticos con ese código en esta comisión.",
      ),
    ).toBeTruthy()
  })

  it("C16: el cartel de la estructura sugerida lleva tilde", async () => {
    montar()
    fireEvent.click(await screen.findByRole("button", { name: "Editar Unidad 1" }))
    fireEvent.click(await screen.findByRole("button", { name: "Usar estructura sugerida" }))
    expect(await screen.findByText("Reemplazar la introducción")).toBeTruthy()
  })
})
