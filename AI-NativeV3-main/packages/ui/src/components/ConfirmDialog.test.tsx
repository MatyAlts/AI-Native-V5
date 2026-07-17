import { cleanup, render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, describe, expect, it, vi } from "vitest"
import { ConfirmProvider, useConfirm } from "./ConfirmDialog"

afterEach(() => {
  cleanup()
})

// Helper: boton que dispara confirm() y reporta el resultado via onResult.
function Trigger({
  onResult,
  tone,
}: {
  onResult: (v: boolean) => void
  tone?: "danger" | "default"
}) {
  const confirm = useConfirm()
  return (
    <button
      type="button"
      onClick={async () => {
        const ok = await confirm({ message: "Borrar el item?", ...(tone ? { tone } : {}) })
        onResult(ok)
      }}
    >
      abrir
    </button>
  )
}

describe("ConfirmDialog / useConfirm", () => {
  it("no muestra el dialogo hasta que se llama confirm()", () => {
    render(
      <ConfirmProvider>
        <Trigger onResult={vi.fn()} />
      </ConfirmProvider>,
    )
    expect(screen.queryByRole("dialog")).toBeNull()
  })

  it("abre el dialogo con el mensaje al llamar confirm()", async () => {
    render(
      <ConfirmProvider>
        <Trigger onResult={vi.fn()} />
      </ConfirmProvider>,
    )
    await userEvent.click(screen.getByRole("button", { name: "abrir" }))
    expect(screen.getByRole("dialog")).toBeInTheDocument()
    expect(screen.getByText("Borrar el item?")).toBeInTheDocument()
  })

  it("resuelve true al confirmar y cierra el dialogo", async () => {
    const onResult = vi.fn()
    render(
      <ConfirmProvider>
        <Trigger onResult={onResult} />
      </ConfirmProvider>,
    )
    await userEvent.click(screen.getByRole("button", { name: "abrir" }))
    await userEvent.click(screen.getByRole("button", { name: "Confirmar" }))
    await waitFor(() => expect(onResult).toHaveBeenCalledWith(true))
    expect(screen.queryByRole("dialog")).toBeNull()
  })

  it("resuelve false al cancelar", async () => {
    const onResult = vi.fn()
    render(
      <ConfirmProvider>
        <Trigger onResult={onResult} />
      </ConfirmProvider>,
    )
    await userEvent.click(screen.getByRole("button", { name: "abrir" }))
    await userEvent.click(screen.getByRole("button", { name: "Cancelar" }))
    await waitFor(() => expect(onResult).toHaveBeenCalledWith(false))
  })

  it("resuelve false al presionar Escape", async () => {
    const onResult = vi.fn()
    render(
      <ConfirmProvider>
        <Trigger onResult={onResult} />
      </ConfirmProvider>,
    )
    await userEvent.click(screen.getByRole("button", { name: "abrir" }))
    await userEvent.keyboard("{Escape}")
    await waitFor(() => expect(onResult).toHaveBeenCalledWith(false))
  })

  it("tone=danger pinta el boton de confirmacion como destructivo", async () => {
    render(
      <ConfirmProvider>
        <Trigger onResult={vi.fn()} tone="danger" />
      </ConfirmProvider>,
    )
    await userEvent.click(screen.getByRole("button", { name: "abrir" }))
    expect(screen.getByRole("button", { name: "Confirmar" }).className).toContain("bg-danger")
  })

  it("useConfirm sin provider lanza error", () => {
    function Bare() {
      useConfirm()
      return null
    }
    const spy = vi.spyOn(console, "error").mockImplementation(() => {})
    expect(() => render(<Bare />)).toThrow(/ConfirmProvider/)
    spy.mockRestore()
  })
})
