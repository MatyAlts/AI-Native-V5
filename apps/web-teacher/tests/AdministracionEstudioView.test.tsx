// Contenido en espanol SIN tildes para evitar problemas de encoding en Windows/cp1252.
/**
 * Administracion del estudio, solo para el investigador
 * (`src/views/estudio/AdministracionEstudioView.tsx`; design D3, D6, D8, D11, D12, D14).
 *
 * Lo que se blinda:
 *   - a un codificador no se le renderiza nada ni se le pide nada;
 *   - la muestra y los enunciados se suben como el ARCHIVO CRUDO (el servidor
 *     hashea esos bytes; el panel no parsea ni reescribe);
 *   - la cobertura de enunciados (faltantes con items afectados, filas ignoradas)
 *     y las alertas de cada enunciado quedan a la vista para la revision;
 *   - aprobar manda `null` (original tal cual) y editar manda el texto editado;
 *   - los errores de validacion del esquema (400) se ven;
 *   - congelar pide confirmacion.
 */
import { fireEvent, screen, waitFor, within } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { AdministracionEstudioView } from "../src/views/estudio/AdministracionEstudioView"
import { renderWithRouter, setupFetchMock } from "./_mocks"

const getToken = async () => null
const E = "/api/v1/interrater/estudios/cibse-2027"

const ENUNCIADOS = {
  cobertura: {
    requeridos: 4,
    cargados: 3,
    revisados: 1,
    faltantes: [{ tipo: "ejercicio", id: "ej-9", items_afectados: 7 }],
    sin_revisar: [{ tipo: "tp", id: "tp-1", items_afectados: 12 }],
  },
  enunciados: [
    {
      id: "en-1",
      tipo: "tp",
      fuente_id: "tp-1",
      contenido_original_md: "Entrega el 12/05/2026 al Prof. Perez",
      contenido_mostrado_md: null,
      alertas: ["fecha", "docente"],
      revisado: false,
    },
    {
      id: "en-2",
      tipo: "ejercicio",
      fuente_id: "ej-1",
      contenido_original_md: "Suma dos numeros",
      contenido_mostrado_md: "Suma dos numeros",
      alertas: [],
      revisado: true,
    },
  ],
}

const VERSIONES = [
  { etiqueta: "v0", estado: "congelada", contenido_sha256: "c".repeat(64), congelada_at: "x", vigente: false },
  { etiqueta: "v1", estado: "borrador", contenido_sha256: null, congelada_at: null, vigente: true },
]

const MEMBRESIAS = [
  {
    membresia_id: "m-1",
    email: "inv@ejemplo.org",
    rol: "investigador",
    alias: "I1",
    estado: "activa",
    atada: true,
    created_at: "x",
    cerrada_at: null,
    revocada_at: null,
  },
  {
    membresia_id: "m-2",
    email: "ana@ejemplo.org",
    rol: "codificador",
    alias: "C1",
    estado: "activa",
    atada: false,
    created_at: "x",
    cerrada_at: null,
    revocada_at: null,
  },
  {
    membresia_id: "m-3",
    email: "viejo@ejemplo.org",
    rol: "codificador",
    alias: "C0",
    estado: "revocada",
    atada: true,
    created_at: "x",
    cerrada_at: null,
    revocada_at: "2026-11-01T00:00:00Z",
  },
]

const PROGRESO = [
  { alias: "C1", completos: 10, parciales: 2, con_regimen_propuesto: 1, cerrada: false, revocada: false },
  { alias: "C2", completos: 150, parciales: 0, con_regimen_propuesto: 3, cerrada: true, revocada: false },
]

const ANCLAS = [
  {
    item_id: "an-1",
    episode_id: "ep-ancla-1",
    uso: "practica",
    orden: 1,
    respuesta_esperada: {
      respuestas: {},
      regimen: null,
      regimen_propuesto: null,
      es_frontera: false,
      confianza: null,
      notas: "",
    },
    explicacion_md: "porque si",
    consensuado_por: "C1, C2",
    enunciados_listos: false,
  },
]

function base(extra: Record<string, unknown> = {}) {
  setupFetchMock({
    [`${E}/codebook/v1/anclas`]: () => ANCLAS,
    [`${E}/codebook/v1/congelar`]: () => ({ ...VERSIONES[1], estado: "congelada" }),
    [`${E}/codebook/versiones`]: () => VERSIONES,
    [`${E}/codebook-vigente`]: () => ({}),
    [`${E}/codebook/v1`]: () => VERSIONES[1],
    [`${E}/codebook`]: () => VERSIONES[1],
    [`${E}/progreso`]: () => PROGRESO,
    [`${E}/enunciados/`]: () => ({ ...ENUNCIADOS.enunciados[0], revisado: true }),
    [`${E}/enunciados`]: () => ENUNCIADOS,
    [`${E}/muestra`]: () => ({ items: 150, sha256: "d".repeat(64) }),
    [`${E}/membresias/`]: () => ({ membresia_id: "m-2", revocada_at: "2026-11-04T12:00:00Z" }),
    [`${E}/membresias`]: () => MEMBRESIAS,
    [`${E}/exportacion`]: () => "a,b\n",
    ...extra,
  } as Parameters<typeof setupFetchMock>[0])
}

function llamadas() {
  return vi.mocked(fetch).mock.calls.map(([u, init]) => ({
    url: String(u),
    metodo: ((init as RequestInit | undefined)?.method ?? "GET").toUpperCase(),
    body: (init as RequestInit | undefined)?.body,
  }))
}

function region(nombre: string) {
  return screen.getByRole("region", { name: nombre })
}

function subir(input: HTMLElement, archivo: File) {
  fireEvent.change(input, { target: { files: [archivo] } })
}

beforeEach(() => {
  URL.createObjectURL = vi.fn(() => "blob:fake") as typeof URL.createObjectURL
  URL.revokeObjectURL = vi.fn() as typeof URL.revokeObjectURL
})

afterEach(() => {
  vi.unstubAllGlobals()
})

async function montarInvestigador() {
  renderWithRouter(<AdministracionEstudioView clave="cibse-2027" rol="investigador" getToken={getToken} />)
  await screen.findByRole("heading", { name: "Administración del estudio" })
}

describe("AdministracionEstudioView: acceso", () => {
  it("a un codificador no le renderiza nada ni pide nada", async () => {
    base()
    const { container } = renderWithRouter(
      <AdministracionEstudioView clave="cibse-2027" rol="codificador" getToken={getToken} />,
    )
    await new Promise((r) => setTimeout(r, 30))
    expect(screen.queryByRole("heading", { name: "Administración del estudio" })).toBeNull()
    expect(container.textContent).not.toContain("Muestra")
    expect(llamadas().filter((l) => l.url.startsWith(E))).toEqual([])
  })
})

describe("AdministracionEstudioView: muestra", () => {
  it("sube el archivo crudo como cuerpo, con el sha256 esperado, y muestra el resultado", async () => {
    base()
    await montarInvestigador()
    const r = region("Muestra")
    const contenido = "﻿estrato,origen,tp,episode_id\r\nA,x,tp1,11111111-1111-4111-8111-111111111111\r\n"
    const archivo = new File([contenido], "muestra.csv", { type: "text/csv" })
    subir(within(r).getByLabelText("Archivo CSV de la muestra"), archivo)
    fireEvent.change(within(r).getByLabelText("sha256 esperado (opcional)"), {
      target: { value: "e".repeat(64) },
    })
    fireEvent.click(within(r).getByRole("button", { name: "Cargar muestra" }))
    await waitFor(() =>
      expect(llamadas().some((l) => l.url.startsWith(`${E}/muestra`) && l.metodo === "POST")).toBe(true),
    )
    const envio = llamadas().find((l) => l.url.startsWith(`${E}/muestra`) && l.metodo === "POST")
    expect(envio?.url).toBe(`${E}/muestra?sha256_esperado=${"e".repeat(64)}`)
    expect(envio?.body).toBe(archivo)
    expect(await within(r).findByText(/150 ítems/)).toBeTruthy()
  })

  it("un 422 de la muestra se ve en la seccion", async () => {
    base({
      [`${E}/muestra`]: {
        ok: false,
        status: 422,
        body: () => ({ detail: "sha256 no coincide con el esperado" }),
      },
    })
    await montarInvestigador()
    const r = region("Muestra")
    subir(within(r).getByLabelText("Archivo CSV de la muestra"), new File(["x"], "m.csv"))
    fireEvent.click(within(r).getByRole("button", { name: "Cargar muestra" }))
    expect(await within(r).findByRole("alert")).toHaveTextContent("sha256 no coincide")
  })
})

describe("AdministracionEstudioView: enunciados", () => {
  it("muestra la cobertura con faltantes e items afectados, y el aviso de bloqueo", async () => {
    base()
    await montarInvestigador()
    const r = region("Enunciados")
    expect(await within(r).findByText(/3 de 4 cargados/)).toBeTruthy()
    expect(within(r).getByText(/1 revisados/)).toBeTruthy()
    expect(within(r).getByText(/ejercicio ej-9/)).toBeTruthy()
    expect(within(r).getByText(/7 ítems afectados/)).toBeTruthy()
    expect(within(r).getByText(/codificación queda bloqueada/)).toBeTruthy()
  })

  it("cobertura: lista los enunciados cargados y sin revisar con sus items afectados", async () => {
    base()
    await montarInvestigador()
    const r = region("Enunciados")
    expect(await within(r).findByText(/Sin revisar tp tp-1 · 12 ítems afectados/)).toBeTruthy()
  })

  it("sube el CSV crudo de enunciados e informa las filas ignoradas", async () => {
    base({
      [`${E}/enunciados`]: () => ({
        ...ENUNCIADOS,
        ignoradas: [{ tipo: "tp", id: "tp-sin-uso" }],
      }),
    })
    await montarInvestigador()
    const r = region("Enunciados")
    const archivo = new File(['tipo,tp_id,ejercicio_id,enunciado\ntp,1,,"a, b"\n'], "en.csv")
    subir(within(r).getByLabelText("Archivo CSV de enunciados"), archivo)
    fireEvent.click(within(r).getByRole("button", { name: "Cargar enunciados" }))
    await waitFor(() =>
      expect(llamadas().some((l) => l.url === `${E}/enunciados` && l.metodo === "POST")).toBe(true),
    )
    const envio = llamadas().find((l) => l.url === `${E}/enunciados` && l.metodo === "POST")
    expect(envio?.body).toBe(archivo)
    expect(await within(r).findByText(/tp tp-sin-uso/)).toBeTruthy()
  })

  it("lista cada enunciado sin revisar con sus alertas y el texto original", async () => {
    base()
    await montarInvestigador()
    const item = await screen.findByTestId("enunciado-en-1")
    expect(within(item).getByText(/fecha/)).toBeTruthy()
    expect(within(item).getByText(/docente/)).toBeTruthy()
    // El original va en un <pre>; el mismo texto prellena el campo editable.
    expect(within(item).getByText(/Prof\. Perez/, { selector: "pre" })).toBeTruthy()
    expect(within(screen.getByTestId("enunciado-en-2")).getByText(/Revisado/)).toBeTruthy()
  })

  it("aprobar tal cual manda null; guardar version editada manda el texto editado", async () => {
    base()
    await montarInvestigador()
    const item = await screen.findByTestId("enunciado-en-1")
    fireEvent.click(within(item).getByRole("button", { name: "Aprobar tal cual" }))
    await waitFor(() =>
      expect(llamadas().some((l) => l.url === `${E}/enunciados/en-1/revision`)).toBe(true),
    )
    const aprobar = llamadas().find((l) => l.url === `${E}/enunciados/en-1/revision`)
    expect(JSON.parse(String(aprobar?.body))).toEqual({ contenido_mostrado_md: null })

    fireEvent.change(within(item).getByLabelText("Versión a mostrar"), {
      target: { value: "Entrega al docente" },
    })
    fireEvent.click(within(item).getByRole("button", { name: "Guardar versión editada" }))
    await waitFor(() =>
      expect(llamadas().filter((l) => l.url === `${E}/enunciados/en-1/revision`).length).toBe(2),
    )
    const editar = llamadas().filter((l) => l.url === `${E}/enunciados/en-1/revision`)[1]
    expect(JSON.parse(String(editar?.body))).toEqual({ contenido_mostrado_md: "Entrega al docente" })
  })
})

describe("AdministracionEstudioView: codebook", () => {
  it("sube .md y esquema JSON a la version en borrador y muestra el 400 de validacion", async () => {
    base({
      [`${E}/codebook/v1`]: {
        ok: false,
        status: 400,
        body: () => ({
          detail: {
            mensaje: "Esquema inválido",
            errores: ["esquema.regimen_evidencia_insuficiente: no es un régimen declarado"],
          },
        }),
      },
    })
    await montarInvestigador()
    const r = region("Codebook")
    subir(within(r).getByLabelText("Texto del codebook (.md)"), new File(["# Codebook"], "cb.md"))
    subir(within(r).getByLabelText("Esquema del formulario (.json)"), new File(['{"dimensiones":[]}'], "e.json"))
    fireEvent.click(within(r).getByRole("button", { name: "Guardar borrador v1" }))
    const alerta = await within(r).findByRole("alert")
    expect(alerta).toHaveTextContent(
      "esquema.regimen_evidencia_insuficiente: no es un régimen declarado",
    )
    expect(alerta.textContent).not.toContain("{")
    const envio = llamadas().find((l) => l.url === `${E}/codebook/v1` && l.metodo === "PUT")
    expect(JSON.parse(String(envio?.body))).toEqual({
      contenido_md: "# Codebook",
      esquema: { dimensiones: [] },
    })
  })

  // verify-1, F1: el PUT avisa que anclas dejaron de valer; congelar las rechaza.
  it("guardar un esquema que invalida anclas avisa cuales y por que", async () => {
    base({
      [`${E}/codebook/v1`]: () => ({
        ...VERSIONES[1],
        contenido_md: "# Codebook",
        esquema: null,
        anclas_invalidas: [
          { item_id: "an-1", uso: "practica", orden: 1, motivos: ["respuestas: dimensión desconocida 'd1'"] },
        ],
      }),
    })
    await montarInvestigador()
    const r = region("Codebook")
    subir(within(r).getByLabelText("Texto del codebook (.md)"), new File(["# Codebook"], "cb.md"))
    subir(within(r).getByLabelText("Esquema del formulario (.json)"), new File(['{"dimensiones":[]}'], "e.json"))
    fireEvent.click(within(r).getByRole("button", { name: "Guardar borrador v1" }))
    const aviso = await within(r).findByText(/1 ancla no vale contra el esquema nuevo/)
    expect(aviso.textContent).toContain("práctica 1: respuestas: dimensión desconocida 'd1'")
    expect(aviso.textContent).toMatch(/no se puede congelar/)
  })

  it("guardar un esquema sin anclas invalidas no muestra aviso de anclas", async () => {
    base({ [`${E}/codebook/v1`]: () => ({ ...VERSIONES[1], anclas_invalidas: [] }) })
    await montarInvestigador()
    const r = region("Codebook")
    subir(within(r).getByLabelText("Texto del codebook (.md)"), new File(["# Codebook"], "cb.md"))
    subir(within(r).getByLabelText("Esquema del formulario (.json)"), new File(['{"dimensiones":[]}'], "e.json"))
    fireEvent.click(within(r).getByRole("button", { name: "Guardar borrador v1" }))
    expect(await within(r).findByText("Borrador v1 guardado.")).toBeTruthy()
    expect(within(r).queryByText(/no vale contra el esquema nuevo/)).toBeNull()
  })

  it("congelar con anclas invalidas muestra el 422 con cada ancla", async () => {
    base({
      [`${E}/codebook/v1/congelar`]: {
        ok: false,
        status: 422,
        body: () => ({
          detail: {
            codigo: "anclas_invalidas",
            anclas: [{ item_id: "an-1", uso: "practica", orden: 1, motivos: ["regimen: x"] }],
            errores: ["ancla practica 1: regimen: x"],
          },
        }),
      },
    })
    await montarInvestigador()
    const r = region("Codebook")
    fireEvent.click(await within(r).findByRole("button", { name: "Congelar v1" }))
    fireEvent.click(await screen.findByRole("button", { name: "Confirmar" }))
    const alerta = await within(r).findByRole("alert")
    expect(alerta).toHaveTextContent(/anclas que no valen contra el esquema/)
    expect(alerta).toHaveTextContent("ancla practica 1: regimen: x")
  })

  it("un esquema que no es JSON se rechaza en el panel sin mandar nada", async () => {
    base()
    await montarInvestigador()
    const r = region("Codebook")
    subir(within(r).getByLabelText("Texto del codebook (.md)"), new File(["# C"], "cb.md"))
    subir(within(r).getByLabelText("Esquema del formulario (.json)"), new File(["{no json"], "e.json"))
    fireEvent.click(within(r).getByRole("button", { name: "Guardar borrador v1" }))
    expect(await within(r).findByRole("alert")).toHaveTextContent(/no es JSON válido/)
    expect(llamadas().some((l) => l.metodo === "PUT")).toBe(false)
  })

  it("congelar pide confirmacion y recien despues manda el POST", async () => {
    base()
    await montarInvestigador()
    const r = region("Codebook")
    fireEvent.click(await within(r).findByRole("button", { name: "Congelar v1" }))
    await screen.findByRole("button", { name: "Confirmar" })
    expect(llamadas().some((l) => l.url.endsWith("/congelar"))).toBe(false)
    fireEvent.click(screen.getByRole("button", { name: "Confirmar" }))
    await waitFor(() =>
      expect(llamadas()).toContainEqual(
        expect.objectContaining({ url: `${E}/codebook/v1/congelar`, metodo: "POST" }),
      ),
    )
  })

  it("congelar cancelado no manda nada", async () => {
    base()
    await montarInvestigador()
    const r = region("Codebook")
    fireEvent.click(await within(r).findByRole("button", { name: "Congelar v1" }))
    fireEvent.click(await screen.findByRole("button", { name: "Cancelar" }))
    await new Promise((res) => setTimeout(res, 20))
    expect(llamadas().some((l) => l.url.endsWith("/congelar"))).toBe(false)
  })

  it("lista las versiones con estado, vigente y sha de las congeladas; fija vigente", async () => {
    base()
    await montarInvestigador()
    const r = region("Codebook")
    expect(await within(r).findByText("cccccccccccc…")).toBeTruthy()
    expect(within(r).getByText(/v1 · borrador · vigente/)).toBeTruthy()
    fireEvent.click(within(r).getByRole("button", { name: "Fijar v0 como vigente" }))
    await waitFor(() =>
      expect(llamadas()).toContainEqual(
        expect.objectContaining({ url: `${E}/codebook-vigente`, metodo: "PUT" }),
      ),
    )
    const pedido = llamadas().find((l) => l.url === `${E}/codebook-vigente`)
    expect(JSON.parse(String(pedido?.body))).toEqual({ etiqueta: "v0" })
  })
})

describe("AdministracionEstudioView: anclas, membresias, progreso, exportacion", () => {
  it("anclas de la version vigente, con las pendientes de enunciado marcadas", async () => {
    base()
    await montarInvestigador()
    const r = region("Anclas")
    const fila = await within(r).findByTestId("ancla-an-1")
    expect(fila.textContent).toContain("práctica")
    expect(fila.textContent).toContain("enunciado pendiente")
  })

  // verify-2, O1: el alta de un ancla incompleta se acepta pero avisa.
  function anclasConAlta(faltantes: string[]) {
    return () => {
      const ultima = vi.mocked(fetch).mock.calls.at(-1)
      const metodo = ((ultima?.[1] as RequestInit | undefined)?.method ?? "GET").toUpperCase()
      return metodo === "POST" ? { ...ANCLAS[0], faltantes } : ANCLAS
    }
  }

  async function agregarAncla() {
    await montarInvestigador()
    const r = region("Anclas")
    await within(r).findByTestId("ancla-an-1")
    fireEvent.change(within(r).getByLabelText("episode_id"), { target: { value: "ep-nuevo" } })
    fireEvent.change(within(r).getByLabelText(/Respuesta esperada/), {
      target: { value: '{"respuestas": {}}' },
    })
    fireEvent.click(within(r).getByRole("button", { name: "Agregar ancla" }))
    await waitFor(() =>
      expect(llamadas()).toContainEqual(
        expect.objectContaining({ url: `${E}/codebook/v1/anclas`, metodo: "POST" }),
      ),
    )
    return r
  }

  it("alta de un ancla incompleta: avisa que falta y que asi no se congela", async () => {
    base({ [`${E}/codebook/v1/anclas`]: anclasConAlta(["regimen", "cita:d1"]) })
    const r = await agregarAncla()
    const aviso = await within(r).findByText(/quedó incompleta/)
    expect(aviso.textContent).toContain("regimen, cita:d1")
    expect(aviso.textContent).toMatch(/antes de congelar/)
  })

  it("alta de un ancla completa: sin aviso de incompleta", async () => {
    base({ [`${E}/codebook/v1/anclas`]: anclasConAlta([]) })
    const r = await agregarAncla()
    await new Promise((res) => setTimeout(res, 20))
    expect(within(r).queryByText(/quedó incompleta/)).toBeNull()
  })

  it("asignar membresia manda email y rol", async () => {
    base()
    await montarInvestigador()
    const r = region("Membresías")
    fireEvent.change(within(r).getByLabelText("Email"), { target: { value: "ana@ejemplo.org" } })
    fireEvent.change(within(r).getByLabelText("Rol"), { target: { value: "codificador" } })
    fireEvent.click(within(r).getByRole("button", { name: "Asignar" }))
    await waitFor(() =>
      expect(llamadas().some((l) => l.url === `${E}/membresias` && l.metodo === "POST")).toBe(true),
    )
    const alta = llamadas().find((l) => l.url === `${E}/membresias` && l.metodo === "POST")
    expect(JSON.parse(String(alta?.body))).toEqual({ email: "ana@ejemplo.org", rol: "codificador" })
  })

  it("lista las membresias con email, rol, alias y estado", async () => {
    base()
    await montarInvestigador()
    const r = region("Membresías")
    const fila = await within(r).findByTestId("membresia-m-2")
    expect(fila.textContent).toContain("ana@ejemplo.org")
    expect(fila.textContent).toContain("codificador")
    expect(fila.textContent).toContain("C1")
    expect(fila.textContent).toContain("activa")
    expect(within(r).getByTestId("membresia-m-3").textContent).toContain("revocada")
  })

  it("revocar va por id, con confirmacion, y solo se ofrece en las activas", async () => {
    base()
    await montarInvestigador()
    const r = region("Membresías")
    const fila = await within(r).findByTestId("membresia-m-2")
    expect(
      within(within(r).getByTestId("membresia-m-3")).queryByRole("button", { name: /Revocar/ }),
    ).toBeNull()
    fireEvent.click(within(fila).getByRole("button", { name: "Revocar C1" }))
    fireEvent.click(await screen.findByRole("button", { name: "Confirmar" }))
    await waitFor(() =>
      expect(llamadas()).toContainEqual(
        expect.objectContaining({ url: `${E}/membresias/m-2`, metodo: "DELETE" }),
      ),
    )
    const pedido = llamadas().find((l) => l.metodo === "DELETE")
    expect(pedido?.body).toBeUndefined()
  })

  it("revocar cancelado no manda el DELETE", async () => {
    base()
    await montarInvestigador()
    const r = region("Membresías")
    const fila = await within(r).findByTestId("membresia-m-2")
    fireEvent.click(within(fila).getByRole("button", { name: "Revocar C1" }))
    fireEvent.click(await screen.findByRole("button", { name: "Cancelar" }))
    await new Promise((res) => setTimeout(res, 20))
    expect(llamadas().some((l) => l.metodo === "DELETE")).toBe(false)
  })

  it("progreso por codificador: solo cantidades por alias", async () => {
    base()
    await montarInvestigador()
    const r = region("Progreso")
    const c2 = await within(r).findByTestId("progreso-C2")
    expect(c2.textContent).toContain("150")
    expect(c2.textContent).toContain("cerrada")
    expect(within(r).getByTestId("progreso-C1").textContent).toContain("10")
  })

  it("exportar pide el contenido y formato elegidos y descarga el archivo", async () => {
    base()
    await montarInvestigador()
    const r = region("Exportación")
    fireEvent.change(within(r).getByLabelText("Contenido"), { target: { value: "historial" } })
    fireEvent.change(within(r).getByLabelText("Formato"), { target: { value: "json" } })
    fireEvent.click(within(r).getByRole("button", { name: "Exportar" }))
    await waitFor(() =>
      expect(llamadas().some((l) => l.url === `${E}/exportacion?contenido=historial&formato=json`)).toBe(
        true,
      ),
    )
    await waitFor(() => expect(URL.createObjectURL).toHaveBeenCalled())
  })
})
