import { Badge, PageContainer } from "@platform/ui"
import { Link } from "@tanstack/react-router"
import { TriangleAlert } from "lucide-react"
import { useEffect, useMemo, useState } from "react"
import { useViewMode } from "../hooks/useViewMode"
import {
  type CIIEvolutionLongitudinal,
  type CIIEvolutionTemplate,
  type CIIEvolutionUnidad,
  type StudentAlertsPayload,
  type StudentEpisode,
  type StudentEpisodesPayload,
  getStudentAlerts,
  getStudentCIIEvolution,
  getStudentEpisodes,
} from "../lib/api"
import {
  APPROPRIATION_DOCENTE,
  APPROPRIATION_INVESTIGADOR,
  APPROPRIATION_REIFICATION_DISCLAIMER,
  slopeToDocente,
  studentShortLabel,
} from "../utils/docenteLabels"
import { helpContent } from "../utils/helpContent"

interface Props {
  getToken: () => Promise<string | null>
  initialComisionId?: string
  initialStudentId?: string
}

function resolveScoreColors(): [string, string, string] {
  if (typeof window === "undefined") return ["#dc2626", "#f59e0b", "#16a34a"]
  const root = window.getComputedStyle(document.documentElement)
  const dele = root.getPropertyValue("--color-appropriation-delegacion").trim()
  const sup = root.getPropertyValue("--color-appropriation-superficial").trim()
  const ref = root.getPropertyValue("--color-appropriation-reflexiva").trim()
  return [
    dele ? `oklch(${dele.replace(/^oklch\(/, "").replace(/\)$/, "")})` : "#dc2626",
    sup ? `oklch(${sup.replace(/^oklch\(/, "").replace(/\)$/, "")})` : "#f59e0b",
    ref ? `oklch(${ref.replace(/^oklch\(/, "").replace(/\)$/, "")})` : "#16a34a",
  ]
}

function slopeLabel(slope: number | null): {
  label: string
  arrow: string
  color: string
} {
  if (slope === null) {
    return { label: "datos insuficientes", arrow: "?", color: "text-muted-soft" }
  }
  if (slope > 0.1) return { label: "mejorando", arrow: "↑", color: "text-[var(--color-success)]" }
  if (slope < -0.1) return { label: "empeorando", arrow: "↓", color: "text-[var(--color-danger)]" }
  return { label: "estable", arrow: "→", color: "text-muted" }
}

function Sparkline({ scores, colors }: { scores: number[]; colors: [string, string, string] }) {
  if (scores.length === 0) {
    return <div className="text-xs text-muted-soft">sin datos</div>
  }
  const W = 120
  const H = 36
  const PAD = 4
  const innerW = W - PAD * 2
  const innerH = H - PAD * 2

  const stepX = scores.length > 1 ? innerW / (scores.length - 1) : 0
  const yFor = (s: number) => PAD + innerH - (s / 2) * innerH

  const points = scores.map((s, i) => `${PAD + i * stepX},${yFor(s)}`).join(" ")

  return (
    <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} className="shrink-0" role="img">
      <title>Sparkline ordinal de {scores.length} puntos</title>
      {[0, 1, 2].map((s) => (
        <line
          key={s}
          x1={PAD}
          y1={yFor(s)}
          x2={W - PAD}
          y2={yFor(s)}
          stroke="#e2e8f0"
          strokeWidth={0.5}
          strokeDasharray="2 2"
        />
      ))}
      {scores.length > 1 && (
        <polyline
          points={points}
          fill="none"
          stroke="#475569"
          strokeWidth={1.5}
          strokeLinejoin="round"
        />
      )}
      {scores.map((s, i) => (
        <circle
          // biome-ignore lint/suspicious/noArrayIndexKey: posicion temporal estable
          key={i}
          cx={PAD + i * stepX}
          cy={yFor(s)}
          r={3}
          fill={colors[s] ?? "#64748b"}
          stroke="white"
          strokeWidth={1}
        />
      ))}
    </svg>
  )
}

function appropriationDot(label: string | null): string {
  if (label === "apropiacion_reflexiva") return "var(--color-appropriation-reflexiva)"
  if (label === "apropiacion_superficial") return "var(--color-appropriation-superficial)"
  if (label === "delegacion_pasiva") return "var(--color-appropriation-delegacion)"
  return "var(--color-level-meta)"
}

function formatShortDate(iso: string | null): string {
  if (!iso) return "sin fecha"
  return new Date(iso).toLocaleDateString("es-AR", {
    day: "2-digit",
    month: "2-digit",
    year: "2-digit",
  })
}

const SEVERITY_BADGE_STYLES: Record<string, string> = {
  low: "bg-surface-alt text-body",
  medium: "bg-warning-soft text-warning border border-warning/40",
  high: "bg-danger-soft text-danger border border-danger/40",
}

const SEVERITY_DOCENTE_LABEL: Record<string, string> = {
  low: "Leve",
  medium: "Moderada",
  high: "Importante",
}

const QUARTILE_LABELS: Record<string, string> = {
  Q1: "Q1 (peor 25%)",
  Q2: "Q2",
  Q3: "Q3",
  Q4: "Q4 (mejor 25%)",
}

const QUARTILE_DOCENTE: Record<string, string> = {
  Q1: "Por debajo de sus companeros",
  Q2: "En la media baja",
  Q3: "En la media alta",
  Q4: "Entre los mejores",
}

export function StudentLongitudinalView({ getToken, initialComisionId, initialStudentId }: Props) {
  const studentId = initialStudentId ?? null
  const comisionId = initialComisionId ?? null
  const [data, setData] = useState<CIIEvolutionLongitudinal | null>(null)
  const [alertsData, setAlertsData] = useState<StudentAlertsPayload | null>(null)
  const [episodesData, setEpisodesData] = useState<StudentEpisodesPayload | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [viewMode] = useViewMode()
  const isDocente = viewMode === "docente"

  const scoreColors = useMemo(resolveScoreColors, [])

  useEffect(() => {
    if (!studentId || !comisionId) return
    setLoading(true)
    setError(null)
    setData(null)
    setAlertsData(null)
    setEpisodesData(null)
    Promise.all([
      getStudentCIIEvolution(studentId, comisionId, getToken),
      getStudentAlerts(studentId, comisionId, getToken),
      getStudentEpisodes(studentId, comisionId, getToken),
    ])
      .then(([evo, alerts, episodes]) => {
        setData(evo)
        setAlertsData(alerts)
        setEpisodesData(episodes)
      })
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false))
  }, [studentId, comisionId, getToken])

  const meanLabel = data ? slopeLabel(data.mean_slope) : null
  const docenteSlope = data ? slopeToDocente(data.mean_slope) : null

  return (
    <PageContainer
      title={isDocente ? "Como va este alumno" : "Evolucion longitudinal del estudiante"}
      description={
        isDocente
          ? studentId
            ? `Alumno ${studentShortLabel(studentId)}`
            : ""
          : "Slope ordinal de apropiacion a traves de problemas analogos (Seccion 15.4, ADR-018, RN-130). N>=3 episodios por template para slope valido."
      }
      eyebrow={isDocente ? "Inicio · Mis alumnos · Detalle" : "Inicio · Cohorte · Estudiante"}
      helpContent={helpContent.studentLongitudinal}
    >
      <div className="space-y-6">
        {comisionId && (
          <div className="flex items-center gap-2 text-xs animate-fade-in-up">
            <Link
              to="/progression"
              search={{ comisionId }}
              className="press-shrink inline-flex items-center gap-1 text-muted hover:text-ink transition-colors"
            >
              ← {isDocente ? "Volver a mis alumnos" : "Volver a la cohorte"}
            </Link>
            {studentId && !isDocente && (
              <>
                <span className="text-border-soft">·</span>
                <span className="font-mono text-muted px-2 py-0.5 rounded bg-surface-alt border border-border-soft">
                  {studentId.slice(0, 8)}...{studentId.slice(-4)}
                </span>
              </>
            )}
          </div>
        )}

        {(!studentId || !comisionId) && !loading && (
          <div className="rounded-2xl border border-dashed border-border bg-surface p-8 animate-fade-in-up">
            <p className="font-semibold text-ink">
              {isDocente
                ? "No hay ningun alumno seleccionado."
                : "Llegaste aca sin estudiante seleccionado."}
            </p>
            <p className="mt-2 text-sm text-muted leading-relaxed">
              Volve a{" "}
              <Link to="/" className="text-accent-brand-deep underline hover:text-accent-brand">
                {isDocente ? "tus alumnos" : "tus comisiones"}
              </Link>
              {isDocente
                ? " y elegi un alumno para ver su evolucion."
                : ", abri una cohorte y elegi un estudiante para ver su evolucion longitudinal."}
            </p>
          </div>
        )}

        {loading && (
          <div className="space-y-4 animate-fade-in">
            <div className="skeleton h-32 rounded-xl" />
            <div className="skeleton h-48 rounded-xl" />
          </div>
        )}

        {error && (
          <div className="animate-fade-in-up rounded-xl border border-danger/30 bg-danger-soft p-4">
            <div className="text-sm font-semibold text-danger">Error consultando al estudiante</div>
            <div className="mt-1.5 font-mono text-xs text-danger/85 break-all">{error}</div>
          </div>
        )}

        {data && (
          <div className="space-y-4">
            {isDocente ? (
              <DocenteSummary data={data} docenteSlope={docenteSlope!} />
            ) : (
              <InvestigadorSummary data={data} meanLabel={meanLabel!} />
            )}

            {alertsData && alertsData.alerts.length > 0 && (
              <div className="rounded-xl border border-warning/30 bg-warning-soft p-4 space-y-2">
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2 text-sm font-semibold text-warning">
                    <TriangleAlert className="h-4 w-4 shrink-0" aria-hidden="true" />
                    {isDocente
                      ? `${alertsData.n_alerts} punto${alertsData.n_alerts !== 1 ? "s" : ""} de atencion`
                      : `${alertsData.n_alerts} alerta${alertsData.n_alerts !== 1 ? "s" : ""}`}
                  </div>
                  {alertsData.quartile && (
                    <span className="text-xs text-warning/90">
                      {isDocente
                        ? (QUARTILE_DOCENTE[alertsData.quartile] ?? alertsData.quartile)
                        : (QUARTILE_LABELS[alertsData.quartile] ?? alertsData.quartile)}
                    </span>
                  )}
                </div>
                <ul className="space-y-1.5">
                  {alertsData.alerts.map((a) => (
                    <li key={a.code} className="flex items-start gap-2 text-xs text-ink">
                      <span
                        className={`shrink-0 rounded px-2 py-0.5 text-[10px] uppercase font-semibold ${SEVERITY_BADGE_STYLES[a.severity] ?? ""}`}
                      >
                        {isDocente
                          ? (SEVERITY_DOCENTE_LABEL[a.severity] ?? a.severity)
                          : a.severity}
                      </span>
                      <span>
                        <strong>{a.title}</strong>
                        {": "}
                        {a.detail}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {alertsData &&
              alertsData.alerts.length === 0 &&
              alertsData.cohort_stats &&
              !alertsData.cohort_stats.insufficient_data && (
                <div className="rounded-xl border border-success/30 bg-success-soft p-3 text-sm text-success">
                  {isDocente ? (
                    <>
                      <strong>Todo bien</strong>: este alumno esta dentro de lo esperado
                      {alertsData.quartile &&
                        ` (${QUARTILE_DOCENTE[alertsData.quartile] ?? alertsData.quartile})`}
                      .
                    </>
                  ) : (
                    <>
                      <strong>Sin alertas</strong>: el estudiante esta dentro del rango esperado de
                      la cohorte
                      {alertsData.quartile && ` (${QUARTILE_LABELS[alertsData.quartile]})`}.
                    </>
                  )}
                </div>
              )}

            {/* Agrupacion por Unidad — PRIMARY cuando evolution_per_unidad tiene datos */}
            {data.evolution_per_unidad.length > 0 ? (
              <>
                {data.evolution_per_unidad.every((e) => e.insufficient_data) ? (
                  <div className="rounded-xl border border-dashed border-border bg-surface p-6 text-sm text-muted space-y-1">
                    <div className="font-semibold text-ink">
                      {isDocente
                        ? "Todavia no hay datos suficientes por unidad."
                        : "Datos insuficientes en todas las unidades."}
                    </div>
                    <div>
                      {isDocente
                        ? "El alumno necesita al menos 3 trabajos por unidad para ver el slope. Asegurate de asignar los TPs a las unidades correctas."
                        : "Cada unidad necesita >= 3 episodios cerrados para calcular slope ordinal. Las TPs sin unidad aparecen en 'Sin unidad'."}
                    </div>
                  </div>
                ) : isDocente ? (
                  <DocenteUnidadTable entries={data.evolution_per_unidad} colors={scoreColors} />
                ) : (
                  <InvestigadorUnidadTable
                    entries={data.evolution_per_unidad}
                    colors={scoreColors}
                    labelerVersion={data.labeler_version}
                  />
                )}

                {/* Template view como seccion secundaria colapsada en modo investigador */}
                {!isDocente && data.evolution_per_template.length > 0 && (
                  <TemplateSecondarySection
                    entries={data.evolution_per_template}
                    colors={scoreColors}
                    labelerVersion={data.labeler_version}
                  />
                )}
              </>
            ) : data.evolution_per_template.length === 0 ? (
              <div className="rounded-xl border border-dashed border-border bg-surface p-8 text-center text-sm text-muted">
                {data.n_episodes_total === 0 ? (
                  <>
                    <div className="font-semibold text-ink">
                      {isDocente
                        ? "Este alumno todavia no empezo."
                        : "Sin episodios cerrados."}
                    </div>
                    <div className="mt-1">
                      {isDocente
                        ? "Cuando complete su primer trabajo practico, va a aparecer aca su evolucion."
                        : "El estudiante no tiene episodios cerrados. Asigna TPs a Unidades para habilitar el analisis por tema."}
                    </div>
                  </>
                ) : (
                  <>
                    <div className="font-semibold text-ink">
                      {isDocente
                        ? `Hizo ${data.n_episodes_total} trabajo${data.n_episodes_total !== 1 ? "s" : ""}, pero no podemos calcular su evolucion.`
                        : `${data.n_episodes_total} episodios sin agrupar.`}
                    </div>
                    <div className="mt-1">
                      {isDocente
                        ? "Los TPs que hizo no estan vinculados a una plantilla canonica ni agrupados en unidades. Sin agrupacion no podemos comparar episodios analogos para ver si mejora o no. Asigna template_id o unidad a esas TPs."
                        : "Las TPs de este estudiante no tienen template_id ni unidad_id. Sin agrupacion canonica no hay episodios analogos para slope longitudinal (RN-130)."}
                    </div>
                  </>
                )}
              </div>
            ) : isDocente ? (
              <DocenteTemplateTable entries={data.evolution_per_template} colors={scoreColors} />
            ) : (
              <InvestigadorTemplateTable
                entries={data.evolution_per_template}
                colors={scoreColors}
                labelerVersion={data.labeler_version}
              />
            )}

            {episodesData && Array.isArray(episodesData.episodes) && (
              <EpisodesList episodes={episodesData.episodes} isDocente={isDocente} />
            )}
          </div>
        )}
      </div>
    </PageContainer>
  )
}

function DocenteSummary({
  data,
  docenteSlope,
}: {
  data: CIIEvolutionLongitudinal
  docenteSlope: ReturnType<typeof slopeToDocente>
}) {
  return (
    <div className="rounded-xl border border-border bg-surface px-6 py-5">
      <div className="flex items-center gap-4 mb-3">
        <span className={`text-4xl leading-none ${docenteSlope.color}`} aria-hidden="true">
          {docenteSlope.emoji}
        </span>
        <div>
          <div className="text-lg font-semibold text-ink">{docenteSlope.label}</div>
          {docenteSlope.action && (
            <div className="text-sm text-warning/85 mt-0.5">{docenteSlope.action}</div>
          )}
        </div>
      </div>
      <div className="flex flex-wrap gap-x-8 gap-y-2 text-sm text-muted">
        <div>
          <span className="font-semibold text-ink">{data.n_episodes_total}</span> trabajo
          {data.n_episodes_total !== 1 ? "s" : ""} completado
          {data.n_episodes_total !== 1 ? "s" : ""}
        </div>
        <div>
          <span className="font-semibold text-ink">{data.n_groups_evaluated}</span> tipo
          {data.n_groups_evaluated !== 1 ? "s" : ""} de trabajo
        </div>
      </div>
    </div>
  )
}

function InvestigadorSummary({
  data,
  meanLabel,
}: {
  data: CIIEvolutionLongitudinal
  meanLabel: ReturnType<typeof slopeLabel>
}) {
  return (
    <div className="rounded-xl border border-border bg-surface px-6 py-5">
      <div className="flex items-center gap-4 mb-4">
        <span className={`text-4xl leading-none ${meanLabel.color}`} aria-hidden="true">
          {meanLabel.arrow}
        </span>
        <div>
          <div className="text-lg font-semibold text-ink capitalize">{meanLabel.label}</div>
          <div className="text-xs text-muted">tendencia general del estudiante</div>
        </div>
      </div>
      <div className="flex flex-wrap gap-x-8 gap-y-2 text-sm">
        <div>
          <span className="font-semibold text-ink">{data.n_episodes_total}</span>
          <span className="text-muted ml-1">episodios</span>
        </div>
        <div>
          <span className="font-semibold text-ink">{data.n_groups_evaluated}</span>
          <span className="text-muted ml-1">templates</span>
        </div>
        <div>
          <span className="font-mono font-semibold text-ink">
            {data.mean_slope === null
              ? "—"
              : `${data.mean_slope > 0 ? "+" : ""}${data.mean_slope.toFixed(3)}`}
          </span>
          <span className="text-muted ml-1">slope prom.</span>
        </div>
        <div className="text-muted text-xs self-end">labeler v{data.labeler_version}</div>
      </div>
    </div>
  )
}

function DocenteTemplateTable({
  entries,
  colors,
}: {
  entries: CIIEvolutionTemplate[]
  colors: [string, string, string]
}) {
  return (
    <div className="overflow-hidden rounded-xl border border-border bg-surface">
      <table className="w-full text-sm">
        <thead className="bg-canvas text-left text-xs text-muted border-b border-border">
          <tr>
            <th className="px-4 py-2.5 font-medium">Trabajo practico</th>
            <th className="px-4 py-2.5 font-medium">Intentos</th>
            <th className="px-4 py-2.5 font-medium">Evolucion</th>
            <th className="px-4 py-2.5 font-medium">Tendencia</th>
          </tr>
        </thead>
        <tbody>
          {entries.map((entry) => {
            const docente = slopeToDocente(entry.slope)
            return (
              <tr
                key={entry.template_id}
                className="border-b border-border last:border-0 hover:bg-canvas transition-colors"
              >
                <td className="px-4 py-3 align-middle text-sm text-ink">
                  TP {entry.template_id.slice(0, 6)}
                </td>
                <td className="px-4 py-3 align-middle text-sm text-ink">{entry.n_episodes}</td>
                <td className="px-4 py-3 align-middle">
                  <Sparkline scores={entry.scores_ordinal} colors={colors} />
                </td>
                <td className="px-4 py-3 align-middle">
                  <div className={`flex items-center gap-1.5 text-sm ${docente.color}`}>
                    <span className="text-xl leading-none">{docente.emoji}</span>
                    <span>{docente.label}</span>
                  </div>
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
      <div className="border-t border-border bg-canvas px-4 py-2 flex items-center gap-4 text-xs text-muted">
        <span className="flex items-center gap-1.5">
          <span
            className="inline-block w-2 h-2 rounded-full"
            style={{ backgroundColor: colors[2] }}
          />
          Autonomo
        </span>
        <span className="flex items-center gap-1.5">
          <span
            className="inline-block w-2 h-2 rounded-full"
            style={{ backgroundColor: colors[1] }}
          />
          Superficial
        </span>
        <span className="flex items-center gap-1.5">
          <span
            className="inline-block w-2 h-2 rounded-full"
            style={{ backgroundColor: colors[0] }}
          />
          Depende de la IA
        </span>
      </div>
    </div>
  )
}

function InvestigadorTemplateTable({
  entries,
  colors,
  labelerVersion,
}: {
  entries: CIIEvolutionTemplate[]
  colors: [string, string, string]
  labelerVersion: string
}) {
  return (
    <div className="overflow-hidden rounded-xl border border-border bg-surface">
      <table className="w-full text-sm">
        <thead className="bg-canvas text-left text-xs uppercase tracking-wider text-muted border-b border-border">
          <tr>
            <th className="px-4 py-2.5 font-medium">Template</th>
            <th className="px-4 py-2.5 font-medium">N episodios</th>
            <th className="px-4 py-2.5 font-medium">Trayectoria ordinal</th>
            <th className="px-4 py-2.5 font-medium">Tendencia</th>
            <th className="px-4 py-2.5 font-medium text-right">Slope</th>
          </tr>
        </thead>
        <tbody>
          {entries.map((entry) => {
            const { label, arrow, color } = slopeLabel(entry.slope)
            return (
              <tr
                key={entry.template_id}
                className="border-b border-border last:border-0 hover:bg-canvas transition-colors"
              >
                <td className="px-4 py-3 align-middle">
                  <div className="font-mono text-xs text-muted break-all">
                    {entry.template_id.slice(0, 8)}...{entry.template_id.slice(-4)}
                  </div>
                </td>
                <td className="px-4 py-3 align-middle text-sm text-ink">{entry.n_episodes}</td>
                <td className="px-4 py-3 align-middle">
                  <Sparkline scores={entry.scores_ordinal} colors={colors} />
                </td>
                <td className="px-4 py-3 align-middle">
                  <div className={`flex items-center gap-1.5 text-sm ${color}`}>
                    <span className="text-xl leading-none">{arrow}</span>
                    <span className="capitalize">{label}</span>
                  </div>
                </td>
                <td className="px-4 py-3 align-middle text-right">
                  {entry.slope === null ? (
                    <span className="text-xs text-muted">sin slope</span>
                  ) : (
                    <span className="font-mono text-sm text-ink">
                      {entry.slope > 0 ? "+" : ""}
                      {entry.slope.toFixed(3)}
                    </span>
                  )}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
      <div className="border-t border-border bg-canvas px-4 py-2 text-xs text-muted">
        Trayectoria: cada punto es la apropiacion de un episodio (
        <Badge
          className="text-white border-0"
          style={{ background: "var(--color-appropriation-delegacion)" }}
        >
          delegacion=0
        </Badge>{" "}
        <Badge
          className="text-white border-0"
          style={{ background: "var(--color-appropriation-superficial)" }}
        >
          superficial=1
        </Badge>{" "}
        <Badge
          className="text-white border-0"
          style={{ background: "var(--color-appropriation-reflexiva)" }}
        >
          reflexiva=2
        </Badge>
        ) ordenada por classified_at. Labeler v{labelerVersion}.
      </div>
    </div>
  )
}

// ── Unidad tables (primary grouping) ─────────────────────────────────

function DocenteUnidadTable({
  entries,
  colors,
}: {
  entries: CIIEvolutionUnidad[]
  colors: [string, string, string]
}) {
  return (
    <div className="overflow-hidden rounded-xl border border-border bg-surface">
      <div className="border-b border-border bg-canvas px-4 py-2.5">
        <span className="text-xs font-semibold text-ink uppercase tracking-wider">
          Evolucion por unidad
        </span>
      </div>
      <table className="w-full text-sm">
        <thead className="bg-canvas text-left text-xs text-muted border-b border-border">
          <tr>
            <th className="px-4 py-2.5 font-medium">Unidad</th>
            <th className="px-4 py-2.5 font-medium">Intentos</th>
            <th className="px-4 py-2.5 font-medium">Evolucion</th>
            <th className="px-4 py-2.5 font-medium">Tendencia</th>
          </tr>
        </thead>
        <tbody>
          {entries.map((entry) => {
            const docente = slopeToDocente(entry.insufficient_data ? null : entry.slope)
            const isSinUnidad = entry.unidad_id === "sin_unidad"
            return (
              <tr
                key={entry.unidad_id}
                className="border-b border-border last:border-0 hover:bg-canvas transition-colors"
              >
                <td className="px-4 py-3 align-middle text-sm">
                  {isSinUnidad ? (
                    <span className="text-muted italic">{entry.unidad_nombre}</span>
                  ) : (
                    <span className="text-ink font-medium">{entry.unidad_nombre}</span>
                  )}
                </td>
                <td className="px-4 py-3 align-middle text-sm text-ink">{entry.n_episodes}</td>
                <td className="px-4 py-3 align-middle">
                  {entry.insufficient_data ? (
                    <span className="text-xs text-muted">min. 3 episodios</span>
                  ) : (
                    <Sparkline scores={entry.scores_ordinal} colors={colors} />
                  )}
                </td>
                <td className="px-4 py-3 align-middle">
                  {entry.insufficient_data ? (
                    <span className="text-xs text-muted">sin datos suf.</span>
                  ) : (
                    <div className={`flex items-center gap-1.5 text-sm ${docente.color}`}>
                      <span className="text-xl leading-none">{docente.emoji}</span>
                      <span>{docente.label}</span>
                    </div>
                  )}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
      <div className="border-t border-border bg-canvas px-4 py-2 flex items-center gap-4 text-xs text-muted">
        <span className="flex items-center gap-1.5">
          <span
            className="inline-block w-2 h-2 rounded-full"
            style={{ backgroundColor: colors[2] }}
          />
          Autonomo
        </span>
        <span className="flex items-center gap-1.5">
          <span
            className="inline-block w-2 h-2 rounded-full"
            style={{ backgroundColor: colors[1] }}
          />
          Superficial
        </span>
        <span className="flex items-center gap-1.5">
          <span
            className="inline-block w-2 h-2 rounded-full"
            style={{ backgroundColor: colors[0] }}
          />
          Depende de la IA
        </span>
      </div>
    </div>
  )
}

function InvestigadorUnidadTable({
  entries,
  colors,
  labelerVersion,
}: {
  entries: CIIEvolutionUnidad[]
  colors: [string, string, string]
  labelerVersion: string
}) {
  return (
    <div className="overflow-hidden rounded-xl border border-border bg-surface">
      <div className="border-b border-border bg-canvas px-4 py-2.5">
        <span className="text-xs font-semibold text-ink uppercase tracking-wider">
          Evolucion por unidad (primario)
        </span>
      </div>
      <table className="w-full text-sm">
        <thead className="bg-canvas text-left text-xs uppercase tracking-wider text-muted border-b border-border">
          <tr>
            <th className="px-4 py-2.5 font-medium">Unidad</th>
            <th className="px-4 py-2.5 font-medium">N episodios</th>
            <th className="px-4 py-2.5 font-medium">Trayectoria ordinal</th>
            <th className="px-4 py-2.5 font-medium">Tendencia</th>
            <th className="px-4 py-2.5 font-medium text-right">Slope</th>
          </tr>
        </thead>
        <tbody>
          {entries.map((entry) => {
            const { label, arrow, color } = slopeLabel(entry.insufficient_data ? null : entry.slope)
            const isSinUnidad = entry.unidad_id === "sin_unidad"
            return (
              <tr
                key={entry.unidad_id}
                className="border-b border-border last:border-0 hover:bg-canvas transition-colors"
              >
                <td className="px-4 py-3 align-middle">
                  {isSinUnidad ? (
                    <span className="text-xs text-muted italic">{entry.unidad_nombre}</span>
                  ) : (
                    <span className="text-sm font-medium text-ink">{entry.unidad_nombre}</span>
                  )}
                </td>
                <td className="px-4 py-3 align-middle text-sm text-ink">{entry.n_episodes}</td>
                <td className="px-4 py-3 align-middle">
                  {entry.insufficient_data ? (
                    <span className="text-xs text-muted">insuficiente (min. 3)</span>
                  ) : (
                    <Sparkline scores={entry.scores_ordinal} colors={colors} />
                  )}
                </td>
                <td className="px-4 py-3 align-middle">
                  <div className={`flex items-center gap-1.5 text-sm ${color}`}>
                    <span className="text-xl leading-none">{arrow}</span>
                    <span className="capitalize">{label}</span>
                  </div>
                </td>
                <td className="px-4 py-3 align-middle text-right">
                  {entry.insufficient_data || entry.slope === null ? (
                    <span className="text-xs text-muted">sin slope</span>
                  ) : (
                    <span className="font-mono text-sm text-ink">
                      {entry.slope > 0 ? "+" : ""}
                      {entry.slope.toFixed(3)}
                    </span>
                  )}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
      <div className="border-t border-border bg-canvas px-4 py-2 text-xs text-muted">
        Trayectoria por unidad tematica: cada punto es un episodio (
        <Badge
          className="text-white border-0"
          style={{ background: "var(--color-appropriation-delegacion)" }}
        >
          delegacion=0
        </Badge>{" "}
        <Badge
          className="text-white border-0"
          style={{ background: "var(--color-appropriation-superficial)" }}
        >
          superficial=1
        </Badge>{" "}
        <Badge
          className="text-white border-0"
          style={{ background: "var(--color-appropriation-reflexiva)" }}
        >
          reflexiva=2
        </Badge>
        ). Labeler v{labelerVersion}.
      </div>
    </div>
  )
}

function TemplateSecondarySection({
  entries,
  colors,
  labelerVersion,
}: {
  entries: CIIEvolutionTemplate[]
  colors: [string, string, string]
  labelerVersion: string
}) {
  const [expanded, setExpanded] = useState(false)
  return (
    <div className="rounded-xl border border-border bg-surface overflow-hidden">
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="w-full flex items-center justify-between px-4 py-3 text-left hover:bg-canvas transition-colors"
      >
        <span className="text-xs font-semibold text-muted uppercase tracking-wider">
          Agrupacion por template (secundario)
        </span>
        <span className="text-xs text-muted">{expanded ? "Ocultar" : "Mostrar"}</span>
      </button>
      {expanded && (
        <InvestigadorTemplateTable
          entries={entries}
          colors={colors}
          labelerVersion={labelerVersion}
        />
      )}
    </div>
  )
}

function EpisodesList({
  episodes,
  isDocente,
}: {
  episodes: StudentEpisode[]
  isDocente: boolean
}) {
  if (episodes.length === 0) {
    return (
      <div className="rounded-xl border border-dashed border-border bg-surface p-6 text-center text-sm text-muted">
        {isDocente
          ? "Este alumno no tiene trabajos completados todavia."
          : "El estudiante no tiene episodios registrados en esta comision todavia."}
      </div>
    )
  }

  const aprLabels = isDocente ? APPROPRIATION_DOCENTE : APPROPRIATION_INVESTIGADOR

  return (
    <section className="rounded-xl border border-border bg-surface overflow-hidden">
      <header className="border-b border-border bg-canvas px-4 py-2.5 flex items-center gap-2">
        <span className="text-xs font-semibold text-ink uppercase tracking-wider">
          {isDocente ? "Trabajos del alumno" : "Episodios del estudiante"}
        </span>
        <span className="text-xs text-muted">
          · {isDocente ? "click para ver detalle" : "click para ver distribucion N1-N4"}
        </span>
      </header>
      <ul className="divide-y divide-[#EAEAEA]" data-testid="student-episodes-list">
        {episodes.map((ep) => {
          const aprKey = ep.appropriation
          const aprText = aprKey ? (aprLabels[aprKey] ?? aprKey) : null
          return (
            <li key={ep.episode_id}>
              <Link
                to="/episode-n-level"
                search={{ episodeId: ep.episode_id }}
                data-testid="student-episode-row"
                className="flex items-center gap-3 px-4 py-3 hover:bg-canvas transition-colors"
              >
                <span
                  aria-hidden="true"
                  className="inline-block w-2.5 h-2.5 rounded-full shrink-0"
                  style={{ backgroundColor: appropriationDot(ep.appropriation) }}
                />
                {!isDocente && (
                  <span className="font-mono text-xs text-muted shrink-0">
                    {ep.episode_id.slice(0, 8)}...{ep.episode_id.slice(-4)}
                  </span>
                )}
                <span className="flex-1 min-w-0 truncate text-sm text-ink">
                  {ep.tarea_codigo ? (
                    <>
                      <span className="font-medium">{ep.tarea_codigo}</span>
                      {ep.tarea_titulo && <span className="text-muted"> {ep.tarea_titulo}</span>}
                    </>
                  ) : (
                    <span className="text-muted italic">
                      {isDocente ? "Trabajo sin asignar" : "TP huerfana"}
                    </span>
                  )}
                </span>
                <span className="text-xs text-muted shrink-0 hidden sm:inline">
                  {formatShortDate(ep.opened_at)}
                </span>
                <span className="text-xs font-mono text-muted shrink-0 w-28 text-right">
                  {aprText ?? (isDocente ? "sin evaluar" : "sin clasif.")}
                </span>
                <span aria-hidden="true" className="text-border shrink-0">
                  ›
                </span>
              </Link>
            </li>
          )
        })}
      </ul>
      {!isDocente && (
        <footer className="border-t border-border bg-canvas px-4 py-2">
          <p
            className="text-[11px] text-muted leading-relaxed italic"
            data-testid="appropriation-reification-disclaimer"
          >
            {APPROPRIATION_REIFICATION_DISCLAIMER}
          </p>
        </footer>
      )}
    </section>
  )
}
