/**
 * ED-2 — "Cerrar episodio" al tamano `md` del sistema.
 *
 * ⚠ QUE **NO** PRUEBA ESTE ARCHIVO
 * --------------------------------
 * Nada de lo que motivo el cambio. El reporte del alumno fue "no encuentro el
 * boton"; esto verifica strings de clases de Tailwind en el DOM de jsdom. NO
 * prueba que el boton se vea mas grande (jsdom no calcula layout ni aplica
 * CSS), NO prueba que se encuentre, y NO prueba la jerarquia visual contra
 * "Seguir despues" — que es la mitad del punto de ED-2 y solo se puede juzgar
 * mirando la pantalla.
 *
 * Entonces, ¿para que existe? Para una sola cosa: que el tamano no vuelva
 * silenciosamente a `text-xs px-3 py-1.5` en un refactor de clases. Es una
 * ancla contra la regresion de una decision deliberada, no una verificacion de
 * la decision. Vale poco; el borrado de este archivo cuesta poco tambien.
 */
import { render, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { EpisodeView } from "../src/pages/EpisodePage"
import { setupFetchMock } from "./_mocks"
import { resetMonacoMock } from "./_monacoMock"

const TAREA_ID = "tp-ed2"
const EPISODIO_ID = "ep-ed2"

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
  titulo: "Primera TP",
  enunciado: "Enunciado",
  fecha_inicio: null,
  fecha_fin: null,
  peso: "1.00",
  estado: "published",
  version: 1,
  inicial_codigo: null,
  language: "python",
}

beforeEach(() => {
  resetMonacoMock()
  window.sessionStorage.clear()
  window.localStorage.clear()
  setupFetchMock({
    "/resume": () => ({ ok: true }),
    [`/api/v1/tareas-practicas/${TAREA_ID}`]: () => TAREA,
    [`/api/v1/episodes/${EPISODIO_ID}`]: () => ESTADO_EPISODIO,
  })
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe("ED-2 — tamano del boton de cierre", () => {
  it('"Cerrar episodio" lleva el tamano md del sistema, no el de un chip', async () => {
    const { findByTestId } = render(<EpisodeView episodeId={EPISODIO_ID} onExit={() => {}} />)
    const boton = await findByTestId("close-episode-button")

    // El tamano nuevo...
    expect(boton).toHaveClass("text-sm", "px-4", "py-2")
    // ...y explicitamente NO el viejo, que lo dejaba del porte de los chips
    // informativos de la barra.
    expect(boton).not.toHaveClass("text-xs")
    expect(boton).not.toHaveClass("px-3")
    expect(boton).not.toHaveClass("py-1.5")
  })

  it("el icono acompana al texto (h-4 w-4, no h-3 w-3)", async () => {
    const { findByTestId } = render(<EpisodeView episodeId={EPISODIO_ID} onExit={() => {}} />)
    const boton = await findByTestId("close-episode-button")
    const icono = boton.querySelector("svg")

    expect(icono).not.toBeNull()
    expect(icono).toHaveClass("h-4", "w-4")
    expect(icono).not.toHaveClass("h-3")
  })

  it('"Seguir despues" se queda chica a proposito (la jerarquia distingue salir de pausar)', async () => {
    // Si alguien "empareja" los dos botones, se pierde la distincion entre la
    // salida definitiva y la pausa, que es lo que ED-2 fue a arreglar.
    const { findByTestId, queryByTestId } = render(
      <EpisodeView episodeId={EPISODIO_ID} onExit={() => {}} />,
    )
    await findByTestId("close-episode-button")
    const pausar = queryByTestId("pause-episode-button")
    // La TP puede no permitir pausa; si el boton no esta, no hay nada que
    // afirmar y el test no inventa una conclusion.
    if (pausar === null) return
    await waitFor(() => expect(pausar).toHaveClass("text-xs"))
  })
})
