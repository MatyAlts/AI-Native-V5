/**
 * BUG-01: "Nuevo TP" arrastraba los datos del TP anterior.
 *
 * `TareaFormModal` en modo "create" quedaba SIEMPRE montado en el JSX (solo el
 * prop `isOpen` cambiaba entre true/false) mientras que las demas variantes
 * (edit, versioning, etc.) se renderizan condicionalmente (`{modal.kind ===
 * "edit" && <TareaFormModal .../>}`). Como `useState(initial?.codigo ?? "")`
 * solo corre al MONTAR, cerrar el modal de crear y volver a abrirlo dejaba el
 * codigo/titulo/fechas tipeados la vez anterior.
 */
import { cleanup, fireEvent, screen, waitFor } from "@testing-library/react"
import { afterEach, describe, expect, it } from "vitest"
import { TareasPracticasView } from "../src/views/TareasPracticasView"
import { renderWithRouter, setupFetchMock } from "./_mocks"

const COMISION_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"

afterEach(() => {
  cleanup()
})

/** El header siempre renderiza "Nuevo TP" primero en el DOM; el empty-state
 * agrega un segundo boton con el mismo nombre cuando la lista esta vacia. */
function clickNuevoTp() {
  const botones = screen.getAllByRole("button", { name: /Nuevo TP/i })
  fireEvent.click(botones[0])
}

describe("TareasPracticasView — BUG-01 el form de crear no arrastra datos", () => {
  it("el segundo 'Nuevo TP' abre con el codigo vacio tras cancelar el primero", async () => {
    setupFetchMock({})
    renderWithRouter(
      <TareasPracticasView comisionId={COMISION_ID} getToken={async () => "tok"} />,
    )

    await waitFor(() => {
      expect(screen.getAllByRole("button", { name: /Nuevo TP/i }).length).toBeGreaterThan(0)
    })

    clickNuevoTp()
    const primerCodigo = (await screen.findByTestId("tp-form-codigo")) as HTMLInputElement
    fireEvent.change(primerCodigo, { target: { value: "TP-VIEJO" } })
    expect(primerCodigo.value).toBe("TP-VIEJO")

    fireEvent.click(screen.getByRole("button", { name: "Cerrar" }))
    await waitFor(() => {
      expect(screen.queryByTestId("tp-form-codigo")).toBeNull()
    })

    clickNuevoTp()
    const segundoCodigo = (await screen.findByTestId("tp-form-codigo")) as HTMLInputElement
    expect(segundoCodigo.value).toBe("")
  })

  it("tambien resetea titulo y 'permite pausa' (no es un parche solo para codigo)", async () => {
    setupFetchMock({})
    renderWithRouter(
      <TareasPracticasView comisionId={COMISION_ID} getToken={async () => "tok"} />,
    )

    await waitFor(() => {
      expect(screen.getAllByRole("button", { name: /Nuevo TP/i }).length).toBeGreaterThan(0)
    })

    clickNuevoTp()
    const tituloInput = (await screen.findByTestId("tp-form-titulo")) as HTMLInputElement
    const permitePausaCheckbox = screen.getByTestId("tp-form-permite-pausa") as HTMLInputElement
    expect(permitePausaCheckbox.checked).toBe(true) // default

    fireEvent.change(tituloInput, { target: { value: "Titulo del TP anterior" } })
    fireEvent.click(permitePausaCheckbox)
    expect(tituloInput.value).toBe("Titulo del TP anterior")
    expect(permitePausaCheckbox.checked).toBe(false)

    fireEvent.click(screen.getByRole("button", { name: "Cerrar" }))
    await waitFor(() => {
      expect(screen.queryByTestId("tp-form-titulo")).toBeNull()
    })

    clickNuevoTp()
    const tituloSegundo = (await screen.findByTestId("tp-form-titulo")) as HTMLInputElement
    const permitePausaSegundo = screen.getByTestId("tp-form-permite-pausa") as HTMLInputElement
    expect(tituloSegundo.value).toBe("")
    expect(permitePausaSegundo.checked).toBe(true)
  })
})
