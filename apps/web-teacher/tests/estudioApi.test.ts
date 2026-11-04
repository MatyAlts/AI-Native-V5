// Contenido en espanol SIN tildes para evitar problemas de encoding en Windows/cp1252.
/**
 * Cliente HTTP del estudio de codificacion ciega (`src/lib/estudioApi.ts`).
 *
 * Contrato: design.md D3 a D14 del change `cibse-codificacion-ciega`. Lo que se
 * blinda aca es lo que el panel no puede inferir solo:
 *   - rutas y metodos de cada endpoint (un typo en la ruta da 404 en produccion
 *     sin que ningun render lo note),
 *   - que los errores 403/409/422 lleguen al llamador con su `status` y su
 *     `detail` (las vistas deciden por el codigo: `evidencia_alterada`,
 *     `enunciados_pendientes`, faltantes del cierre),
 *   - que el `regimen` que devuelve el guardado (derivado por la regla en el
 *     servidor) llegue al llamador sin reinterpretar,
 *   - que la muestra y los enunciados viajen como TEXTO CRUDO del archivo: el
 *     servidor calcula el sha256 sobre esos bytes (D6).
 */
import { afterEach, describe, expect, it, vi } from "vitest"
import { estudioApi } from "../src/lib/estudioApi"
import { setupFetchMock } from "./_mocks"

const getToken = async () => "tok"
const BASE = "/api/v1/interrater/estudios"

function llamadas(): { url: string; init: RequestInit }[] {
  const f = vi.mocked(fetch)
  return f.mock.calls.map(([url, init]) => ({
    url: String(url),
    init: (init ?? {}) as RequestInit,
  }))
}

function ultima() {
  const todas = llamadas()
  // Sin fetch devuelve una llamada vacia: el test falla por la ASERCION de ruta,
  // no por una excepcion del helper.
  return todas[todas.length - 1] ?? { url: "(sin fetch)", init: {} }
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe("estudioApi: rutas y metodos", () => {
  const casos: {
    nombre: string
    llamar: () => Promise<unknown>
    metodo: string
    ruta: string
  }[] = [
    {
      nombre: "mis membresias",
      llamar: () => estudioApi.misMembresias(getToken),
      metodo: "GET",
      ruta: `${BASE}/mis-membresias`,
    },
    {
      nombre: "alta de estudio",
      llamar: () => estudioApi.crearEstudio({ clave: "cibse-2027", titulo: "T" }, getToken),
      metodo: "POST",
      ruta: BASE,
    },
    {
      nombre: "alta de membresia",
      llamar: () =>
        estudioApi.asignarMembresia("cibse-2027", { email: "a@b.org", rol: "codificador" }, getToken),
      metodo: "POST",
      ruta: `${BASE}/cibse-2027/membresias`,
    },
    {
      nombre: "listar membresias (investigador)",
      llamar: () => estudioApi.listarMembresias("cibse-2027", getToken),
      metodo: "GET",
      ruta: `${BASE}/cibse-2027/membresias`,
    },
    {
      nombre: "revocar membresia por id",
      llamar: () => estudioApi.revocarMembresia("cibse-2027", "mem-1", getToken),
      metodo: "DELETE",
      ruta: `${BASE}/cibse-2027/membresias/mem-1`,
    },
    {
      nombre: "versiones del codebook",
      llamar: () => estudioApi.listarVersiones("cibse-2027", getToken),
      metodo: "GET",
      ruta: `${BASE}/cibse-2027/codebook/versiones`,
    },
    {
      nombre: "crear version",
      llamar: () =>
        estudioApi.crearVersion("cibse-2027", { etiqueta: "v1", clonar_de: "v0" }, getToken),
      metodo: "POST",
      ruta: `${BASE}/cibse-2027/codebook`,
    },
    {
      nombre: "editar borrador",
      llamar: () =>
        estudioApi.editarVersion(
          "cibse-2027",
          "v0",
          { contenido_md: "# x", esquema: { a: 1 } },
          getToken,
        ),
      metodo: "PUT",
      ruta: `${BASE}/cibse-2027/codebook/v0`,
    },
    {
      nombre: "congelar",
      llamar: () => estudioApi.congelarVersion("cibse-2027", "v0", getToken),
      metodo: "POST",
      ruta: `${BASE}/cibse-2027/codebook/v0/congelar`,
    },
    {
      nombre: "fijar vigente",
      llamar: () => estudioApi.fijarVigente("cibse-2027", "v0", getToken),
      metodo: "PUT",
      ruta: `${BASE}/cibse-2027/codebook-vigente`,
    },
    {
      nombre: "leer vigente",
      llamar: () => estudioApi.codebookVigente("cibse-2027", getToken),
      metodo: "GET",
      ruta: `${BASE}/cibse-2027/codebook/vigente`,
    },
    {
      nombre: "traza ciega",
      llamar: () => estudioApi.traza("cibse-2027", "it-1", getToken),
      metodo: "GET",
      ruta: `${BASE}/cibse-2027/items/it-1/traza`,
    },
    {
      nombre: "lista de items",
      llamar: () => estudioApi.misItems("cibse-2027", getToken),
      metodo: "GET",
      ruta: `${BASE}/cibse-2027/items`,
    },
    {
      nombre: "leer enunciados",
      llamar: () => estudioApi.enunciados("cibse-2027", getToken),
      metodo: "GET",
      ruta: `${BASE}/cibse-2027/enunciados`,
    },
    {
      nombre: "revisar enunciado",
      llamar: () =>
        estudioApi.revisarEnunciado("cibse-2027", "en-1", { contenido_mostrado_md: null }, getToken),
      metodo: "POST",
      ruta: `${BASE}/cibse-2027/enunciados/en-1/revision`,
    },
    {
      nombre: "listar anclas",
      llamar: () => estudioApi.anclas("cibse-2027", "v0", getToken),
      metodo: "GET",
      ruta: `${BASE}/cibse-2027/codebook/v0/anclas`,
    },
    {
      nombre: "crear ancla",
      llamar: () =>
        estudioApi.crearAncla(
          "cibse-2027",
          "v0",
          {
            episode_id: "e",
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
            explicacion_md: "",
            consensuado_por: "",
          },
          getToken,
        ),
      metodo: "POST",
      ruta: `${BASE}/cibse-2027/codebook/v0/anclas`,
    },
    {
      nombre: "editar ancla en borrador",
      llamar: () =>
        estudioApi.editarAncla("cibse-2027", "v0", "it-9", { orden: 2 }, getToken),
      metodo: "PUT",
      ruta: `${BASE}/cibse-2027/codebook/v0/anclas/it-9`,
    },
    {
      nombre: "borrar ancla",
      llamar: () => estudioApi.borrarAncla("cibse-2027", "v0", "it-9", getToken),
      metodo: "DELETE",
      ruta: `${BASE}/cibse-2027/codebook/v0/anclas/it-9`,
    },
    {
      nombre: "leer mi etiqueta",
      llamar: () => estudioApi.miEtiqueta("cibse-2027", "it-1", getToken),
      metodo: "GET",
      ruta: `${BASE}/cibse-2027/items/it-1/mi-etiqueta`,
    },
    {
      nombre: "cerrar mi codificacion",
      llamar: () => estudioApi.cerrarMiCodificacion("cibse-2027", getToken),
      metodo: "POST",
      ruta: `${BASE}/cibse-2027/mi-codificacion/cerrar`,
    },
    {
      nombre: "progreso",
      llamar: () => estudioApi.progreso("cibse-2027", getToken),
      metodo: "GET",
      ruta: `${BASE}/cibse-2027/progreso`,
    },
    {
      nombre: "entrenamiento",
      llamar: () => estudioApi.entrenamiento("cibse-2027", getToken),
      metodo: "GET",
      ruta: `${BASE}/cibse-2027/entrenamiento`,
    },
    {
      nombre: "responder practica",
      llamar: () =>
        estudioApi.responderPractica(
          "cibse-2027",
          "an-1",
          {
            respuestas: {},
            regimen: null,
            regimen_propuesto: null,
            es_frontera: false,
            confianza: null,
            notas: "",
          },
          getToken,
        ),
      metodo: "POST",
      ruta: `${BASE}/cibse-2027/entrenamiento/an-1/respuesta`,
    },
  ]

  for (const c of casos) {
    it(`${c.nombre}: ${c.metodo} ${c.ruta}`, async () => {
      setupFetchMock({ [BASE]: () => ({}) })
      await c.llamar()
      const u = ultima()
      expect(u.url).toBe(c.ruta)
      expect((u.init.method ?? "GET").toUpperCase()).toBe(c.metodo)
    })
  }

  it("la clave y los ids viajan codificados en la ruta", async () => {
    setupFetchMock({ [BASE]: () => ({}) })
    await estudioApi.traza("a b", "x/y", getToken)
    expect(ultima().url).toBe(`${BASE}/a%20b/items/x%2Fy/traza`)
  })

  it("manda el token del caller como Bearer", async () => {
    setupFetchMock({ [BASE]: () => [] })
    await estudioApi.misMembresias(getToken)
    const headers = ultima().init.headers as Record<string, string>
    expect(headers.Authorization).toBe("Bearer tok")
  })

  it("la exportacion pide contenido y formato por query y devuelve el texto tal cual", async () => {
    setupFetchMock({ [BASE]: () => "no importa" })
    const f = vi.mocked(fetch)
    f.mockResolvedValueOnce({
      ok: true,
      status: 200,
      text: () => Promise.resolve("a,b\n1,2\n"),
      json: () => Promise.reject(new Error("no es json")),
    } as Response)
    const texto = await estudioApi.exportar("cibse-2027", "historial", "csv", getToken)
    expect(ultima().url).toBe(`${BASE}/cibse-2027/exportacion?contenido=historial&formato=csv`)
    expect(texto).toBe("a,b\n1,2\n")
  })
})

describe("estudioApi: cuerpos crudos de archivos", () => {
  it("la muestra viaja como texto crudo del archivo, con el hash esperado por query", async () => {
    setupFetchMock({ [BASE]: () => ({ items: 2, sha256: "abc" }) })
    const crudo = "estrato,origen,tp,episode_id\r\nA,x,tp1,11111111-1111-4111-8111-111111111111\r\n"
    const res = await estudioApi.cargarMuestra("cibse-2027", crudo, "f".repeat(64), getToken)
    const u = ultima()
    expect(u.url).toBe(`${BASE}/cibse-2027/muestra?sha256_esperado=${"f".repeat(64)}`)
    expect(u.init.method).toBe("POST")
    expect(u.init.body).toBe(crudo)
    expect((u.init.headers as Record<string, string>)["Content-Type"]).toBe("text/csv")
    expect(res.items).toBe(2)
  })

  it("un archivo (Blob) viaja tal cual como cuerpo: los bytes que hashea el servidor son los del archivo", async () => {
    setupFetchMock({ [BASE]: () => ({ items: 1, sha256: "abc" }) })
    // BOM + CRLF: dos cosas que una decodificacion a texto en el navegador puede alterar.
    const archivo = new Blob(["\uFEFFestrato,origen,tp,episode_id\r\n"], { type: "text/csv" })
    await estudioApi.cargarMuestra("cibse-2027", archivo, null, getToken)
    expect(ultima().init.body).toBe(archivo)
    await estudioApi.cargarEnunciados("cibse-2027", archivo, getToken)
    expect(ultima().init.body).toBe(archivo)
  })

  it("sin hash esperado no agrega query", async () => {
    setupFetchMock({ [BASE]: () => ({ items: 1, sha256: "abc" }) })
    await estudioApi.cargarMuestra("cibse-2027", "x", null, getToken)
    expect(ultima().url).toBe(`${BASE}/cibse-2027/muestra`)
  })

  it("los enunciados viajan como texto crudo del CSV", async () => {
    setupFetchMock({ [BASE]: () => ({ cobertura: null, ignoradas: [] }) })
    const crudo = 'tipo,tp_id,ejercicio_id,enunciado\ntp,1,,"linea 1\nlinea 2, con coma"\n'
    await estudioApi.cargarEnunciados("cibse-2027", crudo, getToken)
    const u = ultima()
    expect(u.url).toBe(`${BASE}/cibse-2027/enunciados`)
    expect(u.init.method).toBe("POST")
    expect(u.init.body).toBe(crudo)
    expect((u.init.headers as Record<string, string>)["Content-Type"]).toBe("text/csv")
  })

  it("la revocacion va por id: sin email ni cuerpo (contrato del backend, D3)", async () => {
    setupFetchMock({ [BASE]: () => ({}) })
    await estudioApi.revocarMembresia("cibse-2027", "mem-1", getToken)
    const u = ultima()
    expect(u.url).toBe(`${BASE}/cibse-2027/membresias/mem-1`)
    expect(u.init.body).toBeUndefined()
  })

  it("fijar vigente manda la etiqueta en el cuerpo", async () => {
    setupFetchMock({ [BASE]: () => ({}) })
    await estudioApi.fijarVigente("cibse-2027", "v1", getToken)
    expect(JSON.parse(String(ultima().init.body))).toEqual({ etiqueta: "v1" })
  })

  it("editar ancla manda solo los campos cambiados", async () => {
    setupFetchMock({ [BASE]: () => ({}) })
    await estudioApi.editarAncla("cibse-2027", "v0", "it-9", { explicacion_md: "nueva" }, getToken)
    expect(JSON.parse(String(ultima().init.body))).toEqual({ explicacion_md: "nueva" })
  })
})

describe("estudioApi: guardado de etiqueta", () => {
  it("el regimen derivado por la regla en el servidor llega al llamador", async () => {
    setupFetchMock({
      [BASE]: () => ({
        respuestas: { d1: { valor: "presente", cita: "turno 1" } },
        regimen: "reflexiva",
        regimen_regla: "reflexiva",
        regimen_propuesto: null,
        es_frontera: false,
        confianza: null,
        notas: "",
        updated_at: "2026-11-04T00:00:00Z",
      }),
    })
    const enviado = {
      respuestas: { d1: { valor: "presente", cita: "turno 1" } },
      regimen: null,
      regimen_propuesto: null,
      es_frontera: false,
      confianza: null,
      notas: "",
    }
    const res = await estudioApi.guardarMiEtiqueta("cibse-2027", "it-1", enviado, getToken)
    const u = ultima()
    expect(u.url).toBe(`${BASE}/cibse-2027/items/it-1/mi-etiqueta`)
    expect(u.init.method).toBe("PUT")
    expect(JSON.parse(String(u.init.body))).toEqual(enviado)
    expect(res.regimen).toBe("reflexiva")
    expect(res.regimen_regla).toBe("reflexiva")
  })
})

describe("estudioApi: errores propagados con status y detail", () => {
  const errores: { status: number; detail: unknown }[] = [
    { status: 403, detail: "sin_membresia" },
    { status: 409, detail: "enunciados_pendientes" },
    { status: 409, detail: { codigo: "evidencia_alterada" } },
    { status: 422, detail: { codigo: "incompleta", faltantes: [{ posicion: 3, motivos: ["d1"] }] } },
  ]
  for (const e of errores) {
    it(`${e.status} ${JSON.stringify(e.detail)}`, async () => {
      setupFetchMock({
        [BASE]: { ok: false, status: e.status, body: () => ({ detail: e.detail }) },
      })
      const err = (await estudioApi
        .guardarMiEtiqueta(
          "cibse-2027",
          "it-1",
          {
            respuestas: {},
            regimen: null,
            regimen_propuesto: null,
            es_frontera: false,
            confianza: null,
            notas: "",
          },
          getToken,
        )
        .then(
          () => null,
          (x: unknown) => x,
        )) as (Error & { status?: number; detail?: unknown }) | null
      expect(err).not.toBeNull()
      expect(err?.status).toBe(e.status)
      expect(err?.detail).toEqual(e.detail)
    })
  }

  it("codigoDeError lee el codigo tanto de un detail string como de un detail objeto", async () => {
    const { codigoDeError } = await import("../src/lib/estudioApi")
    expect(codigoDeError(Object.assign(new Error("x"), { detail: "enunciado_pendiente" }))).toBe(
      "enunciado_pendiente",
    )
    expect(
      codigoDeError(Object.assign(new Error("x"), { detail: { codigo: "evidencia_alterada" } })),
    ).toBe("evidencia_alterada")
    expect(codigoDeError(new Error("red caida"))).toBeNull()
    expect(codigoDeError("cualquier cosa")).toBeNull()
  })

  it("statusDeError devuelve el status HTTP o null", async () => {
    const { statusDeError } = await import("../src/lib/estudioApi")
    expect(statusDeError(Object.assign(new Error("x"), { status: 502 }))).toBe(502)
    expect(statusDeError(new Error("red caida"))).toBeNull()
  })
})

describe("normalizarEsquema: claves opcionales del meta-esquema real", () => {
  // El backend acepta un esquema con solo dimensiones, regimenes y
  // regimen_evidencia_insuficiente (estudio_esquema.py). Lo demas es opcional.
  const MINIMO = {
    dimensiones: [{ clave: "d1", nombre: "D1", valores: ["a", "b"], cita_requerida_si: [] }],
    regimenes: [
      { clave: "r", nombre: "R" },
      { clave: "ins", nombre: "Ins" },
    ],
    regimen_evidencia_insuficiente: "ins",
  }

  it("completa los defaults del backend", async () => {
    const { normalizarEsquema } = await import("../src/lib/estudioApi")
    expect(normalizarEsquema(MINIMO)).toEqual({
      ...MINIMO,
      regimenes_exentos: ["ins"],
      dimensiones_opcionales_si_regimen: [],
      notas_obligatorias_si_regimen: [],
      marca_frontera: false,
      notas_obligatorias_si_frontera: false,
      confianza: null,
      reglas_regimen: [],
      regimen_por_defecto: null,
    })
  })

  it("respeta lo que el esquema si trae", async () => {
    const { normalizarEsquema } = await import("../src/lib/estudioApi")
    const n = normalizarEsquema({
      ...MINIMO,
      regimenes_exentos: ["ins", "r"],
      confianza: { valores: ["baja"], obligatoria: true },
      marca_frontera: true,
      notas_obligatorias_si_frontera: true,
    })
    expect(n?.regimenes_exentos).toEqual(["ins", "r"])
    expect(n?.confianza).toEqual({ valores: ["baja"], obligatoria: true })
    expect(n?.notas_obligatorias_si_frontera).toBe(true)
  })

  it("null queda null (version sin esquema cargado)", async () => {
    const { normalizarEsquema } = await import("../src/lib/estudioApi")
    expect(normalizarEsquema(null)).toBeNull()
  })

  it("codebookVigente y entrenamiento devuelven el esquema normalizado", async () => {
    setupFetchMock({
      [`${BASE}/cibse-2027/codebook/vigente`]: () => ({
        etiqueta: "v0",
        estado: "congelada",
        contenido_md: "x",
        esquema: MINIMO,
        contenido_sha256: "a",
      }),
      [`${BASE}/cibse-2027/entrenamiento`]: () => ({
        codebook: { etiqueta: "v0", estado: "borrador", contenido_md: "x", esquema: MINIMO, contenido_sha256: null },
        ejemplos: [],
        practicas: [],
      }),
    })
    const v = await estudioApi.codebookVigente("cibse-2027", getToken)
    expect(v.esquema?.reglas_regimen).toEqual([])
    expect(v.esquema?.confianza).toBeNull()
    const en = await estudioApi.entrenamiento("cibse-2027", getToken)
    expect(en.codebook?.esquema?.regimenes_exentos).toEqual(["ins"])
  })
})
