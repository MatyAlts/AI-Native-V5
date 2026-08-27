// Contenido en espanol SIN tildes para evitar problemas de encoding en Windows/cp1252.
//
// Tests de PERSISTENCIA del tour. El contrato es explicito: la persistencia es un
// detalle reemplazable (hoy localStorage, manana el perfil del usuario), y su fallo
// NUNCA puede romper el onboarding. Si el storage no anda, el tour arranca igual y
// simplemente no recuerda.
//
// Casos cubiertos: storage que tira excepcion (Safari privado, cuota llena, cookies
// bloqueadas) y contenido invalido (JSON corrupto o formato de una version anterior).
import { cleanup, render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { useEffect } from "react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { TourProvider, useTour } from "./TourProvider"
import type { TourFlow } from "./types"

function flujo(id = "flow-persistencia"): TourFlow {
  return {
    id,
    steps: [
      { id: "p1", title: "Paso uno", body: <p>cuerpo uno</p> },
      { id: "p2", title: "Paso dos", body: <p>cuerpo dos</p> },
    ],
  }
}

function Arranque({ flow }: { flow: TourFlow }) {
  const { maybeStart } = useTour()
  useEffect(() => {
    maybeStart(flow)
  }, [flow, maybeStart])
  return null
}

function renderTour(flow: TourFlow) {
  return render(
    <TourProvider navigate={vi.fn()}>
      <Arranque flow={flow} />
    </TourProvider>,
  )
}

/** getItem devuelve siempre lo mismo, sea cual sea la clave. Agnostico del prefijo. */
function storageDevuelve(raw: string | null) {
  vi.spyOn(Storage.prototype, "getItem").mockReturnValue(raw)
}

beforeEach(() => {
  window.localStorage.clear()
})

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  window.localStorage.clear()
})

describe("Persistencia — storage que tira excepcion", () => {
  it("con getItem roto, el tour arranca igual", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("SecurityError: acceso a localStorage denegado")
    })
    renderTour(flujo())
    expect(screen.getByRole("dialog")).toBeInTheDocument()
    expect(screen.getByText("Paso uno")).toBeInTheDocument()
  })

  it("con setItem roto, avanzar de paso no explota", async () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("QuotaExceededError")
    })
    renderTour(flujo())
    await userEvent.click(screen.getByRole("button", { name: /siguiente/i }))
    expect(screen.getByText("Paso dos")).toBeInTheDocument()
  })

  it("con setItem roto, completar el tour no explota y simplemente no recuerda", async () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("QuotaExceededError")
    })
    const f = flujo()
    const primera = renderTour(f)
    await userEvent.click(screen.getByRole("button", { name: /siguiente/i }))
    await userEvent.click(screen.getByRole("button", { name: /^listo$/i }))
    expect(screen.queryByRole("dialog")).toBeNull()
    primera.unmount()

    // No recuerda: es la degradacion aceptada, no un bug.
    renderTour(f)
    expect(screen.getByRole("dialog")).toBeInTheDocument()
  })

  it("con el storage entero roto, saltear con Escape no explota", async () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("SecurityError")
    })
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("SecurityError")
    })
    renderTour(flujo())
    await userEvent.keyboard("{Escape}")
    expect(screen.queryByRole("dialog")).toBeNull()
  })
})

describe("Persistencia — contenido invalido", () => {
  it("JSON corrupto degrada a pendiente y el tour arranca", () => {
    storageDevuelve("{no-es-json")
    renderTour(flujo())
    expect(screen.getByRole("dialog")).toBeInTheDocument()
    expect(screen.getByText("Paso uno")).toBeInTheDocument()
  })

  it("un formato viejo (sin campo estado) degrada a pendiente, no tira", () => {
    storageDevuelve(JSON.stringify({ done: true, currentStep: 5 }))
    renderTour(flujo())
    expect(screen.getByRole("dialog")).toBeInTheDocument()
    expect(screen.getByText("Paso uno")).toBeInTheDocument()
  })

  it("un estado desconocido degrada a pendiente", () => {
    storageDevuelve(JSON.stringify({ estado: "vaya-uno-a-saber" }))
    renderTour(flujo())
    expect(screen.getByRole("dialog")).toBeInTheDocument()
  })

  it("un paso guardado que no existe en el flow no deja el indice fuera de rango", () => {
    storageDevuelve(JSON.stringify({ estado: "pendiente", paso: "paso-que-ya-no-existe" }))
    renderTour(flujo())
    expect(screen.getByText("Paso uno")).toBeInTheDocument()
  })

  it("un valor no-objeto (null serializado) degrada a pendiente", () => {
    storageDevuelve("null")
    renderTour(flujo())
    expect(screen.getByRole("dialog")).toBeInTheDocument()
  })
})
