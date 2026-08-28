/**
 * ED-4 — la mitad de ESCRITURA del arrastre, cableada de verdad.
 *
 * `codigoPrevio.test.ts` fija el criterio de `resolverCodigoAPersistir` y
 * `CodigoPrevioSiembra.test.tsx` fija el de la lectura. Entre las dos quedaba
 * el hueco donde vivia el mutante que sobrevivia: sacar
 * `persistirCodigoParaElProximoEjercicio()` de `handleClose` y de
 * `handlePauseExit`.
 *
 * Por que ese hueco es el peor de los cinco
 * -----------------------------------------
 * Una escritura que no ocurre es INVISIBLE. No hay pantalla que se vea mal, no
 * hay request que falle, no hay excepcion. El sintoma aparece un ejercicio
 * despues —el editor abre en blanco— y para entonces no hay forma de saber si
 * fallo la escritura del ejercicio anterior o la lectura de este. Las dos
 * mitades puras podian estar perfectas y el feature muerto igual.
 *
 * Se ejercita el camino completo: montar `EpisodeView`, escribir en el editor
 * (por el doble de Monaco, que dispara `onDidChangeModelContent` como el real,
 * asi que `code` del componente se actualiza por donde se actualiza en
 * produccion), tocar el boton, y mirar `sessionStorage`.
 */

import { act, fireEvent, render, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { claveCodigoPrevio, parseCodigoPrevio } from "../src/lib/codigoPrevio"
import { EpisodeView } from "../src/pages/EpisodePage"
import { setupFetchMock } from "./_mocks"
import { editoresCreados, resetMonacoMock } from "./_monacoMock"

const TAREA_ID = "tp-e2-agenda"
const EPISODIO_ID = "ep-ejercicio-1"

/** Lo que el alumno escribe en el ejercicio 1 y tiene que heredar el 2. */
const CODIGO_DEL_ALUMNO = "def saludar(nombre):\n    print('Hola', nombre)\n"

/** Ejercicio 1 de una TP multi-ejercicio. Es la unica forma en que el arrastre
 * aplica: en una TP monolitica no hay "proximo ejercicio". */
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

function montar() {
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

/** Escribe en el editor por el mismo evento que dispara Monaco real. */
async function escribir(texto: string) {
  await waitFor(() => expect(editoresCreados.length).toBeGreaterThanOrEqual(1))
  const ed = editoresCreados[0]
  if (!ed) throw new Error("no se creo el editor")
  await act(async () => {
    ed.__tipear(texto)
    // El espejo `code` de `EpisodePage` se actualiza por `onCodeChange`, que
    // el editor llama en el mismo tick; el `await` deja correr el re-render.
  })
}

/** Lo que quedo guardado para el proximo ejercicio de esta TP. */
function guardado() {
  return parseCodigoPrevio(window.sessionStorage.getItem(claveCodigoPrevio(TAREA_ID)))
}

beforeEach(() => {
  resetMonacoMock()
  window.sessionStorage.clear()
  window.localStorage.clear()
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe("ED-4 — al salir del ejercicio se guarda el buffer para el siguiente", () => {
  it('"Cerrar episodio" deja el codigo del alumno guardado', async () => {
    const { findByTestId } = montar()
    await escribir(CODIGO_DEL_ALUMNO)

    // Precondicion explicita: antes del click no hay nada. Sin esto el test
    // pasaria si algo mas hubiera escrito la clave durante la hidratacion.
    expect(guardado()).toBeNull()

    const cerrar = await findByTestId("close-episode-button")
    await act(async () => {
      fireEvent.click(cerrar)
    })

    await waitFor(() => expect(guardado()).not.toBeNull())
    expect(guardado()).toEqual({
      tareaId: TAREA_ID,
      ejercicioOrden: 1,
      language: "python",
      code: CODIGO_DEL_ALUMNO,
    })
  })

  it('"Seguir despues" (pausa) tambien guarda', async () => {
    // Pausar tambien es salir del ejercicio. Es la salida MAS probable en una
    // TP encadenada: el alumno termina E1, pausa, y abre E2. Cubrir solo
    // `handleClose` dejaria el camino real sin anclar.
    const { findByTestId } = montar()
    await escribir(CODIGO_DEL_ALUMNO)
    expect(guardado()).toBeNull()

    const pausar = await findByTestId("pause-episode-button")
    await act(async () => {
      fireEvent.click(pausar)
    })

    await waitFor(() => expect(guardado()?.code).toBe(CODIGO_DEL_ALUMNO))
  })

  it("guarda lo ULTIMO que el alumno tenia, no lo primero", async () => {
    // `code` es el espejo vivo del buffer. Si la persistencia leyera un valor
    // capturado en el mount (o de un ref viejo), el arrastre traeria una
    // version anterior del trabajo — peor que no traer nada, porque el alumno
    // no se entera de que perdio los ultimos cambios.
    const { findByTestId } = montar()
    await escribir("print('primera version')\n")
    await escribir(CODIGO_DEL_ALUMNO)

    const cerrar = await findByTestId("close-episode-button")
    await act(async () => {
      fireEvent.click(cerrar)
    })

    await waitFor(() => expect(guardado()?.code).toBe(CODIGO_DEL_ALUMNO))
  })

  it("guarda con el orden y el lenguaje de ESTE ejercicio", async () => {
    // Los dos campos que `resolverSiembra` usa para decidir. Un orden o un
    // lenguaje equivocado deja la entrada en el almacen y el arrastre igual no
    // llega: falla silenciosa con dato escrito, que es la peor de las dos.
    const { findByTestId } = montar()
    await escribir(CODIGO_DEL_ALUMNO)

    const cerrar = await findByTestId("close-episode-button")
    await act(async () => {
      fireEvent.click(cerrar)
    })

    await waitFor(() => expect(guardado()).not.toBeNull())
    expect(guardado()).toMatchObject({ ejercicioOrden: 1, language: "python" })
  })

  it("no guarda si el alumno no escribio nada (el andamio no es trabajo)", async () => {
    // Contraste que hace no-vacuos a los anteriores: si la persistencia
    // guardara siempre, todos pasarian igual. Y guardar el andamio haria que
    // el arrastre "funcione" trayendo exactamente lo que ya iba a estar ahi.
    const { findByTestId } = montar()
    await waitFor(() => expect(editoresCreados.length).toBeGreaterThanOrEqual(1))

    const cerrar = await findByTestId("close-episode-button")
    await act(async () => {
      fireEvent.click(cerrar)
    })

    // Se espera a que el cierre haya ocurrido antes de afirmar la ausencia:
    // sin eso el `toBeNull` pasaria solo porque el handler no termino.
    const fetchMock = globalThis.fetch as unknown as ReturnType<typeof vi.fn>
    await waitFor(() =>
      expect(fetchMock.mock.calls.some((c: unknown[]) => String(c[0]).includes("/close"))).toBe(
        true,
      ),
    )
    expect(guardado()).toBeNull()
  })
})
