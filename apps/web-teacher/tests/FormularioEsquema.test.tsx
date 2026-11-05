// Contenido en espanol SIN tildes para evitar problemas de encoding en Windows/cp1252.
/**
 * Formulario de etiquetado definido por el esquema de la version del codebook
 * (`src/views/estudio/FormularioEsquema.tsx`; design D9; spec estudio-codificacion,
 * "Regimen derivado por la regla del codebook" y "Regimen propuesto").
 *
 * Los dos esquemas se construyen aca, a proposito distintos entre si y distintos
 * del codebook v0 (que no puede vivir en el codigo). Si el formulario tuviera algo
 * cableado, uno de los dos lo delataria.
 *
 * Regla central: con regla en el esquema, el panel NO elige el regimen. Lo manda
 * en null, el servidor lo deriva y el panel muestra lo que volvio como "segun la
 * regla". Solo se elige un regimen exento, o cualquiera si el esquema no tiene regla.
 */
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import type {
  EsquemaFormulario,
  EtiquetaGuardada,
  RespuestaFormulario,
} from "../src/lib/estudioApi"
import { FormularioEsquema } from "../src/views/estudio/FormularioEsquema"
import { esperarSelectsLegibles } from "./_selectLegible"

const CON_REGLA: EsquemaFormulario = {
  dimensiones: [
    { clave: "alfa", nombre: "Dimension Alfa", valores: ["si", "no"], cita_requerida_si: ["si"] },
    {
      clave: "beta",
      nombre: "Dimension Beta",
      valores: ["uno", "dos", "tres"],
      cita_requerida_si: [],
    },
  ],
  regimenes: [
    { clave: "rojo", nombre: "Regimen Rojo" },
    { clave: "verde", nombre: "Regimen Verde" },
    { clave: "nada", nombre: "Sin evidencia" },
  ],
  regimen_evidencia_insuficiente: "nada",
  dimensiones_opcionales_si_regimen: ["nada"],
  notas_obligatorias_si_regimen: ["nada"],
  marca_frontera: true,
  confianza: { valores: ["baja", "alta"], obligatoria: false },
  reglas_regimen: [{ regimen: "verde", condicion: [[{ dimension: "alfa", en: ["si"] }]] }],
  regimen_por_defecto: "rojo",
  regimenes_exentos: ["nada"],
}

const SIN_REGLA: EsquemaFormulario = {
  dimensiones: [
    { clave: "gamma", nombre: "Dimension Gamma", valores: ["a", "b"], cita_requerida_si: [] },
  ],
  regimenes: [
    { clave: "x1", nombre: "Equis Uno" },
    { clave: "x2", nombre: "Equis Dos" },
    { clave: "ins", nombre: "Insuficiente" },
  ],
  regimen_evidencia_insuficiente: "ins",
  dimensiones_opcionales_si_regimen: [],
  notas_obligatorias_si_regimen: [],
  marca_frontera: false,
  confianza: null,
  reglas_regimen: [],
  regimen_por_defecto: null,
  regimenes_exentos: ["ins"],
}

function guardada(parcial: Partial<EtiquetaGuardada> = {}): EtiquetaGuardada {
  return {
    respuestas: {},
    regimen: null,
    regimen_regla: null,
    regimen_propuesto: null,
    es_frontera: false,
    confianza: null,
    notas: "",
    updated_at: "2026-11-04T10:00:00Z",
    ...parcial,
  }
}

function errorHttp(status: number, detail: unknown) {
  return Object.assign(new Error(`${status}: x`), { status, detail })
}

afterEach(() => cleanup())

function ultimoEnvio(fn: ReturnType<typeof vi.fn>): RespuestaFormulario {
  const llamadas = fn.mock.calls
  return llamadas[llamadas.length - 1]?.[0] as RespuestaFormulario
}

describe("FormularioEsquema con regla", () => {
  it("renderiza las dimensiones del esquema con sus valores y cita", () => {
    render(<FormularioEsquema esquema={CON_REGLA} inicial={null} onGuardar={vi.fn()} />)
    const alfa = screen.getByRole("group", { name: "Dimension Alfa" })
    expect(within(alfa).getByLabelText("si")).toBeTruthy()
    expect(within(alfa).getByLabelText("no")).toBeTruthy()
    expect(within(alfa).getByLabelText("Cita")).toBeTruthy()
    const beta = screen.getByRole("group", { name: "Dimension Beta" })
    expect(within(beta).getByLabelText("tres")).toBeTruthy()
  })

  it("no ofrece elegir regimenes de la regla: solo el exento", () => {
    render(<FormularioEsquema esquema={CON_REGLA} inicial={null} onGuardar={vi.fn()} />)
    expect(screen.getByLabelText("Marcar como Sin evidencia")).toBeTruthy()
    expect(screen.queryByRole("radio", { name: "Regimen Rojo" })).toBeNull()
    expect(screen.queryByRole("radio", { name: "Regimen Verde" })).toBeNull()
  })

  it("guardado parcial: manda las dimensiones y el regimen en null para que lo derive el servidor", async () => {
    const onGuardar = vi.fn().mockResolvedValue(guardada())
    render(<FormularioEsquema esquema={CON_REGLA} inicial={null} onGuardar={onGuardar} />)
    const alfa = screen.getByRole("group", { name: "Dimension Alfa" })
    fireEvent.click(within(alfa).getByLabelText("si"))
    fireEvent.change(within(alfa).getByLabelText("Cita"), { target: { value: "turno 2" } })
    fireEvent.click(screen.getByRole("button", { name: "Guardar" }))
    await waitFor(() => expect(onGuardar).toHaveBeenCalledTimes(1))
    const enviado = ultimoEnvio(onGuardar)
    expect(enviado.respuestas).toEqual({
      alfa: { valor: "si", cita: "turno 2" },
      beta: { valor: null, cita: null },
    })
    expect(enviado.regimen).toBeNull()
    expect(enviado.regimen_propuesto).toBeNull()
  })

  it("muestra el regimen que devolvio el servidor como resultado de la regla", async () => {
    const onGuardar = vi
      .fn()
      .mockResolvedValue(guardada({ regimen: "verde", regimen_regla: "verde" }))
    render(<FormularioEsquema esquema={CON_REGLA} inicial={null} onGuardar={onGuardar} />)
    fireEvent.click(screen.getByRole("button", { name: "Guardar" }))
    const caja = await screen.findByTestId("regimen-regla")
    expect(caja.textContent).toContain("Regimen Verde")
    expect(caja.textContent).toContain("según la regla")
  })

  it("sin regimen calculable lo dice, en vez de mostrar uno", () => {
    render(<FormularioEsquema esquema={CON_REGLA} inicial={guardada()} onGuardar={vi.fn()} />)
    expect(screen.getByTestId("regimen-regla").textContent).toContain("Todavía no")
  })

  it("con exento elegido manda el exento y muestra aparte lo que da la regla", async () => {
    const onGuardar = vi
      .fn()
      .mockResolvedValue(guardada({ regimen: "nada", regimen_regla: "verde" }))
    render(<FormularioEsquema esquema={CON_REGLA} inicial={null} onGuardar={onGuardar} />)
    fireEvent.click(screen.getByLabelText("Marcar como Sin evidencia"))
    fireEvent.change(screen.getByLabelText("Notas"), { target: { value: "no alcanza" } })
    fireEvent.click(screen.getByRole("button", { name: "Guardar" }))
    await waitFor(() => expect(onGuardar).toHaveBeenCalledTimes(1))
    expect(ultimoEnvio(onGuardar).regimen).toBe("nada")
    const caja = await screen.findByTestId("regimen-regla")
    await waitFor(() => expect(caja.textContent).toContain("Sin evidencia"))
    expect(caja.textContent).toContain("Regimen Verde")
  })

  it("proponer otro regimen exige nota: sin nota no guarda y avisa", async () => {
    const onGuardar = vi.fn().mockResolvedValue(guardada())
    render(<FormularioEsquema esquema={CON_REGLA} inicial={null} onGuardar={onGuardar} />)
    fireEvent.change(screen.getByLabelText("Régimen propuesto"), { target: { value: "rojo" } })
    fireEvent.change(screen.getByLabelText("Notas"), { target: { value: "   " } })
    fireEvent.click(screen.getByRole("button", { name: "Guardar" }))
    expect(await screen.findByText(/La nota es obligatoria para proponer otro régimen/)).toBeTruthy()
    expect(onGuardar).not.toHaveBeenCalled()
  })

  it("proponer otro regimen con nota: manda el propuesto y el regimen sigue en null", async () => {
    const onGuardar = vi
      .fn()
      .mockResolvedValue(
        guardada({ regimen: "verde", regimen_regla: "verde", regimen_propuesto: "rojo" }),
      )
    render(<FormularioEsquema esquema={CON_REGLA} inicial={null} onGuardar={onGuardar} />)
    fireEvent.change(screen.getByLabelText("Régimen propuesto"), { target: { value: "rojo" } })
    fireEvent.change(screen.getByLabelText("Notas"), { target: { value: "la regla no ve X" } })
    fireEvent.click(screen.getByRole("button", { name: "Guardar" }))
    await waitFor(() => expect(onGuardar).toHaveBeenCalledTimes(1))
    const enviado = ultimoEnvio(onGuardar)
    expect(enviado.regimen_propuesto).toBe("rojo")
    expect(enviado.regimen).toBeNull()
    expect(enviado.notas).toBe("la regla no ve X")
  })

  it("frontera y confianza aparecen y viajan cuando el esquema las define", async () => {
    const onGuardar = vi.fn().mockResolvedValue(guardada())
    render(<FormularioEsquema esquema={CON_REGLA} inicial={null} onGuardar={onGuardar} />)
    fireEvent.click(screen.getByLabelText("Caso de frontera"))
    fireEvent.change(screen.getByLabelText("Confianza"), { target: { value: "alta" } })
    fireEvent.click(screen.getByRole("button", { name: "Guardar" }))
    await waitFor(() => expect(onGuardar).toHaveBeenCalledTimes(1))
    expect(ultimoEnvio(onGuardar).es_frontera).toBe(true)
    expect(ultimoEnvio(onGuardar).confianza).toBe("alta")
  })

  it("carga los valores de una etiqueta ya guardada", () => {
    render(
      <FormularioEsquema
        esquema={CON_REGLA}
        inicial={guardada({
          respuestas: { beta: { valor: "dos", cita: "ejecucion 3" } },
          regimen: "rojo",
          regimen_regla: "rojo",
          notas: "nota previa",
        })}
        onGuardar={vi.fn()}
      />,
    )
    const beta = screen.getByRole("group", { name: "Dimension Beta" })
    expect((within(beta).getByLabelText("dos") as HTMLInputElement).checked).toBe(true)
    expect((within(beta).getByLabelText("Cita") as HTMLTextAreaElement).value).toBe("ejecucion 3")
    expect((screen.getByLabelText("Notas") as HTMLTextAreaElement).value).toBe("nota previa")
    expect(screen.getByTestId("regimen-regla").textContent).toContain("Regimen Rojo")
  })
})

describe("FormularioEsquema sin regla", () => {
  it("deja elegir cualquier regimen y lo manda; sin frontera, confianza ni propuesto", async () => {
    const onGuardar = vi.fn().mockResolvedValue(guardada({ regimen: "x2" }))
    render(<FormularioEsquema esquema={SIN_REGLA} inicial={null} onGuardar={onGuardar} />)
    expect(screen.getByRole("group", { name: "Dimension Gamma" })).toBeTruthy()
    fireEvent.click(screen.getByRole("radio", { name: "Equis Dos" }))
    fireEvent.click(screen.getByRole("button", { name: "Guardar" }))
    await waitFor(() => expect(onGuardar).toHaveBeenCalledTimes(1))
    expect(ultimoEnvio(onGuardar).regimen).toBe("x2")
    expect(screen.queryByLabelText("Caso de frontera")).toBeNull()
    expect(screen.queryByLabelText("Confianza")).toBeNull()
    expect(screen.queryByLabelText("Régimen propuesto")).toBeNull()
    expect(screen.queryByTestId("regimen-regla")).toBeNull()
  })
})

describe("FormularioEsquema: errores y faltantes", () => {
  it("un 409 del guardado se muestra con su motivo", async () => {
    const onGuardar = vi.fn().mockRejectedValue(errorHttp(409, "enunciados_pendientes"))
    render(<FormularioEsquema esquema={CON_REGLA} inicial={null} onGuardar={onGuardar} />)
    fireEvent.click(screen.getByRole("button", { name: "Guardar" }))
    expect(await screen.findByRole("alert")).toHaveTextContent(/consignas.*revisar/i)
  })

  it("un 422 del guardado (regimen distinto o nota faltante en el servidor) se muestra", async () => {
    const onGuardar = vi
      .fn()
      .mockRejectedValue(errorHttp(422, "regimen_propuesto requiere nota"))
    render(<FormularioEsquema esquema={CON_REGLA} inicial={null} onGuardar={onGuardar} />)
    fireEvent.click(screen.getByRole("button", { name: "Guardar" }))
    expect(await screen.findByRole("alert")).toHaveTextContent("regimen_propuesto requiere nota")
  })

  it("muestra los faltantes que devolvio el cierre para este item", () => {
    render(
      <FormularioEsquema
        esquema={CON_REGLA}
        inicial={null}
        onGuardar={vi.fn()}
        faltantes={["cita de Dimension Alfa", "regimen"]}
      />,
    )
    const lista = screen.getByRole("list", { name: "Falta para cerrar" })
    expect(within(lista).getByText("cita de Dimension Alfa")).toBeTruthy()
    expect(within(lista).getByText("regimen")).toBeTruthy()
  })

  it("deshabilitado (codificacion cerrada): no deja guardar", () => {
    render(
      <FormularioEsquema esquema={CON_REGLA} inicial={null} onGuardar={vi.fn()} deshabilitado />,
    )
    expect((screen.getByRole("button", { name: "Guardar" }) as HTMLButtonElement).disabled).toBe(
      true,
    )
  })
})

describe("FormularioEsquema: desplegables legibles", () => {
  it("cada select declara fondo y color de letra (Chrome en Windows lo pinta negro si no)", () => {
    const { container } = render(
      <FormularioEsquema esquema={CON_REGLA} inicial={null} onGuardar={vi.fn()} />,
    )
    esperarSelectsLegibles(container)
  })
})
