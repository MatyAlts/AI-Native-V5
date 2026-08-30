/**
 * AUDITORÍA DEL ALUMNO — reproducciones, no especulación.
 *
 * Cada `it` de este archivo monta el componente real y reproduce un momento
 * concreto del recorrido del alumno en el que algo se rompe. Los asserts
 * describen LO QUE EL ALUMNO VE, no lo que el código hace: por eso muchos
 * afirman la presencia de un string feo en pantalla en vez de afirmar que
 * está bien. Son tests de caracterización del estado ACTUAL — si alguien
 * arregla el hallazgo, el test se pone rojo y hay que reescribirlo (y eso es
 * lo que queremos: que el arreglo sea visible).
 *
 * NO son tests de regresión de comportamiento deseado.
 */

import { act, fireEvent, render } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { EpisodeView } from "../src/pages/EpisodePage"
import { resetMonacoMock } from "./_monacoMock"

const TAREA_ID = "tp-auditoria"
const EPISODIO_ID = "ep-auditoria"

const ESTADO_EPISODIO = {
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
}

const TAREA = {
  id: TAREA_ID,
  codigo: "TP1",
  titulo: "Suma de dos numeros",
  enunciado: "Escribi un programa que sume dos numeros",
  fecha_inicio: null,
  fecha_fin: null,
  peso: "1.00",
  estado: "published",
  version: 1,
  inicial_codigo: null,
  language: "python",
  permite_pausa: true,
  test_cases: [],
}

/**
 * Mock de fetch con control por path Y por método: `setupFetchMock` sólo
 * matchea por prefijo de URL, y acá hace falta que el GET del episodio ande
 * mientras el POST de cierre se cae — que es exactamente el escenario del
 * alumno con la red intermitente.
 */
function mockearRed(opciones: {
  cierreFalla?: "red" | number
  hidratacionFalla?: boolean
  /** El SSE del tutor abre el socket y NO manda un solo chunk, nunca. */
  tutorSeCuelga?: boolean
}) {
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string | URL | Request, init?: RequestInit) => {
      const u = typeof url === "string" ? url : url.toString()
      const metodo = (init?.method ?? "GET").toUpperCase()

      const ok = (body: unknown) =>
        Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve(body),
          text: () => Promise.resolve(JSON.stringify(body)),
        } as Response)

      if (u.includes("/close")) {
        if (opciones.cierreFalla === "red") {
          // Lo que tira `fetch` cuando el alumno se queda sin internet.
          return Promise.reject(new TypeError("Failed to fetch"))
        }
        if (typeof opciones.cierreFalla === "number") {
          return Promise.resolve({
            ok: false,
            status: opciones.cierreFalla,
            json: () => Promise.resolve({ detail: "boom" }),
            text: () => Promise.resolve('{"detail":"boom"}'),
          } as Response)
        }
        return ok({ ok: true })
      }
      if (u.includes("/message")) {
        if (opciones.tutorSeCuelga) {
          // El servidor acepta el POST y abre el stream, pero el LLM se murió
          // del otro lado sin cerrar el socket: `reader.read()` no resuelve
          // NUNCA. `sendMessage` (lib/api.ts) no le pone AbortController ni
          // timeout, y el interceptor de fetch exime a los SSE del suyo.
          return Promise.resolve({
            ok: true,
            status: 200,
            body: { getReader: () => ({ read: () => new Promise<never>(() => {}) }) },
          } as unknown as Response)
        }
        return Promise.resolve({
          ok: true,
          status: 200,
          body: {
            getReader: () => {
              let entregado = false
              return {
                read: () => {
                  if (entregado) return Promise.resolve({ done: true, value: undefined })
                  entregado = true
                  return Promise.resolve({
                    done: false,
                    value: new TextEncoder().encode(
                      'data: {"type":"chunk","content":"hola"}\ndata: {"type":"done","chunks_used_hash":"x","seqs":{}}\n',
                    ),
                  })
                },
              }
            },
          },
        } as unknown as Response)
      }
      if (u.includes("/resume")) return ok({ ok: true })
      if (u.includes(`/api/v1/episodes/${EPISODIO_ID}`) && metodo === "GET") {
        if (opciones.hidratacionFalla) {
          return Promise.reject(new TypeError("Failed to fetch"))
        }
        return ok(ESTADO_EPISODIO)
      }
      if (u.includes(`/api/v1/tareas-practicas/${TAREA_ID}/ejercicios`)) return ok([])
      if (u.includes(`/api/v1/tareas-practicas/${TAREA_ID}`)) return ok(TAREA)
      return ok({ data: [], meta: { cursor_next: null } })
    }),
  )
}

beforeEach(() => {
  resetMonacoMock()
  window.sessionStorage.clear()
  window.localStorage.clear()
  vi.spyOn(console, "warn").mockImplementation(() => {})
  vi.spyOn(console, "debug").mockImplementation(() => {})
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe("A1 — el alumno cierra el episodio y se le cae la red", () => {
  it("le muestra el stack de un TypeError, no qué le pasó ni qué hacer", async () => {
    mockearRed({ cierreFalla: "red" })
    const { findByTestId, findByText } = render(
      <EpisodeView episodeId={EPISODIO_ID} onExit={() => {}} />,
    )

    const cerrar = await findByTestId("close-episode-button")
    await act(async () => {
      fireEvent.click(cerrar)
    })

    // Esto es LITERALMENTE lo que ve un alumno de primer año a las 11 de la
    // noche cuando el wifi le parpadea: la representación en texto de un
    // objeto Error de JavaScript, en una barra roja.
    const banner = await findByText(/Error cerrando:/)
    expect(banner.textContent).toContain("TypeError: Failed to fetch")
    // No dice "no hay internet", no dice "reintentá", no dice "tu código está
    // guardado". No hay botón de reintentar.
  })

  it("la ÚNICA acción que le ofrece la barra de error es 'Salir'", async () => {
    mockearRed({ cierreFalla: 500 })
    const { findByTestId, findByText, container } = render(
      <EpisodeView episodeId={EPISODIO_ID} onExit={() => {}} />,
    )

    const cerrar = await findByTestId("close-episode-button")
    await act(async () => {
      fireEvent.click(cerrar)
    })

    const banner = (await findByText(/Error cerrando:/)).closest("div")
    expect(banner).not.toBeNull()
    const botones = Array.from(banner?.querySelectorAll("button") ?? []).map((b) =>
      b.textContent?.trim(),
    )
    // Un solo botón, y es el destructivo. No hay "Reintentar".
    expect(botones).toEqual(["Salir"])
    expect(botones).not.toContain("Reintentar")
    expect(container.textContent).not.toMatch(/reintent/i)
  })
})

describe("A2 — la hidratación del episodio falla", () => {
  it('deja "No se pudo cargar el episodio." sin ninguna forma de reintentar', async () => {
    mockearRed({ hidratacionFalla: true })
    const { findByText, container } = render(
      <EpisodeView episodeId={EPISODIO_ID} onExit={() => {}} />,
    )

    await findByText("No se pudo cargar el episodio.")
    // El mensaje no distingue "el servidor está caído" de "no tenés internet"
    // de "el episodio se rompió". Y la única salida es abandonar.
    expect(container.textContent).not.toMatch(/reintent|volver a intentar/i)
  })
})

describe("A4 — el tutor deja de responder y el chat queda congelado sin salida", () => {
  it("el input y el botón quedan deshabilitados para siempre, sin cancelar ni avisar", async () => {
    mockearRed({ tutorSeCuelga: true })
    const { findByTestId, queryByTestId, container } = render(
      <EpisodeView episodeId={EPISODIO_ID} onExit={() => {}} />,
    )

    const input = (await findByTestId("tutor-input")) as HTMLTextAreaElement
    await act(async () => {
      fireEvent.change(input, { target: { value: "no entiendo la consigna" } })
    })
    await act(async () => {
      fireEvent.keyDown(input, { key: "Enter", shiftKey: false })
    })

    // Le damos tiempo de sobra: mucho más de lo que un alumno espera antes de
    // pensar que se rompió.
    await new Promise((r) => setTimeout(r, 300))

    // El textarea quedó bloqueado: no puede escribir otra cosa, ni reformular.
    expect(input.disabled).toBe(true)

    // El único botón del compositor es "Enviar", y está deshabilitado con un
    // spinner. NO hay ningún botón de cancelar / detener la respuesta.
    expect(container.textContent).not.toMatch(/cancelar|detener|parar/i)

    // Y no aparece el aviso de "el tutor está saturado": ese sale del `catch`
    // del stream, y un stream que no resuelve nunca no tira nunca.
    expect(queryByTestId("tutor-send-error")).toBeNull()
    expect(queryByTestId("tutor-retry-button")).toBeNull()

    // Resultado para el alumno: burbuja del tutor vacía, spinner eterno, y la
    // única forma de recuperar el chat es recargar la página.
  })
})

describe("A5 — la acusación de haber salido de la pestaña se dispara con cualquier cosa", () => {
  it("volver a la pestaña tras UN segundo ya muestra el overlay bloqueante", async () => {
    mockearRed({})
    const { findByTestId, findByText } = render(
      <EpisodeView episodeId={EPISODIO_ID} onExit={() => {}} />,
    )
    // Esperamos a que el episodio esté hidratado (el listener se registra
    // recién cuando `closed` es false y la página está montada de verdad).
    await findByTestId("tutor-input")

    const ocultar = (estado: "hidden" | "visible") => {
      Object.defineProperty(document, "visibilityState", {
        configurable: true,
        get: () => estado,
      })
      document.dispatchEvent(new Event("visibilitychange"))
    }

    await act(async () => {
      ocultar("hidden")
    })
    await act(async () => {
      ocultar("visible")
    })

    // No hay umbral mínimo: cero segundos afuera alcanzan. En un teléfono esto
    // lo dispara el auto-bloqueo de pantalla, una notificación, o una llamada.
    const overlay = await findByText(/Saliste de la evaluación/i)
    expect(overlay).toBeDefined()
    // Y el texto lo trata como una infracción registrada, no como un accidente.
    await findByText(/quedó registrada en la trazabilidad/i)
  })
})
