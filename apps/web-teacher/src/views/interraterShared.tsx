import { useEffect, useState } from "react"
import { type CTREvent, getEpisodeEvents } from "../lib/api"
import { getEventMeta, relativeTs } from "../utils/eventDisplay"

// Perfiles del protocolo "ejes". Las etiquetas (label) son las canónicas del
// classifier; el texto es lo que ve el docente. Compartido por la codificación
// y la calibración del entrenamiento.
export const PROFILES: { label: string; display: string; color: string }[] = [
  { label: "delegacion_pasiva", display: "Delegación pasiva", color: "bg-danger hover:bg-danger" },
  {
    label: "apropiacion_superficial",
    display: "Apropiación superficial",
    color: "bg-warning hover:bg-warning",
  },
  {
    label: "apropiacion_reflexiva",
    display: "Apropiación reflexiva",
    color: "bg-green-600 hover:bg-green-700",
  },
]

interface EnrichedEvent extends CTREvent {
  meta: ReturnType<typeof getEventMeta>
  relTs: string
}

/**
 * Traza CRUDA del episodio (prompts, ediciones, ejecuciones). NO trae ni muestra
 * la etiqueta de la máquina. Se reusa tal cual en la codificación a ciegas y en
 * las anclas del entrenamiento.
 */
export function EpisodeProcessTrace({
  episodeId,
  getToken,
}: {
  episodeId: string
  getToken: () => Promise<string | null>
}) {
  const [events, setEvents] = useState<EnrichedEvent[] | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    setEvents(null)
    void (async () => {
      try {
        const res = await getEpisodeEvents(episodeId, getToken)
        if (cancelled) return
        const opened = res.events.find((e) => e.event_type === "episodio_abierto")
        const openedMs = opened ? Date.parse(opened.ts) : Date.parse(res.events[0]?.ts ?? "")
        const enriched = res.events
          .slice()
          .sort((a, b) => a.seq - b.seq)
          .map((e) => ({
            ...e,
            meta: getEventMeta(e.event_type),
            relTs: relativeTs(e.ts, openedMs),
          }))
        setEvents(enriched)
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e))
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [episodeId, getToken])

  if (loading) return <div className="text-xs text-muted">Cargando traza…</div>
  if (error) return <div className="text-xs text-danger">No se pudo cargar la traza: {error}</div>
  if (!events || events.length === 0)
    return <div className="text-xs text-muted">Sin eventos registrados.</div>

  return (
    <div className="rounded border border-border-soft bg-surface overflow-hidden">
      <table className="w-full text-sm">
        <thead className="bg-surface-alt text-muted text-xs uppercase">
          <tr>
            <th className="px-3 py-2 text-left w-16">+ts</th>
            <th className="px-3 py-2 text-left w-12">seq</th>
            <th className="px-3 py-2 text-left">Evento</th>
            <th className="px-3 py-2 text-left">Detalle</th>
          </tr>
        </thead>
        <tbody>
          {events.map((e) => (
            <EventRow key={e.seq} event={e} />
          ))}
        </tbody>
      </table>
    </div>
  )
}

function EventRow({ event }: { event: EnrichedEvent }) {
  const [open, setOpen] = useState(false)
  const snapshot =
    event.event_type === "edicion_codigo" && typeof event.payload.snapshot === "string"
      ? (event.payload.snapshot as string)
      : null
  const content =
    (event.event_type === "prompt_enviado" || event.event_type === "tutor_respondio") &&
    typeof event.payload.content === "string"
      ? (event.payload.content as string)
      : null

  return (
    <>
      <tr
        onClick={() => setOpen((v) => !v)}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault()
            setOpen((v) => !v)
          }
        }}
        tabIndex={0}
        className="cursor-pointer border-t border-border-soft hover:bg-surface-alt"
      >
        <td className="px-3 py-2 font-mono text-xs text-muted">{event.relTs}</td>
        <td className="px-3 py-2 font-mono text-xs text-muted">{event.seq}</td>
        <td className="px-3 py-2">
          <span className="mr-1.5">{event.meta.icon}</span>
          {event.meta.label}
        </td>
        <td className="px-3 py-2 text-xs text-body truncate max-w-md">
          {event.meta.summary(event.payload)}
        </td>
      </tr>
      {open && (
        <tr className="border-t border-border-soft bg-surface-alt/40">
          <td colSpan={4} className="px-3 py-3">
            {snapshot && (
              <div className="mb-3">
                <p className="text-xs font-mono uppercase tracking-wider text-muted mb-1">
                  Snapshot de código
                </p>
                <pre className="text-xs bg-slate-950 text-slate-100 p-3 rounded overflow-x-auto max-h-64">
                  {snapshot}
                </pre>
              </div>
            )}
            {content && (
              <div className="mb-3">
                <p className="text-xs font-mono uppercase tracking-wider text-muted mb-1">
                  Contenido
                </p>
                <div className="text-sm bg-surface p-3 rounded whitespace-pre-wrap max-h-64 overflow-y-auto">
                  {content}
                </div>
              </div>
            )}
            <div>
              <p className="text-xs font-mono uppercase tracking-wider text-muted mb-1">
                Payload (JSON)
              </p>
              <pre className="text-[10px] bg-surface p-2 rounded overflow-x-auto max-h-48">
                {JSON.stringify(event.payload, null, 2)}
              </pre>
            </div>
          </td>
        </tr>
      )}
    </>
  )
}
