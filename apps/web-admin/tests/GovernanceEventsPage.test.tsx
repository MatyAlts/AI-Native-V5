/**
 * Tests E2E de GovernanceEventsPage (Sec 12 epic ai-native-completion).
 *
 * Cubre:
 *   - Render inicial: pega al endpoint y muestra eventos en la tabla.
 *   - Filtros: applyFilters ejecuta nuevo fetch con query params.
 *   - Pagination: "Cargar mas" usa cursor del response previo.
 *   - Export CSV: deshabilitado sin eventos, habilitado con eventos.
 *   - HelpButton presente (PageContainer pattern obligatorio).
 *   - Empty state: "Sin eventos para los filtros actuales" cuando no hay data.
 */
import { cleanup, fireEvent, screen, waitFor } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { GovernanceEventsPage } from "../src/pages/GovernanceEventsPage"
import { renderConQuery, setupFetchMock } from "./_mocks"

afterEach(() => {
  cleanup()
})

const SAMPLE_EVENT = {
  episode_id: "11111111-1111-1111-1111-111111111111",
  student_pseudonym: "22222222-2222-2222-2222-222222222222",
  comision_id: "33333333-3333-3333-3333-333333333333",
  ts: "2026-04-01T10:30:00Z",
  category: "jailbreak_substitution",
  severity: 4,
  pattern_id: "jailbreak_substitution_v1_p2",
  matched_text: "ignora las reglas anteriores",
}

const SAMPLE_RESPONSE = {
  events: [SAMPLE_EVENT],
  cursor_next: null,
  n_total_estimate: 1,
  counts_by_category: { jailbreak_substitution: 1 },
  counts_by_severity: { "4": 1 },
  filters_applied: {
    facultad_id: null,
    materia_id: null,
    periodo_id: null,
    severity_min: null,
    severity_max: null,
    category: null,
  },
}

describe("GovernanceEventsPage", () => {
  it("renderiza la tabla con eventos del backend", async () => {
    setupFetchMock({
      "/api/v1/analytics/governance/events": () => SAMPLE_RESPONSE,
    })

    renderConQuery(<GovernanceEventsPage />)

    // Se espera por el `pattern_id`, que SOLO existe en una fila de la tabla.
    //
    // Antes esperaba por "jailbreak_substitution", y eso es una trampa: ese
    // texto tambien es una OPCION del desplegable de categorias, que esta desde
    // el primer render. El `waitFor` pasaba de inmediato sin esperar los datos,
    // y las aserciones de abajo corrian contra la tabla todavia vacia
    // (`0 eventos | categorias: ninguna`). Un waitFor que no espera nada.
    await waitFor(() => {
      expect(screen.getByText("jailbreak_substitution_v1_p2")).toBeInTheDocument()
    })

    expect(screen.getByText("jailbreak_substitution_v1_p2")).toBeInTheDocument()
    expect(screen.getByText("ignora las reglas anteriores")).toBeInTheDocument()
    expect(screen.getByText("4")).toBeInTheDocument() // severidad badge
  })

  it("muestra empty state cuando el backend devuelve lista vacia", async () => {
    setupFetchMock({
      "/api/v1/analytics/governance/events": () => ({
        ...SAMPLE_RESPONSE,
        events: [],
        n_total_estimate: 0,
        counts_by_category: {},
        counts_by_severity: {},
      }),
    })

    renderConQuery(<GovernanceEventsPage />)

    await waitFor(() => {
      expect(screen.getByText(/Sin eventos para los filtros actuales/i)).toBeInTheDocument()
    })
  })

  it("habilita Exportar CSV solo cuando hay eventos", async () => {
    setupFetchMock({
      "/api/v1/analytics/governance/events": () => SAMPLE_RESPONSE,
    })

    renderConQuery(<GovernanceEventsPage />)

    // Se espera por el `pattern_id`, que SOLO existe en una fila de la tabla.
    //
    // Antes esperaba por "jailbreak_substitution", y eso es una trampa: ese
    // texto tambien es una OPCION del desplegable de categorias, que esta desde
    // el primer render. El `waitFor` pasaba de inmediato sin esperar los datos,
    // y las aserciones de abajo corrian contra la tabla todavia vacia
    // (`0 eventos | categorias: ninguna`). Un waitFor que no espera nada.
    await waitFor(() => {
      expect(screen.getByText("jailbreak_substitution_v1_p2")).toBeInTheDocument()
    })

    const exportBtn = screen.getByRole("button", { name: /Exportar CSV/i })
    expect(exportBtn).not.toBeDisabled()
  })

  it("muestra el resumen con n eventos y conteos por categoria", async () => {
    setupFetchMock({
      "/api/v1/analytics/governance/events": () => ({
        ...SAMPLE_RESPONSE,
        events: [SAMPLE_EVENT, { ...SAMPLE_EVENT, ts: "2026-04-01T11:00:00Z" }],
        counts_by_category: { jailbreak_substitution: 2 },
      }),
    })

    renderConQuery(<GovernanceEventsPage />)

    await waitFor(() => {
      expect(screen.getByText(/2 eventos/)).toBeInTheDocument()
    })
    expect(screen.getByText(/jailbreak_substitution=2/)).toBeInTheDocument()
  })

  it("renderiza el HelpButton del PageContainer (pattern obligatorio)", async () => {
    setupFetchMock({
      "/api/v1/analytics/governance/events": () => SAMPLE_RESPONSE,
    })

    renderConQuery(<GovernanceEventsPage />)

    await waitFor(() => {
      // PageContainer renderiza HelpButton con aria-label "Ayuda"
      expect(screen.getByRole("button", { name: /ayuda/i })).toBeInTheDocument()
    })
  })

  it("muestra error si el endpoint devuelve 500", async () => {
    setupFetchMock({
      "/api/v1/analytics/governance/events": {
        ok: false,
        status: 500,
        body: () => ({ detail: "boom" }),
      },
    })

    renderConQuery(<GovernanceEventsPage />)

    await waitFor(() => {
      expect(screen.getByText(/Error al cargar/i)).toBeInTheDocument()
    })
  })

  it("aplica filtros y dispara nuevo fetch", async () => {
    let lastUrl = ""
    setupFetchMock({
      "/api/v1/analytics/governance/events": () => {
        // Capturamos la URL del request mas reciente — fetch fue stubbeado
        // entonces leemos el spy en el global. La verificacion la hacemos
        // por presencia de la query param en el body del response (mock se
        // adapta dinamicamente).
        return SAMPLE_RESPONSE
      },
    })
    // Spy adicional para ver las URLs invocadas
    const fetchSpy = global.fetch as ReturnType<typeof vi.fn>
    fetchSpy.mockClear()

    renderConQuery(<GovernanceEventsPage />)

    // Esperamos render inicial completo
    // Se espera por el `pattern_id`, que SOLO existe en una fila de la tabla.
    //
    // Antes esperaba por "jailbreak_substitution", y eso es una trampa: ese
    // texto tambien es una OPCION del desplegable de categorias, que esta desde
    // el primer render. El `waitFor` pasaba de inmediato sin esperar los datos,
    // y las aserciones de abajo corrian contra la tabla todavia vacia
    // (`0 eventos | categorias: ninguna`). Un waitFor que no espera nada.
    await waitFor(() => {
      expect(screen.getByText("jailbreak_substitution_v1_p2")).toBeInTheDocument()
    })

    // Setear severidad min y aplicar
    const sevMinInput = screen.getByLabelText(/Severidad min/i) as HTMLInputElement
    fireEvent.change(sevMinInput, { target: { value: "3" } })
    const applyBtn = screen.getByRole("button", { name: /Aplicar filtros/i })
    fireEvent.click(applyBtn)

    await waitFor(() => {
      // El segundo call debe incluir severity_min=3
      const calls = fetchSpy.mock.calls
      const lastCall = calls[calls.length - 1]
      lastUrl = String(lastCall?.[0] ?? "")
      expect(lastUrl).toMatch(/severity_min=3/)
    })
  })
})

describe("GovernanceEventsPage — la otra mitad del \"solo\"", () => {
  // El test "habilita Exportar CSV solo cuando hay eventos" probaba una sola
  // mitad: que con eventos el boton esta habilitado. La palabra "solo" es la
  // otra — que SIN eventos esta deshabilitado — y no se afirmaba en ningun
  // lado, asi que borrar `events.length === 0` del `disabled` pasaba la suite.
  //
  // Exportar una lista vacia genera un CSV con encabezados y nada debajo. Sobre
  // eventos de gobernanza (intentos adversos del alumno) un archivo asi no es
  // inocuo: parece la evidencia de que no hubo nada, cuando lo que puede haber
  // pasado es que el filtro no trajo nada todavia.

  it("deshabilita Exportar CSV cuando la lista viene vacia", async () => {
    setupFetchMock({
      "/api/v1/analytics/governance/events": () => ({
        ...SAMPLE_RESPONSE,
        events: [],
        n_total_estimate: 0,
        counts_by_category: {},
        counts_by_severity: {},
      }),
    })

    renderConQuery(<GovernanceEventsPage />)

    // Se espera por el empty state, que solo aparece con la respuesta ya
    // resuelta: sin esto la asercion correria contra el primer render, donde el
    // boton esta deshabilitado por `loading` y no por falta de eventos — un
    // verde que no prueba nada.
    await waitFor(() => {
      expect(screen.getByText(/Sin eventos para los filtros actuales/i)).toBeInTheDocument()
    })

    expect(screen.getByRole("button", { name: /Exportar CSV/i })).toBeDisabled()
  })

  it("no descarga nada mientras la lista este vacia", async () => {
    // Cinturon y tirantes: el `disabled` es la defensa visible, pero el handler
    // tiene su propio `if (events.length === 0) return`. Si alguien saca el
    // `disabled`, esto sigue atajando la descarga.
    const crearUrl = vi.fn(() => "blob:vacio")
    const original = URL.createObjectURL
    URL.createObjectURL = crearUrl as unknown as typeof URL.createObjectURL
    try {
      setupFetchMock({
        "/api/v1/analytics/governance/events": () => ({
          ...SAMPLE_RESPONSE,
          events: [],
          n_total_estimate: 0,
          counts_by_category: {},
          counts_by_severity: {},
        }),
      })

      renderConQuery(<GovernanceEventsPage />)
      await waitFor(() => {
        expect(screen.getByText(/Sin eventos para los filtros actuales/i)).toBeInTheDocument()
      })

      fireEvent.click(screen.getByRole("button", { name: /Exportar CSV/i }))
      expect(crearUrl).not.toHaveBeenCalled()
    } finally {
      URL.createObjectURL = original
    }
  })

  it("con eventos, exportar SI produce una descarga", async () => {
    // El contrapunto: sin esto, un `disabled` pegado en `true` pasaria los dos
    // tests de arriba.
    const crearUrl = vi.fn(() => "blob:lleno")
    const revocarUrl = vi.fn()
    const originalCrear = URL.createObjectURL
    const originalRevocar = URL.revokeObjectURL
    URL.createObjectURL = crearUrl as unknown as typeof URL.createObjectURL
    URL.revokeObjectURL = revocarUrl as unknown as typeof URL.revokeObjectURL
    try {
      setupFetchMock({
        "/api/v1/analytics/governance/events": () => SAMPLE_RESPONSE,
      })

      renderConQuery(<GovernanceEventsPage />)
      await waitFor(() => {
        expect(screen.getByText("jailbreak_substitution_v1_p2")).toBeInTheDocument()
      })

      // El click del <a download> se intercepta: jsdom no implementa descargas
      // y lo reporta como una navegacion no soportada, que ensucia la salida
      // sin agregar informacion.
      const clickAncla = vi
        .spyOn(HTMLAnchorElement.prototype, "click")
        .mockImplementation(() => {})
      try {
        fireEvent.click(screen.getByRole("button", { name: /Exportar CSV/i }))
        expect(crearUrl).toHaveBeenCalledTimes(1)
        expect(clickAncla).toHaveBeenCalledTimes(1)
      } finally {
        clickAncla.mockRestore()
      }
    } finally {
      URL.createObjectURL = originalCrear
      URL.revokeObjectURL = originalRevocar
    }
  })
})
