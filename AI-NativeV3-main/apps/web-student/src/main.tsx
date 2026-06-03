import { ClerkProvider, useAuth } from "@clerk/clerk-react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { RouterProvider, createRouter } from "@tanstack/react-router"
import { StrictMode } from "react"
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
