/**
 * TP devuelta: cerrar un ejercicio reabierto SIN editar lo completa si el
 * editor mostraba codigo propio del alumno (change
 * `editor-muestra-codigo-entregado-al-reabrir`, D2).
 *
 * El reporte de produccion (2026-10-23): "TP devuelto con feedback: cuando
 * pongo siguiente episodio no se desbloquea". El alumno ve su codigo (lo siembra
 * la REAPERTURA del tutor o el artefacto entregado), no toca nada porque estaba
 * bien, cierra, y el guard de BUG-1 (`hayCodigo`) no lo dejaba avanzar porque
 * el borrador local solo lo escribe quien tipea.
 *
 * BUG-1 sigue intacto: scaffold, placeholder, o "edito y lo dejo vacio" NO
 * marcan. Cada negativo de abajo se probo rojo quitando su condicion.
 */
import { act, fireEvent, render, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { collectArtefactoDrafts, saveArtefactoDraft } from "../src/lib/artefactos"
import { EpisodeView } from "../src/pages/EpisodePage"
import { setupFetchMock } from "./_mocks"
import { editoresCreados, resetMonacoMock } from "./_monacoMock"

const TAREA_ID = "tp-devuelta"
const EPISODIO_ID = "ep-nuevo"
const ENTREGA_ID = "entrega-devuelta"
const ORDEN = 1
const EJ_ID = "ej-1"
const CODIGO = "def resolver():\n    return 42\n"
const ACTIVE_EPISODE_KEY = "active-episode-id"

type Llamada = { url: string; method: string; body: string }

interface Opciones {
  snapshot?: string | null
  artefactoCodigo?: string | null
  scaffoldTp?: string | null
  patchFallaLaPrimera?: boolean
  episodeId?: string
}

function montar(op: Opciones = {}) {
  const llamadas: Llamada[] = []
  let patchN = 0
  setupFetchMock({
    [`/api/v1/episodes/${EPISODIO_ID}/close`]: () => ({ ok: true }),
    [`/api/v1/classify_episode/${EPISODIO_ID}`]: () => ({
      appropriation: "apropiacion_reflexiva",
      features: {},
    }),
    [`/api/v1/entregas/${ENTREGA_ID}/artefacto`]: () => ({
      entrega_id: ENTREGA_ID,
      legacy: false,
      artefactos:
        op.artefactoCodigo == null
          ? []
          : [
              {
                orden: ORDEN,
                ejercicio_id: EJ_ID,
                episode_id: "ep-viejo",
                codigo: op.artefactoCodigo,
                language: "python",
                sha256: "x",
                created_at: "2026-10-20T10:00:00Z",
              },
            ],
    }),
    [`/api/v1/entregas/${ENTREGA_ID}/ejercicio/${ORDEN}`]: () => {
      patchN += 1
      if (op.patchFallaLaPrimera && patchN === 1) throw new Error("patch caido")
      return { id: ENTREGA_ID }
    },
    "/resume": () => ({ ok: true }),
    [`/api/v1/tareas-practicas/${TAREA_ID}/ejercicios`]: () => [
      {
        id: "tpe-1",
        tarea_practica_id: TAREA_ID,
        ejercicio_id: EJ_ID,
        orden: ORDEN,
        peso_en_tp: "1.00",
        ejercicio: {
          id: EJ_ID,
          titulo: "E1",
          enunciado: "Enunciado 1",
          language: "python",
          inicial_codigo: null,
          test_cases: [],
        },
      },
    ],
    [`/api/v1/tareas-practicas/${TAREA_ID}`]: () => ({
      id: TAREA_ID,
      codigo: "TP",
      titulo: "TP",
      enunciado: "x",
      fecha_inicio: null,
      fecha_fin: null,
      peso: "1.00",
      estado: "published",
      version: 1,
      inicial_codigo: op.scaffoldTp ?? null,
      language: "python",
      permite_pausa: true,
    }),
    [`/api/v1/episodes/${EPISODIO_ID}`]: () => ({
      episode_id: EPISODIO_ID,
      tarea_practica_id: TAREA_ID,
      comision_id: "com-1",
      estado: "open",
      opened_at: "2026-10-27T10:00:00Z",
      closed_at: null,
      last_code_snapshot: op.snapshot ?? null,
      messages: [],
      notes: [],
      ejercicio_id: EJ_ID,
      ejercicio_orden: ORDEN,
    }),
  })
  const stub = globalThis.fetch
  vi.stubGlobal("fetch", (url: string | URL | Request, init?: RequestInit) => {
    llamadas.push({
      url: typeof url === "string" ? url : url.toString(),
      method: init?.method ?? "GET",
      body: String(init?.body ?? ""),
    })
    return (stub as typeof fetch)(url as never, init)
  })
  const vista = render(
    <EpisodeView
      episodeId={EPISODIO_ID}
      onExit={() => {}}
      ejercicioContext={{ entregaId: ENTREGA_ID, ejercicioId: EJ_ID, ejercicioOrden: ORDEN }}
    />,
  )
  return { llamadas, vista }
}

const patches = (ll: Llamada[]) =>
  ll.filter((l) => l.method === "PATCH" && l.url.includes(`/entregas/${ENTREGA_ID}/ejercicio/`))

async function esperarEditorSembrado() {
  await waitFor(() => expect(editoresCreados.length).toBeGreaterThanOrEqual(1))
  await waitFor(() => expect(editoresCreados[0]?.__opciones.value).not.toBe(""))
}

async function cerrar(vista: ReturnType<typeof render>) {
  const btn = await vista.findByTestId("close-episode-button")
  await act(async () => {
    fireEvent.click(btn)
  })
}

async function saltarReflexion(vista: ReturnType<typeof render>) {
  const saltar = await vista.findByRole("button", { name: /no quiero reflexionar/i })
  await act(async () => {
    fireEvent.click(saltar)
  })
}

beforeEach(() => {
  resetMonacoMock()
  window.sessionStorage.clear()
  window.localStorage.clear()
  window.sessionStorage.setItem(ACTIVE_EPISODE_KEY, EPISODIO_ID)
})
afterEach(() => vi.unstubAllGlobals())

describe("cerrar sin editar completa el ejercicio cuando el editor mostraba codigo propio", () => {
  it("snapshot heredado (REAPERTURA): UN PATCH completado:true con el episode_id actual", async () => {
    const { llamadas, vista } = montar({ snapshot: CODIGO })
    await esperarEditorSembrado()
    await cerrar(vista)
    await waitFor(() => expect(patches(llamadas)).toHaveLength(1))
    expect(JSON.parse(patches(llamadas)[0]?.body ?? "{}")).toMatchObject({
      completado: true,
      episode_id: EPISODIO_ID,
      ejercicio_id: EJ_ID,
    })
  })

  it("codigo entregado (cadena cortada): UN PATCH completado:true", async () => {
    const { llamadas, vista } = montar({ artefactoCodigo: CODIGO })
    await esperarEditorSembrado()
    expect(editoresCreados[0]?.__opciones.value).toBe(CODIGO)
    await cerrar(vista)
    await waitFor(() => expect(patches(llamadas)).toHaveLength(1))
  })

  it("(d) el codigo mostrado queda como borrador con el episode_id actual (la re-entrega lo manda)", async () => {
    const { llamadas, vista } = montar({ snapshot: CODIGO })
    await esperarEditorSembrado()
    await cerrar(vista)
    await waitFor(() => expect(patches(llamadas)).toHaveLength(1))
    const borradores = collectArtefactoDrafts(ENTREGA_ID, [ORDEN])
    expect(borradores).toHaveLength(1)
    expect(borradores[0]).toMatchObject({
      orden: ORDEN,
      ejercicio_id: EJ_ID,
      episode_id: EPISODIO_ID,
      codigo: CODIGO,
    })
  })

  it("(e) cerrar + 'Siguiente ejercicio' manda UN solo PATCH", async () => {
    const { llamadas, vista } = montar({ snapshot: CODIGO })
    await esperarEditorSembrado()
    await cerrar(vista)
    await waitFor(() => expect(patches(llamadas)).toHaveLength(1))
    await saltarReflexion(vista)
    const siguiente = await vista.findByRole("button", { name: /siguiente ejercicio/i })
    await act(async () => {
      fireEvent.click(siguiente)
    })
    expect(patches(llamadas)).toHaveLength(1)
  })

  it("si el primer PATCH falla, 'Siguiente ejercicio' lo reintenta y marca (segundo camino de cierre)", async () => {
    const { llamadas, vista } = montar({ snapshot: CODIGO, patchFallaLaPrimera: true })
    await esperarEditorSembrado()
    await cerrar(vista)
    await waitFor(() => expect(patches(llamadas)).toHaveLength(1))
    await saltarReflexion(vista)
    const siguiente = await vista.findByRole("button", { name: /siguiente ejercicio/i })
    await act(async () => {
      fireEvent.click(siguiente)
    })
    await waitFor(() => expect(patches(llamadas)).toHaveLength(2))
    expect(JSON.parse(patches(llamadas)[1]?.body ?? "{}")).toMatchObject({ completado: true })
  })
})

describe("BUG-1 intacto: sin codigo propio NO se marca", () => {
  it("(a) scaffold del docente: 0 PATCH", async () => {
    const { llamadas, vista } = montar({ scaffoldTp: "# scaffold del docente\n" })
    await esperarEditorSembrado()
    expect(editoresCreados[0]?.__opciones.value).toBe("# scaffold del docente\n")
    await cerrar(vista)
    await waitFor(() =>
      expect(llamadas.some((l) => l.url.includes("/classify_episode/"))).toBe(true),
    )
    expect(patches(llamadas)).toHaveLength(0)
  })

  it("(a') placeholder: 0 PATCH", async () => {
    const { llamadas, vista } = montar()
    await esperarEditorSembrado()
    await cerrar(vista)
    await waitFor(() =>
      expect(llamadas.some((l) => l.url.includes("/classify_episode/"))).toBe(true),
    )
    expect(patches(llamadas)).toHaveLength(0)
  })

  it("(b) edito y lo dejo vacio: no se usa el codigo sembrado, 0 PATCH", async () => {
    const { llamadas, vista } = montar({ snapshot: CODIGO })
    await esperarEditorSembrado()
    await act(async () => {
      editoresCreados[0]?.__tipear("")
    })
    await cerrar(vista)
    await waitFor(() =>
      expect(llamadas.some((l) => l.url.includes("/classify_episode/"))).toBe(true),
    )
    expect(patches(llamadas)).toHaveLength(0)
  })

  it("(c) tipeo codigo: UN PATCH y el borrador es el que escribio (precedencia intacta)", async () => {
    const { llamadas, vista } = montar({ snapshot: CODIGO })
    await esperarEditorSembrado()
    await act(async () => {
      editoresCreados[0]?.__tipear("print('nuevo')\n")
    })
    await cerrar(vista)
    await waitFor(() => expect(patches(llamadas)).toHaveLength(1))
    expect(collectArtefactoDrafts(ENTREGA_ID, [ORDEN])[0]?.codigo).toBe("print('nuevo')\n")
  })

  it("(f) un borrador de OTRO episodio no siembra: el editor no hereda lo viejo", async () => {
    saveArtefactoDraft(ENTREGA_ID, {
      orden: ORDEN,
      ejercicio_id: EJ_ID,
      episode_id: "ep-de-otro-intento",
      codigo: "print('de otro episodio')\n",
      language: "python",
    })
    montar()
    await esperarEditorSembrado()
    expect(editoresCreados[0]?.__opciones.value).not.toContain("de otro episodio")
  })
})
