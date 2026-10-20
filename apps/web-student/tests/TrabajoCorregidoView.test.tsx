/**
 * Change `alumno-mis-trabajos-corregidos` — "Mi trabajo corregido".
 *
 * Restriccion dura: la vista es de SOLO LECTURA. Nada de lo que hace puede
 * tocar la traza cognitiva (CTR) ni los resultados de la tesis. Los tests del
 * final lo afirman sobre el log REAL de requests, no de palabra.
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { TrabajoCorregidoView } from "../src/components/TrabajoCorregidoView"
import type { Entrega } from "../src/lib/api"

const ENTREGA_ID = "cccccccc-cccc-cccc-cccc-cccccccccccc"

function entrega(estado: Entrega["estado"] = "graded"): Entrega {
  return {
    id: ENTREGA_ID,
    tenant_id: "t1",
    tarea_practica_id: "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
    comision_id: "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
    student_pseudonym: "b1b1b1b1-0001-0001-0001-000000000001",
    estado,
    ejercicio_estados: [],
    submitted_at: "2026-09-20T10:00:00Z",
    created_at: "2026-09-20T09:00:00Z",
    updated_at: "2026-09-23T12:00:00Z",
    tarea_titulo: "TP Listas",
  }
}

const CALIFICACION = {
  id: "k1",
  entrega_id: ENTREGA_ID,
  nota_final: 8,
  feedback_general: "Muy bien",
  detalle_criterios: [{ criterio: "Claridad", puntaje: 4, max_puntaje: 5, comentario: "ok" }],
  graded_at: "2026-09-23T12:00:00Z",
  graded_by: "d1",
}

function art(orden: number, extra: Record<string, unknown> = {}) {
  return {
    orden,
    ejercicio_id: `e${orden}`,
    episode_id: `ep-${orden}`,
    codigo: `codigo_del_ejercicio_${orden}`,
    language: "python",
    sha256: "x",
    created_at: "2026-10-01T00:00:00Z",
    ...extra,
  }
}

interface Req {
  url: string
  method: string
}
type Respuesta = { status: number; body: unknown }

/** fetch falso que REGISTRA cada request (url + metodo). */
function stubRed(rutas: Record<string, Respuesta>) {
  const log: Req[] = []
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string | URL | Request, init?: RequestInit) => {
      const u = typeof url === "string" ? url : url.toString()
      log.push({ url: u, method: (init?.method ?? "GET").toUpperCase() })
      const clave = Object.keys(rutas).find((k) => u.includes(k))
      const r: Respuesta = (clave && rutas[clave]) || { status: 500, body: {} }
      return Promise.resolve({
        ok: r.status < 300,
        status: r.status,
        json: () => Promise.resolve(r.body),
        text: () => Promise.resolve(JSON.stringify(r.body)),
      } as Response)
    }),
  )
  return log
}

const rutasOk = (artefactos = [art(2), art(1), art(3)], extra: Record<string, Respuesta> = {}) => ({
  "/calificacion": { status: 200, body: CALIFICACION },
  "/artefacto": { status: 200, body: { entrega_id: ENTREGA_ID, legacy: false, artefactos } },
  "/api/v1/episodes/": {
    status: 200,
    body: {
      last_code_snapshot: "SNAPSHOT_QUE_NO_SE_ENTREGO",
      messages: [{ role: "user", content: "hola tutor", ts: "t" }],
    },
  },
  ...extra,
})

/** Contrato de solo lectura: lo que TODA sesion de la vista debe cumplir. */
const PROHIBIDAS = [
  /\/events/,
  /\/close/,
  /\/abandoned/,
  /\/resume/,
  /\/message/,
  /\/reflection/,
  /classify/,
]
function verificarSoloLectura(log: Req[]) {
  const noGet = log.filter((r) => r.method !== "GET")
  expect(noGet, "requests que no son GET").toEqual([])
  const prohibidas = log.filter((r) => PROHIBIDAS.some((p) => p.test(r.url)))
  expect(prohibidas, "requests a rutas de escritura/CTR").toEqual([])
}

let descargas: { filename: string; blob: Blob }[]
beforeEach(() => {
  descargas = []
  let ultimoBlob: Blob | null = null
  // jsdom no implementa createObjectURL: se define y se limpia a mano.
  URL.createObjectURL = (b: Blob | MediaSource) => {
    ultimoBlob = b as Blob
    return "blob:fake"
  }
  URL.revokeObjectURL = () => {}
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (
    this: HTMLAnchorElement,
  ) {
    if (ultimoBlob) descargas.push({ filename: this.download, blob: ultimoBlob })
  })
})
afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

function leer(blob: Blob): Promise<string> {
  return new Promise((res) => {
    const fr = new FileReader()
    fr.onload = () => res(String(fr.result))
    fr.readAsText(blob)
  })
}

describe("TrabajoCorregidoView — render", () => {
  it("muestra nota, criterios y un bloque de codigo por ejercicio, en orden", async () => {
    stubRed(rutasOk())
    render(<TrabajoCorregidoView entrega={entrega()} onBack={vi.fn()} />)

    await waitFor(() => expect(screen.getAllByTestId("ejercicio-codigo")).toHaveLength(3))
    expect(await screen.findByTestId("nota-final")).toHaveTextContent("8")
    expect(screen.getByText("Claridad")).toBeInTheDocument()
    const codigos = screen.getAllByTestId("ejercicio-codigo").map((e) => e.textContent)
    expect(codigos).toEqual([
      "codigo_del_ejercicio_1",
      "codigo_del_ejercicio_2",
      "codigo_del_ejercicio_3",
    ])
    expect(screen.getByText("Ejercicio 1")).toBeInTheDocument()
    expect(screen.getByText("Ejercicio 3")).toBeInTheDocument()
  })

  it("returned: el cartel de devolucion sigue visible junto al codigo", async () => {
    stubRed(rutasOk([art(1)]))
    render(<TrabajoCorregidoView entrega={entrega("returned")} onBack={vi.fn()} />)
    await waitFor(() => expect(screen.getAllByTestId("ejercicio-codigo")).toHaveLength(1))
    expect(await screen.findByText(/devolvio la entrega/i)).toBeInTheDocument()
  })

  it("legacy sin artefactos: lo dice con palabras, sin descarga, con la nota", async () => {
    stubRed(rutasOk([], {}))
    render(<TrabajoCorregidoView entrega={entrega()} onBack={vi.fn()} />)
    await waitFor(() => expect(screen.getByTestId("sin-codigo-guardado")).toBeInTheDocument())
    expect(screen.getByTestId("sin-codigo-guardado")).toHaveTextContent(
      /anterior a que la plataforma guardara el c[oó]digo entregado/i,
    )
    expect(screen.queryByRole("button", { name: /descargar/i })).not.toBeInTheDocument()
    expect(await screen.findByTestId("nota-final")).toHaveTextContent("8")
  })

  it("falla el artefacto (500): mensaje distinto al de legacy", async () => {
    stubRed(rutasOk([], { "/artefacto": { status: 500, body: {} } }))
    render(<TrabajoCorregidoView entrega={entrega()} onBack={vi.fn()} />)
    await waitFor(() => expect(screen.getByTestId("codigo-error")).toBeInTheDocument())
    expect(screen.getByTestId("codigo-error")).toHaveTextContent(/no pudimos traer tu c[oó]digo/i)
    expect(screen.queryByTestId("sin-codigo-guardado")).not.toBeInTheDocument()
  })

  it("artefacto 404: se informa como no disponible, no como sin codigo", async () => {
    stubRed(rutasOk([], { "/artefacto": { status: 404, body: {} } }))
    render(<TrabajoCorregidoView entrega={entrega()} onBack={vi.fn()} />)
    await waitFor(() => expect(screen.getByTestId("codigo-no-disponible")).toBeInTheDocument())
    expect(screen.queryByTestId("sin-codigo-guardado")).not.toBeInTheDocument()
  })

  it("mientras carga muestra el skeleton", () => {
    stubRed(rutasOk())
    render(<TrabajoCorregidoView entrega={entrega()} onBack={vi.fn()} />)
    expect(screen.getByTestId("codigo-cargando")).toBeInTheDocument()
  })
})

describe("TrabajoCorregidoView — descarga", () => {
  it("descarga el codigo ENTREGADO (no el snapshot), pide el episodio del ARTEFACTO y comenta la charla", async () => {
    const log = stubRed(rutasOk([art(1, { episode_id: "ep-del-artefacto-1" })]))
    render(<TrabajoCorregidoView entrega={entrega()} onBack={vi.fn()} />)

    await userEvent.click(await screen.findByRole("button", { name: /descargar.*\.py/i }))

    await waitFor(() => expect(descargas).toHaveLength(1))
    const texto = await leer(descargas[0]!.blob)
    expect(texto).toContain("codigo_del_ejercicio_1")
    expect(texto).not.toContain("SNAPSHOT_QUE_NO_SE_ENTREGO")
    expect(texto).toContain("# [Alumno] hola tutor")
    expect(descargas[0]!.filename).toMatch(/\.py$/)
    expect(log.some((r) => r.url.endsWith("/api/v1/episodes/ep-del-artefacto-1"))).toBe(true)
  })

  it("java: ofrece .java", async () => {
    stubRed(rutasOk([art(1, { language: "java", codigo: "class A {}" })]))
    render(<TrabajoCorregidoView entrega={entrega()} onBack={vi.fn()} />)
    await userEvent.click(await screen.findByRole("button", { name: /descargar.*\.java/i }))
    await waitFor(() => expect(descargas).toHaveLength(1))
    expect(descargas[0]!.filename).toMatch(/\.java$/)
  })

  it("si la charla falla, igual descarga el codigo y avisa", async () => {
    stubRed(rutasOk([art(1)], { "/api/v1/episodes/": { status: 500, body: {} } }))
    render(<TrabajoCorregidoView entrega={entrega()} onBack={vi.fn()} />)
    await userEvent.click(await screen.findByRole("button", { name: /descargar/i }))
    await waitFor(() => expect(descargas).toHaveLength(1))
    const texto = await leer(descargas[0]!.blob)
    expect(texto).toContain("codigo_del_ejercicio_1")
    expect(texto).not.toContain("Charla con el tutor")
    expect(await screen.findByText(/charla con el tutor no se pudo incluir/i)).toBeInTheDocument()
  })

  it("el spinner es solo del boton apretado; los demas siguen operativos", async () => {
    stubRed(rutasOk([art(1), art(2)]))
    render(<TrabajoCorregidoView entrega={entrega()} onBack={vi.fn()} />)
    const botones = await screen.findAllByRole("button", { name: /descargar/i })
    expect(botones).toHaveLength(2)
    fireEvent.click(botones[0]!)
    expect(botones[0]).toBeDisabled()
    expect(botones[1]).not.toBeDisabled()
    await waitFor(() => expect(descargas).toHaveLength(1))
  })
})

describe("TrabajoCorregidoView — teclado", () => {
  it("volver y cada Descargar se alcanzan con Tab y se activan con Enter", async () => {
    stubRed(rutasOk([art(1), art(2)]))
    const onBack = vi.fn()
    const user = userEvent.setup()
    render(<TrabajoCorregidoView entrega={entrega()} onBack={onBack} />)
    const botones = await screen.findAllByRole("button", { name: /descargar/i })

    await user.tab()
    expect(screen.getByRole("button", { name: /volver/i })).toHaveFocus()
    await user.keyboard("{Enter}")
    expect(onBack).toHaveBeenCalledTimes(1)

    // Tab recorre hasta el 2do Descargar (alcanzable por teclado).
    for (let i = 0; i < 10 && document.activeElement !== botones[1]; i++) await user.tab()
    expect(botones[1]).toHaveFocus()
    await user.keyboard("{Enter}")
    await waitFor(() => expect(descargas).toHaveLength(1))
    expect(descargas[0]!.filename).toMatch(/ejercicio-2/)
  })
})

describe("TrabajoCorregidoView — SOLO LECTURA (restriccion dura: no altera la tesis)", () => {
  it("el verificador detecta una escritura (si no detectara, los tests de abajo no valdrian)", () => {
    expect(() => verificarSoloLectura([{ url: "/api/v1/entregas", method: "POST" }])).toThrow()
    expect(() =>
      verificarSoloLectura([{ url: "/api/v1/episodes/x/events/foo", method: "GET" }]),
    ).toThrow()
    expect(() =>
      verificarSoloLectura([{ url: "/api/v1/episodes/x/close", method: "GET" }]),
    ).toThrow()
  })

  it("recorrer la vista y descargar TODOS los ejercicios: solo GET, nada de CTR", async () => {
    const log = stubRed(rutasOk([art(1), art(2), art(3)]))
    render(<TrabajoCorregidoView entrega={entrega()} onBack={vi.fn()} />)

    for (let i = 0; i < 3; i++) {
      const botones = await screen.findAllByRole("button", { name: /descargar/i })
      await userEvent.click(botones[i]!)
      await waitFor(() => expect(descargas).toHaveLength(i + 1))
    }

    expect(log.length).toBeGreaterThanOrEqual(5) // calificacion + artefacto + 3 episodios
    verificarSoloLectura(log)
  })

  it("salir de la pestana / cerrar la ventana no genera ninguna request", async () => {
    const log = stubRed(rutasOk([art(1)]))
    render(<TrabajoCorregidoView entrega={entrega()} onBack={vi.fn()} />)
    await screen.findAllByTestId("ejercicio-codigo")
    const antes = log.length

    document.dispatchEvent(new Event("visibilitychange"))
    window.dispatchEvent(new Event("blur"))
    window.dispatchEvent(new Event("pagehide"))
    window.dispatchEvent(new Event("beforeunload"))

    expect(log.length).toBe(antes)
  })
})
