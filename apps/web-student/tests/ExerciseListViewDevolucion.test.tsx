/**
 * La puerta de vuelta: reabrir un ejercicio, y trabajar sobre un TP devuelto.
 *
 * BUG-1 — LA ENTREGA FANTASMA (QA 2026-08-31, entrega f8abde1a-…)
 * ---------------------------------------------------------------
 * El alumno cierra los cinco ejercicios, los ve TODOS en "Completado" con tilde
 * verde, y al entregar recibe
 *
 *     "Falta el código de los ejercicios: [2,3,4,5]. Abrí cada ejercicio una
 *      vez antes de entregar."
 *
 * Y no puede abrirlos. La entrega queda en `draft`: él cree que entregó, el
 * docente ve un casillero vacío.
 *
 * La causa era una puerta de una sola dirección. `canStart` era
 *
 *     !locked && !completed && estado === "draft"
 *
 * y el botón vivía dentro de `{canStart && (...)}`: con el ejercicio completo
 * el botón NO SE RENDERIZA. No queda gris — desaparece. El sistema le exigía
 * lo único que él ya no podía hacer.
 *
 * Lo que más duele: el backend SIEMPRE supo des-marcar. `MarkEjercicioBody.
 * completado` acepta `False` desde el 2026-06-19, con el comentario "reapertura
 * docente: el docente reabrió el episodio para que el alumno lo retome". La
 * salida de emergencia estaba construida y no había ninguna puerta que llevara
 * a ella. Nadie —alumno, docente ni admin— la llamaba nunca.
 *
 * LA DEVOLUCIÓN QUE NO DEVOLVÍA NADA
 * ----------------------------------
 * El mismo `estado === "draft"` gateaba `canSubmit`. Con la entrega en
 * `returned`, al alumno le aparecía el cartel "Devuelta para revisar. Tu docente
 * devolvió la entrega con observaciones." y NINGÚN botón: ni de ejercicio ni de
 * entregar. El botón "Devolver al estudiante" le mostraba un cartel que lo
 * invitaba a revisar y le sacaba todas las herramientas para revisar.
 *
 * Una pieza, tres resultados: el alumno trabado se destraba, el botón "Devolver"
 * pasa a hacer lo que promete, y la feature de rehacer el TP queda hecha.
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { ExerciseListView } from "../src/components/ExerciseListView"
import type { AvailableTarea, Entrega, TpEjercicio } from "../src/lib/api"
import { setupFetchMock } from "./_mocks"

const COMISION_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
const TAREA_ID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
const ENTREGA_ID = "cccccccc-cccc-cccc-cccc-cccccccccccc"
const EJ1 = "ejejejej-0001-0001-0001-000000000001"
const EJ2 = "ejejejej-0002-0002-0002-000000000002"

function estados(completados: boolean[]) {
  return completados.map((c, i) => ({
    ejercicio_id: i === 0 ? EJ1 : EJ2,
    orden: i + 1,
    completado: c,
    episode_id: `epepepep-000${i + 1}-0001-0001-00000000000${i + 1}`,
    completado_at: null,
  }))
}

function makeEntrega(overrides: Partial<Entrega> = {}): Entrega {
  return {
    id: ENTREGA_ID,
    tenant_id: "t1",
    tarea_practica_id: TAREA_ID,
    comision_id: COMISION_ID,
    student_pseudonym: "b1b1b1b1-0001-0001-0001-000000000001",
    estado: "draft",
    ejercicio_estados: estados([false, false]),
    submitted_at: null,
    created_at: "2026-05-06T10:00:00Z",
    updated_at: "2026-05-06T10:00:00Z",
    ...overrides,
  }
}

function makePairs(): TpEjercicio[] {
  const base = { tarea_practica_id: TAREA_ID, peso_en_tp: "0.50" }
  const ejercicio = (id: string, titulo: string) => ({
    id,
    titulo,
    enunciado_md: titulo,
    inicial_codigo: null,
    unidad_tematica: "funciones",
    dificultad: "basica",
    test_cases: [],
  })
  return [
    { ...base, id: "pair-1", ejercicio_id: EJ1, orden: 1, ejercicio: ejercicio(EJ1, "Suma") },
    { ...base, id: "pair-2", ejercicio_id: EJ2, orden: 2, ejercicio: ejercicio(EJ2, "Resta") },
  ]
}

function makeTarea(): AvailableTarea {
  return {
    id: TAREA_ID,
    codigo: "TP01",
    titulo: "Funciones basicas",
    enunciado: "Implementar funciones basicas en Python.",
    fecha_inicio: null,
    fecha_fin: null,
    peso: "1.0",
    estado: "published",
    version: 1,
    inicial_codigo: null,
  }
}

function montar(props: Partial<Parameters<typeof ExerciseListView>[0]> = {}) {
  return render(
    <ExerciseListView
      tarea={makeTarea()}
      comisionId={COMISION_ID}
      onSelectEjercicio={vi.fn()}
      onViewGrade={vi.fn()}
      onBack={vi.fn()}
      {...props}
    />,
  )
}

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

describe("BUG-1: la puerta de vuelta", () => {
  it("un ejercicio completado ofrece 'Volver a abrir'", async () => {
    // El corazón del fix. Verificado por reversión: sin el botón, un alumno con
    // los dos en "Completado" y sin código guardado no tiene NINGUNA acción
    // disponible sobre ese ejercicio y la entrega no sale nunca.
    setupFetchMock({
      "/ejercicios": () => makePairs(),
      "/api/v1/entregas": () => makeEntrega({ ejercicio_estados: estados([true, true]) }),
    })
    montar()

    await waitFor(() => expect(screen.getByTestId("ejercicios-list")).toBeDefined())
    expect(screen.getByTestId("ejercicio-reabrir-1")).toBeDefined()
    expect(screen.getByTestId("ejercicio-reabrir-2")).toBeDefined()
  })

  it("no ofrece reabrir lo que todavia no se completo", async () => {
    // No es un botón decorativo en todas las filas: sólo donde hay algo que
    // reabrir. Si no, el alumno lo lee como una acción disponible siempre y
    // deja de significar nada.
    setupFetchMock({
      "/ejercicios": () => makePairs(),
      "/api/v1/entregas": () => makeEntrega(),
    })
    montar()

    await waitFor(() => expect(screen.getByTestId("ejercicios-list")).toBeDefined())
    expect(screen.queryByTestId("ejercicio-reabrir-1")).toBeNull()
  })

  it("reabrir manda completado:false con el ejercicio_id, y NO pisa el episode_id", async () => {
    // El `episode_id` guardado apunta al episodio del intento anterior, que
    // sigue cerrado y firmado. Es lo ÚNICO con lo que `recuperarArtefactos`
    // puede rescatar el código viejo cuando no hay borrador local: pisarlo acá
    // lo perdería para siempre.
    const cuerpos: string[] = []
    setupFetchMock({
      "/ejercicios": () => makePairs(),
      "/api/v1/entregas": () => makeEntrega({ ejercicio_estados: estados([true, true]) }),
    })
    const original = globalThis.fetch as unknown as (u: string, i?: RequestInit) => Promise<Response>
    vi.stubGlobal(
      "fetch",
      vi.fn((u: string, init?: RequestInit) => {
        if (init?.method === "PATCH" && typeof init.body === "string") cuerpos.push(init.body)
        return original(u, init)
      }),
    )
    montar()

    await waitFor(() => expect(screen.getByTestId("ejercicio-reabrir-1")).toBeDefined())
    fireEvent.click(screen.getByTestId("ejercicio-reabrir-1"))

    await waitFor(() => expect(cuerpos.length).toBe(1))
    const body = JSON.parse(cuerpos[0])
    expect(body.completado).toBe(false)
    expect(body.ejercicio_id).toBe(EJ1)
    expect(body.episode_id).toBeUndefined()
  })
})

describe("una entrega devuelta se puede trabajar", () => {
  it("con returned, el ejercicio pendiente muestra su boton", async () => {
    // Verificado por reversión: con `estado === "draft"` esto es null y el
    // alumno recibe la devolución sin poder abrir un solo ejercicio.
    setupFetchMock({
      "/ejercicios": () => makePairs(),
      "/api/v1/entregas": () =>
        makeEntrega({ estado: "returned", ejercicio_estados: estados([false, false]) }),
    })
    montar()

    await waitFor(() => expect(screen.getByTestId("ejercicios-list")).toBeDefined())
    expect(screen.getByTestId("ejercicio-start-1")).toBeDefined()
  })

  it("con returned y todo completo, el boton de entregar vuelve", async () => {
    // Sin esto el ciclo docente → alumno → docente se corta en el último
    // tramo: el alumno corrige y no tiene con qué devolverlo.
    setupFetchMock({
      "/ejercicios": () => makePairs(),
      "/api/v1/entregas": () =>
        makeEntrega({ estado: "returned", ejercicio_estados: estados([true, true]) }),
    })
    montar()

    await waitFor(() => expect(screen.getByTestId("ejercicios-list")).toBeDefined())
    expect(screen.getByTestId("submit-entrega-btn")).toBeDefined()
  })

  it("con submitted NO se puede tocar nada", async () => {
    // Ya está en manos del docente. Ni reabrir ni re-entregar: cambiar lo
    // entregado después de entregado rompe lo que el hash del artefacto
    // certifica.
    setupFetchMock({
      "/ejercicios": () => makePairs(),
      "/api/v1/entregas": () =>
        makeEntrega({ estado: "submitted", ejercicio_estados: estados([true, true]) }),
    })
    montar()

    await waitFor(() => expect(screen.getByTestId("ejercicios-list")).toBeDefined())
    expect(screen.queryByTestId("ejercicio-reabrir-1")).toBeNull()
    expect(screen.queryByTestId("submit-entrega-btn")).toBeNull()
  })

  it("con graded tampoco", async () => {
    setupFetchMock({
      "/ejercicios": () => makePairs(),
      "/api/v1/entregas": () =>
        makeEntrega({ estado: "graded", ejercicio_estados: estados([true, true]) }),
    })
    montar()

    await waitFor(() => expect(screen.getByTestId("ejercicios-list")).toBeDefined())
    expect(screen.queryByTestId("ejercicio-reabrir-1")).toBeNull()
    expect(screen.queryByTestId("submit-entrega-btn")).toBeNull()
  })
})
