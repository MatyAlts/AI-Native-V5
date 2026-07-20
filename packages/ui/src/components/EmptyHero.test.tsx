import { cleanup, fireEvent, render, screen } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { EmptyHero } from "./EmptyHero"

afterEach(() => {
  cleanup()
})

describe("EmptyHero", () => {
  it("renderiza title, description y el icono provisto por el caller", () => {
    render(
      <EmptyHero
        icon={<svg data-testid="hero-icon" />}
        title="Empezá eligiendo una comisión"
        description="Elegí la comisión con la que vas a trabajar."
      />,
    )
    expect(screen.getByText("Empezá eligiendo una comisión")).toBeInTheDocument()
    expect(screen.getByText("Elegí la comisión con la que vas a trabajar.")).toBeInTheDocument()
    expect(screen.getByTestId("hero-icon")).toBeInTheDocument()
  })

  it("dispara primaryAction.onClick cuando se hace click en el CTA", () => {
    const onClick = vi.fn()
    render(
      <EmptyHero
        icon={<svg />}
        title="t"
        description="d"
        primaryAction={{ label: "Ir al panel", onClick }}
      />,
    )
    fireEvent.click(screen.getByRole("button", { name: "Ir al panel" }))
    expect(onClick).toHaveBeenCalledTimes(1)
  })

  it("muestra el hint chico cuando se provee", () => {
    render(
      <EmptyHero icon={<svg />} title="t" description="d" hint="Después podés cambiarla" />,
    )
    expect(screen.getByText("Después podés cambiarla")).toBeInTheDocument()
  })
})
