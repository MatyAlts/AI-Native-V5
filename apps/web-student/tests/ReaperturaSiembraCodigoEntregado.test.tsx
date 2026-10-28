/**
 * El editor de un ejercicio reabierto abre con el codigo que el alumno YA
 * entrego cuando no hay nada mejor (change
 * `editor-muestra-codigo-entregado-al-reabrir`, D1).
 *
 * Cubre la "cadena cortada" de la REAPERTURA del tutor-service: si el episodio
 * cerrado mas reciente no tiene codigo, el estado llega sin `last_code_snapshot`
 * y el editor caia al scaffold. Ahora cae al artefacto sellado de la entrega.
 *
 * La otra mitad de lo que se protege es la TESIS: sembrar el editor NO emite
 * `edicion_codigo` (el editor arranca con `initialCode` como baseline), y
 * tipear una letra emite exactamente uno con `diff_chars` = 1.
 */
import { act, render, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { LANGUAGE_PLACEHOLDER } from "../src/lib/api"
import { saveArtefactoDraft } from "../src/lib/artefactos"
import { EpisodeView } from "../src/pages/EpisodePage"
import { setupFetchMock } from "./_mocks"
import { editoresCreados, resetMonacoMock } from "./_monacoMock"

const TAREA_ID = "tp-reapertura"
const EPISODIO_ID = "ep-reapertura"
const ENTREGA_ID = "entrega-reapertura"
const ORDEN = 1
const EJ_ID = "ej-1"
const ENTREGADO = "def resolver():\n    return 42\n"

type Llamada = { url: string; method: string; body: string }
type Artefacto = { orden: number; ejercicio_id: string | null; codigo: string }

interface Opciones {
  snapshot?: string | null
  artefactos?: Artefacto[]
  legacy?: boolean
  artefactoStatus?: number
  scaffoldTp?: string | null
  monolitica?: boolean
}

function montar(op: Opciones = {}) {
  const llamadas: Llamada[] = []
  const artefactoRespuesta = () => ({
    entrega_id: ENTREGA_ID,
    legacy: op.legacy ?? false,
    artefactos: (op.artefactos ?? []).map((a) => ({
      ...a,
      episode_id: "ep-viejo",
      language: "python",
      sha256: "x",
      created_at: "2026-10-20T10:00:00Z",
    })),
  })
  setupFetchMock({
    [`/api/v1/entregas/${ENTREGA_ID}/artefacto`]:
      op.artefactoStatus && op.artefactoStatus !== 200
        ? { ok: false, status: op.artefactoStatus, body: () => ({ detail: "boom" }) }
        : artefactoRespuesta,
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
      ejercicio_id: op.monolitica ? null : EJ_ID,
      ejercicio_orden: op.monolitica ? null : ORDEN,
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
      {...(op.monolitica
        ? {}
        : {
            ejercicioContext: { entregaId: ENTREGA_ID, ejercicioId: EJ_ID, ejercicioOrden: ORDEN },
          })}
    />,
  )
  return { llamadas, vista }
}

const getsArtefacto = (ll: Llamada[]) =>
  ll.filter((l) => l.method === "GET" && l.url.includes("/artefacto"))
const edicionesPorRed = (ll: Llamada[]) => ll.filter((l) => l.url.includes("edicion_codigo"))

async function valorInicial(): Promise<string> {
  await waitFor(() => expect(editoresCreados.length).toBeGreaterThanOrEqual(1))
  await waitFor(() => expect(editoresCreados[0]?.__opciones.value).not.toBe(""))
  return String(editoresCreados[0]?.__opciones.value)
}

beforeEach(() => {
  resetMonacoMock()
  window.sessionStorage.clear()
  window.localStorage.clear()
  window.sessionStorage.setItem("active-episode-id", EPISODIO_ID)
})
afterEach(() => vi.unstubAllGlobals())

describe("la cadena cortada cae al codigo entregado", () => {
  it("sin snapshot ni borrador, abre con el artefacto del mismo orden y ejercicio_id", async () => {
    const { llamadas } = montar({
      artefactos: [
        { orden: 2, ejercicio_id: "ej-otro", codigo: "# del ejercicio 2\n" },
        { orden: ORDEN, ejercicio_id: EJ_ID, codigo: ENTREGADO },
      ],
    })
    expect(await valorInicial()).toBe(ENTREGADO)
    expect(getsArtefacto(llamadas)).toHaveLength(1)
  })

  it("gana al scaffold del docente", async () => {
    montar({
      scaffoldTp: "# scaffold del docente\n",
      artefactos: [{ orden: ORDEN, ejercicio_id: EJ_ID, codigo: ENTREGADO }],
    })
    expect(await valorInicial()).toBe(ENTREGADO)
  })
})

describe("triangulacion", () => {
  it("(a) con snapshot propio/heredado NO pide el artefacto y gana el snapshot", async () => {
    const { llamadas } = montar({
      snapshot: "print('snapshot')\n",
      artefactos: [{ orden: ORDEN, ejercicio_id: EJ_ID, codigo: ENTREGADO }],
    })
    expect(await valorInicial()).toBe("print('snapshot')\n")
    expect(getsArtefacto(llamadas)).toHaveLength(0)
  })

  it("(a') con borrador local del MISMO episodio NO pide el artefacto", async () => {
    saveArtefactoDraft(ENTREGA_ID, {
      orden: ORDEN,
      ejercicio_id: EJ_ID,
      episode_id: EPISODIO_ID,
      codigo: "print('borrador')\n",
      language: "python",
    })
    const { llamadas } = montar({
      artefactos: [{ orden: ORDEN, ejercicio_id: EJ_ID, codigo: ENTREGADO }],
    })
    expect(await valorInicial()).toBe("print('borrador')\n")
    expect(getsArtefacto(llamadas)).toHaveLength(0)
  })

  it("(b) artefacto de otro orden / otro ejercicio_id: se ignora y cae al placeholder", async () => {
    montar({
      artefactos: [
        { orden: 2, ejercicio_id: EJ_ID, codigo: "# otro orden\n" },
        { orden: ORDEN, ejercicio_id: "ej-otro", codigo: "# otro ejercicio\n" },
      ],
    })
    expect(await valorInicial()).toBe(LANGUAGE_PLACEHOLDER.python)
  })

  it("(c) GET 500 -> placeholder y la hidratacion no falla", async () => {
    const { vista } = montar({ artefactoStatus: 500 })
    expect(await valorInicial()).toBe(LANGUAGE_PLACEHOLDER.python)
    expect(vista.queryByText(/No se pudo cargar el episodio/i)).toBeNull()
  })

  it("(c) entrega legacy -> placeholder aunque traiga filas", async () => {
    montar({ legacy: true, artefactos: [{ orden: ORDEN, ejercicio_id: EJ_ID, codigo: ENTREGADO }] })
    expect(await valorInicial()).toBe(LANGUAGE_PLACEHOLDER.python)
  })

  it("(c) codigo entregado vacio -> placeholder", async () => {
    montar({ artefactos: [{ orden: ORDEN, ejercicio_id: EJ_ID, codigo: "   \n" }] })
    expect(await valorInicial()).toBe(LANGUAGE_PLACEHOLDER.python)
  })

  it("(d) TP monolitica (sin ejercicioContext): 0 GET a /artefacto", async () => {
    const { llamadas } = montar({ monolitica: true })
    expect(await valorInicial()).toBe(LANGUAGE_PLACEHOLDER.python)
    expect(getsArtefacto(llamadas)).toHaveLength(0)
  })
})

describe("tesis: sembrar no emite edicion_codigo", () => {
  it("cargar el codigo entregado y esperar mas que el debounce deja 0 edicion_codigo", async () => {
    const { llamadas } = montar({
      artefactos: [{ orden: ORDEN, ejercicio_id: EJ_ID, codigo: ENTREGADO }],
    })
    expect(await valorInicial()).toBe(ENTREGADO)
    await act(async () => {
      await new Promise((r) => setTimeout(r, 2500))
    })
    expect(edicionesPorRed(llamadas)).toEqual([])
    expect(window.localStorage.getItem(`ctr-queue:${EPISODIO_ID}`) ?? "").not.toContain(
      "edicion_codigo",
    )
  })

  it("teclear UNA letra emite exactamente un edicion_codigo con diff_chars = 1", async () => {
    const { llamadas } = montar({
      artefactos: [{ orden: ORDEN, ejercicio_id: EJ_ID, codigo: ENTREGADO }],
    })
    expect(await valorInicial()).toBe(ENTREGADO)
    await act(async () => {
      editoresCreados[0]?.__tipear(`${ENTREGADO}x`)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 2500))
    })
    const ediciones = edicionesPorRed(llamadas)
    expect(ediciones).toHaveLength(1)
    expect(ediciones[0]?.body).toContain('"diff_chars":1')
  })
})
