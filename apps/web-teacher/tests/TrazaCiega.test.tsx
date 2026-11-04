// Contenido en espanol SIN tildes para evitar problemas de encoding en Windows/cp1252.
/**
 * Vista ciega de un episodio (`src/views/estudio/TrazaCiega.tsx`; design D4, D13,
 * D14; spec traza-ciega-episodio, "Presentacion en el panel docente").
 *
 * El cegamiento lo hace el SERVIDOR (lista blanca `traza_v1`). Esta vista agrega
 * una segunda barrera: renderiza solo los campos que conoce por tipo y omite los
 * tipos que no conoce. Por eso el mock inyecta a proposito claves y tipos que el
 * servidor NO deberia mandar: si un dia los manda, el panel igual no los muestra.
 */
import { cleanup, render, screen, within } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import type { TrazaCiega as TrazaCiegaData } from "../src/lib/estudioApi"
import { TrazaCiega } from "../src/views/estudio/TrazaCiega"
import { setupFetchMock } from "./_mocks"

const getToken = async () => null
const RUTA = "/api/v1/interrater/estudios/cibse-2027/items/it-1/traza"

function traza(parcial: Partial<TrazaCiegaData> = {}): TrazaCiegaData {
  return {
    traza_version: "traza_v1",
    enunciado: { tp_md: "Escribi una funcion **suma**.", ejercicio_md: "Usa un bucle for." },
    elementos: [
      { n: 1, tipo: "inicio", t_seg: 0, k: null, datos: { language: "python" } },
      { n: 2, tipo: "lectura", t_seg: 5, k: 1, datos: { duration_seconds: 90 } },
      {
        n: 3,
        tipo: "mensaje_alumno",
        t_seg: 65,
        k: 1,
        // `prompt_kind` NO esta en la lista blanca: si llegara, no se muestra.
        datos: { content: "como empiezo?", prompt_kind: "valor_prohibido_kind" },
      },
      {
        n: 4,
        tipo: "respuesta_tutor",
        t_seg: 70,
        k: 1,
        datos: { content: "que sabes de bucles?", model_used: "modelo_prohibido" },
      },
      {
        n: 5,
        tipo: "codigo",
        t_seg: 100,
        k: 1,
        datos: { snapshot: "x = 1\nprint(x)", language: "python", origin: "origen_prohibido" },
      },
      {
        n: 6,
        tipo: "codigo",
        t_seg: 130,
        k: 2,
        datos: { snapshot: "x = 2\nprint(x)", language: "python" },
      },
      {
        n: 7,
        tipo: "ejecucion",
        t_seg: 3725,
        k: 1,
        datos: {
          code: "x = 2\nprint(x)",
          stdout: "salida_normal",
          stderr: "NameError: y no definida",
          passed: 1,
          failed: 2,
          total: 3,
          failed_test_names: ["test_cero", "test_negativo"],
          execution_engine: "motor_prohibido",
        },
      },
      {
        n: 8,
        tipo: "prueba",
        t_seg: 3800,
        k: 1,
        datos: {
          test_count_total: 5,
          test_count_passed: 4,
          test_count_failed: 1,
          tests_publicos: 3,
          tests_hidden: 2,
        },
      },
      { n: 9, tipo: "nota", t_seg: 3810, k: 1, datos: { content: "me falto el caso negativo" } },
      { n: 10, tipo: "copia", t_seg: 3820, k: null, datos: { seleccion_chars: 42, metodo: "teclado" } },
      {
        n: 11,
        tipo: "pegado",
        t_seg: 3830,
        k: null,
        datos: {
          contenido_longitud: 17,
          metodo: "menu",
          contenido_preview: "texto_pegado_prohibido",
        },
      },
      // Tipo que la lista blanca omite. Si el servidor fallara y lo mandara:
      {
        n: 12,
        tipo: "intento_adverso_detectado" as never,
        t_seg: 3840,
        k: null,
        datos: { category: "overuse", severity: 1 },
      },
      { n: 13, tipo: "fin_abandonado", t_seg: 3900, k: null, datos: { reason: "timeout" } },
    ],
    ...parcial,
  }
}

function montar(datos: TrazaCiegaData) {
  setupFetchMock({ [RUTA]: () => datos })
  return render(<TrazaCiega clave="cibse-2027" itemId="it-1" getToken={getToken} />)
}

function montarError(status: number, detail: unknown) {
  setupFetchMock({ [RUTA]: { ok: false, status, body: () => ({ detail }) } })
  return render(<TrazaCiega clave="cibse-2027" itemId="it-1" getToken={getToken} />)
}

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

describe("TrazaCiega: consigna", () => {
  it("muestra la consigna de la TP y la del ejercicio, rotuladas y en ese orden", async () => {
    montar(traza())
    const tp = await screen.findByRole("region", { name: "Consigna del trabajo práctico" })
    const ej = screen.getByRole("region", { name: "Consigna del ejercicio" })
    expect(within(tp).getByText("suma")).toBeTruthy()
    expect(within(ej).getByText("Usa un bucle for.")).toBeTruthy()
    expect(tp.compareDocumentPosition(ej) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })

  it("TP monolitica: solo la consigna de la TP", async () => {
    montar(traza({ enunciado: { tp_md: "Solo TP.", ejercicio_md: null } }))
    await screen.findByRole("region", { name: "Consigna del trabajo práctico" })
    expect(screen.queryByRole("region", { name: "Consigna del ejercicio" })).toBeNull()
  })
})

describe("TrazaCiega: cada tipo de la lista blanca", () => {
  it("renderiza inicio, lectura, conversacion, codigo, ejecucion, prueba, nota, copia, pegado y fin", async () => {
    montar(traza())
    await screen.findByText("como empiezo?")
    expect(screen.getByText(/Inicio del episodio/)).toBeTruthy()
    expect(screen.getByText(/Lectura de la consigna/)).toBeTruthy()
    expect(screen.getByText(/90 s/)).toBeTruthy()
    expect(screen.getByText("que sabes de bucles?")).toBeTruthy()
    expect(screen.getByText("salida_normal")).toBeTruthy()
    expect(screen.getByText(/1 de 3 pruebas pasaron/)).toBeTruthy()
    expect(screen.getByText(/test_cero/)).toBeTruthy()
    expect(screen.getByText(/4 de 5 pasaron/)).toBeTruthy()
    expect(screen.getByText("me falto el caso negativo")).toBeTruthy()
    expect(screen.getByText(/Intento de copiar: 42 caracteres/)).toBeTruthy()
    expect(screen.getByText(/Intento de pegar: 17 caracteres/)).toBeTruthy()
    expect(screen.getByText("Fin: abandonado")).toBeTruthy()
  })

  it("fin cerrado se distingue de fin abandonado", async () => {
    const t = traza()
    t.elementos = [
      { n: 1, tipo: "inicio", t_seg: 0, k: null, datos: { language: "python" } },
      { n: 2, tipo: "fin_cerrado", t_seg: 10, k: null, datos: {} },
    ]
    montar(t)
    expect(await screen.findByText("Fin: cerrado")).toBeTruthy()
    expect(screen.queryByText("Fin: abandonado")).toBeNull()
  })

  it("localizadores global y por tipo, y tiempo relativo", async () => {
    montar(traza())
    const ejec = await screen.findByTestId("traza-elemento-7")
    expect(within(ejec).getByText("#7")).toBeTruthy()
    expect(within(ejec).getByText("ejecución 1")).toBeTruthy()
    expect(within(ejec).getByText("+1:02:05")).toBeTruthy()
    const msg = screen.getByTestId("traza-elemento-3")
    expect(within(msg).getByText("turno 1")).toBeTruthy()
    expect(within(msg).getByText("+01:05")).toBeTruthy()
    expect(within(screen.getByTestId("traza-elemento-4")).getByText("turno 1")).toBeTruthy()
    expect(within(screen.getByTestId("traza-elemento-6")).getByText("código 2")).toBeTruthy()
    expect(within(screen.getByTestId("traza-elemento-8")).getByText("prueba 1")).toBeTruthy()
    expect(within(screen.getByTestId("traza-elemento-9")).getByText("nota 1")).toBeTruthy()
    expect(within(screen.getByTestId("traza-elemento-2")).getByText("lectura 1")).toBeTruthy()
  })

  it("ejecucion con error: la salida de error aparece con su localizador", async () => {
    montar(traza())
    const ejec = await screen.findByTestId("traza-elemento-7")
    expect(within(ejec).getByText("Salida de error")).toBeTruthy()
    expect(within(ejec).getByText("NameError: y no definida")).toBeTruthy()
  })

  it("dos estados de codigo: la linea cambiada se marca quitada y su reemplazo agregada", async () => {
    montar(traza())
    const segundo = await screen.findByTestId("traza-elemento-6")
    const quitadas = Array.from(segundo.querySelectorAll('[data-diff="quitada"]')).map(
      (n) => n.textContent,
    )
    const agregadas = Array.from(segundo.querySelectorAll('[data-diff="agregada"]')).map(
      (n) => n.textContent,
    )
    expect(quitadas.join("|")).toContain("x = 1")
    expect(agregadas.join("|")).toContain("x = 2")
    expect(
      Array.from(segundo.querySelectorAll('[data-diff="igual"]')).map((n) => n.textContent).join("|"),
    ).toContain("print(x)")
  })
})

describe("TrazaCiega: nada fuera de la lista blanca llega al DOM", () => {
  it("sin JSON crudo, sin claves desconocidas ni sus valores, sin tipos omitidos", async () => {
    const { container } = montar(traza())
    await screen.findByText("como empiezo?")
    const html = container.innerHTML
    expect(html).not.toContain("Payload (JSON)")
    for (const prohibido of [
      "valor_prohibido_kind",
      "prompt_kind",
      "modelo_prohibido",
      "origen_prohibido",
      "motor_prohibido",
      "execution_engine",
      "texto_pegado_prohibido",
      "contenido_preview",
      "overuse",
      "intento_adverso",
      "timeout",
      "{&quot;",
      '{"',
    ]) {
      expect(html, `aparecio "${prohibido}"`).not.toContain(prohibido)
    }
  })

  it("el elemento de tipo desconocido no se renderiza", async () => {
    montar(traza())
    await screen.findByText("como empiezo?")
    expect(screen.queryByTestId("traza-elemento-12")).toBeNull()
  })
})

describe("TrazaCiega: errores", () => {
  it("409 evidencia_alterada: avisa y no muestra eventos", async () => {
    montarError(409, "evidencia_alterada")
    expect(await screen.findByText(/La evidencia de este ítem cambió/)).toBeTruthy()
    expect(screen.queryByTestId(/traza-elemento-/)).toBeNull()
  })

  it("409 traza_version_distinta (detail objeto): avisa", async () => {
    montarError(409, { codigo: "traza_version_distinta" })
    expect(await screen.findByText(/versión de la vista ciega/)).toBeTruthy()
  })

  it("409 enunciado_pendiente: avisa que falta revisar la consigna", async () => {
    montarError(409, "enunciado_pendiente")
    expect(await screen.findByText(/consigna de este ítem todavía no está revisada/)).toBeTruthy()
  })

  it("otro error (500): mensaje generico, sin el cuerpo del error", async () => {
    montarError(500, "traceback secreto_500 en ctr_lectura.py")
    expect(await screen.findByText(/No se pudo cargar la traza/)).toBeTruthy()
    expect(document.body.innerHTML).not.toContain("secreto_500")
  })

  it("502: mensaje generico sin reenviar el cuerpo del error", async () => {
    montarError(502, "upstream: ctr-service 500 detalle_interno")
    expect(await screen.findByText(/registro de episodios no respondió/)).toBeTruthy()
    expect(document.body.innerHTML).not.toContain("detalle_interno")
  })
})
