/**
 * El 409 de la reflexion significa "todavia no", y la reflexion NO se pierde.
 *
 * EL REPORTE (2026-09-30, un alumno del piloto por nombre)
 * ---------------------------------------------------------
 *     "No funciona la seccion de reflexion. Cuando uno pone la reflexion sale
 *      un error."
 *     Error enviando reflexion: Error: submit reflection failed: 409
 *
 * LA CAUSA, QUE NO ES "YA ENVIASTE UNA"
 * ---------------------------------------
 * Es una carrera con la consistencia eventual del CTR:
 *
 *   1. El alumno cierra el episodio.
 *   2. El cierre se publica al ctr-service, que responde **202** apenas hace
 *      el XADD a Redis — la persistencia es asincronica.
 *   3. `EpisodePage` abre ESTE modal sobre ese 202.
 *   4. El `partition_worker` drena el evento y recien ahi pone
 *      `estado = "closed"`.
 *   5. Si el alumno escribe rapido y envia antes del paso 4, el endpoint ve el
 *      episodio todavia abierto y devuelve 409.
 *
 * Y el 409 **pierde la reflexion**: el chequeo de estado corta ANTES de
 * publicar al CTR, asi que no se escribe nada. No es un "se guardo y el ACK se
 * perdio" — para la tesis queda un `reflexion_completada` que no existe.
 *
 * El propio `partition_worker` ya tenia anotado el filo, en un comentario sobre
 * no pisar `estado` "para no romper la reflexion final, que exige
 * estado == closed". Estaba visto y sin cerrar.
 *
 * POR QUE REINTENTAR ES SEGURO
 * ------------------------------
 * La `Idempotency-Key` es la misma en todos los intentos (se genera una vez al
 * abrir el modal). Si alguno llegara a persistir, el siguiente recibe el seq ya
 * asignado en vez de emitir un segundo evento.
 */
import { act, render, screen, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { ESPERAS_409_MS, ReflectionModal } from "../src/components/ReflectionModal"

vi.mock("../src/lib/api", async (importOriginal) => {
  const real = await importOriginal<typeof import("../src/lib/api")>()
  return { ...real, submitReflection: vi.fn() }
})

const { submitReflection } = await import("../src/lib/api")

/** Un error con `status`, igual al que arma `submitReflection` ante un !ok. */
function errorHttp(status: number): Error {
  const e = new Error(`submit reflection failed: ${status}`) as Error & { status?: number }
  e.status = status
  return e
}

/** Avanza el reloj falso lo suficiente para agotar las N esperas de reintento. */
async function pasarEsperas(n: number): Promise<void> {
  for (let i = 0; i < n; i++) {
    await act(async () => {
      await vi.advanceTimersByTimeAsync(ESPERAS_409_MS[i] ?? 0)
    })
  }
}

function montar(onClose = vi.fn()) {
  render(<ReflectionModal isOpen episodeId="ep-1" onClose={onClose} />)
  return { onClose }
}

async function apretarEnviar(): Promise<void> {
  await act(async () => {
    screen.getByRole("button", { name: /^Enviar$/ }).click()
  })
}

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true })
  vi.mocked(submitReflection).mockReset()
})

afterEach(() => {
  vi.useRealTimers()
  vi.restoreAllMocks()
})

describe("409 transitorio: el worker todavia no drenó el cierre", () => {
  it("reintenta y la reflexion entra, sin que el alumno haga nada", async () => {
    vi.mocked(submitReflection)
      .mockRejectedValueOnce(errorHttp(409))
      .mockRejectedValueOnce(errorHttp(409))
      .mockResolvedValueOnce({ seq: 7 } as never)

    const { onClose } = montar()
    await apretarEnviar()
    await pasarEsperas(2)

    await waitFor(() => expect(onClose).toHaveBeenCalledWith(true))
    expect(vi.mocked(submitReflection)).toHaveBeenCalledTimes(3)
    // Y nunca le mostramos un error: para el alumno esto fue un envio normal.
    expect(screen.queryByTestId("reflexion-error")).toBeNull()
  })

  it("mientras reintenta le dice por que esta esperando", async () => {
    vi.mocked(submitReflection)
      .mockRejectedValueOnce(errorHttp(409))
      .mockResolvedValueOnce({ seq: 7 } as never)

    montar()
    await apretarEnviar()

    // El cartel aparece ANTES de que termine: sin esto el alumno ve el boton
    // girando hasta cinco segundos y el silencio se lee como "se colgo".
    await waitFor(() => expect(screen.getByTestId("reflexion-esperando-cierre")).toBeTruthy())
  })

  it("reusa la MISMA idempotency key en todos los intentos", async () => {
    vi.mocked(submitReflection)
      .mockRejectedValueOnce(errorHttp(409))
      .mockResolvedValueOnce({ seq: 7 } as never)

    montar()
    await apretarEnviar()
    await pasarEsperas(1)

    await waitFor(() => expect(vi.mocked(submitReflection)).toHaveBeenCalledTimes(2))
    const llamadas = vi.mocked(submitReflection).mock.calls
    const key1 = llamadas[0]?.[2]
    const key2 = llamadas[1]?.[2]
    expect(key1).toBeTruthy()
    // Es lo unico que hace seguro reintentar: con keys distintas, dos intentos
    // que ambos persistieran emitirian dos eventos con el mismo seq y mandarian
    // el episodio a la DLQ.
    expect(key2).toBe(key1)
  })
})

describe("409 que no cede: se lo decimos en castellano", () => {
  it("no le muestra el codigo HTTP pelado", async () => {
    vi.mocked(submitReflection).mockRejectedValue(errorHttp(409))

    montar()
    await apretarEnviar()
    await pasarEsperas(ESPERAS_409_MS.length)

    const error = await waitFor(() => screen.getByTestId("reflexion-error"))
    const texto = error.textContent ?? ""
    // Lo que vio el alumno que lo reporto. No puede volver.
    expect(texto).not.toContain("submit reflection failed")
    expect(texto).not.toContain("409")
    expect(texto).toMatch(/cerrar tu episodio/i)
    // Y lo mas importante: que sepa que su texto sigue ahi.
    expect(texto).toMatch(/no se pierde/i)
  })

  it("agota los reintentos y no insiste para siempre", async () => {
    vi.mocked(submitReflection).mockRejectedValue(errorHttp(409))

    montar()
    await apretarEnviar()
    await pasarEsperas(ESPERAS_409_MS.length)

    await waitFor(() => expect(screen.getByTestId("reflexion-error")).toBeTruthy())
    // 1 intento inicial + un reintento por cada espera. Si reintentara sin
    // techo, un backend caido dejaria el modal girando sin fin.
    expect(vi.mocked(submitReflection)).toHaveBeenCalledTimes(ESPERAS_409_MS.length + 1)
  })
})

describe("otros errores no se tratan como el 409", () => {
  it("un 500 no reintenta: no es 'todavia no', es 'se rompio'", async () => {
    vi.mocked(submitReflection).mockRejectedValue(errorHttp(500))

    montar()
    await apretarEnviar()

    const error = await waitFor(() => screen.getByTestId("reflexion-error"))
    expect(vi.mocked(submitReflection)).toHaveBeenCalledTimes(1)
    expect(error.textContent ?? "").toMatch(/no se pierde/i)
  })
})

describe("doble click (patron NB-11)", () => {
  it("dos clicks seguidos mandan UN solo POST", async () => {
    let resolver: ((v: unknown) => void) | null = null
    vi.mocked(submitReflection).mockImplementation(
      () =>
        new Promise((r) => {
          resolver = r
        }) as never,
    )

    montar()
    // Los dos clicks en el MISMO tick: es el caso que el guard por state no
    // atrapa, porque `submitting` todavia no se re-rendereo.
    await act(async () => {
      const boton = screen.getByRole("button", { name: /^Enviar$/ })
      boton.click()
      boton.click()
    })

    expect(vi.mocked(submitReflection)).toHaveBeenCalledTimes(1)
    await act(async () => {
      resolver?.({ seq: 7 })
    })
  })
})
