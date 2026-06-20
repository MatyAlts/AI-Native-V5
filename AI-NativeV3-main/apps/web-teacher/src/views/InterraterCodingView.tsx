import { PageContainer } from "@platform/ui"
import { useCallback, useEffect, useMemo, useState } from "react"
import {
  type CTREvent,
  getEpisodeEvents,
  getInterraterProgress,
  getInterraterSample,
  saveInterraterRating,
} from "../lib/api"
import { getEventMeta, relativeTs } from "../utils/eventDisplay"
import { helpContent } from "../utils/helpContent"

interface Props {
  comisionId: string
  getToken: () => Promise<string | null>
}

// Perfiles del protocolo "ejes" (codificación a ciegas). Las etiquetas
// (label) son las canónicas del classifier; el texto es lo que ve el docente.
const PROFILES: { label: string; display: string; color: string }[] = [
  {
    label: "delegacion_pasiva",
    display: "Delegación pasiva",
    color: "bg-danger hover:bg-danger",
  },
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

export function InterraterCodingView({ comisionId, getToken }: Props) {
  const [episodes, setEpisodes] = useState<{ episode_id: string }[]>([])
  const [coded, setCoded] = useState<Set<string>>(new Set())
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [sample, progress] = await Promise.all([
        getInterraterSample(comisionId, getToken),
        getInterraterProgress(comisionId, getToken),
      ])
      setEpisodes(sample.episodes)
      setCoded(new Set(progress.rated_episode_ids))
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }, [comisionId, getToken])

  useEffect(() => {
    void load()
  }, [load])

  const markCoded = useCallback((episodeId: string) => {
    setCoded((prev) => {
      const next = new Set(prev)
      next.add(episodeId)
      return next
    })
  }, [])

  const codedCount = useMemo(
    () => episodes.filter((e) => coded.has(e.episode_id)).length,
    [episodes, coded],
  )

  return (
    <PageContainer
      title="Codificación a ciegas (inter-jueces)"
      description="Etiquetá cada episodio según el proceso del alumno, SIN ver la etiqueta de la máquina. Tu codificación se compara después con la de otros jueces y con el clasificador."
      helpContent={helpContent.interraterCoding}
    >
      <div className="space-y-6 max-w-4xl">
        <div className="rounded-xl border border-amber-300 bg-amber-50 px-6 py-4 text-sm text-amber-900">
          <p className="font-semibold mb-1">Codificación a ciegas</p>
          <p>
            En esta vista <strong>no se muestra la etiqueta del clasificador</strong>. Revisá la
            traza cruda de cada episodio (prompts, ediciones, ejecuciones) con "Ver proceso" y
            elegí el perfil que mejor lo describa. Podés re-etiquetar las veces que quieras.
          </p>
        </div>

        {loading && <div className="text-sm text-muted">Cargando episodios de la comisión…</div>}
        {error && <div className="p-3 rounded bg-danger-soft text-danger text-sm">{error}</div>}

        {!loading && !error && (
          <>
            <div className="flex items-center justify-between border-b border-border pb-3">
              <div className="text-sm">
                <span className="font-medium">{codedCount}</span> de{" "}
                <span className="font-medium">{episodes.length}</span> codificados
              </div>
              <button
                type="button"
                onClick={() => void load()}
                className="px-3 py-1.5 text-sm border border-border rounded hover:bg-canvas"
              >
                Recargar
              </button>
            </div>

            {episodes.length === 0 && (
              <div className="text-sm text-muted">No hay episodios para codificar en esta comisión.</div>
            )}

            <div className="space-y-3">
              {episodes.map((ep) => (
                <EpisodeCodingCard
                  key={ep.episode_id}
                  episodeId={ep.episode_id}
                  comisionId={comisionId}
                  getToken={getToken}
                  isCoded={coded.has(ep.episode_id)}
                  onCoded={() => markCoded(ep.episode_id)}
                />
              ))}
            </div>
          </>
        )}
      </div>
    </PageContainer>
  )
}

function EpisodeCodingCard({
  episodeId,
  comisionId,
  getToken,
  isCoded,
  onCoded,
}: {
  episodeId: string
  comisionId: string
  getToken: () => Promise<string | null>
  isCoded: boolean
  onCoded: () => void
}) {
  const [selected, setSelected] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [showProcess, setShowProcess] = useState(false)

  const handleRate = async (label: string) => {
    setSaving(true)
    setSaveError(null)
    try {
      await saveInterraterRating(
        { episode_id: episodeId, comision_id: comisionId, label, protocol: "ejes" },
        getToken,
      )
      setSelected(label)
      onCoded()
    } catch (e) {
      setSaveError(e instanceof Error ? e.message : String(e))
    } finally {
      setSaving(false)
    }
  }

  return (
    <div
      className={`rounded-xl border bg-white p-4 transition-colors ${
        isCoded ? "border-green-300 bg-green-50/30" : "border-border"
      }`}
    >
      <div className="flex items-center gap-2 mb-3">
        <span className="font-mono text-[11px] text-muted-soft uppercase tracking-wider">
          Episodio {episodeId.slice(0, 12)}
        </span>
        {isCoded && (
          <span className="text-[11px] font-semibold px-2 py-0.5 rounded-full bg-green-100 text-green-800">
            ✓ Codificado
          </span>
        )}
        <button
          type="button"
          onClick={() => setShowProcess((v) => !v)}
          className="ml-auto px-3 py-1 text-xs border border-border rounded hover:bg-canvas"
        >
          {showProcess ? "Ocultar proceso" : "Ver proceso"}
        </button>
      </div>

      {showProcess && (
        <div className="mb-4">
          <EpisodeProcessTrace episodeId={episodeId} getToken={getToken} />
        </div>
      )}

      <div>
        <div className="text-[11px] font-semibold text-muted mb-1.5 uppercase tracking-wider">
          ¿Cómo codificás este episodio?
        </div>
        <div className="flex flex-wrap gap-2">
          {PROFILES.map((p) => {
            const isSelected = selected === p.label
            return (
              <button
                key={p.label}
                type="button"
                disabled={saving}
                onClick={() => void handleRate(p.label)}
                className={`flex-1 min-w-[150px] px-3 py-2 rounded text-white text-xs font-medium transition disabled:opacity-50 ${p.color} ${
                  isSelected ? "ring-2 ring-offset-2 ring-[#111111]" : "opacity-70 hover:opacity-100"
                }`}
              >
                {p.display}
              </button>
            )
          })}
        </div>
        {saving && <p className="mt-2 text-xs text-muted">Guardando…</p>}
        {saveError && <p className="mt-2 text-xs text-danger">No se pudo guardar: {saveError}</p>}
      </div>
    </div>
  )
}

interface EnrichedEvent extends CTREvent {
  meta: ReturnType<typeof getEventMeta>
  relTs: string
}

// Traza CRUDA del episodio (reusa getEpisodeEvents + getEventMeta de la
// EpisodeTimelineView). NO trae ni muestra la etiqueta de la máquina.
function EpisodeProcessTrace({
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
