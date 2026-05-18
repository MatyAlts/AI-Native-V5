import { cleanup, fireEvent, render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, describe, expect, it, vi } from "vitest"
import { Modal } from "./Modal"

afterEach(() => {
  cleanup()
})

describe("Modal", () => {
  it("no se renderiza cuando isOpen=false", () => {
    render(
      <Modal isOpen={false} onClose={vi.fn()} title="Titulo">
        <p>contenido</p>
      </Modal>,
    )
    expect(screen.queryByRole("dialog")).toBeNull()
  })

  it("se renderiza cuando isOpen=true y muestra title y children", () => {
    render(
      <Modal isOpen={true} onClose={vi.fn()} title="Mi Titulo">
        <p>contenido visible</p>
      </Modal>,
    )
    expect(screen.getByRole("dialog")).toBeInTheDocument()
    expect(screen.getByText("Mi Titulo")).toBeInTheDocument()
    expect(screen.getByText("contenido visible")).toBeInTheDocument()
  })

  it("dispara onClose al presionar Escape", async () => {
    const onClose = vi.fn()
    render(
      <Modal isOpen={true} onClose={onClose} title="T">
        <p>x</p>
      </Modal>,
    )
    await userEvent.keyboard("{Escape}")
    expect(onClose).toHaveBeenCalledOnce()
  })

  it("dispara onClose al click en el backdrop", async () => {
    const onClose = vi.fn()
    render(
      <Modal isOpen={true} onClose={onClose} title="T">
        <p>x</p>
      </Modal>,
    )
    const backdrop = screen.getByTestId("modal-backdrop")
    await userEvent.click(backdrop)
    expect(onClose).toHaveBeenCalledOnce()
  })

  it("NO dispara onClose al click dentro del panel", async () => {
    const onClose = vi.fn()
    render(
      <Modal isOpen={true} onClose={onClose} title="T">
        <p>contenido</p>
      </Modal>,
    )
    await userEvent.click(screen.getByText("contenido"))
    expect(onClose).not.toHaveBeenCalled()
  })

  it("dispara onClose al click en el boton X de cerrar", async () => {
    const onClose = vi.fn()
    render(
      <Modal isOpen={true} onClose={onClose} title="T">
        <p>x</p>
      </Modal>,
    )
    await userEvent.click(screen.getByRole("button", { name: /cerrar/i }))
    expect(onClose).toHaveBeenCalledOnce()
  })

  it.each([
    ["sm", "max-w-md"],
    ["md", "max-w-lg"],
    ["lg", "max-w-2xl"],
    ["xl", "max-w-3xl"],
  ] as const)("aplica %s => clase %s al panel", (size, expectedClass) => {
    render(
      <Modal isOpen={true} onClose={vi.fn()} title="T" size={size}>
        <p>x</p>
      </Modal>,
    )
    const panel = screen.getByRole("dialog")
    expect(panel.className).toContain(expectedClass)
  })

  it("por default usa size md (max-w-lg)", () => {
    render(
      <Modal isOpen={true} onClose={vi.fn()} title="T">
        <p>x</p>
      </Modal>,
    )
    expect(screen.getByRole("dialog").className).toContain("max-w-lg")
  })

  it("expone role=dialog y aria-modal=true", () => {
    render(
      <Modal isOpen={true} onClose={vi.fn()} title="T">
        <p>x</p>
      </Modal>,
    )
    const dialog = screen.getByRole("dialog")
    expect(dialog).toHaveAttribute("aria-modal", "true")
  })

  it("por default usa variant=light (panel surface)", () => {
    render(
      <Modal isOpen={true} onClose={vi.fn()} title="T">
        <p>x</p>
      </Modal>,
    )
    const dialog = screen.getByRole("dialog")
    expect(dialog).toHaveAttribute("data-variant", "light")
    expect(dialog.className).toContain("bg-surface")
  })

  it("variant=dark aplica panel sidebar-bg (cohesión carbón)", () => {
    render(
      <Modal isOpen={true} onClose={vi.fn()} title="T" variant="dark">
        <p>x</p>
      </Modal>,
    )
    const dialog = screen.getByRole("dialog")
    expect(dialog).toHaveAttribute("data-variant", "dark")
    expect(dialog.className).toContain("bg-sidebar-bg")
  })
})

// fireEvent local import-guard (some setups need the symbol referenced)
void fireEvent
