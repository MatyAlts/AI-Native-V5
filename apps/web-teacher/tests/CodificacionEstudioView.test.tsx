// Contenido en espanol SIN tildes para evitar problemas de encoding en Windows/cp1252.
/**
 * Seccion Codificacion (inter-jueces) del estudio (`src/views/estudio/CodificacionEstudioView.tsx`;
 * design D10, D13; spec estudio-codificacion y estudio-codificacion-acceso).
 *
 * Lo que se blinda:
 *   - docente sin membresia: aviso + enlace a /interrater-admin, y NINGUN pedido de
 *     datos del estudio (solo la consulta de membresias);
 *   - el enlace al piloto no aparece a miembros;
 *   - la lista viene en el orden del codificador (posicion), no en el del servidor;
 *   - con codebook vigente en borrador no hay formulario;
 *   - cerrar pide confirmacion; cancelar no manda nada; el 422 lista los faltantes;
 *   - una falla del servicio del estudio queda dentro de la seccion.
 */
import { fireEvent, screen, waitFor, within } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import type { EsquemaFormulario } from "../src/lib/estudioApi"
import { CodificacionEstudioView } from "../src/views/estudio/CodificacionEstudioView"
import { renderWithRouter, setupFetchMock } from "./_mocks"

const getToken = async () => null
const E = "/api/v1/interrater/estudios"

const ESQUEMA: EsquemaFormulario = {
  dimensiones: [
    { clave: "alfa", nombre: "Dimension Alfa", valores: ["si", "no"], cita_requerida_si: [] },
  ],
  regimenes: [
    { clave: "r1", nombre: "Reg Uno" },
    { clave: "ins", nombre: "Insuf" },
  ],
  regimen_evidencia_insuficiente: "ins",
  dimensiones_opcionales_si_regimen: [],
  notas_obligatorias_si_regimen: [],
  marca_frontera: false,
  confianza: null,
  reglas_regimen: [{ regimen: "r1", condicion: [[{ dimension: "alfa", en: ["si"] }]] }],
  regimen_por_defecto: "r1",
  regimenes_exentos: ["ins"],
}

const CODIFICADOR = [{ clave: "cibse-2027", titulo: "CIbSE 2027", rol: "codificador", cerrada: false }]

const ITEMS = [
  { item_id: "it-c", posicion: 3, estado: "sin_empezar" },
  { item_id: "it-a", posicion: 1, estado: "completa" },
  { item_id: "it-b", posicion: 2, estado: "parcial" },
]

const TRAZA = {
  traza_version: "traza_v1",
  enunciado: { tp_md: "Consigna de prueba", ejercicio_md: null },
  elementos: [
    { n: 1, tipo: "mensaje_alumno", t_seg: 3, k: 1, datos: { content: "hola tutor" } },
  ],
}

const VIGENTE_CONGELADA = {
  etiqueta: "v1",
  estado: "congelada",
  contenido_md: "# cb",
  esquema: ESQUEMA,
  contenido_sha256: "a".repeat(64),
}

function mockCodificador(extra: Record<string, unknown> = {}) {
  // `extra` va AL FINAL: con la misma clave reemplaza el valor de la base y
  // conserva su posicion (setupFetchMock elige el primer prefijo que matchea).
  setupFetchMock({
    [`${E}/mis-membresias`]: () => CODIFICADOR,
    [`${E}/cibse-2027/items/it-a/traza`]: () => TRAZA,
    [`${E}/cibse-2027/items/it-a/mi-etiqueta`]: () => ({
      respuestas: { alfa: { valor: "si", cita: "turno 1" } },
      regimen: "r1",
      regimen_regla: "r1",
      regimen_propuesto: null,
      es_frontera: false,
      confianza: null,
      notas: "",
      updated_at: "2026-11-04T10:00:00Z",
    }),
    [`${E}/cibse-2027/items`]: () => ITEMS,
    [`${E}/cibse-2027/codebook/vigente`]: () => VIGENTE_CONGELADA,
    ...extra,
  } as Parameters<typeof setupFetchMock>[0])
}

function urls(): { url: string; metodo: string }[] {
  return vi.mocked(fetch).mock.calls.map(([u, init]) => ({
    url: String(u),
    metodo: ((init as RequestInit | undefined)?.method ?? "GET").toUpperCase(),
  }))
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe("CodificacionEstudioView: docente sin membresia", () => {
  it("ve el aviso y el enlace a /interrater-admin, sin ningun pedido de datos del estudio", async () => {
    setupFetchMock({ [`${E}/mis-membresias`]: () => [] })
    renderWithRouter(<CodificacionEstudioView getToken={getToken} />)
    expect(await screen.findByText(/se usa para un estudio de codificación/)).toBeTruthy()
    const enlace = screen.getByRole("link", { name: /acuerdo del piloto/ })
    expect(enlace.getAttribute("href")).toContain("/interrater-admin")
    await new Promise((r) => setTimeout(r, 30))
    const delEstudio = urls().filter((u) => u.url.startsWith(E) && !u.url.endsWith("/mis-membresias"))
    expect(delEstudio).toEqual([])
  })
})

describe("CodificacionEstudioView: codificador", () => {
  it("no muestra el enlace al piloto a un miembro", async () => {
    mockCodificador()
    renderWithRouter(<CodificacionEstudioView getToken={getToken} />)
    await screen.findByRole("list", { name: "Ítems en tu orden" })
    expect(screen.queryByRole("link", { name: /acuerdo del piloto/ })).toBeNull()
  })

  it("lista los items en el orden del codificador, con su estado y el progreso", async () => {
    mockCodificador()
    renderWithRouter(<CodificacionEstudioView getToken={getToken} />)
    const lista = await screen.findByRole("list", { name: "Ítems en tu orden" })
    const filas = within(lista).getAllByRole("button").map((b) => b.textContent ?? "")
    expect(filas[0]).toContain("Ítem 1")
    expect(filas[1]).toContain("Ítem 2")
    expect(filas[2]).toContain("Ítem 3")
    expect(filas[0]).toContain("completa")
    expect(filas[1]).toContain("parcial")
    expect(screen.getByText(/1 de 3 completos/)).toBeTruthy()
    // El identificador opaco no se muestra como texto: alcanza la posicion.
    expect(lista.textContent).not.toContain("it-a")
  })

  it("abrir un item muestra su traza ciega y el formulario con la etiqueta propia", async () => {
    mockCodificador()
    renderWithRouter(<CodificacionEstudioView getToken={getToken} />)
    const lista = await screen.findByRole("list", { name: "Ítems en tu orden" })
    fireEvent.click(within(lista).getAllByRole("button")[0] as HTMLElement)
    expect(await screen.findByText("hola tutor")).toBeTruthy()
    const alfa = await screen.findByRole("group", { name: "Dimension Alfa" })
    await waitFor(() =>
      expect((within(alfa).getByLabelText("si") as HTMLInputElement).checked).toBe(true),
    )
  })

  it("guardar manda el PUT de la etiqueta propia del item abierto", async () => {
    mockCodificador()
    renderWithRouter(<CodificacionEstudioView getToken={getToken} />)
    const lista = await screen.findByRole("list", { name: "Ítems en tu orden" })
    fireEvent.click(within(lista).getAllByRole("button")[0] as HTMLElement)
    await screen.findByRole("group", { name: "Dimension Alfa" })
    fireEvent.click(screen.getByRole("button", { name: "Guardar" }))
    await waitFor(() =>
      expect(urls()).toContainEqual({
        url: `${E}/cibse-2027/items/it-a/mi-etiqueta`,
        metodo: "PUT",
      }),
    )
  })

  it("con el codebook vigente en borrador bloquea la codificacion y no muestra formulario", async () => {
    mockCodificador({
      [`${E}/cibse-2027/codebook/vigente`]: () => ({ ...VIGENTE_CONGELADA, estado: "borrador" }),
    })
    renderWithRouter(<CodificacionEstudioView getToken={getToken} />)
    expect(await screen.findByText(/codebook vigente todavía es un borrador/)).toBeTruthy()
    expect(screen.queryByRole("button", { name: "Guardar" })).toBeNull()
    expect(screen.queryByRole("button", { name: "Cerrar mi codificación" })).toBeNull()
  })

  it("cerrar pide confirmacion: cancelar no manda nada", async () => {
    mockCodificador()
    renderWithRouter(<CodificacionEstudioView getToken={getToken} />)
    fireEvent.click(await screen.findByRole("button", { name: "Cerrar mi codificación" }))
    fireEvent.click(await screen.findByRole("button", { name: "Cancelar" }))
    await new Promise((r) => setTimeout(r, 20))
    expect(urls().some((u) => u.url.endsWith("/mi-codificacion/cerrar"))).toBe(false)
  })

  it("cerrar confirmado manda el POST y deja la codificacion cerrada", async () => {
    mockCodificador({ [`${E}/cibse-2027/mi-codificacion/cerrar`]: () => ({ cerrada: true }) })
    renderWithRouter(<CodificacionEstudioView getToken={getToken} />)
    fireEvent.click(await screen.findByRole("button", { name: "Cerrar mi codificación" }))
    fireEvent.click(await screen.findByRole("button", { name: "Confirmar" }))
    await waitFor(() =>
      expect(urls()).toContainEqual({ url: `${E}/cibse-2027/mi-codificacion/cerrar`, metodo: "POST" }),
    )
    expect(await screen.findByText(/Tu codificación está cerrada/)).toBeTruthy()
  })

  it("cierre rechazado (422): lista cuantos items faltan y cuales", async () => {
    mockCodificador({
      [`${E}/cibse-2027/mi-codificacion/cerrar`]: {
        ok: false,
        status: 422,
        body: () => ({
          detail: {
            codigo: "incompleta",
            faltan: 2,
            faltantes: [
              { item_id: "it-b", posicion: 2, motivos: ["regimen", "dimension:alfa"] },
              { item_id: "it-c", posicion: 3, motivos: ["sin_etiqueta"] },
            ],
          },
        }),
      },
    })
    renderWithRouter(<CodificacionEstudioView getToken={getToken} />)
    fireEvent.click(await screen.findByRole("button", { name: "Cerrar mi codificación" }))
    fireEvent.click(await screen.findByRole("button", { name: "Confirmar" }))
    const aviso = await screen.findByRole("alert")
    expect(aviso.textContent).toContain("Faltan 2 ítems")
    // Los motivos llegan como codigos estables del backend (faltantes_cierre):
    // se muestran con los nombres del esquema, nunca el codigo crudo.
    expect(aviso.textContent).toContain("Ítem 2: régimen, valor de Dimension Alfa")
    expect(aviso.textContent).toContain("Ítem 3: sin etiqueta")
    expect(aviso.textContent).not.toContain("dimension:alfa")
    expect(aviso.textContent).not.toContain("sin_etiqueta")
  })

  // verify-1, F4: sin muestra cargada el panel no dice "0 de 0" ni "Faltan 0".
  it("sin muestra cargada: estado vacio claro y sin boton de cierre", async () => {
    mockCodificador({ [`${E}/cibse-2027/items`]: () => [] })
    renderWithRouter(<CodificacionEstudioView getToken={getToken} />)
    expect(await screen.findByText(/muestra del estudio todavía no se cargó/)).toBeTruthy()
    expect(screen.queryByText(/0 de 0/)).toBeNull()
    expect(screen.queryByRole("button", { name: "Cerrar mi codificación" })).toBeNull()
  })

  it("cierre rechazado con 409 sin_muestra: mensaje claro, nunca 'Faltan 0'", async () => {
    mockCodificador({
      [`${E}/cibse-2027/mi-codificacion/cerrar`]: {
        ok: false,
        status: 409,
        body: () => ({ detail: "sin_muestra" }),
      },
    })
    renderWithRouter(<CodificacionEstudioView getToken={getToken} />)
    fireEvent.click(await screen.findByRole("button", { name: "Cerrar mi codificación" }))
    fireEvent.click(await screen.findByRole("button", { name: "Confirmar" }))
    const aviso = await screen.findByRole("alert")
    expect(aviso.textContent).toMatch(/muestra del estudio todavía no se cargó/)
    expect(aviso.textContent).not.toMatch(/Faltan 0/)
  })

  it("un 422 de cierre sin faltantes no se muestra como 'Faltan 0'", async () => {
    mockCodificador({
      [`${E}/cibse-2027/mi-codificacion/cerrar`]: {
        ok: false,
        status: 422,
        body: () => ({ detail: { codigo: "incompleta", faltan: 0, faltantes: [] } }),
      },
    })
    renderWithRouter(<CodificacionEstudioView getToken={getToken} />)
    fireEvent.click(await screen.findByRole("button", { name: "Cerrar mi codificación" }))
    fireEvent.click(await screen.findByRole("button", { name: "Confirmar" }))
    const aviso = await screen.findByRole("alert")
    expect(aviso.textContent).not.toMatch(/Faltan 0/)
  })

  it("membresia ya cerrada: formulario deshabilitado y sin boton de cierre", async () => {
    mockCodificador({
      [`${E}/mis-membresias`]: () => [{ ...CODIFICADOR[0], cerrada: true }],
    })
    renderWithRouter(<CodificacionEstudioView getToken={getToken} />)
    const lista = await screen.findByRole("list", { name: "Ítems en tu orden" })
    expect(screen.getByText(/Tu codificación está cerrada/)).toBeTruthy()
    expect(screen.queryByRole("button", { name: "Cerrar mi codificación" })).toBeNull()
    fireEvent.click(within(lista).getAllByRole("button")[0] as HTMLElement)
    const guardar = await screen.findByRole("button", { name: "Guardar" })
    expect((guardar as HTMLButtonElement).disabled).toBe(true)
  })
})

describe("CodificacionEstudioView: contrato real del backend", () => {
  it("item nunca guardado: el backend devuelve 200 con la etiqueta vacia y el formulario arranca vacio", async () => {
    mockCodificador({
      [`${E}/cibse-2027/items/it-a/mi-etiqueta`]: () => ({
        respuestas: {},
        regimen: null,
        regimen_regla: null,
        regimen_propuesto: null,
        disiente_de_regla: false,
        es_frontera: false,
        confianza: null,
        notas: null,
        updated_at: null,
      }),
    })
    renderWithRouter(<CodificacionEstudioView getToken={getToken} />)
    const lista = await screen.findByRole("list", { name: "Ítems en tu orden" })
    fireEvent.click(within(lista).getAllByRole("button")[0] as HTMLElement)
    const alfa = await screen.findByRole("group", { name: "Dimension Alfa" })
    expect((within(alfa).getByLabelText("si") as HTMLInputElement).checked).toBe(false)
    expect((screen.getByLabelText("Notas") as HTMLTextAreaElement).value).toBe("")
  })

  it("un 404 de mi-etiqueta es un error (item inexistente), no un item vacio", async () => {
    mockCodificador({
      [`${E}/cibse-2027/items/it-a/mi-etiqueta`]: {
        ok: false,
        status: 404,
        body: () => ({ detail: "Ítem inexistente" }),
      },
    })
    renderWithRouter(<CodificacionEstudioView getToken={getToken} />)
    const lista = await screen.findByRole("list", { name: "Ítems en tu orden" })
    fireEvent.click(within(lista).getAllByRole("button")[0] as HTMLElement)
    expect(await screen.findByText(/Ítem inexistente/)).toBeTruthy()
    expect(screen.queryByRole("button", { name: "Guardar" })).toBeNull()
  })

  it("esquema minimo (solo claves obligatorias del meta-esquema) se renderiza", async () => {
    mockCodificador({
      [`${E}/cibse-2027/codebook/vigente`]: () => ({
        ...VIGENTE_CONGELADA,
        esquema: {
          dimensiones: ESQUEMA.dimensiones,
          regimenes: ESQUEMA.regimenes,
          regimen_evidencia_insuficiente: "ins",
        },
      }),
    })
    renderWithRouter(<CodificacionEstudioView getToken={getToken} />)
    const lista = await screen.findByRole("list", { name: "Ítems en tu orden" })
    fireEvent.click(within(lista).getAllByRole("button")[0] as HTMLElement)
    expect(await screen.findByRole("group", { name: "Dimension Alfa" })).toBeTruthy()
    // Sin reglas: el codificador elige el regimen; sin confianza declarada, no hay selector.
    expect(screen.getByRole("radio", { name: "Reg Uno" })).toBeTruthy()
    expect(screen.queryByLabelText("Confianza")).toBeNull()
  })
})

describe("CodificacionEstudioView: errores y roles", () => {
  it("si mis-membresias falla, el error queda dentro de la seccion", async () => {
    setupFetchMock({
      [`${E}/mis-membresias`]: { ok: false, status: 502, body: () => ({ detail: "x" }) },
    })
    renderWithRouter(<CodificacionEstudioView getToken={getToken} />)
    expect(await screen.findByRole("alert")).toHaveTextContent(/servicio del estudio no respondió/)
    expect(screen.queryByRole("link", { name: /acuerdo del piloto/ })).toBeNull()
  })

  it("investigador: ve la administracion del estudio y no la lista de codificador", async () => {
    setupFetchMock({
      [`${E}/mis-membresias`]: () => [
        { clave: "cibse-2027", titulo: "CIbSE 2027", rol: "investigador", cerrada: false },
      ],
    })
    renderWithRouter(<CodificacionEstudioView getToken={getToken} />)
    expect(await screen.findByRole("heading", { name: "Administración del estudio" })).toBeTruthy()
    expect(screen.queryByRole("list", { name: "Ítems en tu orden" })).toBeNull()
  })
})
