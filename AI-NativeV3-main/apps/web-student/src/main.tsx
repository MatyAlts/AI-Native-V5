import { ClerkProvider, useAuth, useUser } from "@clerk/clerk-react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { RouterProvider, createRouter } from "@tanstack/react-router"
import { StrictMode, useEffect } from "react"
import { createRoot } from "react-dom/client"
import "./index.css"
import { routeTree } from "./routeTree.gen"
import {
  DEV_NO_CLERK,
  SELECTED_TENANT_STORAGE_KEY,
  getCurrentUserUuid,
  setDevStudentId,
} from "./auth"

const CLERK_PUBLISHABLE_KEY = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY as string

const originalFetch = window.fetch.bind(window)
const apiBase = (import.meta.env.VITE_API_URL ?? "").replace(/\/$/, "")
window.fetch = async (input, init) => {
  const rawUrl = typeof input === "string" ? input : input instanceof URL ? input.href : input.url
  const isRelativeApi = rawUrl.startsWith("/api/")
  const targetUrl = isRelativeApi && apiBase ? `${apiBase}${rawUrl}` : rawUrl

  if (!isRelativeApi) return originalFetch(targetUrl, init)
  const headers = new Headers(init?.headers ?? {})
  const tenantId = localStorage.getItem(SELECTED_TENANT_STORAGE_KEY)
  if (tenantId) headers.set("x-selected-tenant", tenantId)
  const userUuid = getCurrentUserUuid()
  if (userUuid) headers.set("x-user-id", userUuid)
  // Token de Clerk: el gateway lo valida y deriva la identidad real. En dev
  // sin Clerk, window.Clerk no existe y se usan los headers X-* de arriba.
  if (!headers.has("Authorization")) {
    try {
      const clerk = (
        window as unknown as {
          Clerk?: {
            loaded?: boolean
            load?: () => Promise<unknown>
            session?: { getToken: () => Promise<string | null> }
          }
        }
      ).Clerk
      // Esperar a que Clerk hidrate la sesión antes de pedir el token: evita
      // requests sin Bearer en el primer render (el nginx los rechazaría con
      // Basic Auth). En dev sin Clerk, window.Clerk no existe → se saltea.
      if (clerk && clerk.loaded === false && clerk.load) await clerk.load()
      const token = await clerk?.session?.getToken()
      if (token) headers.set("Authorization", `Bearer ${token}`)
    } catch {
      /* dev sin Clerk: sin token */
    }
  }
  return originalFetch(targetUrl, { ...init, headers })
}

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
        <DevApp />
      </QueryClientProvider>
    ) : (
      <ClerkProvider publishableKey={CLERK_PUBLISHABLE_KEY}>
        <QueryClientProvider client={queryClient}>
          <InnerApp />
        </QueryClientProvider>
      </ClerkProvider>
    )}
  </StrictMode>,
)
