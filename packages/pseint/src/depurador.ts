/**
 * Ejecución paso a paso y prueba de escritorio (HU-032). ESQUELETO DE
 * ACEPTACIÓN: fija el contrato que usa el editor del alumno. El constructor
 * lo reemplaza por la implementación sobre el mismo intérprete; no cambia los
 * tipos ni las firmas sin acordarlo.
 *
 * Un paso es UNA instrucción: una asignación, un `Definir`, un `Leer`, un
 * `Escribir`, una llamada a subproceso, o la evaluación de la condición de un
 * `Si`, `Segun`, `Mientras`, `Repetir` o de la cabecera de un `Para` (que se
 * cuenta una vez por vuelta). Entrar a una función o subproceso es entrar a su
 * primera instrucción.
 */
import type { ErrorPseint, OpcionesEjecucion, ResultadoEjecucion } from "./index"

export interface VariableVisible {
  nombre: string
  /** Valor como lo mostraría `Escribir` ("" si todavía no tiene). Arreglos: `[4, 9, -2]`, matrices `[[1, 2], [3, 4]]`. */
  valor: string
}

export interface EstadoDepuracion {
  /** Línea de la PRÓXIMA instrucción a ejecutar (desde 1); `null` si terminó. */
  linea: number | null
  /** Nombre del algoritmo, función o subproceso donde está la próxima instrucción. */
  ambito: string
  /** Variables del ámbito actual, en el orden en que aparecieron. */
  variables: VariableVisible[]
  terminado: boolean
  /** Resultado final (igual al de `ejecutar`) cuando `terminado`; si no, `null`. */
  resultado: ResultadoEjecucion | null
}

/** Una fila de la prueba de escritorio: el estado DESPUÉS de cada paso. */
export interface FilaPrueba {
  /** 1, 2, 3… */
  paso: number
  /** Línea de la instrucción que se ejecutó. */
  linea: number
  ambito: string
  /** Valor de cada variable del ámbito después del paso ("" sin valor). */
  valores: Record<string, string>
  /** Lo que escribió ese paso ("" si no escribió). */
  salida: string
}

export interface Depurador {
  /** Estado actual sin avanzar. Al crearlo, apunta a la primera instrucción. */
  estado(): EstadoDepuracion
  /** Ejecuta una instrucción. Si ya terminó, no hace nada. */
  paso(): Promise<EstadoDepuracion>
  /** Ejecuta hasta el final (o hasta el límite de pasos). */
  continuar(): Promise<EstadoDepuracion>
  /** Filas de la prueba de escritorio, una por paso ejecutado. */
  filas(): FilaPrueba[]
}

export type ResultadoDepurador =
  | { ok: true; depurador: Depurador }
  | { ok: false; error: ErrorPseint }

/**
 * Prepara la ejecución paso a paso. `leer`, `escribir` y `maxPasos` funcionan
 * igual que en `ejecutar`. Con un error de sintaxis no se crea el depurador.
 */
export function crearDepurador(_fuente: string, _opciones: OpcionesEjecucion): ResultadoDepurador {
  const estado: EstadoDepuracion = {
    linea: null,
    ambito: "",
    variables: [],
    terminado: true,
    resultado: null,
  }
  return {
    ok: true,
    depurador: {
      estado: () => estado,
      paso: async () => estado,
      continuar: async () => estado,
      filas: () => [],
    },
  }
}
