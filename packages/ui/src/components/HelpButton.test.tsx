import { cleanup, render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, describe, expect, it } from "vitest"
import { HelpButton } from "./HelpButton"

afterEach(() => {
  cleanup()
})

describe("HelpButton", () => {
  it("no muestra el modal inicialmente", () => {
    render(<HelpButton title="Ayuda" content={<p>texto de ayuda</p>} />)
    expect(screen.queryByRole("dialog")).toBeNull()
  })

  it("al hacer click abre el modal con title y content", async () => {
    render(<HelpButton title="Ayuda de Pagina" content={<p>info util</p>} />)
    await userEvent.click(screen.getByRole("button", { name: /ayuda/i }))
    expect(screen.getByRole("dialog")).toBeInTheDocument()
    expect(screen.getByText("Ayuda de Pagina")).toBeInTheDocument()
    expect(screen.getByText("info util")).toBeInTheDocument()
  })

  it("Escape cierra el modal una vez abierto", async () => {
    render(<HelpButton title="T" content={<p>x</p>} />)
    await userEvent.click(screen.getByRole("button", { name: /ayuda/i }))
    expect(screen.getByRole("dialog")).toBeInTheDocument()
    await userEvent.keyboard("{Escape}")
    expect(screen.queryByRole("dialog")).toBeNull()
  })

  it("el modal abierto SIEMPRE tiene max-w-3xl (size xl), sin importar el size del boton", async () => {
    const { rerender } = render(<HelpButton title="T" content={<p>x</p>} size="md" />)
    await userEvent.click(screen.getByRole("button", { name: /ayuda/i }))
    expect(screen.getByRole("dialog").className).toContain("max-w-3xl")

    // cerrar, re-render con size="sm", abrir de nuevo
    await userEvent.keyboard("{Escape}")
    rerender(<HelpButton title="T" content={<p>x</p>} size="sm" />)
    await userEvent.click(screen.getByRole("button", { name: /ayuda/i }))
    expect(screen.getByRole("dialog").className).toContain("max-w-3xl")
  })

  it("size=md (default) aplica clases de boton grande", () => {
    render(<HelpButton title="T" content={<p>x</p>} />)
    const btn = screen.getByRole("button", { name: /ayuda/i })
    expect(btn.className).toContain("h-9")
  })

  it("size=sm aplica clases de boton chico", () => {
    render(<HelpButton title="T" content={<p>x</p>} size="sm" />)
    const btn = screen.getByRole("button", { name: /ayuda/i })
    expect(btn.className).toContain("h-7")
  })

  it("el modal abierto SIEMPRE es variant=dark (el skill asume fondo oscuro para el contenido)", async () => {
    render(<HelpButton title="T" content={<p>x</p>} />)
    await userEvent.click(screen.getByRole("button", { name: /ayuda/i }))
    expect(screen.getByRole("dialog")).toHaveAttribute("data-variant", "dark")
  })
})
