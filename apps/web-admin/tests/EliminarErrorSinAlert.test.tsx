// El error al eliminar se muestra en el banner inline de la pagina, nunca con
// `window.alert` (bloqueante, no accesible, y duplicaba el banner que ya existia).
import { ConfirmProvider } from "@platform/ui"
import { cleanup, fireEvent, screen, waitFor } from "@testing-library/react"
import type { ReactNode } from "react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { CarrerasPage } from "../src/pages/CarrerasPage"
import { UniversidadesPage } from "../src/pages/UniversidadesPage"
import { renderConQuery } from "./_mocks"

const UNIVERSIDAD = {
  id: "u1",
  nombre: "UTN Test",
  codigo: "utn",
  dominio_email: null,
  keycloak_realm: "r",
  config: {},
  created_at: "2026-01-01T00:00:00Z",
}
const FACULTAD = { id: "f1", nombre: "Fac", codigo: "f" }
const CARRERA = {
  id: "c1",
  tenant_id: "t",
  universidad_id: "u1",
  facultad_id: "f1",
  nombre: "Tecnicatura",
  codigo: "tup",
  duracion_semestres: 6,
  modalidad: "virtual",
  director_user_id: null,
  created_at: "2026-01-01T00:00:00Z",
}

/** GET devuelve la lista; DELETE falla con el status/detail pedido. */
function stubFetch(
  recurso: "universidades" | "carreras",
  item: unknown,
  status: number,
  detail: string,
) {
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string | URL | Request, init?: RequestInit) => {
      const u = String(url)
      if (init?.method === "DELETE") {
        return Promise.resolve({
          ok: false,
          status,
          statusText: "Error",
          text: () => Promise.resolve(JSON.stringify({ detail })),
        } as Response)
      }
      const data = u.includes(`/${recurso}`) ? [item] : u.includes("/facultades") ? [FACULTAD] : []
      return Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve({ data, meta: { cursor_next: null, total: null } }),
        text: () => Promise.resolve(""),
      } as Response)
    }),
  )
}

function conConfirm(node: ReactNode) {
  return renderConQuery(<ConfirmProvider>{node}</ConfirmProvider>)
}

async function eliminarYConfirmar() {
  fireEvent.click(await screen.findByRole("button", { name: /^eliminar$/i }))
  fireEvent.click(await screen.findByRole("button", { name: /^confirmar$/i }))
}

let alertSpy: ReturnType<typeof vi.spyOn>
beforeEach(() => {
  alertSpy = vi.spyOn(window, "alert").mockImplementation(() => {})
})
afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe("eliminar con error — sin window.alert", () => {
  it("UniversidadesPage muestra el error en el banner inline", async () => {
    stubFetch("universidades", UNIVERSIDAD, 409, "tiene carreras asociadas")
    conConfirm(<UniversidadesPage />)
    await eliminarYConfirmar()
    expect(
      await screen.findByText(/No se pudo eliminar: 409: tiene carreras asociadas/),
    ).toBeVisible()
    await waitFor(() => expect(alertSpy).not.toHaveBeenCalled())
  })

  it("CarrerasPage muestra el error en el banner inline", async () => {
    stubFetch("carreras", CARRERA, 403, "sin permiso")
    conConfirm(<CarrerasPage />)
    await eliminarYConfirmar()
    expect(await screen.findByText(/No se pudo eliminar: 403: sin permiso/)).toBeVisible()
    await waitFor(() => expect(alertSpy).not.toHaveBeenCalled())
  })
})
