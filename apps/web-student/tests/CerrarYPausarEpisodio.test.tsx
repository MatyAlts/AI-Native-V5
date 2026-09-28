/**
 * Los dos botones de salida del episodio: "Cerrar episodio" y "Seguir despues".
 *
 * POR QUE EXISTE ESTE ARCHIVO
 * ---------------------------
 * Hasta el 2026-09-28 los unicos tests que apretaban estos dos botones vivian
 * en `CodigoPrevioPersistencia.test.tsx`, y estaban ahi de rebote: lo que
 * afirmaban era sobre ED-4 (el arrastre del codigo al ejercicio siguiente), y
 * el click era el vehiculo para llegar a la persistencia.
 *
 * Al eliminar ED-4 ese archivo se borro entero — correctamente, porque el
 * modulo que probaba dejo de existir. Pero con el se fue la unica cobertura de
 * los dos handlers, y QA lo demostro por mutacion el mismo dia: vaciando
 * `handleClose()` por completo la suite quedaba en 528/528 verde. El alumno
 * apretaba "Cerrar episodio" y no pasaba nada — ni el POST de cierre, ni la
 * clasificacion, ni la reflexion — y nadie se enteraba.
 *
 * Este archivo cubre esos dos caminos por si mismos, sin hablar de ED-4.
 * La leccion, que vale mas que el archivo: un test borrado con buen argumento
 * puede llevarse cobertura que nadie le habia atribuido. Lo que justifica
 * borrarlo es que el modulo murio, no que nada mas dependiera de el.
 *
 * Contratos verificados contra `EpisodePage.tsx:654-739`:
 *   handleClose()     -> POST /close, luego POST /classify_episode,
 *                        y borra ACTIVE_EPISODE_KEY de sessionStorage.
 *   handlePauseExit() -> POST /abandoned con reason "explicit",
 *                        borra ACTIVE_EPISODE_KEY, y llama a onExit.
 *   Los dos frenan el doble click con un ref SINCRONICO (NB-11).
 */
import { act, fireEvent, render, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { EpisodeView } from "../src/pages/EpisodePage"
import { setupFetchMock } from "./_mocks"
import { editoresCreados, resetMonacoMock } from "./_monacoMock"

const TAREA_ID = "tp-e2-agenda"
const EPISODIO_ID = "ep-ejercicio-1"
const ACTIVE_EPISODE_KEY = "active-episode-id"

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
  ejercicio_id: "ej-1",
  ejercicio_orden: 1,
}

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
  permite_pausa: true,
}

const EJERCICIOS_TP = [
  {
    id: "tpe-1",
    tarea_practica_id: TAREA_ID,
    ejercicio_id: "ej-1",
    orden: 1,
    peso_en_tp: "1.00",
    ejercicio: {
      id: "ej-1",
      titulo: "E1",
      enunciado: "Escribi la funcion saludar",
      language: "python",
      inicial_codigo: null,
      test_cases: [],
    },
  },
]

/**
 * Las llamadas que los dos handlers hacen, registradas por ruta y con su body.
 *
 * `setupFetchMock` recibe handlers SIN argumentos (`type Handler = () => unknown`),
 * asi que no hay forma de leer el body desde ahi. Envolvemos el stub que deja
 * instalado y delegamos: asi registramos url + body sin duplicar su logica de
 * matcheo por prefijo.
 */
type Llamada = { url: string; body: string }

function montar(): {
  llamadas: Llamada[]
  salidas: number[]
  vista: ReturnType<typeof render>
} {
  const llamadas: Llamada[] = []
  const salidas: number[] = []

  // El orden importa: `setupFetchMock` matchea por prefijo en orden de
  // insercion, y `/ejercicios` es sufijo de la ruta de la TP.
  setupFetchMock({
    [`/api/v1/episodes/${EPISODIO_ID}/close`]: () => ({ ok: true }),
    [`/api/v1/episodes/${EPISODIO_ID}/abandoned`]: () => ({ ok: true }),
    [`/api/v1/classify_episode/${EPISODIO_ID}`]: () => ({
      appropriation: "apropiacion_reflexiva",
      features: {},
    }),
    "/resume": () => ({ ok: true }),
    [`/api/v1/tareas-practicas/${TAREA_ID}/ejercicios`]: () => EJERCICIOS_TP,
    [`/api/v1/tareas-practicas/${TAREA_ID}`]: () => TAREA,
    [`/api/v1/episodes/${EPISODIO_ID}`]: () => ESTADO_EPISODIO,
  })

  const stub = globalThis.fetch
  vi.stubGlobal("fetch", (url: string | URL | Request, init?: RequestInit) => {
    llamadas.push({
      url: typeof url === "string" ? url : url.toString(),
      body: String(init?.body ?? ""),
    })
    return (stub as typeof fetch)(url as never, init)
  })

  // `emitEpisodioAbandonado` usa fetch con `keepalive` SI hay token, y cae a
  // `navigator.sendBeacon` si no (api.ts:176-182). En test no hay token, asi
  // que el camino real es el beacon: capturamos los dos o el test mide el
  // camino que no se ejecuta.
  vi.stubGlobal("navigator", {
    ...navigator,
    sendBeacon: (url: string, data?: BodyInit) => {
      // El body viaja como Blob y `Blob.text()` no existe en este entorno de
      // test. No importa: el contenido lo cubre emitEpisodioAbandonado.test.ts;
      // aca alcanza con registrar QUE se llamo y a que ruta.
      llamadas.push({ url, body: data instanceof Blob ? "[blob]" : String(data ?? "") })
      return true
    },
  })

  const vista = render(
    <EpisodeView episodeId={EPISODIO_ID} onExit={() => salidas.push(Date.now())} />,
  )
  return { llamadas, salidas, vista }
}

/** Cuantas veces se pego a una ruta. */
function veces(llamadas: Llamada[], fragmento: string): number {
  return llamadas.filter((l) => l.url.includes(fragmento)).length
}

/** Escribe en el editor por el mismo evento que dispara Monaco real. */
async function escribir(texto: string) {
  await waitFor(() => expect(editoresCreados.length).toBeGreaterThanOrEqual(1))
  const ed = editoresCreados[0]
  if (!ed) throw new Error("no se creo el editor")
  await act(async () => {
    ed.__tipear(texto)
  })
}

beforeEach(() => {
  resetMonacoMock()
  window.sessionStorage.clear()
  window.localStorage.clear()
  window.sessionStorage.setItem(ACTIVE_EPISODE_KEY, EPISODIO_ID)
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('"Cerrar episodio" hace las tres cosas que tiene que hacer', () => {
  it("manda el cierre al backend", async () => {
    const { llamadas, vista } = montar()
    await escribir("print('hola')")
    const cerrar = await vista.findByTestId("close-episode-button")
    await act(async () => {
      fireEvent.click(cerrar)
    })
    await waitFor(() =>
      expect(veces(llamadas, "/close")).toBe(1),
    )
  })

  it("dispara la clasificacion despues del cierre", async () => {
    const { llamadas, vista } = montar()
    await escribir("print('hola')")
    const cerrar = await vista.findByTestId("close-episode-button")
    await act(async () => {
      fireEvent.click(cerrar)
    })
    // Es best-effort en el handler (un classifier caido no bloquea el cierre),
    // pero tiene que INTENTARSE: sin esta llamada el episodio queda cerrado y
    // sin etiqueta, que es la entrada del dato a la tesis.
    await waitFor(() => expect(veces(llamadas, "/classify_episode/")).toBe(1))
  })

  it("suelta la llave del episodio activo", async () => {
    const { vista } = montar()
    await escribir("print('hola')")
    const cerrar = await vista.findByTestId("close-episode-button")
    await act(async () => {
      fireEvent.click(cerrar)
    })
    // Si no se borra, el recovery de `routes/index.tsx` vuelve a meter al
    // alumno en un episodio que ya cerro.
    await waitFor(() =>
      expect(window.sessionStorage.getItem(ACTIVE_EPISODE_KEY)).toBeNull(),
    )
  })

  it("el doble click no cierra dos veces (guard sincronico NB-11)", async () => {
    const { llamadas, vista } = montar()
    await escribir("print('hola')")
    const cerrar = await vista.findByTestId("close-episode-button")
    await act(async () => {
      fireEvent.click(cerrar)
      fireEvent.click(cerrar)
    })
    await waitFor(() => expect(veces(llamadas, "/close")).toBe(1))
  })
})

describe('"Seguir despues" pausa sin cerrar', () => {
  it("emite el abandono explicito, NO el cierre", async () => {
    const { llamadas, vista } = montar()
    await escribir("print('hola')")
    const pausar = await vista.findByTestId("pause-episode-button")
    await act(async () => {
      fireEvent.click(pausar)
    })
    await waitFor(() => expect(veces(llamadas, "/abandoned")).toBe(1))
    // El CONTENIDO del payload (reason "explicit", el keepalive, el Bearer) ya
    // lo cubre `emitEpisodioAbandonado.test.ts` a nivel de la funcion de api.
    // Lo que se perdio al borrar CodigoPrevioPersistencia.test.tsx, y lo que
    // este archivo recupera, es que EL BOTON llegue hasta ahi.
    // La diferencia con cerrar: pausar NO clasifica ni cierra. Si algun dia
    // clasifica, el episodio pausado entra al dato como si hubiera terminado.
    expect(veces(llamadas, "/close")).toBe(0)
    expect(veces(llamadas, "/classify_episode/")).toBe(0)
  })

  it("suelta la llave y sale de la pantalla", async () => {
    const { salidas, vista } = montar()
    await escribir("print('hola')")
    const pausar = await vista.findByTestId("pause-episode-button")
    await act(async () => {
      fireEvent.click(pausar)
    })
    await waitFor(() =>
      expect(window.sessionStorage.getItem(ACTIVE_EPISODE_KEY)).toBeNull(),
    )
    expect(salidas.length).toBe(1)
  })
})
