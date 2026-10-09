/**
 * Tests para CorreccionesView (EntregasListView + GradingFormView).
 * tp-entregas-correccion, task 12.2.
 *
 * Cubre:
 *   - EntregasListView: muestra tabla con filas de entregas
 *   - EntregasListView: filtra por estado
 *   - EntregasListView: click en fila abre GradingFormView
 *   - GradingFormView: muestra cabecera y ejercicios de la entrega
 *   - GradingFormView: muestra formulario para entregas submitted
 *   - GradingFormView: muestra boton Devolver para entregas graded
 *   - GradingFormView: no muestra boton Calificar para entregas graded
 */
import { cleanup, fireEvent, screen, waitFor } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { CorreccionesView } from "../src/views/CorreccionesView"
import { renderWithRouter, setupFetchMock } from "./_mocks"

const COMISION_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
const TAREA_ID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
const ENTREGA_ID = "cccccccc-cccc-cccc-cccc-cccccccccccc"
const STUDENT_ID = "b1b1b1b1-0001-0001-0001-000000000001"

const mockEntregaSubmitted = {
  id: ENTREGA_ID,
  tenant_id: "t1",
  tarea_practica_id: TAREA_ID,
  comision_id: COMISION_ID,
  student_pseudonym: STUDENT_ID,
  estado: "submitted",
  ejercicio_estados: [
    {
      orden: 1,
      completado: true,
      episode_id: "ep-0000001-abcd",
      completado_at: "2026-05-06T11:00:00Z",
    },
    {
      orden: 2,
      completado: true,
      episode_id: "ep-0000002-abcd",
      completado_at: "2026-05-06T11:30:00Z",
    },
  ],
  submitted_at: "2026-05-06T12:00:00Z",
  created_at: "2026-05-06T10:00:00Z",
  updated_at: "2026-05-06T12:00:00Z",
}

const mockEntregaGraded = {
  ...mockEntregaSubmitted,
  estado: "graded",
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

const getToken = () => Promise.resolve("dev-token")

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

describe("CorreccionesView — EntregasListView", () => {
  it("muestra la tabla con una entrega submitted", async () => {
    setupFetchMock({
      // Las sub-rutas van ARRIBA: `/api/v1/entregas` las matchea a todas por
      // `includes`, y les devolveria el shape pageable donde el codigo espera
      // una lista. El sintoma engana — el test dice "Unable to find
      // [data-testid=...]" como si el componente no renderizara, y en realidad
      // revento antes con "X is not iterable".
      "/correccion-ia": () => ({ correcciones: [] }),
      "/api/v1/entregas": () => ({ data: [mockEntregaSubmitted], meta: { cursor_next: null } }),
      // La ruta de ejercicios devuelve un ARRAY pelado, no el shape
      // pageable del default. Sin declararla, `listTpEjercicios` recibe
      // `{data:[],meta:{}}` y el componente muere en `tpEjercicios.slice`
      // — con un sintoma que enganna: el test falla con "Unable to find
      // [data-testid=...]" como si no renderizara, y en realidad revento antes.
      "/ejercicios": () => [],
      "/api/v1/tareas-practicas/": () => mockTarea,
    })
    renderWithRouter(<CorreccionesView comisionId={COMISION_ID} getToken={getToken} />)
    // Se espera por la TABLA, no por `entregas-list-view`: ese div es el
    // contenedor de la vista y esta desde el primer render, asi que el
    // `waitFor` volvia de inmediato y la asercion corria ANTES de que la data
    // llegara. Desde que la vista pasa por react-query esa carrera es siempre
    // perdida; antes andaba de casualidad.
    await waitFor(() => {
      expect(screen.getByTestId("entregas-table")).toBeDefined()
    })
    const rows = screen.getAllByTestId("entrega-row")
    expect(rows.length).toBe(1)
  })

  it("muestra badge de estado 'Enviada' para submitted", async () => {
    setupFetchMock({
      // Las sub-rutas van ARRIBA: `/api/v1/entregas` las matchea a todas por
      // `includes`, y les devolveria el shape pageable donde el codigo espera
      // una lista. El sintoma engana — el test dice "Unable to find
      // [data-testid=...]" como si el componente no renderizara, y en realidad
      // revento antes con "X is not iterable".
      "/correccion-ia": () => ({ correcciones: [] }),
      "/api/v1/entregas": () => ({ data: [mockEntregaSubmitted], meta: { cursor_next: null } }),
      // La ruta de ejercicios devuelve un ARRAY pelado, no el shape
      // pageable del default. Sin declararla, `listTpEjercicios` recibe
      // `{data:[],meta:{}}` y el componente muere en `tpEjercicios.slice`
      // — con un sintoma que enganna: el test falla con "Unable to find
      // [data-testid=...]" como si no renderizara, y en realidad revento antes.
      "/ejercicios": () => [],
      "/api/v1/tareas-practicas/": () => mockTarea,
    })
    renderWithRouter(<CorreccionesView comisionId={COMISION_ID} getToken={getToken} />)
    await waitFor(() => {
      expect(screen.getByTestId("entrega-estado-submitted")).toBeDefined()
    })
    // "Enviada" aparece en 2 lugares: el badge de estado y el label del timestamp
    // de submitted_at. Asertamos que el badge contiene la etiqueta correcta.
    expect(screen.getByTestId("entrega-estado-submitted")).toHaveTextContent("Enviada")
  })

  it("muestra mensaje cuando no hay entregas", async () => {
    setupFetchMock({
      "/api/v1/entregas": () => ({ data: [], meta: { cursor_next: null } }),
    })
    renderWithRouter(<CorreccionesView comisionId={COMISION_ID} getToken={getToken} />)
    // Mismo motivo que arriba: se espera por el MENSAJE, no por el contenedor.
    await waitFor(() => {
      expect(screen.getByText(/aun no tiene entregas/i)).toBeDefined()
    })
  })

  it("click en Corregir abre el GradingFormView", async () => {
    setupFetchMock({
      // Las sub-rutas van ARRIBA: `/api/v1/entregas` las matchea a todas por
      // `includes`, y les devolveria el shape pageable donde el codigo espera
      // una lista. El sintoma engana — el test dice "Unable to find
      // [data-testid=...]" como si el componente no renderizara, y en realidad
      // revento antes con "X is not iterable".
      "/correccion-ia": () => ({ correcciones: [] }),
      "/api/v1/entregas": () => ({ data: [mockEntregaSubmitted], meta: { cursor_next: null } }),
      // La ruta de ejercicios devuelve un ARRAY pelado, no el shape
      // pageable del default. Sin declararla, `listTpEjercicios` recibe
      // `{data:[],meta:{}}` y el componente muere en `tpEjercicios.slice`
      // — con un sintoma que enganna: el test falla con "Unable to find
      // [data-testid=...]" como si no renderizara, y en realidad revento antes.
      "/ejercicios": () => [],
      "/api/v1/tareas-practicas/": () => mockTarea,
    })
    renderWithRouter(<CorreccionesView comisionId={COMISION_ID} getToken={getToken} />)
    await waitFor(() => {
      expect(screen.getByTestId("entrega-drill-btn")).toBeDefined()
    })
    fireEvent.click(screen.getByTestId("entrega-drill-btn"))
    await waitFor(() => {
      expect(screen.getByTestId("grading-form-view")).toBeDefined()
    })
  })
})

describe("CorreccionesView — GradingFormView", () => {
  it("muestra los ejercicios completados en la entrega", async () => {
    setupFetchMock({
      // Las sub-rutas van ARRIBA: `/api/v1/entregas` las matchea a todas por
      // `includes`, y les devolveria el shape pageable donde el codigo espera
      // una lista. El sintoma engana — el test dice "Unable to find
      // [data-testid=...]" como si el componente no renderizara, y en realidad
      // revento antes con "X is not iterable".
      "/correccion-ia": () => ({ correcciones: [] }),
      "/api/v1/entregas": () => ({ data: [mockEntregaSubmitted], meta: { cursor_next: null } }),
      // La ruta de ejercicios devuelve un ARRAY pelado, no el shape
      // pageable del default. Sin declararla, `listTpEjercicios` recibe
      // `{data:[],meta:{}}` y el componente muere en `tpEjercicios.slice`
      // — con un sintoma que enganna: el test falla con "Unable to find
      // [data-testid=...]" como si no renderizara, y en realidad revento antes.
      "/ejercicios": () => [],
      "/api/v1/tareas-practicas/": () => mockTarea,
    })
    renderWithRouter(<CorreccionesView comisionId={COMISION_ID} getToken={getToken} />)
    await waitFor(() => {
      expect(screen.getByTestId("entrega-drill-btn")).toBeDefined()
    })
    fireEvent.click(screen.getByTestId("entrega-drill-btn"))
    await waitFor(() => {
      expect(screen.getByTestId("ejercicios-estados-list")).toBeDefined()
    })
    expect(screen.getByTestId("ej-estado-1")).toBeDefined()
    expect(screen.getByTestId("ej-estado-2")).toBeDefined()
  })

  it("muestra el formulario de calificacion para entrega submitted", async () => {
    setupFetchMock({
      // Las sub-rutas van ARRIBA: `/api/v1/entregas` las matchea a todas por
      // `includes`, y les devolveria el shape pageable donde el codigo espera
      // una lista. El sintoma engana — el test dice "Unable to find
      // [data-testid=...]" como si el componente no renderizara, y en realidad
      // revento antes con "X is not iterable".
      "/correccion-ia": () => ({ correcciones: [] }),
      "/api/v1/entregas": () => ({ data: [mockEntregaSubmitted], meta: { cursor_next: null } }),
      // La ruta de ejercicios devuelve un ARRAY pelado, no el shape
      // pageable del default. Sin declararla, `listTpEjercicios` recibe
      // `{data:[],meta:{}}` y el componente muere en `tpEjercicios.slice`
      // — con un sintoma que enganna: el test falla con "Unable to find
      // [data-testid=...]" como si no renderizara, y en realidad revento antes.
      "/ejercicios": () => [],
      "/api/v1/tareas-practicas/": () => mockTarea,
    })
    renderWithRouter(<CorreccionesView comisionId={COMISION_ID} getToken={getToken} />)
    await waitFor(() => {
      expect(screen.getByTestId("entrega-drill-btn")).toBeDefined()
    })
    fireEvent.click(screen.getByTestId("entrega-drill-btn"))
    await waitFor(() => {
      expect(screen.getByTestId("calificar-btn")).toBeDefined()
    })
    expect(screen.getByTestId("nota-final-input")).toBeDefined()
    expect(screen.getByTestId("feedback-input")).toBeDefined()
  })

  it("muestra boton Devolver para entrega graded", async () => {
    const calificacion = {
      id: "d1",
      entrega_id: ENTREGA_ID,
      nota_final: 8,
      feedback_general: "Buen trabajo",
      detalle_criterios: [],
      calificado_at: "2026-05-06T13:00:00Z",
      calificador_id: "docente-1",
    }
    setupFetchMock({
      // Las sub-rutas van ARRIBA de `/api/v1/entregas`: ese prefijo las matchea
      // a todas por `includes` y les devuelve el shape pageable donde el codigo
      // espera otra cosa. El sintoma engana — el test dice "Unable to find
      // [data-testid=...]" como si no renderizara, y en realidad revento antes.
      "/calificacion": () => calificacion,
      "/correccion-ia": () => ({ correcciones: [] }),
      "/ejercicios": () => [],
      "/api/v1/entregas": () => ({ data: [mockEntregaGraded], meta: { cursor_next: null } }),
      "/api/v1/tareas-practicas/": () => mockTarea,
    })
    renderWithRouter(<CorreccionesView comisionId={COMISION_ID} getToken={getToken} />)
    await waitFor(() => {
      expect(screen.getByTestId("entrega-drill-btn")).toBeDefined()
    })
    fireEvent.click(screen.getByTestId("entrega-drill-btn"))
    await waitFor(() => {
      expect(screen.getByTestId("devolver-btn")).toBeDefined()
    })
    expect(screen.queryByTestId("calificar-btn")).toBeNull()
  })

  it("BUG-12: tras Calificar exitoso, Devolver al estudiante aparece sin apretar Cancelar", async () => {
    // Reproduce el camino real del bug: el docente usa la sugerencia de
    // Active-IA ("Usar como base"), que deja la vista en reediting=true
    // (`onUsarComoBase` llama `setReediting(true)`) ANTES de calificar. Si
    // `handleCalificar` no sale de `reediting` al terminar, el gate de
    // "Devolver al estudiante" (`entrega.estado === "graded" && !reediting &&
    // !queueMode`) queda cerrado hasta que el docente aprieta "Cancelar" — que
    // se lee como descartar la calificacion que recien guardo.
    const calificacionGuardada = {
      id: "califid-1",
      entrega_id: ENTREGA_ID,
      nota_final: 9,
      feedback_general: "Buen trabajo",
      detalle_criterios: [],
      calificado_at: "2026-09-23T13:00:00Z",
      calificador_id: "docente-1",
    }
    const correccionIA = {
      id: "corr-1",
      entrega_id: ENTREGA_ID,
      tp_ejercicio_id: null,
      orden: 1,
      estado: "done",
      rubrica_id: "nativa:v1",
      nota_100: 90,
      desglose: [],
      tests_snapshot: {},
      created_at: "2026-09-23T12:00:00Z",
    }
    const tpEjercicio = {
      id: "tpej-1",
      tarea_practica_id: TAREA_ID,
      ejercicio_id: "ej-1",
      orden: 1,
      peso_en_tp: "1.00",
      ejercicio: { id: "ej-1", titulo: "Ejercicio 1", rubrica: null },
    }
    setupFetchMock({
      // Las rutas mas especificas van ARRIBA de "/api/v1/entregas": ese
      // prefijo matchea a todas por `includes` (get singular, calificar,
      // calificacion) y les devolveria el shape pageable donde el codigo
      // espera otra cosa.
      "/calificacion": () => calificacionGuardada,
      "/correccion-ia": () => ({ correcciones: [correccionIA] }),
      "/ejercicios": () => [tpEjercicio],
      [`/api/v1/entregas/${ENTREGA_ID}/calificar`]: () => calificacionGuardada,
      [`/api/v1/entregas/${ENTREGA_ID}`]: () => mockEntregaGraded,
      "/api/v1/entregas": () => ({ data: [mockEntregaSubmitted], meta: { cursor_next: null } }),
      "/api/v1/tareas-practicas/": () => mockTarea,
    })
    renderWithRouter(<CorreccionesView comisionId={COMISION_ID} getToken={getToken} />)
    await waitFor(() => {
      expect(screen.getByTestId("entrega-drill-btn")).toBeDefined()
    })
    fireEvent.click(screen.getByTestId("entrega-drill-btn"))

    // "Usar como base" deja la vista en reediting=true, antes de calificar.
    await waitFor(() => {
      expect(screen.getByTestId("resumen-usar-como-base")).toBeDefined()
    })
    fireEvent.click(screen.getByTestId("resumen-usar-como-base"))

    fireEvent.change(screen.getByTestId("feedback-input"), {
      target: { value: "Buen trabajo" },
    })
    fireEvent.click(screen.getByTestId("calificar-btn"))

    await waitFor(() => {
      expect(screen.getByTestId("devolver-btn")).toBeDefined()
    })
    // No debe requerir un click en "Cancelar" para verlo.
    expect(screen.queryByTestId("cancelar-recalificacion-btn")).toBeNull()
  })

  it("BUG-12 (borde): Calificar sin pasar por 'Usar como base' tambien deja Devolver visible", async () => {
    // Caso sin la sugerencia de IA: `reediting` nunca se activa antes de
    // calificar. `setReediting(false)` en `handleCalificar` debe ser inocuo
    // aca (ya estaba en false) y el boton debe seguir apareciendo — cubre que
    // el fix no dependa de que la sugerencia de IA haya sido usada.
    const calificacionGuardada = {
      id: "califid-2",
      entrega_id: ENTREGA_ID,
      nota_final: 7,
      feedback_general: "Correcto",
      detalle_criterios: [],
      calificado_at: "2026-09-23T14:00:00Z",
      calificador_id: "docente-1",
    }
    setupFetchMock({
      "/calificacion": () => calificacionGuardada,
      "/correccion-ia": () => ({ correcciones: [] }),
      "/ejercicios": () => [],
      [`/api/v1/entregas/${ENTREGA_ID}/calificar`]: () => calificacionGuardada,
      [`/api/v1/entregas/${ENTREGA_ID}`]: () => mockEntregaGraded,
      "/api/v1/entregas": () => ({ data: [mockEntregaSubmitted], meta: { cursor_next: null } }),
      "/api/v1/tareas-practicas/": () => mockTarea,
    })
    renderWithRouter(<CorreccionesView comisionId={COMISION_ID} getToken={getToken} />)
    await waitFor(() => {
      expect(screen.getByTestId("entrega-drill-btn")).toBeDefined()
    })
    fireEvent.click(screen.getByTestId("entrega-drill-btn"))
    await waitFor(() => {
      expect(screen.getByTestId("calificar-btn")).toBeDefined()
    })
    fireEvent.change(screen.getByTestId("nota-final-input"), { target: { value: "7" } })
    fireEvent.change(screen.getByTestId("feedback-input"), { target: { value: "Correcto" } })
    fireEvent.click(screen.getByTestId("calificar-btn"))

    await waitFor(() => {
      expect(screen.getByTestId("devolver-btn")).toBeDefined()
    })
    expect(screen.queryByTestId("cancelar-recalificacion-btn")).toBeNull()
  })

  it("RUBRICA-AUTOCOMPLETE: 'Usar como base' autocompleta los puntajes por criterio, no solo la nota", async () => {
    // Antes, `onUsarComoBase` solo rellenaba `nota-final`; el docente tenia
    // que copiar el desglose a mano criterio por criterio. Sin eso, "Usar
    // como base" + "Calificar" persistia detalle_criterios con puntaje 0 en
    // cada fila — la mitad del BUG-19 que ve el alumno como "0 / NaN".
    const tpEjercicioConRubrica = {
      id: "tpej-1",
      tarea_practica_id: TAREA_ID,
      ejercicio_id: "ej-1",
      orden: 1,
      peso_en_tp: "1.00",
      ejercicio: {
        id: "ej-1",
        titulo: "Ejercicio 1",
        rubrica: {
          criterios: [
            { nombre: "Usa la interfaz", descripcion: "", puntaje_max: "5" },
            { nombre: "Produce la salida esperada", descripcion: "", puntaje_max: "5" },
          ],
        },
      },
    }
    const correccionIA = {
      id: "corr-1",
      entrega_id: ENTREGA_ID,
      tp_ejercicio_id: "ej-1",
      orden: 1,
      estado: "done",
      rubrica_id: "nativa:v1",
      nota_100: 70,
      desglose: [
        { nombre: "Usa la interfaz", puntaje: 3 },
        { nombre: "Produce la salida esperada", puntaje: 4 },
      ],
      tests_snapshot: {},
      created_at: "2026-09-23T12:00:00Z",
    }
    setupFetchMock({
      "/correccion-ia": () => ({ correcciones: [correccionIA] }),
      "/ejercicios": () => [tpEjercicioConRubrica],
      "/api/v1/entregas": () => ({ data: [mockEntregaSubmitted], meta: { cursor_next: null } }),
      "/api/v1/tareas-practicas/": () => mockTarea,
    })
    renderWithRouter(<CorreccionesView comisionId={COMISION_ID} getToken={getToken} />)
    await waitFor(() => {
      expect(screen.getByTestId("entrega-drill-btn")).toBeDefined()
    })
    fireEvent.click(screen.getByTestId("entrega-drill-btn"))

    await waitFor(() => {
      expect(screen.getByTestId("resumen-usar-como-base")).toBeDefined()
    })
    fireEvent.click(screen.getByTestId("resumen-usar-como-base"))

    // El ejercicio 1 esta abierto por default (primera tarjeta): sus
    // criterios se autocompletan con el desglose de la correccion vigente.
    await waitFor(() => {
      expect(screen.getByTestId("criterio-puntaje-ej-1#0")).toHaveValue(3)
    })
    expect(screen.getByTestId("criterio-puntaje-ej-1#1")).toHaveValue(4)
  })

  it("boton Volver regresa a la lista", async () => {
    setupFetchMock({
      // Las sub-rutas van ARRIBA: `/api/v1/entregas` las matchea a todas por
      // `includes`, y les devolveria el shape pageable donde el codigo espera
      // una lista. El sintoma engana — el test dice "Unable to find
      // [data-testid=...]" como si el componente no renderizara, y en realidad
      // revento antes con "X is not iterable".
      "/correccion-ia": () => ({ correcciones: [] }),
      "/api/v1/entregas": () => ({ data: [mockEntregaSubmitted], meta: { cursor_next: null } }),
      // La ruta de ejercicios devuelve un ARRAY pelado, no el shape
      // pageable del default. Sin declararla, `listTpEjercicios` recibe
      // `{data:[],meta:{}}` y el componente muere en `tpEjercicios.slice`
      // — con un sintoma que enganna: el test falla con "Unable to find
      // [data-testid=...]" como si no renderizara, y en realidad revento antes.
      "/ejercicios": () => [],
      "/api/v1/tareas-practicas/": () => mockTarea,
    })
    renderWithRouter(<CorreccionesView comisionId={COMISION_ID} getToken={getToken} />)
    await waitFor(() => {
      expect(screen.getByTestId("entrega-drill-btn")).toBeDefined()
    })
    fireEvent.click(screen.getByTestId("entrega-drill-btn"))
    await waitFor(() => {
      expect(screen.getByTestId("grading-form-view")).toBeDefined()
    })
    // Click en Volver
    const backBtn = screen.getByText(/Volver a entregas/i)
    fireEvent.click(backBtn)
    await waitFor(() => {
      expect(screen.getByTestId("entregas-list-view")).toBeDefined()
    })
  })
})

/**
 * Hallazgo #2: `EjercicioCodigo` leia solo los eventos del episodio. Si el
 * reintento vacio pisaba el `episode_id`, mostraba "// Sin codigo registrado"
 * aunque el artefacto entregado (hash-sellado) tenia el codigo real. Ahora
 * muestra primero `artefactos[orden].codigo` y cae a los eventos solo si no hay.
 */
describe("CorreccionesView — codigo entregado vs reconstruido", () => {
  const artefacto = (codigo: string) => ({
    entrega_id: ENTREGA_ID,
    tarea_practica_id: TAREA_ID,
    student_pseudonym: STUDENT_ID,
    submitted_at: "2026-05-06T12:00:00Z",
    artefacto_sha256: "abc",
    legacy: false,
    artefactos: [
      {
        orden: 1,
        ejercicio_id: null,
        episode_id: "ep-0000001-abcd",
        codigo,
        language: "python",
        sha256: "h1",
        created_at: "2026-05-06T12:00:00Z",
      },
    ],
  })
  const eventosConCodigo = (snapshot: string) => ({
    episode_id: "ep-0000001-abcd",
    events: [{ event_type: "edicion_codigo", seq: 1, payload: { snapshot } }],
  })
  const eventosVacios = { episode_id: "ep-0000001-abcd", events: [] }

  async function abrirEntrega() {
    renderWithRouter(<CorreccionesView comisionId={COMISION_ID} getToken={getToken} />)
    await waitFor(() => {
      expect(screen.getByTestId("entrega-drill-btn")).toBeDefined()
    })
    fireEvent.click(screen.getByTestId("entrega-drill-btn"))
  }

  const baseHandlers = {
    "/correccion-ia": () => ({ correcciones: [] }),
    "/ejercicios": () => [],
    "/api/v1/tareas-practicas/": () => mockTarea,
  }

  it("muestra el codigo del artefacto entregado cuando los eventos del episodio estan vacios", async () => {
    setupFetchMock({
      ...baseHandlers,
      "/artefacto": () => artefacto("def suma(a, b):\n    return a + b"),
      "/api/v1/audit/episodes/": () => eventosVacios,
      "/api/v1/entregas": () => ({ data: [mockEntregaSubmitted], meta: { cursor_next: null } }),
    })
    await abrirEntrega()
    await waitFor(() => {
      expect(screen.getByText(/def suma\(a, b\)/)).toBeDefined()
    })
    expect(screen.queryByText("// Sin codigo registrado")).toBeNull()
    expect(screen.getByTestId("codigo-origen-1")).toHaveTextContent(/entregado/i)
  })

  it("el artefacto gana sobre un snapshot distinto de los eventos", async () => {
    setupFetchMock({
      ...baseHandlers,
      "/artefacto": () => artefacto("print('entregado')"),
      "/api/v1/audit/episodes/": () => eventosConCodigo("print('reconstruido')"),
      "/api/v1/entregas": () => ({ data: [mockEntregaSubmitted], meta: { cursor_next: null } }),
    })
    await abrirEntrega()
    await waitFor(() => {
      expect(screen.getByText("print('entregado')")).toBeDefined()
    })
    expect(screen.queryByText("print('reconstruido')")).toBeNull()
  })

  it("sin artefacto (404, entrega legacy) cae al codigo de los eventos y lo rotula reconstruido", async () => {
    setupFetchMock({
      ...baseHandlers,
      "/artefacto": { ok: false, status: 404, body: () => ({}) },
      "/api/v1/audit/episodes/": () => eventosConCodigo("print('reconstruido')"),
      "/api/v1/entregas": () => ({ data: [mockEntregaSubmitted], meta: { cursor_next: null } }),
    })
    await abrirEntrega()
    await waitFor(() => {
      expect(screen.getByText("print('reconstruido')")).toBeDefined()
    })
    expect(screen.getByTestId("codigo-origen-1")).toHaveTextContent(/reconstruido/i)
  })

  it("artefacto sin entrada para ese orden: cae a los eventos", async () => {
    const otroOrden = artefacto("print('del ejercicio 2')")
    otroOrden.artefactos[0] = { ...otroOrden.artefactos[0], orden: 2 } as never
    setupFetchMock({
      ...baseHandlers,
      "/artefacto": () => otroOrden,
      "/api/v1/audit/episodes/": () => eventosConCodigo("print('reconstruido')"),
      "/api/v1/entregas": () => ({ data: [mockEntregaSubmitted], meta: { cursor_next: null } }),
    })
    await abrirEntrega()
    await waitFor(() => {
      expect(screen.getByText("print('reconstruido')")).toBeDefined()
    })
  })

  const entregaConEjercicioId = (ejercicioId: string) => ({
    ...mockEntregaSubmitted,
    ejercicio_estados: [
      {
        orden: 1,
        ejercicio_id: ejercicioId,
        completado: true,
        episode_id: "ep-0000001-abcd",
        completado_at: "2026-05-06T11:00:00Z",
      },
    ],
  })
  const art = (orden: number, ejercicio_id: string | null, codigo: string) => ({
    orden,
    ejercicio_id,
    episode_id: "ep-0000001-abcd",
    codigo,
    language: "python",
    sha256: `h${orden}`,
    created_at: "2026-05-06T12:00:00Z",
  })

  it("TP reordenada: empareja el artefacto por ejercicio_id aunque el orden no coincida", async () => {
    const reordenado = artefacto("")
    reordenado.artefactos = [
      art(1, "ej-A", "print('del ejercicio A')"),
      art(2, "ej-B", "print('del ejercicio B')"),
    ]
    setupFetchMock({
      ...baseHandlers,
      "/artefacto": () => reordenado,
      "/api/v1/audit/episodes/": () => eventosVacios,
      "/api/v1/entregas": () => ({
        data: [entregaConEjercicioId("ej-B")],
        meta: { cursor_next: null },
      }),
    })
    await abrirEntrega()
    await waitFor(() => {
      expect(screen.getByText("print('del ejercicio B')")).toBeDefined()
    })
    expect(screen.queryByText("print('del ejercicio A')")).toBeNull()
  })

  it("si el artefacto no trae ejercicio_id cae al orden", async () => {
    const legacy = artefacto("")
    legacy.artefactos = [art(1, null, "print('por orden')")]
    setupFetchMock({
      ...baseHandlers,
      "/artefacto": () => legacy,
      "/api/v1/audit/episodes/": () => eventosVacios,
      "/api/v1/entregas": () => ({
        data: [entregaConEjercicioId("ej-B")],
        meta: { cursor_next: null },
      }),
    })
    await abrirEntrega()
    await waitFor(() => {
      expect(screen.getByText("print('por orden')")).toBeDefined()
    })
  })
})
