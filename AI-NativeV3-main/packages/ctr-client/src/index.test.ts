import { beforeEach, describe, expect, it, vi } from "vitest"
import {
  CTRClient,
  type CTRFetch,
  type DropReason,
  type QueuedEvent,
  type StorageLike,
} from "./index"

/** Storage en memoria que satisface StorageLike (localStorage subset). */
function memStorage(): StorageLike & { dump(): Map<string, string> } {
  const map = new Map<string, string>()
  return {
    getItem: (k) => map.get(k) ?? null,
    setItem: (k, v) => void map.set(k, v),
    removeItem: (k) => void map.delete(k),
    dump: () => map,
  }
}

interface FetchCall {
  url: string
  body: unknown
}

/** Fetch mock: registra las llamadas en orden y responde segun `responder`. */
function mockFetch(responder: (call: FetchCall, index: number) => { ok: boolean; status: number }) {
  const calls: FetchCall[] = []
  const impl = vi.fn(async (input: unknown, init?: { body?: unknown }) => {
    const url = String(input)
    const body = init?.body ? JSON.parse(String(init.body)) : undefined
    const call: FetchCall = { url, body }
    const res = responder(call, calls.length)
    calls.push(call)
    return { ok: res.ok, status: res.status } as Response
  })
  return { impl: impl as unknown as CTRFetch, calls }
}

const okResponse = () => ({ ok: true, status: 202 })

function baseOpts(storage: StorageLike, fetchImpl: CTRFetch) {
  return {
    episodeId: "ep-1",
    storage,
    fetchImpl,
    installLifecycleHooks: false,
    // Scheduler no-op: en los tests forzamos los reintentos llamando flush() a mano.
    scheduler: (() => 0 as unknown as ReturnType<typeof setTimeout>) as (
      fn: () => void,
      ms: number,
    ) => ReturnType<typeof setTimeout>,
    baseBackoffMs: 0,
    maxBackoffMs: 0,
  }
}

describe("CTRClient — orden append-only", () => {
  let storage: ReturnType<typeof memStorage>
  beforeEach(() => {
    storage = memStorage()
  })

  it("envia los eventos en el mismo orden en que se encolaron (FIFO)", async () => {
    const { impl, calls } = mockFetch(okResponse)
    const client = new CTRClient(baseOpts(storage, impl))

    client.emit({ event_type: "lectura_enunciado", payload: { n: 1 } })
    client.emit({ event_type: "edicion_codigo", payload: { n: 2 } })
    client.emit({ event_type: "codigo_ejecutado", payload: { n: 3 } })

    await client.flush()

    expect(calls.map((c) => (c.body as { n: number }).n)).toEqual([1, 2, 3])
    expect(calls.map((c) => c.url)).toEqual([
      "/api/v1/episodes/ep-1/events/lectura_enunciado",
      "/api/v1/episodes/ep-1/events/edicion_codigo",
      "/api/v1/episodes/ep-1/events/codigo_ejecutado",
    ])
    expect(client.pendingCount()).toBe(0)
  })

  it("single-flight: no envia el evento N+1 hasta que el N fue aceptado", async () => {
    // El 2do evento falla la 1ra vez => la cola debe FRENAR en el 2do,
    // nunca adelantar el 3ro.
    let secondShouldFail = true
    const { impl, calls } = mockFetch((call) => {
      const n = (call.body as { n: number }).n
      if (n === 2 && secondShouldFail) return { ok: false, status: 503 }
      return okResponse()
    })
    const client = new CTRClient(baseOpts(storage, impl))
    client.emit({ event_type: "lectura_enunciado", payload: { n: 1 } })
    client.emit({ event_type: "lectura_enunciado", payload: { n: 2 } })
    client.emit({ event_type: "lectura_enunciado", payload: { n: 3 } })

    await client.flush()
    // Se envio 1 (ok) y 2 (503 => frena). El 3 NO se adelanto.
    expect(calls.map((c) => (c.body as { n: number }).n)).toEqual([1, 2])
    expect(client.pendingCount()).toBe(2) // el 2 y el 3 siguen

    secondShouldFail = false
    await client.flush()
    // Reanuda desde el 2, luego el 3 — orden intacto.
    expect(calls.map((c) => (c.body as { n: number }).n)).toEqual([1, 2, 2, 3])
    expect(client.pendingCount()).toBe(0)
  })
})

describe("CTRClient — no duplica", () => {
  it("un evento aceptado se envia exactamente una vez, aun con flush repetidos", async () => {
    const storage = memStorage()
    const { impl, calls } = mockFetch(okResponse)
    const client = new CTRClient(baseOpts(storage, impl))
    client.emit({ event_type: "anotacion_creada", payload: { contenido: "x" } })

    await client.flush()
    await client.flush()
    await client.flush()

    expect(calls).toHaveLength(1)
  })

  it("tras ACK, el evento se borra de localStorage (una recarga no lo reenvia)", async () => {
    const storage = memStorage()
    const { impl, calls } = mockFetch(okResponse)
    const client = new CTRClient(baseOpts(storage, impl))
    client.emit({ event_type: "anotacion_creada", payload: { contenido: "x" } })
    await client.flush()
    expect(calls).toHaveLength(1)

    // Simula recarga: nuevo cliente, misma storage.
    const { impl: impl2, calls: calls2 } = mockFetch(okResponse)
    const client2 = new CTRClient(baseOpts(storage, impl2))
    await client2.flush()
    expect(calls2).toHaveLength(0)
    expect(client2.pendingCount()).toBe(0)
  })
})

describe("CTRClient — persistencia offline", () => {
  it("la cola sobrevive una recarga y se reenvia en orden al reconectar", async () => {
    const storage = memStorage()
    // 1ra sesion: la red esta caida (fetch rechaza) => todo queda encolado.
    const downFetch = vi.fn(async () => {
      throw new Error("network down")
    }) as unknown as CTRFetch
    const client = new CTRClient(baseOpts(storage, downFetch))
    client.emit({ event_type: "lectura_enunciado", payload: { n: 1 } })
    client.emit({ event_type: "lectura_enunciado", payload: { n: 2 } })
    await client.flush()
    expect(client.pendingCount()).toBe(2)
    // Persistido en localStorage.
    const persisted = JSON.parse(storage.getItem("ctr-queue:ep-1") ?? "[]") as QueuedEvent[]
    expect(persisted.map((e) => (e.payload as { n: number }).n)).toEqual([1, 2])

    // 2da sesion (recarga): red OK.
    const { impl, calls } = mockFetch(okResponse)
    const client2 = new CTRClient(baseOpts(storage, impl))
    expect(client2.pendingCount()).toBe(2)
    await client2.flush()
    expect(calls.map((c) => (c.body as { n: number }).n)).toEqual([1, 2])
    expect(storage.getItem("ctr-queue:ep-1")).toBeNull()
  })
})

describe("CTRClient — dead-letter (no bloquea la cola)", () => {
  it("un 409 (episodio cerrado) se descarta y NO frena a los demas", async () => {
    const storage = memStorage()
    const dropped: Array<{ event: QueuedEvent; reason: DropReason }> = []
    const { impl, calls } = mockFetch((call) => {
      const n = (call.body as { n: number }).n
      if (n === 1) return { ok: false, status: 409 }
      return okResponse()
    })
    const client = new CTRClient({
      ...baseOpts(storage, impl),
      onDrop: (event, reason) => dropped.push({ event, reason }),
    })
    client.emit({ event_type: "lectura_enunciado", payload: { n: 1 } })
    client.emit({ event_type: "lectura_enunciado", payload: { n: 2 } })
    await client.flush()

    expect(calls.map((c) => (c.body as { n: number }).n)).toEqual([1, 2])
    expect(dropped).toHaveLength(1)
    expect(dropped[0]?.reason).toBe("rejected")
    expect(client.pendingCount()).toBe(0)
  })

  it("un 422 (payload invalido) NO se reintenta", async () => {
    const storage = memStorage()
    const { impl, calls } = mockFetch(() => ({ ok: false, status: 422 }))
    const client = new CTRClient(baseOpts(storage, impl))
    client.emit({ event_type: "anotacion_creada", payload: { contenido: "" } })
    await client.flush()
    await client.flush()
    expect(calls).toHaveLength(1) // se intento una vez y se descarto
    expect(client.pendingCount()).toBe(0)
  })

  it("corta a dead-letter tras agotar maxAttempts contra 5xx persistente", async () => {
    const storage = memStorage()
    const dropped: DropReason[] = []
    const { impl, calls } = mockFetch(() => ({ ok: false, status: 500 }))
    const client = new CTRClient({
      ...baseOpts(storage, impl),
      maxAttempts: 3,
      onDrop: (_e, reason) => dropped.push(reason),
    })
    client.emit({ event_type: "lectura_enunciado", payload: { n: 1 } })
    // Cada flush hace 1 intento (scheduler es no-op), luego frena.
    await client.flush()
    await client.flush()
    await client.flush()
    expect(calls).toHaveLength(3)
    expect(dropped).toEqual(["exhausted"])
    expect(client.pendingCount()).toBe(0)
  })
})
