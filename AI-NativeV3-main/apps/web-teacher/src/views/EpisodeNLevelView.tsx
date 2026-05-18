import { Button, Input, Label, PageContainer } from "@platform/ui"
import { Link } from "@tanstack/react-router"
import { useEffect, useMemo, useState } from "react"
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts"
import { useViewMode } from "../hooks/useViewMode"
import { type NLevel, type NLevelDistribution, getEpisodeNLevelDistribution } from "../lib/api"
import { NLEVEL_DOCENTE, NLEVEL_INVESTIGADOR } from "../utils/docenteLabels"
import { helpContent } from "../utils/helpContent"

interface Props {
  getToken: () => Promise<string | null>
  initialEpisodeId?: string
}

const LEVEL_TOKEN_VAR: Record<NLevel, string> = {
  N1: "--color-level-n1",
  N2: "--color-level-n2",
  N3: "--color-level-n3",
  N4: "--color-level-n4",
  meta: "--color-level-meta",
}

function resolveLevelColors(): Record<NLevel, string> {
  const fallback: Record<NLevel, string> = {
    N1: "#22c55e",
    N2: "#3b82f6",
    N3: "#eab308",
    N4: "#f97316",
    meta: "#94a3b8",
  }
  if (typeof window === "undefined") return fallback
  const root = window.getComputedStyle(document.documentElement)
  const out: Partial<Record<NLevel, string>> = {}
  ;(Object.keys(LEVEL_TOKEN_VAR) as NLevel[]).forEach((lvl) => {
    const raw = root.getPropertyValue(LEVEL_TOKEN_VAR[lvl]).trim()
    if (raw) {
      out[lvl] =
        raw.startsWith("oklch") || raw.startsWith("#") ? raw : `var(${LEVEL_TOKEN_VAR[lvl]})`
    } else {
      out[lvl] = fallback[lvl]
    }
  })
  return out as Record<NLevel, string>
}

function formatSeconds(s: number): string {
  if (s < 60) return `${s.toFixed(1)}s`
  const m = Math.floor(s / 60)
  const rest = s - m * 60
  return `${m}m ${rest.toFixed(0)}s`
}

function formatMinutes(s: number): string {
  if (s < 60) return `${Math.round(s)} seg`
  const m = Math.floor(s / 60)
  const rest = Math.round(s - m * 60)
  if (rest === 0) return `${m} min`
  return `${m} min ${rest} seg`
}

function dominantLevel(
  dist: Record<NLevel, number>,
  labels: Record<string, string>,
): { level: NLevel; ratio: number; label: string } | null {
  const total = Object.values(dist).reduce((a, b) => a + b, 0)
  if (total === 0) return null
  const levels: NLevel[] = ["N1", "N2", "N3", "N4", "meta"]
  let max: NLevel = "N1"
  for (const l of levels) {
    if ((dist[l] ?? 0) > (dist[max] ?? 0)) max = l
  }
  return { level: max, ratio: (dist[max] ?? 0) / total, label: labels[max] ?? max }
}

function NLevelDistributionChart({
  data,
  colors,
  isDocente,
}: {
  data: NLevelDistribution
  colors: Record<NLevel, string>
  isDocente: boolean
}) {
  const total = Object.values(data.distribution_seconds).reduce((a, b) => a + b, 0)
  const levels: NLevel[] = ["N1", "N2", "N3", "N4", "meta"]
  const levelLabels = isDocente ? NLEVEL_DOCENTE : NLEVEL_INVESTIGADOR

  if (total === 0) {
    return (
      <div className="rounded-xl border border-dashed border-border p-8 text-center text-muted text-sm">
        {isDocente
          ? "Todavia no hay datos de esta sesion."
          : "Sin datos de duracion. El episodio aun no tiene eventos persistidos o el modo dev del analytics-service no tiene CTR configurado."}
      </div>
    )
  }

  const pieData = levels
    .map((lvl) => ({
      name: lvl,
      value: data.distribution_seconds[lvl] ?? 0,
      color: colors[lvl],
    }))
    .filter((d) => d.value > 0)

  const maxSecs = Math.max(...levels.map((l) => data.distribution_seconds[l] ?? 0), 1)

  return (
    <div className="flex flex-col gap-6 sm:flex-row sm:items-start">
      <div className="w-full sm:w-52 shrink-0">
        <ResponsiveContainer width="100%" height={200}>
          <PieChart>
            <Pie
              data={pieData}
              cx="50%"
              cy="50%"
              innerRadius={55}
              outerRadius={85}
              paddingAngle={2}
              dataKey="value"
            >
              {pieData.map((entry) => (
                <Cell key={entry.name} fill={entry.color} />
              ))}
            </Pie>
            <Tooltip
              formatter={(value) => [
                isDocente ? formatMinutes(Number(value)) : formatSeconds(Number(value)),
                "tiempo",
              ]}
              contentStyle={{ fontSize: "12px", borderRadius: "8px", border: "1px solid #EAEAEA" }}
            />
          </PieChart>
        </ResponsiveContainer>
      </div>

      <div className="flex-1 space-y-3">
        {levels.map((lvl) => {
          const secs = data.distribution_seconds[lvl] ?? 0
          const count = data.total_events_per_level[lvl] ?? 0
          const ratio = data.distribution_ratio[lvl] ?? 0
          const barWidth = (secs / maxSecs) * 100
          return (
            <div key={lvl}>
              <div className="flex items-center justify-between mb-1">
                <div className="flex items-center gap-2">
                  <span
                    aria-hidden="true"
                    className="inline-block w-2.5 h-2.5 rounded-full shrink-0"
                    style={{ backgroundColor: colors[lvl] }}
                  />
                  <span className="text-sm font-medium text-ink">{levelLabels[lvl] ?? lvl}</span>
                </div>
                <span className="text-xs text-muted font-mono">
                  {(ratio * 100).toFixed(1)}%<span className="mx-1 text-border">·</span>
                  {isDocente ? formatMinutes(secs) : formatSeconds(secs)}
                  {!isDocente && (
                    <>
                      <span className="mx-1 text-border">·</span>
                      {count} ev.
                    </>
                  )}
                </span>
              </div>
              <div className="h-1.5 bg-border rounded-full overflow-hidden">
                <div
                  className="h-full rounded-full transition-all"
                  style={{ width: `${barWidth}%`, backgroundColor: colors[lvl] }}
                />
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

export function EpisodeNLevelView({ getToken, initialEpisodeId }: Props) {
  const [episodeIdInput, setEpisodeIdInput] = useState(initialEpisodeId ?? "")
  const [data, setData] = useState<NLevelDistribution | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const colors = useMemo(resolveLevelColors, [])
  const [viewMode] = useViewMode()
  const isDocente = viewMode === "docente"

  const handleSearch = () => {
    if (!episodeIdInput.trim()) return
    setLoading(true)
    setError(null)
    setData(null)
    getEpisodeNLevelDistribution(episodeIdInput.trim(), getToken)
      .then(setData)
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    if (!initialEpisodeId) return
    setEpisodeIdInput(initialEpisodeId)
    setLoading(true)
    setError(null)
    setData(null)
    getEpisodeNLevelDistribution(initialEpisodeId, getToken)
      .then(setData)
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false))
  }, [initialEpisodeId, getToken])

  const dom = data
    ? dominantLevel(data.distribution_seconds, isDocente ? NLEVEL_DOCENTE : NLEVEL_INVESTIGADOR)
    : null

  return (
    <PageContainer
      title={isDocente ? "Que hizo el alumno en esta sesion" : "Distribucion N1-N4 por episodio"}
      description={
        isDocente
          ? "Mirá en que actividades paso mas tiempo el alumno durante el trabajo practico."
          : "Drill-down del tiempo invertido por el estudiante en cada nivel analitico de un episodio (componente C3.2 de la tesis, ADR-020)"
      }
      helpContent={helpContent.episodeNLevel}
    >
      <div className="space-y-6">
        {!initialEpisodeId && !data && !loading && (
          <div className="rounded-xl border border-dashed border-border bg-white p-6 text-sm text-muted space-y-2">
            <p className="font-semibold text-ink">
              {isDocente
                ? "No hay ninguna sesion seleccionada."
                : "Llegaste aca sin episodio seleccionado."}
            </p>
            <p>
              {isDocente ? (
                <>
                  Volve a la{" "}
                  <Link
                    to="/student-longitudinal"
                    className="text-[var(--color-accent-brand)] underline"
                  >
                    vista del alumno
                  </Link>{" "}
                  y elegi un trabajo para ver que hizo.
                </>
              ) : (
                <>
                  Volve a la lista del estudiante (
                  <Link
                    to="/student-longitudinal"
                    className="text-[var(--color-accent-brand)] underline"
                  >
                    evolucion del estudiante
                  </Link>
                  ) y elegi un episodio para ver su distribucion N1-N4.
                </>
              )}
            </p>
            {!isDocente && (
              <p className="text-xs text-muted pt-2 border-t border-border mt-3">
                Tambien podes pegar un UUID a mano (auditoria) en el formulario de abajo.
              </p>
            )}
          </div>
        )}

        {error && (
          <div className="rounded-xl border border-danger/30 bg-danger-soft p-4 text-sm text-danger">
            <div className="font-semibold">Error consultando el episodio</div>
            <div className="mt-1 font-mono text-xs">{error}</div>
          </div>
        )}

        {data && (
          <>
            {isDocente && dom && <DocenteInterpretation dominant={dom} />}
            <div className="rounded-xl border border-border bg-white overflow-hidden">
              <div className="flex items-start justify-between gap-4 border-b border-border px-6 py-4">
                <div>
                  <div className="text-xs uppercase tracking-wider text-muted mb-1">
                    {isDocente ? "Sesion" : "Episodio"}
                  </div>
                  <div className="font-mono text-sm text-ink break-all">
                    {isDocente ? data.episode_id.slice(0, 8) : data.episode_id}
                  </div>
                </div>
                {!isDocente && (
                  <div className="text-right text-xs text-muted shrink-0">
                    <div>labeler v{data.labeler_version}</div>
                    <div>
                      {Object.values(data.total_events_per_level).reduce((a, b) => a + b, 0)}{" "}
                      eventos
                    </div>
                  </div>
                )}
              </div>
              <div className="px-6 py-5">
                <NLevelDistributionChart data={data} colors={colors} isDocente={isDocente} />
              </div>
            </div>
          </>
        )}

        {!isDocente && (
          <details
            className="rounded-xl border border-border bg-white"
            open={!initialEpisodeId && !data}
          >
            <summary className="cursor-pointer px-6 py-3 text-sm font-medium text-ink hover:bg-canvas transition-colors">
              Buscar otro episodio por UUID
            </summary>
            <div className="px-6 pb-5 pt-2">
              <Label htmlFor="episode-id-input">UUID del episodio</Label>
              <div className="mt-2 flex gap-2">
                <Input
                  id="episode-id-input"
                  value={episodeIdInput}
                  onChange={(e) => setEpisodeIdInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") handleSearch()
                  }}
                  placeholder="ej. 12345678-1234-1234-1234-123456789012"
                  className="flex-1 font-mono text-sm"
                />
                <Button onClick={handleSearch} disabled={loading || !episodeIdInput.trim()}>
                  {loading ? "Cargando..." : "Analizar"}
                </Button>
              </div>
              <p className="mt-2 text-xs text-muted">
                El UUID se obtiene desde la lista de episodios del estudiante o del CTR.
              </p>
            </div>
          </details>
        )}
      </div>
    </PageContainer>
  )
}

function DocenteInterpretation({
  dominant,
}: {
  dominant: { level: NLevel; ratio: number; label: string }
}) {
  const pct = Math.round(dominant.ratio * 100)
  const insights: Record<NLevel, string> = {
    N1: "El alumno paso la mayor parte del tiempo leyendo el enunciado. Puede que le cueste entender la consigna o que sea un problema nuevo para el.",
    N2: "El alumno dedico bastante tiempo a tomar notas y planificar. Buena senal de estrategia antes de codear.",
    N3: "El alumno paso la mayor parte del tiempo escribiendo y probando codigo. Esta trabajando activamente en la solucion.",
    N4: "El alumno paso la mayor parte del tiempo usando el tutor IA. Conviene revisar si esta entendiendo o solo copiando respuestas.",
    meta: "La mayor parte del tiempo fue de inicio y cierre de sesion. Puede que la sesion haya sido muy corta.",
  }

  return (
    <div className="rounded-xl border border-border bg-white px-6 py-4 text-sm text-ink">
      <strong>{pct}% del tiempo</strong> lo paso <strong>{dominant.label.toLowerCase()}</strong>.{" "}
      {insights[dominant.level]}
    </div>
  )
}
