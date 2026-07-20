/**
 * Pagina "Mi progreso" del web-student (F9).
 *
 * Vista de SOLO LECTURA de la progresion pedagogica longitudinal del alumno:
 *   1. Trayectoria de apropiacion en problemas analogos (CII longitudinal, ADR-018).
 *   2. Sus episodios cerrados.
 *   3. Señales pedagogicas vs su cohorte (alertas, ADR-022) — cuando hay datos.
 *
 * NO es un ranking ni una nota. Es como fue cambiando SU forma de trabajar con
 * el tutor a lo largo de TPs parecidas. Presentacion no-reificante (ADR-053):
 * los tres modos de apropiacion son cualitativos, no un puntaje; la "tendencia"
 * es una operacionalizacion conservadora declarada, no una verdad academica.
 *
 * Endpoints (analytics-service, via ROUTE_MAP `/api/v1/analytics`):
 *   - GET /student/me/episodes?comision_id=X          (listStudentEpisodes, ya en api.ts)
 *   - GET /student/{pseudonym}/cii-evolution-longitudinal?comision_id=X  (fetch inline)
 *   - GET /student/{pseudonym}/alerts?comision_id=X                       (fetch inline)
 *
 * Pseudonimo del alumno: el backend autoriza estos dos endpoints exigiendo
 * `student_pseudonym == X-User-Id` (rama estudiante de require_student_progress_access).
 * Resolvemos ese id con `getCurrentUserUuid()` (el mismo UUID que el fetch-patch
 * manda como X-User-Id), con fallback al `student_pseudonym` que devuelve
 * `/student/me/episodes` (resuelto server-side desde el header). Asi el path
 * SIEMPRE coincide con la identidad que ve el gateway, en dev y con Clerk.
 *
 * k-anonymity: si CII devuelve `sufficient_data=false` (todos los grupos con
 * N<3) o alerts trae `cohort_stats.insufficient_data=true` (cohorte N<5), lo
 * mostramos con un mensaje amable, nunca como error.
 */
import { HelpButton } from "@platform/ui"
import { useQuery } from "@tanstack/react-query"
import { useNavigate } from "@tanstack/react-router"
import { ArrowLeft, History, Info, Minus, Sparkles, TrendingDown, TrendingUp } from "lucide-react"
import { type ReactNode, useState } from "react"
import { getCurrentUserUuid } from "../auth"
import {
  type MateriaInscripta,
  type StudentEpisode,
  listMisMaterias,
  listStudentEpisodes,
} from "../lib/api"

// ── Tipos de los endpoints F9 (fetch inline: NO tocamos lib/api.ts) ──────
// FOLLOW-UP: si esta vista se estabiliza, promover fetchCiiEvolution /
// fetchStudentAlerts + estos tipos a src/lib/api.ts para reuso.

interface CIIEvolutionGroup {
  n_episodes: number
  /** Secuencia ordinal de apropiacion por episodio analogo: 0=delegacion,
   * 1=superficial, 2=reflexiva. Ordenada por `classified_at`. */
  scores_ordinal: number[]
  slope: number | null
  insufficient_data: boolean
}

interface CIIEvolutionTemplate extends CIIEvolutionGroup {
  template_id: string
}

interface CIIEvolutionUnidad extends CIIEvolutionGroup {
  unidad_id: string
  unidad_nombre: string
}

interface CIIEvolutionLongitudinal {
  student_pseudonym: string
  comision_id: string
  n_groups_evaluated: number
  n_groups_insufficient: number
  n_episodes_total: number
  evolution_per_template: CIIEvolutionTemplate[]
  evolution_per_unidad: CIIEvolutionUnidad[]
  mean_slope: number | null
  sufficient_data: boolean
  labeler_version: string
}

interface StudentAlert {
  code: string
  severity: "low" | "medium" | "high"
  title: string
  detail: string
  threshold_used: string
  z_score: number | null
}

interface StudentAlerts {
  student_pseudonym: string
  comision_id: string
  labeler_version: string
  student_slope: number | null
  cohort_stats: { insufficient_data?: boolean; n_students_evaluated?: number }
  quartile: "Q1" | "Q2" | "Q3" | "Q4" | null
  alerts: StudentAlert[]
  n_alerts: number
  highest_severity: "low" | "medium" | "high" | null
}

async function fetchCiiEvolution(
  pseudonym: string,
  comisionId: string,
): Promise<CIIEvolutionLongitudinal> {
  const qs = new URLSearchParams({ comision_id: comisionId })
  const r = await fetch(
    `/api/v1/analytics/student/${pseudonym}/cii-evolution-longitudinal?${qs.toString()}`,
  )
  if (!r.ok) throw new Error(`cii-evolution-longitudinal failed: ${r.status}`)
  return (await r.json()) as CIIEvolutionLongitudinal
}

async function fetchStudentAlerts(pseudonym: string, comisionId: string): Promise<StudentAlerts> {
  const qs = new URLSearchParams({ comision_id: comisionId })
  const r = await fetch(`/api/v1/analytics/student/${pseudonym}/alerts?${qs.toString()}`)
  if (!r.ok) throw new Error(`student alerts failed: ${r.status}`)
  return (await r.json()) as StudentAlerts
}

// ── Escala de apropiacion (cualitativa, NO un puntaje) ───────────────────
// Colores tomados del DS: delegacion en slate neutro (pasivo, sin juicio de
// valor tipo rojo/verde que reificaria), superficial en el azul de marca,
// reflexiva en la terracota que la tesis usa para "apropiacion" (level-n4).

interface ModoApropiacion {
  label: string
  short: string
  color: string
}

const MODOS: Record<number, ModoApropiacion> = {
  0: { label: "Delegacion", short: "Delegacion", color: "var(--color-muted)" },
  1: {
    label: "Apropiacion superficial",
    short: "Superficial",
    color: "var(--color-accent-brand)",
  },
  2: {
    label: "Apropiacion reflexiva",
    short: "Reflexiva",
    color: "var(--color-level-n4)",
  },
}

const APPROPRIATION_TO_ORDINAL: Record<string, number> = {
  delegacion_pasiva: 0,
  apropiacion_superficial: 1,
  apropiacion_reflexiva: 2,
}

// ── Pagina ───────────────────────────────────────────────────────────────

export function MiProgresoPage() {
  const navigate = useNavigate()

  const materiasQuery = useQuery({
    queryKey: ["mis-materias"],
    queryFn: () => listMisMaterias(),
    staleTime: 5 * 60 * 1000,
  })

  const materias = materiasQuery.data ?? []
  const [selectedComisionId, setSelectedComisionId] = useState<string | null>(null)
  const comisionId = selectedComisionId ?? materias[0]?.comision_id ?? null

  return (
    <div className="page-enter flex-1 overflow-y-auto px-6 py-10">
      <div className="max-w-3xl mx-auto">
        <button
          type="button"
          onClick={() => navigate({ to: "/" })}
          className="press-shrink inline-flex items-center gap-1.5 text-xs text-muted hover:text-ink mb-6"
          data-testid="mi-progreso-back"
        >
          <ArrowLeft className="h-3.5 w-3.5" aria-hidden="true" />
          Volver a mis materias
        </button>

        <header className="animate-fade-in-down mb-8 flex items-start justify-between gap-4">
          <div className="min-w-0">
            <p className="text-[11px] font-mono uppercase tracking-[0.12em] text-muted mb-2">
              Tu progresion pedagogica
            </p>
            <h1 className="text-3xl font-semibold tracking-tight text-ink leading-none">
              Mi progreso
            </h1>
            <p className="text-sm text-muted leading-relaxed mt-2 max-w-xl">
              Como fue cambiando tu forma de trabajar con el tutor a lo largo de tareas parecidas.
              No es una nota ni un ranking: es tu recorrido, para vos.
            </p>
          </div>
          <HelpButton title="Mi progreso" content={progresoHelp} />
        </header>

        {materiasQuery.isLoading && <LoadingSkeleton />}
        {materiasQuery.error && <ErrorPanel error={String(materiasQuery.error)} />}
        {!materiasQuery.isLoading && !materiasQuery.error && materias.length === 0 && (
          <NoMateriasState onGoHome={() => navigate({ to: "/" })} />
        )}

        {!materiasQuery.isLoading && !materiasQuery.error && comisionId && (
          <>
            {materias.length > 1 && (
              <MateriaPicker
                materias={materias}
                selected={comisionId}
                onSelect={setSelectedComisionId}
              />
            )}
            <ProgresoContent comisionId={comisionId} />
          </>
        )}
      </div>
    </div>
  )
}

// ── Contenido por comision ───────────────────────────────────────────────

function ProgresoContent({ comisionId }: { comisionId: string }) {
  const episodesQuery = useQuery({
    queryKey: ["mi-progreso", "episodes", comisionId],
    queryFn: () => listStudentEpisodes(comisionId),
    staleTime: 60 * 1000,
  })

  // El pseudonimo ES el X-User-Id que ve el gateway. getCurrentUserUuid() lo
  // tiene (mismo valor que el fetch-patch envia); si aun no esta seteado,
  // caemos al que resuelve el propio backend en /student/me/episodes.
  const pseudonym = getCurrentUserUuid() ?? episodesQuery.data?.student_pseudonym ?? null

  const ciiQuery = useQuery({
    queryKey: ["mi-progreso", "cii", comisionId, pseudonym],
    queryFn: () => fetchCiiEvolution(pseudonym as string, comisionId),
    enabled: !!pseudonym,
    staleTime: 60 * 1000,
  })

  const alertsQuery = useQuery({
    queryKey: ["mi-progreso", "alerts", comisionId, pseudonym],
    queryFn: () => fetchStudentAlerts(pseudonym as string, comisionId),
    enabled: !!pseudonym,
    staleTime: 60 * 1000,
  })

  return (
    <div className="space-y-10">
      <TrayectoriaSection query={ciiQuery} episodes={episodesQuery.data?.episodes ?? []} />
      <SeñalesSection query={alertsQuery} />
      <EpisodiosSection query={episodesQuery} />
    </div>
  )
}

// ── Seccion 1: trayectoria de apropiacion (CII longitudinal) ─────────────

function TrayectoriaSection({
  query,
  episodes,
}: {
  query: ReturnType<typeof useQuery<CIIEvolutionLongitudinal>>
  episodes: StudentEpisode[]
}) {
  // template_id -> titulo legible, derivado de los episodios del alumno. El
  // endpoint CII solo trae UUIDs de template, no nombres; los episodios si.
  const templateTitles = new Map<string, string>()
  for (const ep of episodes) {
    if (ep.template_id && ep.tarea_titulo && !templateTitles.has(ep.template_id)) {
      templateTitles.set(ep.template_id, ep.tarea_titulo)
    }
  }

  return (
    <section aria-labelledby="progreso-trayectoria-title" className="animate-fade-in-up">
      <SectionHeader
        id="progreso-trayectoria-title"
        icon={<Sparkles className="h-4 w-4 text-accent-brand" aria-hidden="true" />}
        title="Tu trayectoria en tareas parecidas"
        subtitle="Cada fila junta tus episodios de un mismo problema logico y muestra como fue tu modo de trabajo, del primero al ultimo."
      />

      {query.isLoading && <div className="skeleton h-40 rounded-xl mt-4" />}
      {query.error && <ErrorPanel error={String(query.error)} />}

      {query.data && <TrayectoriaBody data={query.data} templateTitles={templateTitles} />}
    </section>
  )
}

function TrayectoriaBody({
  data,
  templateTitles,
}: {
  data: CIIEvolutionLongitudinal
  templateTitles: Map<string, string>
}) {
  // Preferimos los grupos por template (agrupamiento canonico ADR-018); si el
  // piloto no tiene templates configurados, caemos a los grupos por unidad.
  const templateGroups = data.evolution_per_template.map((g) => ({
    key: g.template_id,
    nombre: templateTitles.get(g.template_id) ?? "Problema analogo",
    grupo: g as CIIEvolutionGroup,
  }))
  const unidadGroups = data.evolution_per_unidad.map((g) => ({
    key: g.unidad_id,
    nombre: g.unidad_nombre,
    grupo: g as CIIEvolutionGroup,
  }))
  const groups = templateGroups.length > 0 ? templateGroups : unidadGroups

  const withData = groups.filter((g) => !g.grupo.insufficient_data)
  const pending = groups.filter((g) => g.grupo.insufficient_data)

  // k-anonymity / RN-130: sin ningun grupo con N>=3 episodios analogos, no hay
  // trayectoria que dibujar todavia. Mensaje amable, nunca un error.
  if (withData.length === 0) {
    return (
      <div className="mt-4 space-y-4">
        <Leyenda />
        <div
          data-testid="mi-progreso-trayectoria-insuficiente"
          className="rounded-xl border border-border bg-surface p-6"
        >
          <p className="text-sm font-medium text-ink mb-1">
            Todavia no hay trayectoria para mostrar
          </p>
          <p className="text-sm text-muted leading-relaxed max-w-lg">
            Para ver como evoluciona tu forma de trabajar necesitas al menos 3 episodios cerrados en
            tareas del mismo tipo. Ya llevas {data.n_episodes_total}{" "}
            {data.n_episodes_total === 1 ? "episodio" : "episodios"}: segui resolviendo y esta
            seccion se va a ir llenando sola.
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="mt-4 space-y-4">
      <Leyenda />
      <ul
        className="rounded-xl border border-border bg-surface divide-y divide-border-soft overflow-hidden"
        data-testid="mi-progreso-trayectoria-list"
      >
        {withData.map(({ key, nombre, grupo }) => (
          <li key={key} className="px-5 py-5">
            <TrayectoriaRow nombre={nombre} grupo={grupo} />
          </li>
        ))}
      </ul>

      {pending.length > 0 && (
        <p className="text-xs text-muted-soft leading-relaxed">
          {pending.length}{" "}
          {pending.length === 1
            ? "tarea mas se va a sumar cuando tenga"
            : "tareas mas se van a sumar cuando tengan"}{" "}
          3 o mas episodios cerrados.
        </p>
      )}

      <p className="text-[11px] text-muted-soft leading-relaxed">
        La tendencia es una lectura conservadora del recorrido (pendiente ordinal sobre los tres
        modos, ADR-018), no una calificacion.
      </p>
    </div>
  )
}

function TrayectoriaRow({
  nombre,
  grupo,
}: {
  nombre: string
  grupo: CIIEvolutionGroup
}) {
  const ultimo = grupo.scores_ordinal[grupo.scores_ordinal.length - 1]
  const modo = ultimo != null ? MODOS[ultimo] : undefined
  return (
    <div>
      <div className="flex items-start justify-between gap-4 mb-3">
        <div className="min-w-0">
          <p className="text-sm font-medium text-ink truncate">{nombre}</p>
          <p className="text-xs text-muted mt-0.5">
            {grupo.n_episodes} episodios analogos
            {modo && (
              <>
                <span className="text-muted-soft mx-1.5">·</span>
                ultimo: {modo.short.toLowerCase()}
              </>
            )}
          </p>
        </div>
        <TendenciaChip slope={grupo.slope} />
      </div>
      <TrayectoriaStrip scores={grupo.scores_ordinal} nombre={nombre} />
    </div>
  )
}

/**
 * Sparkline de apropiacion: una lane por cada modo (reflexiva arriba), un punto
 * por episodio analogo conectado en orden cronologico. Accesible via aria-label
 * que enumera la secuencia en palabras.
 */
function TrayectoriaStrip({ scores, nombre }: { scores: number[]; nombre: string }) {
  const n = scores.length
  const W = 100
  const H = 46
  const padX = 6
  const laneY = [10, 23, 36] // ordinal 2, 1, 0 (arriba a abajo)
  const yFor = (ordinal: number) => laneY[2 - ordinal] ?? laneY[2]
  const xFor = (i: number) => (n <= 1 ? W / 2 : padX + (i * (W - 2 * padX)) / (n - 1))

  const points = scores.map((s, i) => ({ x: xFor(i), y: yFor(s), s }))
  const polyline = points.map((p) => `${p.x},${p.y}`).join(" ")

  const aria = `Trayectoria en ${nombre}: ${scores.map((s) => MODOS[s]?.short ?? "").join(", ")}.`

  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      preserveAspectRatio="none"
      className="w-full h-12"
      role="img"
      aria-label={aria}
      data-testid="mi-progreso-strip"
    >
      {/* Lineas guia de las 3 lanes */}
      {laneY.map((y) => (
        <line
          key={y}
          x1={padX}
          y1={y}
          x2={W - padX}
          y2={y}
          stroke="var(--color-border-soft)"
          strokeWidth={0.5}
          vectorEffect="non-scaling-stroke"
        />
      ))}
      {/* Recorrido */}
      {n > 1 && (
        <polyline
          points={polyline}
          fill="none"
          stroke="var(--color-border-strong)"
          strokeWidth={1}
          vectorEffect="non-scaling-stroke"
          strokeLinejoin="round"
          strokeLinecap="round"
        />
      )}
      {/* Puntos por episodio */}
      {points.map((p, i) => (
        <circle
          key={`${p.x}-${i}`}
          cx={p.x}
          cy={p.y}
          r={2.6}
          fill={MODOS[p.s]?.color ?? "var(--color-muted)"}
          stroke="var(--color-surface)"
          strokeWidth={0.8}
          vectorEffect="non-scaling-stroke"
        />
      ))}
    </svg>
  )
}

function Leyenda() {
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5" aria-hidden="true">
      {[2, 1, 0].map((ord) => {
        const m = MODOS[ord]
        if (!m) return null
        return (
          <span key={ord} className="inline-flex items-center gap-1.5">
            <span
              className="inline-block w-2.5 h-2.5 rounded-full"
              style={{ backgroundColor: m.color }}
            />
            <span className="text-xs text-muted">{m.label}</span>
          </span>
        )
      })}
    </div>
  )
}

function TendenciaChip({ slope }: { slope: number | null }) {
  if (slope == null) return null
  let icon: ReactNode
  let label: string
  let tone: string
  if (slope > 0.05) {
    icon = <TrendingUp className="h-3.5 w-3.5" aria-hidden="true" />
    label = "En ascenso"
    tone = "text-accent-brand-deep bg-accent-brand-soft border-accent-brand/20"
  } else if (slope < -0.05) {
    icon = <TrendingDown className="h-3.5 w-3.5" aria-hidden="true" />
    label = "En descenso"
    tone = "text-warning bg-warning-soft border-warning/20"
  } else {
    icon = <Minus className="h-3.5 w-3.5" aria-hidden="true" />
    label = "Estable"
    tone = "text-muted bg-surface-alt border-border"
  }
  return (
    <span
      className={`shrink-0 inline-flex items-center gap-1 px-2 py-0.5 rounded-full border text-[11px] font-medium ${tone}`}
      data-testid="mi-progreso-tendencia"
    >
      {icon}
      {label}
    </span>
  )
}

// ── Seccion 2: señales pedagogicas (alertas vs cohorte) ──────────────────

function SeñalesSection({
  query,
}: {
  query: ReturnType<typeof useQuery<StudentAlerts>>
}) {
  if (query.isLoading) {
    return (
      <section className="animate-fade-in-up">
        <SectionHeader
          icon={<Info className="h-4 w-4 text-accent-brand" aria-hidden="true" />}
          title="Señales para acompañarte"
        />
        <div className="skeleton h-24 rounded-xl mt-4" />
      </section>
    )
  }
  // Un error en alertas NO debe romper la pagina: es una seccion secundaria.
  if (query.error || !query.data) return null

  const data = query.data
  const cohortInsufficient = data.cohort_stats?.insufficient_data === true

  return (
    <section aria-labelledby="progreso-señales-title" className="animate-fade-in-up">
      <SectionHeader
        id="progreso-señales-title"
        icon={<Info className="h-4 w-4 text-accent-brand" aria-hidden="true" />}
        title="Señales para acompañarte"
        subtitle="Pistas pedagogicas, no clinicas: para que sepas donde apoyarte, nunca para calificarte."
      />

      {cohortInsufficient ? (
        <div
          data-testid="mi-progreso-señales-insuficiente"
          className="mt-4 rounded-xl border border-border bg-surface p-6"
        >
          <p className="text-sm font-medium text-ink mb-1">Todavia no comparamos con tu comision</p>
          <p className="text-sm text-muted leading-relaxed max-w-lg">
            Necesitamos datos de al menos 5 estudiantes para poder dar señales sin exponer a nadie.
            Mientras tanto, tu progreso se mira solo, no contra un ranking.
          </p>
        </div>
      ) : data.alerts.length === 0 ? (
        <div
          data-testid="mi-progreso-señales-ok"
          className="mt-4 rounded-xl border border-border bg-surface p-6"
        >
          <p className="text-sm font-medium text-ink mb-1">Sin señales por ahora</p>
          <p className="text-sm text-muted leading-relaxed max-w-lg">
            No hay nada que marcar en tu recorrido reciente. Segui a tu ritmo.
          </p>
        </div>
      ) : (
        <ul className="mt-4 space-y-3" data-testid="mi-progreso-señales-list">
          {data.alerts.map((a) => (
            <li key={a.code}>
              <SeñalCard alert={a} />
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}

function SeñalCard({ alert }: { alert: StudentAlert }) {
  // Severidad -> tono. Medium/high usan warning-soft (calido, sin alarmar);
  // low se queda en surface neutro. Nunca danger: no es un error del alumno.
  const strong = alert.severity === "high" || alert.severity === "medium"
  const container = strong ? "border-warning/30 bg-warning-soft" : "border-border bg-surface"
  return (
    <div
      className={`rounded-xl border p-5 ${container}`}
      data-testid="mi-progreso-señal"
      data-severity={alert.severity}
    >
      <p className="text-sm font-semibold text-ink mb-1">{alert.title}</p>
      <p className="text-sm text-body leading-relaxed">{alert.detail}</p>
    </div>
  )
}

// ── Seccion 3: episodios cerrados ────────────────────────────────────────

function EpisodiosSection({
  query,
}: {
  query: ReturnType<typeof useQuery<Awaited<ReturnType<typeof listStudentEpisodes>>>>
}) {
  return (
    <section aria-labelledby="progreso-episodios-title" className="animate-fade-in-up">
      <SectionHeader
        id="progreso-episodios-title"
        icon={<History className="h-4 w-4 text-accent-brand" aria-hidden="true" />}
        title="Tus episodios"
        subtitle="Cada vez que trabajaste una tarea con el tutor. En orden, del mas reciente al mas viejo."
      />

      {query.isLoading && <div className="skeleton h-32 rounded-xl mt-4" />}
      {query.error && <ErrorPanel error={String(query.error)} />}

      {query.data && query.data.episodes.length === 0 && (
        <div
          data-testid="mi-progreso-episodios-empty"
          className="mt-4 rounded-xl border border-border bg-surface p-6"
        >
          <p className="text-sm font-medium text-ink mb-1">Todavia no cerraste episodios</p>
          <p className="text-sm text-muted leading-relaxed max-w-lg">
            Cuando resuelvas una tarea con el tutor y cierres el episodio, va a aparecer aca con el
            modo de trabajo que registro la plataforma.
          </p>
        </div>
      )}

      {query.data && query.data.episodes.length > 0 && (
        <ul
          className="mt-4 rounded-xl border border-border bg-surface divide-y divide-border-soft overflow-hidden"
          data-testid="mi-progreso-episodios-list"
        >
          {query.data.episodes.map((ep) => (
            <li key={ep.episode_id}>
              <EpisodioRow episode={ep} />
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}

function EpisodioRow({ episode }: { episode: StudentEpisode }) {
  const label =
    episode.tarea_codigo && episode.tarea_titulo
      ? `${episode.tarea_codigo} · ${episode.tarea_titulo}`
      : (episode.tarea_titulo ?? episode.tarea_codigo ?? "Tarea (sin titulo)")
  const fecha = episode.closed_at ?? episode.opened_at
  const ordinal =
    episode.appropriation != null ? APPROPRIATION_TO_ORDINAL[episode.appropriation] : undefined
  const modo = ordinal != null ? MODOS[ordinal] : undefined
  const paused = episode.estado === "paused"

  return (
    <div className="px-5 py-4 flex items-start gap-4" data-testid="mi-progreso-episodio">
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-ink truncate">{label}</p>
        <p className="text-xs text-muted mt-0.5">
          {fecha ? formatDate(fecha) : "Sin fecha"}
          <span className="text-muted-soft mx-1.5">·</span>
          {episode.events_count} interacciones
          {paused && (
            <>
              <span className="text-muted-soft mx-1.5">·</span>
              <span className="text-warning">pausado</span>
            </>
          )}
        </p>
      </div>
      {modo ? (
        <span
          className="shrink-0 inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-medium"
          style={{
            color: modo.color,
            backgroundColor: "color-mix(in oklch, transparent, currentColor 10%)",
          }}
        >
          <span
            className="inline-block w-2 h-2 rounded-full"
            style={{ backgroundColor: modo.color }}
          />
          {modo.short}
        </span>
      ) : (
        <span className="shrink-0 text-[11px] text-muted-soft">sin clasificar</span>
      )}
    </div>
  )
}

// ── Selector de materia (solo si el alumno cursa mas de una) ─────────────

function MateriaPicker({
  materias,
  selected,
  onSelect,
}: {
  materias: MateriaInscripta[]
  selected: string
  onSelect: (comisionId: string) => void
}) {
  return (
    <fieldset className="mb-8 m-0 p-0 border-0">
      <legend className="text-[11px] font-mono uppercase tracking-[0.12em] text-muted mb-2 p-0">
        Materia
      </legend>
      <div className="flex flex-wrap gap-2">
        {materias.map((m) => {
          const active = m.comision_id === selected
          return (
            <button
              key={m.inscripcion_id}
              type="button"
              onClick={() => onSelect(m.comision_id)}
              aria-pressed={active}
              className={`press-shrink px-3 py-1.5 rounded-md border text-xs font-medium transition-colors ${
                active
                  ? "border-accent-brand/40 bg-accent-brand-soft text-accent-brand-deep"
                  : "border-border bg-surface text-body hover:bg-surface-alt"
              }`}
            >
              <span className="font-mono">{m.codigo}</span>
              <span className="text-muted-soft mx-1">·</span>
              {m.nombre}
            </button>
          )
        })}
      </div>
    </fieldset>
  )
}

// ── Auxiliares de presentacion ───────────────────────────────────────────

function SectionHeader({
  id,
  icon,
  title,
  subtitle,
}: {
  id?: string
  icon: ReactNode
  title: string
  subtitle?: string
}) {
  return (
    <div>
      <div className="flex items-center gap-2">
        {icon}
        <h2 id={id} className="text-lg font-semibold tracking-tight text-ink">
          {title}
        </h2>
      </div>
      {subtitle && <p className="text-sm text-muted leading-relaxed mt-1.5 max-w-xl">{subtitle}</p>}
    </div>
  )
}

function LoadingSkeleton() {
  return (
    <div className="space-y-6" data-testid="mi-progreso-loading">
      <div className="skeleton h-40 rounded-xl" />
      <div className="skeleton h-24 rounded-xl" />
      <div className="skeleton h-32 rounded-xl" />
    </div>
  )
}

function ErrorPanel({ error }: { error: string }) {
  return (
    <div
      role="alert"
      className="mt-4 rounded-xl border border-danger/30 bg-danger-soft p-6"
      data-testid="mi-progreso-error"
    >
      <p className="text-sm font-semibold text-danger mb-2">
        No pudimos cargar esta parte de tu progreso.
      </p>
      <p className="text-xs font-mono text-danger/80 break-all">{error}</p>
    </div>
  )
}

function NoMateriasState({ onGoHome }: { onGoHome: () => void }) {
  return (
    <div
      data-testid="mi-progreso-no-materias"
      className="rounded-xl border border-border bg-surface p-8 text-center"
    >
      <p className="text-base font-medium text-ink mb-2">Todavia no estas en ninguna comision</p>
      <p className="text-sm text-muted max-w-md mx-auto leading-relaxed mb-4">
        Cuando te unas a la comision de tu materia y empieces a trabajar con el tutor, vas a ver aca
        tu progreso.
      </p>
      <button
        type="button"
        onClick={onGoHome}
        className="press-shrink inline-flex items-center gap-1.5 px-4 py-2 rounded-md bg-accent-brand text-white text-sm font-medium hover:opacity-90"
      >
        Ir a mis materias
      </button>
    </div>
  )
}

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString("es-AR", {
      day: "2-digit",
      month: "short",
      year: "numeric",
    })
  } catch {
    return iso
  }
}

// ── Contenido del HelpButton (inline: no tocamos utils/helpContent.tsx) ──

const progresoHelp: ReactNode = (
  <div className="space-y-4 text-muted-soft">
    <p className="text-lg font-medium text-[var(--text-inverse)]">Mi progreso</p>
    <p>
      Esta vista te muestra como fue cambiando tu forma de trabajar con el tutor. No hay nota, no
      hay ranking, no te compara con nadie por default.
    </p>
    <ul className="list-disc list-inside space-y-2 ml-4">
      <li>
        <strong>Trayectoria:</strong> junta tus episodios de tareas parecidas y marca tu modo de
        apropiacion en cada uno, del primero al ultimo.
      </li>
      <li>
        <strong>Tres modos:</strong> delegacion (dejas que el tutor resuelva), apropiacion
        superficial y apropiacion reflexiva (te apropiaste de la solucion pensandola).
      </li>
      <li>
        <strong>Señales:</strong> pistas pedagogicas para acompañarte. Solo aparecen si hay datos
        suficientes de tu comision, y nunca para calificarte.
      </li>
      <li>
        <strong>Es tuyo:</strong> el listado filtra por tu identidad. Solo vos ves esto.
      </li>
    </ul>
    <div className="bg-sidebar-bg-edge p-4 rounded-lg mt-2">
      <p className="text-warning font-medium">Sobre la tendencia</p>
      <p className="text-sm mt-1">
        "En ascenso", "Estable" o "En descenso" son una lectura conservadora de tu recorrido
        (ADR-018), no una verdad absoluta ni una calificacion.
      </p>
    </div>
  </div>
)
