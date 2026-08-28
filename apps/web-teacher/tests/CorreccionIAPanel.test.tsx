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
import { screen, waitFor } from "@testing-library/react"
import { describe, expect, test } from "vitest"
import { CorreccionIAPanel } from "../src/components/CorreccionIAPanel"
import type { CorreccionIA } from "../src/lib/api"
import { renderWithRouter, setupFetchMock } from "./_mocks"

const ENTREGA = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
const getToken = async () => null

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
