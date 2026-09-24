/**
 * BUG-18 (wiring): `throwIfNotOk` interpolaba `detail` directo en un template
 * string. Cuando FastAPI devuelve `detail` como array de errores de
 * validacion (422), eso rendereaba "422: [object Object]" y la info de que
 * campo fallo se perdia para siempre (el string ya quedaba corrompido antes
 * de llegar al catch del form). El fix adjunta el `detail` crudo como
 * propiedad del Error para que `formatApiError` pueda leerlo.
 */
import { afterEach, describe, expect, test, vi } from "vitest"
import { createTareaPractica } from "../src/lib/api"

describe("createTareaPractica ante 422 de FastAPI", () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  test("el error lanzado nunca tiene '[object Object]' en el mensaje", async () => {
    const body = {
      detail: [
        { loc: ["body", "peso"], msg: "el valor debe ser menor o igual a 1", type: "value_error" },
      ],
    }
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify(body), {
          status: 422,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    )

    await expect(createTareaPractica({} as never)).rejects.toSatisfy((err: unknown) => {
      const mensaje = err instanceof Error ? err.message : String(err)
      return !mensaje.includes("[object Object]")
    })
  })

  test("el error lanzado expone el detail crudo (array) como propiedad", async () => {
    const body = {
      detail: [
        { loc: ["body", "peso"], msg: "el valor debe ser menor o igual a 1", type: "value_error" },
      ],
    }
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify(body), {
          status: 422,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    )

    let capturado: unknown
    try {
      await createTareaPractica({} as never)
    } catch (e) {
      capturado = e
    }

    expect((capturado as { detail?: unknown } | undefined)?.detail).toEqual(body.detail)
  })
})
