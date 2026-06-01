import { ClerkProvider } from "@clerk/clerk-react"
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
window.fetch = (input, init) => {
  const rawUrl = typeof input === "string" ? input : input instanceof URL ? input.href : input.url
  const isRelativeApi = rawUrl.startsWith("/api/")
  const targetUrl = isRelativeApi && apiBase ? `${apiBase}${rawUrl}` : rawUrl

  if (!isRelativeApi) return originalFetch(targetUrl, init)
  const headers = new Headers(init?.headers ?? {})
  const tenantId = window.localStorage.getItem(SELECTED_TENANT_STORAGE_KEY)
  if (tenantId) headers.set("x-selected-tenant", tenantId)
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
    <App />
  </QueryClientProvider>
)

createRoot(rootElement).render(
  <StrictMode>
    {DEV_NO_CLERK ? (
      appTree
    ) : (
      <ClerkProvider publishableKey={CLERK_PUBLISHABLE_KEY}>{appTree}</ClerkProvider>
    )}
  </StrictMode>,
)
