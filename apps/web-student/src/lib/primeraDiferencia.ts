/**
 * Primer carácter distinto entre la salida esperada y la obtenida (HU-009 C11).
 *
 * En la prueba 2 del 20/11 un alumno escribió "º" (ordinal, U+00BA) donde el
 * test esperaba "°" (grado, U+00B0): Probar fallaba y ESPERADO y OBTENIDO se
 * veían idénticos. Esta función dice dónde está la primera diferencia y qué
 * carácter es cada uno, con su código, para que se vea lo que el ojo no ve.
 *
 * Compara las salidas YA NORMALIZADAS con la misma regla que decide el
 * veredicto (`normalizarSalida`): así no marca un espacio al final o una línea
 * vacía que la comparación perdona. Recorre por código Unicode, no por unidad
 * UTF-16, para que un emoji o un carácter fuera del plano básico cuente uno.
 */
import { normalizarSalida } from "./comparacionSalida"

export interface Diferencia {
  /** Línea de la diferencia (desde 1) cuando lo esperado tiene más de una. */
  linea: number | null
  /** Posición dentro de la línea (o del texto, si es una sola), desde 1. */
  posicion: number
  /** Carácter esperado en esa posición; null si lo esperado ya terminó. */
  esperado: string | null
  /** Carácter obtenido en esa posición; null si la salida ya terminó. */
  obtenido: string | null
}

export function primeraDiferencia(esperado: string, obtenido: string): Diferencia | null {
  const a = Array.from(normalizarSalida(esperado))
  const b = Array.from(normalizarSalida(obtenido))
  const largo = Math.max(a.length, b.length)
  let i = 0
  while (i < largo && a[i] === b[i]) i++
  if (i === largo) return null

  let linea = 1
  let inicioLinea = 0
  for (let k = 0; k < i; k++) {
    if (a[k] === "\n") {
      linea++
      inicioLinea = k + 1
    }
  }
  const variasLineas = a.includes("\n")
  return {
    linea: variasLineas ? linea : null,
    posicion: i - inicioLinea + 1,
    esperado: a[i] ?? null,
    obtenido: b[i] ?? null,
  }
}

export function codigoUnicode(c: string): string {
  const cp = c.codePointAt(0) ?? 0
  return `U+${cp.toString(16).toUpperCase().padStart(4, "0")}`
}

const NOMBRES: Record<string, string> = {
  " ": "un espacio",
  "\n": "un salto de línea",
  "\t": "una tabulación",
}

function caracter(c: string): string {
  return `${NOMBRES[c] ?? c} (${codigoUnicode(c)})`
}

/** Texto para el alumno: dónde está la diferencia y qué carácter es cada uno.
 *  No repite "Esperado" ni "Obtenido": son las etiquetas de las filas de
 *  arriba y la pantalla las tiene que seguir mostrando una sola vez. */
export function describirDiferencia(d: Diferencia): string {
  const donde =
    d.linea !== null ? `línea ${d.linea}, posición ${d.posicion}` : `posición ${d.posicion}`
  if (d.esperado !== null && d.obtenido !== null) {
    return `${donde}: se esperaba ${caracter(d.esperado)} y salió ${caracter(d.obtenido)}`
  }
  if (d.esperado !== null) {
    return `${donde}: tu salida termina antes; se esperaba ${caracter(d.esperado)}`
  }
  // d.obtenido !== null: lo esperado ya terminó y la salida sigue.
  return `${donde}: tu salida sigue después del final, con ${caracter(d.obtenido as string)}`
}
