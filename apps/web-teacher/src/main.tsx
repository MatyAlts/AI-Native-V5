import { ClerkProvider, SignIn, SignedIn, SignedOut, useAuth, useUser } from "@clerk/clerk-react"
import { installApiFetchInterceptor } from "@platform/auth-client/fetch"
import { ErrorBoundary } from "@platform/ui"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { RouterProvider, createRouter } from "@tanstack/react-router"
import { StrictMode, useEffect, useState } from "react"
import { createRoot } from "react-dom/client"
import "./index.css"
import { SELECTED_TENANT_STORAGE_KEY } from "./constants"
import { comisionesApi } from "./lib/api"
import { routeTree } from "./routeTree.gen"

const CLERK_PUBLISHABLE_KEY = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY as string
// Dev sin Clerk: si no hay publishable key, la identidad (docente) la inyecta
// el proxy de Vite y el backend corre con dev_trust_headers.
const DEV_NO_CLERK = !CLERK_PUBLISHABLE_KEY

// Timeouts del cliente. El default de 25s (P-12) existe para que un backend
// colgado no cuelgue la UI, pero hay endpoints legitimamente largos: el wizard
// IA de ejercicios genera un borrador completo (ADR-048) con UNA llamada al
// LLM, sin streaming, y puede tardar minutos. No entra por la exencion de SSE,
// asi que con 25s el cliente cortaba una request que el backend seguia
// sirviendo y el docente veia "Request timeout tras 25000ms".
//
// La cascada tiene que ir de MAS a MENOS hacia adentro — si una capa externa
// corta antes que una interna, el error que ve el usuario es opaco:
//
//   cliente 300s  >  api-gateway 270s  >  academic-service -> ai-gateway 240s
//
// Al tocar cualquiera de estos, mover los tres.
const DEFAULT_TIMEOUT_MS = 25_000
const LONG_RUNNING_TIMEOUT_MS = 300_000
const LONG_RUNNING_PATHS = ["/api/v1/ejercicios/generate"]

// Interceptor de fetch compartido (P-18/P-13/P-12). Antes, el patch
// best-effort dejaba salir el request SIN Bearer cuando la sesion de Clerk aun
// no estaba lista -> caia a dev_trust y usaba el user_id por defecto del nginx
// -> 403 de identidad cruzada (assert_comision_access). El helper espera el
// token (con timeout corto) y solo sale sin Bearer si Clerk confirma que no hay
// sesion o es dev sin Clerk. La unica pieza especifica del teacher es el header
// x-selected-tenant.
installApiFetchInterceptor({
  apiBase: (import.meta.env.VITE_API_URL ?? "") as string,
  devNoClerk: DEV_NO_CLERK,
  dynamicHeaders: () => ({
    "x-selected-tenant": window.localStorage.getItem(SELECTED_TENANT_STORAGE_KEY),
  }),
  requestTimeoutMs: (url) =>
    LONG_RUNNING_PATHS.some((path) => url.includes(path))
      ? LONG_RUNNING_TIMEOUT_MS
      : DEFAULT_TIMEOUT_MS,
})

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 60_000,
      retry: 1,
    },
  },
})

const router = createRouter({
  routeTree,
  basepath: "/teacher",
  context: { getToken: async () => null },
  defaultPreload: "intent",
})

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router
  }
}

function InnerApp() {
  const { getToken } = useAuth()
  const { user } = useUser()
  // null = resolviendo; true = staff de al menos una comision; false = no docente.
  const [esDocente, setEsDocente] = useState<boolean | null>(null)

  // Re-vincula la identidad de Clerk con las comisiones que el admin le asigno
  // por email (POST /users/me/profile, idempotente) y RECIEN DESPUES resuelve si
  // es docente. Modelo: todos arrancan como alumno; solo es docente quien el
  // admin asigno a una comision (existe en usuarios_comision). El orden importa:
  // si consultaramos /comisiones/mis antes de re-vincular, daria vacio y
  // rebotaria a un docente real.
  useEffect(() => {
    if (!user) return
    let cancelled = false
    const email = user.primaryEmailAddress?.emailAddress ?? null
    const fullName =
      user.fullName ?? [user.firstName, user.lastName].filter(Boolean).join(" ").trim() ?? null
    ;(async () => {
      if (email) {
        try {
          await fetch("/api/v1/users/me/profile", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ full_name: fullName || null, email }),
          })
        } catch {
          /* best-effort: la re-vinculacion no debe bloquear el chequeo siguiente */
        }
      }
      try {
        const res = await comisionesApi.listMine()
        if (!cancelled) setEsDocente(res.items.length > 0)
      } catch {
        if (!cancelled) setEsDocente(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [user])

  // No es docente (sin comisiones asignadas): lo mandamos directo al panel de
  // alumno (`/`), donde puede ingresar el codigo de su comision. Modelo: todos
  // son alumnos hasta que el admin los asigne como docentes de una comision.
  // replace() para no dejar /teacher en el historial (evita volver con "atras").
  useEffect(() => {
    if (esDocente === false) window.location.replace("/")
  }, [esDocente])

  if (esDocente !== true) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-canvas text-sm text-muted">
        {esDocente === null ? "Verificando tu acceso…" : "Te llevamos a tu pantalla…"}
      </div>
    )
  }

  return <RouterProvider router={router} context={{ getToken }} />
}

// Dev sin Clerk: router sin token (el proxy mete los headers de identidad).
function DevApp() {
  return <RouterProvider router={router} context={{ getToken: async () => null }} />
}

const rootElement = document.getElementById("root")
if (!rootElement) throw new Error("Missing #root element")

createRoot(rootElement).render(
  <StrictMode>
    {DEV_NO_CLERK ? (
      <QueryClientProvider client={queryClient}>
        <ErrorBoundary>
          <DevApp />
        </ErrorBoundary>
      </QueryClientProvider>
    ) : (
      <ClerkProvider publishableKey={CLERK_PUBLISHABLE_KEY}>
        {/* Sin sesion: pantalla de login de Clerk. Con sesion: la app (y el
            push de perfil que vincula al docente con sus comisiones). */}
        <SignedOut>
          <div className="min-h-screen flex items-center justify-center bg-canvas">
            {/* forceRedirectUrl: sin esto Clerk redirige a "/" (que es el
                web-student) tras el login. Forzamos quedarnos en /teacher. */}
            <SignIn forceRedirectUrl="/teacher/" signUpForceRedirectUrl="/teacher/" />
          </div>
        </SignedOut>
        <SignedIn>
          <QueryClientProvider client={queryClient}>
            <ErrorBoundary>
              <InnerApp />
            </ErrorBoundary>
          </QueryClientProvider>
        </SignedIn>
      </ClerkProvider>
    )}
  </StrictMode>,
)
