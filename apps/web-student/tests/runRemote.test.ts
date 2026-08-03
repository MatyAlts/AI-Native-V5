import { afterEach, describe, expect, it, vi } from "vitest"
import { ExecutionQuotaError, ExecutionUnavailableError } from "../src/lib/api"
import { runRemote } from "../src/lib/runRemote"

const RESULTADO_OK = {
  outcome: "completed",
  total: 2,
  passed: 2,
  failed: 0,
  cases: [],
  compile_output: "",
}

/** Encola respuestas para el POST y los GET sucesivos del polling. */
function mockFetch(...respuestas: Array<{ status?: number; body: unknown }>) {
  const fn = vi.fn()
  for (const r of respuestas) {
    fn.mockResolvedValueOnce({
      ok: (r.status ?? 200) < 400,
      status: r.status ?? 200,
      json: async () => r.body,
    })
  }
  vi.stubGlobal("fetch", fn)
  return fn
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe("runRemote", () => {
  it("pide la ejecucion y devuelve el resultado cuando termina", async () => {
    mockFetch(
      { body: { execution_id: "exec-1", quota_remaining: 29 } },
      { body: { execution_id: "exec-1", state: "done", result: RESULTADO_OK } },
    )

    const result = await runRemote({ ejercicioId: "ej-1", sourceCode: "class Main {}" })
    expect(result.outcome).toBe("completed")
    expect(result.passed).toBe(2)
  })

  it("avisa el cambio de estado para que la UI explique la espera", async () => {
    mockFetch(
      { body: { execution_id: "exec-1", quota_remaining: 29 } },
      { body: { state: "queued", result: null } },
      { body: { state: "running", result: null } },
      { body: { state: "done", result: RESULTADO_OK } },
    )

    const estados: string[] = []
    await runRemote({
      ejercicioId: "ej-1",
      sourceCode: "class Main {}",
      onStateChange: (s) => estados.push(s),
    })

    // La espera pasa en CADA corrida, no solo la primera: el alumno tiene que
    // poder distinguir "esta compilando" de "se colgo".
    expect(estados).toEqual(["queued", "running"])
  })

  it("no repite el aviso si el estado no cambia", async () => {
    mockFetch(
      { body: { execution_id: "exec-1", quota_remaining: 29 } },
      { body: { state: "running", result: null } },
      { body: { state: "running", result: null } },
      { body: { state: "done", result: RESULTADO_OK } },
    )

    const estados: string[] = []
    await runRemote({
      ejercicioId: "ej-1",
      sourceCode: "class Main {}",
      onStateChange: (s) => estados.push(s),
    })
    expect(estados).toEqual(["running"])
  })

  it("propaga la cuota agotada sin disfrazarla de error de codigo", async () => {
    // El alumno se pasó del limite: es informacion suya, no un fallo nuestro.
    mockFetch({ status: 429, body: { detail: "Alcanzaste el limite de 30 ejecuciones" } })

    await expect(
      runRemote({ ejercicioId: "ej-1", sourceCode: "class Main {}" }),
    ).rejects.toBeInstanceOf(ExecutionQuotaError)
  })

  it("propaga el servicio caido como error propio, no del alumno", async () => {
    // 503 = las cuotas fallaron CERRADAS (el contador no respondio). No es que
    // el alumno hizo algo mal: confundirlos es lo que la tarea 6.6 evita.
    mockFetch({ status: 503, body: { detail: "El servicio no esta disponible" } })

    await expect(
      runRemote({ ejercicioId: "ej-1", sourceCode: "class Main {}" }),
    ).rejects.toBeInstanceOf(ExecutionUnavailableError)
  })

  it("un estado done sin resultado es fallo nuestro, no del codigo", async () => {
    mockFetch(
      { body: { execution_id: "exec-1", quota_remaining: 29 } },
      { body: { state: "done", result: null } },
    )

    await expect(
      runRemote({ ejercicioId: "ej-1", sourceCode: "class Main {}" }),
    ).rejects.toBeInstanceOf(ExecutionUnavailableError)
  })
})
