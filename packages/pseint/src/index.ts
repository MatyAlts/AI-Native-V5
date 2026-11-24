/**
 * Intérprete de PSeInt (HU-030). ESQUELETO DE ACEPTACIÓN: fija el contrato
 * que usan el alumno, el docente y el servidor. El constructor lo reemplaza
 * por la implementación; no cambia los tipos ni las firmas sin acordarlo.
 */

/** Versión del intérprete. El runtime del CTR es `pseint-ts-${VERSION}`. */
export const VERSION = "0.0.0"

export type EstadoEjecucion = "ok" | "error_sintaxis" | "error_ejecucion" | "limite_excedido"

export interface ErrorPseint {
  /** Línea del fuente, contada desde 1. */
  linea: number
  /** Mensaje en castellano, pensado para el alumno. */
  mensaje: string
}

export interface ResultadoEjecucion {
  estado: EstadoEjecucion
  /** Lo que escribió el algoritmo, sin el eco de `Leer`. */
  salida: string
  /** `null` si `estado === "ok"`. */
  error: ErrorPseint | null
}

export interface OpcionesEjecucion {
  /** Se llama una vez por cada valor que pide `Leer`. Devuelve el texto ingresado. */
  leer: () => Promise<string> | string
  /** Recibe la salida a medida que se escribe (para la consola interactiva). */
  escribir?: (texto: string) => void
  /** Tope de instrucciones ejecutadas. Por defecto, `MAX_PASOS_POR_DEFECTO`. */
  maxPasos?: number
}

export const MAX_PASOS_POR_DEFECTO = 1_000_000

/** Revisa la sintaxis sin ejecutar. Lista vacía = sin errores. */
export function verificarSintaxis(_fuente: string): ErrorPseint[] {
  return []
}

/** Ejecuta un algoritmo con `Leer` interactivo. */
export async function ejecutar(_fuente: string, _opciones: OpcionesEjecucion): Promise<ResultadoEjecucion> {
  return { estado: "ok", salida: "", error: null }
}

/**
 * Ejecuta con toda la entrada por adelantado, una línea por valor de `Leer`
 * (casos `stdin_stdout`, Probar y servidor). Si `Leer` pide un valor y la
 * entrada se terminó, es un error de ejecución.
 */
export async function ejecutarConEntrada(
  _fuente: string,
  _entrada: string,
  _opciones?: { maxPasos?: number },
): Promise<ResultadoEjecucion> {
  return { estado: "ok", salida: "", error: null }
}
