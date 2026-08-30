/**
 * AUDITORÍA DEL ALUMNO — la pantalla desde la que entrega la TP.
 *
 * Es la última pantalla del recorrido y la que más caro sale que falle: acá el
 * alumno convierte semanas de trabajo en una entrega. Estos tests montan
 * `ExerciseListView` de verdad y reproducen tres momentos en los que la
 * pantalla lo deja peor de lo que lo encontró.
 *
 * Son tests de CARACTERIZACIÓN del estado actual, no de comportamiento
 * deseado: afirman que en pantalla aparece algo malo (o que no aparece nada).
 * Si alguien arregla el hallazgo, el test se pone rojo — que es justamente el
 * punto: que el arreglo sea visible.
 */

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { ExerciseListView } from "../src/components/ExerciseListView"
import type { AvailableTarea, Entrega, TpEjercicio } from "../src/lib/api"

const COMISION_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
const TAREA_ID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
const ENTREGA_ID = "cccccccc-cccc-cccc-cccc-cccccccccccc"

/** Entrega con los DOS ejercicios ya completados: el estado en el que el
 * alumno tiene el botón "Entregar TP" habilitado. */
function entregaLista(estado: Entrega["estado"] = "draft"): Entrega {
  return {
    id: ENTREGA_ID,
    tenant_id: "t1",
    tarea_practica_id: TAREA_ID,
    comision_id: COMISION_ID,
    student_pseudonym: "b1b1b1b1-0001-0001-0001-000000000001",
    estado,
    ejercicio_estados: [
      {
        ejercicio_id: "ej-1",
        orden: 1,
        completado: true,
        episode_id: "ep-1",
        completado_at: "2026-08-27T10:00:00Z",
      },
      {
        ejercicio_id: "ej-2",
        orden: 2,
        completado: true,
        episode_id: "ep-2",
        completado_at: "2026-08-27T11:00:00Z",
      },
    ],
    submitted_at: null,
    created_at: "2026-08-27T09:00:00Z",
    updated_at: "2026-08-27T11:00:00Z",
  }
}

function pares(): TpEjercicio[] {
  const base = { tarea_practica_id: TAREA_ID, peso_en_tp: "0.50" }
  return [
    {
      ...base,
      id: "pair-1",
      ejercicio_id: "ej-1",
      orden: 1,
      ejercicio: {
        id: "ej-1",
        titulo: "Suma",
        enunciado_md: "Implementar suma",
        inicial_codigo: null,
        unidad_tematica: "funciones",
        dificultad: "basica",
        test_cases: [],
      },
    },
    {
      ...base,
      id: "pair-2",
      ejercicio_id: "ej-2",
      orden: 2,
      ejercicio: {
        id: "ej-2",
        titulo: "Resta",
        enunciado_md: "Implementar resta",
        inicial_codigo: null,
        unidad_tematica: "funciones",
        dificultad: "basica",
        test_cases: [],
      },
    },
  ]
}

const TAREA: AvailableTarea = {
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

/**
 * Mock de red con control por método: el mount hace `POST /entregas`
 * (createOrGet) y el submit hace `GET /entregas/{id}` (relectura fresca) +
 * `POST /entregas/{id}/submit`. Los tres pegan al mismo prefijo, así que
 * `setupFetchMock` (que sólo mira la URL) no alcanza.
 */
function mockearRed(opts: {
  /** Lo que devuelve la RELECTURA fresca previa al submit. */
  frescaEstado?: Entrega["estado"]
  /** Falla del POST /submit. */
  submitFalla?: { status: number; body: string }
}) {
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string | URL | Request, init?: RequestInit) => {
      const u = typeof url === "string" ? url : url.toString()
      const metodo = (init?.method ?? "GET").toUpperCase()
      const ok = (body: unknown) =>
        Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve(body),
          text: () => Promise.resolve(JSON.stringify(body)),
        } as Response)

      if (u.includes("/ejercicios")) return ok(pares())

      if (u.includes("/submit")) {
        if (opts.submitFalla) {
          return Promise.resolve({
            ok: false,
            status: opts.submitFalla.status,
            json: () => Promise.resolve({}),
            text: () => Promise.resolve(opts.submitFalla?.body ?? ""),
          } as Response)
        }
        return ok({ ...entregaLista("submitted"), submitted_at: "2026-08-27T12:00:00Z" })
      }
      // GET /entregas/{id} — la relectura fresca de `handleSubmit`.
      if (u.includes("/api/v1/entregas/") && metodo === "GET") {
        return ok(entregaLista(opts.frescaEstado ?? "draft"))
      }
      // POST /entregas — createOrGet del mount.
      if (u.includes("/api/v1/entregas")) return ok(entregaLista())

      // Los episodios que consulta `recuperarArtefactos` cuando no hay
      // borrador local: sin snapshot, para que no aporte nada.
      if (u.includes("/api/v1/episodes/")) {
        return ok({
          episode_id: "ep-1",
          tarea_practica_id: TAREA_ID,
          comision_id: COMISION_ID,
          estado: "closed",
          opened_at: "2026-08-27T10:00:00Z",
          closed_at: "2026-08-27T10:30:00Z",
          last_code_snapshot: "print('hola')\n",
          messages: [],
          notes: [],
        })
      }
      return ok({ data: [], meta: { cursor_next: null } })
    }),
  )
}

function montar() {
  return render(
    <ExerciseListView
      tarea={TAREA}
      comisionId={COMISION_ID}
      onSelectEjercicio={vi.fn()}
      onViewGrade={vi.fn()}
      onBack={vi.fn()}
    />,
  )
}

async function apretarEntregar() {
  const boton = await screen.findByTestId("submit-entrega-btn")
  fireEvent.click(boton)
  return boton
}

beforeEach(() => {
  window.localStorage.clear()
  window.sessionStorage.clear()
  // `handleSubmit` pide confirmación con el diálogo NATIVO del navegador.
  // jsdom no lo implementa; en el navegador real bloquea todo el hilo.
  vi.stubGlobal(
    "confirm",
    vi.fn(() => true),
  )
})

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe("E1 — el submit falla y el alumno recibe la excepción cruda", () => {
  it("le muestra el status HTTP y el body del backend, tal cual", async () => {
    mockearRed({
      submitFalla: { status: 500, body: "Internal Server Error" },
    })
    montar()
    await apretarEntregar()

    // Esto es lo que ve el alumno en el cartel rojo, palabra por palabra.
    const cartel = await screen.findByText(/submit entrega failed/)
    expect(cartel.textContent).toContain("500")
    expect(cartel.textContent).toContain("Internal Server Error")
    // No dice si su trabajo se guardó, no dice si puede reintentar, no dice
    // si tiene que avisarle al docente.
  })

  it("un 422 le filtra el JSON del backend en la cara", async () => {
    mockearRed({
      submitFalla: {
        status: 422,
        body: '{"detail":"Falta el código de los ejercicios: [2]"}',
      },
    })
    montar()
    await apretarEntregar()

    const cartel = await screen.findByText(/submit entrega failed/)
    // El backend sí dice algo útil ("falta el código del ejercicio 2"), pero
    // llega envuelto en `Error: submit entrega failed: 422 {"detail":...}`.
    // La única parte accionable está sepultada en el medio de un JSON.
    expect(cartel.textContent).toContain('{"detail":')
    expect(cartel.textContent).toMatch(/^Error: submit entrega failed: 422/)
  })
})

describe("E2 — el docente devolvió la TP y el botón se esfuma sin decir nada", () => {
  it("el aviso se setea pero NUNCA se renderiza: el alumno ve desaparecer el botón", async () => {
    // Escenario real: el alumno dejó la pestaña abierta en el celular. El
    // docente le devolvió la entrega para corregir (`returned`). El alumno
    // vuelve a la pestaña vieja —que sigue diciendo "draft"— y aprieta
    // "Entregar TP".
    mockearRed({ frescaEstado: "returned" })
    montar()

    const boton = await apretarEntregar()

    // El guard hace su trabajo: NO re-envía (eso borraría la devolución del
    // docente). Y setea un mensaje explicativo... que vive DENTRO del bloque
    // `{canSubmit && ...}`. Al guardar la entrega fresca, `canSubmit` pasa a
    // false y el bloque entero —mensaje incluido— se desmonta.
    await waitFor(() => {
      expect(screen.queryByTestId("submit-entrega-btn")).toBeNull()
    })
    expect(boton.isConnected).toBe(false)

    // El mensaje que el código escribió no llegó nunca a la pantalla.
    expect(screen.queryByText(/ya no esta en borrador/i)).toBeNull()
    expect(screen.queryByText(/Actualiza la pagina/i)).toBeNull()

    // Y tampoco aparece el cartel de "TP entregada" (ese sólo sale con
    // estado `submitted`). El alumno apretó el botón más importante de la
    // cursada y la pantalla se lo comió en silencio.
    expect(screen.queryByText(/TP entregada/i)).toBeNull()
  })
})

describe("E3 — lo que la pantalla le promete al alumno", () => {
  it('dice "tu docente recibira notificacion" — no existe ningún sistema de notificación', async () => {
    mockearRed({})
    montar()
    // Reproducido: el string está en pantalla. Que sea falso es un hallazgo
    // de lectura (no hay nada que mande mails ni push en el backend), pero la
    // promesa la hace ESTA pantalla y por eso queda anclada acá.
    expect(await screen.findByText(/tu docente recibira notificacion/i)).toBeDefined()
  })
})
