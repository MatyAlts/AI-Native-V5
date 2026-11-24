/**
 * Intérprete de PSeInt (HU-030, ADR-064): el contrato que usan el alumno
 * (Ejecutar y Probar en el navegador), el docente (Probar) y el servidor
 * (corrección con IA, vía `cli.ts` dentro de la imagen del sandbox).
 *
 * El perfil es el de PSeInt oficial 20250314 por defecto: ver `PERFIL.md`.
 * Sin DOM ni dependencias de runtime.
 */

import { CEDER, ErrorEjecucion, Interprete, LEER, LimiteExcedido } from "./interprete"
import { parsear } from "./parser"

/** Versión del intérprete. El runtime del CTR es `pseint-ts-${VERSION}`. */
export const VERSION = "1.0.0"

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

/**
 * Tope de instrucciones por ejecución. Alcanza de sobra para los ejercicios
 * de la materia (un Para de 20.000 vueltas usa ~40.000) y corta un ciclo
 * infinito en pocos segundos.
 */
export const MAX_PASOS_POR_DEFECTO = 2_000_000

/** Revisa la sintaxis sin ejecutar. Lista vacía = sin errores. */
export function verificarSintaxis(fuente: string): ErrorPseint[] {
  const { error } = parsear(fuente)
  return error ? [{ linea: error.linea, mensaje: error.mensaje }] : []
}

function ceder(): Promise<void> {
  return new Promise((resolve) => {
    if (typeof setTimeout === "function") setTimeout(resolve, 0)
    else resolve()
  })
}

async function correr(
  fuente: string,
  leer: () => Promise<string | undefined> | string | undefined,
  escribir: ((texto: string) => void) | undefined,
  maxPasos: number,
): Promise<ResultadoEjecucion> {
  const { programa, error } = parsear(fuente)
  if (!programa) {
    return {
      estado: "error_sintaxis",
      salida: "",
      error: { linea: error!.linea, mensaje: error!.mensaje },
    }
  }
  const interprete = new Interprete(programa, (t) => escribir?.(t), maxPasos)
  const gen = interprete.principal()
  try {
    let paso = gen.next()
    while (!paso.done) {
      if (paso.value === LEER) {
        let dato: string | undefined
        try {
          dato = await leer()
        } catch {
          return {
            estado: "error_ejecucion",
            salida: interprete.salida,
            error: { linea: interprete.linea, mensaje: "Se canceló el ingreso de datos." },
          }
        }
        paso = gen.next(dato)
      } else if (paso.value === CEDER) {
        await ceder()
        paso = gen.next()
      }
    }
    return { estado: "ok", salida: interprete.salida, error: null }
  } catch (e) {
    if (e instanceof ErrorEjecucion) {
      return {
        estado: "error_ejecucion",
        salida: interprete.salida,
        error: { linea: e.linea, mensaje: e.mensaje },
      }
    }
    if (e instanceof LimiteExcedido) {
      return {
        estado: "limite_excedido",
        salida: interprete.salida,
        error: {
          linea: e.linea,
          mensaje: `El algoritmo superó el límite de ${maxPasos.toLocaleString("es-AR")} instrucciones y se detuvo. Revisá si tiene un ciclo que nunca termina.`,
        },
      }
    }
    if (e instanceof RangeError) {
      return {
        estado: "error_ejecucion",
        salida: interprete.salida,
        error: {
          linea: interprete.linea,
          mensaje: "Demasiadas llamadas anidadas: revisá que la recursión tenga un caso base.",
        },
      }
    }
    throw e
  }
}

/** Ejecuta un algoritmo con `Leer` interactivo. */
export async function ejecutar(
  fuente: string,
  opciones: OpcionesEjecucion,
): Promise<ResultadoEjecucion> {
  return correr(
    fuente,
    opciones.leer,
    opciones.escribir,
    opciones.maxPasos ?? MAX_PASOS_POR_DEFECTO,
  )
}

/** Separa la entrada en un valor por línea (sin el `\n` final). */
export function lineasDeEntrada(entrada: string): string[] {
  if (entrada === "") return []
  const lineas = entrada.replace(/\r\n?/g, "\n").split("\n")
  if (lineas[lineas.length - 1] === "") lineas.pop()
  return lineas
}

/**
 * Ejecuta con toda la entrada por adelantado, una línea por valor de `Leer`
 * (casos `stdin_stdout`, Probar y servidor). Si `Leer` pide un valor y la
 * entrada se terminó, es un error de ejecución. Es una divergencia deliberada
 * con PSeInt oficial, que en ese caso se queda esperando o lee vacío: un caso
 * de prueba con menos datos de los que pide el algoritmo es un error del
 * algoritmo o del caso, no algo que se pueda dejar pasar en silencio.
 */
export async function ejecutarConEntrada(
  fuente: string,
  entrada: string,
  opciones?: { maxPasos?: number },
): Promise<ResultadoEjecucion> {
  const datos = lineasDeEntrada(entrada)
  let i = 0
  return correr(
    fuente,
    () => (i < datos.length ? datos[i++] : undefined),
    undefined,
    opciones?.maxPasos ?? MAX_PASOS_POR_DEFECTO,
  )
}
