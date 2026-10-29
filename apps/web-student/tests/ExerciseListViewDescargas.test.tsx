/**
 * Change `descargas-borrador-y-entregado` — botones de descarga en la pantalla
 * de la TP: "borrador" (episodio) vs "lo entregado" (artefacto sellado).
 *
 * Los tests que afirman AUSENCIA ("no aparece X") estan emparejados con una
 * afirmacion de PRESENCIA en el mismo caso, para que no se vacien solos.
 */
import { ConfirmProvider } from "@platform/ui"
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { ExerciseListView } from "../src/components/ExerciseListView"
import type { AvailableTarea, Entrega, EntregaEstado, TpEjercicio } from "../src/lib/api"

const COMISION_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
const TAREA_ID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
const ENTREGA_ID = "cccccccc-cccc-cccc-cccc-cccccccccccc"
const EJ1 = "ejejejej-0001-0001-0001-000000000001"
const EJ2 = "ejejejej-0002-0002-0002-000000000002"

function entrega(
  estado: EntregaEstado,
  completados: [boolean, boolean],
  extra: Partial<Entrega> = {},
): Entrega {
  return {
    id: ENTREGA_ID,
    tenant_id: "t1",
    tarea_practica_id: TAREA_ID,
    comision_id: COMISION_ID,
    student_pseudonym: "b1b1b1b1-0001-0001-0001-000000000001",
    estado,
    ejercicio_estados: completados.map((c, i) => ({
      ejercicio_id: i === 0 ? EJ1 : EJ2,
      orden: i + 1,
      completado: c,
      episode_id: `episode-${i + 1}`,
      completado_at: null,
    })),
    submitted_at: estado === "draft" ? null : "2026-10-01T10:00:00Z",
    created_at: "2026-10-01T09:00:00Z",
    updated_at: "2026-10-01T09:00:00Z",
    ...extra,
  }
}

function pares(lang?: "java"): TpEjercicio[] {
  return [EJ1, EJ2].map((id, i) => ({
    id: `pair-${i + 1}`,
    tarea_practica_id: TAREA_ID,
    peso_en_tp: "0.50",
    ejercicio_id: id,
    orden: i + 1,
    ejercicio: {
      id,
      titulo: i === 0 ? "Suma" : "Resta",
      enunciado_md: "x",
      inicial_codigo: null,
      unidad_tematica: "funciones",
      dificultad: "basica",
      test_cases: [],
      ...(lang ? { language: lang } : {}),
    },
  })) as TpEjercicio[]
}

const TAREA: AvailableTarea = {
  id: TAREA_ID,
  codigo: "TP01",
  titulo: "Funciones basicas",
  enunciado: "x",
  fecha_inicio: null,
  fecha_fin: null,
  peso: "1.0",
  estado: "published",
  version: 1,
  inicial_codigo: null,
}

type Req = { url: string; method: string }
interface Red {
  entrega: Entrega
  pairs?: TpEjercicio[]
  artefacto?: { status: number; body: unknown }
  episodio?: { status: number; body: unknown }
}

function artefactos(...ordenes: number[]) {
  return ordenes.map((orden) => ({
    orden,
    ejercicio_id: orden === 1 ? EJ1 : EJ2,
    episode_id: `ep-sellado-${orden}`,
    language: "python",
    codigo: `print("SELLADO_${orden}")`,
    sha256: "x",
    created_at: "2026-10-01T10:00:00Z",
  }))
}

function stubRed(red: Red) {
  const log: Req[] = []
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string | URL | Request, init?: RequestInit) => {
      const u = typeof url === "string" ? url : url.toString()
      log.push({ url: u, method: (init?.method ?? "GET").toUpperCase() })
      let r: { status: number; body: unknown }
      if (u.includes("/artefacto")) {
        r = red.artefacto ?? {
          status: 200,
          body: { entrega_id: ENTREGA_ID, legacy: false, artefactos: artefactos(1, 2) },
        }
      } else if (u.includes("/api/v1/episodes/")) {
        r = red.episodio ?? {
          status: 200,
          body: {
            last_code_snapshot: 'print("BORRADOR")',
            messages: [{ role: "user", content: "hola", ts: "t" }],
          },
        }
      } else if (u.includes("/ejercicios")) {
        r = { status: 200, body: red.pairs ?? pares() }
      } else if (u.includes("/api/v1/entregas")) {
        r = { status: 200, body: red.entrega }
      } else {
        r = { status: 200, body: { data: [], meta: { cursor_next: null } } }
      }
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

function stubDescarga() {
  const blobs: Blob[] = []
  const createObjectURL = vi.fn((b: Blob) => {
    blobs.push(b)
    return "blob:fake"
  })
  vi.stubGlobal("URL", { ...URL, createObjectURL, revokeObjectURL: vi.fn() })
  let filename: string | null = null
  const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (
    this: HTMLAnchorElement,
  ) {
    filename = this.download
  })
  return { click, blobs, filename: () => filename }
}

/** jsdom no trae `Blob.text()`. */
function leer(b: Blob | undefined): Promise<string> {
  return new Promise((resolve, reject) => {
    if (!b) return reject(new Error("no se descargo ningun blob"))
    const fr = new FileReader()
    fr.onload = () => resolve(String(fr.result))
    fr.onerror = () => reject(fr.error)
    fr.readAsText(b)
  })
}

async function montar() {
  render(
    <ExerciseListView
      tarea={TAREA}
      comisionId={COMISION_ID}
      onSelectEjercicio={vi.fn()}
      onViewGrade={vi.fn()}
      onBack={vi.fn()}
    />,
    { wrapper: ConfirmProvider },
  )
  await waitFor(() => expect(screen.getByTestId("ejercicio-item-1")).toBeDefined())
}

const borrador = (n: number) => screen.queryByTestId(`ejercicio-descargar-${n}`)
const entregado = (n: number) => screen.queryByTestId(`ejercicio-descargar-entregado-${n}`)

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

describe("rotulos y visibilidad", () => {
  it("draft con el 1 completado: 'Descargar borrador (.py)' y nada de 'lo entregado'", async () => {
    stubRed({ entrega: entrega("draft", [true, false]) })
    await montar()
    expect(borrador(1)?.textContent).toBe("Descargar borrador (.py)")
    expect(entregado(1)).toBeNull()
    // el 2 no esta completado: ningun boton
    expect(borrador(2)).toBeNull()
    expect(entregado(2)).toBeNull()
  })

  it("draft con ejercicio java: el rotulo dice (.java)", async () => {
    stubRed({ entrega: entrega("draft", [true, false]), pairs: pares("java") })
    await montar()
    expect(borrador(1)?.textContent).toBe("Descargar borrador (.java)")
  })

  it("graded: 'lo entregado' en cada ejercicio y ningun borrador", async () => {
    stubRed({ entrega: entrega("graded", [true, true]) })
    await montar()
    expect(entregado(1)?.textContent).toBe("Descargar lo entregado (.py)")
    expect(entregado(2)?.textContent).toBe("Descargar lo entregado (.py)")
    expect(borrador(1)).toBeNull()
    expect(borrador(2)).toBeNull()
  })

  it("returned con ejercicios sin completar: 'lo entregado' igual", async () => {
    stubRed({ entrega: entrega("returned", [false, false]) })
    await montar()
    expect(entregado(1)).not.toBeNull()
    expect(entregado(2)).not.toBeNull()
    expect(borrador(1)).toBeNull()
    expect(borrador(2)).toBeNull()
  })

  it("returned con el 2 re-completado: el 2 muestra los dos, el 1 solo lo entregado", async () => {
    stubRed({ entrega: entrega("returned", [false, true]) })
    await montar()
    expect(borrador(2)?.textContent).toBe("Descargar borrador (.py)")
    expect(entregado(2)).not.toBeNull()
    expect(entregado(1)).not.toBeNull()
    expect(borrador(1)).toBeNull()
  })

  it("legacy graded: solo borrador", async () => {
    stubRed({ entrega: entrega("graded", [true, true], { legacy: true }) })
    await montar()
    expect(borrador(1)).not.toBeNull()
    expect(entregado(1)).toBeNull()
    expect(entregado(2)).toBeNull()
  })
})

describe("descarga de lo entregado", () => {
  it("baja el codigo SELLADO (no el last_code_snapshot) y es solo lectura", async () => {
    const log = stubRed({ entrega: entrega("returned", [false, false]) })
    const nav = stubDescarga()
    await montar()
    // lectura perezosa: antes del click no se pidio el artefacto
    expect(log.some((r) => r.url.includes("/artefacto"))).toBe(false)
    log.length = 0
    fireEvent.click(entregado(1) as HTMLElement)
    await waitFor(() => expect(nav.click).toHaveBeenCalled())
    expect(nav.filename()).toBe("suma.py")
    const texto = await leer(nav.blobs[0])
    expect(texto).toContain('print("SELLADO_1")')
    expect(texto).not.toContain("BORRADOR")
    expect(texto).toContain("hola") // charla del episodio del artefacto
    expect(log.every((r) => r.method === "GET")).toBe(true)
    expect(log.map((r) => r.url).sort()).toEqual([
      `/api/v1/entregas/${ENTREGA_ID}/artefacto`,
      "/api/v1/episodes/ep-sellado-1",
    ])
  })

  it("el borrador sigue bajando el last_code_snapshot", async () => {
    stubRed({ entrega: entrega("draft", [true, false]) })
    const nav = stubDescarga()
    await montar()
    fireEvent.click(borrador(1) as HTMLElement)
    await waitFor(() => expect(nav.click).toHaveBeenCalled())
    expect(await leer(nav.blobs[0])).toContain('print("BORRADOR")')
  })

  it("artefacto java: el archivo es .java", async () => {
    const java = artefactos(1, 2).map((a) => ({ ...a, language: "java" }))
    stubRed({
      entrega: entrega("graded", [true, true]),
      artefacto: { status: 200, body: { entrega_id: ENTREGA_ID, legacy: false, artefactos: java } },
    })
    const nav = stubDescarga()
    await montar()
    fireEvent.click(entregado(2) as HTMLElement)
    await waitFor(() => expect(nav.click).toHaveBeenCalled())
    expect(nav.filename()).toBe("resta.java")
  })

  it("sin artefacto para ese orden: aviso con palabras y nada descargado", async () => {
    stubRed({
      entrega: entrega("graded", [true, true]),
      artefacto: {
        status: 200,
        body: { entrega_id: ENTREGA_ID, legacy: false, artefactos: artefactos(2) },
      },
    })
    const nav = stubDescarga()
    await montar()
    fireEvent.click(entregado(1) as HTMLElement)
    await waitFor(() => expect(screen.getByTestId("descarga-error")).toBeDefined())
    expect(screen.getByTestId("descarga-error").textContent).toMatch(/codigo entregado/i)
    expect(nav.click).not.toHaveBeenCalled()
  })

  it("falla la lectura del artefacto: aviso y los otros botones siguen", async () => {
    stubRed({
      entrega: entrega("graded", [true, true]),
      artefacto: { status: 500, body: {} },
    })
    const nav = stubDescarga()
    await montar()
    fireEvent.click(entregado(1) as HTMLElement)
    await waitFor(() => expect(screen.getByTestId("descarga-error")).toBeDefined())
    expect(nav.click).not.toHaveBeenCalled()
    expect(entregado(2)).not.toBeNull()
  })

  it("falla la charla: baja el codigo igual y avisa", async () => {
    stubRed({
      entrega: entrega("graded", [true, true]),
      episodio: { status: 500, body: {} },
    })
    const nav = stubDescarga()
    await montar()
    fireEvent.click(entregado(1) as HTMLElement)
    await waitFor(() => expect(nav.click).toHaveBeenCalled())
    expect(await leer(nav.blobs[0])).toContain('print("SELLADO_1")')
    await waitFor(() => expect(screen.getByTestId("descarga-error").textContent).toMatch(/charla/i))
  })
})
