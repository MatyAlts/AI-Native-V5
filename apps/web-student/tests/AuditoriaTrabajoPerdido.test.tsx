/**
 * AUDITORÍA DEL ALUMNO — dónde se le pierde el trabajo, y dónde se cuelga.
 *
 * Dos hallazgos que no se ven leyendo un archivo solo, porque nacen de que dos
 * piezas correctas por separado no se hablan entre sí.
 *
 * Tests de CARACTERIZACIÓN del estado actual: afirman lo que pasa hoy, que es
 * lo que no queremos. Si alguien lo arregla, se ponen rojos — a propósito.
 */

import { act, render, screen, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { EpisodeView } from "../src/pages/EpisodePage"
import { InstrumentosPage } from "../src/pages/InstrumentosPage"
import { editoresCreados, resetMonacoMock } from "./_monacoMock"

const TAREA_ID = "tp-perdida"
const EPISODIO_ID = "ep-perdida"

const TAREA = {
  id: TAREA_ID,
  codigo: "TP1",
  titulo: "Suma",
  enunciado: "Sumar dos numeros",
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

// ═══════════════════════════════════════════════════════════════════════════
// P1 — El borrador local es MÁS NUEVO que el snapshot del servidor, y aun así
//      el editor abre con el del servidor.
//
// Dos mecanismos de guardado corren en paralelo cada vez que el alumno tipea
// (`onEditDebounced`, `EpisodePage.tsx`):
//
//   a) `saveArtefactoDraft(...)` → `localStorage`, SÍNCRONO, no puede fallar
//      por red. Es lo que se manda al ENTREGAR.
//   b) el evento `edicion_codigo` → cola del CTR → ingesta asíncrona en el
//      servidor. Es de donde sale `last_code_snapshot`.
//
// Al REHIDRATAR el episodio (F5, volver a entrar, cambio de máquina), la
// cascada de `cascadaCodigo.ts` sólo mira (b). El borrador local (a) —que
// puede tener minutos más de trabajo si la cola del CTR quedó atrasada por la
// red— no es siquiera un candidato.
//
// Al alumno le pasa así: escribe media hora con el wifi intermitente, refresca
// sin querer, y el editor le abre con el código de hace veinte minutos. Su
// trabajo NO está perdido (sigue en `localStorage`, y se entregaría desde
// ahí), pero él no lo ve, no tiene forma de recuperarlo desde la UI, y lo
// razonable que va a hacer es reescribirlo — pisando el borrador bueno.
// ═══════════════════════════════════════════════════════════════════════════

describe("P1 — al rehidratar, el borrador local más nuevo se ignora", () => {
  it("el editor abre con el snapshot viejo del servidor y no con lo último que el alumno tipeó", async () => {
    const VIEJO = "# lo que el CTR alcanzo a ingerir hace 20 minutos\n"
    const NUEVO = "def sumar(a, b):\n    return a + b\n# media hora de trabajo\n"

    // El borrador local: lo ÚLTIMO que el alumno tenía en pantalla. Es la
    // misma clave y el mismo shape que escribe `saveArtefactoDraft` en la TP
    // monolítica (scope = episodio, orden = MONOLITHIC_ORDEN = 1).
    window.localStorage.setItem(
      `entrega_artefacto_${EPISODIO_ID}_1`,
      JSON.stringify({
        orden: 1,
        ejercicio_id: null,
        episode_id: EPISODIO_ID,
        codigo: NUEVO,
        language: "python",
        saved_at: Date.now(),
      }),
    )

    vi.stubGlobal(
      "fetch",
      vi.fn((url: string | URL | Request) => {
        const u = typeof url === "string" ? url : url.toString()
        const ok = (body: unknown) =>
          Promise.resolve({
            ok: true,
            status: 200,
            json: () => Promise.resolve(body),
            text: () => Promise.resolve(JSON.stringify(body)),
          } as Response)
        if (u.includes(`/api/v1/tareas-practicas/${TAREA_ID}/ejercicios`)) return ok([])
        if (u.includes(`/api/v1/tareas-practicas/${TAREA_ID}`)) return ok(TAREA)
        if (u.includes(`/api/v1/episodes/${EPISODIO_ID}`)) {
          return ok({
            episode_id: EPISODIO_ID,
            tarea_practica_id: TAREA_ID,
            comision_id: "com-1",
            estado: "open",
            opened_at: "2026-08-27T10:00:00Z",
            closed_at: null,
            // El servidor quedó atrasado: la cola del CTR no drenó.
            last_code_snapshot: VIEJO,
            messages: [],
            notes: [],
            ejercicio_id: null,
            ejercicio_orden: null,
          })
        }
        return ok({ data: [], meta: { cursor_next: null } })
      }),
    )

    render(<EpisodeView episodeId={EPISODIO_ID} onExit={() => {}} />)

    await waitFor(() => expect(editoresCreados.length).toBeGreaterThanOrEqual(1))
    const editor = editoresCreados[0]
    if (!editor) throw new Error("no se creo el editor")

    await waitFor(() => expect(editor.getValue()).toBe(VIEJO))

    // Lo que el alumno tenía escrito, que está ahí nomás en el mismo
    // navegador, no aparece en ningún lado de la pantalla.
    expect(editor.getValue()).not.toContain("media hora de trabajo")
    expect(screen.queryByText(/borrador|recuperar|version local/i)).toBeNull()

    // Y sigue guardado: el submit lo mandaría. Pero el alumno no lo sabe.
    const guardado = window.localStorage.getItem(`entrega_artefacto_${EPISODIO_ID}_1`)
    expect(guardado).not.toBeNull()
    expect(JSON.parse(guardado ?? "{}").codigo).toBe(NUEVO)
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// P2 — La pantalla de instrumentos se cuelga en skeleton para siempre.
//
// El patrón está repetido tres veces (cuestionario IA, pretest, transferencia):
//
//     .catch((e) => setError(String(e)))
//     ...
//     if (!catalogo) return <CardLoading ... />
//
// Si el fetch del catálogo falla, `catalogo` queda `null` para siempre (el
// `useEffect` no reintenta) y el `return` temprano gana. Y el `{error && ...}`
// que mostraría el mensaje vive DENTRO del JSX que sólo se renderiza cuando
// `catalogo` existe: el error se setea y no se pinta nunca.
//
// El alumno mira tres tarjetas cargando indefinidamente. Nada le dice que se
// rompió, ni que puede volver más tarde.
// ═══════════════════════════════════════════════════════════════════════════

describe("P2 — los instrumentos se cuelgan en skeleton eterno sin mostrar el error", () => {
  it("con el backend caído quedan cargando para siempre y el mensaje de error nunca se pinta", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() =>
        Promise.resolve({
          ok: false,
          status: 503,
          json: () => Promise.resolve({ detail: "service unavailable" }),
          text: () => Promise.resolve('{"detail":"service unavailable"}'),
        } as Response),
      ),
    )

    const { container } = render(
      <InstrumentosPage
        comisionId="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
        studentPseudonym="b1b1b1b1-0001-0001-0001-000000000001"
      />,
    )

    // Tiempo de sobra para que las tres promesas rechacen y React repinte.
    await act(async () => {
      await new Promise((r) => setTimeout(r, 300))
    })

    // Los títulos siguen ahí (los pinta el skeleton), pero el contenido no
    // llegó nunca.
    expect(await screen.findByText(/Cuestionario sobre experiencia previa con IA/i)).toBeDefined()

    // Y no hay UNA sola palabra que le diga al alumno que algo falló.
    expect(container.textContent ?? "").not.toMatch(
      /error|no se pudo|no pudimos|fall|reintent|volve mas tarde/i,
    )

    // Y los spinners de `CardLoading` siguen girando, indefinidamente: uno por
    // cada uno de los tres instrumentos.
    expect(container.querySelectorAll(".animate-spin").length).toBe(3)
  })
})
