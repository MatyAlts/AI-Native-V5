/**
 * Ejecucion server-side: pedir + esperar el resultado (tareas 6.1 y 6.2).
 *
 * Vive en `lib/` y no dentro de `CodeEditor.tsx` por el mismo motivo que
 * `pyodideError.ts`: para ser testeable sin arrastrar el import de
 * `monaco-editor`, que en test no resuelve porque se carga por CDN.
 *
 * El servicio responde de inmediato con un identificador y el resultado se
 * consulta aparte (D2 del design). Compilar y arrancar una JVM no es
 * instantaneo, y con una comision entera ejecutando en la misma ventana de dos
 * minutos la cola puede tardar: una peticion sincrona dejaria el editor
 * congelado sin poder distinguir "esta compilando" de "se colgo".
 */

import {
  type ExecutionResult,
  ExecutionUnavailableError,
  type TokenGetter,
  getExecution,
  requestExecution,
} from "./api"

/** Cada cuanto se pregunta por el resultado. */
const POLL_INTERVAL_MS = 700

/**
 * Techo de espera. Por encima de esto se asume que algo se rompio del lado del
 * servidor: el limite de wall time por corrida es bastante menor, asi que si
 * pasamos esto no es que el codigo del alumno sea lento.
 */
const POLL_TIMEOUT_MS = 90_000

export interface RunRemoteOptions {
  ejercicioId: string
  sourceCode: string
  /** Episodio al que pertenece la corrida.
   *
   * Es lo que le permite al execution-service emitir `tests_ejecutados` al CTR.
   * Sin esto el evento NO se emite y el episodio queda sin la señal que el
   * labeler usa para separar N3 de N4 — que es como Java estuvo generando
   * episodios no comparables con los de Python.
   *
   * Opcional porque el panel del docente prueba ejercicios fuera de todo
   * episodio, y esa corrida no es actividad de ningún alumno. */
  episodeId?: string | undefined
  /** Comision del episodio, para la habilitacion progresiva del backend
   * (`EXECUTION_ENABLED_COMISIONES`). Opcional por el mismo motivo que
   * `episodeId`: el panel del docente prueba fuera de toda comision — y por eso
   * el backend exime al staff del filtro, si no quedaria sin poder probar
   * durante el rollout. */
  comisionId?: string | undefined
  // `| undefined` explicito: el repo usa `exactOptionalPropertyTypes`.
  getToken?: TokenGetter | undefined
  /** Se llama cuando la corrida pasa de encolada a ejecutandose, para que la UI
   * pueda cambiar el texto de espera. */
  onStateChange?: ((state: "queued" | "running") => void) | undefined
  /** Cortocircuito para tests. */
  signal?: AbortSignal | undefined
}

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms))

/**
 * Pide una ejecucion y espera su resultado.
 *
 * Propaga `ExecutionQuotaError` (el alumno se paso del limite) y
 * `ExecutionUnavailableError` (el servicio no esta) sin traducirlas: el caller
 * las distingue para mostrar mensajes distintos. Confundir "no hay entorno" con
 * "tu codigo falla" es exactamente lo que la tarea 6.6 pide evitar.
 */
export async function runRemote(opts: RunRemoteOptions): Promise<ExecutionResult> {
  const { execution_id } = await requestExecution(
    {
      ejercicio_id: opts.ejercicioId,
      source_code: opts.sourceCode,
      ...(opts.episodeId ? { episode_id: opts.episodeId } : {}),
      ...(opts.comisionId ? { comision_id: opts.comisionId } : {}),
    },
    opts.getToken,
  )

  const deadline = Date.now() + POLL_TIMEOUT_MS
  let ultimoEstado: "queued" | "running" | null = null

  while (Date.now() < deadline) {
    if (opts.signal?.aborted) throw new ExecutionUnavailableError("Ejecucion cancelada")

    const status = await getExecution(execution_id, opts.getToken)

    if (status.state !== "done") {
      if (status.state !== ultimoEstado) {
        ultimoEstado = status.state
        opts.onStateChange?.(status.state)
      }
      await sleep(POLL_INTERVAL_MS)
      continue
    }

    if (!status.result) {
      // Estado `done` sin resultado no deberia pasar; si pasa es del lado del
      // servidor, no del codigo del alumno.
      throw new ExecutionUnavailableError("La ejecucion termino sin resultado")
    }
    return status.result
  }

  throw new ExecutionUnavailableError(
    "La ejecucion tardo mas de lo esperado. Volve a intentar en un momento.",
  )
}
