/**
 * La red que faltaba: que salir de un episodio NO re-envie una entrega devuelta.
 *
 * QUE PROBLEMA RESUELVE ESTE ARCHIVO
 * ----------------------------------
 * Una entrega en `returned` es una que el docente devolvio con observaciones.
 * Re-enviarla la pasa a `submitted` y **borra la devolucion**. Y no hace falta
 * que el alumno apriete nada: basta con que vuelva a entrar al episodio cerrado
 * para leer lo que le escribieron —la hidratacion llama `onExit()` sola al ver
 * `estado === "closed"`— para que el ciclo se dispare.
 *
 * O sea: el alumno abre el episodio para LEER la correccion, y el solo hecho de
 * abrirlo se la borra.
 *
 * POR QUE NO ALCANZABA CON EL UNIT TEST DE `debeEnviarLaEntrega`
 * -------------------------------------------------------------
 * La auditoria adversarial del PR #86 lo midio: reintroduciendo a mano el bug
 * —que `debeEnviarLaEntrega` acepte `returned`— sobre las 529 pruebas de
 * `web-student` se ponian rojos exactamente 3 asserts, los tres del unit test
 * de la propia funcion. Ninguna otra prueba en todo el repo se enteraba.
 *
 * Eso deja el defecto mas caro del dominio con una sola red, y una que se rompe
 * sola: un refactor que decida que `puedeEditarLaEntrega` y `debeEnviarLaEntrega`
 * "hacen casi lo mismo" y las unifique va a tocar ese test de paso. Cuando lo
 * toque, nada le va a avisar.
 *
 * Estos tests preguntan por el COMPORTAMIENTO —"¿se llamo a submit?"— y no por
 * el nombre de una funcion. Sobreviven al renombre y al refactor.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { enviarEntregaAlSalir } from "../src/lib/entregaAlSalir"
import { setupFetchMock } from "./_mocks"

const EPISODIO = "ep-devuelta"
const TAREA = "tp-1"
const COMISION = "com-1"
const ENTREGA = "entrega-1"

function estadoDelEpisodio(estado: string) {
  return {
    episode_id: EPISODIO,
    tarea_practica_id: TAREA,
    comision_id: COMISION,
    estado,
    opened_at: "2026-08-31T10:00:00Z",
    closed_at: estado === "closed" ? "2026-08-31T11:00:00Z" : null,
    last_code_snapshot: "print('hola')",
    messages: [],
    notes: [],
    ejercicio_id: null,
    ejercicio_orden: null,
  }
}

/** Monta el mundo con el episodio cerrado y la entrega en el estado pedido. */
function mundoCon(estadoEntrega: string) {
  setupFetchMock({
    "/api/v1/episodes/": () => estadoDelEpisodio("closed"),
    "/api/v1/entregas": () => ({
      id: ENTREGA,
      tarea_practica_id: TAREA,
      comision_id: COMISION,
      estado: estadoEntrega,
      ejercicio_estados: [],
    }),
    "/api/v1/tareas-practicas/": () => ({ id: TAREA, language: "python" }),
  })
}

/** Las llamadas a `POST .../submit` que se hicieron. */
function submitsHechos(): string[] {
  const fetchMock = globalThis.fetch as unknown as { mock: { calls: unknown[][] } }
  return fetchMock.mock.calls.map((c) => String(c[0])).filter((u) => u.includes("/submit"))
}

describe("enviarEntregaAlSalir", () => {
  beforeEach(() => {
    window.localStorage.clear()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it("NO re-envia una entrega devuelta — borrarle la devolucion al docente", async () => {
    mundoCon("returned")

    const resultado = await enviarEntregaAlSalir(EPISODIO)

    expect(resultado).toBe("entrega-no-enviable")
    expect(submitsHechos()).toEqual([])
  })

  it("NO re-envia una ya enviada", async () => {
    mundoCon("submitted")

    await enviarEntregaAlSalir(EPISODIO)

    expect(submitsHechos()).toEqual([])
  })

  it("NO re-envia una ya calificada", async () => {
    mundoCon("graded")

    await enviarEntregaAlSalir(EPISODIO)

    expect(submitsHechos()).toEqual([])
  })

  it("SI envia un borrador: sin esto la card se queda en 'Empezar'", async () => {
    mundoCon("draft")

    const resultado = await enviarEntregaAlSalir(EPISODIO)

    expect(resultado).toBe("enviada")
    expect(submitsHechos()).toHaveLength(1)
  })

  it("no toca nada si el episodio no quedo cerrado", async () => {
    setupFetchMock({
      "/api/v1/episodes/": () => estadoDelEpisodio("paused"),
      "/api/v1/entregas": () => ({ id: ENTREGA, estado: "draft" }),
    })

    const resultado = await enviarEntregaAlSalir(EPISODIO)

    expect(resultado).toBe("episodio-no-cerrado")
    expect(submitsHechos()).toEqual([])
  })

  it("un fallo de red no propaga: el alumno no queda atrapado en el episodio", async () => {
    setupFetchMock({
      "/api/v1/episodes/": { ok: false, status: 500, body: () => ({}) },
    })

    await expect(enviarEntregaAlSalir(EPISODIO)).resolves.toBe("error")
  })
})
