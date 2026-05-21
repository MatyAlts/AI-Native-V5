import { Button, Input, Label, PageContainer } from "@platform/ui"
import { useEffect, useMemo, useState } from "react"
import { type CTREvent, type EpisodeWithEvents, getEpisodeEvents } from "../lib/api"
import {
  ALL_CATEGORIES,
  CATEGORY_LABEL,
  type EventCategory,
  getEventMeta,
  relativeTs,
} from "../utils/eventDisplay"
import { helpContent } from "../utils/helpContent"

interface Props {
  getToken: () => Promise<string | null>
  initialEpisodeId?: string
}

const LEVEL_COLOR: Record<string, string> = {
  N1: "bg-green-100 text-green-800 border-green-300",
  N2: "bg-blue-100 text-blue-800 border-blue-300",
  N3: "bg-yellow-100 text-yellow-800 border-yellow-300",
  N4: "bg-orange-100 text-orange-800 border-orange-300",
  meta: "bg-slate-100 text-slate-700 border-slate-300",
}

const CATEGORY_COLOR: Record<EventCategory, string> = {
  meta: "bg-slate-100 text-slate-700 border-slate-300",
  lectura: "bg-green-100 text-green-800 border-green-300",
  anotacion: "bg-purple-100 text-purple-800 border-purple-300",
  codigo: "bg-yellow-100 text-yellow-800 border-yellow-300",
  tutor: "bg-orange-100 text-orange-800 border-orange-300",
  integridad: "bg-red-100 text-red-800 border-red-300",
}

interface EnrichedEvent extends CTREvent {
  meta: ReturnType<typeof getEventMeta>
  relTs: string
}

export function EpisodeTimelineView({ getToken, initialEpisodeId }: Props) {
  const [episodeIdInput, setEpisodeIdInput] = useState(initialEpisodeId ?? "")
  const [data, setData] = useState<EpisodeWithEvents | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [activeCategories, setActiveCategories] = useState<Set<EventCategory>>(
    new Set(ALL_CATEGORIES),
  )
  const [selected, setSelected] = useState<EnrichedEvent | null>(null)

  async function load(id: string) {
    if (!id) return
    setLoading(true)
    setError(null)
    setData(null)
    setSelected(null)
    try {
      const res = await getEpisodeEvents(id, getToken)
      setData(res)
    } catch (e) {
      setError(`No se pudo cargar el episodio: ${e instanceof Error ? e.message : String(e)}`)
    } finally {
      setLoading(false)
    }
  }

  // Auto-load si vino con initialEpisodeId
  useEffect(() => {
    if (initialEpisodeId) void load(initialEpisodeId)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialEpisodeId])

  const enriched: EnrichedEvent[] = useMemo(() => {
    if (!data) return []
    const opened = data.events.find((e) => e.event_type === "episodio_abierto")
    const openedMs = opened ? Date.parse(opened.ts) : Date.parse(data.events[0]?.ts ?? "")
    return data.events
      .slice()
      .sort((a, b) => a.seq - b.seq)
      .map((e) => ({
        ...e,
        meta: getEventMeta(e.event_type),
        relTs: relativeTs(e.ts, openedMs),
      }))
  }, [data])

  const filtered = useMemo(
    () => enriched.filter((e) => activeCategories.has(e.meta.category)),
    [enriched, activeCategories],
  )

  const countsByCategory = useMemo(() => {
    const out: Record<EventCategory, number> = {
      meta: 0,
      lectura: 0,
      anotacion: 0,
      codigo: 0,
      tutor: 0,
      integridad: 0,
    }
    for (const e of enriched) out[e.meta.category]++
    return out
  }, [enriched])

  function toggleCategory(c: EventCategory) {
    setActiveCategories((prev) => {
      const next = new Set(prev)
      if (next.has(c)) next.delete(c)
      else next.add(c)
      return next
    })
  }

  return (
    <PageContainer
      title="Timeline del episodio"
      description="Secuencia firmada criptográficamente de cada interacción del alumno dentro de un episodio."
      helpContent={helpContent.episodeNLevel}
    >
      <div className="space-y-4">
        {/* Buscador */}
        <div className="flex gap-2 items-end">
          <div className="flex-1">
            <Label htmlFor="episode-id">Episode ID</Label>
            <Input
              id="episode-id"
              value={episodeIdInput}
              onChange={(e) => setEpisodeIdInput(e.target.value)}
              placeholder="UUID del episodio (ej. 0ee0e49e-fdb1-44a4-93d2-3ca8a9aed172)"
              data-testid="timeline-episode-input"
            />
          </div>
          <Button
            onClick={() => void load(episodeIdInput)}
            disabled={loading || !episodeIdInput}
            data-testid="timeline-load"
          >
            {loading ? "Cargando..." : "Cargar"}
          </Button>
        </div>

        {error && (
          <div
            className="rounded border border-red-300 bg-red-50 p-3 text-sm text-red-800"
            data-testid="timeline-error"
          >
            {error}
          </div>
        )}

        {data && (
          <div className="space-y-3">
            {/* Header del episodio */}
            <div className="rounded border border-border-soft bg-surface p-3 text-sm flex flex-wrap gap-x-6 gap-y-1">
              <div>
                <span className="text-muted">Episodio:</span>{" "}
                <span className="font-mono">{data.id.slice(0, 8)}…</span>
              </div>
              <div>
                <span className="text-muted">Estado:</span>{" "}
                <span className="font-mono">{data.estado}</span>
              </div>
              <div>
                <span className="text-muted">Eventos:</span>{" "}
                <span className="font-mono">{enriched.length}</span>
              </div>
              <div className="ml-auto">
                <a
                  href={`/api/v1/audit/episodes/${data.id}/verify`}
                  target="_blank"
                  rel="noreferrer"
                  className="text-accent-brand hover:underline text-xs font-medium"
                >
                  Verificar cadena criptográfica ↗
                </a>
              </div>
            </div>

            {/* Filtros por categoría */}
            <div className="flex flex-wrap gap-2" data-testid="timeline-filters">
              {ALL_CATEGORIES.map((c) => {
                const active = activeCategories.has(c)
                const count = countsByCategory[c]
                return (
                  <button
                    key={c}
                    type="button"
                    onClick={() => toggleCategory(c)}
                    className={`px-3 py-1.5 rounded-full border text-xs font-medium transition-colors ${
                      active
                        ? CATEGORY_COLOR[c]
                        : "bg-surface text-muted border-border-soft opacity-50"
                    }`}
                  >
                    {CATEGORY_LABEL[c]} ({count})
                  </button>
                )
              })}
            </div>

            {/* Layout 2 columnas: tabla + panel lateral */}
            <div className="grid grid-cols-1 lg:grid-cols-[1fr_400px] gap-4">
              {/* Tabla */}
              <div
                className="rounded border border-border-soft bg-surface overflow-hidden"
                data-testid="timeline-table"
              >
                <table className="w-full text-sm">
                  <thead className="bg-surface-alt text-muted text-xs uppercase">
                    <tr>
                      <th className="px-3 py-2 text-left w-16">+ts</th>
                      <th className="px-3 py-2 text-left w-12">seq</th>
                      <th className="px-3 py-2 text-left">Evento</th>
                      <th className="px-3 py-2 text-left w-16">N</th>
                      <th className="px-3 py-2 text-left">Resumen</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filtered.length === 0 && (
                      <tr>
                        <td colSpan={5} className="px-3 py-6 text-center text-muted text-xs">
                          Sin eventos para los filtros activos.
                        </td>
                      </tr>
                    )}
                    {filtered.map((e) => {
                      const isSelected = selected?.seq === e.seq
                      return (
                        <tr
                          key={e.seq}
                          onClick={() => setSelected(e)}
                          className={`cursor-pointer border-t border-border-soft hover:bg-surface-alt ${
                            isSelected ? "bg-accent-brand/10" : ""
                          }`}
                          data-testid={`timeline-row-${e.seq}`}
                        >
                          <td className="px-3 py-2 font-mono text-xs text-muted">{e.relTs}</td>
                          <td className="px-3 py-2 font-mono text-xs text-muted">{e.seq}</td>
                          <td className="px-3 py-2">
                            <span className="mr-1.5">{e.meta.icon}</span>
                            {e.meta.label}
                          </td>
                          <td className="px-3 py-2">
                            <span
                              className={`inline-block px-2 py-0.5 rounded border text-[10px] font-mono ${
                                LEVEL_COLOR[e.meta.nLevelBase] ?? LEVEL_COLOR.meta
                              }`}
                            >
                              {e.meta.nLevelBase}
                            </span>
                          </td>
                          <td className="px-3 py-2 text-xs text-body truncate max-w-md">
                            {e.meta.summary(e.payload)}
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>

              {/* Panel lateral */}
              <div className="rounded border border-border-soft bg-surface p-4 sticky top-4 self-start max-h-[80vh] overflow-y-auto">
                {!selected && (
                  <p className="text-sm text-muted">
                    Hacé click en una fila para ver el payload completo del evento.
                  </p>
                )}
                {selected && (
                  <div className="space-y-3" data-testid="timeline-detail">
                    <div>
                      <p className="text-xs font-mono uppercase tracking-wider text-muted">
                        Detalle del evento
                      </p>
                      <h3 className="font-medium text-base mt-1">
                        <span className="mr-2">{selected.meta.icon}</span>
                        {selected.meta.label}
                      </h3>
                      <p className="text-xs text-muted mt-1">
                        seq={selected.seq} · {selected.relTs} ·{" "}
                        <span className="font-mono">{selected.event_type}</span>
                      </p>
                    </div>

                    {/* Si es edicion_codigo, render del snapshot con monospace */}
                    {selected.event_type === "edicion_codigo" &&
                      typeof selected.payload.snapshot === "string" && (
                        <div>
                          <p className="text-xs font-mono uppercase tracking-wider text-muted mb-1">
                            Snapshot de código
                          </p>
                          <pre className="text-xs bg-slate-950 text-slate-100 p-3 rounded overflow-x-auto max-h-64">
                            {selected.payload.snapshot as string}
                          </pre>
                        </div>
                      )}

                    {/* Si es prompt o respuesta del tutor, render como texto */}
                    {(selected.event_type === "prompt_enviado" ||
                      selected.event_type === "tutor_respondio") &&
                      typeof selected.payload.content === "string" && (
                        <div>
                          <p className="text-xs font-mono uppercase tracking-wider text-muted mb-1">
                            Contenido
                          </p>
                          <div className="text-sm bg-surface-alt p-3 rounded whitespace-pre-wrap max-h-64 overflow-y-auto">
                            {selected.payload.content as string}
                          </div>
                        </div>
                      )}

                    {/* Payload crudo siempre disponible */}
                    <div>
                      <p className="text-xs font-mono uppercase tracking-wider text-muted mb-1">
                        Payload (JSON)
                      </p>
                      <pre className="text-[10px] bg-surface-alt p-2 rounded overflow-x-auto max-h-48">
                        {JSON.stringify(selected.payload, null, 2)}
                      </pre>
                    </div>

                    <div className="pt-2 border-t border-border-soft text-[10px] text-muted">
                      ts: <span className="font-mono">{selected.ts}</span>
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>
        )}
      </div>
    </PageContainer>
  )
}
