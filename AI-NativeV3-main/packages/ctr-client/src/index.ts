/**
 * Cliente del CTR para los frontends.
 *
 * Responsabilidades:
 * - Encolar eventos y enviarlos en batch al backend
 * - Debounce de eventos de edición de código (500 ms)
 * - Flush al blur del editor y al beforeunload (sendBeacon)
 * - Persistencia local en IndexedDB si falla la red
 * - Idempotencia por event_uuid
 */
import { type IDBPDatabase, openDB } from "idb"

export interface CTREventInput {
  event_type: string
  episode_id: string
  payload: Record<string, unknown>
}

interface QueuedEvent extends CTREventInput {
  event_uuid: string
  ts: string
}

interface CTREventsDB {
  events: {
    key: string
    value: QueuedEvent
  }
}

export interface CTRClientConfig {
  endpoint: string
  episodeId: string
  batchSize?: number
  flushIntervalMs?: number
  debounceEditMs?: number
  getAuthToken?: () => Promise<string | null>
}

export class CTRClient {
  private queue: QueuedEvent[] = []
  private flushTimer: ReturnType<typeof setTimeout> | null = null
  private debouncedEdit: ReturnType<typeof setTimeout> | null = null
  private readonly batchSize: number
  private readonly flushIntervalMs: number
  private readonly debounceEditMs: number
  private dbPromise: Promise<IDBPDatabase<CTREventsDB>>

  constructor(private config: CTRClientConfig) {
    this.batchSize = config.batchSize ?? 10
    this.flushIntervalMs = config.flushIntervalMs ?? 2000
    this.debounceEditMs = config.debounceEditMs ?? 500

    this.dbPromise = openDB<CTREventsDB>("ctr-client", 1, {
      upgrade(db) {
        db.createObjectStore("events", { keyPath: "event_uuid" })
      },
    })

    this.setupLifecycleHooks()
    void this.replayUnflushedFromIndexedDB()
  }

  /** Emite un evento genérico. Se encola y flushea cuando corresponde. */
  emit(event: CTREventInput): void {
    const enriched: QueuedEvent = {
      ...event,
      event_uuid: crypto.randomUUID(),
      ts: new Date().toISOString(),
    }
    this.queue.push(enriched)
    void this.saveToIndexedDB(enriched)

    if (this.queue.length >= this.batchSize) {
      void this.flush()
    } else {
      this.scheduleFlush()
    }
  }

  /** Edición de código con debounce (500ms default) para capturar pausas significativas. */
  emitCodeEdit(payload: {
    snapshot: string
    diff_chars: number
    language: string
  }): void {
    if (this.debouncedEdit) clearTimeout(this.debouncedEdit)
    this.debouncedEdit = setTimeout(() => {
      this.emit({
        event_type: "EdicionCodigo",
        episode_id: this.config.episodeId,
        payload,
      })
      this.debouncedEdit = null
    }, this.debounceEditMs)
  }

  /** Fuerza flush del buffer debounceado más la cola. Útil antes de ejecutar tests. */
  async flushAll(): Promise<void> {
    if (this.debouncedEdit) {
      clearTimeout(this.debouncedEdit)
      this.debouncedEdit = null
    }
    await this.flush()
  }

  private scheduleFlush(delayMs?: number): void {
    if (this.flushTimer) return
    this.flushTimer = setTimeout(() => {
      this.flushTimer = null
      void this.flush()
    }, delayMs ?? this.flushIntervalMs)
  }

  private async flush(): Promise<void> {
    if (this.queue.length === 0) return
    const batch = [...this.queue]
    this.queue = []

    try {
      const token = await this.config.getAuthToken?.()
      const headers: Record<string, string> = {
        "Content-Type": "application/json",
      }
      if (token) headers.Authorization = `Bearer ${token}`

      const response = await fetch(this.config.endpoint, {
        method: "POST",
        headers,
        body: JSON.stringify({ events: batch }),
      })
      if (!response.ok) throw new Error(`CTR flush HTTP ${response.status}`)

      // Ack: remover de IndexedDB
      await this.clearFromIndexedDB(batch.map((e) => e.event_uuid))
    } catch (err) {
      // Re-queue y backoff
      this.queue.unshift(...batch)
      console.warn("CTR flush falló, reintento programado", err)
      this.scheduleFlush(5000)
    }
  }

  private async saveToIndexedDB(event: QueuedEvent): Promise<void> {
    try {
      const db = await this.dbPromise
      await db.put("events", event)
    } catch {
      // Silencioso: IndexedDB puede fallar en modo privado, no es crítico
    }
  }

  private async clearFromIndexedDB(uuids: string[]): Promise<void> {
    try {
      const db = await this.dbPromise
      const tx = db.transaction("events", "readwrite")
      await Promise.all(uuids.map((u) => tx.store.delete(u)))
      await tx.done
    } catch {
      // No crítico
    }
  }

  private async replayUnflushedFromIndexedDB(): Promise<void> {
    try {
      const db = await this.dbPromise
      const pending = await db.getAll("events")
      if (pending.length > 0) {
        this.queue.push(...pending)
        this.scheduleFlush(1000)
      }
    } catch {
      // No crítico
    }
  }

  private setupLifecycleHooks(): void {
    // Flush al cerrar la pestaña: único mecanismo confiable es sendBeacon
    window.addEventListener("beforeunload", () => {
      if (this.queue.length > 0) {
        const blob = new Blob([JSON.stringify({ events: this.queue })], {
          type: "application/json",
        })
        navigator.sendBeacon(this.config.endpoint, blob)
      }
    })

    // Flush al perder foco (captura eventos pendientes de edición)
    window.addEventListener("blur", () => void this.flushAll(), true)
  }
}
