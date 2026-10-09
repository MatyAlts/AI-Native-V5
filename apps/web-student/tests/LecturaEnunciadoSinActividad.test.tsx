/**
 * Hallazgo #6-B: `lectura_enunciado` no debe sumar el tiempo en que el alumno
 * esta tipeando en el editor o conversando con el tutor.
 *
 * Integracion del hook `useReadingTimeReporter` via EpisodeView, con reloj falso
 * (solo Date/setInterval/clearInterval: setTimeout queda real para waitFor) y un
 * IntersectionObserver que reporta el enunciado como visible.
 */
import { act, render } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { resetActividad } from "../src/lib/lecturaEnunciadoActividad"
import { EpisodeView } from "../src/pages/EpisodePage"
import { setupFetchMock } from "./_mocks"
import { editoresCreados, resetMonacoMock } from "./_monacoMock"

const TAREA_ID = "tp-lectura"
const EPISODIO_ID = "ep-lectura"

const originalIO = globalThis.IntersectionObserver

function instalarIOVisible() {
  globalThis.IntersectionObserver = class {
    constructor(private cb: IntersectionObserverCallback) {}
    observe(t: Element) {
      this.cb(
        [{ isIntersecting: true, intersectionRatio: 1, target: t } as IntersectionObserverEntry],
        this as unknown as IntersectionObserver,
      )
    }
    unobserve() {}
    disconnect() {}
    takeRecords() {
      return []
    }
  } as unknown as typeof IntersectionObserver
}

function montar() {
  const lecturas: { duration_seconds: number }[] = []
  setupFetchMock({
    "/resume": () => ({ ok: true }),
    [`/api/v1/tareas-practicas/${TAREA_ID}/ejercicios`]: () => [],
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
      inicial_codigo: null,
      language: "python",
      permite_pausa: true,
    }),
    [`/api/v1/episodes/${EPISODIO_ID}`]: () => ({
      episode_id: EPISODIO_ID,
      tarea_practica_id: TAREA_ID,
      comision_id: "com-1",
      estado: "open",
      opened_at: "2026-08-27T10:00:00Z",
      closed_at: null,
      last_code_snapshot: null,
      messages: [],
      notes: [],
      ejercicio_id: null,
      ejercicio_orden: null,
    }),
    [`/api/v1/episodes/${EPISODIO_ID}/events/lectura_enunciado`]: () => ({ ok: true }),
  })
  const stub = globalThis.fetch
  vi.stubGlobal("fetch", (url: string | URL | Request, init?: RequestInit) => {
    if (String(url).includes("/events/lectura_enunciado")) {
      lecturas.push(JSON.parse(String(init?.body ?? "{}")))
    }
    return (stub as typeof fetch)(url as never, init)
  })
  render(<EpisodeView episodeId={EPISODIO_ID} onExit={() => {}} />)
  return lecturas
}

/** waitFor usa setInterval (falso aca): sondeamos avanzando el reloj falso. */
async function esperarEditor() {
  for (let i = 0; i < 100 && editoresCreados.length === 0; i++) {
    await act(async () => {
      await vi.advanceTimersByTimeAsync(20)
    })
  }
  expect(editoresCreados.length).toBeGreaterThanOrEqual(1)
}

beforeEach(() => {
  resetMonacoMock()
  resetActividad()
  window.sessionStorage.clear()
  window.localStorage.clear()
  instalarIOVisible()
  vi.useFakeTimers({ toFake: ["Date", "setInterval", "clearInterval"] })
})

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
  globalThis.IntersectionObserver = originalIO
})

describe("lectura_enunciado vs. actividad en el editor", () => {
  it("sin actividad acumula el tiempo de lectura (~30 s al flush)", async () => {
    const lecturas = montar()
    await esperarEditor()
    await act(async () => {
      vi.advanceTimersByTime(30_000)
    })
    expect(lecturas).toHaveLength(1)
    expect(lecturas[0]?.duration_seconds).toBeGreaterThanOrEqual(29)
  })

  it("tipeando todo el tiempo NO acumula lectura (no hay flush)", async () => {
    const lecturas = montar()
    await esperarEditor()
    for (let i = 0; i < 30; i++) {
      await act(async () => {
        editoresCreados[0]?.__tipear(`x${i}`)
        vi.advanceTimersByTime(1000)
      })
    }
    await act(async () => {
      await Promise.resolve()
    })
    expect(lecturas).toHaveLength(0)
  })

  it("tipea 20 s y luego lee 10 s: cuenta solo lo posterior a la ventana de quietud", async () => {
    const lecturas = montar()
    await esperarEditor()
    for (let i = 0; i < 20; i++) {
      await act(async () => {
        editoresCreados[0]?.__tipear(`x${i}`)
        vi.advanceTimersByTime(1000)
      })
    }
    await act(async () => {
      vi.advanceTimersByTime(10_000)
    })
    expect(lecturas).toHaveLength(1)
    const s = lecturas[0]?.duration_seconds ?? 0
    // ~11 s desde la ultima tecla hasta el flush, menos la ventana de quietud
    // de 5 s: unos 6 s. Sin el fix serian ~30 s (todo el tramo).
    expect(s).toBeGreaterThanOrEqual(4)
    expect(s).toBeLessThanOrEqual(8)
  })
})
