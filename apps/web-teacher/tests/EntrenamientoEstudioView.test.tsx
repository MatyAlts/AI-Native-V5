// Contenido en espanol SIN tildes para evitar problemas de encoding en Windows/cp1252.
/**
 * Entrenamiento-Recalibracion del estudio (`src/views/estudio/EntrenamientoEstudioView.tsx`;
 * design D8, D11, D13; specs codebook-versionado y entrenamiento-calibracion).
 *
 * Lo que se blinda:
 *   - el codebook vigente se lee renderizado, con marca visible si es borrador;
 *   - estados vacios explicitos (sin codebook, sin anclas);
 *   - los ejemplos muestran traza, respuesta esperada y explicacion;
 *   - la practica NO muestra la respuesta esperada antes de responder; despues,
 *     la devolucion compara el regimen derivado por la regla con el esperado;
 *   - docente sin membresia: aviso y enlace al piloto, nada del estudio.
 */
import { fireEvent, screen, waitFor, within } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import type { EsquemaFormulario } from "../src/lib/estudioApi"
import { EntrenamientoEstudioView } from "../src/views/estudio/EntrenamientoEstudioView"
import { renderWithRouter, setupFetchMock } from "./_mocks"

const getToken = async () => null
const E = "/api/v1/interrater/estudios"

const ESQUEMA: EsquemaFormulario = {
  dimensiones: [
    { clave: "alfa", nombre: "Dimension Alfa", valores: ["si", "no"], cita_requerida_si: [] },
  ],
  regimenes: [
    { clave: "r1", nombre: "Reg Uno" },
    { clave: "r2", nombre: "Reg Dos" },
    { clave: "ins", nombre: "Insuf" },
  ],
  regimen_evidencia_insuficiente: "ins",
  dimensiones_opcionales_si_regimen: [],
  notas_obligatorias_si_regimen: [],
  marca_frontera: false,
  confianza: null,
  reglas_regimen: [{ regimen: "r1", condicion: [[{ dimension: "alfa", en: ["si"] }]] }],
  regimen_por_defecto: "r2",
  regimenes_exentos: ["ins"],
}

const CODEBOOK_BORRADOR = {
  etiqueta: "v0",
  estado: "borrador",
  contenido_md: "## Definiciones del estudio\n\nTexto del codebook de prueba.",
  esquema: ESQUEMA,
  contenido_sha256: null,
}

const ESPERADA = {
  respuestas: { alfa: { valor: "no", cita: "turno 2" } },
  regimen: "r2",
  regimen_propuesto: null,
  es_frontera: false,
  confianza: null,
  notas: "",
}

const TRAZA = {
  traza_version: "traza_v1",
  enunciado: { tp_md: "Consigna del ancla", ejercicio_md: null },
  elementos: [{ n: 1, tipo: "mensaje_alumno", t_seg: 1, k: 1, datos: { content: "mensaje del ancla" } }],
}

const MIEMBRO = [{ clave: "cibse-2027", titulo: "CIbSE", rol: "codificador", cerrada: false }]

function mock(entrenamiento: unknown, extra: Record<string, unknown> = {}) {
  // La respuesta de la practica se puede reemplazar por `extra` sin moverla de lugar:
  // setupFetchMock elige el PRIMER prefijo que matchea, y la ruta de la respuesta
  // tiene que quedar antes que la generica `/entrenamiento`.
  setupFetchMock({
    [`${E}/mis-membresias`]: () => MIEMBRO,
    [`${E}/cibse-2027/entrenamiento/an-p/respuesta`]: (extra[`${E}/cibse-2027/entrenamiento/an-p/respuesta`] as (() => unknown) | undefined) ?? (() => ({
      regimen: "r1",
      regimen_regla: "r1",
      regimen_propuesto: null,
      esperada: ESPERADA,
      explicacion_md: "Explicacion de la practica: alfa es no.",
      coincide: false,
    })),
    [`${E}/cibse-2027/entrenamiento`]: () => entrenamiento,
    [`${E}/cibse-2027/items/`]: () => TRAZA,
    ...extra,
  } as Parameters<typeof setupFetchMock>[0])
}

function llamadas() {
  return vi.mocked(fetch).mock.calls.map(([u, init]) => ({
    url: String(u),
    metodo: ((init as RequestInit | undefined)?.method ?? "GET").toUpperCase(),
  }))
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe("EntrenamientoEstudioView: codebook", () => {
  it("muestra el codebook vigente renderizado y la marca de borrador", async () => {
    mock({ codebook: CODEBOOK_BORRADOR, ejemplos: [], practicas: [] })
    renderWithRouter(<EntrenamientoEstudioView getToken={getToken} />)
    expect(await screen.findByRole("heading", { name: "Definiciones del estudio" })).toBeTruthy()
    expect(screen.getByText(/Borrador/)).toBeTruthy()
  })

  it("congelado: sin marca de borrador y con su sha256 a la vista", async () => {
    mock({
      codebook: { ...CODEBOOK_BORRADOR, estado: "congelada", contenido_sha256: "f".repeat(64) },
      ejemplos: [],
      practicas: [],
    })
    renderWithRouter(<EntrenamientoEstudioView getToken={getToken} />)
    await screen.findByRole("heading", { name: "Definiciones del estudio" })
    expect(screen.queryByText(/Borrador/)).toBeNull()
    expect(screen.getByText(/ffffffffffff/)).toBeTruthy()
  })

  it("sin codebook: estado vacio explicito", async () => {
    mock({ codebook: null, ejemplos: [], practicas: [] })
    renderWithRouter(<EntrenamientoEstudioView getToken={getToken} />)
    expect(await screen.findByText(/todavía no hay codebook cargado/i)).toBeTruthy()
  })

  it("sin anclas: estado vacio de ejemplos y practica", async () => {
    mock({ codebook: CODEBOOK_BORRADOR, ejemplos: [], practicas: [] })
    renderWithRouter(<EntrenamientoEstudioView getToken={getToken} />)
    expect(await screen.findByText(/todavía no hay ejemplos ni práctica cargados/i)).toBeTruthy()
  })
})

describe("EntrenamientoEstudioView: ejemplos y practica", () => {
  it("ejemplo: traza ciega, regimen y dimensiones esperadas y explicacion", async () => {
    mock({
      codebook: CODEBOOK_BORRADOR,
      ejemplos: [
        {
          item_id: "an-e",
          orden: 1,
          respuesta_esperada: ESPERADA,
          explicacion_md: "Explicacion del ejemplo.",
        },
      ],
      practicas: [],
    })
    renderWithRouter(<EntrenamientoEstudioView getToken={getToken} />)
    const ej = await screen.findByTestId("ejemplo-an-e")
    expect(await within(ej).findByText("mensaje del ancla")).toBeTruthy()
    expect(within(ej).getByText(/Reg Dos/)).toBeTruthy()
    expect(within(ej).getByText(/Dimension Alfa: no/)).toBeTruthy()
    expect(within(ej).getByText("Explicacion del ejemplo.")).toBeTruthy()
    expect(llamadas().some((l) => l.url === `${E}/cibse-2027/items/an-e/traza`)).toBe(true)
  })

  it("practica: no muestra la respuesta esperada antes de responder", async () => {
    mock({ codebook: CODEBOOK_BORRADOR, ejemplos: [], practicas: [{ item_id: "an-p", orden: 1 }] })
    renderWithRouter(<EntrenamientoEstudioView getToken={getToken} />)
    const pr = await screen.findByTestId("practica-an-p")
    await within(pr).findByText("mensaje del ancla")
    expect(within(pr).queryByText(/Explicacion de la practica/)).toBeNull()
    expect(within(pr).queryByText(/Esperado/)).toBeNull()
  })

  it("practica respondida: devolucion con esperado, explicacion y comparacion con el regimen de la regla", async () => {
    mock({ codebook: CODEBOOK_BORRADOR, ejemplos: [], practicas: [{ item_id: "an-p", orden: 1 }] })
    renderWithRouter(<EntrenamientoEstudioView getToken={getToken} />)
    const pr = await screen.findByTestId("practica-an-p")
    const alfa = await within(pr).findByRole("group", { name: "Dimension Alfa" })
    fireEvent.click(within(alfa).getByLabelText("si"))
    fireEvent.click(within(pr).getByRole("button", { name: "Guardar" }))
    await waitFor(() =>
      expect(llamadas()).toContainEqual({
        url: `${E}/cibse-2027/entrenamiento/an-p/respuesta`,
        metodo: "POST",
      }),
    )
    const dev = await within(pr).findByTestId("devolucion-an-p")
    expect(dev.textContent).toContain("Reg Uno")
    expect(dev.textContent).toContain("Reg Dos")
    expect(dev.textContent).toMatch(/no coincide/)
    expect(within(dev).getByText("Explicacion de la practica: alfa es no.")).toBeTruthy()
    expect(dev.textContent).toContain("Dimension Alfa: no")
  })
})

describe("EntrenamientoEstudioView: comparacion de la devolucion", () => {
  it("coincide cuando el regimen de la regla es el esperado, aunque haya propuesto otro", async () => {
    mock(
      { codebook: CODEBOOK_BORRADOR, ejemplos: [], practicas: [{ item_id: "an-p", orden: 1 }] },
      {
        [`${E}/cibse-2027/entrenamiento/an-p/respuesta`]: () => ({
          regimen: "r2",
          regimen_regla: "r2",
          regimen_propuesto: "r1",
          esperada: ESPERADA,
          explicacion_md: "x",
          coincide: true,
        }),
      },
    )
    renderWithRouter(<EntrenamientoEstudioView getToken={getToken} />)
    const pr = await screen.findByTestId("practica-an-p")
    await within(pr).findByRole("group", { name: "Dimension Alfa" })
    fireEvent.change(within(pr).getByLabelText("Régimen propuesto"), { target: { value: "r1" } })
    fireEvent.change(within(pr).getByLabelText("Notas"), { target: { value: "propongo otro" } })
    fireEvent.click(within(pr).getByRole("button", { name: "Guardar" }))
    const dev = await within(pr).findByTestId("devolucion-an-p")
    expect(dev.textContent).toMatch(/coincide/)
    expect(dev.textContent).not.toMatch(/no coincide/)
  })
})

describe("EntrenamientoEstudioView: contrato real del backend", () => {
  it("respuesta esperada con notas null (forma persistida) no rompe el ejemplo", async () => {
    mock({
      codebook: CODEBOOK_BORRADOR,
      ejemplos: [
        {
          item_id: "an-e",
          orden: 1,
          respuesta_esperada: { ...ESPERADA, notas: null },
          explicacion_md: "Explicacion del ejemplo.",
        },
      ],
      practicas: [],
    })
    renderWithRouter(<EntrenamientoEstudioView getToken={getToken} />)
    const ej = await screen.findByTestId("ejemplo-an-e")
    expect(within(ej).getByText(/Dimension Alfa: no/)).toBeTruthy()
  })

  it("la devolucion usa `coincide` del servidor: sin regimen derivado no coincide aunque el esperado tambien sea null", async () => {
    mock(
      { codebook: CODEBOOK_BORRADOR, ejemplos: [], practicas: [{ item_id: "an-p", orden: 1 }] },
      {
        [`${E}/cibse-2027/entrenamiento/an-p/respuesta`]: () => ({
          regimen: null,
          regimen_regla: null,
          regimen_propuesto: null,
          esperada: { ...ESPERADA, regimen: null },
          explicacion_md: "x",
          coincide: false,
        }),
      },
    )
    renderWithRouter(<EntrenamientoEstudioView getToken={getToken} />)
    const pr = await screen.findByTestId("practica-an-p")
    await within(pr).findByRole("group", { name: "Dimension Alfa" })
    fireEvent.click(within(pr).getByRole("button", { name: "Guardar" }))
    const dev = await within(pr).findByTestId("devolucion-an-p")
    expect(dev.textContent).toMatch(/no coincide/)
  })
})

describe("EntrenamientoEstudioView: acceso", () => {
  it("docente sin membresia: aviso y enlace al piloto, sin pedir el entrenamiento", async () => {
    setupFetchMock({ [`${E}/mis-membresias`]: () => [] })
    renderWithRouter(<EntrenamientoEstudioView getToken={getToken} />)
    expect(await screen.findByText(/se usa para un estudio de codificación/)).toBeTruthy()
    expect(screen.getByRole("link", { name: /acuerdo del piloto/ })).toBeTruthy()
    expect(llamadas().some((l) => l.url.includes("/entrenamiento"))).toBe(false)
  })

  it("no exige un umbral ni bloquea la codificacion (el entrenamiento es opcional)", async () => {
    mock({ codebook: CODEBOOK_BORRADOR, ejemplos: [], practicas: [{ item_id: "an-p", orden: 1 }] })
    const { container } = renderWithRouter(<EntrenamientoEstudioView getToken={getToken} />)
    await screen.findByTestId("practica-an-p")
    expect(container.textContent).not.toMatch(/6\/7|Necesitás|aprobar el entrenamiento/i)
    expect(container.textContent).toMatch(/no es obligatorio/i)
  })
})
