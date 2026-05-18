import { HeroStatsPanel, type HeroStat } from "@platform/ui"
import { Activity, Building2, GraduationCap, Layers } from "lucide-react"
import type { ReactNode } from "react"
import { useEffect, useState } from "react"

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

interface KpiState {
  value: number | null
  loading: boolean
  error: string | null
}

const initialKpi: KpiState = { value: null, loading: true, error: null }

async function fetchCount(url: string): Promise<number> {
  const r = await fetch(url)
  if (!r.ok) throw new Error(`HTTP ${r.status}`)
  const body = await r.json()
  if (Array.isArray(body)) return body.length
  if (body && typeof body === "object") {
    const asData = body as { data?: unknown; items?: unknown }
    if (Array.isArray(asData.data)) return asData.data.length
    if (Array.isArray(asData.items)) return asData.items.length
  }
  throw new Error("Unexpected response shape")
}

export function HomePage(): ReactNode {
  const [apiStatus, setApiStatus] = useState<string>("verificando...")
  const [universidades, setUniversidades] = useState<KpiState>(initialKpi)
  const [comisiones, setComisiones] = useState<KpiState>(initialKpi)

  useEffect(() => {
    fetch("/health")
      .then((r) => r.json())
      .then((d) => setApiStatus(d.status ?? "unknown"))
      .catch(() => setApiStatus("no responde"))
  }, [])

  useEffect(() => {
    fetchCount("/api/v1/universidades")
      .then((n) => setUniversidades({ value: n, loading: false, error: null }))
      .catch((e) => setUniversidades({ value: null, loading: false, error: String(e) }))
  }, [])

  useEffect(() => {
    fetchCount("/api/v1/comisiones?estado=activa")
      .then((n) => setComisiones({ value: n, loading: false, error: null }))
      .catch((e) => setComisiones({ value: null, loading: false, error: String(e) }))
  }, [])

  const known = STATUS_LABEL[apiStatus]

  const stats: HeroStat[] = [
    {
      label: "Universidades",
      value: universidades.loading
        ? "..."
        : universidades.value !== null
          ? universidades.value.toLocaleString()
          : "—",
      unit: universidades.error ? "sin datos" : "registradas",
    },
    {
      label: "Comisiones",
      value: comisiones.loading
        ? "..."
        : comisiones.value !== null
          ? comisiones.value.toLocaleString()
          : "—",
      unit: "activas",
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
            Resumen del piloto y CRUDs institucionales: universidades, facultades, carreras,
            planes, materias y comisiones.
          </p>
        </div>
      </header>

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
