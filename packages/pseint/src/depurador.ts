/**
 * Ejecución paso a paso y prueba de escritorio (HU-032), sobre el mismo
 * intérprete que `ejecutar`: el intérprete cede `PASO` antes de cada
 * instrucción y acá se decide cuándo seguir. Al terminar, el resultado es el
 * mismo que el de `ejecutar` con los mismos datos.
 *
 * Un paso es UNA instrucción: una asignación, un `Definir`, un `Leer`, un
 * `Escribir`, una llamada a subproceso, o la evaluación de la condición de un
 * `Si`, `Segun`, `Mientras`, `Repetir` o de la cabecera de un `Para` (que se
 * cuenta una vez por vuelta). Entrar a una función o subproceso es entrar a su
 * primera instrucción.
 */
import type { ErrorPseint, OpcionesEjecucion, ResultadoEjecucion } from "./index"
import {
  CEDER,
  Interprete,
  LEER,
  MAX_PASOS_POR_DEFECTO,
  type Marco,
  PASO,
  type PuntoDePaso,
  ceder,
  resultadoCancelado,
  resultadoDeExcepcion,
} from "./interprete"
import { parsear } from "./parser"

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
export function crearDepurador(fuente: string, opciones: OpcionesEjecucion): ResultadoDepurador {
  const { programa, error } = parsear(fuente)
  if (!programa) return { ok: false, error: { linea: error!.linea, mensaje: error!.mensaje } }

  const maxPasos = opciones.maxPasos ?? MAX_PASOS_POR_DEFECTO
  let salidaDelPaso = ""
  const interprete = new Interprete(
    programa,
    (t) => {
      salidaDelPaso += t
      opciones.escribir?.(t)
    },
    maxPasos,
  )
  interprete.depurando = true
  const gen = interprete.principal()
  const filas: FilaPrueba[] = []
  let resultado: ResultadoEjecucion | null = null
  let punto: PuntoDePaso | null = null
  // Lo último que se mostró, para el estado final.
  let ultimoAmbito = programa.nombre
  let ultimoMarco: Marco | null = null

  const terminar = (r: ResultadoEjecucion) => {
    resultado = r
    punto = null
  }
  const fallar = (e: unknown) => {
    const r = resultadoDeExcepcion(e, interprete, maxPasos)
    if (!r) throw e
    terminar(r)
  }

  // Hasta la primera instrucción: antes de ella no hay `Leer` posible.
  try {
    let r = gen.next()
    while (!r.done && r.value !== PASO) r = gen.next()
    if (r.done) terminar({ estado: "ok", salida: interprete.salida, error: null })
    else punto = interprete.punto
  } catch (e) {
    fallar(e)
  }

  /** Corre desde la pausa actual hasta la próxima (o el final). */
  async function avanzar(): Promise<void> {
    if (resultado || !punto) return
    const ejecutado = punto
    salidaDelPaso = ""
    try {
      let r = gen.next()
      for (;;) {
        if (r.done) {
          terminar({ estado: "ok", salida: interprete.salida, error: null })
          break
        }
        if (r.value === PASO) {
          punto = interprete.punto
          break
        }
        if (r.value === LEER) {
          let dato: string | undefined
          try {
            dato = await opciones.leer()
          } catch {
            terminar(resultadoCancelado(interprete))
            break
          }
          r = gen.next(dato)
        } else if (r.value === CEDER) {
          await ceder()
          r = gen.next()
        }
      }
    } catch (e) {
      fallar(e)
    }
    const valores: Record<string, string> = {}
    for (const v of interprete.variables(ejecutado.marco)) valores[v.nombre] = v.valor
    filas.push({
      paso: filas.length + 1,
      linea: ejecutado.linea,
      ambito: ejecutado.ambito,
      valores,
      salida: salidaDelPaso,
    })
    ultimoAmbito = ejecutado.ambito
    ultimoMarco = ejecutado.marco
  }

  function estado(): EstadoDepuracion {
    const actual = punto as PuntoDePaso | null
    const marco = actual?.marco ?? ultimoMarco
    return {
      linea: actual?.linea ?? null,
      ambito: actual?.ambito ?? ultimoAmbito,
      variables: marco ? interprete.variables(marco) : [],
      terminado: resultado !== null,
      resultado,
    }
  }

  return {
    ok: true,
    depurador: {
      estado,
      paso: async () => {
        await avanzar()
        return estado()
      },
      continuar: async () => {
        while (resultado === null) await avanzar()
        return estado()
      },
      filas: () => filas,
    },
  }
}
