/**
 * Aceptacion HU-016, ronda de arreglos (orquestador, antes de corregir; el
 * constructor no la modifica). Sale de la verificacion independiente del PR
 * #147 (22/11). Juani: "vos terminas todo entonces".
 *
 * R04  Al entregar, solo se muestra tal cual el texto del servidor que esta
 *      pensado para el alumno (plazo, ejercicios incompletos, falta el codigo);
 *      cualquier otro rechazo da un mensaje generico, sin estados internos ni
 *      textos de autorizacion.
 * R05  La entrega al salir de una TP de un solo ejercicio distingue el plazo
 *      vencido: `enviarEntregaAlSalir` devuelve "vencida" (no "error").
 */
import { afterEach, describe, expect, it, vi } from "vitest"
import { ApiError } from "../src/lib/api"
import { enviarEntregaAlSalir } from "../src/lib/entregaAlSalir"
import { mensajeAlEntregar } from "../src/utils/mensajesPlazo"

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe("HU-016 · ronda · mensajes al entregar", () => {
  it.each([
    [409, "No se puede enviar una entrega en estado 'graded'"],
    [403, "Permiso denegado: create sobre entrega"],
    [401, "Missing auth headers (X-User-Id, X-Tenant-Id)"],
  ])("R04: %i con texto interno da un mensaje generico", (status, detail) => {
    const msg = mensajeAlEntregar(new ApiError("submit entrega", status, detail))
    expect(msg).not.toContain(detail)
    expect(msg).toMatch(/no se pudo/i)
  })

  it.each([
    [409, "Venció el plazo de entrega de esta TP."],
    [422, "Ejercicios incompletos: [2]. Completa todos antes de entregar."],
    [422, "Falta el código de los ejercicios: [1]. Abrí cada ejercicio una vez antes de entregar."],
  ])("R04: %i pensado para el alumno se muestra", (status, detail) => {
    const msg = mensajeAlEntregar(new ApiError("submit entrega", status, detail))
    expect(msg).toContain(detail.split(":")[0])
  })
})

describe("HU-016 · ronda · entrega al salir", () => {
  it("R05: con el plazo vencido devuelve 'vencida'", async () => {
    const respuestas: Record<string, () => Response> = {
      "/api/v1/episodes/": () =>
        new Response(
          JSON.stringify({
            estado: "closed",
            tarea_practica_id: "t",
            comision_id: "c",
            last_code_snapshot: "print(1)",
          }),
        ),
      "/submit": () =>
        new Response(JSON.stringify({ detail: "Venció el plazo de entrega de esta TP." }), {
          status: 409,
        }),
      "/api/v1/entregas": () =>
        new Response(JSON.stringify({ id: "e1", estado: "draft", ejercicio_estados: [] })),
      "/api/v1/tareas-practicas/": () => new Response(JSON.stringify({ language: "python" })),
    }
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        const k = Object.keys(respuestas).find((p) => String(url).includes(p))
        return k ? respuestas[k]?.() : new Response("{}", { status: 404 })
      }),
    )
    expect(await enviarEntregaAlSalir("ep1")).toBe("vencida")
  })
})
