import { ClerkProvider, SignIn, SignedIn, SignedOut } from "@clerk/clerk-react"
import { ErrorBoundary } from "@platform/ui"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { StrictMode } from "react"
import { createRoot } from "react-dom/client"
import App from "./App"
import "./index.css"
import { SELECTED_TENANT_STORAGE_KEY } from "./constants"

const CLERK_PUBLISHABLE_KEY = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY as string
// Dev sin Clerk: si no hay publishable key, la identidad la inyecta el proxy
// de Vite (x-user-id/x-tenant-id/x-user-roles) y el backend corre con
// dev_trust_headers. Permite levantar el front sin cuenta Clerk.
const DEV_NO_CLERK = !CLERK_PUBLISHABLE_KEY

const originalFetch = window.fetch.bind(window)
const apiBase = (import.meta.env.VITE_API_URL ?? "").replace(/\/$/, "")

// Espera robusta del token de Clerk para requests /api/ (mismo patrón que
// web-teacher). Sin esto, el panel admin mandaba los requests SIN Bearer y el
// gateway respondía 401 a todo (no hay proxy de Vite en prod que inyecte X-*).
type ClerkLike = {
  loaded?: boolean
  load?: () => Promise<unknown>
  user?: unknown
  session?: { getToken: () => Promise<string | null> } | null
}
async function getClerkToken(): Promise<string | null> {
  if (DEV_NO_CLERK) return null
  const deadlineMs = Date.now() + 5000
  const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms))
  const readClerk = () => (window as unknown as { Clerk?: ClerkLike }).Clerk
  let clerk = readClerk()
  while (!clerk && Date.now() < deadlineMs) {
    await sleep(50)
    clerk = readClerk()
  }
  if (!clerk) return null
  if (clerk.loaded === false && clerk.load) await clerk.load()
  while (Date.now() < deadlineMs) {
    const token = await clerk.session?.getToken().catch(() => null)
    if (token) return token
    if (clerk.loaded && !clerk.session && !clerk.user) return null
    await sleep(50)
  }
  return null
}

window.fetch = async (input, init) => {
  const rawUrl = typeof input === "string" ? input : input instanceof URL ? input.href : input.url
  const isRelativeApi = rawUrl.startsWith("/api/")
  const targetUrl = isRelativeApi && apiBase ? `${apiBase}${rawUrl}` : rawUrl

  if (!isRelativeApi) return originalFetch(targetUrl, init)
  const headers = new Headers(init?.headers ?? {})
  const tenantId = window.localStorage.getItem(SELECTED_TENANT_STORAGE_KEY)
  if (tenantId) headers.set("x-selected-tenant", tenantId)
  if (!headers.has("Authorization")) {
    const token = await getClerkToken()
    if (token) headers.set("Authorization", `Bearer ${token}`)
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

const rootElement = document.getElementById("root")
if (!rootElement) throw new Error("Missing #root element")

const appTree = (
  <QueryClientProvider client={queryClient}>
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  </QueryClientProvider>
)

createRoot(rootElement).render(
  <StrictMode>
    {DEV_NO_CLERK ? (
      appTree
    ) : (
      <ClerkProvider publishableKey={CLERK_PUBLISHABLE_KEY}>
        {/* Sin sesión: pantalla de login de Clerk. Con sesión: la app. El acceso
            real al panel lo da el rol superadmin (gateway CLERK_ADMIN_EMAILS). */}
        <SignedOut>
          <div className="min-h-screen flex items-center justify-center">
            <SignIn forceRedirectUrl="/admin/" signUpForceRedirectUrl="/admin/" />
          </div>
        </SignedOut>
        <SignedIn>{appTree}</SignedIn>
      </ClerkProvider>
    )}
  </StrictMode>,
)
