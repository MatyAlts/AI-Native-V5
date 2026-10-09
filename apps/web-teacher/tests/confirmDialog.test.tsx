/**
 * Hallazgo #15 (QA 08/10): las acciones destructivas usaban `window.confirm`
 * nativo (feo, inconsistente con el DS, bloqueante). Ahora usan `useConfirm`
 * del DS. Lo que se fija: (1) nunca se llama a window.confirm, (2) no se
 * ejecuta la accion hasta confirmar en el dialogo, (3) cancelar no ejecuta.
 */
import { cleanup, fireEvent, screen, waitFor } from "@testing-library/react"
import { type Mock, afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { ActiveIAView } from "../src/views/ActiveIAView"
import { TareasPracticasView } from "../src/views/TareasPracticasView"
import { renderWithRouter, setupFetchMock } from "./_mocks"

const COMISION = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
const getToken = async () => "tok"

let confirmSpy: ReturnType<typeof vi.spyOn>

beforeEach(() => {
  confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true)
})

afterEach(() => {
  cleanup()
  confirmSpy.mockRestore()
  vi.unstubAllGlobals()
})

function llamadasConMetodo(metodo: string) {
  return (fetch as unknown as Mock).mock.calls.filter(
    ([, init]) => (init as RequestInit | undefined)?.method === metodo,
  )
}

const tp = (over: Record<string, unknown>) => ({
  id: "tp-1",
  tenant_id: "t",
  comision_id: COMISION,
  codigo: "TP1",
  titulo: "Primer TP",
  enunciado: "x",
  fecha_inicio: null,
  fecha_fin: null,
  peso: "1.0",
  rubrica: null,
  estado: "draft",
  version: 1,
  parent_tarea_id: null,
  template_id: null,
  has_drift: false,
  created_by: "u",
  created_at: "2026-10-01T00:00:00Z",
  updated_at: "2026-10-01T00:00:00Z",
  unidad_id: null,
  permite_pausa: true,
  ...over,
})

describe("ActiveIAView — desconectar usa el dialogo del DS", () => {
  function montar() {
    setupFetchMock({
      "/api/v1/activeia/credenciales": () => ({
        conectada: true,
        modo_simulado: false,
        username: "docente@utn.edu.ar",
        created_at: "2026-08-18T10:00:00Z",
        last_login_at: "2026-08-18T10:00:00Z",
        last_login_ok: true,
      }),
      "/api/v1/tareas-practicas": () => ({ data: [], meta: { cursor_next: null } }),
    })
    renderWithRouter(<ActiveIAView comisionId={COMISION} getToken={getToken} />)
  }

  it("cancelar en el dialogo NO desconecta, y no se usa window.confirm", async () => {
    montar()
    fireEvent.click(await screen.findByTestId("activeia-desconectar"))
    expect(await screen.findByRole("button", { name: "Cancelar" })).toBeInTheDocument()
    expect(confirmSpy).not.toHaveBeenCalled()
    expect(llamadasConMetodo("DELETE")).toHaveLength(0)
    fireEvent.click(screen.getByRole("button", { name: "Cancelar" }))
    await waitFor(() => expect(screen.queryByRole("button", { name: "Cancelar" })).toBeNull())
    expect(llamadasConMetodo("DELETE")).toHaveLength(0)
  })

  it("confirmar en el dialogo SI desconecta (DELETE)", async () => {
    montar()
    fireEvent.click(await screen.findByTestId("activeia-desconectar"))
    fireEvent.click(await screen.findByRole("button", { name: "Confirmar" }))
    await waitFor(() => expect(llamadasConMetodo("DELETE")).toHaveLength(1))
    expect(confirmSpy).not.toHaveBeenCalled()
  })
})

describe("TareasPracticasView — eliminar/archivar usan el dialogo del DS", () => {
  it("eliminar un borrador: pide confirmacion en el dialogo y recien ahi borra", async () => {
    setupFetchMock({
      "/api/v1/tareas-practicas": () => ({
        data: [tp({ estado: "draft" })],
        meta: { cursor_next: null },
      }),
    })
    renderWithRouter(<TareasPracticasView comisionId={COMISION} getToken={getToken} />)
    fireEvent.click(await screen.findByRole("button", { name: /Eliminar/i }))
    const cancelar = await screen.findByRole("button", { name: "Cancelar" })
    // El dialogo muestra el TP concreto (antes el mensaje se perdia en silencio).
    expect(screen.getByText(/Eliminar el TP "TP1: Primer TP"/)).toBeInTheDocument()
    expect(confirmSpy).not.toHaveBeenCalled()
    expect(llamadasConMetodo("DELETE")).toHaveLength(0)

    fireEvent.click(cancelar)
    await waitFor(() => expect(screen.queryByRole("button", { name: "Cancelar" })).toBeNull())
    expect(llamadasConMetodo("DELETE")).toHaveLength(0)

    fireEvent.click(screen.getByRole("button", { name: /Eliminar/i }))
    fireEvent.click(await screen.findByRole("button", { name: "Confirmar" }))
    await waitFor(() => expect(llamadasConMetodo("DELETE")).toHaveLength(1))
  })

  it("archivar un publicado: mismo flujo (dialogo, sin window.confirm)", async () => {
    setupFetchMock({
      "/api/v1/tareas-practicas": () => ({
        data: [tp({ estado: "published" })],
        meta: { cursor_next: null },
      }),
    })
    renderWithRouter(<TareasPracticasView comisionId={COMISION} getToken={getToken} />)
    fireEvent.click(await screen.findByRole("button", { name: /Archivar/i }))
    expect(await screen.findByText(/Archivar el TP "TP1: Primer TP"/)).toBeInTheDocument()
    fireEvent.click(await screen.findByRole("button", { name: "Confirmar" }))
    await waitFor(() => {
      const posts = llamadasConMetodo("POST").filter(([u]) => String(u).includes("archive"))
      expect(posts.length).toBeGreaterThanOrEqual(1)
    })
    expect(confirmSpy).not.toHaveBeenCalled()
  })
})
