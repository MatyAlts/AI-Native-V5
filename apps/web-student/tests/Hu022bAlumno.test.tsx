/**
 * HU-022 (vuelta 2), aceptación del lado del alumno.
 *
 * C01 (F24): la vista alumno pide SUS entregas con `propias=true`. Sin eso,
 *   un docente que pasa a "Ver como alumno" recibe la comisión entera y ve
 *   como propias las entregas de los demás (prueba en producción del 23/11).
 * C05 (F30): un ejercicio sin completar dice "Abrir" (decisión de Juani
 *   tras la revisión, 23/11): la pantalla no sabe si el alumno lo abrió y lo
 *   dejó sin cerrar, porque el episodio se anota en la entrega recién al
 *   cerrar. "Abrir" no miente en ningún caso; antes un ejercicio nunca
 *   empezado decía "Continuar".
 * C06 (F31): sin jerga ("ADR-035", "chars") en lo que ve el alumno.
 *
 * Lo que se prueba en navegador real en la demo (no acá): el cierre del
 * último ejercicio no ofrece "Siguiente ejercicio", el TP devuelto no cae en
 * "LISTO" y el título del ejercicio no se corta.
 */
import { ConfirmProvider } from "@platform/ui"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { cleanup, render, screen, waitFor } from "@testing-library/react"
import type { ReactElement } from "react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { ExerciseListView } from "../src/components/ExerciseListView"
import { ReflectionModal } from "../src/components/ReflectionModal"
import type { AvailableTarea, Entrega, TpEjercicio } from "../src/lib/api"
import { getEntregaForTp, listMisEntregas } from "../src/lib/api"
import { setupFetchMock } from "./_mocks"

vi.mock("@tanstack/react-router", async (importOriginal) => {
  const real = await importOriginal<typeof import("@tanstack/react-router")>()
  return { ...real, useNavigate: () => vi.fn() }
})

const COMISION_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
const TAREA_ID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

function capturarUrls(): string[] {
  const urls: string[] = []
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      urls.push(String(url))
      return new Response(JSON.stringify({ data: [], meta: { cursor_next: null } }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      })
    }),
  )
  return urls
}

describe("C01 · la vista alumno pide solo las entregas propias", () => {
  it("getEntregaForTp manda propias=true", async () => {
    const urls = capturarUrls()
    await getEntregaForTp(TAREA_ID, COMISION_ID)
    const listado = urls.find((u) => u.startsWith("/api/v1/entregas?"))
    expect(listado, `no pidió el listado: ${urls.join(" ")}`).toBeDefined()
    expect(new URLSearchParams(listado?.split("?")[1]).get("propias")).toBe("true")
  })

  it("listMisEntregas manda propias=true", async () => {
    const urls = capturarUrls()
    await listMisEntregas(COMISION_ID)
    const listado = urls.find((u) => u.startsWith("/api/v1/entregas?"))
    expect(listado, `no pidió el listado: ${urls.join(" ")}`).toBeDefined()
    expect(new URLSearchParams(listado?.split("?")[1]).get("propias")).toBe("true")
  })
})

function estado(orden: number, completado: boolean, episode: string | null) {
  return { ejercicio_id: null, orden, completado, episode_id: episode, completado_at: null }
}

function entregaCon(estados: ReturnType<typeof estado>[]): Entrega {
  return {
    id: "cccccccc-cccc-cccc-cccc-cccccccccccc",
    tenant_id: "t1",
    tarea_practica_id: TAREA_ID,
    comision_id: COMISION_ID,
    student_pseudonym: "b1b1b1b1-0001-0001-0001-000000000001",
    estado: "draft",
    ejercicio_estados: estados,
    submitted_at: null,
    created_at: "2026-11-23T10:00:00Z",
    updated_at: "2026-11-23T10:00:00Z",
  }
}

function pares(n: number): TpEjercicio[] {
  return Array.from({ length: n }, (_, i) => ({
    tarea_practica_id: TAREA_ID,
    peso_en_tp: "1.0",
    id: `pair-${i + 1}`,
    ejercicio_id: `ejejejej-000${i + 1}-0001-0001-00000000000${i + 1}`,
    orden: i + 1,
    ejercicio: {
      id: `ejejejej-000${i + 1}-0001-0001-00000000000${i + 1}`,
      titulo: `Ejercicio ${i + 1}`,
      enunciado_md: "x",
      inicial_codigo: null,
      unidad_tematica: "secuenciales",
      dificultad: "basica",
      test_cases: [],
    },
  }))
}

const TAREA: AvailableTarea = {
  id: TAREA_ID,
  codigo: "E2E",
  titulo: "TP de prueba",
  enunciado: "x",
  fecha_inicio: null,
  fecha_fin: null,
  peso: "1.0",
  estado: "published",
  version: 1,
  inicial_codigo: null,
}

async function botonDel(orden: number, entrega: Entrega): Promise<string> {
  setupFetchMock({
    "/ejercicios": () => pares(3),
    "/api/v1/entregas": () => entrega,
  })
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
  const item = await waitFor(() => screen.getByTestId(`ejercicio-item-${orden}`))
  const textos = Array.from(item.querySelectorAll("button")).map((b) => b.textContent ?? "")
  return textos.join(" | ")
}

describe("C05 · un ejercicio sin completar dice Abrir", () => {
  it("el ejercicio 2, nunca empezado y con el 1 completo, dice Abrir", async () => {
    const botones = await botonDel(
      2,
      entregaCon([estado(1, true, "ep-1"), estado(2, false, null), estado(3, false, null)]),
    )
    expect(botones).toMatch(/Abrir/)
    expect(botones).not.toMatch(/Continuar|Empezar/)
  })

  it("un ejercicio con episodio y sin completar también dice Abrir", async () => {
    const botones = await botonDel(
      2,
      entregaCon([estado(1, true, "ep-1"), estado(2, false, "ep-2"), estado(3, false, null)]),
    )
    expect(botones).toMatch(/Abrir/)
    expect(botones).not.toMatch(/Continuar|Empezar/)
  })

  it("el primer ejercicio de un TP sin empezar dice Abrir", async () => {
    const botones = await botonDel(
      1,
      entregaCon([estado(1, false, null), estado(2, false, null), estado(3, false, null)]),
    )
    expect(botones).toMatch(/Abrir/)
    expect(botones).not.toMatch(/Continuar|Empezar/)
  })
})

function conQuery(ui: ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}>{ui}</QueryClientProvider>
}

describe("C06 · sin jerga en lo que ve el alumno", () => {
  it("el modal de reflexión no dice 'chars'", () => {
    render(<ReflectionModal isOpen episodeId="ep-1" onClose={vi.fn()} />)
    expect(document.body.textContent ?? "").not.toMatch(/chars/i)
  })

  it("Mis reflexiones no muestra 'ADR-035'", async () => {
    setupFetchMock({
      "/reflections": () => ({ data: [], meta: { cursor_next: null } }),
    })
    const { MisReflexionesPage } = await import("../src/pages/MisReflexionesPage")
    render(conQuery(<MisReflexionesPage />))
    await waitFor(() => expect(screen.getByText(/Mis reflexiones/)).toBeDefined())
    expect(document.body.textContent ?? "").not.toMatch(/ADR-\d+/)
  })
})
