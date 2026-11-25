/**
 * Aceptacion HU-043 (orquestador, antes de construir; el constructor no la
 * modifica). Hallazgo de la prueba en produccion del 25/11: en el Banco de
 * ejercicios, buscar "rectángulo" no encontro "Área y perímetro de un
 * rectángulo"; "Par o impar" si.
 *
 * Donde vive el filtro: en el CLIENTE. `EjerciciosView` filtra en un `useMemo`
 * (`visibles`) lo que ya trajo `GET /api/v1/ejercicios`; el endpoint del
 * academic-service no recibe ningun parametro de texto (solo filtros de
 * igualdad). Por eso la prueba es de la vista y no de pytest.
 *
 * C03  El buscador del banco ignora tildes y mayusculas: "rectangulo",
 *      "RECTÁNGULO" y "rectángulo" encuentran "Área y perímetro de un
 *      rectángulo". Tambien si el titulo llego guardado en Unicode
 *      descompuesto (NFD: la "a" y la tilde como dos caracteres, tipico de
 *      texto pegado desde macOS o de algunos JSON importados), que es una
 *      causa posible de que en produccion fallara hasta con la tilde puesta.
 * N02  Una busqueda que no coincide sigue sin resultados (el arreglo no puede
 *      ser "mostrar todo"), y la busqueda sigue filtrando: con "rectangulo" no
 *      aparece "Par o impar".
 *
 * Contrato: el input con aria-label "Buscar ejercicios"; cada ejercicio
 * visible es un boton con su titulo en la tabla; sin coincidencias aparece el
 * cartel "Ningun ejercicio coincide con ...".
 */
import { cleanup, fireEvent, screen, waitFor } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { EjerciciosView } from "../src/views/EjerciciosView"
import { renderWithRouter, setupFetchMock } from "./_mocks"

const COM = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
const MAT = "99999999-9999-9999-9999-999999999999"
const RECT = "Área y perímetro de un rectángulo"
const PAR = "Par o impar"

function ejercicio(id: string, titulo: string, enunciado: string) {
  return {
    id,
    tenant_id: "t",
    titulo,
    enunciado_md: enunciado,
    inicial_codigo: null,
    materia_id: MAT,
    unidad_tematica: "secuenciales",
    dificultad: null,
    language: "pseint",
    prerequisitos: { sintacticos: [], conceptuales: [] },
    test_cases: [],
    rubrica: null,
    tutor_rules: null,
    banco_preguntas: null,
    misconceptions: [],
    respuesta_pista: [],
    heuristica_cierre: null,
    anti_patrones: [],
    created_by: "u",
    created_via_ai: false,
    created_at: "2026-11-20T10:00:00Z",
    deleted_at: null,
  }
}

async function montar(tituloRect: string) {
  setupFetchMock({
    "/api/v1/comisiones/mis": () => ({
      data: [{ id: COM, materia_id: MAT, materia_nombre: "Programacion 1" }],
      meta: { cursor_next: null },
    }),
    "/api/v1/ejercicios": () => ({
      data: [
        // Enunciados sin la palabra buscada: el match tiene que venir del titulo.
        ejercicio("11111111-1111-1111-1111-111111111111", tituloRect, "Calcula con base y altura."),
        ejercicio("22222222-2222-2222-2222-222222222222", PAR, "Decidi si un numero es par."),
      ],
      meta: { cursor_next: null },
    }),
  })
  renderWithRouter(<EjerciciosView comisionId={COM} getToken={async () => "tok"} />)
  // Guarda contra la prueba vacia: los dos ejercicios estan en la tabla antes de buscar.
  await screen.findByRole("button", { name: PAR }, { timeout: 4000 })
  expect(screen.getByRole("button", { name: tituloRect })).toBeTruthy()
}

function buscar(texto: string) {
  fireEvent.change(screen.getByLabelText("Buscar ejercicios"), { target: { value: texto } })
}

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

describe("HU-043 · el buscador del banco ignora tildes y mayusculas", () => {
  for (const termino of ["rectangulo", "RECTÁNGULO", "rectángulo", "area y perimetro"]) {
    it(`C03: "${termino}" encuentra "${RECT}" y no "${PAR}"`, async () => {
      await montar(RECT)
      buscar(termino)
      await waitFor(() => expect(screen.queryByRole("button", { name: PAR })).toBeNull())
      expect(screen.queryByRole("button", { name: RECT })).not.toBeNull()
      expect(screen.queryByText(/Ningun ejercicio coincide/)).toBeNull()
    })
  }

  it("C03: con el titulo guardado en NFD, 'rectángulo' (NFC) lo encuentra igual", async () => {
    const nfd = RECT.normalize("NFD")
    expect(nfd).not.toBe(RECT) // la fixture de verdad esta descompuesta
    await montar(nfd)
    buscar("rectángulo".normalize("NFC"))
    await waitFor(() => expect(screen.queryByRole("button", { name: PAR })).toBeNull())
    expect(screen.queryByRole("button", { name: nfd })).not.toBeNull()
  })

  it("N02: una busqueda que no coincide sigue sin resultados", async () => {
    await montar(RECT)
    buscar("triangulo")
    expect(await screen.findByText(/Ningun ejercicio coincide/)).toBeTruthy()
    expect(screen.queryByRole("button", { name: RECT })).toBeNull()
    expect(screen.queryByRole("button", { name: PAR })).toBeNull()
  })
})
