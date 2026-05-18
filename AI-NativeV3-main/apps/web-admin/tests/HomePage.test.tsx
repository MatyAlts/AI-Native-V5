import { cleanup, render, screen, waitFor } from "@testing-library/react"
import { afterEach, describe, expect, it } from "vitest"
import { HomePage } from "../src/pages/HomePage"
import { setupFetchMock } from "./_mocks"

afterEach(() => {
  cleanup()
})

describe("HomePage KPI cards", () => {
  it("renderiza 3 KPI cards con counts cuando los 3 endpoints responden", async () => {
    setupFetchMock({
      "/health": () => ({ status: "ready" }),
      "/api/v1/universidades": () => ({ data: [{}, {}], meta: { cursor_next: null } }),
      "/api/v1/comisiones": () => ({ data: [{}, {}, {}], meta: { cursor_next: null } }),
    })

    render(<HomePage />)

    await waitFor(() => {
      expect(screen.getByText("2")).toBeInTheDocument() // Universidades
      expect(screen.getByText("3")).toBeInTheDocument() // Comisiones activas
    })

    expect(screen.getByText("Universidades")).toBeInTheDocument()
    expect(screen.getByText("Comisiones activas")).toBeInTheDocument()
    expect(screen.getByText("Episodios cerrados (últimos 7 días)")).toBeInTheDocument()
    // Tercer card: cae a "—" porque la HomePage no tiene comisión seleccionada.
    expect(screen.getAllByText("—").length).toBeGreaterThanOrEqual(1)
  })

  it("degrada graciosamente cuando un endpoint falla — la card afectada cae a '—' y el resto renderiza", async () => {
    setupFetchMock({
      "/health": () => ({ status: "ready" }),
      "/api/v1/universidades": {
        ok: false,
        status: 500,
        body: () => ({ detail: "internal error" }),
      },
      "/api/v1/comisiones": () => ({ data: [{}], meta: { cursor_next: null } }),
    })

    render(<HomePage />)

    await waitFor(() => {
      // Comisiones renderiza count normal
      expect(screen.getByText("1")).toBeInTheDocument()
    })

    // Universidades cae a "—" porque su endpoint dio 500 — la página NO crashea
    expect(screen.getByText("Universidades")).toBeInTheDocument()
    expect(screen.getAllByText("—").length).toBeGreaterThanOrEqual(1)
  })

  it("NO renderiza KPI card de integrity_compromised (NON-GOAL del proposal)", async () => {
    setupFetchMock({
      "/health": () => ({ status: "ready" }),
      "/api/v1/universidades": () => ({ data: [], meta: { cursor_next: null } }),
      "/api/v1/comisiones": () => ({ data: [], meta: { cursor_next: null } }),
    })

    render(<HomePage />)

    await waitFor(() => {
      expect(screen.getByText("Universidades")).toBeInTheDocument()
    })

    expect(screen.queryByText(/integridad/i)).toBeNull()
    expect(screen.queryByText(/integrity/i)).toBeNull()
    expect(screen.queryByText(/comprometid/i)).toBeNull()
  })
})
