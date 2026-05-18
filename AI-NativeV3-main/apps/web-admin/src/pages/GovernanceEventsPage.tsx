/**
 * Vista institucional cross-cohort de eventos `intento_adverso_detectado`.
 *
 * Solo lectura (ADR-037). Reusa el endpoint de analytics extendido con
 * filtros opcionales facultad/materia/periodo + severidad/categoria.
 * Pagination cursor-based. Export CSV con headers ASCII (cp1252-safe).
 *
 * Casbin: docente_admin / superadmin only — el api-gateway enforced via
 * dev_trust_headers (X-User-Roles).
 */
import { PageContainer } from "@platform/ui"
import { type ReactNode, useCallback, useEffect, useMemo, useState } from "react"
import {
  type GovernanceEvent,
  type GovernanceEventsFilters,
  HttpError,
  governanceApi,
} from "../lib/api"
import { helpContent } from "../utils/helpContent"

const PAGE_LIMIT = 100

const CATEGORIES = [
  { value: "", label: "Todas" },
  { value: "jailbreak_indirect", label: "jailbreak_indirect" },
  { value: "jailbreak_substitution", label: "jailbreak_substitution" },
  { value: "jailbreak_fiction", label: "jailbreak_fiction" },
  { value: "persuasion_urgency", label: "persuasion_urgency" },
  { value: "prompt_injection", label: "prompt_injection" },
] as const

interface FilterState {
  facultad_id: string
  materia_id: string
  periodo_id: string
  severity_min: string
  severity_max: string
  category: string
}

const EMPTY_FILTERS: FilterState = {
  facultad_id: "",
  materia_id: "",
  periodo_id: "",
  severity_min: "",
  severity_max: "",
  category: "",
}

function filtersToApiArgs(f: FilterState, cursor?: string): GovernanceEventsFilters {
  const out: GovernanceEventsFilters = { limit: PAGE_LIMIT }
  if (f.facultad_id.trim()) out.facultad_id = f.facultad_id.trim()
  if (f.materia_id.trim()) out.materia_id = f.materia_id.trim()
  if (f.periodo_id.trim()) out.periodo_id = f.periodo_id.trim()
  if (f.severity_min.trim()) out.severity_min = Number(f.severity_min)
  if (f.severity_max.trim()) out.severity_max = Number(f.severity_max)
  if (f.category.trim()) out.category = f.category.trim()
  if (cursor) out.cursor = cursor
  return out
}

export function GovernanceEventsPage(): ReactNode {
  const [filters, setFilters] = useState<FilterState>(EMPTY_FILTERS)
  const [events, setEvents] = useState<GovernanceEvent[]>([])
  const [cursorNext, setCursorNext] = useState<string | null>(null)
  const [countsByCategory, setCountsByCategory] = useState<Record<string, number>>({})
  const [countsBySeverity, setCountsBySeverity] = useState<Record<string, number>>({})
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(
    async (currentFilters: FilterState, append: boolean, cursor?: string) => {
      setLoading(true)
      setError(null)
      try {
        const r = await governanceApi.listEvents(filtersToApiArgs(currentFilters, cursor))
        setCursorNext(r.cursor_next)
        setCountsByCategory(r.counts_by_category)
        setCountsBySeverity(r.counts_by_severity)
        setEvents((prev) => (append ? [...prev, ...r.events] : r.events))
      } catch (e) {
        setError(e instanceof HttpError ? `${e.status}: ${e.detail}` : (e as Error).message)
      } finally {
        setLoading(false)
      }
    },
    [],
  )

  // Carga inicial con filtros vacios
  useEffect(() => {
    void load(EMPTY_FILTERS, false)
  }, [load])

  function handleApplyFilters() {
    void load(filters, false)
  }

  function handleReset() {
    setFilters(EMPTY_FILTERS)
    void load(EMPTY_FILTERS, false)
  }

  function handleLoadMore() {
    if (cursorNext) void load(filters, true, cursorNext)
  }

  function handleExportCsv() {
    if (events.length === 0) return
    const csv = buildCsv(events)
    const ts = new Date().toISOString().replace(/[:.]/g, "-").slice(0, 19)
    const facultadSlug = filters.facultad_id ? `_fac-${filters.facultad_id.slice(0, 8)}` : ""
    const sevSlug =
      filters.severity_min || filters.severity_max
        ? `_sev${filters.severity_min || "x"}-${filters.severity_max || "x"}`
        : ""
    const filename = `governance-events-${ts}${facultadSlug}${sevSlug}.csv`
    triggerCsvDownload(csv, filename)
  }

  const totalEvents = events.length
  const summaryText = useMemo(() => {
    const cats = Object.entries(countsByCategory)
      .map(([k, v]) => `${k}=${v}`)
      .join(", ")
    return `${totalEvents} eventos | categorias: ${cats || "ninguna"}`
  }, [totalEvents, countsByCategory])

  return (
    <PageContainer
      title="Eventos de gobernanza"
      eyebrow="Inicio · Eventos de gobernanza"
      description="Vista institucional cross-cohort de intentos adversos al tutor (ADR-019, RN-129)"
      helpContent={helpContent.governanceEvents}
    >
      <div className="space-y-4">
        <FilterPanel
          filters={filters}
          onChange={setFilters}
          onApply={handleApplyFilters}
          onReset={handleReset}
          loading={loading}
        />

        {error && (
          <div className="rounded-lg bg-danger-soft border border-danger/30 text-danger p-4">
            <p className="font-medium">Error al cargar</p>
            <p className="text-sm mt-1">{error}</p>
          </div>
        )}

        <div className="flex items-center justify-between">
          <p className="text-sm text-muted">{summaryText}</p>
          <button
            type="button"
            onClick={handleExportCsv}
            disabled={events.length === 0 || loading}
            className="rounded bg-success hover:bg-success disabled:bg-border disabled:cursor-not-allowed text-white text-sm px-3 py-2"
          >
            Exportar CSV
          </button>
        </div>

        <EventsTable events={events} />

        {cursorNext && (
          <div className="flex justify-center">
            <button
              type="button"
              onClick={handleLoadMore}
              disabled={loading}
              className="rounded border border-border hover:bg-surface-alt disabled:cursor-not-allowed text-sm px-4 py-2"
            >
              {loading ? "Cargando..." : "Cargar mas"}
            </button>
          </div>
        )}

        {!loading && events.length === 0 && !error && (
          <p className="text-sm text-muted text-center py-8">
            Sin eventos para los filtros actuales.
          </p>
        )}

        <SeverityCountsRow counts={countsBySeverity} />
      </div>
    </PageContainer>
  )
}

interface FilterPanelProps {
  filters: FilterState
  onChange: (f: FilterState) => void
  onApply: () => void
  onReset: () => void
  loading: boolean
}

function FilterPanel({
  filters,
  onChange,
  onApply,
  onReset,
  loading,
}: FilterPanelProps): ReactNode {
  function setField<K extends keyof FilterState>(k: K, v: string) {
    onChange({ ...filters, [k]: v })
  }
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault()
        onApply()
      }}
      className="rounded-lg border border-border-soft bg-surface p-4 grid grid-cols-1 md:grid-cols-3 gap-3"
    >
      <FilterText
        label="Facultad ID (UUID)"
        value={filters.facultad_id}
        onChange={(v) => setField("facultad_id", v)}
      />
      <FilterText
        label="Materia ID (UUID)"
        value={filters.materia_id}
        onChange={(v) => setField("materia_id", v)}
      />
      <FilterText
        label="Periodo ID (UUID)"
        value={filters.periodo_id}
        onChange={(v) => setField("periodo_id", v)}
      />
      <FilterNumber
        label="Severidad min (1-5)"
        value={filters.severity_min}
        onChange={(v) => setField("severity_min", v)}
      />
      <FilterNumber
        label="Severidad max (1-5)"
        value={filters.severity_max}
        onChange={(v) => setField("severity_max", v)}
      />
      <FilterSelect
        label="Categoria"
        value={filters.category}
        options={CATEGORIES}
        onChange={(v) => setField("category", v)}
      />
      <div className="md:col-span-3 flex gap-2 pt-2">
        <button
          type="submit"
          disabled={loading}
          className="rounded bg-accent-brand hover:bg-accent-brand-deep disabled:bg-border text-white text-sm px-4 py-2"
        >
          {loading ? "Filtrando..." : "Aplicar filtros"}
        </button>
        <button
          type="button"
          onClick={onReset}
          disabled={loading}
          className="text-sm text-muted hover:text-body px-3 py-2"
        >
          Limpiar
        </button>
      </div>
    </form>
  )
}

function FilterText({
  label,
  value,
  onChange,
}: {
  label: string
  value: string
  onChange: (v: string) => void
}): ReactNode {
  return (
    <label className="text-sm">
      <span className="block text-body font-medium mb-1">{label}</span>
      <input
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full font-mono text-xs rounded border border-border px-2 py-1.5"
        placeholder="(opcional)"
      />
    </label>
  )
}

function FilterNumber({
  label,
  value,
  onChange,
}: {
  label: string
  value: string
  onChange: (v: string) => void
}): ReactNode {
  return (
    <label className="text-sm">
      <span className="block text-body font-medium mb-1">{label}</span>
      <input
        type="number"
        min={1}
        max={5}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full text-sm rounded border border-border px-2 py-1.5"
        placeholder="(opcional)"
      />
    </label>
  )
}

function FilterSelect({
  label,
  value,
  options,
  onChange,
}: {
  label: string
  value: string
  options: ReadonlyArray<{ value: string; label: string }>
  onChange: (v: string) => void
}): ReactNode {
  return (
    <label className="text-sm">
      <span className="block text-body font-medium mb-1">{label}</span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full text-sm rounded border border-border px-2 py-1.5 bg-surface"
      >
        {options.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </select>
    </label>
  )
}

function EventsTable({ events }: { events: GovernanceEvent[] }): ReactNode {
  if (events.length === 0) return null
  return (
    <div className="rounded-lg border border-border-soft bg-surface overflow-x-auto">
      <table className="w-full text-sm">
        <thead className="bg-surface-alt text-left text-xs uppercase text-muted">
          <tr>
            <th className="px-3 py-2">Timestamp</th>
            <th className="px-3 py-2">Estudiante</th>
            <th className="px-3 py-2">Categoria</th>
            <th className="px-3 py-2">Sev</th>
            <th className="px-3 py-2">Pattern</th>
            <th className="px-3 py-2">Texto matcheado</th>
          </tr>
        </thead>
        <tbody>
          {events.map((ev) => (
            <tr
              key={`${ev.episode_id}-${ev.ts}-${ev.pattern_id}`}
              className="border-t border-border-soft"
            >
              <td className="px-3 py-2 font-mono text-xs">{ev.ts}</td>
              <td className="px-3 py-2 font-mono text-xs">{ev.student_pseudonym.slice(0, 8)}...</td>
              <td className="px-3 py-2">{ev.category}</td>
              <td className="px-3 py-2">
                <SeverityBadge severity={ev.severity} />
              </td>
              <td className="px-3 py-2 font-mono text-xs">{ev.pattern_id}</td>
              <td className="px-3 py-2 text-body max-w-md truncate" title={ev.matched_text}>
                {ev.matched_text}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function SeverityBadge({ severity }: { severity: number }): ReactNode {
  const palette =
    severity >= 4
      ? "bg-danger-soft text-danger"
      : severity === 3
        ? "bg-warning-soft text-warning"
        : "bg-surface-alt text-body"
  return (
    <span className={`inline-block rounded px-2 py-0.5 text-xs font-medium ${palette}`}>
      {severity}
    </span>
  )
}

function SeverityCountsRow({ counts }: { counts: Record<string, number> }): ReactNode {
  const entries = Object.entries(counts).sort(([a], [b]) => Number(a) - Number(b))
  if (entries.length === 0) return null
  return (
    <div className="flex flex-wrap gap-2 text-xs text-muted">
      <span className="font-medium">Por severidad:</span>
      {entries.map(([sev, n]) => (
        <span key={sev} className="rounded bg-surface-alt px-2 py-0.5">
          sev {sev}: {n}
        </span>
      ))}
    </div>
  )
}

// ── CSV helpers (cp1252-safe — sin tildes en headers) ──────────────────

function buildCsv(events: GovernanceEvent[]): string {
  const headers = [
    "timestamp",
    "episode_id",
    "student_pseudonym",
    "comision_id",
    "categoria",
    "severidad",
    "pattern_id",
    "texto_matcheado",
  ]
  const rows = events.map((e) => [
    e.ts,
    e.episode_id,
    e.student_pseudonym,
    e.comision_id,
    e.category,
    String(e.severity),
    e.pattern_id,
    e.matched_text,
  ])
  const lines = [headers, ...rows].map((row) => row.map(escapeCsvCell).join(","))
  return lines.join("\r\n")
}

function escapeCsvCell(value: string): string {
  // Si contiene coma, comilla o newline => envolver en comillas dobles + escape
  if (/[",\r\n]/.test(value)) {
    return `"${value.replace(/"/g, '""')}"`
  }
  return value
}

function triggerCsvDownload(csv: string, filename: string): void {
  // BOM UTF-8 para que Excel en Windows reconozca encoding (CLAUDE.md gotcha de cp1252).
  const blob = new Blob([`﻿${csv}`], { type: "text/csv;charset=utf-8;" })
  const url = URL.createObjectURL(blob)
  const a = document.createElement("a")
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}
