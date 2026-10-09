/**
 * Hallazgo #10 (QA 08/10): "Verificar cadena criptografica" era un <a href>
 * (GET sin Authorization) contra un endpoint POST → pagina de error. Ahora es
 * un boton que hace POST autenticado y muestra el resultado inline.
 */
import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, describe, expect, test, vi } from "vitest"
import { verifyEpisode } from "../src/lib/api"
import { EpisodeTimelineView } from "../src/views/EpisodeTimelineView"

const EP = "11111111-2222-3333-4444-555555555555"
const getToken = async () => "tok"

type VerifyReply = { status: number; body: unknown } | "network"

function stubFetch(verify: VerifyReply) {
  const fn = vi.fn((url: string | URL | Request) => {
    const u = String(url)
    if (u.endsWith("/verify")) {
      if (verify === "network") return Promise.reject(new Error("boom de red"))
      return Promise.resolve(
        new Response(JSON.stringify(verify.body), {
          status: verify.status,
          headers: { "Content-Type": "application/json" },
        }),
      )
    }
    return Promise.resolve(
      new Response(JSON.stringify({ id: EP, estado: "closed", events: [] }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    )
  })
  vi.stubGlobal("fetch", fn)
  return fn
}

afterEach(() => vi.unstubAllGlobals())

describe("verifyEpisode (api)", () => {
  test("hace POST a /audit/episodes/{id}/verify con Bearer", async () => {
    const f = stubFetch({
      status: 200,
      body: {
        episode_id: EP,
        valid: true,
        events_count: 3,
        failing_seq: null,
        integrity_compromised: false,
        message: "Cadena íntegra",
      },
    })
    const r = await verifyEpisode(EP, getToken)
    expect(r.valid).toBe(true)
    const [url, init] = f.mock.calls[0] as [string, RequestInit]
    expect(url).toBe(`/api/v1/audit/episodes/${EP}/verify`)
    expect(init.method).toBe("POST")
    expect((init.headers as Record<string, string>).Authorization).toBe("Bearer tok")
  })

  test("un 403 lanza error con status", async () => {
    stubFetch({ status: 403, body: { detail: "no sos miembro" } })
    await expect(verifyEpisode(EP, getToken)).rejects.toMatchObject({ status: 403 })
  })
})

describe("EpisodeTimelineView — verificar cadena", () => {
  test("ya no es un link GET: es un boton", async () => {
    stubFetch({ status: 200, body: {} })
    render(<EpisodeTimelineView getToken={getToken} initialEpisodeId={EP} />)
    const btn = await screen.findByTestId("timeline-verify")
    expect(btn.tagName).toBe("BUTTON")
    expect(document.querySelector('a[href*="/verify"]')).toBeNull()
  })

  test("cadena integra: muestra cantidad de eventos", async () => {
    stubFetch({
      status: 200,
      body: {
        episode_id: EP,
        valid: true,
        events_count: 12,
        failing_seq: null,
        integrity_compromised: false,
        message: "Cadena íntegra",
      },
    })
    render(<EpisodeTimelineView getToken={getToken} initialEpisodeId={EP} />)
    await userEvent.click(await screen.findByTestId("timeline-verify"))
    const res = await screen.findByTestId("timeline-verify-result")
    expect(res).toHaveTextContent(/íntegra/i)
    expect(res).toHaveTextContent("12")
    expect(res).toHaveAttribute("data-state", "ok")
  })

  test("cadena rota: indica en que evento se rompe", async () => {
    stubFetch({
      status: 200,
      body: {
        episode_id: EP,
        valid: false,
        events_count: 12,
        failing_seq: 7,
        integrity_compromised: true,
        message: "Cadena rota en seq=7",
      },
    })
    render(<EpisodeTimelineView getToken={getToken} initialEpisodeId={EP} />)
    await userEvent.click(await screen.findByTestId("timeline-verify"))
    const res = await screen.findByTestId("timeline-verify-result")
    expect(res).toHaveAttribute("data-state", "broken")
    expect(res).toHaveTextContent(/rota/i)
    expect(res).toHaveTextContent("7")
  })

  test("error de API (403): muestra el error, no un falso 'integra'", async () => {
    stubFetch({ status: 403, body: { detail: "no sos miembro de la comision" } })
    render(<EpisodeTimelineView getToken={getToken} initialEpisodeId={EP} />)
    await userEvent.click(await screen.findByTestId("timeline-verify"))
    const res = await screen.findByTestId("timeline-verify-result")
    expect(res).toHaveAttribute("data-state", "error")
    expect(res).toHaveTextContent(/no sos miembro/i)
    expect(res).not.toHaveTextContent(/íntegra/i)
  })

  test("durante la verificacion el boton queda deshabilitado (loading)", async () => {
    let release: (r: Response) => void = () => {}
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string | URL | Request) =>
        String(url).endsWith("/verify")
          ? new Promise<Response>((res) => {
              release = res
            })
          : Promise.resolve(
              new Response(JSON.stringify({ id: EP, estado: "closed", events: [] }), {
                status: 200,
              }),
            ),
      ),
    )
    render(<EpisodeTimelineView getToken={getToken} initialEpisodeId={EP} />)
    const btn = await screen.findByTestId("timeline-verify")
    await userEvent.click(btn)
    await waitFor(() => expect(btn).toBeDisabled())
    release(
      new Response(
        JSON.stringify({
          episode_id: EP,
          valid: true,
          events_count: 1,
          failing_seq: null,
          integrity_compromised: false,
          message: "ok",
        }),
        { status: 200 },
      ),
    )
    await waitFor(() => expect(btn).not.toBeDisabled())
  })
})
