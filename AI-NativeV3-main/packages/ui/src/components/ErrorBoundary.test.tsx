import { cleanup, fireEvent, render, screen } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { ErrorBoundary } from "./ErrorBoundary"

function Boom(): never {
  throw new Error("kaboom")
}

afterEach(() => {
  cleanup()
})

describe("ErrorBoundary", () => {
  beforeEach(() => {
    // El boundary loguea el error atrapado; silenciamos el ruido en el test.
    vi.spyOn(console, "error").mockImplementation(() => {})
  })

  it("renderiza los hijos cuando no hay error", () => {
    render(
      <ErrorBoundary>
        <p>contenido ok</p>
      </ErrorBoundary>,
    )
    expect(screen.getByText("contenido ok")).toBeInTheDocument()
  })

  it("un throw en un hijo muestra el fallback (no pantalla en blanco) con role=alert", () => {
    render(
      <ErrorBoundary>
        <Boom />
      </ErrorBoundary>,
    )
    expect(screen.getByRole("alert")).toBeInTheDocument()
    expect(screen.getByText("Algo salio mal")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Reintentar" })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Recargar la pagina" })).toBeInTheDocument()
    expect(console.error).toHaveBeenCalled()
  })

  it("acepta title/description custom en el fallback", () => {
    render(
      <ErrorBoundary title="Falla local" description="Probá de nuevo">
        <Boom />
      </ErrorBoundary>,
    )
    expect(screen.getByText("Falla local")).toBeInTheDocument()
    expect(screen.getByText("Probá de nuevo")).toBeInTheDocument()
  })

  it("Reintentar resetea el boundary y re-renderiza los hijos si el error se resolvio", () => {
    let shouldThrow = true
    function Maybe() {
      if (shouldThrow) throw new Error("transitorio")
      return <p>recuperado</p>
    }
    render(
      <ErrorBoundary>
        <Maybe />
      </ErrorBoundary>,
    )
    expect(screen.getByRole("alert")).toBeInTheDocument()
    shouldThrow = false
    fireEvent.click(screen.getByRole("button", { name: "Reintentar" }))
    expect(screen.getByText("recuperado")).toBeInTheDocument()
  })
})
