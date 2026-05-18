/**
 * Router principal del web-admin.
 *
 * F1: rutas simples basadas en useState. En F2-F3 se reemplaza por TanStack Router con
 * type-safe routes y code splitting automático.
 *
 * Layout: Sidebar fijo a la izquierda (colapsable, agrupado por dominio) + main scrollable
 * a la derecha. La topbar/header anterior fue reemplazada por el Sidebar para liberar
 * espacio vertical y dar lugar a más entidades académicas sin que la nav se vuelva un
 * carrusel horizontal apretado.
 */
import { type NavGroup, Sidebar } from "@platform/ui"
import { TenantSelector } from "../components/TenantSelector"
import {
  Building2,
  CalendarDays,
  FileBarChart,
  GraduationCap,
  Home,
  Key,
  Landmark,
  Layers,
  Library,
  ShieldAlert,
  ShieldCheck,
  Upload,
  Users,
} from "lucide-react"
import { type ReactNode, useState } from "react"
import { AuditoriaPage } from "../pages/AuditoriaPage"
import { BulkImportPage } from "../pages/BulkImportPage"
import { ByokPage } from "../pages/ByokPage"
import { CarrerasPage } from "../pages/CarrerasPage"
import { ClasificacionesPage } from "../pages/ClasificacionesPage"
import { ComisionesPage } from "../pages/ComisionesPage"
import { FacultadesPage } from "../pages/FacultadesPage"
import { GovernanceEventsPage } from "../pages/GovernanceEventsPage"
import { HomePage } from "../pages/HomePage"
import { MateriasPage } from "../pages/MateriasPage"
import { PeriodosPage } from "../pages/PeriodosPage"
import { PlanesPage } from "../pages/PlanesPage"
import { UniversidadesPage } from "../pages/UniversidadesPage"

/**
 * Identificadores de ruta del web-admin.
 *
 * Mantener sincronizado con `NAV_GROUPS` y el switch de render en `Router`. Cuando se
 * migre a TanStack Router type-safe (F2-F3), reemplazar este union por los path types
 * generados.
 */
export type Route =
  | "home"
  | "universidades"
  | "facultades"
  | "carreras"
  | "planes"
  | "materias"
  | "comisiones"
  | "clasificaciones"
  | "periodos"
  | "bulk-import"
  | "auditoria"
  | "governance-events"
  | "byok"

export interface NavContext {
  current: Route
  navigate: (to: Route) => void
}

const NAV_GROUPS: NavGroup[] = [
  {
    items: [{ id: "home", label: "Inicio", icon: Home }],
  },
  {
    label: "Jerarquía académica",
    items: [
      { id: "universidades", label: "Universidades", icon: Landmark },
      { id: "facultades", label: "Facultades", icon: Building2 },
      { id: "carreras", label: "Carreras", icon: GraduationCap },
      { id: "planes", label: "Planes", icon: Library },
      { id: "materias", label: "Materias", icon: Layers },
      { id: "comisiones", label: "Comisiones", icon: Users },
    ],
  },
  {
    label: "Pedagogía",
    items: [{ id: "clasificaciones", label: "Clasificaciones N4", icon: FileBarChart }],
  },
  {
    label: "Auditoria",
    items: [
      { id: "auditoria", label: "Integridad CTR", icon: ShieldCheck },
      { id: "governance-events", label: "Eventos de gobernanza", icon: ShieldAlert },
    ],
  },
  {
    label: "Operacional",
    items: [
      { id: "periodos", label: "Periodos", icon: CalendarDays },
      { id: "bulk-import", label: "Importación masiva", icon: Upload },
      { id: "byok", label: "BYOK Keys", icon: Key },
    ],
  },
]

export function Router(): ReactNode {
  const [current, setCurrent] = useState<Route>("home")

  const navigate = (to: Route) => setCurrent(to)

  return (
    <div className="min-h-screen flex bg-surface-alt">
      <Sidebar
        navGroups={NAV_GROUPS}
        headerLabel="AI-Native N4"
        collapsedHeaderLabel="N4"
        storageKey="web-admin-sidebar-collapsed"
        activeItemId={current}
        onNavigate={(id) => navigate(id as Route)}
      />
      <main className="flex-1 overflow-x-hidden">
        <div className="border-b border-border bg-surface-alt px-6 py-3 flex justify-end">
          <TenantSelector />
        </div>
        <div className="container mx-auto p-6 max-w-6xl">
          {current === "home" && <HomePage />}
          {current === "universidades" && <UniversidadesPage />}
          {current === "facultades" && <FacultadesPage />}
          {current === "carreras" && <CarrerasPage />}
          {current === "planes" && <PlanesPage />}
          {current === "materias" && <MateriasPage />}
          {current === "comisiones" && <ComisionesPage />}
          {current === "clasificaciones" && <ClasificacionesPage />}
          {current === "periodos" && <PeriodosPage />}
          {current === "bulk-import" && <BulkImportPage />}
          {current === "auditoria" && <AuditoriaPage />}
          {current === "governance-events" && <GovernanceEventsPage />}
          {current === "byok" && <ByokPage />}
        </div>
      </main>
    </div>
  )
}
