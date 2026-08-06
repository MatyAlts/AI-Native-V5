import { Button, Input, Label, PageContainer } from "@platform/ui"
import { useCallback, useEffect, useMemo, useState } from "react"
import { type CTREvent, type EpisodeWithEvents, getEpisodeEvents } from "../lib/api"
import {
  ALL_CATEGORIES,
  CATEGORY_LABEL,
  type EventCategory,
  getEventMeta,
  relativeTs,
} from "../utils/eventDisplay"
import { helpContent } from "../utils/helpContent"
import { type DiffLineType, diffLines } from "../utils/lineDiff"

interface Props {
  getToken: () => Promise<string | null>
  initialEpisodeId?: string
}

// Un "intento de código" es cualquier evento que lleva el código completo del
// alumno en su payload: `edicion_codigo.snapshot` o `codigo_ejecutado.code`.
interface CodeAttempt {
  seq: number
  relTs: string
  eventType: string
  label: string
  icon: string
  code: string
}

/** Extrae el código completo de un evento de código; null si no lo lleva. */
function codeOf(payload: Record<string, unknown>, eventType: string): string | null {
  if (eventType === "edicion_codigo" && typeof payload.snapshot === "string")
    return payload.snapshot
  if (eventType === "codigo_ejecutado" && typeof payload.code === "string") return payload.code
  return null
}

const DIFF_ROW_CLASS: Record<DiffLineType, string> = {
  add: "bg-green-500/15 text-green-300",
  remove: "bg-red-500/15 text-red-300",
  equal: "text-slate-300",
}

const DIFF_SIGN: Record<DiffLineType, string> = {
  add: "+",
  remove: "-",
  equal: " ",
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
  // F6 — diff entre intentos de código.
  const [showDiff, setShowDiff] = useState(false)
  const [diffASeq, setDiffASeq] = useState<number | null>(null)
  const [diffBSeq, setDiffBSeq] = useState<number | null>(null)

  const load = useCallback(
    async (id: string) => {
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
    },
    [getToken],
  )

  // Auto-load si vino con initialEpisodeId
  useEffect(() => {
    if (initialEpisodeId) void load(initialEpisodeId)
  }, [initialEpisodeId, load])

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

  // Intentos de código en orden temporal (los que llevan el código en el payload).
  const codeAttempts: CodeAttempt[] = useMemo(() => {
    const out: CodeAttempt[] = []
    for (const e of enriched) {
      const code = codeOf(e.payload, e.event_type)
      if (code == null) continue
      out.push({
        seq: e.seq,
        relTs: e.relTs,
        eventType: e.event_type,
        label: e.meta.label,
        icon: e.meta.icon,
        code,
      })
    }
    return out
  }, [enriched])

  // Default: comparar los dos últimos intentos consecutivos al cargar un episodio.
  useEffect(() => {
    if (codeAttempts.length >= 2) {
      setDiffASeq(codeAttempts[codeAttempts.length - 2]?.seq ?? null)
      setDiffBSeq(codeAttempts[codeAttempts.length - 1]?.seq ?? null)
    } else {
      setDiffASeq(null)
      setDiffBSeq(null)
    }
  }, [codeAttempts])

  const diff = useMemo(() => {
    const a = codeAttempts.find((c) => c.seq === diffASeq)
    const b = codeAttempts.find((c) => c.seq === diffBSeq)
    if (!a || !b) return null
    return { a, b, ...diffLines(a.code, b.code) }
  }, [codeAttempts, diffASeq, diffBSeq])

  // Abre el diff de un intento contra el intento inmediatamente anterior.
  function openDiffForAttempt(seq: number) {
    const idx = codeAttempts.findIndex((c) => c.seq === seq)
    if (idx <= 0) return
    setDiffASeq(codeAttempts[idx - 1]?.seq ?? null)
    setDiffBSeq(seq)
    setShowDiff(true)
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

            {/* F6 — Diff entre intentos de código */}
            {codeAttempts.length >= 2 && (
              <div
                className="rounded border border-border-soft bg-surface"
                data-testid="timeline-diff"
              >
                <button
                  type="button"
                  onClick={() => setShowDiff((v) => !v)}
                  className="w-full flex items-center justify-between px-3 py-2 text-sm font-medium hover:bg-surface-alt transition-colors"
                  data-testid="timeline-diff-toggle"
                >
                  <span>⌗ Diff entre intentos de código ({codeAttempts.length} intentos)</span>
                  <span className="text-muted text-xs">
                    {showDiff ? "Ocultar ▲" : "Ver diff ▼"}
                  </span>
                </button>

                {showDiff && (
                  <div className="border-t border-border-soft p-3 space-y-3">
                    {/* Selector intento A vs intento B */}
                    <div className="flex flex-wrap items-end gap-3 text-xs">
                      <label className="flex flex-col gap-1">
                        <span className="text-muted uppercase tracking-wider">
                          Intento base (A)
                        </span>
                        <select
                          value={diffASeq ?? ""}
                          onChange={(e) => setDiffASeq(Number(e.target.value))}
                          className="text-xs rounded-md border border-border-soft bg-surface px-2 py-1 hover:border-ink transition-colors"
                          data-testid="timeline-diff-a"
                        >
                          {codeAttempts.map((c) => (
                            <option key={c.seq} value={c.seq}>
                              {c.icon} seq={c.seq} · {c.relTs} · {c.label}
                            </option>
                          ))}
                        </select>
                      </label>
                      <span className="pb-1.5 text-muted">→</span>
                      <label className="flex flex-col gap-1">
                        <span className="text-muted uppercase tracking-wider">
                          Intento nuevo (B)
                        </span>
                        <select
                          value={diffBSeq ?? ""}
                          onChange={(e) => setDiffBSeq(Number(e.target.value))}
                          className="text-xs rounded-md border border-border-soft bg-surface px-2 py-1 hover:border-ink transition-colors"
                          data-testid="timeline-diff-b"
                        >
                          {codeAttempts.map((c) => (
                            <option key={c.seq} value={c.seq}>
                              {c.icon} seq={c.seq} · {c.relTs} · {c.label}
                            </option>
                          ))}
                        </select>
                      </label>
                      {diff && !diff.truncated && (
                        <div className="ml-auto flex gap-2 pb-1 font-mono">
                          <span className="px-2 py-0.5 rounded border border-green-300 bg-green-100 text-green-800">
                            +{diff.stats.added}
                          </span>
                          <span className="px-2 py-0.5 rounded border border-red-300 bg-red-100 text-red-800">
                            -{diff.stats.removed}
                          </span>
                        </div>
                      )}
                    </div>

                    {/* Render del diff línea-a-línea */}
                    {diff &&
                      (diff.truncated ? (
                        <p className="text-xs text-warning" data-testid="timeline-diff-truncated">
                          Diff no disponible: alguno de los intentos es demasiado grande para
                          compararlo línea a línea.
                        </p>
                      ) : diff.stats.added === 0 && diff.stats.removed === 0 ? (
                        <p className="text-xs text-muted">
                          Sin cambios de código entre estos dos intentos.
                        </p>
                      ) : (
                        <div
                          className="rounded bg-slate-950 text-xs font-mono overflow-auto max-h-96"
                          data-testid="timeline-diff-view"
                        >
                          {diff.lines.map((ln, idx) => (
                            <div
                              key={`${ln.type}-${ln.aLine}-${ln.bLine}-${idx}`}
                              className={`flex ${DIFF_ROW_CLASS[ln.type]}`}
                            >
                              <span className="select-none px-2 text-slate-500 text-right w-10 shrink-0">
                                {ln.aLine ?? ""}
                              </span>
                              <span className="select-none pr-2 text-slate-500 text-right w-10 shrink-0">
                                {ln.bLine ?? ""}
                              </span>
                              <span className="select-none pr-2 shrink-0">
                                {DIFF_SIGN[ln.type]}
                              </span>
                              <span className="whitespace-pre">
                                {ln.text.length === 0 ? " " : ln.text}
                              </span>
                            </div>
                          ))}
                        </div>
                      ))}
                  </div>
                )}
              </div>
            )}

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
                      {/* "N base", no "N": esta columna sale de `EVENT_META.nLevelBase`,
                          que mapea tipo-de-evento → nivel y NO aplica los overrides
                          temporales del labeler (v1.1.0 `anotacion_creada`, v1.2.0
                          `tests_ejecutados`). El nivel OFICIAL puede diferir: un
                          `tests_ejecutados` con todo en verde y sin tutor reciente
                          se contabiliza N4 aunque acá figure N3.
                          Deliberadamente NO se replican los overrides en TS — serian
                          una sexta copia de reglas que ya se desincronizaron una vez
                          (ver el gotcha de los cinco `Literal` de `origin`). El fix de
                          fondo es que el backend exponga el nivel por evento. */}
                      <th
                        className="px-3 py-2 text-left w-20"
                        title="Nivel base por tipo de evento. El nivel oficial puede diferir: el labeler aplica overrides temporales que esta vista no calcula."
                      >
                        N base
                      </th>
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
                          onKeyDown={(ev) => {
                            if (ev.key === "Enter" || ev.key === " ") {
                              ev.preventDefault()
                              setSelected(e)
                            }
                          }}
                          tabIndex={0}
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

                    {/* F6 — atajo al diff contra el intento de código anterior */}
                    {codeOf(selected.payload, selected.event_type) != null &&
                      codeAttempts.findIndex((c) => c.seq === selected.seq) > 0 && (
                        <button
                          type="button"
                          onClick={() => openDiffForAttempt(selected.seq)}
                          className="text-xs font-medium text-accent-brand hover:underline"
                          data-testid="timeline-detail-diff"
                        >
                          ⌗ Ver diff vs intento anterior
                        </button>
                      )}

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
