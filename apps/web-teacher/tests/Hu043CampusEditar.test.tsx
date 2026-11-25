/**
 * Aceptacion HU-043 (orquestador, antes de construir; el constructor no la
 * modifica). Hallazgo de la prueba en produccion del 25/11: en "Campus del
 * curso", "Editar" de una unidad abre el editor DEBAJO de la lista de
 * unidades, fuera de la vista; parece que el boton no hace nada.
 *
 * C02  Tocar "Editar <unidad>" lleva el editor a la vista.
 *
 * Contrato elegido: al tocar "Editar <unidad>" se llama `scrollIntoView` sobre
 * el BLOQUE DEL EDITOR: un elemento que contiene `#campus-introduccion` y NO
 * contiene la lista de unidades (ningun boton "Editar ..."). Asi queda a la
 * vista el titulo de la unidad que se esta editando y no solo el textarea.
 * Las opciones de `scrollIntoView` (block, behavior) quedan libres.
 *
 * Que implementaciones malas descarta:
 *  - Hacer scroll sobre la seccion "Unidades" entera o sobre la pagina: esa
 *    contiene tambien la lista, y su tope es la lista, no el editor.
 *  - Hacer scroll solo cuando el editor se MONTA (un efecto sin dependencia de
 *    la unidad): con el editor ya abierto, tocar "Editar" en OTRA unidad no
 *    movia nada. Por eso se prueba el cambio de una unidad a otra.
 *  - Hacer scroll al montar la vista, antes de tocar nada.
 *
 * `scrollIntoView` no existe en jsdom: se reemplaza en `Element.prototype` por
 * un `vi.fn()` y se lee a que elemento se le llamo (`mock.contexts`).
 */
import { cleanup, fireEvent, screen, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { CampusView } from "../src/views/CampusView"
import { renderWithRouter } from "./_mocks"

const COM = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"

function unidad(id: string, nombre: string, orden: number) {
  return {
    id,
    tenant_id: "t",
    comision_id: COM,
    nombre,
    descripcion: null,
    orden,
    introduccion_html: `<p>Intro de ${nombre}</p>`,
    fecha_apertura: null,
    created_by: "u",
    created_at: "x",
    updated_at: null,
    deleted_at: null,
  }
}

function montar() {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: string | URL | Request) => {
      const url = typeof input === "string" ? input : input.toString()
      const json = (data: unknown) =>
        ({
          ok: true,
          status: 200,
          json: async () => data,
          text: async () => JSON.stringify(data),
        }) as Response
      if (url.includes("/bienvenida")) return json({ html: "" })
      if (url.includes("/api/v1/unidades"))
        return json({
          data: [
            unidad("11111111-1111-1111-1111-111111111111", "Unidad 1", 0),
            unidad("22222222-2222-2222-2222-222222222222", "Unidad 2", 1),
          ],
          meta: { cursor_next: null },
        })
      return json({ data: [], meta: { cursor_next: null } })
    }),
  )
  renderWithRouter(<CampusView comisionId={COM} getToken={async () => "t"} hoy="2026-11-25" />)
}

let scroll: ReturnType<typeof vi.fn>

beforeEach(() => {
  scroll = vi.fn()
  Element.prototype.scrollIntoView = scroll as unknown as Element["scrollIntoView"]
})

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

/** Elementos sobre los que se llamo scrollIntoView y que son el bloque del editor. */
function scrollsAlEditor(): Element[] {
  const intro = document.querySelector("#campus-introduccion")
  return (scroll.mock.contexts as Element[]).filter(
    (el) =>
      el instanceof Element &&
      intro !== null &&
      el.contains(intro) &&
      el.querySelector('button[aria-label^="Editar "]') === null,
  )
}

describe("HU-043 · Editar una unidad lleva el editor a la vista", () => {
  it("C02: tocar Editar hace scroll al bloque del editor", async () => {
    montar()
    const editar = await screen.findByRole("button", { name: "Editar Unidad 1" })
    // Nada se mueve antes de tocar Editar.
    expect(scroll).not.toHaveBeenCalled()

    fireEvent.click(editar)
    await waitFor(() => expect(document.querySelector("#campus-introduccion")).not.toBeNull())
    await waitFor(() => expect(scrollsAlEditor().length).toBeGreaterThanOrEqual(1))
  })

  it("C02: con el editor abierto, Editar en otra unidad vuelve a llevarlo a la vista", async () => {
    montar()
    fireEvent.click(await screen.findByRole("button", { name: "Editar Unidad 1" }))
    await waitFor(() => expect(scrollsAlEditor().length).toBeGreaterThanOrEqual(1))
    const antes = scrollsAlEditor().length

    fireEvent.click(screen.getByRole("button", { name: "Editar Unidad 2" }))
    // El editor ahora es el de la Unidad 2...
    await waitFor(() =>
      expect((document.querySelector("#campus-introduccion") as HTMLTextAreaElement).value).toBe(
        "<p>Intro de Unidad 2</p>",
      ),
    )
    // ...y hubo un scroll nuevo hacia el.
    await waitFor(() => expect(scrollsAlEditor().length).toBeGreaterThan(antes))
  })
})
