/**
 * Diagramas de flujo de PSeInt (HU-031). ESQUELETO DE ACEPTACIÓN: fija el
 * contrato que usan la consigna y el editor del alumno. El constructor lo
 * reemplaza por la implementación; no cambia los tipos ni las firmas sin
 * acordarlo.
 *
 * Un diagrama es una estructura ya ubicada (con coordenadas): quien lo dibuja
 * (`DiagramaFlujo` en `@platform/ui`) solo pinta, no calcula posiciones. Así
 * el layout se prueba acá, sin DOM.
 */
import type { ErrorPseint } from "./index"

/**
 * Formas, con la convención de PSeInt:
 * - `inicio` / `fin`: terminal ovalado ("Algoritmo nombre" / "FinAlgoritmo").
 * - `entrada`: `Leer` (paralelogramo).
 * - `salida`: `Escribir` (paralelogramo).
 * - `proceso`: asignación o `Definir`/`Dimension` (rectángulo).
 * - `decision`: `Si`, `Mientras`, `Repetir…Hasta Que` y `Segun` (rombo).
 * - `para`: cabecera del `Para` (hexágono).
 * - `llamada`: llamada a un `SubProceso` como instrucción (rectángulo con
 *   doble borde lateral).
 */
export type TipoNodo = "inicio" | "fin" | "entrada" | "salida" | "proceso" | "decision" | "para" | "llamada"

export interface NodoDiagrama {
  id: string
  tipo: TipoNodo
  /** Texto dentro de la forma, tal como lo escribiría PSeInt (p. ej. `Leer n`, `n <- n + 1`, `n > 0`). */
  etiqueta: string
  /** Línea del fuente, desde 1. */
  linea: number
  /** Esquina superior izquierda de la caja que contiene la forma. */
  x: number
  y: number
  ancho: number
  alto: number
}

export interface PuntoDiagrama {
  x: number
  y: number
}

export interface AristaDiagrama {
  desde: string
  hasta: string
  /**
   * "V"/"F" en las salidas de un `Si`, `Mientras` o `Repetir`; el valor del
   * caso (o "De Otro Modo") en las de un `Segun`; vacío en el resto.
   */
  etiqueta: string
  /** Polilínea de la flecha, del borde de `desde` al de `hasta`. Al menos 2 puntos. */
  puntos: PuntoDiagrama[]
}

export interface Diagrama {
  /** Nombre del algoritmo, función o subproceso. */
  nombre: string
  nodos: NodoDiagrama[]
  aristas: AristaDiagrama[]
  /** Tamaño total del dibujo: todos los nodos y puntos entran en [0, ancho] x [0, alto]. */
  ancho: number
  alto: number
}

export type ResultadoDiagrama = { ok: true; diagramas: Diagrama[] } | { ok: false; error: ErrorPseint }

/**
 * Arma un diagrama por algoritmo: primero el `Algoritmo`/`Proceso` principal
 * y después cada `Funcion`/`SubProceso` en el orden del fuente. Con un error
 * de sintaxis no dibuja nada y devuelve el error (línea y mensaje).
 */
export function construirDiagramas(_fuente: string): ResultadoDiagrama {
  return { ok: true, diagramas: [] }
}
