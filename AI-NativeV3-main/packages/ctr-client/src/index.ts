/**
 * Cliente del CTR para los frontends (P-17).
 *
 * PROBLEMA QUE RESUELVE
 * ---------------------
 * Hoy web-student emite cada evento CTR con un `fetch` a mano y, si la request
 * falla (red caida, backend 5xx), el evento se pierde en silencio. Para la
 * trazabilidad de la tesis, perder eventos del CTR es grave.
 *
 * Este cliente encola cada evento en una cola persistente (localStorage), lo
 * envia al backend y, ante una falla transitoria, lo reintenta con backoff sin
 * perderlo. La cola sobrevive recargas de pagina y modo offline.
 *
 * INVARIANTES QUE PRESERVA (append-only del CTR, ADR-010)
 * -------------------------------------------------------
 * 1. ORDEN por episodio. El backend asigna `seq` en el ORDEN DE LLEGADA
 *    (`SessionState.next_seq()` incrementa un contador de sesion). Por eso el
 *    flush es SINGLE-FLIGHT y FIFO: nunca se envia el evento N+1 antes de que
 *    el N haya sido aceptado. Un solo POST en vuelo a la vez => el servidor ve
 *    los eventos de esta cola en el mismo orden en que se encolaron.
 * 2. NO duplicar. Un evento se remueve de la cola (memoria + localStorage)
 *    recien despues del ACK 2xx. Los reintentos reenvian el MISMO item (mismo
 *    `payload`), nunca uno nuevo.
 * 3. NO reordenar / NO mutar payloads. La cola es un array FIFO; el payload se
 *    serializa una sola vez al encolar y no se toca en los reintentos.
 *
 * LIMITE DE IDEMPOTENCIA (documentado a proposito)
 * ------------------------------------------------
 * Los endpoints por-evento del tutor-service NO deduplican por `event_uuid`
 * (ver docstrings de `apps/tutor-service/.../routes/episodes.py`: "el cliente
 * NO debe reintentar en error de red — generara una segunda fila con seq
 * distinto"). Este cliente MINIMIZA el riesgo de duplicado:
 *   - Reintenta SOLO ante fallas donde el servidor tipicamente NO persistio:
 *     error de red (fetch rechaza), 5xx, 408, 429.
 *   - NO reintenta 4xx de negocio (409 episodio cerrado, 422 invalido): esos
 *     eventos no son apendables y se descartan a dead-letter (con callback,
 *     nunca en silencio).
 * La unica ventana residual de duplicado es "el servidor persistio pero el ACK
 * se perdio / el tab murio antes de borrar de localStorage". Cerrarla por
 * completo exige un `Idempotency-Key` server-side (fuera del alcance de este
 * paquete; anotado como deuda). Cada item lleva `event_uuid` justamente para
 * habilitar esa dedup del lado del backend en el futuro.
 */

/** Tipos de evento CTR que el frontend puede emitir al tutor-service.
 * Cada uno mapea 1:1 a `POST /api/v1/episodes/{id}/events/{event_type}`. */
export type CTRClientEventType =
  | "codigo_ejecutado"
  | "edicion_codigo"
  | "lectura_enunciado"
  | "anotacion_creada"
  | "pestana_perdida"
  | "pestana_recuperada"
  | "copia_intentada"
  | "pega_intentada"

export interface CTREventInput {
  event_type: CTRClientEventType
  payload: Record<string, unknown>
}

/** Item encolado. `event_uuid` es correlacion cliente (y semilla para una
 * futura dedup server-side). `attempts` cuenta reintentos para el backoff y el
 * corte a dead-letter. */
export interface QueuedEvent extends CTREventInput {
  event_uuid: string
  enqueued_at: string
  attempts: number
}

/** Subconjunto de Web Storage que usamos. `localStorage` lo satisface; en
 * tests se inyecta un Map en memoria. */
export interface StorageLike {
  getItem(key: string): string | null
  setItem(key: string, value: string): void
  removeItem(key: string): void
}

export type CTRFetch = typeof fetch

/** Razon por la que un evento termino en dead-letter (descartado sin reenvio).
 * `rejected` = 4xx de negocio (episodio cerrado/invalido). `exhausted` =
 * agoto los reintentos. */
export type DropReason = "rejected" | "exhausted"

export interface CTRClientOptions {
  /** Episodio al que pertenecen los eventos. Aisla la cola en localStorage. */
  episodeId: string
  /** Base del API. Default "" => URL relativa `/api/v1/...`, que en web-student
   * pasa por el interceptor de fetch (P-18) que inyecta el Bearer. */
  apiBase?: string
  storage?: StorageLike
  fetchImpl?: CTRFetch
  /** Si se provee, agrega `Authorization: Bearer <token>`. En web-student NO
   * hace falta (el interceptor global lo agrega); util para otros consumidores. */
  getAuthToken?: () => Promise<string | null>
  /** Reintentos maximos antes de dead-letter un item envenenado (para no
   * bloquear la cola entera indefinidamente). Default 8. */
  maxAttempts?: number
  baseBackoffMs?: number
  maxBackoffMs?: number
  /** Inyectable para tests deterministas. Default setTimeout. */
  scheduler?: (fn: () => void, ms: number) => ReturnType<typeof setTimeout>
  /** Callback cuando un evento se descarta (dead-letter). Nunca es silencioso. */
  onDrop?: (event: QueuedEvent, reason: DropReason) => void
  /** Instala listeners `online` / `visibilitychange` para flush automatico.
   * Default true. En tests o SSR conviene false. */
  installLifecycleHooks?: boolean
}

const QUEUE_KEY_PREFIX = "ctr-queue:"
const DEFAULT_MAX_ATTEMPTS = 8
const DEFAULT_BASE_BACKOFF_MS = 1000
const DEFAULT_MAX_BACKOFF_MS = 30000

type SendResult = "ok" | "retry" | "drop"

function noopStorage(): StorageLike {
  const map = new Map<string, string>()
  return {
    getItem: (k) => map.get(k) ?? null,
    setItem: (k, v) => {
      map.set(k, v)
    },
    removeItem: (k) => {
      map.delete(k)
    },
  }
}

function resolveStorage(injected?: StorageLike): StorageLike {
  if (injected) return injected
  try {
    if (typeof globalThis !== "undefined" && globalThis.localStorage) {
      return globalThis.localStorage
    }
  } catch {
    // Acceso a localStorage puede tirar en modo privado / sandbox. Degradamos.
  }
  return noopStorage()
}

export class CTRClient {
  private queue: QueuedEvent[] = []
  private flushPromise: Promise<void> | null = null
  private retryTimer: ReturnType<typeof setTimeout> | null = null
  private disposed = false

  private readonly episodeId: string
  private readonly apiBase: string
  private readonly storage: StorageLike
  private readonly storageKey: string
  private readonly fetchImpl: CTRFetch
  private readonly getAuthToken: (() => Promise<string | null>) | undefined
  private readonly maxAttempts: number
  private readonly baseBackoffMs: number
  private readonly maxBackoffMs: number
  private readonly scheduler: (fn: () => void, ms: number) => ReturnType<typeof setTimeout>
  private readonly onDrop: (event: QueuedEvent, reason: DropReason) => void
  private readonly lifecycleHooks: boolean
  private onlineHandler: (() => void) | null = null
  private visibilityHandler: (() => void) | null = null

  constructor(options: CTRClientOptions) {
    this.episodeId = options.episodeId
    this.apiBase = options.apiBase ?? ""
    this.storage = resolveStorage(options.storage)
    this.storageKey = `${QUEUE_KEY_PREFIX}${options.episodeId}`
    // Lazy: resuelve globalThis.fetch en cada llamada, no en construccion. En
    // web-student el fetch esta monkeypatcheado (interceptor P-18 que inyecta el
    // Bearer); capturarlo tarde garantiza usar la version parcheada vigente.
    this.fetchImpl =
      options.fetchImpl ?? ((input, init) => globalThis.fetch(input as RequestInfo, init))
    this.getAuthToken = options.getAuthToken
    this.maxAttempts = options.maxAttempts ?? DEFAULT_MAX_ATTEMPTS
    this.baseBackoffMs = options.baseBackoffMs ?? DEFAULT_BASE_BACKOFF_MS
    this.maxBackoffMs = options.maxBackoffMs ?? DEFAULT_MAX_BACKOFF_MS
    this.scheduler = options.scheduler ?? ((fn, ms) => setTimeout(fn, ms))
    this.onDrop = options.onDrop ?? (() => {})
    this.lifecycleHooks = options.installLifecycleHooks ?? true

    this.queue = this.loadQueue()
    if (this.lifecycleHooks) this.installLifecycleHooks()
    // Si quedaron eventos de una sesion anterior (offline / crash), drenar.
    if (this.queue.length > 0) void this.flush()
  }

  /** Encola un evento generico y agenda un flush. */
  emit(input: CTREventInput): void {
    if (this.disposed) return
    const event: QueuedEvent = {
      event_type: input.event_type,
      payload: input.payload,
      event_uuid: crypto.randomUUID(),
      enqueued_at: new Date().toISOString(),
      attempts: 0,
    }
    this.queue.push(event)
    this.persist()
    void this.flush()
  }

  // ── Helpers tipados por tipo de evento (azucar sobre emit) ─────────────
  codigoEjecutado(payload: {
    code: string
    stdout: string
    stderr: string
    duration_ms: number
  }): void {
    this.emit({ event_type: "codigo_ejecutado", payload })
  }

  edicionCodigo(payload: {
    snapshot: string
    diff_chars: number
    language: string
    origin?: "student_typed" | "copied_from_tutor" | "pasted_external" | null
  }): void {
    this.emit({ event_type: "edicion_codigo", payload })
  }

  lecturaEnunciado(payload: { duration_seconds: number }): void {
    this.emit({ event_type: "lectura_enunciado", payload })
  }

  anotacionCreada(payload: { contenido: string }): void {
    this.emit({ event_type: "anotacion_creada", payload })
  }

  pestanaPerdida(payload: { trigger: "visibilitychange" | "blur" }): void {
    this.emit({ event_type: "pestana_perdida", payload })
  }

  pestanaRecuperada(payload: { tiempo_fuera_segundos: number }): void {
    this.emit({ event_type: "pestana_recuperada", payload })
  }

  copiaIntentada(payload: {
    seleccion_chars: number
    metodo: "shortcut" | "menu_contextual"
  }): void {
    this.emit({ event_type: "copia_intentada", payload })
  }

  pegaIntentada(payload: {
    contenido_longitud: number
    contenido_preview: string
    metodo: "shortcut" | "menu_contextual" | "drag_drop"
  }): void {
    this.emit({ event_type: "pega_intentada", payload })
  }

  /** Cantidad de eventos pendientes de ACK. */
  pendingCount(): number {
    return this.queue.length
  }

  /**
   * Drena la cola en orden FIFO, un POST a la vez (single-flight).
   *
   * - 2xx           => remueve el head y sigue.
   * - 4xx negocio   => dead-letter (onDrop "rejected") y sigue. Un evento no
   *                    apendable (409/422) no debe bloquear a los siguientes.
   * - red/5xx/408/429 => reintentable: incrementa `attempts`. Si supero
   *                    `maxAttempts` => dead-letter "exhausted" y sigue; si no,
   *                    FRENA (preserva orden) y agenda un reintento con backoff.
   *
   * Resuelve cuando no puede avanzar mas (cola vacia o head en espera de
   * backoff). Single-flight: si ya hay un drenaje en curso, las llamadas
   * concurrentes comparten la MISMA promesa (awaitear flush() espera al drenaje
   * real, no retorna antes de tiempo). Esto garantiza un solo POST en vuelo.
   */
  flush(): Promise<void> {
    if (this.disposed) return Promise.resolve()
    if (this.flushPromise) return this.flushPromise
    this.flushPromise = this.drain().finally(() => {
      this.flushPromise = null
    })
    return this.flushPromise
  }

  private async drain(): Promise<void> {
    while (this.queue.length > 0) {
      const head = this.queue[0]
      if (!head) break
      const result = await this.send(head)
      if (result === "ok") {
        this.queue.shift()
        this.persist()
        continue
      }
      if (result === "drop") {
        this.queue.shift()
        this.persist()
        this.onDrop(head, "rejected")
        continue
      }
      // retry
      head.attempts += 1
      this.persist()
      if (head.attempts >= this.maxAttempts) {
        this.queue.shift()
        this.persist()
        this.onDrop(head, "exhausted")
        continue
      }
      this.scheduleRetry(head.attempts)
      break
    }
  }

  /** Libera listeners y timers. La cola persistida NO se borra: se retoma en
   * la proxima construccion con el mismo episodeId. */
  dispose(): void {
    this.disposed = true
    if (this.retryTimer) {
      clearTimeout(this.retryTimer)
      this.retryTimer = null
    }
    this.removeLifecycleHooks()
  }

  // ── Internos ───────────────────────────────────────────────────────────

  private async send(event: QueuedEvent): Promise<SendResult> {
    const url = `${this.apiBase}/api/v1/episodes/${this.episodeId}/events/${event.event_type}`
    const headers: Record<string, string> = { "Content-Type": "application/json" }
    if (this.getAuthToken) {
      try {
        const token = await this.getAuthToken()
        if (token) headers.Authorization = `Bearer ${token}`
      } catch {
        // Si falla obtener el token, tratamos como reintentable (no perdemos).
        return "retry"
      }
    }

    let status: number
    let ok: boolean
    try {
      const response = await this.fetchImpl(url, {
        method: "POST",
        headers,
        body: JSON.stringify(event.payload),
      })
      status = response.status
      ok = response.ok
    } catch {
      // Fetch rechaza: red caida / offline / DNS. El servidor NO recibio la
      // request => reintentar es seguro (no duplica).
      return "retry"
    }

    if (ok) return "ok"
    // 4xx de negocio: no apendable, no reintentar. Excepto 408/429 (transitorios).
    if (status >= 400 && status < 500 && status !== 408 && status !== 429) {
      return "drop"
    }
    // 5xx, 408, 429: reintentar.
    return "retry"
  }

  private scheduleRetry(attempts: number): void {
    if (this.retryTimer || this.disposed) return
    const backoff = Math.min(this.maxBackoffMs, this.baseBackoffMs * 2 ** (attempts - 1))
    // Jitter +-25% para evitar thundering herd al volver la red.
    const jitter = backoff * (Math.random() * 0.5 - 0.25)
    const delay = Math.max(0, Math.round(backoff + jitter))
    this.retryTimer = this.scheduler(() => {
      this.retryTimer = null
      void this.flush()
    }, delay)
  }

  private persist(): void {
    try {
      if (this.queue.length === 0) {
        this.storage.removeItem(this.storageKey)
      } else {
        this.storage.setItem(this.storageKey, JSON.stringify(this.queue))
      }
    } catch {
      // localStorage lleno / bloqueado: la cola en memoria sigue siendo la
      // fuente de verdad de esta sesion. No perdemos en runtime; solo la
      // durabilidad cross-reload de estos items queda degradada.
    }
  }

  private loadQueue(): QueuedEvent[] {
    try {
      const raw = this.storage.getItem(this.storageKey)
      if (!raw) return []
      const parsed = JSON.parse(raw) as unknown
      if (!Array.isArray(parsed)) return []
      // Validacion defensiva: descartar items corruptos preservando el orden.
      return parsed.filter(
        (e): e is QueuedEvent =>
          typeof e === "object" &&
          e !== null &&
          typeof (e as QueuedEvent).event_type === "string" &&
          typeof (e as QueuedEvent).event_uuid === "string" &&
          typeof (e as QueuedEvent).payload === "object",
      )
    } catch {
      return []
    }
  }

  private installLifecycleHooks(): void {
    if (typeof globalThis.addEventListener !== "function") return
    this.onlineHandler = () => void this.flush()
    this.visibilityHandler = () => {
      if (typeof document !== "undefined" && document.visibilityState === "visible") {
        void this.flush()
      }
    }
    globalThis.addEventListener("online", this.onlineHandler)
    if (typeof document !== "undefined") {
      document.addEventListener("visibilitychange", this.visibilityHandler)
    }
  }

  private removeLifecycleHooks(): void {
    if (this.onlineHandler && typeof globalThis.removeEventListener === "function") {
      globalThis.removeEventListener("online", this.onlineHandler)
      this.onlineHandler = null
    }
    if (this.visibilityHandler && typeof document !== "undefined") {
      document.removeEventListener("visibilitychange", this.visibilityHandler)
      this.visibilityHandler = null
    }
  }
}
