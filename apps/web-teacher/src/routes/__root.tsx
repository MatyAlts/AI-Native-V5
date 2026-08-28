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
import { UserButton } from "@clerk/clerk-react"
import {
  AuditFooter,
  type NavGroup,
  type OnboardingFlow,
  OnboardingProvider,
  Sidebar,
  TourProvider,
  useTour,
} from "@platform/ui"
import {
  Outlet,
  createRootRouteWithContext,
  useNavigate,
  useRouterState,
} from "@tanstack/react-router"
import {
  BarChart3,
  BookOpen,
  Bot,
  CheckSquare,
  ClipboardList,
  Compass,
  Cpu,
  Download,
  FlaskConical,
  FolderOpen,
  GraduationCap,
  Group,
  Home,
  Layers,
  PieChart,
  ShieldAlert,
  TrendingUp,
  Users,
} from "lucide-react"
import { type ReactNode, useCallback, useEffect } from "react"
import { ComisionSelectorRouted } from "../components/ComisionSelectorRouted"
import { TenantSelector } from "../components/TenantSelector"
import { ViewModeToggle } from "../components/ViewModeToggle"
import { docenteOnboarding } from "../onboarding/docenteOnboarding"
import { type EstadoDocente, useEstadoDocente } from "../onboarding/estadoDocente"
import { docenteTour } from "../tour/docenteTour"

const HAS_CLERK = !!import.meta.env.VITE_CLERK_PUBLISHABLE_KEY

/**
 * Comision elegida en el selector, persistida por `ComisionSelectorRouted`. Es el
 * fallback cuando el search de la ruta actual no la trae (rutas con path param, o
 * recarga inicial sin search).
 */
function comisionGuardada(): string | null {
  return typeof window !== "undefined" ? window.localStorage.getItem("selectedComisionId") : null
}

export interface RouterContext {
  /** Función de auth, placeholder hasta integración Keycloak (F8). */
  getToken: () => Promise<string | null>
}

// Exportado SOLO para que un test pueda verificarlo. Ver
// `navegacionAlcanzable.test.ts`: hasta el 2026-08-28 la ruta /activeia
// existia completa y no estaba en ninguno de los 16 items, asi que solo se
// llegaba escribiendo la URL a mano. Un menu es de las pocas cosas que se
// verifican mirando, y por eso nadie lo miro.
export const NAV_GROUPS: NavGroup[] = [
  {
    label: "Inicio",
    items: [{ id: "/", label: "Mis comisiones", icon: Home }],
  },
  {
    label: "Trabajo del docente",
    items: [
      { id: "/unidades", label: "Unidades", icon: Group },
      { id: "/ejercicios", label: "Banco de ejercicios", icon: BookOpen },
      { id: "/tareas-practicas", label: "Trabajos Prácticos", icon: ClipboardList },
      { id: "/materiales", label: "Materiales", icon: FolderOpen },
      { id: "/correcciones", label: "Correcciones", icon: CheckSquare },
      // Va DEBAJO de Correcciones porque es su continuacion: acá el docente
      // conecta su cuenta de Active-IA y sincroniza las rubricas, que es lo
      // que habilita el boton "Corregir con IA" de esa pantalla.
      //
      // La ruta existia y estaba completa desde que se armo el epic, pero no
      // figuraba en ninguno de los 16 items del menu: solo se llegaba
      // escribiendo la URL. Por eso nadie la habia usado nunca — y por eso la
      // doc decia que jamas se habia sincronizado una rubrica. No estaba
      // rota: no tenia puerta.
      //
      // El `comisionId` no hace falta declararlo acá: el sidebar lo arrastra
      // entre rutas (ver `carry` mas abajo), que es lo que evita que esta
      // ruta —que lo exige en el `beforeLoad`— rebote al home.
      { id: "/activeia", label: "Active-IA", icon: Bot },
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
      {
        id: "/entrenamiento-recalibracion",
        label: "Entrenamiento-Recalibración",
        icon: GraduationCap,
      },
      { id: "/interrater", label: "Codificación (inter-jueces)", icon: Users },
      { id: "/instrumentos-cohorte", label: "Instrumentos research", icon: FlaskConical },
    ],
  },
  {
    label: "Operacional",
    items: [
      { id: "/export", label: "Exportar", icon: Download },
      { id: "/uso-ia", label: "Uso de IA", icon: Cpu },
    ],
  },
]

/** Dispara el tour en el primer ingreso. Vive adentro del provider para poder usar el hook. */
function TourAutoStart() {
  const { maybeStart } = useTour()
  useEffect(() => {
    maybeStart(docenteTour)
  }, [maybeStart])
  return null
}

/**
 * Mismo flow, sin carteles. Es como apagamos el onboarding por estado mientras corre un
 * tour: los dos mecanismos son ciegos entre si, y el arbitraje corresponde a esta capa,
 * que es la unica que conoce a los dos.
 *
 * Conserva el `id` del flow real a proposito: es el prefijo de los descartes en
 * localStorage. Con otro id, alternar de uno al otro leeria un catalogo vacio y le
 * resucitaria al docente carteles que ya habia cerrado.
 */
const DOCENTE_SIN_CARTELES: OnboardingFlow<EstadoDocente> = {
  id: docenteOnboarding.id,
  hints: [],
}

/**
 * Onboarding por estado. Vive ADENTRO del TourProvider a proposito: necesita saber si
 * hay un tour corriendo para no abrir un cartel encima del recorrido guiado. Los dos
 * iluminan el mismo sidebar, asi que superpuestos no son el doble de ayuda: son ruido.
 */
function OnboardingDocente({
  comisionActivaId,
  route,
  children,
}: {
  comisionActivaId: string | null
  route: string
  children: ReactNode
}) {
  const { activo } = useTour()
  const estado = useEstadoDocente(comisionActivaId)
  return (
    <OnboardingProvider
      flow={activo ? DOCENTE_SIN_CARTELES : docenteOnboarding}
      estado={estado}
      route={route}
    >
      {children}
    </OnboardingProvider>
  )
}

/** Relanzar el tour a mano. El primer ingreso pasa una vez; las dudas vuelven. */
function TourRelanzar() {
  const { start, activo } = useTour()
  if (activo) return null
  return (
    <button
      type="button"
      onClick={() => start(docenteTour)}
      title="Ver el tour de nuevo"
      className="text-muted hover:text-ink focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-border-strong"
    >
      <Compass className="h-4 w-4" aria-hidden="true" />
      <span className="sr-only">Ver el tour de nuevo</span>
    </button>
  )
}

function RootLayout() {
  const navigate = useNavigate()
  const search = useRouterState({
    select: (s) => s.location.search as Record<string, unknown>,
  })
  // Ruta actual sin el basepath del router (`/teacher`): es lo que los carteles del
  // onboarding comparan contra su `route`. El motor no conoce el router.
  const rutaActual = useRouterState({
    select: (s) => s.matches[s.matches.length - 1]?.fullPath ?? "/",
  })
  const searchComisionId = typeof search.comisionId === "string" ? search.comisionId : null
  const comisionActivaId = searchComisionId ?? comisionGuardada()
  const handleNavigate = useCallback(
    (id: string) => {
      // El sidebar navega entre rutas que requieren `comisionId` (search) y rutas
      // que no. Preservar el comisionId actual entre clicks evita el loop al home.
      // Fallback a localStorage cuando venimos de /comision/$id (path param) o de
      // recarga inicial sin search.
      const carry = searchComisionId ?? comisionGuardada()
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

  // El tour usa EL MISMO navegador que el sidebar, y no uno propio: `navigate({ to })`
  // sin `search` DESCARTA los query params, y ahi vive el `comisionId` — el estado
  // global que consume `ComisionSelectorRouted` y del que dependen /ejercicios,
  // /tareas-practicas y /correcciones (sin el redirigen al home). Un tour con su
  // propio navegador le borraba al docente la comision elegida y se rebotaba solo.

  return (
    <TourProvider navigate={handleNavigate}>
      <OnboardingDocente comisionActivaId={comisionActivaId} route={rutaActual}>
        <TourAutoStart />
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
              <TourRelanzar />
              <span className="w-px h-5 bg-border" aria-hidden="true" />
              <ViewModeToggle />
              <span className="w-px h-5 bg-border" aria-hidden="true" />
              <TenantSelector />
              <span className="w-px h-5 bg-border" aria-hidden="true" />
              <ComisionSelectorRouted />
              {HAS_CLERK && (
                <>
                  <span className="w-px h-5 bg-border" aria-hidden="true" />
                  <UserButton afterSignOutUrl="/teacher/" />
                </>
              )}
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
      </OnboardingDocente>
    </TourProvider>
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
