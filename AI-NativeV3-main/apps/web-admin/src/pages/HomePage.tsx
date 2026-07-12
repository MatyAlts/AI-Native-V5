import { type HeroStat, HeroStatsPanel } from "@platform/ui"
import { useQuery } from "@tanstack/react-query"
import { Activity, Building2, GraduationCap, Layers, Sparkles, TriangleAlert } from "lucide-react"
import type { ReactNode } from "react"
import { byokApi, comisionesApi, universidadesApi } from "../lib/api"
import type { Route } from "../router/Router"

/**
 * HomePage admin — rediseño v2 (layout dashboard 2026 light).
 *
 * Hero panel con stats agregados + sección de estado de plataforma con icon
 * grid + animaciones suaves.
 */
const STATUS_LABEL: Record<string, { label: string; tone: "success" | "warning" | "danger" }> = {
  ready: { label: "Operativo", tone: "success" },
  degraded: { label: "Degradado", tone: "warning" },
  error: { label: "Caído", tone: "danger" },
}

export function HomePage({ onNavigate }: { onNavigate?: (to: Route) => void }): ReactNode {
  // KPIs institucionales via TanStack Query (patrón ComisionesPage) — reemplaza
  // el useState+fetch a mano, que arrastraba estado stale y el gotcha de
  // useCallback en deps de useEffect.
  //
  // NB-19: el conteo real sale de `meta.total` del backend. Hoy los endpoints
  // de universidades/comisiones NO populan `total` (queda null) y paginan por
  // cursor con `limit` (máx 200); antes se pegaba sin `limit` → default 50 →
  // el KPI truncaba a 50. Pedimos `limit: 200` (máximo) y usamos
  // `meta.total ?? data.length`: correcto de punta a punta para la escala del
  // piloto y listo para cuando el backend empiece a devolver el total real.
  const universidadesQuery = useQuery({
    queryKey: ["universidades", { limit: 200 }],
    queryFn: () => universidadesApi.list({ limit: 200 }),
  })

  // NB-22: el KPI contaba con `?estado=activa`, un estado que NO existe en el
  // modelo `Comision` (ni el endpoint acepta ese query param) → contaba 0. El
  // criterio real es el total de comisiones (no borradas) del tenant; el label
  // pasa de "activas" a "registradas".
  const comisionesQuery = useQuery({
    queryKey: ["comisiones", { limit: 200 }],
    queryFn: () => comisionesApi.list({ limit: 200 }),
  })

  const healthQuery = useQuery({
    queryKey: ["health"],
    queryFn: async (): Promise<{ status?: string }> => {
      const r = await fetch("/api/v1/health")
      if (!r.ok) throw new Error(`HTTP ${r.status}`)
      return r.json()
    },
  })

  // BK-2: aviso si no hay ninguna clave BYOK activa. Sin una key de proveedor
  // el ai-gateway no puede resolver completions → el tutor y toda función de IA
  // quedan inertes. Una key está "activa" mientras no tenga `revoked_at`. Solo
  // afirmamos "no hay key" cuando la query resolvió OK (isSuccess) para no
  // disparar el banner por un error transitorio de red.
  const byokKeysQuery = useQuery({
    queryKey: ["byok-keys"],
    queryFn: () => byokApi.list(),
  })
  const noActiveKey =
    byokKeysQuery.isSuccess && !byokKeysQuery.data.some((k) => k.revoked_at === null)

  const universidadesTotal = universidadesQuery.data
    ? (universidadesQuery.data.meta.total ?? universidadesQuery.data.data.length)
    : null
  const comisionesTotal = comisionesQuery.data
    ? (comisionesQuery.data.meta.total ?? comisionesQuery.data.data.length)
    : null

  const apiStatus: string = healthQuery.isError
    ? "no responde"
    : healthQuery.data
      ? (healthQuery.data.status ?? "unknown")
      : "verificando..."

  const known = STATUS_LABEL[apiStatus]

  const stats: HeroStat[] = [
    {
      label: "Universidades",
      value: universidadesQuery.isLoading
        ? "..."
        : universidadesTotal !== null
          ? universidadesTotal.toLocaleString()
          : "—",
      unit: universidadesQuery.isError ? "sin datos" : "registradas",
    },
    {
      label: "Comisiones",
      value: comisionesQuery.isLoading
        ? "..."
        : comisionesTotal !== null
          ? comisionesTotal.toLocaleString()
          : "—",
      unit: comisionesQuery.isError ? "sin datos" : "registradas",
    },
    {
      label: "API Gateway",
      value: known ? known.label : apiStatus === "verificando..." ? "..." : "—",
      tone: known?.tone ?? "default",
      unit: known ? "estado" : "no responde",
      pulse: known?.tone !== "success",
    },
  ]

  return (
    <div className="page-enter space-y-8 p-6 max-w-7xl mx-auto">
      {/* ═══ HEADER ═════════════════════════════════════════════════════ */}
      <header className="flex items-start justify-between gap-6 animate-fade-in-down">
        <div className="flex flex-col gap-1.5 min-w-0">
          <span className="text-[11px] uppercase tracking-[0.12em] font-semibold text-muted">
            Panel de administración institucional
          </span>
          <h1 className="text-3xl font-semibold tracking-tight text-ink leading-none">
            Bienvenido
          </h1>
          <p className="text-sm text-muted leading-relaxed mt-1.5 max-w-xl">
            Resumen del piloto y CRUDs institucionales: universidades, facultades, carreras, planes,
            materias y comisiones.
          </p>
        </div>
      </header>

      {/* ═══ AVISO: SIN CLAVE DE IA ACTIVA (BK-2) ═══════════════════════ */}
      {noActiveKey && (
        <div
          role="alert"
          className="animate-fade-in-down flex flex-col gap-3 rounded-xl border border-warning/40 bg-warning-soft p-4 sm:flex-row sm:items-center sm:justify-between"
        >
          <div className="flex items-start gap-3 min-w-0">
            <span className="mt-0.5 inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-warning/15 text-warning">
              <TriangleAlert className="h-4 w-4" />
            </span>
            <div className="flex flex-col gap-0.5 min-w-0">
              <span className="text-sm font-semibold text-ink">
                No hay ninguna clave de IA activa
              </span>
              <span className="text-xs text-body leading-relaxed max-w-2xl">
                El tutor socrático y todas las funciones de IA no van a funcionar hasta que cargues
                una clave de proveedor (Anthropic, OpenAI, Gemini o Mistral). Configurala para
                habilitar la plataforma.
              </span>
            </div>
          </div>
          <button
            type="button"
            onClick={() => onNavigate?.("byok")}
            className="press-shrink inline-flex shrink-0 items-center gap-1.5 rounded-md bg-accent-brand px-4 py-2 text-sm font-medium text-white hover:bg-accent-brand-deep"
          >
            <Sparkles className="h-4 w-4" />
            Configurar clave de IA
          </button>
        </div>
      )}

      {/* ═══ HERO STATS PANEL ═══════════════════════════════════════════ */}
      <HeroStatsPanel
        eyebrow="Plataforma en números"
        icon={<Activity className="h-4 w-4" />}
        stats={stats}
        footnote="Episodios cerrados se muestran por cohorte — seleccioná una comisión específica para ese KPI."
      />

      {/* ═══ ATAJOS ADMIN ═══════════════════════════════════════════════ */}
      <section className="animate-fade-in-up animate-delay-200" aria-label="Atajos principales">
        <h2 className="text-[11px] uppercase tracking-[0.12em] font-semibold text-muted mb-4">
          Gestión institucional
        </h2>
        <ul className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          <ShortcutCard
            href="#/universidades"
            icon={<Building2 className="h-4 w-4" />}
            title="Universidades"
            description="Tenants raíz y federación institucional"
          />
          <ShortcutCard
            href="#/facultades"
            icon={<Layers className="h-4 w-4" />}
            title="Facultades · Carreras · Planes"
            description="Jerarquía académica de cada institución"
          />
          <ShortcutCard
            href="#/comisiones"
            icon={<GraduationCap className="h-4 w-4" />}
            title="Comisiones"
            description="Cohortes activas con docentes y alumnos asignados"
          />
        </ul>
      </section>
    </div>
  )
}

function ShortcutCard({
  href,
  icon,
  title,
  description,
}: {
  href: string
  icon: ReactNode
  title: string
  description: string
}) {
  return (
    <li>
      <a
        href={href}
        className="hover-lift press-shrink group flex items-start gap-3 rounded-xl border border-border bg-surface p-4 transition-colors hover:border-accent-brand/40"
      >
        <span className="inline-flex h-9 w-9 items-center justify-center rounded-md bg-accent-brand-soft text-accent-brand-deep transition-colors group-hover:bg-accent-brand group-hover:text-white">
          {icon}
        </span>
        <div className="flex flex-col gap-0.5 min-w-0">
          <span className="text-sm font-medium text-ink leading-tight">{title}</span>
          <span className="text-xs text-muted leading-relaxed">{description}</span>
        </div>
      </a>
    </li>
  )
}
