/**
 * ED-4 — la siembra del codigo heredado NO puede emitir `edicion_codigo`.
 *
 * Equivalente, para el camino del arrastre entre ejercicios, del test
 * "el re-montaje NO emite un edicion_codigo fantasma" de
 * `CodeEditorRemonte.test.tsx`. Mismo invariante y mismo motivo: un evento de
 * edicion que el alumno no hizo es evidencia falsa en la cadena CTR, y peor que
 * perder codigo — la cadena es lo que sostiene la tesis.
 *
 * Como se prueba
 * --------------
 * Se monta `EpisodeView` de verdad (Monaco doblado por `_monacoMock.ts`, la
 * red por `setupFetchMock`) con `sessionStorage` ya sembrado como lo dejaria el
 * ejercicio 1, y se abre el ejercicio 2 de la MISMA TP. Despues de la
 * hidratacion:
 *
 *   1. el editor tiene que haberse creado con el codigo heredado en
 *      `editor.create({ value })` — o sea por `initialCode`, el mismo camino
 *      que `last_code_snapshot`;
 *   2. NINGUN POST a `.../events/edicion_codigo`, ni ahora ni pasado el
 *      debounce.
 *
 * El punto 1 no es decorado: sin el, el punto 2 pasaria solo porque no se
 * sembro nada. Los dos juntos son la propiedad. Si alguien "mejorara" la
 * siembra llamando `editor.setValue()` despues del mount, el doble de Monaco
 * dispara `onDidChangeModelContent` (igual que Monaco real) y el punto 2 cae.
 */
import { act, render, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { EpisodeView } from "../src/pages/EpisodePage"
import { setupFetchMock } from "./_mocks"
import { editoresCreados, resetMonacoMock } from "./_monacoMock"

const TAREA_ID = "tp-e2-agenda"
const EPISODIO_ID = "ep-ejercicio-2"

/** Lo que el alumno dejo escrito en el ejercicio 1 de esta misma TP. */
const CODIGO_DEL_EJERCICIO_1 = "def saludar(nombre):\n    print('Hola', nombre)\n"

/** Estado del episodio del ejercicio 2: sin snapshot propio (recien abierto),
 * `ejercicio_orden` 2. Es lo que devuelve GET /api/v1/episodes/{id}. */
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
  ejercicio_id: "ej-2",
  ejercicio_orden: 2,
}

/** La TP: sin `inicial_codigo` propio (es multi-ejercicio). */
const TAREA = {
  id: TAREA_ID,
  codigo: "TP2",
  titulo: "Agenda de turnos",
  enunciado: "Enunciado",
  fecha_inicio: null,
  fecha_fin: null,
  peso: "1.00",
  estado: "published",
  version: 1,
  inicial_codigo: null,
  language: "python",
}

/** El ejercicio 2 del banco, TAMBIEN sin `inicial_codigo`: es la unica
 * situacion en la que la siembra ED-4 entra (es el ultimo eslabon de la
 * cascada; el scaffold del docente manda siempre). */
const EJERCICIOS_TP = [
  {
    id: "tpe-2",
    tarea_practica_id: TAREA_ID,
    ejercicio_id: "ej-2",
    orden: 2,
    peso_en_tp: "1.00",
    ejercicio: {
      id: "ej-2",
      titulo: "E2",
      enunciado: "Usar la funcion del E1",
      language: "python",
      inicial_codigo: null,
      test_cases: [],
    },
  },
]

function montarEpisodio() {
  // El orden importa: `setupFetchMock` matchea por prefijo en orden de
  // insercion, y `/ejercicios` es sufijo de la ruta de la TP.
  setupFetchMock({
    "/resume": () => ({ ok: true }),
    [`/api/v1/tareas-practicas/${TAREA_ID}/ejercicios`]: () => EJERCICIOS_TP,
    [`/api/v1/tareas-practicas/${TAREA_ID}`]: () => TAREA,
    [`/api/v1/episodes/${EPISODIO_ID}`]: () => ESTADO_EPISODIO,
  })
  return render(<EpisodeView episodeId={EPISODIO_ID} onExit={() => {}} />)
}

/**
 * Todo rastro de un `edicion_codigo`, por los DOS caminos por los que
 * `EpisodeView` lo manda: el POST directo y la cola durable del `CTRClient`
 * (que persiste en `localStorage` antes de flushear). Mirar solo el fetch
 * dejaria pasar un evento que quedo encolado y todavia no salio.
 */
function rastrosDeEdicion(): string[] {
  const fetchMock = globalThis.fetch as unknown as ReturnType<typeof vi.fn>
  const porRed = fetchMock.mock.calls
    .map((c: unknown[]) => String(c[0]))
    .filter((u: string) => u.includes("edicion_codigo"))
  const encolados = window.localStorage.getItem(`ctr-queue:${EPISODIO_ID}`) ?? ""
  return encolados.includes("edicion_codigo") ? [...porRed, "en la cola del CTRClient"] : porRed
}

beforeEach(() => {
  resetMonacoMock()
  window.sessionStorage.clear()
  window.localStorage.clear()
})

afterEach(() => {
  vi.unstubAllGlobals()
})

/** Deja `sessionStorage` como lo dejaria el cierre del ejercicio 1. */
function sembrarAlmacen(code: string, language = "python") {
  window.sessionStorage.setItem(
    `web-student.codigo-previo.${TAREA_ID}`,
    JSON.stringify({ tareaId: TAREA_ID, ejercicioOrden: 1, language, code }),
  )
}

describe("ED-4 — siembra del codigo del ejercicio anterior", () => {
  it("el codigo heredado entra por editor.create, no por un setValue posterior", async () => {
    sembrarAlmacen(CODIGO_DEL_EJERCICIO_1)
    montarEpisodio()

    await waitFor(() => expect(editoresCreados.length).toBeGreaterThanOrEqual(1))
    // `__opciones.value` es lo que se le paso a `monaco.editor.create`. Si la
    // siembra llegara despues del mount (un `setValue`, un effect sobre
    // `initialCode`), este valor seria el andamio del lenguaje y el codigo
    // heredado aparecería recien en `getValue()`.
    await waitFor(() => expect(editoresCreados[0]?.__opciones.value).toBe(CODIGO_DEL_EJERCICIO_1))
  })

  it("la siembra NO emite un edicion_codigo fantasma", async () => {
    // Este es el equivalente, para el camino del arrastre, de
    // "el re-montaje NO emite un edicion_codigo fantasma".
    //
    // La espera es sobre el BUFFER (`getValue()`), no sobre `__opciones.value`:
    // asi el test sigue siendo valido —y sigue pudiendo fallar— para cualquier
    // implementacion que termine con el codigo heredado en el editor, entre por
    // donde entre. Lo que se afirma es que llegar ahi no dejo rastro en la
    // cadena CTR.
    sembrarAlmacen(CODIGO_DEL_EJERCICIO_1)
    montarEpisodio()

    await waitFor(() => expect(editoresCreados.length).toBeGreaterThanOrEqual(1))
    await waitFor(() => expect(editoresCreados[0]?.getValue()).toBe(CODIGO_DEL_EJERCICIO_1))

    // Pasado el debounce del editor (1s) con margen.
    await act(async () => {
      await new Promise((r) => setTimeout(r, 2500))
    })
    expect(rastrosDeEdicion(), "la siembra dejo un edicion_codigo en la cadena").toEqual([])
  })

  it("sin nada guardado el editor abre en el andamio del lenguaje, sin emitir nada", async () => {
    // Contraste de los dos anteriores: prueba que el `value` sembrado viene del
    // arrastre y no de que el editor arranque con ese texto igual.
    montarEpisodio()

    await waitFor(() => expect(editoresCreados.length).toBeGreaterThanOrEqual(1))
    await waitFor(() => expect(editoresCreados[0]?.__opciones.value).not.toBe(""))
    expect(editoresCreados[0]?.__opciones.value).not.toBe(CODIGO_DEL_EJERCICIO_1)
    expect(rastrosDeEdicion()).toEqual([])
  })

  it("el codigo guardado de OTRO lenguaje no siembra el editor", async () => {
    // El ejercicio 2 es Python; lo guardado es Java. Sembrarlo abriria el
    // archivo ya roto.
    window.sessionStorage.setItem(
      `web-student.codigo-previo.${TAREA_ID}`,
      JSON.stringify({
        tareaId: TAREA_ID,
        ejercicioOrden: 1,
        language: "java",
        code: "class Main {}",
      }),
    )

    montarEpisodio()

    await waitFor(() => expect(editoresCreados.length).toBeGreaterThanOrEqual(1))
    await waitFor(() => expect(editoresCreados[0]?.__opciones.value).not.toBe(""))
    expect(editoresCreados[0]?.__opciones.value).not.toBe("class Main {}")
  })
})
