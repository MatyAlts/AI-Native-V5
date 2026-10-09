/**
 * Hallazgo #15 (QA 08/10): UnidadesView avisaba los errores de escritura con
 * `alert()` nativo. Ahora los muestra inline (banner), sin bloquear la pagina.
 */
import { cleanup, fireEvent, screen, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { UnidadesView } from "../src/views/UnidadesView"
import { renderWithRouter } from "./_mocks"

const COMISION = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
const getToken = async () => "tok"

const json = (body: unknown, status = 200) =>
  Promise.resolve(
    new Response(JSON.stringify(body), {
      status,
      headers: { "Content-Type": "application/json" },
    }),
  )

const unidad = {
  id: "u1",
  comision_id: COMISION,
  nombre: "Condicionales",
  orden: 1,
  descripcion: null,
}
const tp = {
  id: "tp1",
  codigo: "TP1",
  titulo: "Primer TP",
  estado: "published",
  unidad_id: null,
  comision_id: COMISION,
  version: 1,
}

let alertSpy: ReturnType<typeof vi.spyOn>

function stubFetch(fallaEscritura: { metodo: string; status: number; detail: string }) {
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string | URL | Request, init?: RequestInit) => {
      const u = String(url)
      const m = init?.method ?? "GET"
      if (m === fallaEscritura.metodo) {
        return json({ detail: fallaEscritura.detail }, fallaEscritura.status)
      }
      if (u.includes("/api/v1/unidades")) return json({ data: [unidad] })
      if (u.includes("/api/v1/tareas-practicas"))
        return json({ data: [tp], meta: { cursor_next: null } })
      return json({ data: [], meta: { cursor_next: null } })
    }),
  )
}

beforeEach(() => {
  alertSpy = vi.spyOn(window, "alert").mockImplementation(() => {})
})
afterEach(() => {
  cleanup()
  alertSpy.mockRestore()
  vi.unstubAllGlobals()
})

describe("UnidadesView — errores de escritura inline", () => {
  it("crear unidad que falla: banner con el detalle, sin alert()", async () => {
    stubFetch({ metodo: "POST", status: 409, detail: "ya existe una unidad con ese nombre" })
    renderWithRouter(<UnidadesView comisionId={COMISION} getToken={getToken} />)
    fireEvent.click(await screen.findByRole("button", { name: /Nueva unidad/i }))
    fireEvent.change(await screen.findByLabelText(/Nombre/i), { target: { value: "Bucles" } })
    fireEvent.click(screen.getByRole("button", { name: "Guardar" }))

    const banner = await screen.findByTestId("unidades-action-error")
    expect(banner).toHaveTextContent(/crear unidad/i)
    expect(banner).toHaveTextContent(/ya existe una unidad/i)
    expect(alertSpy).not.toHaveBeenCalled()
  })

  it("asignar TP que falla: banner distinto (asignar), sin alert()", async () => {
    stubFetch({ metodo: "PATCH", status: 403, detail: "sin permiso para editar el TP" })
    renderWithRouter(<UnidadesView comisionId={COMISION} getToken={getToken} />)
    fireEvent.click(await screen.findByRole("button", { name: /Sin unidad/i }))
    const select = await screen.findByRole("combobox")
    fireEvent.change(select, { target: { value: "u1" } })

    const banner = await screen.findByTestId("unidades-action-error")
    expect(banner).toHaveTextContent(/asignar TP/i)
    expect(banner).toHaveTextContent(/sin permiso/i)
    expect(alertSpy).not.toHaveBeenCalled()
  })

  it("el banner se puede cerrar", async () => {
    stubFetch({ metodo: "PATCH", status: 500, detail: "boom" })
    renderWithRouter(<UnidadesView comisionId={COMISION} getToken={getToken} />)
    fireEvent.click(await screen.findByRole("button", { name: /Sin unidad/i }))
    fireEvent.change(await screen.findByRole("combobox"), { target: { value: "u1" } })
    await screen.findByTestId("unidades-action-error")
    fireEvent.click(screen.getByRole("button", { name: /Cerrar aviso/i }))
    await waitFor(() => expect(screen.queryByTestId("unidades-action-error")).toBeNull())
  })
})
