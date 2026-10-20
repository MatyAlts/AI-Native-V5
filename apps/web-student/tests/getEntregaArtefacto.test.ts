/**
 * Change `alumno-mis-trabajos-corregidos` — cliente de SOLO LECTURA del codigo
 * que el alumno entrego (`GET /api/v1/entregas/{id}/artefacto`, ya existe).
 */
import { afterEach, describe, expect, it, vi } from "vitest"
import { getEntregaArtefacto } from "../src/lib/api"

const ENTREGA_ID = "cccccccc-cccc-cccc-cccc-cccccccccccc"

function stubFetch(status: number, body: unknown) {
  const fn = vi.fn(() =>
    Promise.resolve({
      ok: status >= 200 && status < 300,
      status,
      json: () => Promise.resolve(body),
      text: () => Promise.resolve(JSON.stringify(body)),
    } as Response),
  )
  vi.stubGlobal("fetch", fn)
  return fn
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe("getEntregaArtefacto", () => {
  it("hace GET a /artefacto y devuelve los artefactos tipados", async () => {
    const fn = stubFetch(200, {
      entrega_id: ENTREGA_ID,
      legacy: false,
      artefactos: [
        {
          orden: 1,
          ejercicio_id: "e1",
          episode_id: "ep1",
          codigo: "print(1)",
          language: "python",
          sha256: "abc",
          created_at: "2026-10-01T00:00:00Z",
        },
      ],
    })

    const r = await getEntregaArtefacto(ENTREGA_ID)

    const [url, init] = fn.mock.calls[0] as unknown as [string, RequestInit | undefined]
    expect(url).toBe(`/api/v1/entregas/${ENTREGA_ID}/artefacto`)
    expect((init?.method ?? "GET").toUpperCase()).toBe("GET")
    expect(r.legacy).toBe(false)
    expect(r.artefactos[0]).toMatchObject({ orden: 1, codigo: "print(1)", language: "python" })
  })

  it("un 404 y un 500 tiran errores distinguibles por status", async () => {
    stubFetch(404, {})
    await expect(getEntregaArtefacto(ENTREGA_ID)).rejects.toMatchObject({ status: 404 })
    stubFetch(500, {})
    await expect(getEntregaArtefacto(ENTREGA_ID)).rejects.toMatchObject({ status: 500 })
  })
})
