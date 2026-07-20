import { cleanup, render, screen } from "@testing-library/react"
import { afterEach, describe, expect, it } from "vitest"
import { StateMessage } from "./StateMessage"

afterEach(() => {
  cleanup()
})

describe("StateMessage", () => {
  it("variant=loading muestra spinner y titulo por default", () => {
    render(<StateMessage variant="loading" />)
    expect(screen.getByRole("status")).toBeInTheDocument()
    expect(screen.getByTestId("state-spinner")).toBeInTheDocument()
    expect(screen.getByText("Cargando...")).toBeInTheDocument()
  })

  it("variant=empty muestra borde dashed y mensaje 'Sin datos' por default", () => {
    render(<StateMessage variant="empty" description="No hay episodios todavia" />)
    const node = screen.getByRole("status")
    expect(node).toHaveAttribute("data-variant", "empty")
    expect(node.className).toContain("border-dashed")
    expect(screen.getByText("Sin datos")).toBeInTheDocument()
    expect(screen.getByText("No hay episodios todavia")).toBeInTheDocument()
  })

  it("variant=error usa role=alert y aplica el token de color danger", () => {
    render(
      <StateMessage variant="error" title="No se pudo cargar" description="Reintenta luego" />,
    )
    const node = screen.getByRole("alert")
    expect(node).toHaveAttribute("data-variant", "error")
    expect(screen.getByText("No se pudo cargar")).toBeInTheDocument()
    expect(screen.getByText("Reintenta luego")).toBeInTheDocument()
  })
})
