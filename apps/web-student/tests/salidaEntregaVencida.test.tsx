/**
 * Apoyo de HU-016 (R05): al salir de una TP de un solo ejercicio, si la entrega
 * automatica se rechazo por plazo, el alumno llega a la home con el aviso
 * (`?aviso=plazo-vencido`), sin `alert()` y sin trabar la salida.
 *
 * `episodio.$id.tsx` hace `navigate(destinoAlSalir(await enviarEntregaAlSalir(...)))`.
 * No se monta la ruta: el plugin del router parte el componente en un chunk
 * lazy y la primera carga en frio pasa los 5 s.
 */
import { cleanup, fireEvent, render, screen } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { destinoAlSalir } from "../src/lib/entregaAlSalir"
import { AvisoEntregaVencida } from "../src/routes/index"
import { MENSAJE_ENTREGA_VENCIDA } from "../src/utils/mensajesPlazo"

afterEach(() => cleanup())

describe("destinoAlSalir", () => {
  it("con la entrega vencida va a la home con el aviso", () => {
    expect(destinoAlSalir("vencida")).toEqual({ to: "/", search: { aviso: "plazo-vencido" } })
  })

  it.each(["enviada", "error", "episodio-no-cerrado", "entrega-no-enviable"] as const)(
    "con %s va a la home sin aviso",
    (r) => {
      expect(destinoAlSalir(r)).toEqual({ to: "/", search: {} })
    },
  )
})

describe("AvisoEntregaVencida", () => {
  it("muestra el aviso de plazo y se puede cerrar", () => {
    const onClose = vi.fn()
    render(<AvisoEntregaVencida onClose={onClose} />)
    expect(screen.getByRole("alert").textContent).toContain(MENSAJE_ENTREGA_VENCIDA)
    fireEvent.click(screen.getByLabelText("Cerrar aviso"))
    expect(onClose).toHaveBeenCalled()
  })
})
