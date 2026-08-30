/**
 * Reproducciones de la auditoria del panel del docente (rama `audita/docente`).
 *
 * NO son tests de regresion de comportamiento deseado: cada `it` documenta algo
 * que HOY esta mal y lo deja corriendo para que el fix tenga contra que medirse.
 * Las aserciones estan escritas sobre el comportamiento ACTUAL (roto) y el
 * comentario dice cual deberia ser el correcto.
 */
import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { CorreccionesView } from "../src/views/CorreccionesView"
import { renderWithRouter, setupFetchMock } from "./_mocks"

const COMISION_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
const TAREA_ID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
const ENTREGA_ID = "cccccccc-cccc-cccc-cccc-cccccccccccc"
const STUDENT_ID = "b1b1b1b1-0001-0001-0001-000000000001"
const EJ_A = "11111111-0000-0000-0000-0000000000aa"
const EJ_B = "22222222-0000-0000-0000-0000000000bb"

const getToken = () => Promise.resolve("dev-token")

const entregaSubmitted = {
  id: ENTREGA_ID,
  tenant_id: "t1",
  tarea_practica_id: TAREA_ID,
  comision_id: COMISION_ID,
  student_pseudonym: STUDENT_ID,
  estado: "submitted",
  ejercicio_estados: [
    { orden: 1, ejercicio_id: EJ_A, completado: true, episode_id: null, completed_at: null },
    { orden: 2, ejercicio_id: EJ_B, completado: true, episode_id: null, completed_at: null },
  ],
  submitted_at: "2026-05-06T12:00:00Z",
  artefacto_sha256: null,
  legacy: false,
  created_at: "2026-05-06T10:00:00Z",
  updated_at: "2026-05-06T12:00:00Z",
}

const mockTarea = {
  id: TAREA_ID,
  tenant_id: "t1",
  comision_id: COMISION_ID,
  codigo: "TP01",
  titulo: "Funciones basicas",
  enunciado: "Implementar funciones",
  fecha_inicio: null,
  fecha_fin: null,
  peso: "1.0",
  rubrica: null,
  estado: "published",
  version: 1,
  parent_tarea_id: null,
  template_id: null,
  has_drift: false,
  created_by: "u1",
  created_at: "2026-05-01T00:00:00Z",
  updated_at: "2026-05-01T00:00:00Z",
}

/**
 * TP de dos ejercicios donde las DOS ponderaciones que la plataforma usa
 * apuntan al reves:
 *
 *   - `peso_en_tp`: A vale 0.90 del TP, B vale 0.10. Es lo que declaro el
 *     docente al armar el TP, y es lo que usa el resumen de Active-IA.
 *   - puntos de rubrica: A tiene 1 punto, B tiene 9. Es lo que usa la
 *     "Nota sugerida" de la correccion manual.
 */
function tpEjercicios(pesoA = "0.90", pesoB = "0.10") {
  return [
    {
      id: "tpe-a",
      tarea_practica_id: TAREA_ID,
      ejercicio_id: EJ_A,
      orden: 1,
      peso_en_tp: pesoA,
      ejercicio: {
        id: EJ_A,
        titulo: "Recursion",
        rubrica: {
          criterios: [{ nombre: "Correctitud", descripcion: "", puntaje_max: "1" }],
        },
      },
    },
    {
      id: "tpe-b",
      tarea_practica_id: TAREA_ID,
      ejercicio_id: EJ_B,
      orden: 2,
      peso_en_tp: pesoB,
      ejercicio: {
        id: EJ_B,
        titulo: "Estilo",
        rubrica: {
          criterios: [
            { nombre: "Nombres", descripcion: "", puntaje_max: "3" },
            { nombre: "Comentarios", descripcion: "", puntaje_max: "3" },
            { nombre: "Formato", descripcion: "", puntaje_max: "3" },
          ],
        },
      },
    },
  ]
}

async function abrirCorreccion() {
  renderWithRouter(<CorreccionesView comisionId={COMISION_ID} getToken={getToken} />)
  await waitFor(() => {
    expect(screen.getByTestId("entrega-drill-btn")).toBeDefined()
  })
  fireEvent.click(screen.getByTestId("entrega-drill-btn"))
  await waitFor(() => {
    expect(screen.getByTestId("grading-form-view")).toBeDefined()
  })
}

/** Expande la tarjeta del ejercicio (solo la primera nace abierta). */
function expandir(orden: number) {
  const card = screen.getByTestId(`ej-estado-${orden}`)
  const toggle = within(card).getAllByRole("button")[0]
  if (toggle) fireEvent.click(toggle)
}

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

describe("H1 — las dos notas del mismo trabajo", () => {
  it("la nota sugerida de la rubrica y la propuesta de Active-IA discrepan 8 puntos", async () => {
    // Mismo trabajo, mismas correcciones: el alumno hizo bien el ejercicio que
    // pesa 0.90 del TP (100/100) y mal el que pesa 0.10 (0/100).
    setupFetchMock({
      "/correccion-ia": () => ({
        correcciones: [
          {
            id: "c1",
            entrega_id: ENTREGA_ID,
            orden: 1,
            tp_ejercicio_id: EJ_A,
            estado: "done",
            nota_100: "100.00",
            created_at: "2026-05-06T13:00:00Z",
            desglose: [],
          },
          {
            id: "c2",
            entrega_id: ENTREGA_ID,
            orden: 2,
            tp_ejercicio_id: EJ_B,
            estado: "done",
            nota_100: "0.00",
            created_at: "2026-05-06T13:00:00Z",
            desglose: [],
          },
        ],
      }),
      "/ejercicios": () => tpEjercicios(),
      "/api/v1/entregas": () => ({ data: [entregaSubmitted], meta: { cursor_next: null } }),
      "/api/v1/tareas-practicas/": () => mockTarea,
    })
    await abrirCorreccion()

    // Active-IA pondera por `peso_en_tp`: 100*0.9 + 0*0.1 = 90 -> 9/10.
    await waitFor(() => {
      expect(screen.getByTestId("resumen-propuesta")).toBeDefined()
    })
    expect(screen.getByTestId("resumen-propuesta").textContent).toBe("9")

    // El docente carga la MISMA correccion a mano: todo bien en A, todo mal en B.
    fireEvent.change(screen.getByTestId(`criterio-puntaje-${EJ_A}#0`), { target: { value: "1" } })
    expandir(2)
    for (const i of [0, 1, 2]) {
      fireEvent.change(screen.getByTestId(`criterio-puntaje-${EJ_B}#${i}`), {
        target: { value: "0" },
      })
    }

    // `suggestNota` pondera por PUNTOS DE RUBRICA: 1/10 -> 1.0.
    // Ocho puntos de diferencia sobre el mismo trabajo y las mismas notas por
    // ejercicio. La pantalla muestra los dos numeros a la vez y no dice que
    // miden cosas distintas.
    await waitFor(() => {
      expect(screen.getByText(/Nota sugerida:/)).toBeDefined()
    })
    const sugerida = screen.getByText(/Nota sugerida:/).textContent ?? ""
    expect(sugerida).toContain("1.0")
  })
})

describe("H2 — criterios que el docente nunca toco se guardan como 0", () => {
  it("Calificar persiste puntaje 0 en los criterios vacios", async () => {
    setupFetchMock({
      "/correccion-ia": () => ({ correcciones: [] }),
      "/ejercicios": () => tpEjercicios(),
      "/api/v1/entregas": () => ({ data: [entregaSubmitted], meta: { cursor_next: null } }),
      "/api/v1/tareas-practicas/": () => mockTarea,
    })
    await abrirCorreccion()

    // El docente corrige SOLO el primer ejercicio y pone la nota a mano. Los
    // tres criterios del ejercicio 2 quedan en blanco: no los evaluo.
    fireEvent.change(await screen.findByTestId(`criterio-puntaje-${EJ_A}#0`), {
      target: { value: "1" },
    })
    fireEvent.change(screen.getByTestId("nota-final-input"), { target: { value: "8" } })
    fireEvent.change(screen.getByTestId("feedback-input"), { target: { value: "ok" } })
    fireEvent.click(screen.getByTestId("calificar-btn"))

    const fetchMock = globalThis.fetch as unknown as ReturnType<typeof vi.fn>
    await waitFor(() => {
      const llamadas = fetchMock.mock.calls.filter((c: unknown[]) =>
        String(c[0]).includes("/calificar"),
      )
      expect(llamadas.length).toBeGreaterThan(0)
    })
    const call = fetchMock.mock.calls.find((c: unknown[]) => String(c[0]).includes("/calificar"))
    const body = JSON.parse(String((call?.[1] as RequestInit).body))
    const detalle: Array<{ criterio: string; puntaje: number }> = body.detalle_criterios

    // Lo que queda escrito en `calificaciones.detalle_criterios`: tres ceros
    // que el docente no puso. En una plataforma cuya tesis es trazabilidad,
    // "no lo evalue" y "le puse 0" quedan indistinguibles en la base.
    expect(detalle.map((d) => d.puntaje)).toEqual([1, 0, 0, 0])
    expect(detalle.filter((d) => d.puntaje === 0).length).toBe(3)
  })
})

describe("H3 — un puntaje_max ilegible se vuelve 0 en silencio", () => {
  it("un criterio con puntaje_max no numerico no aporta al maximo y solo acepta 0", async () => {
    const ejercicios = tpEjercicios()
    // Caso real posible: el wizard de IA devolvio `puntaje_max` vacio, o la
    // rubrica se cargo a mano y quedo un string no numerico.
    ejercicios[1]!.ejercicio.rubrica.criterios[0]!.puntaje_max = ""
    setupFetchMock({
      "/correccion-ia": () => ({ correcciones: [] }),
      "/ejercicios": () => ejercicios,
      "/api/v1/entregas": () => ({ data: [entregaSubmitted], meta: { cursor_next: null } }),
      "/api/v1/tareas-practicas/": () => mockTarea,
    })
    await abrirCorreccion()
    expandir(2)

    // El criterio se muestra "/ 0": puntua sobre cero, y el input rechaza
    // cualquier valor > 0. El maximo del ejercicio bajo de 9 a 6 sin aviso,
    // asi que la "Nota sugerida" se calcula sobre otro denominador.
    const fila = screen.getByTestId(`criterio-row-${EJ_B}#0`)
    expect(within(fila).getByText("/ 0")).toBeDefined()

    fireEvent.change(screen.getByTestId(`criterio-puntaje-${EJ_A}#0`), { target: { value: "1" } })
    fireEvent.change(screen.getByTestId(`criterio-puntaje-${EJ_B}#0`), { target: { value: "3" } })
    fireEvent.change(screen.getByTestId("nota-final-input"), { target: { value: "8" } })
    fireEvent.change(screen.getByTestId("feedback-input"), { target: { value: "ok" } })
    fireEvent.click(screen.getByTestId("calificar-btn"))

    // No guarda: el docente queda trabado sin entender por que, con el mensaje
    // "debe estar entre 0 y 0".
    await waitFor(() => {
      expect(screen.getByText(/entre 0 y 0/)).toBeDefined()
    })
  })
})

describe("H7 — un ejercicio sin rubrica desaparece del progreso y de la nota", () => {
  it("la TP se declara 100% corregida con la mitad sin evaluar, y sugiere 10", async () => {
    // TP de dos ejercicios donde el segundo no tiene rubrica cargada — algo que
    // el gate de publicacion permite (`validar_tp_no_vacia` cuenta ejercicios,
    // no mira su contenido).
    const ejercicios = tpEjercicios("0.50", "0.50")
    ejercicios[1]!.ejercicio.rubrica = null
    setupFetchMock({
      "/correccion-ia": () => ({ correcciones: [] }),
      "/ejercicios": () => ejercicios,
      "/api/v1/entregas": () => ({ data: [entregaSubmitted], meta: { cursor_next: null } }),
      "/api/v1/tareas-practicas/": () => mockTarea,
    })
    await abrirCorreccion()

    // El docente puntua al maximo el UNICO ejercicio que tiene rubrica.
    fireEvent.change(await screen.findByTestId(`criterio-puntaje-${EJ_A}#0`), {
      target: { value: "1" },
    })

    // La pantalla declara la TP entera corregida: `totalCalificables` sólo
    // cuenta los ejercicios CON rubrica. El de al lado, que vale la mitad del
    // TP, no figura ni como pendiente.
    await waitFor(() => {
      expect(screen.getByTestId("correccion-progreso").textContent).toContain(
        "1 de 1 ejercicios corregidos",
      )
    })

    // Y propone un 10 sobre la mitad del trabajo. Es exactamente lo que el
    // camino de Active-IA se niega a hacer (`correccionIA.ts`: "Falta alguno ->
    // NO se promedia"); el camino manual no tiene ese guard.
    expect(screen.getByText(/Nota sugerida:/).textContent).toContain("10.0")
  })
})

describe("H6 — la cola en lote solo abarca la primera pagina", () => {
  it("con mas entregas de las cargadas, el boton anuncia el subconjunto como si fuera el total", async () => {
    // El backend pagina de a 50 (`limit` default de `GET /entregas`). Con 30
    // alumnos y varias TPs, la primera pagina no es la comision entera.
    const pagina1 = Array.from({ length: 3 }, (_, i) => ({
      ...entregaSubmitted,
      id: `dddddddd-0000-0000-0000-00000000000${i}`,
    }))
    setupFetchMock({
      "/correccion-ia": () => ({ correcciones: [] }),
      "/ejercicios": () => [],
      // `cursor_next` no nulo = hay mas paginas sin traer.
      "/api/v1/entregas": () => ({
        data: pagina1,
        meta: { cursor_next: "dddddddd-0000-0000-0000-000000000002" },
      }),
      "/api/v1/tareas-practicas/": () => mockTarea,
    })
    renderWithRouter(<CorreccionesView comisionId={COMISION_ID} getToken={getToken} />)
    await waitFor(() => {
      expect(screen.getByTestId("corregir-en-lote-btn")).toBeDefined()
    })

    // El boton dice "Corregir en lote 3" y la cola arranca con 3, aunque el
    // propio backend acaba de avisar que hay mas (cursor_next != null). No hay
    // nada en el boton ni al lado que diga "de lo cargado".
    expect(screen.getByTestId("corregir-en-lote-btn").textContent).toContain("3")
    fireEvent.click(screen.getByTestId("corregir-en-lote-btn"))
    await waitFor(() => {
      expect(screen.getByTestId("batch-progress-counter")).toBeDefined()
    })
    expect(screen.getByTestId("batch-progress-counter").textContent).toContain("de")
    expect(screen.getByTestId("batch-progress-counter").textContent).toContain("3")
  })
})

describe("H0 — nada verifica que `nota_100` este en escala 0-100", () => {
  it("una nota de Active-IA en escala 0-10 se propone como un decimo de si misma", async () => {
    // Active-IA devuelve `nota` y el evaluation-service la escribe tal cual en
    // `nota_100` (correccion_ejecutor.py:451). No hay `Field(ge=0, le=100)`, ni
    // CHECK de rango en la tabla (el unico CHECK es sobre null/estado), ni
    // normalizacion en el frontend. La rubrica que sumaba 9 o 10 —una de las
    // dos escalas que conviven hoy— entra por aca.
    setupFetchMock({
      "/correccion-ia": () => ({
        correcciones: [
          {
            id: "c1",
            entrega_id: ENTREGA_ID,
            orden: 1,
            tp_ejercicio_id: EJ_A,
            estado: "done",
            nota_100: "8.00",
            created_at: "2026-05-06T13:00:00Z",
            // El desglose cierra contra el total: `chequearAritmetica` da OK.
            // La unica defensa de la pantalla es ciega a un error de escala.
            desglose: [{ criterio: "Correctitud", puntaje: 8 }],
          },
          {
            id: "c2",
            entrega_id: ENTREGA_ID,
            orden: 2,
            tp_ejercicio_id: EJ_B,
            estado: "done",
            nota_100: "8.00",
            created_at: "2026-05-06T13:00:00Z",
            desglose: [{ criterio: "Estilo", puntaje: 8 }],
          },
        ],
      }),
      "/ejercicios": () => tpEjercicios(),
      "/api/v1/entregas": () => ({ data: [entregaSubmitted], meta: { cursor_next: null } }),
      "/api/v1/tareas-practicas/": () => mockTarea,
    })
    await abrirCorreccion()

    await waitFor(() => {
      expect(screen.getByTestId("resumen-propuesta")).toBeDefined()
    })
    // Un 8 se propone como 0.8. La pantalla lo imprime como "8/100 x 90%" y
    // "Equivale a 0.8/10", sin una sola advertencia de escala.
    expect(screen.getByTestId("resumen-propuesta").textContent).toBe("0.8")
    expect(screen.getByTestId("resumen-terminos").textContent).toContain("8/100")

    // Y el boton escribe ese 0.8 en el campo de nota final, que lo acepta:
    // esta dentro de 0..10, asi que ninguna validacion lo frena.
    fireEvent.click(screen.getByTestId("resumen-usar-como-base"))
    await waitFor(() => {
      expect((screen.getByTestId("nota-final-input") as HTMLInputElement).value).toBe("0.8")
    })
  })
})

describe("H5 — una correccion a medias se pierde sin aviso", () => {
  it("volver a la lista descarta la rubrica y el feedback tipeados", async () => {
    setupFetchMock({
      "/correccion-ia": () => ({ correcciones: [] }),
      "/ejercicios": () => tpEjercicios(),
      "/api/v1/entregas": () => ({ data: [entregaSubmitted], meta: { cursor_next: null } }),
      "/api/v1/tareas-practicas/": () => mockTarea,
    })
    await abrirCorreccion()

    // Quince minutos de corrección: los puntajes de la rúbrica y un feedback
    // largo escrito a mano.
    fireEvent.change(await screen.findByTestId(`criterio-puntaje-${EJ_A}#0`), {
      target: { value: "1" },
    })
    fireEvent.change(screen.getByTestId("feedback-input"), {
      target: { value: "Muy buena resolucion recursiva, revisar el caso base." },
    })

    // El docente vuelve a la lista para chequear otra entrega. NO hay
    // confirmacion, ni borrador, ni `beforeunload`: el formulario vive solo en
    // estado de React.
    fireEvent.click(screen.getByText(/Volver a entregas/i))
    await waitFor(() => {
      expect(screen.getByTestId("entregas-list-view")).toBeDefined()
    })
    fireEvent.click(screen.getByTestId("entrega-drill-btn"))

    const feedback = (await screen.findByTestId("feedback-input")) as HTMLTextAreaElement
    expect(feedback.value).toBe("")
    const puntaje = (await screen.findByTestId(`criterio-puntaje-${EJ_A}#0`)) as HTMLInputElement
    expect(puntaje.value).toBe("")
  })
})

describe("H4 — los contadores de la cola cuentan solo lo que esta cargado", () => {
  it("con un filtro de estado activo, los otros contadores muestran 0", async () => {
    const graded = {
      ...entregaSubmitted,
      id: "dddddddd-0000-0000-0000-000000000001",
      estado: "graded",
    }
    setupFetchMock({
      "/correccion-ia": () => ({ correcciones: [] }),
      "/ejercicios": () => [],
      // El backend filtra por `estado` server-side (entregas.py:186-187).
      "/api/v1/entregas": () => ({ data: [entregaSubmitted, graded], meta: { cursor_next: null } }),
      "/api/v1/tareas-practicas/": () => mockTarea,
    })
    renderWithRouter(<CorreccionesView comisionId={COMISION_ID} getToken={getToken} />)
    await waitFor(() => {
      expect(screen.getByTestId("entregas-table")).toBeDefined()
    })

    const chip = (nombre: RegExp) => screen.getByRole("tab", { name: nombre })
    // Sin filtro: 1 pendiente + 1 calificada. Los contadores cierran.
    expect(chip(/Enviada/).textContent).toContain("1")
    expect(chip(/Calificada/).textContent).toContain("1")

    // El docente clickea "Enviada" para ver solo lo que le falta corregir.
    // El backend devuelve SOLO las submitted; `counts` se recalcula sobre ese
    // set y el resto de los chips se van a 0.
    const respuestaFiltrada = { data: [entregaSubmitted], meta: { cursor_next: null } }
    setupFetchMock({
      "/correccion-ia": () => ({ correcciones: [] }),
      "/ejercicios": () => [],
      "/api/v1/entregas": () => respuestaFiltrada,
      "/api/v1/tareas-practicas/": () => mockTarea,
    })
    fireEvent.click(chip(/Enviada/))

    // Mientras react-query recarga con la queryKey nueva, `entregas` es [] y
    // TODOS los chips muestran 0 — "cargando" y "no hay nada" se ven igual.
    await waitFor(() => {
      expect(chip(/Todos/).textContent).toContain("1")
    })
    // La pantalla dice: "Calificada 0". El docente califico una. El contador
    // no es "cuantas hay", es "cuantas de las que cargue en esta consulta".
    expect(chip(/Calificada/).textContent).toContain("0")
    expect(chip(/Devuelta/).textContent).toContain("0")
  })
})
