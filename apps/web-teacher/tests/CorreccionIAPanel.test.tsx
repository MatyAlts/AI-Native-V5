/**
 * Tests del panel de correccion asistida.
 *
 * Lo que fijan:
 *  - Que un fallo de INFRAESTRUCTURA y un RECHAZO se vean distinto. Es la
 *    distincion que evita reintentar durante dos dias un error que nunca se
 *    va a destrabar solo.
 *  - Que el preview no gaste nada y muestre con que rubrica se va a corregir.
 *  - Que el resultado se presente como SUGERENCIA, no como nota puesta.
 */
import { act, screen, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest"
import { CorreccionIAPanel } from "../src/components/CorreccionIAPanel"
import type { CorreccionIA } from "../src/lib/api"
import { renderWithRouter, setupFetchMock } from "./_mocks"

const ENTREGA = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
const getToken = async () => null
// El mismo valor que el componente. Con timers falsos, esperar 3s de verdad por
// cada vuelta convertiria estos tests en diez segundos de reloj.
const POLL_MS = 3000

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true })
})
afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

function correccion(over: Partial<CorreccionIA> = {}): CorreccionIA {
  return {
    id: "11111111-1111-1111-1111-111111111111",
    entrega_id: ENTREGA,
    orden: 1,
    estado: "done",
    rubrica_id: "r1",
    nota_100: 87,
    desglose: [],
    tests_snapshot: {},
    artefacto_sha256: "s",
    error_code: null,
    error_detail: null,
    es_infraestructura: false,
    external_correccion_id: null,
    tiene_pdf: false,
    created_at: "2026-08-18T10:00:00Z",
    finished_at: "2026-08-18T10:02:00Z",
    ...over,
  }
}

function render(correcciones: CorreccionIA[]) {
  setupFetchMock({ "/correccion-ia": () => ({ correcciones }) })
  renderWithRouter(<CorreccionIAPanel entregaId={ENTREGA} orden={1} getToken={getToken} />)
}

describe("CorreccionIAPanel", () => {
  test("sin correccion ofrece pedirla", async () => {
    render([])
    await waitFor(() => {
      expect(screen.getByTestId("correccion-ia-pedir")).toBeInTheDocument()
    })
  })

  test("un fallo de infraestructura es ambar y ofrece reintentar", async () => {
    render([
      correccion({
        estado: "error",
        nota_100: null,
        error_code: "GEMINI_OVERLOADED",
        error_detail: "El motor estaba saturado",
        es_infraestructura: true,
      }),
    ])
    await waitFor(() => {
      expect(screen.getByTestId("correccion-ia-fallo-infra")).toBeInTheDocument()
    })
    expect(screen.getByTestId("correccion-ia-reintentar")).toBeInTheDocument()
    expect(screen.queryByTestId("correccion-ia-rechazo")).not.toBeInTheDocument()
  })

  test("un rechazo es rojo y NO ofrece reintentar", async () => {
    render([
      correccion({
        estado: "error",
        nota_100: null,
        error_code: "RUBRICA_INEXISTENTE",
        error_detail: "La rubrica no existe",
        es_infraestructura: false,
      }),
    ])
    await waitFor(() => {
      expect(screen.getByTestId("correccion-ia-rechazo")).toBeInTheDocument()
    })
    expect(screen.queryByTestId("correccion-ia-reintentar")).not.toBeInTheDocument()
  })

  test("un fallo nunca muestra una nota", async () => {
    render([
      correccion({
        estado: "error",
        nota_100: null,
        error_code: "TIMEOUT",
        es_infraestructura: true,
      }),
    ])
    await waitFor(() => {
      expect(screen.getByTestId("correccion-ia-fallo-infra")).toBeInTheDocument()
    })
    expect(screen.queryByTestId("correccion-ia-resultado")).not.toBeInTheDocument()
    expect(screen.queryByText(/\/100/)).not.toBeInTheDocument()
  })

  test("el resultado se presenta como sugerencia, no como nota puesta", async () => {
    render([correccion()])
    await waitFor(() => {
      expect(screen.getByTestId("correccion-ia-resultado")).toBeInTheDocument()
    })
    expect(screen.getByText(/87/)).toBeInTheDocument()
    expect(screen.getByText(/sugerencia/i)).toBeInTheDocument()
    expect(screen.getByText(/no se guarda/i)).toBeInTheDocument()
  })

  test("avisa cuando la nota salio de codigo que no compila", async () => {
    // Desde el 19/08 ese codigo se manda igual a corregir. La nota entonces
    // sale de LEERLO, no de ejecutarlo — y sin este aviso el docente aprieta
    // "Usar como base" sobre un numero que ningun test respalda.
    render([
      correccion({
        tests_snapshot: {
          compila: false,
          error_compilacion: "Main.java:3: error: ';' expected",
          total: 6,
          passed: 0,
        },
      }),
    ])
    await waitFor(() => {
      expect(screen.getByTestId("correccion-ia-no-compila")).toBeInTheDocument()
    })
    expect(screen.getByText(/no compila/i)).toBeInTheDocument()
    expect(screen.getByText(/';' expected/)).toBeInTheDocument()
  })

  test("cuando compila no muestra el aviso", async () => {
    // El aviso tiene que ser excepcional: si apareciera siempre, se vuelve
    // ruido y deja de leerse justo cuando importa.
    render([correccion({ tests_snapshot: { compila: true, total: 6, passed: 6 } })])
    await waitFor(() => {
      expect(screen.getByTestId("correccion-ia-resultado")).toBeInTheDocument()
    })
    expect(screen.queryByTestId("correccion-ia-no-compila")).not.toBeInTheDocument()
  })

  test("mientras corre avisa que esta en curso", async () => {
    render([correccion({ estado: "running", nota_100: null })])
    await waitFor(() => {
      expect(screen.getByTestId("correccion-ia-en-curso")).toBeInTheDocument()
    })
  })
})

describe("el PDF de devolucion", () => {
  test("ofrece bajarlo cuando existe", async () => {
    render([correccion({ tiene_pdf: true })])
    await waitFor(() => {
      expect(screen.getByTestId("correccion-ia-pdf")).toBeInTheDocument()
    })
  })

  test("no lo ofrece cuando no hay", async () => {
    render([correccion({ tiene_pdf: false })])
    await waitFor(() => {
      expect(screen.getByTestId("correccion-ia-resultado")).toBeInTheDocument()
    })
    expect(screen.queryByTestId("correccion-ia-pdf")).not.toBeInTheDocument()
  })
})

describe("«en cola» y «corrigiendo» no son lo mismo", () => {
  /**
   * Mostrarlos con el mismo cartel costo dos dias de diagnostico en produccion
   * (2026-09-03). `pending` significa que el trabajo TODAVIA NO ARRANCO: esta
   * esperando un cupo del semaforo, o murio antes de empezar y su fila quedo
   * huerfana. `running` significa que esta trabajando de verdad.
   *
   * Con un solo cartel, "hace cola" y "corrige" eran indistinguibles — y
   * tambien lo era "esto se rompio hace diez minutos y nadie te lo dijo".
   *
   * Verificado por reversion colapsando los dos estados a un solo texto:
   * colapsando a "Corrigiendo..." cae el primero, colapsando al otro cae el
   * segundo. Uno por reversion, no los dos juntos.
   */
  test("pending dice que esta esperando turno, no que esta corrigiendo", async () => {
    render([correccion({ estado: "pending", nota_100: null, finished_at: null })])

    const cartel = await screen.findByTestId("correccion-ia-en-curso")
    expect(cartel).toHaveTextContent(/en cola/i)
    expect(cartel).not.toHaveTextContent(/Corrigiendo/i)
  })

  test("running si dice que esta corrigiendo", async () => {
    render([correccion({ estado: "running", nota_100: null, finished_at: null })])

    const cartel = await screen.findByTestId("correccion-ia-en-curso")
    expect(cartel).toHaveTextContent(/Corrigiendo/i)
    expect(cartel).not.toHaveTextContent(/en cola/i)
  })
})

describe("el poll no puede morirse en silencio", () => {
  /**
   * El `catch` del poll no hacia nada. Si el GET de estado fallaba, el panel se
   * quedaba con el estado viejo y seguia mostrando "Corrigiendo..." — una
   * correccion podia haber cerrado con error diez minutos antes y el docente
   * miraba una pantalla que le mentia.
   *
   * Y hay una segunda mitad, mas sutil, que es la que rompio el primer intento
   * de arreglo: el poll se sostiene porque cada tick exitoso cambia
   * `correccion`, y ESO reagenda el effect. En el camino de ERROR no se toca
   * `correccion`, asi que si el contador de fallos no esta en las deps, ninguna
   * dep cambia: el effect no vuelve a correr, no se agenda otro timer, y **el
   * poll muere en el primer fallo**. El contador queda clavado en 1 y el cartel
   * (que pide 3) nunca aparece — codigo muerto con cobertura en verde.
   *
   * Por eso el primer test cuenta REQUESTS y no mira el DOM: es lo unico que
   * distingue "el poll sigue vivo" de "el poll murio calladito".
   *
   * Verificado por reversion sacando `fallosDeConsulta` de las deps del effect:
   * los dos caen en rojo.
   */
  const EN_CURSO = correccion({ estado: "running", nota_100: null, finished_at: null })

  function conElDetalleCaido(): { detalles: () => number } {
    let detalles = 0
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string | URL | Request) => {
        const u = typeof url === "string" ? url : url.toString()
        // El detalle —el que poletea— falla SIEMPRE.
        if (/\/correccion-ia\/[0-9a-f-]+/.test(u)) {
          detalles += 1
          return Promise.reject(new Error("sin contacto"))
        }
        // El listado inicial anda: hace falta para que el panel entre en el
        // estado "en curso" y arranque a poletear.
        if (u.includes("/correccion-ia")) {
          return Promise.resolve({
            ok: true,
            status: 200,
            json: () => Promise.resolve({ correcciones: [EN_CURSO] }),
          } as Response)
        }
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve({ data: [], meta: { cursor_next: null } }),
        } as Response)
      }),
    )
    renderWithRouter(<CorreccionIAPanel entregaId={ENTREGA} orden={1} getToken={getToken} />)
    return { detalles: () => detalles }
  }

  test("sigue reintentando despues de un fallo, no se muere en el primero", async () => {
    const { detalles } = conElDetalleCaido()
    await screen.findByTestId("correccion-ia-en-curso")

    // Reloj de sobra para varias vueltas, contando el backoff (3s, 6s, 9s,
    // 12s). Con el poll vivo se acumulan; con el poll muerto el contador se
    // queda en 1 para siempre.
    for (let i = 0; i < 6; i++) {
      await act(async () => {
        await vi.advanceTimersByTimeAsync(POLL_MS * 5)
      })
    }

    expect(detalles()).toBeGreaterThanOrEqual(3)
  })

  test("a partir del tercer fallo avisa que lo que se ve puede estar viejo", async () => {
    conElDetalleCaido()
    await screen.findByTestId("correccion-ia-en-curso")

    expect(screen.queryByTestId("correccion-ia-sin-contacto")).not.toBeInTheDocument()

    for (let i = 0; i < 6; i++) {
      await act(async () => {
        await vi.advanceTimersByTimeAsync(POLL_MS * 5)
      })
    }

    expect(screen.getByTestId("correccion-ia-sin-contacto")).toBeInTheDocument()
  })
})
