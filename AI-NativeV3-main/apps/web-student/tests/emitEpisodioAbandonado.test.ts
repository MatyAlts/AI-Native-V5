/**
 * Tests para emitEpisodioAbandonado (fix QA 2026-06-15 #9).
 *
 * Causa raíz del bug: sin el 3er arg `getToken`, la función caía a
 * `navigator.sendBeacon`, que NO pasa por el override de `window.fetch` que
 * inyecta el `Authorization: Bearer` de Clerk → llegaba sin token → 401 → el
 * evento nunca se appendeaba. Con `getToken` presente debe usar
 * `fetch(..., {keepalive:true})` con el Bearer.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { emitEpisodioAbandonado } from "../src/lib/api"

const EPISODE_ID = "ep-1234"
const PAYLOAD = { reason: "beforeunload" as const, last_activity_seconds_ago: 0 }

describe("emitEpisodioAbandonado", () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it("con getToken: usa fetch keepalive con Authorization Bearer y NO sendBeacon", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 204 } as Response)
    vi.stubGlobal("fetch", fetchMock)
    const beacon = vi.fn().mockReturnValue(true)
    vi.stubGlobal("navigator", { sendBeacon: beacon })

    await emitEpisodioAbandonado(EPISODE_ID, PAYLOAD, async () => "tok-abc")

    expect(beacon).not.toHaveBeenCalled()
    expect(fetchMock).toHaveBeenCalledTimes(1)
    const call = fetchMock.mock.calls[0] as [string, RequestInit]
    const [url, init] = call
    expect(url).toBe(`/api/v1/episodes/${EPISODE_ID}/abandoned`)
    expect(init.method).toBe("POST")
    expect(init.keepalive).toBe(true)
    expect((init.headers as Record<string, string>).Authorization).toBe("Bearer tok-abc")
  })

  it("sin getToken: cae a sendBeacon (no puede mandar Authorization header)", async () => {
    const fetchMock = vi.fn()
    vi.stubGlobal("fetch", fetchMock)
    const beacon = vi.fn().mockReturnValue(true)
    vi.stubGlobal("navigator", { sendBeacon: beacon })

    await emitEpisodioAbandonado(EPISODE_ID, PAYLOAD)

    expect(fetchMock).not.toHaveBeenCalled()
    expect(beacon).toHaveBeenCalledTimes(1)
    const beaconCall = beacon.mock.calls[0] as [string, Blob]
    expect(beaconCall[0]).toBe(`/api/v1/episodes/${EPISODE_ID}/abandoned`)
  })

  it("con getToken pero fetch falla: hace fallthrough a sendBeacon", async () => {
    const fetchMock = vi.fn().mockRejectedValue(new Error("network down"))
    vi.stubGlobal("fetch", fetchMock)
    const beacon = vi.fn().mockReturnValue(true)
    vi.stubGlobal("navigator", { sendBeacon: beacon })

    await emitEpisodioAbandonado(EPISODE_ID, PAYLOAD, async () => "tok-abc")

    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(beacon).toHaveBeenCalledTimes(1)
  })
})
