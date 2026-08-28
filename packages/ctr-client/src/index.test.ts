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

describe("CTRClient — Idempotency-Key (P-17)", () => {
  /** Fetch mock que captura los headers y el status por llamada. */
  function mockFetchWithHeaders(statuses: number[]) {
    let i = 0
    const headers: Array<Record<string, string>> = []
    const impl = vi.fn(async (_input: unknown, init?: { headers?: Record<string, string> }) => {
      headers.push({ ...(init?.headers ?? {}) })
      const status = statuses[Math.min(i, statuses.length - 1)] ?? 202
      i += 1
      return { ok: status >= 200 && status < 300, status } as Response
    })
    return { impl: impl as unknown as CTRFetch, headers }
  }

  function opts(storage: StorageLike, fetchImpl: CTRFetch) {
    return {
      episodeId: "ep-idem",
      storage,
      fetchImpl,
      installLifecycleHooks: false,
      scheduler: (() => 0 as unknown as ReturnType<typeof setTimeout>) as (
        fn: () => void,
        ms: number,
      ) => ReturnType<typeof setTimeout>,
      baseBackoffMs: 0,
      maxBackoffMs: 0,
    }
  }

  it("manda el event_uuid como header Idempotency-Key", async () => {
    const storage = memStorage()
    const { impl, headers } = mockFetchWithHeaders([202])
    const client = new CTRClient(opts(storage, impl))
    client.emit({ event_type: "pestana_perdida", payload: { trigger: "blur" } })
    await client.flush()
    expect(headers).toHaveLength(1)
    expect(headers[0]?.["Idempotency-Key"]).toMatch(
      /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i,
    )
  })

  it("reintenta con el MISMO Idempotency-Key (dedup server-side lo aprovecha)", async () => {
    const storage = memStorage()
    // 1er intento 500 (reintentable), 2do 202 (ok). Mismo item => mismo uuid.
    const { impl, headers } = mockFetchWithHeaders([500, 202])
    const client = new CTRClient(opts(storage, impl))
    client.emit({ event_type: "pestana_perdida", payload: { trigger: "blur" } })
    await client.flush() // intento 1 (500) => frena y agenda retry
    await client.flush() // intento 2 (202) => ok
    expect(headers).toHaveLength(2)
    // El mismo evento reintentado lleva EXACTAMENTE el mismo Idempotency-Key.
    expect(headers[0]?.["Idempotency-Key"]).toBe(headers[1]?.["Idempotency-Key"])
    expect(client.pendingCount()).toBe(0)
  })
})

describe("CTRClient — tests_ejecutados (el evento de mayor señal)", () => {
  /** Fetch mock que captura url, body y headers por llamada. */
  function mockFetchDetallado(statuses: number[]) {
    let i = 0
    const calls: Array<{ url: string; body: unknown; headers: Record<string, string> }> = []
    const impl = vi.fn(
      async (
        input: unknown,
        init?: { body?: unknown; headers?: Record<string, string> },
      ): Promise<Response> => {
        calls.push({
          url: String(input),
          body: init?.body ? JSON.parse(String(init.body)) : undefined,
          headers: { ...(init?.headers ?? {}) },
        })
        const status = statuses[Math.min(i, statuses.length - 1)] ?? 202
        i += 1
        return { ok: status >= 200 && status < 300, status } as Response
      },
    )
    return { impl: impl as unknown as CTRFetch, calls }
  }

  const CONTEOS = {
    test_count_total: 3,
    test_count_passed: 2,
    test_count_failed: 1,
    tests_publicos: 3,
    ejecucion_ms: 120,
  }

  it("va al endpoint /run-tests, no al generico /events/{tipo}", async () => {
    // El backend valida los conteos antes de appendear, asi que este evento
    // tiene ruta propia. Mandarlo al generico seria un 404 => dead-letter.
    const storage = memStorage()
    const { impl, calls } = mockFetchDetallado([202])
    const client = new CTRClient(baseOpts(storage, impl))
    client.testsEjecutados(CONTEOS)
    await client.flush()
    expect(calls).toHaveLength(1)
    expect(calls[0]?.url).toBe("/api/v1/episodes/ep-1/run-tests")
  })

  it("agrega tests_hidden: 0 — los casos ocultos no corren en el navegador", async () => {
    const storage = memStorage()
    const { impl, calls } = mockFetchDetallado([202])
    const client = new CTRClient(baseOpts(storage, impl))
    client.testsEjecutados(CONTEOS)
    await client.flush()
    expect(calls[0]?.body).toEqual({ ...CONTEOS, tests_hidden: 0 })
  })

  it("sobrevive a un 5xx y reintenta con el MISMO Idempotency-Key", async () => {
    // Es lo que separa "el episodio queda mal nivelado" de "no pasa nada": el
    // labeler v1.2.0 deriva N3 vs N4 de este evento.
    const storage = memStorage()
    const { impl, calls } = mockFetchDetallado([500, 202])
    const client = new CTRClient(baseOpts(storage, impl))
    client.testsEjecutados(CONTEOS)
    await client.flush()
    expect(client.pendingCount()).toBe(1) // no se perdio
    await client.flush()
    expect(calls).toHaveLength(2)
    expect(calls[0]?.headers["Idempotency-Key"]).toBe(calls[1]?.headers["Idempotency-Key"])
    expect(client.pendingCount()).toBe(0)
  })

  it("sobrevive a la recarga de la pagina: la cola se retoma del storage", async () => {
    const storage = memStorage()
    const caido = mockFetchDetallado([500])
    const client = new CTRClient(baseOpts(storage, caido.impl))
    client.testsEjecutados(CONTEOS)
    await client.flush()
    client.dispose()

    // Nueva pestaña, mismo episodio: la cola persistida se retoma.
    const revivido = mockFetchDetallado([202])
    const client2 = new CTRClient(baseOpts(storage, revivido.impl))
    await client2.flush()
    expect(revivido.calls).toHaveLength(1)
    expect(revivido.calls[0]?.url).toBe("/api/v1/episodes/ep-1/run-tests")
    expect(client2.pendingCount()).toBe(0)
  })

  it("no se adelanta a un edicion_codigo encolado antes (FIFO)", async () => {
    // El orden importa: `tests_ejecutados` no puede preceder a la edicion del
    // snapshot que se probo.
    const storage = memStorage()
    const { impl, calls } = mockFetchDetallado([202])
    const client = new CTRClient(baseOpts(storage, impl))
    client.edicionCodigo({ snapshot: "x = 1", diff_chars: 5, language: "python" })
    client.testsEjecutados(CONTEOS)
    await client.flush()
    expect(calls.map((c) => c.url)).toEqual([
      "/api/v1/episodes/ep-1/events/edicion_codigo",
      "/api/v1/episodes/ep-1/run-tests",
    ])
  })
})

describe("CTRClient — 429 y 408 son transitorios, no rechazos", () => {
  // La linea `status >= 400 && status < 500 && status !== 408 && status !== 429`
  // sobrevivia intacta a que le sacaran las dos excepciones: los 15 tests
  // pasaban igual. Con esa mutacion un 429 del rate limiter manda el evento a
  // dead-letter PERMANENTE — sin reintento y sin ruido, porque `onDrop` es
  // opcional y nadie lo cablea en produccion. El evento se pierde y la cadena
  // CTR queda con un hueco que nadie ve.
  //
  // Y el escenario no es hipotetico: `CLAUDE.md` documenta que estos frontends
  // llegaron a ~36 req/s contra el rate limiter por un `useEffect` con una dep
  // que cambiaba en cada render. O sea que el 429 ya paso acá.

  it("un 429 (rate limiter) se REINTENTA, no se descarta", async () => {
    const storage = memStorage()
    const dropped: DropReason[] = []
    // Primer intento 429, segundo OK: el evento tiene que llegar.
    const { impl, calls } = mockFetch((_call, i) =>
      i === 0 ? { ok: false, status: 429 } : okResponse(),
    )
    const client = new CTRClient({
      ...baseOpts(storage, impl),
      onDrop: (_e, reason) => dropped.push(reason),
    })
    client.emit({ event_type: "edicion_codigo", payload: { n: 1 } })

    await client.flush()
    expect(dropped).toEqual([])
    expect(client.pendingCount()).toBe(1) // sigue en la cola, esperando

    await client.flush()
    expect(calls).toHaveLength(2)
    expect(dropped).toEqual([])
    expect(client.pendingCount()).toBe(0)
  })

  it("un 408 (timeout) se REINTENTA, no se descarta", async () => {
    const storage = memStorage()
    const dropped: DropReason[] = []
    const { impl, calls } = mockFetch((_call, i) =>
      i === 0 ? { ok: false, status: 408 } : okResponse(),
    )
    const client = new CTRClient({
      ...baseOpts(storage, impl),
      onDrop: (_e, reason) => dropped.push(reason),
    })
    client.emit({ event_type: "codigo_ejecutado", payload: { n: 1 } })

    await client.flush()
    expect(client.pendingCount()).toBe(1)

    await client.flush()
    expect(calls).toHaveLength(2)
    expect(dropped).toEqual([])
    expect(client.pendingCount()).toBe(0)
  })

  it("el 429 reintenta con el MISMO Idempotency-Key", async () => {
    // Si el reintento cambiara la clave, el backend le asignaria un `seq`
    // nuevo y avanzaria el contador de la sesion: hueco en la cadena y
    // episodio `integrity_compromised` (P-17).
    const storage = memStorage()
    const keys: (string | undefined)[] = []
    const impl = vi.fn(async (_input: unknown, init?: { headers?: Record<string, string> }) => {
      keys.push(init?.headers?.["Idempotency-Key"])
      return { ok: keys.length > 1, status: keys.length > 1 ? 202 : 429 } as Response
    }) as unknown as CTRFetch
    const client = new CTRClient(baseOpts(storage, impl))
    client.emit({ event_type: "edicion_codigo", payload: { n: 1 } })

    await client.flush()
    await client.flush()

    expect(keys).toHaveLength(2)
    expect(keys[0]).toBeTruthy()
    expect(keys[1]).toBe(keys[0])
  })

  it("un 429 persistente termina en dead-letter por agotamiento, no por rechazo", async () => {
    // La distincion importa: "exhausted" dice "lo intentamos N veces y no
    // entro"; "rejected" dice "el servidor lo rechazo, no lo mandes mas". Sobre
    // un 429 lo segundo es mentira.
    const storage = memStorage()
    const dropped: DropReason[] = []
    const { impl, calls } = mockFetch(() => ({ ok: false, status: 429 }))
    const client = new CTRClient({
      ...baseOpts(storage, impl),
      maxAttempts: 3,
      onDrop: (_e, reason) => dropped.push(reason),
    })
    client.emit({ event_type: "edicion_codigo", payload: { n: 1 } })
    await client.flush()
    await client.flush()
    await client.flush()

    expect(calls).toHaveLength(3)
    expect(dropped).toEqual(["exhausted"])
  })

  it("los 4xx de negocio vecinos SIGUEN siendo dead-letter inmediato", async () => {
    // La otra mitad del guard: ensanchar la excepcion a todo 4xx tampoco puede
    // pasar en silencio. 400/401/403/404/409/422 son rechazos definitivos —
    // reintentarlos es martillar al servidor con algo que nunca va a entrar.
    for (const status of [400, 401, 403, 404, 409, 422]) {
      const storage = memStorage()
      const dropped: DropReason[] = []
      const { impl, calls } = mockFetch(() => ({ ok: false, status }))
      const client = new CTRClient({
        ...baseOpts(storage, impl),
        onDrop: (_e, reason) => dropped.push(reason),
      })
      client.emit({ event_type: "edicion_codigo", payload: { n: 1 } })
      await client.flush()
      await client.flush()

      expect(calls, `status ${status}`).toHaveLength(1)
      expect(dropped, `status ${status}`).toEqual(["rejected"])
    }
  })
})
