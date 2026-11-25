/**
 * Aceptacion HU-036 (orquestador, antes de construir; el constructor no la
 * modifica). Autorizada por Jarvis en nombre de Juani (24/11).
 *
 * En el apartado "Campus del curso" (HU-033) el docente guarda su campus
 * como plantilla de la materia y aplica una plantilla a su comision en un
 * clic. Despues retoca fechas y textos.
 *
 * Contrato que fija esta prueba (dentro de `CampusView`):
 *  - Listado: `GET /api/v1/plantillas-campus?comision_id=<c>` ->
 *    { data: [{ id, nombre, materia_id, created_at }] }.
 *  - Guardar: input con label "Nombre de la plantilla" y boton "Guardar como
 *    plantilla" (deshabilitado con el nombre vacio) -> `POST
 *    /api/v1/plantillas-campus` con { comision_id, nombre }. Exito: el texto
 *    "Plantilla guardada" y la plantilla aparece en el selector.
 *  - Aplicar: <select> con label "Plantilla para aplicar" (una opcion por
 *    plantilla, por nombre) y boton "Aplicar plantilla" -> `POST
 *    /api/v1/plantillas-campus/<id>/aplicar` con { comision_id }. Respuesta
 *    { unidades_creadas, unidades_omitidas, tps_creados, bienvenida_aplicada }.
 *    Se muestra "Se crearon 2 unidades y 4 trabajos prácticos en borrador."
 *    y, si hubo omitidas, "Ya existían y no se tocaron: <nombres separados por
 *    coma>." Despues se recargan las unidades y la bienvenida.
 *  - Sin plantillas: el texto "Todavía no hay plantillas de esta materia".
 *
 * C01  Guardar el campus como plantilla desde el panel.
 * C02  Aplicar una plantilla en un clic y ver que se creo.
 * C03  El selector lista las plantillas de la materia de la comision.
 * N02  Se informa que lo existente no se piso.
 * N06  Sin nombre no se guarda (no hay pedido).
 * N07  Si el servidor rechaza (p. ej. otra materia, 422), se avisa con un
 *      alert y no se muestra el resumen.
 */
import { cleanup, fireEvent, screen, waitFor } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { CampusView } from "../src/views/CampusView"
import { renderWithRouter } from "./_mocks"

const COM = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
const P1 = "11111111-aaaa-aaaa-aaaa-111111111111"
const P2 = "22222222-aaaa-aaaa-aaaa-222222222222"

type Llamada = { url: string; method: string; body: unknown }

function montar(opciones: { plantillas?: unknown[]; rechazarAplicar?: boolean } = {}) {
  const llamadas: Llamada[] = []
  let plantillas = opciones.plantillas ?? [
    { id: P1, nombre: "Prog 1 base 2027", materia_id: "m1", created_at: "2026-11-24T00:00:00Z" },
    { id: P2, nombre: "Prog 1 con PSeInt", materia_id: "m1", created_at: "2026-11-24T00:00:00Z" },
  ]
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input.toString()
      const method = (init?.method ?? "GET").toUpperCase()
      const body = init?.body ? JSON.parse(String(init.body)) : undefined
      llamadas.push({ url, method, body })
      const json = (status: number, data: unknown) =>
        ({
          ok: status < 400,
          status,
          json: async () => data,
          text: async () => JSON.stringify(data),
        }) as Response
      if (url.includes("/aplicar") && method === "POST") {
        if (opciones.rechazarAplicar)
          return json(422, { detail: "La plantilla es de otra materia" })
        return json(200, {
          unidades_creadas: 2,
          unidades_omitidas: ["Unidad 1 · Bienvenida", "Unidad 2 · Secuenciales"],
          tps_creados: 4,
          bienvenida_aplicada: false,
        })
      }
      if (url.includes("/api/v1/plantillas-campus") && method === "POST") {
        const nueva = {
          id: "33333333-aaaa-aaaa-aaaa-333333333333",
          nombre: (body as { nombre: string }).nombre,
          materia_id: "m1",
          created_at: "2026-11-25T00:00:00Z",
        }
        plantillas = [...plantillas, nueva]
        return json(201, nueva)
      }
      if (url.includes("/api/v1/plantillas-campus")) {
        return json(200, { data: plantillas, meta: { cursor_next: null } })
      }
      if (url.includes(`/comisiones/${COM}/bienvenida`)) return json(200, { html: "<h1>Hola</h1>" })
      if (url.includes("/api/v1/unidades"))
        return json(200, { data: [], meta: { cursor_next: null } })
      return json(200, { data: [], meta: { cursor_next: null } })
    }),
  )
  renderWithRouter(<CampusView comisionId={COM} getToken={async () => "t"} />)
  return llamadas
}

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

describe("HU-036 · plantillas de campus en el panel docente", () => {
  it("C03: el selector lista las plantillas de la materia de la comision", async () => {
    const llamadas = montar()
    const select = (await screen.findByLabelText("Plantilla para aplicar")) as HTMLSelectElement
    await waitFor(() => {
      const textos = Array.from(select.options).map((o) => o.textContent)
      expect(textos).toContain("Prog 1 base 2027")
      expect(textos).toContain("Prog 1 con PSeInt")
    })
    const get = llamadas.find(
      (l) => l.method === "GET" && l.url.includes("/api/v1/plantillas-campus"),
    )
    expect(get?.url).toContain(`comision_id=${COM}`)
  })

  it("C03: sin plantillas lo dice", async () => {
    montar({ plantillas: [] })
    expect(await screen.findByText("Todavía no hay plantillas de esta materia")).toBeTruthy()
  })

  it("N06/C01: sin nombre no guarda; con nombre guarda y aparece en el selector", async () => {
    const llamadas = montar()
    const boton = (await screen.findByRole("button", {
      name: "Guardar como plantilla",
    })) as HTMLButtonElement
    expect(boton.disabled).toBe(true)
    fireEvent.click(boton)
    expect(
      llamadas.some((l) => l.method === "POST" && l.url.endsWith("/api/v1/plantillas-campus")),
    ).toBe(false)

    fireEvent.change(screen.getByLabelText("Nombre de la plantilla"), {
      target: { value: "Mi campus 2027" },
    })
    expect(boton.disabled).toBe(false)
    fireEvent.click(boton)
    await waitFor(() => {
      const post = llamadas.find(
        (l) => l.method === "POST" && /\/api\/v1\/plantillas-campus$/.test(l.url),
      )
      expect(post?.body).toEqual({ comision_id: COM, nombre: "Mi campus 2027" })
    })
    expect(await screen.findByText("Plantilla guardada")).toBeTruthy()
    await waitFor(() => {
      const select = screen.getByLabelText("Plantilla para aplicar") as HTMLSelectElement
      expect(Array.from(select.options).map((o) => o.textContent)).toContain("Mi campus 2027")
    })
  })

  it("C02/N02: aplica en un clic, informa lo creado y lo que no se toco, y recarga", async () => {
    const llamadas = montar()
    const select = (await screen.findByLabelText("Plantilla para aplicar")) as HTMLSelectElement
    await waitFor(() => expect(select.options.length).toBeGreaterThanOrEqual(2))
    const opcion = Array.from(select.options).find((o) => o.textContent === "Prog 1 con PSeInt")
    fireEvent.change(select, { target: { value: opcion?.value } })
    const unidadesAntes = llamadas.filter(
      (l) => l.method === "GET" && l.url.includes("/api/v1/unidades"),
    ).length
    fireEvent.click(screen.getByRole("button", { name: "Aplicar plantilla" }))
    await waitFor(() => {
      const post = llamadas.find(
        (l) => l.method === "POST" && l.url.includes(`/api/v1/plantillas-campus/${P2}/aplicar`),
      )
      expect(post?.body).toEqual({ comision_id: COM })
    })
    expect(
      await screen.findByText("Se crearon 2 unidades y 4 trabajos prácticos en borrador."),
    ).toBeTruthy()
    expect(
      screen.getByText(
        "Ya existían y no se tocaron: Unidad 1 · Bienvenida, Unidad 2 · Secuenciales.",
      ),
    ).toBeTruthy()
    await waitFor(() => {
      const despues = llamadas.filter(
        (l) => l.method === "GET" && l.url.includes("/api/v1/unidades"),
      ).length
      expect(despues).toBeGreaterThan(unidadesAntes)
    })
  })

  it("N07: si el servidor rechaza, avisa y no muestra el resumen", async () => {
    montar({ rechazarAplicar: true })
    const select = (await screen.findByLabelText("Plantilla para aplicar")) as HTMLSelectElement
    await waitFor(() => expect(select.options.length).toBeGreaterThanOrEqual(2))
    fireEvent.change(select, { target: { value: P1 } })
    fireEvent.click(screen.getByRole("button", { name: "Aplicar plantilla" }))
    expect(await screen.findByRole("alert")).toBeTruthy()
    expect(screen.queryByText(/^Se crearon/)).toBeNull()
  })
})
