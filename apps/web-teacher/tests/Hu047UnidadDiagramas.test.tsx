/**
 * Aceptacion HU-047 (orquestador, antes de construir; el constructor no la
 * modifica). La Unidad 1 del Preuniversitario 2027 son diagramas de flujo y
 * prueba de escritorio: sus ejercicios llegan con unidad_tematica "diagramas",
 * pero el panel docente tiene listas fijas de unidades y esa no esta. El
 * backend acepta texto libre (migracion 20260611), asi que el cambio es del
 * panel.
 *
 * C01  En una comision de Programacion 1, "Diagramas de flujo" (valor
 *      "diagramas") es la primera unidad de la lista, antes de Secuenciales.
 * C02  Se puede elegir al crear un ejercicio, se filtra en el banco (el pedido
 *      a la API lleva unidad_tematica=diagramas) y un ejercicio de esa unidad
 *      muestra "Diagramas de flujo" en la tabla, no el valor crudo.
 * C03  Una materia "Preuniversitario ..." usa la lista de Programacion 1, sin
 *      ninguna unidad de POO. Hoy su nombre no matchea ni 1 ni 2 y cae en la
 *      union de las dos listas.
 * N01  Programacion 2 queda igual: sus 8 unidades de POO, en el mismo orden, y
 *      sin "diagramas".
 *
 * Contrato: el filtro del banco es el <select> cuya primera opcion es "Todas
 * las unidades"; el del formulario tiene id "ejercicio-unidad-tematica".
 */
import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { EjerciciosView } from "../src/views/EjerciciosView"
import { renderWithRouter, setupFetchMock } from "./_mocks"

const COM = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
const MAT = "99999999-9999-9999-9999-999999999999"

const PROG1 = [
  "diagramas",
  "secuenciales",
  "condicionales",
  "repetitivas",
  "mixtos",
  "funciones",
  "manejo_errores",
  "manejo_archivos",
  "estructura_datos",
  "recursividad",
]
const PROG2 = [
  "poo",
  "poo_avanzada",
  "relaciones_uml",
  "colecciones",
  "herencia_polimorfismo",
  "interfaces_excepciones",
  "genericos",
  "bases_datos",
]

function ejercicio(id: string, titulo: string, unidad: string) {
  return {
    id,
    tenant_id: "t",
    titulo,
    enunciado_md: "# Consigna",
    inicial_codigo: null,
    materia_id: MAT,
    unidad_tematica: unidad,
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

const URLS: string[] = []

async function montar(materiaNombre: string) {
  URLS.length = 0
  setupFetchMock({
    "/api/v1/comisiones/mis": () => ({
      data: [{ id: COM, materia_id: MAT, materia_nombre: materiaNombre }],
      meta: { cursor_next: null },
    }),
    "/api/v1/ejercicios": () => ({
      data: [
        ejercicio("11111111-1111-1111-1111-111111111111", "Seguir el diagrama", "diagramas"),
        ejercicio("22222222-2222-2222-2222-222222222222", "Par o impar", "condicionales"),
      ],
      meta: { cursor_next: null },
    }),
  })
  const fetchMock = globalThis.fetch as unknown as ReturnType<typeof vi.fn>
  const original = fetchMock.getMockImplementation()!
  fetchMock.mockImplementation((url: string | URL | Request) => {
    URLS.push(typeof url === "string" ? url : url.toString())
    return original(url)
  })
  renderWithRouter(<EjerciciosView comisionId={COM} getToken={async () => "tok"} />)
  // Guarda contra la prueba vacia: el banco cargo antes de mirar las listas.
  await screen.findByRole("button", { name: "Par o impar" }, { timeout: 4000 })
}

function filtroUnidad(): HTMLSelectElement {
  const s = screen
    .getAllByRole("combobox")
    .find((el) => (el as HTMLSelectElement).options[0]?.textContent === "Todas las unidades")
  expect(s, "no esta el filtro de unidades del banco").toBeTruthy()
  return s as HTMLSelectElement
}

async function valoresDelFiltro(): Promise<string[]> {
  // La lista depende de la materia, que se resuelve async: esperar a que la
  // lista deje de ser la union (o a que tenga diagramas) evita leerla a medias.
  let vals: string[] = []
  await waitFor(() => {
    vals = Array.from(filtroUnidad().options)
      .map((o) => o.value)
      .filter((v) => v !== "")
    expect(vals.length).toBeGreaterThan(0)
    expect(vals.length).toBeLessThan(PROG1.length + PROG2.length)
  })
  return vals
}

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

describe("HU-047 · unidad tematica Diagramas de flujo", () => {
  it("C01: en Programacion 1, Diagramas de flujo es la primera unidad", async () => {
    await montar("Programacion 1")
    const vals = await valoresDelFiltro()
    expect(vals).toEqual(PROG1)
    const opt = Array.from(filtroUnidad().options).find((o) => o.value === "diagramas")!
    expect(opt.textContent).toBe("Diagramas de flujo")
  })

  it("C02: se filtra en el banco y la tabla muestra la etiqueta", async () => {
    await montar("Programacion 1")
    await valoresDelFiltro()
    const fila = screen.getByRole("button", { name: "Seguir el diagrama" }).closest("tr")!
    expect(within(fila).getByText("Diagramas de flujo")).toBeTruthy()
    fireEvent.change(filtroUnidad(), { target: { value: "diagramas" } })
    await waitFor(() =>
      expect(
        URLS.some((u) => u.includes("/api/v1/ejercicios") && u.includes("unidad_tematica=diagramas")),
      ).toBe(true),
    )
  })

  it("C02: se elige al crear un ejercicio", async () => {
    await montar("Programacion 1")
    await valoresDelFiltro()
    fireEvent.click(screen.getByRole("button", { name: /Crear manual/ }))
    const sel = (await screen.findByLabelText("Unidad tematica")) as HTMLSelectElement
    expect(sel.id).toBe("ejercicio-unidad-tematica")
    const vals = Array.from(sel.options).map((o) => o.value)
    expect(vals[0]).toBe("diagramas")
    fireEvent.change(sel, { target: { value: "diagramas" } })
    expect(sel.value).toBe("diagramas")
    expect(sel.selectedOptions[0]?.textContent).toBe("Diagramas de flujo")
  })

  for (const nombre of ["Preuniversitario 2027", "Preuniversitario de Programación"]) {
    it(`C03: "${nombre}" usa la lista de Programacion 1 sin POO`, async () => {
      await montar(nombre)
      const vals = await valoresDelFiltro()
      expect(vals).toEqual(PROG1)
      for (const k of PROG2) expect(vals).not.toContain(k)
    })
  }

  it("N01: Programacion 2 queda igual y sin diagramas", async () => {
    await montar("Programacion 2")
    const vals = await valoresDelFiltro()
    expect(vals).toEqual(PROG2)
  })
})
