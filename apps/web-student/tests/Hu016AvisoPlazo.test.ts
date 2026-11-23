/**
 * Aceptacion HU-016, aviso de plazo al alumno (orquestador, antes de construir;
 * el constructor no la modifica). Juani (22/11): "merega y segui con los proximos".
 *
 * Hallazgo F17 de HU-014: con la TP vencida, al recargar el alumno veia
 * "Error abriendo episodio: Error: open episode failed: 403", sin saber que
 * habia vencido el plazo. Y al entregar vencido (C03 de HU-016, 409) veria
 * "submit entrega failed: 409 {...}".
 *
 * Contrato: `src/utils/mensajesPlazo.ts` exporta
 *   - mensajeAlAbrirEpisodio(e: unknown): string
 *   - mensajeAlEntregar(e: unknown): string
 * que reciben el error que tiran `openEpisode` y `submitEntrega` de `lib/api.ts`.
 * `materia.$id.tsx` y `ExerciseListView.tsx` muestran ese mensaje tal cual.
 *
 * C05  TP vencida al abrir -> "Vencio el plazo..." sin codigos ni jerga.
 * C06  Entrega rechazada por plazo -> mismo tipo de aviso.
 * N03  Otro error sigue diciendo que no se pudo, sin el texto crudo.
 */
import { afterEach, describe, expect, it, vi } from "vitest"
import { openEpisode, submitEntrega } from "../src/lib/api"
import { mensajeAlAbrirEpisodio, mensajeAlEntregar } from "../src/utils/mensajesPlazo"

function respuesta(status: number, detail: string) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response(JSON.stringify({ detail }), { status })),
  )
}

async function errorDe(fn: () => Promise<unknown>): Promise<unknown> {
  try {
    await fn()
  } catch (e) {
    return e
  }
  throw new Error("se esperaba que fallara")
}

const CRUDO = /failed|Error:|\b40[39]\b|\b500\b|detail|deadline/i

afterEach(() => {
  vi.unstubAllGlobals()
})

describe("HU-016 · aviso de plazo", () => {
  it("C05: abrir con la TP vencida dice que vencio el plazo", async () => {
    respuesta(403, "Tarea práctica fuera de plazo (deadline pasado)")
    const e = await errorDe(() =>
      openEpisode({ tarea_practica_id: "t", comision_id: "c" } as never),
    )
    const msg = mensajeAlAbrirEpisodio(e)
    expect(msg).toMatch(/venci[oó] el plazo/i)
    expect(msg).not.toMatch(CRUDO)
  })

  it("C06: entregar vencido dice que vencio el plazo", async () => {
    respuesta(409, "Vencio el plazo de entrega de esta TP.")
    const e = await errorDe(() => submitEntrega("e1", []))
    const msg = mensajeAlEntregar(e)
    expect(msg).toMatch(/venci[oó] el plazo/i)
    expect(msg).not.toMatch(CRUDO)
  })

  it("N03: otro error al abrir no muestra el texto crudo", async () => {
    respuesta(500, "Internal Server Error")
    const e = await errorDe(() =>
      openEpisode({ tarea_practica_id: "t", comision_id: "c" } as never),
    )
    const msg = mensajeAlAbrirEpisodio(e)
    expect(msg).toMatch(/no se pudo/i)
    expect(msg).not.toMatch(CRUDO)
    expect(msg).not.toMatch(/venci[oó] el plazo/i)
  })

  it("N03: otro error al entregar no se confunde con el plazo", async () => {
    respuesta(422, "Ejercicios incompletos: [2]. Completa todos antes de entregar.")
    const e = await errorDe(() => submitEntrega("e1", []))
    const msg = mensajeAlEntregar(e)
    expect(msg).not.toMatch(/venci[oó] el plazo/i)
    expect(msg).toMatch(/Ejercicios incompletos/)
    expect(msg).not.toMatch(/failed/i)
  })
})
