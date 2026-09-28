/**
 * ED-4 afuera — codigo heredado de un ejercicio anterior de la MISMA TP, que
 * pudo quedar en `sessionStorage` por una version anterior del frontend, ya
 * NO siembra el editor.
 *
 * Antes de esta change, este archivo probaba lo contrario: que la siembra
 * SI funcionaba y que lo hacia sin emitir un `edicion_codigo` fantasma. El
 * dueno del producto decidio (2026-09-28) que un `inicial_codigo` vacio es
 * una decision del docente ("que arranque vacio"), no un silencio a
 * interpretar heredando codigo de otro ejercicio — ver
 * `openspec/changes/eliminar-ed4-siembra-codigo-previo/proposal.md`.
 *
 * Lo que queda por proteger no es que la siembra funcione, sino lo contrario:
 * que un residuo de `sessionStorage` bajo la clave vieja
 * `web-student.codigo-previo.{tareaId}` — dejado por una pestana que no
 * recargo desde el deploy de esta change — no vuelva a colarse en el editor
 * ni deje un evento en la cadena CTR. `codigoPrevio.ts`, que era quien leia
 * esa clave, ya no existe; este test asume solamente el contrato observable
 * (que hay en el storage no importa).
 *
 * Por que se assertea tambien la ausencia de `edicion_codigo`
 * -------------------------------------------------------
 * Un evento de edicion que el alumno no hizo es evidencia falsa en la cadena
 * CTR — el motivo original por el que este archivo existia. Sigue siendo
 * relevante: si algun dia alguien reintrodujera una lectura de esta clave,
 * este test cae en las dos puntas (el editor se siembra Y aparece el evento
 * fantasma), no solo en una.
 */
import { act, render, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { LANGUAGE_PLACEHOLDER } from "../src/lib/api"
import { EpisodeView } from "../src/pages/EpisodePage"
import { setupFetchMock } from "./_mocks"
import { editoresCreados, resetMonacoMock } from "./_monacoMock"

const TAREA_ID = "tp-e2-agenda"
const EPISODIO_ID = "ep-ejercicio-2"

/** Lo que un alumno pudo haber dejado escrito en el ejercicio 1 de esta misma
 * TP, con una version anterior del frontend (pre-ED-4-afuera). */
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

/** El ejercicio 2 del banco, TAMBIEN sin `inicial_codigo`: es el caso en el
 * que, con ED-4, la siembra hubiera entrado (el scaffold del docente manda
 * siempre). Sin ED-4 este caso cae al placeholder. */
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

/** Deja en `sessionStorage` la clave vieja de ED-4, como la hubiera dejado el
 * cierre del ejercicio 1 con una version anterior del frontend. */
function sembrarAlmacenResidual(code: string, language = "python") {
  window.sessionStorage.setItem(
    `web-student.codigo-previo.${TAREA_ID}`,
    JSON.stringify({ tareaId: TAREA_ID, ejercicioOrden: 1, language, code }),
  )
}

describe("ED-4 afuera — el codigo heredado ya NO siembra el editor", () => {
  it("un ejercicio sin inicial_codigo, con codigo guardado de un ejercicio anterior de la misma TP, abre con el placeholder del lenguaje y no con lo heredado", async () => {
    sembrarAlmacenResidual(CODIGO_DEL_EJERCICIO_1)
    montarEpisodio()

    await waitFor(() => expect(editoresCreados.length).toBeGreaterThanOrEqual(1))
    // Afirmacion POSITIVA, no dos negativas: el titulo promete el placeholder,
    // asi que el test compara CONTRA el placeholder. Es la linea 1 que se ve en
    // el video del 2026-09-28 — atado al sintoma reportado y no a su negacion.
    await waitFor(() => expect(editoresCreados[0]?.__opciones.value).not.toBe(""))
    expect(editoresCreados[0]?.__opciones.value).toBe(LANGUAGE_PLACEHOLDER.python)
    expect(editoresCreados[0]?.__opciones.value).not.toBe(CODIGO_DEL_EJERCICIO_1)
  })

  it("el residuo en sessionStorage no deja rastro en la cadena CTR", async () => {
    sembrarAlmacenResidual(CODIGO_DEL_EJERCICIO_1)
    montarEpisodio()

    await waitFor(() => expect(editoresCreados.length).toBeGreaterThanOrEqual(1))
    await waitFor(() => expect(editoresCreados[0]?.getValue()).not.toBe(""))

    // Pasado el debounce del editor (1s) con margen.
    await act(async () => {
      await new Promise((r) => setTimeout(r, 2500))
    })
    expect(rastrosDeEdicion(), "el residuo dejo un edicion_codigo en la cadena").toEqual([])
  })

  it("sin nada guardado el resultado es identico: el placeholder gana y no hay rastro", async () => {
    // Contraste del par anterior: prueba que el comportamiento no depende de
    // que exista o no la clave vieja — ya no hay ninguna rama que la lea.
    montarEpisodio()

    await waitFor(() => expect(editoresCreados.length).toBeGreaterThanOrEqual(1))
    await waitFor(() => expect(editoresCreados[0]?.__opciones.value).not.toBe(""))
    expect(editoresCreados[0]?.__opciones.value).not.toBe(CODIGO_DEL_EJERCICIO_1)
    expect(rastrosDeEdicion()).toEqual([])
  })
})
