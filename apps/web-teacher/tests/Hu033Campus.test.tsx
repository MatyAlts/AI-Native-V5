import { readFileSync } from "node:fs"
import { dirname, join } from "node:path"
import { fileURLToPath } from "node:url"
/**
 * Aceptacion HU-033 (orquestador, antes de construir; el constructor no la
 * modifica). Decision de Juani (24/11): el docente arma el campus de su
 * comision desde su panel, en un apartado nuevo tipo "campus del alumno":
 * bienvenida, unidades con introduccion en HTML, fecha de apertura y resumen
 * de la tarjeta, todo desde el mismo lugar.
 *
 * Contrato que fija esta prueba:
 *  - Ruta `/campus` (search `comisionId`) con item "Campus del curso" en el
 *    grupo "Trabajo del docente" del menu (NAV_GROUPS).
 *  - `CampusView` en `src/views/CampusView.tsx`, props `comisionId` y
 *    `getToken`, con PageContainer + `helpContent.campus`.
 *  - Bienvenida: textarea con aria-label "HTML de la bienvenida" cargado con
 *    `GET /api/v1/comisiones/{id}/bienvenida` ({ html }); el boton "Guardar
 *    bienvenida" manda `PUT` a esa ruta con { html }.
 *  - Una fila por unidad de `GET /api/v1/unidades?comision_id=` (en orden),
 *    con boton "Editar <nombre>". El editor tiene: textarea "HTML de la
 *    introduccion", input date "Fecha de apertura", textarea "Resumen de la
 *    tarjeta" y boton "Guardar unidad", que manda `PATCH
 *    /api/v1/unidades/{id}` con { introduccion_html, fecha_apertura,
 *    descripcion }. Fecha vacia se manda como null.
 *  - Boton "Usar estructura sugerida": llena la introduccion con las 7
 *    secciones (De que se trata, Al terminar vas a poder, Resumen
 *    interactivo, La teoria, Ejemplo resuelto paso a paso, Errores comunes,
 *    Antes del TP) como <h2>.
 *  - Vista previa en `HtmlAislado` con titulo "Vista previa".
 *  - Cada fila dice cuando abre: "Abre el 09/03/2027", o "Abierta" sin fecha.
 *
 * C01  El apartado existe en el menu y en la ruta.
 * C02  El docente carga y guarda la bienvenida.
 * C03  El docente edita una unidad: introduccion, fecha y resumen.
 * C05  La estructura sugerida trae las 7 secciones.
 * C06  La vista previa usa el recuadro aislado con lo que se esta escribiendo.
 * C07  La lista muestra cuando abre cada unidad.
 * N07  Si el servidor rechaza el guardado (403), se avisa y no se dice
 *      "Guardado".
 */
import { cleanup, fireEvent, screen, waitFor } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { NAV_GROUPS } from "../src/routes/__root"
import { helpContent } from "../src/utils/helpContent"
import { CampusView } from "../src/views/CampusView"
import { renderWithRouter } from "./_mocks"

const COM = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
const U1 = "11111111-1111-1111-1111-111111111111"
const U2 = "22222222-2222-2222-2222-222222222222"
const RAIZ = join(dirname(fileURLToPath(import.meta.url)), "..")

const unidad = (
  id: string,
  nombre: string,
  orden: number,
  extra: Record<string, unknown> = {},
) => ({
  id,
  tenant_id: "t1",
  comision_id: COM,
  nombre,
  descripcion: null,
  orden,
  introduccion_html: null,
  fecha_apertura: null,
  created_by: "u1",
  created_at: "2026-05-01T00:00:00Z",
  updated_at: null,
  deleted_at: null,
  ...extra,
})

type Llamada = { url: string; method: string; body: unknown }

function montar(opciones: { rechazar?: boolean } = {}) {
  const llamadas: Llamada[] = []
  const fetchMock = vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
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
    if (opciones.rechazar && method !== "GET") return json(403, { detail: "No es tu comision" })
    if (url.includes(`/comisiones/${COM}/bienvenida`)) {
      return method === "GET" ? json(200, { html: "<h1>Hola curso</h1>" }) : json(200, body)
    }
    if (url.includes("/api/v1/unidades") && method === "GET") {
      return json(200, {
        data: [
          unidad(U2, "Unidad 2 · Secuenciales", 1, { fecha_apertura: "2027-03-09" }),
          unidad(U1, "Unidad 1 · Bienvenida", 0),
        ],
        meta: { cursor_next: null },
      })
    }
    if (url.includes(`/api/v1/unidades/`) && method === "PATCH") {
      return json(200, { ...unidad(U2, "Unidad 2 · Secuenciales", 1), ...(body as object) })
    }
    return json(200, { data: [], meta: { cursor_next: null } })
  })
  vi.stubGlobal("fetch", fetchMock)
  // Dia fijo (HU-039): con la fecha real, "Abre el 09/03/2027" pasaria a
  // "Abierta desde..." el 09/03/2027 y la prueba fallaria sola.
  renderWithRouter(<CampusView comisionId={COM} getToken={async () => "t"} hoy="2026-11-25" />)
  return llamadas
}

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

describe("HU-033 · campus del curso en el panel docente", () => {
  it("C01: el apartado esta en el menu y tiene su ruta y su ayuda", () => {
    const grupo = NAV_GROUPS.find((g) => g.label === "Trabajo del docente")
    expect(grupo?.items.some((i) => i.id === "/campus" && i.label === "Campus del curso")).toBe(
      true,
    )
    const ruta = readFileSync(join(RAIZ, "src/routes/campus.tsx"), "utf-8")
    expect(ruta).toContain('createFileRoute("/campus")')
    expect(ruta).toContain("CampusView")
    expect(helpContent.campus).toBeTruthy()
  })

  it("C02: carga y guarda la bienvenida", async () => {
    const llamadas = montar()
    const area = (await screen.findByLabelText("HTML de la bienvenida")) as HTMLTextAreaElement
    await waitFor(() => expect(area.value).toBe("<h1>Hola curso</h1>"))
    fireEvent.change(area, { target: { value: "<h1>Bienvenidos a Prog 1</h1>" } })
    fireEvent.click(screen.getByRole("button", { name: "Guardar bienvenida" }))
    await waitFor(() => {
      const put = llamadas.find(
        (l) => l.method === "PUT" && l.url.includes(`/comisiones/${COM}/bienvenida`),
      )
      expect(put?.body).toEqual({ html: "<h1>Bienvenidos a Prog 1</h1>" })
    })
  })

  it("C07: lista las unidades en orden con su apertura", async () => {
    montar()
    const botones = await screen.findAllByRole("button", { name: /^Editar Unidad/ })
    expect(botones.map((b) => b.getAttribute("aria-label") ?? b.textContent)).toEqual([
      "Editar Unidad 1 · Bienvenida",
      "Editar Unidad 2 · Secuenciales",
    ])
    expect(await screen.findByText("Abre el 09/03/2027")).toBeTruthy()
    expect(screen.getByText("Abierta")).toBeTruthy()
  })

  it("C03: edita introduccion, fecha y resumen de una unidad", async () => {
    const llamadas = montar()
    fireEvent.click(await screen.findByRole("button", { name: "Editar Unidad 2 · Secuenciales" }))
    const intro = (await screen.findByLabelText("HTML de la introduccion")) as HTMLTextAreaElement
    const fecha = screen.getByLabelText("Fecha de apertura") as HTMLInputElement
    expect(fecha.value).toBe("2027-03-09")
    fireEvent.change(intro, { target: { value: "<h2>De que se trata</h2><script>1</script>" } })
    fireEvent.change(fecha, { target: { value: "2027-03-16" } })
    fireEvent.change(screen.getByLabelText("Resumen de la tarjeta"), {
      target: { value: "Primeros programas completos" },
    })
    fireEvent.click(screen.getByRole("button", { name: "Guardar unidad" }))
    await waitFor(() => {
      const patch = llamadas.find(
        (l) => l.method === "PATCH" && l.url.includes(`/api/v1/unidades/${U2}`),
      )
      expect(patch?.body).toEqual({
        introduccion_html: "<h2>De que se trata</h2><script>1</script>",
        fecha_apertura: "2027-03-16",
        descripcion: "Primeros programas completos",
      })
    })
  })

  it("C03: sin fecha se manda null (la unidad queda abierta)", async () => {
    const llamadas = montar()
    fireEvent.click(await screen.findByRole("button", { name: "Editar Unidad 2 · Secuenciales" }))
    fireEvent.change(await screen.findByLabelText("Fecha de apertura"), { target: { value: "" } })
    fireEvent.click(screen.getByRole("button", { name: "Guardar unidad" }))
    await waitFor(() => {
      const patch = llamadas.find((l) => l.method === "PATCH")
      expect((patch?.body as { fecha_apertura: unknown }).fecha_apertura).toBeNull()
    })
  })

  it("C05: la estructura sugerida trae las 7 secciones", async () => {
    montar()
    fireEvent.click(await screen.findByRole("button", { name: "Editar Unidad 1 · Bienvenida" }))
    fireEvent.click(await screen.findByRole("button", { name: "Usar estructura sugerida" }))
    const intro = screen.getByLabelText("HTML de la introduccion") as HTMLTextAreaElement
    const titulos = Array.from(intro.value.matchAll(/<h2[^>]*>([^<]+)<\/h2>/g)).map((m) =>
      (m[1] ?? "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase(),
    )
    expect(titulos).toHaveLength(7)
    const esperados = [
      "de que se trata",
      "al terminar vas a poder",
      "resumen interactivo",
      "la teoria",
      "ejemplo resuelto",
      "errores comunes",
      "antes del tp",
    ]
    esperados.forEach((e, i) => expect(titulos[i]).toContain(e))
  })

  it("C06: la vista previa usa el recuadro aislado con lo que se escribe", async () => {
    montar()
    fireEvent.click(await screen.findByRole("button", { name: "Editar Unidad 2 · Secuenciales" }))
    fireEvent.change(await screen.findByLabelText("HTML de la introduccion"), {
      target: { value: "<p>Texto en vivo</p>" },
    })
    await waitFor(() => {
      const previa = document.querySelector('iframe[title="Vista previa"]')
      expect(previa).not.toBeNull()
      expect(previa?.getAttribute("srcdoc") ?? "").toContain("<p>Texto en vivo</p>")
      expect(previa?.getAttribute("sandbox") ?? "").not.toContain("allow-same-origin")
    })
  })

  it("N07: si el servidor rechaza, avisa y no dice Guardado", async () => {
    montar({ rechazar: true })
    const area = await screen.findByLabelText("HTML de la bienvenida")
    fireEvent.change(area, { target: { value: "<p>x</p>" } })
    fireEvent.click(screen.getByRole("button", { name: "Guardar bienvenida" }))
    expect(await screen.findByRole("alert")).toBeTruthy()
    expect(screen.queryByText(/^Guardado/)).toBeNull()
  })
})
