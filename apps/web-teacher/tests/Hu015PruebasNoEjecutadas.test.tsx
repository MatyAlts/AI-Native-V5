/**
 * Aceptacion HU-015, tramo 1, C02 (orquestador, antes de construir; el
 * constructor no la modifica). Criterios aprobados por Juani el 22/11/2026.
 *
 * Si las pruebas no se ejecutaron (`tests_snapshot.ejecutado === false`), el
 * docente lo ve antes de usar la nota sugerida. Contrato:
 * data-testid="correccion-ia-sin-ejecutar", con el texto "Pruebas no ejecutadas".
 */
import { screen, waitFor } from "@testing-library/react"
import { afterEach, describe, expect, test, vi } from "vitest"
import { CorreccionIAPanel } from "../src/components/CorreccionIAPanel"
import type { CorreccionIA } from "../src/lib/api"
import { renderWithRouter, setupFetchMock } from "./_mocks"

const ENTREGA = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
const getToken = async () => null

afterEach(() => {
  vi.unstubAllGlobals()
})

function correccion(tests_snapshot: CorreccionIA["tests_snapshot"]): CorreccionIA {
  return {
    id: "11111111-1111-1111-1111-111111111111",
    entrega_id: ENTREGA,
    orden: 1,
    estado: "done",
    rubrica_id: "r1",
    nota_100: 60,
    desglose: [],
    tests_snapshot,
    artefacto_sha256: "s",
    error_code: null,
    error_detail: null,
    es_infraestructura: false,
    external_correccion_id: null,
    tiene_pdf: false,
    created_at: "2026-11-22T10:00:00Z",
    finished_at: "2026-11-22T10:02:00Z",
  } as CorreccionIA
}

function render(c: CorreccionIA) {
  setupFetchMock({ "/correccion-ia": () => ({ correcciones: [c] }) })
  renderWithRouter(<CorreccionIAPanel entregaId={ENTREGA} orden={1} getToken={getToken} />)
}

describe("HU-015 · pruebas no ejecutadas", () => {
  test("C02: si no se ejecutaron, el docente ve 'Pruebas no ejecutadas'", async () => {
    render(correccion({ compila: true, ejecutado: false, total: 0, passed: 0, casos: [] }))
    const aviso = await screen.findByTestId("correccion-ia-sin-ejecutar")
    expect(aviso.textContent).toMatch(/Pruebas no ejecutadas/)
    expect(screen.queryByText(/0 de \d/)).toBeNull()
  })

  test("C02: con pruebas ejecutadas no aparece el aviso", async () => {
    render(correccion({ compila: true, ejecutado: true, total: 2, passed: 2, casos: [] }))
    await waitFor(() => expect(screen.getByText(/60/)).toBeDefined())
    expect(screen.queryByTestId("correccion-ia-sin-ejecutar")).toBeNull()
  })

  test("C02: una correccion vieja sin el campo no muestra el aviso", async () => {
    render(correccion({ compila: true, total: 2, passed: 1 }))
    await waitFor(() => expect(screen.getByText(/60/)).toBeDefined())
    expect(screen.queryByTestId("correccion-ia-sin-ejecutar")).toBeNull()
  })
})
