import { ClerkProvider, useAuth, useUser } from "@clerk/clerk-react"
import { installApiFetchInterceptor } from "@platform/auth-client/fetch"
import { ErrorBoundary } from "@platform/ui"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { RouterProvider, createRouter } from "@tanstack/react-router"
import { StrictMode, useEffect } from "react"
import { createRoot } from "react-dom/client"
import "./index.css"
import {
  DEV_NO_CLERK,
  SELECTED_TENANT_STORAGE_KEY,
  getCurrentUserUuid,
  setDevStudentId,
} from "./auth"
import { routeTree } from "./routeTree.gen"

const CLERK_PUBLISHABLE_KEY = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY as string

// Interceptor de fetch compartido (P-18/P-13/P-12). Con un usuario logueado
// nunca se manda un request /api/ sin Bearer (evita caer al user_id por defecto
// del nginx -> identidad cruzada / datos de otra comision). El token de Clerk lo
// valida el gateway y deriva la identidad real. Piezas especificas del student:
// x-selected-tenant y x-user-id (el pseudonym derivado del Clerk user.id).
installApiFetchInterceptor({
  apiBase: (import.meta.env.VITE_API_URL ?? "") as string,
  devNoClerk: DEV_NO_CLERK,
  dynamicHeaders: () => ({
    "x-selected-tenant": localStorage.getItem(SELECTED_TENANT_STORAGE_KEY),
    "x-user-id": getCurrentUserUuid(),
  }),
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

  // Re-vincula la identidad de Clerk con las comisiones que el admin asigno por
  // email (POST /users/me/profile, idempotente: tambien llena el perfil del
  // alumno). Si resulta STAFF de alguna comision (es docente), lo manda al panel
  // docente automaticamente. Si no, se queda aca, en el panel de alumno, donde
  // puede ingresar el codigo de su comision. Optimista: no bloquea al alumno
  // (caso comun); solo el docente ve un instante esta pantalla antes de redirigir.
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
          /* best-effort */
        }
      }
      try {
        const r = await fetch("/api/v1/comisiones/mis")
        if (!r.ok) return
        const data = await r.json()
        const items = data?.data ?? data?.items ?? []
        if (!cancelled && Array.isArray(items) && items.length > 0) {
          window.location.replace("/teacher/")
        }
      } catch {
        /* se queda en el panel de alumno */
      }
    })()
    return () => {
      cancelled = true
    }
  }, [user])

  return <RouterProvider router={router} context={{ getToken }} />
}

// Dev sin Clerk: fija el alumno hardcodeado y monta el router sin token.
function DevApp() {
  setDevStudentId()
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
        <QueryClientProvider client={queryClient}>
          <ErrorBoundary>
            <InnerApp />
          </ErrorBoundary>
        </QueryClientProvider>
      </ClerkProvider>
    )}
  </StrictMode>,
)
