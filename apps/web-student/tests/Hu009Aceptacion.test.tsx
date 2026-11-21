/**
 * Aceptacion HU-009, lado alumno (orquestador, antes de construir; el
 * constructor no la modifica).
 *
 * Sale de la prueba 2 como alumno en produccion (20/11/2026).
 *
 * C02  Sobreuso sin confirmar: el cierre dice "Muchas consultas seguidas".
 * C03  Autonomo competente: el cierre dice "¡Muy bien! Resolviste por tu cuenta".
 *      (C02 y C03 dependen del POST con subgrupo, que prueba el classifier; aca
 *      se fija que la pantalla lo use.)
 * C05  Cerrar sin reflexion termina SIEMPRE en la misma pantalla, aunque la
 *      clasificacion llegue despues de saltear la reflexion, y sin jerga.
 * C11  Si Probar falla y esperado y obtenido se ven iguales ("º" contra "°"),
 *      la pantalla marca el primer caracter distinto y su codigo.
 * C12  "Cambiaste mucho de estrategia" no sale con pocas consultas.
 * N01  Un delegador sigue viendo el mensaje de delegacion.
 */
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { CodeEditor } from "../src/components/CodeEditor"
import type { Classification, TestCasePublic } from "../src/lib/api"
import { EpisodeView, buildPedagogicalFeedback } from "../src/pages/EpisodePage"
import { setupFetchMock } from "./_mocks"
import { editoresCreados, resetMonacoMock } from "./_monacoMock"
import { type PyodideFake, instalarPyodideFake } from "./_pyodideFake"

function clasif(over: Record<string, unknown>): Classification {
  return {
    episode_id: "e",
    comision_id: "c",
    classifier_config_hash: "h",
    appropriation: "apropiacion_superficial",
    appropriation_reason: "",
    ct_summary: null,
    ccd_mean: null,
    ccd_orphan_ratio: null,
    cii_stability: null,
    cii_evolution: null,
    is_current: true,
    subgrupo: null,
    pasiva_por_sobreuso: false,
    ...over,
  } as unknown as Classification
}

function sg(key: string, eje: string) {
  return {
    key,
    label: key,
    accion_docente: "x",
    eje,
    dimensiones: { autonomia: 0.5, experimentacion: 0.5, persistencia: 0.5, foco: 0.5 },
  }
}

describe("HU-009 · mensaje de cierre", () => {
  it("C02: sobreuso sin confirmar da Muchas consultas seguidas", () => {
    const fb = buildPedagogicalFeedback(
      clasif({
        appropriation: "delegacion_pasiva",
        subgrupo: sg("dependiente_sobreuso", "delegacion_pasiva"),
        pasiva_por_sobreuso: true,
      }),
    )
    expect(fb.titulo).toBe("Muchas consultas seguidas")
  })

  it("C03: autonomo competente da Muy bien", () => {
    const fb = buildPedagogicalFeedback(
      clasif({ appropriation: "autonomo", subgrupo: sg("autonomo_competente", "autonomo") }),
    )
    expect(fb.titulo).toBe("¡Muy bien!")
    expect(fb.mensaje).toMatch(/Resolviste por tu cuenta/)
  })

  it("N01: un delegador sigue viendo delegacion", () => {
    const fb = buildPedagogicalFeedback(
      clasif({
        appropriation: "delegacion_pasiva",
        subgrupo: sg("dependiente_delegador", "delegacion_pasiva"),
      }),
    )
    expect(fb.mensaje).toMatch(/lo hizo el tutor/i)
  })
})

describe("HU-009 · consejo de estrategia (C12)", () => {
  const bajo = { cii_stability: 0.1, cii_evolution: 0.1 }

  it("con 2 consultas no aparece", () => {
    const fb = buildPedagogicalFeedback(clasif({ ...bajo, cii_iteraciones: 2 }))
    expect(fb.sugerencias.join(" ")).not.toMatch(/estrategia/i)
  })

  it("sin el dato (clasificaciones viejas) no aparece", () => {
    const fb = buildPedagogicalFeedback(clasif({ ...bajo }))
    expect(fb.sugerencias.join(" ")).not.toMatch(/estrategia/i)
  })

  it("con 5 consultas sale un consejo mas que con 2", () => {
    const pocas = buildPedagogicalFeedback(clasif({ ...bajo, cii_iteraciones: 2 }))
    const muchas = buildPedagogicalFeedback(clasif({ ...bajo, cii_iteraciones: 5 }))
    expect(muchas.sugerencias.length).toBe(pocas.sugerencias.length + 1)
  })
})

// ── C05: cerrar sin reflexion ───────────────────────────────────────────────
const EP = "ep-hu009"
const TAREA = "tp-hu009"

function montarCierre() {
  let soltar: (() => void) | null = null
  const clasificacionLista = new Promise<void>((r) => {
    soltar = r
  })
  setupFetchMock({
    [`/api/v1/episodes/${EP}/close`]: () => ({ ok: true }),
    "/resume": () => ({ ok: true }),
    [`/api/v1/tareas-practicas/${TAREA}`]: () => ({
      id: TAREA,
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
    [`/api/v1/episodes/${EP}`]: () => ({
      episode_id: EP,
      tarea_practica_id: TAREA,
      comision_id: "com-1",
      estado: "open",
      opened_at: "2026-11-20T10:00:00Z",
      closed_at: null,
      last_code_snapshot: null,
      messages: [],
      notes: [],
    }),
  })
  const base = globalThis.fetch
  vi.stubGlobal("fetch", async (url: string | URL | Request, init?: RequestInit) => {
    const u = typeof url === "string" ? url : url.toString()
    if (u.includes(`/api/v1/classify_episode/${EP}`)) {
      // La clasificacion tarda: el alumno saltea la reflexion antes de que llegue.
      await clasificacionLista
      return {
        ok: true,
        status: 201,
        json: async () =>
          clasif({
            episode_id: EP,
            appropriation: "apropiacion_reflexiva",
            subgrupo: sg("colaborador_reflexivo", "reflexiva"),
          }),
      } as Response
    }
    return (base as typeof fetch)(url as never, init)
  })
  const onExit = vi.fn()
  const vista = render(<EpisodeView episodeId={EP} onExit={onExit} />)
  return { vista, onExit, soltar: () => soltar?.() }
}

beforeEach(() => {
  resetMonacoMock()
  window.sessionStorage.clear()
  window.localStorage.clear()
  window.sessionStorage.setItem("active-episode-id", EP)
})
afterEach(() => vi.unstubAllGlobals())

describe("HU-009 · cerrar sin reflexion (C05)", () => {
  it("saltear antes de que llegue la clasificacion igual muestra la pantalla de cierre", async () => {
    const { vista, onExit, soltar } = montarCierre()
    await waitFor(() => expect(editoresCreados.length).toBeGreaterThanOrEqual(1))
    await act(async () => {
      editoresCreados[0]?.__tipear("print('hola')")
    })
    await act(async () => {
      fireEvent.click(await vista.findByTestId("close-episode-button"))
    })
    await act(async () => {
      fireEvent.click(await screen.findByText("No quiero reflexionar ahora"))
    })
    await act(async () => {
      soltar()
    })
    expect(await screen.findByText(/Tu trabajo qued[oó] registrado/i)).toBeTruthy()
    expect(onExit).not.toHaveBeenCalled()
  })

  it("la pantalla sin reflexion no usa jerga", async () => {
    const { vista, soltar } = montarCierre()
    await waitFor(() => expect(editoresCreados.length).toBeGreaterThanOrEqual(1))
    await act(async () => {
      editoresCreados[0]?.__tipear("print('hola')")
    })
    await act(async () => {
      fireEvent.click(await vista.findByTestId("close-episode-button"))
    })
    await act(async () => {
      soltar()
    })
    await act(async () => {
      fireEvent.click(await screen.findByText("No quiero reflexionar ahora"))
    })
    await screen.findByText(/Tu trabajo qued[oó] registrado/i)
    const texto = document.body.textContent ?? ""
    expect(texto).not.toMatch(/\bN4\b/)
    expect(texto).not.toMatch(/apropiaci[oó]n/i)
  })
})

// ── C11: el caracter que no se ve ───────────────────────────────────────────
const CASOS: TestCasePublic[] = [
  {
    id: "c1",
    name: "temperatura",
    type: "stdin_stdout",
    code: "20",
    expected: "68.0 °F",
    is_public: true,
  },
]

let pyodide: PyodideFake | null = null
afterEach(() => {
  pyodide?.desinstalar()
  pyodide = null
})

async function probar(obtenido: string) {
  pyodide = instalarPyodideFake()
  pyodide.resultadosDeTests = [
    {
      id: "c1",
      name: "temperatura",
      type: "stdin_stdout",
      passed: false,
      expected: "68.0 °F",
      actual: obtenido,
      comparacion: obtenido,
      stdin: "20",
      error: null,
    },
  ]
  render(<CodeEditor initialCode="x = 0" language="python" testCases={CASOS} />)
  await waitFor(() => expect(editoresCreados.length).toBeGreaterThanOrEqual(1))
  await waitFor(() =>
    expect((screen.getByTestId("run-tests-button") as HTMLButtonElement).disabled).toBe(false),
  )
  await act(async () => {
    screen.getByTestId("run-tests-button").click()
  })
  await waitFor(() => expect(screen.getByText(/^Esperado$/i)).toBeTruthy())
}

describe("HU-009 · primer caracter distinto (C11)", () => {
  it("ordinal º contra grado °: marca la posicion y los dos codigos", async () => {
    await probar("68.0 ºF")
    const marca = await screen.findByTestId("primer-diferencia")
    const t = marca.textContent ?? ""
    expect(t).toMatch(/U\+00B0/i)
    expect(t).toMatch(/U\+00BA/i)
  })

  it("si la diferencia se ve a simple vista, igual no rompe y marca", async () => {
    await probar("68.0 F")
    expect(await screen.findByTestId("primer-diferencia")).toBeTruthy()
  })
})
