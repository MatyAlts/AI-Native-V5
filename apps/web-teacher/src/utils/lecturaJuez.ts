/**
 * Lectura del veredicto del juez del eje fino para la vista del episodio.
 *
 * El backend devuelve `regimen_llm.raw` con DOS formas segun que juez lo
 * emitio (HU-008):
 *   - v1 (`regimen_llm.py`): `verbalizacion/verificacion/justificacion/autonomia`
 *     con `{presente, evidencia}`; `presente` puede ser booleano legado.
 *   - v2/v3 (`juez_v2.py`, `juez_v3.py`): `d1_verbalizacion..d4_autonomia` con
 *     `{valor, localizador, cita}`; D4 con cuatro valores propios; el v3 suma
 *     `es_frontera`/`frontera_entre`.
 *
 * Esta funcion las unifica en lo que la vista dibuja. Si `raw` no tiene
 * ninguna de las dos formas, o el regimen no es uno que la vista conozca,
 * devuelve `null` y la vista muestra "Sin lectura disponible." en vez de
 * romper la pagina (N01). La salida para un veredicto v1 es la misma que la
 * vista armaba antes de HU-008.
 */
import type { RegimenLLM } from "../lib/api"

export interface DimensionLeida {
  nombre: "Verbalizacion" | "Verificacion" | "Justificacion" | "Autonomia"
  /** Valor "a favor" (presente / interlocutor): se dibuja en tinta, no apagado. */
  on: boolean
  estado: string
  /** Cita textual del alumno (v1: `evidencia`). Vacia si no hay. */
  ev: string
  /** Donde esta la cita en la traza (`mensaje 2`). Solo v2/v3. */
  localizador: string
}

export interface LecturaJuez {
  label: string
  dot: string
  dims: DimensionLeida[]
  justificacionGlobal: string
  /** Texto de la marca de frontera del v3; `null` si no es frontera. */
  frontera: string | null
}

const REGIMEN_DISPLAY: Record<string, { label: string; dot: string }> = {
  REFLEXIVA: { label: "Reflexiva", dot: "bg-success" },
  SUPERFICIAL: { label: "Superficial", dot: "bg-warning" },
  PASIVA: { label: "Pasiva", dot: "bg-danger" },
  EVIDENCIA_INSUFICIENTE: { label: "Evidencia insuficiente", dot: "bg-muted" },
}

type Tri = "presente" | "ausente" | "no_evaluable"

// Vocabulario generico para V/E/J.
const DIM_LABEL: Record<Tri, string> = {
  presente: "presente",
  ausente: "ausente",
  no_evaluable: "no evaluable",
}

// Autonomia del v1 conserva su vocabulario propio (interlocutor/oraculo);
// "no evaluable" es el tercer valor, con el mismo tratamiento neutro que
// "ausente" (4.3 del design.md de B2a).
const AUTONOMIA_V1_LABEL: Record<Tri, string> = {
  presente: "interlocutor",
  ausente: "oraculo",
  no_evaluable: "no evaluable",
}

// Autonomia de los jueces v2/v3 (codebook MTAC): cuatro valores.
const AUTONOMIA_MTAC_LABEL: Record<string, string> = {
  interlocutor: "interlocutor",
  oraculo: "oraculo",
  transferencia: "transferencia",
  no_evaluable: "no evaluable",
}

function esObjeto(x: unknown): x is Record<string, unknown> {
  return typeof x === "object" && x !== null && !Array.isArray(x)
}

function texto(x: unknown): string {
  return typeof x === "string" ? x : ""
}

// `presente` puede llegar como booleano (clasificaciones persistidas antes de
// B2a) o como el string trivaluado: el docente solo necesita el valor final.
function triV1(valor: unknown): Tri | null {
  if (typeof valor === "boolean") return valor ? "presente" : "ausente"
  if (valor === "presente" || valor === "ausente" || valor === "no_evaluable") return valor
  return null
}

// Una dimension con un valor que no se reconoce queda con el estado en blanco
// en vez de tirar el veredicto entero: es el borde defensivo que ya cubria la
// vista con el dict crudo pre-B2a (`autonomia: {oraculo: false}` sin normalizar,
// test "dato degradado" de EpisodeNLevelView). La forma del `raw` se decide
// antes, en `lecturaJuez`.
function leerV1(raw: Record<string, unknown>): DimensionLeida[] {
  const claves = [
    ["Verbalizacion", "verbalizacion"],
    ["Verificacion", "verificacion"],
    ["Justificacion", "justificacion"],
    ["Autonomia", "autonomia"],
  ] as const
  return claves.map(([nombre, clave]) => {
    const d = esObjeto(raw[clave]) ? (raw[clave] as Record<string, unknown>) : {}
    const v = triV1(d.presente)
    const labels = nombre === "Autonomia" ? AUTONOMIA_V1_LABEL : DIM_LABEL
    return {
      nombre,
      on: v === "presente",
      estado: v === null ? "" : labels[v],
      ev: texto(d.evidencia),
      localizador: "",
    }
  })
}

function leerMTAC(raw: Record<string, unknown>): DimensionLeida[] {
  const claves = [
    ["Verbalizacion", "d1_verbalizacion"],
    ["Verificacion", "d2_verificacion"],
    ["Justificacion", "d3_justificacion"],
    ["Autonomia", "d4_autonomia"],
  ] as const
  return claves.map(([nombre, clave]) => {
    const d = esObjeto(raw[clave]) ? (raw[clave] as Record<string, unknown>) : {}
    const valor = texto(d.valor)
    const labels: Record<string, string> = nombre === "Autonomia" ? AUTONOMIA_MTAC_LABEL : DIM_LABEL
    return {
      nombre,
      on: nombre === "Autonomia" ? valor === "interlocutor" : valor === "presente",
      estado: labels[valor] ?? "",
      ev: texto(d.cita),
      localizador: texto(d.localizador),
    }
  })
}

function leerFrontera(raw: Record<string, unknown>): string | null {
  if (raw.es_frontera !== true) return null
  const entre = Array.isArray(raw.frontera_entre) ? raw.frontera_entre : []
  const labels = entre.map((r) => REGIMEN_DISPLAY[String(r)]?.label).filter(Boolean)
  return labels.length === 2
    ? `Caso de frontera entre ${labels[0]} y ${labels[1]}`
    : "Caso de frontera"
}

export function lecturaJuez(regimen: RegimenLLM): LecturaJuez | null {
  if (regimen.estado !== "ok" || regimen.regimen === null) return null
  const raw: unknown = regimen.raw
  if (!esObjeto(raw)) return null
  const disp = REGIMEN_DISPLAY[regimen.regimen]
  if (disp === undefined) return null
  // Forma del raw: la decide la dimension D1 de cada juez. Sin ninguna de las
  // dos, no hay nada que dibujar (N01 de HU-008).
  let dims: DimensionLeida[]
  if (esObjeto(raw.d1_verbalizacion)) dims = leerMTAC(raw)
  else if (esObjeto(raw.verbalizacion)) dims = leerV1(raw)
  else return null
  return {
    label: disp.label,
    dot: disp.dot,
    dims,
    justificacionGlobal: texto(raw.justificacion_global),
    frontera: leerFrontera(raw),
  }
}
