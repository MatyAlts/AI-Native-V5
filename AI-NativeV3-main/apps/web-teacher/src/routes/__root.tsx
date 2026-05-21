/**
 * Root layout del web-teacher (ADR-022, shape docente 2026-05-04).
 *
 * Layout vertical del chrome:
 *   header global (Plataforma N4 · UTN) + ComisionSelectorRouted + email
 *   [sidebar | main scrollable]
 *   AuditFooter compartido (mismo patron que web-student)
 *
 * El sidebar mantiene NAV_GROUPS con `selectedComisionId` en search params
 * para que las URLs sean shareable. Las views consumen el comisionId via
 * Route.useSearch().
 */
import { AuditFooter, type NavGroup, Sidebar } from "@platform/ui"
import {
  Outlet,
  createRootRouteWithContext,
  useNavigate,
  useRouterState,
} from "@tanstack/react-router"
import {
  BarChart3,
  BookOpen,
  CheckSquare,
  ClipboardList,
  Download,
  FileBarChart,
  FileCode2,
  FlaskConical,
  FolderOpen,
  Group,
  Home,
  Layers,
  PieChart,
  ShieldAlert,
  TrendingUp,
} from "lucide-react"
import { useCallback } from "react"
import { ComisionSelectorRouted } from "../components/ComisionSelectorRouted"
import { TenantSelector } from "../components/TenantSelector"
import { ViewModeToggle } from "../components/ViewModeToggle"

export interface RouterContext {
  /** Función de auth, placeholder hasta integración Keycloak (F8). */
  getToken: () => Promise<string | null>
}

const NAV_GROUPS: NavGroup[] = [
  {
    label: "Inicio",
    items: [{ id: "/", label: "Mis comisiones", icon: Home }],
  },
  {
    label: "Trabajo del docente",
    items: [
      { id: "/templates", label: "Plantillas", icon: FileCode2 },
      { id: "/unidades", label: "Unidades", icon: Group },
      { id: "/ejercicios", label: "Banco de ejercicios", icon: BookOpen },
      { id: "/tareas-practicas", label: "Trabajos Prácticos", icon: ClipboardList },
      { id: "/materiales", label: "Materiales", icon: FolderOpen },
      { id: "/correcciones", label: "Correcciones", icon: CheckSquare },
    ],
  },
  {
    label: "Análisis",
    items: [
      { id: "/progression", label: "Progresión", icon: BarChart3 },
      { id: "/student-longitudinal", label: "Evolución por estudiante", icon: TrendingUp },
      { id: "/cohort-quartiles", label: "Cuartiles CII", icon: PieChart },
      { id: "/episode-n-level", label: "Niveles N1-N4", icon: Layers },
      { id: "/cohort-adversarial", label: "Intentos adversos", icon: ShieldAlert },
      { id: "/kappa", label: "Inter-rater", icon: FileBarChart },
      { id: "/instrumentos-cohorte", label: "Instrumentos research", icon: FlaskConical },
    ],
  },
  {
    label: "Operacional",
    items: [{ id: "/export", label: "Exportar", icon: Download }],
  },
]

function RootLayout() {
  const navigate = useNavigate()
  const search = useRouterState({
    select: (s) => s.location.search as Record<string, unknown>,
  })
  const searchComisionId = typeof search.comisionId === "string" ? search.comisionId : null
  const handleNavigate = useCallback(
    (id: string) => {
      // El sidebar navega entre rutas que requieren `comisionId` (search) y rutas
      // que no. Preservar el comisionId actual entre clicks evita el loop al home.
      // Fallback a localStorage cuando venimos de /comision/$id (path param) o de
      // recarga inicial sin search.
      const fromStorage =
        typeof window !== "undefined" ? window.localStorage.getItem("selectedComisionId") : null
      const carry = searchComisionId ?? fromStorage
      if (carry) {
        navigate({
          to: id as never,
          search: ((prev: Record<string, unknown>) => ({
            ...prev,
            comisionId: carry,
            // biome-ignore lint/suspicious/noExplicitAny: search update dinamico
          })) as any,
        })
        return
      }
      navigate({ to: id as never })
    },
    [navigate, searchComisionId],
  )

  return (
    <div className="min-h-screen flex flex-col bg-canvas text-ink">
      <header
        data-testid="teacher-global-header"
        className="border-b border-border bg-white px-6 h-12 flex items-center justify-between gap-4 shrink-0"
      >
        <div className="flex items-center gap-3 min-w-0">
          <span
            aria-hidden="true"
            className="inline-block w-1.5 h-4 rounded-sm"
            style={{ backgroundColor: "var(--color-accent-brand)" }}
          />
          <h1 className="text-sm font-semibold tracking-tight text-ink">
            Plataforma N4 <span className="text-muted mx-1">·</span> UTN
          </h1>
        </div>
        <div className="flex items-center gap-3 shrink-0">
          <ViewModeToggle />
          <span className="w-px h-5 bg-border" aria-hidden="true" />
          <TenantSelector />
          <span className="w-px h-5 bg-border" aria-hidden="true" />
          <ComisionSelectorRouted />
        </div>
      </header>

      <div className="flex-1 flex min-h-0">
        <Sidebar
          navGroups={NAV_GROUPS}
          headerLabel="Docente · N4"
          collapsedHeaderLabel="N4"
          storageKey="web-teacher-sidebar-collapsed"
          activeItemId={window.location.pathname}
          onNavigate={handleNavigate}
        />
        <main className="flex-1 overflow-x-hidden overflow-y-auto bg-canvas">
          <Outlet />
        </main>
      </div>

      <AuditFooter episodeId={null} classifierHash={null} />
    </div>
  )
}

export const Route = createRootRouteWithContext<RouterContext>()({
  component: RootLayout,
  notFoundComponent: () => (
    <div className="flex-1 flex items-center justify-center p-8 min-h-screen">
      <div className="max-w-md text-center">
        <h1 className="text-2xl font-semibold text-ink">Vista no encontrada</h1>
        <p className="mt-2 text-sm text-muted">
          La URL que intentaste abrir no corresponde a ninguna vista del web-teacher.
        </p>
      </div>
    </div>
  ),
})
